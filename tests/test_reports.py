"""Reports in services/reports.py and their admin-only pages."""
from datetime import date
from decimal import Decimal

import pytest

from app.errors import ValidationError
from app.extensions import db
from app.services import reports
from app.services.orders import cancel_order, confirm_order
from app.services.stock import adjust_stock


@pytest.fixture
def confirmed_order(sales_user, make_order):
    """confirmed_order(customer, [(product, qty), ...], on=date, discount="0") -> a confirmed order."""
    def _confirmed_order(customer, lines, on, discount="0"):
        order = make_order(sales_user, customer, lines, discount)
        confirm_order(order.id, sales_user)
        order.order_date = on
        db.session.commit()
        return order

    return _confirmed_order


def summary_by_name(rows):
    return {row.name: (row.order_count, row.total_sales) for row in rows}


# ---------- customer sales summary ----------

def test_order_with_several_items_is_counted_once(make_customer, make_product, confirmed_order):
    customer = make_customer(name="Many Items")
    keyboard = make_product(price="1500.00", stock=10)
    mouse = make_product(price="500.00", stock=10)
    hub = make_product(price="100.00", stock=10)
    # 3000 + 1500 + 100 = 4600, 10% off = 4140.00
    confirmed_order(customer, [(keyboard, 2), (mouse, 3), (hub, 1)], date(2026, 10, 1), "10")

    result = summary_by_name(reports.customer_sales_summary())

    assert result["Many Items"] == (1, Decimal("4140.00"))


def test_draft_and_cancelled_orders_are_left_out(sales_user, make_customer, make_product, make_order,
                                                 confirmed_order):
    customer = make_customer(name="Mixed")
    product = make_product(price="100.00", stock=50)
    confirmed_order(customer, [(product, 1)], date(2026, 10, 1))      # counts: 100.00
    make_order(sales_user, customer, [(product, 5)])                   # draft: left out
    cancelled = confirmed_order(customer, [(product, 7)], date(2026, 10, 2))
    cancel_order(cancelled.id, sales_user)                             # cancelled: left out

    result = summary_by_name(reports.customer_sales_summary())

    assert result["Mixed"] == (1, Decimal("100.00"))


def test_customers_with_no_sales_show_zero(make_customer, make_product, confirmed_order):
    buyer = make_customer(name="Buyer")
    make_customer(name="Never Bought")
    make_customer(name="Inactive One", is_active=False)
    product = make_product(price="10.00", stock=5)
    confirmed_order(buyer, [(product, 1)], date(2026, 10, 1))

    result = summary_by_name(reports.customer_sales_summary())

    assert result["Never Bought"] == (0, Decimal("0"))
    assert result["Inactive One"] == (0, Decimal("0"))
    assert result["Buyer"] == (1, Decimal("10.00"))


def test_date_range_filters_orders_and_keeps_customers(make_customer, make_product, confirmed_order):
    customer = make_customer(name="Ranged")
    other = make_customer(name="Only Earlier")
    product = make_product(price="10.00", stock=50)
    confirmed_order(customer, [(product, 1)], date(2026, 9, 30))
    confirmed_order(customer, [(product, 2)], date(2026, 10, 1))   # first day, included
    confirmed_order(customer, [(product, 3)], date(2026, 10, 31))  # last day, included
    confirmed_order(other, [(product, 4)], date(2026, 9, 1))

    result = summary_by_name(reports.customer_sales_summary(date(2026, 10, 1), date(2026, 10, 31)))

    assert result["Ranged"] == (2, Decimal("50.00"))
    assert result["Only Earlier"] == (0, Decimal("0"))  # still listed, with zero


# ---------- product sales summary ----------

def test_product_sales_are_gross_before_order_discount(make_customer, make_product, make_order,
                                                       sales_user, confirmed_order):
    customer = make_customer()
    keyboard = make_product(code="RPT-KEY", price="1500.00", stock=20)
    mouse = make_product(code="RPT-MOU", price="500.00", stock=20)
    confirmed_order(customer, [(keyboard, 2), (mouse, 3)], date(2026, 10, 1), "10")
    confirmed_order(customer, [(keyboard, 1)], date(2026, 10, 5), "20")
    make_order(sales_user, customer, [(mouse, 9)])  # draft: left out

    rows = {row.code: (row.quantity_sold, row.gross_value) for row in reports.product_sales_summary()}

    assert rows == {
        "RPT-KEY": (3, Decimal("4500.00")),  # 2 x 1500 + 1 x 1500, no discount taken off
        "RPT-MOU": (3, Decimal("1500.00")),
    }


def test_product_sales_date_range(make_customer, make_product, confirmed_order):
    customer = make_customer()
    product = make_product(code="RPT-RNG", price="10.00", stock=20)
    confirmed_order(customer, [(product, 1)], date(2026, 9, 1))
    confirmed_order(customer, [(product, 4)], date(2026, 10, 1))

    rows = reports.product_sales_summary(date(2026, 10, 1), None)

    assert [(row.code, row.quantity_sold) for row in rows] == [("RPT-RNG", 4)]


# ---------- date and threshold checks ----------

