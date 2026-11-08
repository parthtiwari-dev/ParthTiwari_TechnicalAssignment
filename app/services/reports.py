"""Report queries: customer sales summary, product sales summary, low stock, movement history.

Sales reports count confirmed orders only. Draft and cancelled orders are left out.
The input checks (dates, threshold) live here too, so the rules exist once.
"""
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import joinedload

from app.errors import ValidationError
from app.extensions import db
from app.models import (
    STATUS_CONFIRMED,
    Customer,
    Product,
    SalesOrder,
    SalesOrderItem,
    StockMovement,
)
from app.services.pricing import parse_int, round_money

MOVEMENTS_PER_PAGE = 50


# ---------- input checks ----------

def parse_date(value, label):
    """'2026-11-07' -> a date. Blank -> None (no limit). Anything else raises ValidationError."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{label} must be a real date like 2026-11-07.")


def parse_date_range(date_from, date_to):
    """Both dates are optional. Returns (start, end). From can't be after To."""
    start = parse_date(date_from, "From date")
    end = parse_date(date_to, "To date")
    if start and end and start > end:
        raise ValidationError("From date can't be after To date.")
    return start, end


def parse_threshold(value):
    """The low stock threshold: a whole number, zero or more."""
    threshold = parse_int(value, "threshold")
    if threshold < 0:
        raise ValidationError("Threshold can't be negative.")
    return threshold


def _with_money_rounded(rows, money_column):
    """Each result row as a dict, with the summed money column rounded to 2 places.

    MySQL's SUM of a DECIMAL(12,2) column already has 2 decimal places. round_money() makes
    sure, so the page can print the Decimal as it is ("4140.00"), with no float in between.
    """
    result = []
    for row in rows:
        values = row._asdict()
        values[money_column] = round_money(values[money_column])
        result.append(values)
    return result


def _date_conditions(start, end):
    """Order-date conditions for a range. Both ends are included."""
    conditions = []
    if start:
        conditions.append(SalesOrder.order_date >= start)
    if end:
        conditions.append(SalesOrder.order_date <= end)
    return conditions


# ---------- reports ----------

def customer_sales_summary(start=None, end=None):
    """Every customer, with their confirmed order count and total sales after discount.

    Works on whole orders (grand_total is stored on the order), never on item rows, so an
    order with five items is still counted once.

    The status and date conditions sit in the LEFT JOIN's ON clause, not in WHERE. That keeps
    customers with no matching orders in the result, with 0 orders and 0.00 sales. In WHERE
    they would be dropped, because their order columns are NULL.

    Returns a list of dicts with: id, name, is_active, order_count, total_sales (a Decimal).
    """
    join_condition = and_(
        SalesOrder.customer_id == Customer.id,
        SalesOrder.status == STATUS_CONFIRMED,
        *_date_conditions(start, end),
    )
    total_sales = func.coalesce(func.sum(SalesOrder.grand_total), 0)
    query = (
        select(
            Customer.id,
            Customer.name,
            Customer.is_active,
            func.count(SalesOrder.id).label("order_count"),
            total_sales.label("total_sales"),
        )
        .select_from(Customer)
        .outerjoin(SalesOrder, join_condition)
        .group_by(Customer.id, Customer.name, Customer.is_active)
        .order_by(total_sales.desc(), Customer.name)
    )
    return _with_money_rounded(db.session.execute(query).all(), "total_sales")


def product_sales_summary(start=None, end=None):
    """Products sold in confirmed orders: quantity sold and gross value before order discount.

    Gross value is the sum of the item amounts (qty x rate). The order discount is not taken
    off, because it belongs to the whole order, not to one product.
    Only products with at least one confirmed sale in the range are listed.

    Returns a list of dicts with: id, code, name, quantity_sold, gross_value (a Decimal).
    """
    join_condition = and_(
        SalesOrder.id == SalesOrderItem.order_id,
        SalesOrder.status == STATUS_CONFIRMED,
        *_date_conditions(start, end),
    )
    gross_value = func.sum(SalesOrderItem.amount)
    query = (
        select(
            Product.id,
            Product.code,
            Product.name,
            func.sum(SalesOrderItem.quantity).label("quantity_sold"),
            gross_value.label("gross_value"),
        )
        .select_from(SalesOrderItem)
        .join(SalesOrder, join_condition)
        .join(Product, Product.id == SalesOrderItem.product_id)
        .group_by(Product.id, Product.code, Product.name)
        .order_by(gross_value.desc(), Product.code)
    )
    return _with_money_rounded(db.session.execute(query).all(), "gross_value")


def low_stock_products(threshold):
    """Active products with stock strictly below the threshold, lowest stock first."""
    query = (
        select(Product)
        .where(Product.is_active.is_(True), Product.stock_quantity < threshold)
        .order_by(Product.stock_quantity, Product.code)
    )
    return db.session.scalars(query).all()


def stock_movements(product_id=None, page=1):
    """Stock movements, newest first, MOVEMENTS_PER_PAGE at a time. Optionally for one product.

    Returns (movements, total, page, last_page). A page number out of range is moved to the
    nearest real page.
    """
    query = select(StockMovement)
    count_query = select(func.count(StockMovement.id))
    if product_id:
        query = query.where(StockMovement.product_id == product_id)
        count_query = count_query.where(StockMovement.product_id == product_id)

    total = db.session.scalar(count_query)
    last_page = max((total + MOVEMENTS_PER_PAGE - 1) // MOVEMENTS_PER_PAGE, 1)
    page = min(max(page, 1), last_page)

    query = (
        query
        # Load the product, order and user in the same query, not one extra query per row.
        .options(
            joinedload(StockMovement.product),
            joinedload(StockMovement.order),
            joinedload(StockMovement.creator),
        )
        # id breaks ties: rows written in the same second still come out newest first.
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(MOVEMENTS_PER_PAGE)
        .offset((page - 1) * MOVEMENTS_PER_PAGE)
    )
    return db.session.scalars(query).all(), total, page, last_page


def all_products():
    """Every product, active or not, for the movement history's product dropdown."""
    return db.session.scalars(select(Product).order_by(Product.code)).all()
