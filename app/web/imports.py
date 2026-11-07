"""CSV product import page (admin only). The checking and saving live in services/csv_import.py."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.errors import ConflictError, ValidationError
from app.permissions import require_admin
from app.services import csv_import

imports_bp = Blueprint("imports", __name__, url_prefix="/import")
imports_bp.before_request(require_admin)  # every route here is admin only


@imports_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("imports/index.html", columns=csv_import.COLUMNS)

    upload = request.files.get("file")
    error, row_errors, filename = None, [], ""
    if upload is None or upload.filename == "":
        error = "Choose a CSV file to upload."
    elif not upload.filename.lower().endswith(".csv"):
        error = "Only .csv files can be imported."
    else:
        filename = upload.filename
        # Read one byte more than the limit, so the service can tell the file is too big
        # without reading a huge upload into memory.
        data = upload.read(csv_import.MAX_FILE_BYTES + 1)
        try:
            imported, row_errors = csv_import.import_products(data, current_user)
            if not row_errors:
                flash(f"Imported {imported} products from {filename}, with their opening stock.", "success")
                return redirect(url_for("imports.index"))
        except (ValidationError, ConflictError) as exc:
            error = exc.message

    return render_template(
        "imports/index.html",
        columns=csv_import.COLUMNS,
        error=error,
        row_errors=row_errors,
        filename=filename,
    )
