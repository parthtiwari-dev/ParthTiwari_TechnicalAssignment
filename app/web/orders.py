"""Order pages: list, create/edit Draft (the JS order form), view, confirm, cancel.
Load orders only through permissions.get_order_for_user; call services/orders.py for changes.

Stub from Stage A. The orders/JS work (Stage B) fills this in. Keep the endpoint name
`orders.index`: the home page redirects there.
"""
from flask import Blueprint, render_template

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


@orders_bp.route("/")
def index():
    return render_template("orders/index.html")
