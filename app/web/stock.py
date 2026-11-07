"""Stock adjustment page (admin only): pick a product, enter a change and a reason,
call services.stock.adjust_stock.

Stub from Stage A. The master-data work (Stage B) fills this in.
"""
from flask import Blueprint, render_template

from app.permissions import require_admin

stock_bp = Blueprint("stock", __name__, url_prefix="/stock")
stock_bp.before_request(require_admin)  # every route here is admin only


@stock_bp.route("/")
def index():
    return render_template("stock/index.html")
