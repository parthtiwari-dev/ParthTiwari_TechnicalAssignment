"""Fill the database with sample data: 3 users, 8 customers, 10 products, 6 orders.

Usage (from the project root, after `flask db upgrade`):

    python scripts/seed.py           # seeds an empty database; refuses if users already exist
    python scripts/seed.py --reset   # deletes ALL rows first, then seeds again

Passwords and emails come from the SEED_* values in .env, so no real credentials are in git.

Orders go through the real services (create_draft_order, confirm_order, cancel_order), so
stock and stock movements are exactly what the app itself would produce. A few confirmed
orders are then moved to earlier dates so the month-wise reports have more than one month.
"""
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

# Let "python scripts/seed.py" find the `app` package in the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select, text  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    MOVEMENT_OPENING,
    ROLE_ADMIN,
    ROLE_SALES,
    Customer,
    Product,
    User,
)
from app.services.orders import cancel_order, confirm_order, create_draft_order  # noqa: E402
from app.services.stock import change_stock  # noqa: E402

CUSTOMERS = [
    # name, email, mobile, city, is_active
    ("Sharma Traders", "accounts@sharmatraders.example", "9824000001", "Ahmedabad", True),
    ("Patel Electronics", "orders@patelelectronics.example", "9824000002", "Surat", True),
    ("Mehta Office Supplies", "buy@mehtaoffice.example", "9824000003", "Vadodara", True),
    ("Gupta Computers", "info@guptacomputers.example", "9824000004", "Rajkot", True),
    ("Iyer Systems", "purchase@iyersystems.example", "9824000005", "Mumbai", True),
    ("Khan & Sons", "khanandsons@example.com", "9824000006", "Pune", True),
    ("Desai Enterprises", "desai.ent@example.com", "9824000007", "Gandhinagar", True),  # never orders
    ("Old Town Stationers", "oldtown@example.com", "9824000008", "Bhavnagar", False),  # inactive
]

PRODUCTS = [
    # code, name, category, price, opening stock, is_active
    ("ACC-001", "Keyboard", "Accessories", "1500.00", 40, True),
    ("ACC-002", "Mouse", "Accessories", "500.00", 60, True),
    ("ACC-003", "USB-C Hub", "Accessories", "1899.00", 4, True),  # low stock
    ("ACC-004", "Laptop Stand", "Accessories", "1250.00", 25, True),
    ("MON-001", "24-inch Monitor", "Monitors", "11499.00", 12, True),
    ("MON-002", "27-inch Monitor", "Monitors", "18999.00", 3, True),  # low stock
    ("MON-003", "Monitor Arm", "Monitors", "2799.00", 15, True),
    ("STO-001", "1 TB SSD", "Storage", "6499.00", 30, True),
    ("STO-002", "64 GB Pen Drive", "Storage", "549.00", 100, True),
    ("STO-003", "500 GB Hard Disk", "Storage", "2999.00", 8, False),  # inactive
]


def require_env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Set {name} in .env first (see .env.example).")
    return value


def delete_all_rows():
    # Children before parents, so foreign keys never block a delete.
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(text(f"DELETE FROM `{table.name}`"))
    db.session.commit()


def make_user(name, email_key, password_key, role):
    user = User(name=name, email=require_env(email_key).strip().lower(), role=role)
    user.set_password(require_env(password_key))
    db.session.add(user)
    return user


def seed():
    admin = make_user("Asha Admin", "SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD", ROLE_ADMIN)
    sales1 = make_user("Ravi Sales", "SEED_SALES_EMAIL", "SEED_SALES_PASSWORD", ROLE_SALES)
    sales2 = make_user("Neha Sales", "SEED_SALES2_EMAIL", "SEED_SALES2_PASSWORD", ROLE_SALES)
    db.session.flush()  # gives the users their ids, needed for created_by below

    customers = {}
    for name, email, mobile, city, is_active in CUSTOMERS:
        customers[name] = Customer(name=name, email=email, mobile=mobile, city=city, is_active=is_active)
        db.session.add(customers[name])

    products = {}
    for code, name, category, price, stock, is_active in PRODUCTS:
        product = Product(
            code=code, name=name, category=category, price=Decimal(price),
            stock_quantity=0, is_active=is_active,
        )
        db.session.add(product)
        # Opening stock goes through change_stock, so it is recorded as a movement.
        change_stock(product, stock, MOVEMENT_OPENING, admin, reason="Opening stock")
        products[code] = product
    db.session.commit()

    def order(user, customer_name, lines, discount):
        items = [{"product_id": products[code].id, "quantity": qty} for code, qty in lines]
        return create_draft_order(user, customers[customer_name].id, items, discount)

    # The example from the assignment: Keyboard 2 x 1500 + Mouse 3 x 500, 10% -> 4050.00
    first = order(sales1, "Sharma Traders", [("ACC-001", 2), ("ACC-002", 3)], "10")
    confirm_order(first.id, sales1)

    second = order(sales1, "Patel Electronics", [("MON-001", 2), ("MON-003", 2), ("ACC-004", 1)], "5")
    confirm_order(second.id, sales1)

    third = order(sales2, "Mehta Office Supplies", [("STO-001", 3), ("STO-002", 10)], "0")
    confirm_order(third.id, sales2)

    fourth = order(sales2, "Sharma Traders", [("ACC-003", 1), ("MON-002", 1)], "12.5")
    confirm_order(fourth.id, admin)

    draft = order(sales1, "Gupta Computers", [("ACC-001", 1), ("STO-002", 5)], "0")

    cancelled = order(sales2, "Iyer Systems", [("ACC-002", 4)], "0")
    confirm_order(cancelled.id, sales2)
    cancel_order(cancelled.id, sales2)

    # Spread confirmed orders over three months so the month-wise report has something to show.
    today = date.today()
    first.order_date = today - timedelta(days=62)
    second.order_date = today - timedelta(days=31)
    db.session.commit()

    print("Seeded: 3 users, 8 customers, 10 products, 6 orders "
          f"(4 confirmed, 1 draft {draft.order_number}, 1 cancelled {cancelled.order_number}).")


def main():
    reset = "--reset" in sys.argv[1:]
    app = create_app()
    with app.app_context():
        if reset:
            delete_all_rows()
        elif db.session.scalar(select(func.count()).select_from(User)) > 0:
            sys.exit("The database already has users. Run with --reset to wipe it and seed again.")
        seed()


if __name__ == "__main__":
    main()
