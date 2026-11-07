"""Stock adjustment page (admin only): pick a product, enter a change and a reason,
call services.stock.adjust_stock. Also shows the chosen product's latest movements.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.errors import ValidationError
from app.permissions import require_admin
from app.services import catalog
from app.services.stock import adjust_stock

stock_bp = Blueprint("stock", __name__, url_prefix="/stock")
stock_bp.before_request(require_admin)  # every route here is admin only


@stock_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        product_id = request.form.get("product_id", type=int)
        try:
            if product_id is None:
                raise ValidationError("Please fix the problems below.", {"product_id": "Choose a product."})
            product = adjust_stock(
                product_id, request.form.get("quantity_change"), request.form.get("reason"), current_user
            )
        except ValidationError as error:
            return render_page(product_id, request.form, error), 422
        flash(f"Stock for {product.code} is now {product.stock_quantity}.", "success")
        return redirect(url_for("stock.index", product_id=product.id))

    return render_page(request.args.get("product_id", type=int), {}, None)


def render_page(product_id, values, error):
    """The form, plus the chosen product's stock and latest movements."""
    product = catalog.get_product(product_id) if product_id else None
    return render_template(
        "stock/index.html",
        products=catalog.all_products(),
        product=product,
        movements=catalog.product_movements(product.id) if product else [],
        values=values,
        message=error.message if error else None,
        errors=error.details if error else {},
    )
