"""Report pages (admin only): customer sales summary, product sales summary, low stock,
stock movement history. Queries live in services/reports.py.

Stub from Stage A. The reports work (Stage B) fills this in.
"""
from flask import Blueprint, render_template

from app.permissions import require_admin

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")
reports_bp.before_request(require_admin)  # every route here is admin only


@reports_bp.route("/")
def index():
    return render_template("reports/index.html")