def test_date_range_parsing():
    assert reports.parse_date_range("", "") == (None, None)
    assert reports.parse_date_range("2026-10-01", "2026-10-31") == (date(2026, 10, 1), date(2026, 10, 31))
    with pytest.raises(ValidationError, match="From date must be a real date"):
        reports.parse_date_range("2026-02-30", "")
    with pytest.raises(ValidationError, match="To date must be a real date"):
        reports.parse_date_range("", "yesterday")
    with pytest.raises(ValidationError, match="From date can't be after To date"):
        reports.parse_date_range("2026-11-02", "2026-11-01")


@pytest.mark.parametrize("value, message", [
    ("", "Threshold is required."),
    ("abc", "Threshold must be a whole number."),
    ("2.5", "Threshold must be a whole number."),
    ("-1", "Threshold can't be negative."),
])
def test_bad_threshold_is_rejected(value, message):
    with pytest.raises(ValidationError) as error:
        reports.parse_threshold(value)
    assert error.value.message == message


def test_low_stock_lists_active_products_strictly_below(make_product):
    make_product(code="LOW-A", stock=2)
    make_product(code="LOW-B", stock=0)
    make_product(code="LOW-C", stock=5)    # equal to the threshold: not below
    make_product(code="LOW-D", stock=1, is_active=False)

    products = reports.low_stock_products(5)

    assert [product.code for product in products] == ["LOW-B", "LOW-A"]


# ---------- movement history ----------

def test_movement_history_newest_first_and_filtered(admin_user, make_customer, make_product, confirmed_order):
    keyboard = make_product(code="MOV-KEY", stock=10)
    mouse = make_product(code="MOV-MOU", stock=10)
    adjust_stock(keyboard.id, -2, "Damaged in transit", admin_user)
    order = confirmed_order(make_customer(), [(keyboard, 3)], date(2026, 10, 1))

    movements, total, page, last_page = reports.stock_movements(keyboard.id)

    assert total == 3
    assert (page, last_page) == (1, 1)
    assert [(m.movement_type, m.quantity_change) for m in movements] == [
        ("sale", -3), ("adjustment", -2), ("opening", 10),
    ]
    assert movements[0].order.order_number == order.order_number
    assert movements[1].reason == "Damaged in transit"
    assert movements[1].creator.name == admin_user.name
    assert all(m.product_id == keyboard.id for m in movements)

    _all, total_all, _page, _last = reports.stock_movements()
    assert total_all == 4  # mouse's opening movement too


def test_movement_history_pages(admin_user, make_product, monkeypatch):
    monkeypatch.setattr(reports, "MOVEMENTS_PER_PAGE", 2)
    product = make_product(stock=10)
    for change in (1, 2, 3, 4):
        adjust_stock(product.id, change, "Recount", admin_user)

    first, total, page, last_page = reports.stock_movements(product.id, 1)
    third, _total, third_page, _last = reports.stock_movements(product.id, 99)  # past the end

    assert (total, last_page) == (5, 3)
    assert [m.quantity_change for m in first] == [4, 3]
    assert third_page == 3
    assert [m.quantity_change for m in third] == [10]


# ---------- pages ----------

def test_report_pages_are_admin_only(client, login, sales_user):
    login(client, sales_user)
    for url in ["/reports/", "/reports/customer-sales", "/reports/product-sales",
                "/reports/low-stock", "/reports/stock-movements"]:
        assert client.get(url).status_code == 403, url


def test_report_pages_render_for_admin(client, login, admin_user, make_customer, make_product,
                                       confirmed_order):
    make_customer(name="Zero Sales Co")
    product = make_product(code="PG-001", stock=3)
    confirmed_order(make_customer(name="Page Buyer"), [(product, 1)], date(2026, 10, 1))
    login(client, admin_user)

    index = client.get("/reports/").get_data(as_text=True)
    customers = client.get("/reports/customer-sales?date_from=2026-10-01&date_to=2026-10-31")
    products = client.get("/reports/product-sales").get_data(as_text=True)
    low = client.get("/reports/low-stock?threshold=5").get_data(as_text=True)
    history = client.get(f"/reports/stock-movements?product_id={product.id}").get_data(as_text=True)

    assert "Customer sales summary" in index and "Stock movement history" in index
    assert customers.status_code == 200
    assert "Zero Sales Co" in customers.get_data(as_text=True)
    assert "PG-001" in products
    assert "PG-001" in low  # 3 - 1 sold = 2 left, below 5
    assert "Opening stock" in history and "Sale" in history


def test_report_pages_show_input_errors(client, login, admin_user):
    login(client, admin_user)

    bad_date = client.get("/reports/customer-sales?date_from=2026-13-01").get_data(as_text=True)
    reversed_range = client.get("/reports/product-sales?date_from=2026-11-02&date_to=2026-11-01")
    bad_threshold = client.get("/reports/low-stock?threshold=-3").get_data(as_text=True)

    assert "From date must be a real date like 2026-11-07." in bad_date
    assert reversed_range.status_code == 200
    assert "From date can&#39;t be after To date." in reversed_range.get_data(as_text=True)
    assert "Threshold can&#39;t be negative." in bad_threshold
