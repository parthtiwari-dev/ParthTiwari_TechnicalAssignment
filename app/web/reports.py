"""Report pages (admin only): customer sales summary, product sales summary, low stock,
stock movement history. Queries and input checks live in services/reports.py.

Filters come in the URL (GET), so a report can be bookmarked or refreshed. Bad input shows
a message on the same page instead of redirecting, so the user sees what they typed.
"""
from flask import Blueprint, render_template, request

from app.errors import ValidationError
from app.permissions import require_admin
from app.services import reports

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")
reports_bp.before_request(require_admin)  # every route here is admin only

DEFAULT_THRESHOLD = "10"


@reports_bp.route("/")
def index():
    return render_template("reports/index.html")


@reports_bp.route("/customer-sales")
def customer_sales():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    rows, error = [], None
    try:
        start, end = reports.parse_date_range(date_from, date_to)
        rows = reports.customer_sales_summary(start, end)
    except ValidationError as exc:
        error = exc.message
    return render_template(
        "reports/customer_sales.html", rows=rows, error=error, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/product-sales")
def product_sales():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    rows, error = [], None
    try:
        start, end = reports.parse_date_range(date_from, date_to)
        rows = reports.product_sales_summary(start, end)
    except ValidationError as exc:
        error = exc.message
    return render_template(
        "reports/product_sales.html", rows=rows, error=error, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/low-stock")
def low_stock():
    threshold_text = request.args.get("threshold", DEFAULT_THRESHOLD)
    products, threshold, error = [], None, None
    try:
        threshold = reports.parse_threshold(threshold_text)
        products = reports.low_stock_products(threshold)
    except ValidationError as exc:
        error = exc.message
    return render_template(
        "reports/low_stock.html",
        products=products,
        threshold=threshold,
        threshold_text=threshold_text,
        error=error,
    )


@reports_bp.route("/stock-movements")
def stock_movements():
    # type=int gives None (or the default) for anything that isn't a whole number.
    product_id = request.args.get("product_id", type=int)
    page = request.args.get("page", 1, type=int)
    movements, total, page, last_page = reports.stock_movements(product_id, page)
    return render_template(
        "reports/stock_movements.html",
        movements=movements,
        total=total,
        page=page,
        last_page=last_page,
        product_id=product_id,
        products=reports.all_products(),
    )
