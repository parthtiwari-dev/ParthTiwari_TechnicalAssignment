"""Database tables, as SQLAlchemy models.

Rules the database itself enforces (so bad data can't get in even if app code has a bug):
- unique: user email, product code, order number, one row per product per order
- CHECK: price >= 0, stock >= 0, quantity > 0, discount between 0 and 20, and the allowed
  values for role, order status and movement type
- foreign keys use ON DELETE RESTRICT: MySQL refuses to delete a customer, product or user
  that an order or stock movement still points to

Money columns are DECIMAL(12,2). Python reads them as Decimal, never float.

Text is compared the MySQL 8 default way (utf8mb4_0900_ai_ci: case and accents ignored),
except products.code, which uses utf8mb4_0900_as_ci: case is ignored but accents count.
So PRD-1 and prd-1 are the same code, while CAFE-1 and CAFÉ-1 are two different codes.
"""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

ROLE_ADMIN = "admin"
ROLE_SALES = "sales"

STATUS_DRAFT = "draft"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"

MOVEMENT_OPENING = "opening"
MOVEMENT_ADJUSTMENT = "adjustment"
MOVEMENT_SALE = "sale"
MOVEMENT_CANCELLATION = "cancellation"

MONEY = db.Numeric(12, 2)
# Case-insensitive, accent-sensitive. Python's str.lower() gives the same answer for normal
# codes, so the product form, the CSV import and the unique index all agree.
CODE_COLLATION = "utf8mb4_0900_as_ci"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.CheckConstraint("role IN ('admin', 'sales')", name="role_valid"),
    )

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(255), index=True)
    mobile = db.Column(db.String(20), index=True)
    city = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50, collation=CODE_COLLATION), nullable=False, unique=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False, index=True)
    price = db.Column(MONEY, nullable=False)
    # Always change this through services.stock.change_stock(), so a movement row is written too.
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.CheckConstraint("price >= 0", name="price_not_negative"),
        db.CheckConstraint("stock_quantity >= 0", name="stock_not_negative"),
    )


class SalesOrder(db.Model):
    __tablename__ = "sales_orders"

    id = db.Column(db.Integer, primary_key=True)
    # Set right after the first insert, from the id: "SO-000123". Null only inside that transaction.
    order_number = db.Column(db.String(20), unique=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False, default=STATUS_DRAFT)
    discount_percent = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    subtotal = db.Column(MONEY, nullable=False, default=0)
    discount_amount = db.Column(MONEY, nullable=False, default=0)
    grand_total = db.Column(MONEY, nullable=False, default=0)
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    customer = db.relationship("Customer")
    creator = db.relationship("User")
    items = db.relationship(
        "SalesOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="SalesOrderItem.id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled')", name="status_valid"
        ),
        db.CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 20", name="discount_range"
        ),
        # Reports filter confirmed orders by date.
        db.Index("ix_sales_orders_status_order_date", "status", "order_date"),
    )


class SalesOrderItem(db.Model):
    __tablename__ = "sales_order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity = db.Column(db.Integer, nullable=False)
    # The product's price when it was added. Copied, so later price changes don't alter the order.
    rate = db.Column(MONEY, nullable=False)
    amount = db.Column(MONEY, nullable=False)

    order = db.relationship("SalesOrder", back_populates="items")
    product = db.relationship("Product")

    __table_args__ = (
        # One row per product per order. This unique key also serves as the index on order_id.
        db.UniqueConstraint("order_id", "product_id"),
        db.CheckConstraint("quantity > 0", name="quantity_positive"),
        db.CheckConstraint("rate >= 0", name="rate_not_negative"),
    )


class StockMovement(db.Model):
    """One line of the stock 'bank statement'. products.stock_quantity is the balance."""

    __tablename__ = "stock_movements"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type = db.Column(db.String(20), nullable=False)
    # Positive adds stock, negative removes it.
    quantity_change = db.Column(db.Integer, nullable=False)
    order_id = db.Column(
        db.Integer, db.ForeignKey("sales_orders.id", ondelete="RESTRICT"), index=True
    )
    reason = db.Column(db.String(255), nullable=False)
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    product = db.relationship("Product")
    order = db.relationship("SalesOrder")
    creator = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "movement_type IN ('opening', 'adjustment', 'sale', 'cancellation')",
            name="movement_type_valid",
        ),
        db.CheckConstraint("quantity_change <> 0", name="change_not_zero"),
        # Movement history is read per product, newest first.
        db.Index("ix_stock_movements_product_id_created_at", "product_id", "created_at"),
    )
