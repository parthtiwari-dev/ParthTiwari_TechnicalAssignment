"""GET /api/products and GET /api/products/<id>.

Only active products are returned. The search itself lives in services/catalog.py, so the
products page and this endpoint find the same products.
"""
from flask import jsonify, request

from app.api import api_bp
from app.errors import NotFoundError, ValidationError
from app.extensions import db
from app.models import Product
from app.serializers import product_to_dict
from app.services.catalog import DEFAULT_PER_PAGE, search_products
from app.services.pricing import parse_int


@api_bp.route("/products", methods=["GET"])
def list_products():
    """?q= (code or name), ?category=, ?page= (from 1), ?per_page= (1 to 100, default 20)."""
    errors = {}
    page = 1
    per_page = DEFAULT_PER_PAGE
    try:
        page = parse_int(request.args.get("page", "1"), "page")
    except ValidationError as error:
        errors.update(error.details)
    try:
        per_page = parse_int(request.args.get("per_page", str(DEFAULT_PER_PAGE)), "per_page")
    except ValidationError as error:
        errors.update(error.details)
    if errors:
        raise ValidationError("Page and per_page must be whole numbers.", errors)

    # search_products keeps page at 1 or more and per_page between 1 and 100,
    # and gives back the values it actually used.
    products, total, page, per_page = search_products(
        q=request.args.get("q"),
        category=request.args.get("category"),
        status="active",
        page=page,
        per_page=per_page,
    )
    return jsonify({
        "items": [product_to_dict(product) for product in products],
        "page": page,
        "per_page": per_page,
        "total": total,
    })


@api_bp.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = db.session.get(Product, product_id)
    # An inactive product is hidden from the API, so it looks the same as a missing one.
    if product is None or not product.is_active:
        raise NotFoundError("Product not found.")
    return jsonify(product_to_dict(product))
