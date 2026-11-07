"""Customers and products: search, create, edit, delete, activate and deactivate.

The pages and the API both use these, so the rules live in one place.

Every function that changes data owns its transaction: it commits on success and rolls back
on any error. Only admins may call the changing functions; the routes check that
(admin_required) before calling them.
"""
import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.errors import ConflictError, NotFoundError, ValidationError
from app.extensions import db
from app.models import (
    MOVEMENT_OPENING,
    Customer,
    Product,
    SalesOrder,
    SalesOrderItem,
    StockMovement,
)
from app.services.pricing import parse_price, parse_stock_quantity
from app.services.stock import change_stock

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

# Loose checks only: something@something.something, and digits with + - or spaces.
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MOBILE_PATTERN = re.compile(r"\+?[0-9][0-9 \-]{5,19}")


# ---------------------------------------------------------------------------
# Search and lookup
# ---------------------------------------------------------------------------

def _paginate(query, page, per_page):
    """Run query for one page. Returns (rows, total). Bad page numbers fall back to safe values."""
    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or DEFAULT_PER_PAGE), 1), MAX_PER_PAGE)
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(query.limit(per_page).offset((page - 1) * per_page)).all()
    return rows, total, page, per_page


def search_products(q=None, category=None, status="active", page=1, per_page=DEFAULT_PER_PAGE):
    """Products matching q (code or name), category and status ("active", "inactive" or "all").

    Returns (products, total, page, per_page), ordered by code.
    """
    query = select(Product)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Product.code.like(like), Product.name.like(like)))
    if category:
        query = query.where(Product.category == category)
    if status == "active":
        query = query.where(Product.is_active.is_(True))
    elif status == "inactive":
        query = query.where(Product.is_active.is_(False))
    return _paginate(query.order_by(Product.code), page, per_page)


def search_customers(q=None, status="active", page=1, per_page=DEFAULT_PER_PAGE):
    """Customers matching q (name, email or mobile) and status ("active", "inactive" or "all").

    Returns (customers, total, page, per_page), ordered by name.
    """
    query = select(Customer)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(Customer.name.like(like), Customer.email.like(like), Customer.mobile.like(like))
        )
    if status == "active":
        query = query.where(Customer.is_active.is_(True))
    elif status == "inactive":
        query = query.where(Customer.is_active.is_(False))
    return _paginate(query.order_by(Customer.name), page, per_page)


def product_categories():
    """Distinct categories, for the filter dropdown."""
    return db.session.scalars(select(Product.category).distinct().order_by(Product.category)).all()


def active_customers():
    """Every active customer by name, for the order form's dropdown."""
    return db.session.scalars(
        select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.name)
    ).all()


def active_products():
    """Every active product by code, for the order form's dropdowns."""
    return db.session.scalars(
        select(Product).where(Product.is_active.is_(True)).order_by(Product.code)
    ).all()


def all_products():
    """Every product by code, active or not, for the stock adjustment dropdown."""
    return db.session.scalars(select(Product).order_by(Product.code)).all()


def product_movements(product_id, limit=20):
    """A product's latest stock movements, newest first."""
    return db.session.scalars(
        select(StockMovement)
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(limit)
    ).all()


def get_customer(customer_id):
    customer = db.session.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


