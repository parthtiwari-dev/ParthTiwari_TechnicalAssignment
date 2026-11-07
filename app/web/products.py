"""Product pages: list with search and category/active filters, create, view, edit,
delete-if-unused, activate and deactivate. The rules live in services/catalog.py.

Admins change products. Sales users see active products only, read-only; the change routes
are guarded by admin_required, so they get 403 even if they type the URL.
Stock is set once, as opening stock, when a product is created. After that it changes only
through the stock adjustment page and orders.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.errors import ConflictError, NotFoundError, ValidationError
from app.permissions import admin_required
from app.services import catalog

products_bp = Blueprint("products", __name__, url_prefix="/products")


@products_bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    # Sales users only ever see active products, whatever the URL says.
    status = request.args.get("status", "active") if current_user.is_admin else "active"
    page = request.args.get("page", 1, type=int)
    products, total, page, per_page = catalog.search_products(
        q=q, category=category, status=status, page=page
    )
    return render_template(
        "products/index.html",
        products=products, total=total, page=page, per_page=per_page,
        q=q, category=category, status=status, categories=catalog.product_categories(),
    )


@products_bp.route("/<int:product_id>")
def view(product_id):
    product = catalog.get_product(product_id)
    if not product.is_active and not current_user.is_admin:
        raise NotFoundError("Product not found.")
    return render_template("products/view.html", product=product)


@products_bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    if request.method == "POST":
        try:
            product = catalog.create_product(request.form, current_user)
        except ValidationError as error:
            return render_form(None, request.form, error), 422
        flash(f"Product {product.code} created.", "success")
        return redirect(url_for("products.view", product_id=product.id))
    return render_form(None, {"stock_quantity": "0"}, None)


@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(product_id):
    product = catalog.get_product(product_id)
    if request.method == "POST":
        try:
            catalog.update_product(product.id, request.form)
        except ValidationError as error:
            return render_form(product, request.form, error), 422
        flash("Product saved.", "success")
        return redirect(url_for("products.view", product_id=product.id))
    values = {"code": product.code, "name": product.name, "category": product.category, "price": str(product.price)}
    return render_form(product, values, None)


def render_form(product, values, error):
    """The create/edit form. After a failed save it shows what the user typed and each field's error."""
    return render_template(
        "products/form.html",
        product=product,
        values=values,
        categories=catalog.product_categories(),
        message=error.message if error else None,
        errors=error.details if error else {},
    )


@products_bp.route("/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete(product_id):
    try:
        catalog.delete_product(product_id)
    except ConflictError as error:
        flash(error.message, "error")
        return redirect(url_for("products.view", product_id=product_id))
    flash("Product deleted.", "success")
    return redirect(url_for("products.index"))


@products_bp.route("/<int:product_id>/activate", methods=["POST"])
@admin_required
def activate(product_id):
    product = catalog.set_product_active(product_id, True)
    flash(f"{product.code} is active again.", "success")
    return redirect(url_for("products.view", product_id=product_id))


@products_bp.route("/<int:product_id>/deactivate", methods=["POST"])
@admin_required
def deactivate(product_id):
    product = catalog.set_product_active(product_id, False)
    flash(f"{product.code} is now inactive. It can't be added to new orders.", "success")
    return redirect(url_for("products.view", product_id=product_id))
