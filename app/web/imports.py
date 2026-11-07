"""CSV product import page (admin only). The checking and saving live in services/csv_import.py.

Stub from Stage A. The CSV import work (Stage B, on a feature branch) fills this in.
"""
from flask import Blueprint, render_template

from app.permissions import require_admin

imports_bp = Blueprint("imports", __name__, url_prefix="/import")
imports_bp.before_request(require_admin)  # every route here is admin only


@imports_bp.route("/")
def index():
    return render_template("imports/index.html")
