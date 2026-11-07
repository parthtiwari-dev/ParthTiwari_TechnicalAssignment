"""Runs sql/queries.sql against the test database with known data and checks each result."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.extensions import db
from app.services.orders import cancel_order, confirm_order

QUERIES_FILE = Path(__file__).resolve().parent.parent / "sql" / "queries.sql"


def load_statements():
    """The file's statements in order, with comment lines removed, split on ';'."""
    lines = [line for line in QUERIES_FILE.read_text(encoding="utf-8").splitlines()
             if not line.strip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


@pytest.fixture
def sales_data(sales_user, make_customer, make_product, make_order):
    """Confirmed, draft and cancelled orders over three months, plus low-stock products."""
    c = {name: make_customer(name=name) for name in ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Xray"]}
    p = {
        "P1": make_product(code="SQL-P1", price="100.00", stock=100),
        "P2": make_product(code="SQL-P2", price="50.00", stock=100),
        "P3": make_product(code="SQL-P3", price="10.00", stock=100),
        "P4": make_product(code="SQL-P4", price="1.00", stock=100),
        "LOW": make_product(code="SQL-LOW", stock=3),
        "LOW_INACTIVE": make_product(code="SQL-LOWX", stock=9, is_active=False),
        "AT_THRESHOLD": make_product(code="SQL-TEN", stock=10),
    }

    def confirmed(customer, lines, on, discount="0"):
        order = make_order(sales_user, customer, lines, discount)
        confirm_order(order.id, sales_user)
        order.order_date = on
        db.session.commit()
        return order

    confirmed(c["Alpha"], [(p["P1"], 5)], date(2026, 1, 15))                           # 500.00
    confirmed(c["Alpha"], [(p["P2"], 2)], date(2026, 2, 10))                           # 100.00
    confirmed(c["Bravo"], [(p["P1"], 3), (p["P2"], 4)], date(2026, 2, 20), "10")       # 500 - 10% = 450.00
    confirmed(c["Charlie"], [(p["P3"], 20)], date(2026, 2, 25))                        # 200.00
    confirmed(c["Xray"], [(p["P4"], 1)], date(2026, 3, 1))                             # 1.00

    # Echo: a big order, confirmed then cancelled. Must not count anywhere in sales.
    cancelled = confirmed(c["Echo"], [(p["P1"], 50)], date(2026, 1, 20))
    cancel_order(cancelled.id, sales_user)
    # Foxtrot: a draft only. Must not count in sales.
    make_order(sales_user, c["Foxtrot"], [(p["P1"], 10)])
    # Delta: never orders.


def run_all(statements):
    """Run every statement on one connection (so SET @threshold carries over). Returns the results."""
    results = []
    for statement in statements:
        result = db.session.execute(text(statement))
        results.append(result.mappings().all() if result.returns_rows else None)
    db.session.rollback()
    return results


def test_file_has_five_queries_and_the_threshold_variable():
    statements = load_statements()
    assert len(statements) == 6
    assert statements[4] == "SET @threshold = 10"


def test_queries_return_the_expected_rows(sales_data):
    top_customers, top_products, never_ordered, monthly, _set, low_stock = run_all(load_statements())

    # 1. Top 3 customers by confirmed grand total. Echo's cancelled 5000 doesn't count.
    assert [(row["name"], row["confirmed_orders"], row["total_sales"]) for row in top_customers] == [
        ("Alpha", 2, Decimal("600.00")),
        ("Bravo", 1, Decimal("450.00")),
        ("Charlie", 1, Decimal("200.00")),
    ]

    # 2. Top 3 products by quantity in confirmed orders. The cancelled 50 and draft 10 of P1 don't count.
    assert [(row["code"], row["quantity_sold"]) for row in top_products] == [
        ("SQL-P3", 20),
        ("SQL-P1", 8),
        ("SQL-P2", 6),
    ]

    # 3. Never placed any order. Echo (cancelled) and Foxtrot (draft) did place one.
    assert [row["name"] for row in never_ordered] == ["Delta"]

    # 4. Month-wise confirmed totals.
    assert [(row["order_year"], row["order_month"], row["confirmed_orders"], row["total_sales"])
            for row in monthly] == [
        (2026, 1, 1, Decimal("500.00")),
        (2026, 2, 3, Decimal("750.00")),
        (2026, 3, 1, Decimal("1.00")),
    ]

    # 5. Active products below 10. Not the inactive one, not the one at exactly 10.
    assert [(row["code"], row["stock_quantity"]) for row in low_stock] == [("SQL-LOW", 3)]
