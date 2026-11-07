"""Customer pages: list with search and active filter, create, view, edit, delete-if-unused,
activate and deactivate. The rules live in services/catalog.py.

Admins change customers. Sales users see active customers only, read-only; the change routes
are guarded by admin_required, so they get 403 even if they type the URL.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.errors import ConflictError, NotFoundError, ValidationError
from app.permissions import admin_required
from app.services import catalog

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    # Sales users only ever see active customers, whatever the URL says.
    status = request.args.get("status", "active") if current_user.is_admin else "active"
    page = request.args.get("page", 1, type=int)
    customers, total, page, per_page = catalog.search_customers(q=q, status=status, page=page)
    return render_template(
        "customers/index.html",
        customers=customers, total=total, page=page, per_page=per_page, q=q, status=status,
    )


@customers_bp.route("/<int:customer_id>")
def view(customer_id):
    customer = catalog.get_customer(customer_id)
    if not customer.is_active and not current_user.is_admin:
        raise NotFoundError("Customer not found.")
    return render_template("customers/view.html", customer=customer)


@customers_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    if request.method == "POST":
        try:
            customer = catalog.create_customer(request.form)
        except ValidationError as error:
            return render_form(None, request.form, error), 422
        flash(f"Customer {customer.name} created.", "success")
        return redirect(url_for("customers.view", customer_id=customer.id))
    return render_form(None, {}, None)


@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(customer_id):
    customer = catalog.get_customer(customer_id)
    if request.method == "POST":
        try:
            catalog.update_customer(customer.id, request.form)
        except ValidationError as error:
            return render_form(customer, request.form, error), 422
        flash("Customer saved.", "success")
        return redirect(url_for("customers.view", customer_id=customer.id))
    values = {"name": customer.name, "email": customer.email, "mobile": customer.mobile, "city": customer.city}
    return render_form(customer, values, None)


def render_form(customer, values, error):
    """The create/edit form. After a failed save it shows what the user typed and each field's error."""
    return render_template(
        "customers/form.html",
        customer=customer,
        values=values,
        message=error.message if error else None,
        errors=error.details if error else {},
    )


@customers_bp.route("/<int:customer_id>/delete", methods=["POST"])
@admin_required
def delete(customer_id):
    try:
        catalog.delete_customer(customer_id)
    except ConflictError as error:
        flash(error.message, "error")
        return redirect(url_for("customers.view", customer_id=customer_id))
    flash("Customer deleted.", "success")
    return redirect(url_for("customers.index"))


@customers_bp.route("/<int:customer_id>/activate", methods=["POST"])
@admin_required
def activate(customer_id):
    customer = catalog.set_customer_active(customer_id, True)
    flash(f"{customer.name} is active again.", "success")
    return redirect(url_for("customers.view", customer_id=customer_id))


@customers_bp.route("/<int:customer_id>/deactivate", methods=["POST"])
@admin_required
def deactivate(customer_id):
    customer = catalog.set_customer_active(customer_id, False)
    flash(f"{customer.name} is now inactive. It can't be picked for new orders.", "success")
    return redirect(url_for("customers.view", customer_id=customer_id))