def get_product(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found.")
    return product


# ---------------------------------------------------------------------------
# Input checks
# ---------------------------------------------------------------------------

def _text(data, field):
    """A form field as a trimmed string ("" if missing)."""
    return (data.get(field) or "").strip()


def _check_length(errors, field, value, max_length, required):
    if required and not value:
        errors[field] = "Required."
    elif len(value) > max_length:
        errors[field] = f"At most {max_length} characters."


def _clean_customer(data):
    """Check customer form data. Returns a dict of clean values or raises ValidationError.

    Collects every problem at once, so the form can show them all next to their fields.
    """
    errors = {}
    name = _text(data, "name")
    email = _text(data, "email").lower()
    mobile = _text(data, "mobile")
    city = _text(data, "city")

    _check_length(errors, "name", name, 100, required=True)
    _check_length(errors, "email", email, 255, required=False)
    _check_length(errors, "mobile", mobile, 20, required=False)
    _check_length(errors, "city", city, 100, required=False)
    if email and "email" not in errors and not EMAIL_PATTERN.fullmatch(email):
        errors["email"] = "Enter a valid email address."
    if mobile and "mobile" not in errors and not MOBILE_PATTERN.fullmatch(mobile):
        errors["mobile"] = "Use digits (spaces, - and a leading + are allowed), at least 7."

    if errors:
        raise ValidationError("Please fix the problems below.", errors)
    # Empty optional fields are stored as NULL, not "".
    return {"name": name, "email": email or None, "mobile": mobile or None, "city": city or None}


def _clean_product(data, product_id=None, with_stock=False):
    """Check product form data. Returns a dict of clean values or raises ValidationError.

    product_id is the product being edited, so its own code doesn't count as a duplicate.
    with_stock=True also checks "stock_quantity". Only creating a product sets stock this
    way; after that, stock changes only through stock adjustments and orders.
    """
    errors = {}
    values = {
        "code": _text(data, "code"),
        "name": _text(data, "name"),
        "category": _text(data, "category"),
    }
    _check_length(errors, "code", values["code"], 50, required=True)
    _check_length(errors, "name", values["name"], 150, required=True)
    _check_length(errors, "category", values["category"], 100, required=True)

    try:
        values["price"] = parse_price(data.get("price"))
    except ValidationError as error:
        errors.update(error.details)

    if with_stock:
        try:
            values["stock_quantity"] = parse_stock_quantity(data.get("stock_quantity"))
        except ValidationError as error:
            errors.update(error.details)

    if "code" not in errors and _code_taken(values["code"], product_id):
        errors["code"] = _duplicate_code_message(values["code"])

    if errors:
        raise ValidationError("Please fix the problems below.", errors)
    return values


def _code_taken(code, product_id=None):
    """True if another product already has this code. MySQL compares it ignoring case."""
    query = select(Product.id).where(Product.code == code)
    if product_id is not None:
        query = query.where(Product.id != product_id)
    return db.session.scalar(query.limit(1)) is not None


def _duplicate_code_message(code):
    return f"Code {code} is already used by another product."


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def create_customer(data):
    """Create an active customer from form data. Returns the customer."""
    try:
        customer = Customer(is_active=True, **_clean_customer(data))
        db.session.add(customer)
        db.session.commit()
        return customer
    except Exception:
        db.session.rollback()
        raise


def update_customer(customer_id, data):
    """Change a customer's name, email, mobile and city. Returns the customer."""
    try:
        customer = get_customer(customer_id)
        for field, value in _clean_customer(data).items():
            setattr(customer, field, value)
        db.session.commit()
        return customer
    except Exception:
        db.session.rollback()
        raise


def delete_customer(customer_id):
    """Delete a customer that no order uses. Otherwise refuse and suggest deactivating."""
    try:
        customer = get_customer(customer_id)
        used = db.session.scalar(
            select(SalesOrder.id).where(SalesOrder.customer_id == customer.id).limit(1)
        )
        if used is not None:
            raise ConflictError(
                f"{customer.name} has orders, so it can't be deleted. Deactivate it instead."
            )
        db.session.delete(customer)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def set_customer_active(customer_id, is_active):
    """Activate or deactivate a customer. Inactive customers can't be picked for new orders."""
    try:
        customer = get_customer(customer_id)
        customer.is_active = is_active
        db.session.commit()
        return customer
    except Exception:
        db.session.rollback()
        raise


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def create_product(data, user):
    """Create an active product from form data. Returns the product.

    The product starts at zero stock. Opening stock, if any, goes through change_stock(),
    so it is recorded as an 'opening' movement, like every other stock change.
    """
    try:
        values = _clean_product(data, with_stock=True)
        opening_stock = values.pop("stock_quantity")
        product = Product(is_active=True, stock_quantity=0, **values)
        db.session.add(product)
        if opening_stock > 0:
            change_stock(product, opening_stock, MOVEMENT_OPENING, user, "Opening stock")
        db.session.commit()
        return product
    except IntegrityError:
        # The unique index caught a duplicate code saved between our check and our commit.
        db.session.rollback()
        code = _text(data, "code")
        raise ValidationError("Please fix the problems below.", {"code": _duplicate_code_message(code)})
    except Exception:
        db.session.rollback()
        raise


def update_product(product_id, data):
    """Change a product's code, name, category and price. Returns the product.

    Stock is not edited here: it changes only through stock adjustments and orders, so every
    change has a movement row. Existing orders keep their stored rate if the price changes.
    """
    try:
        product = get_product(product_id)
        for field, value in _clean_product(data, product_id=product.id).items():
            setattr(product, field, value)
        db.session.commit()
        return product
    except IntegrityError:
        db.session.rollback()
        code = _text(data, "code")
        raise ValidationError("Please fix the problems below.", {"code": _duplicate_code_message(code)})
    except Exception:
        db.session.rollback()
        raise


def delete_product(product_id):
    """Delete a product that no order item or stock movement uses. Otherwise refuse.

    A product created with opening stock already has a movement, so it can only be deactivated.
    """
    try:
        product = get_product(product_id)
        in_order = db.session.scalar(
            select(SalesOrderItem.id).where(SalesOrderItem.product_id == product.id).limit(1)
        )
        has_movement = db.session.scalar(
            select(StockMovement.id).where(StockMovement.product_id == product.id).limit(1)
        )
        if in_order is not None or has_movement is not None:
            raise ConflictError(
                f"{product.code} is used by orders or stock history, so it can't be deleted. "
                "Deactivate it instead."
            )
        db.session.delete(product)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def set_product_active(product_id, is_active):
    """Activate or deactivate a product. Inactive products can't be added to orders."""
    try:
        product = get_product(product_id)
        product.is_active = is_active
        db.session.commit()
        return product
    except Exception:
        db.session.rollback()
        raise
