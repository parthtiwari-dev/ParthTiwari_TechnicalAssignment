"""Order pages: list, view, and the new/edit Draft form.

Orders are loaded only through permissions.get_order_for_user, so a sales user who types
another user's order id gets 403. Saving, confirming and cancelling happen in the browser
through the JSON API (static/js/order_form.js), which calls services/orders.py.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.models import STATUS_CONFIRMED, STATUS_DRAFT
from app.permissions import get_order_for_user
from app.serializers import order_to_dict
from app.services import catalog
from app.services.order_search import search_orders

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


@orders_bp.route("/")
def index():
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    orders, total, page, per_page = search_orders(current_user, status=status, page=page)
    return render_template(
        "orders/index.html", orders=orders, total=total, page=page, per_page=per_page, status=status
    )


@orders_bp.route("/<int:order_id>")
def view(order_id):
    order = get_order_for_user(order_id, current_user)
    return render_template(
        "orders/view.html",
        order=order,
        can_edit=order.status == STATUS_DRAFT,
        can_confirm=order.status == STATUS_DRAFT,
        can_cancel=order.status in (STATUS_DRAFT, STATUS_CONFIRMED),
    )


@orders_bp.route("/new")
def create():
    return render_form(None)


@orders_bp.route("/<int:order_id>/edit")
def edit(order_id):
    order = get_order_for_user(order_id, current_user)
    if order.status != STATUS_DRAFT:
        flash(f"Order {order.order_number} is {order.status}, so it can't be edited.", "error")
        return redirect(url_for("orders.view", order_id=order.id))
    return render_form(order)


def render_form(order):
    """The order form. The browser fills and saves it (order_form.js).

    Dropdowns list active customers and products. When editing, the order's own customer and
    products are listed too even if they were deactivated since, so the form shows the order
    as it is; saving then explains that they must be replaced.
    """
    customers = catalog.active_customers()
    products = catalog.active_products()
    if order is not None:
        if not order.customer.is_active:
            customers.append(order.customer)
        for item in order.items:
            if not item.product.is_active:
                products.append(item.product)
    return render_template(
        "orders/form.html",
        order=order,
        order_data=order_to_dict(order) if order else None,
        customers=customers,
        products=products,
    )
