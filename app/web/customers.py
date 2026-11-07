"""Customer pages: list with search and active filter, create, view, edit, delete-if-unused.
Admins change customers; sales users only see active ones.

Stub from Stage A. The master-data work (Stage B) fills this in.
"""
from flask import Blueprint, render_template

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.route("/")
def index():
    return render_template("customers/index.html")
