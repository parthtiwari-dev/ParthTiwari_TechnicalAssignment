"""Product pages: list with search and category/active filters, create, view, edit, delete-if-unused.
Admins change products; sales users only see active ones.

Stub from Stage A. The master-data work (Stage B) fills this in.
"""
from flask import Blueprint, render_template

products_bp = Blueprint("products", __name__, url_prefix="/products")


@products_bp.route("/")
def index():
    return render_template("products/index.html")
