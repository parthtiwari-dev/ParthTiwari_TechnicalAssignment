"""JSON API under /api. Same rules as the pages: it calls the same services.

Login is required (require_login in app/__init__.py returns 401 JSON here).
POST and PUT need the X-CSRFToken header, taken from the page's csrf-token meta tag.
Errors are turned into {"error": ..., "details": ...} by app/errors.py.
"""
from flask import Blueprint, abort, request

api_bp = Blueprint("api", __name__, url_prefix="/api")


def json_body():
    """The request body as a dict. Malformed or missing JSON -> 400 with a clear message."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="The request body must be a JSON object.")
    return data


# Imported at the bottom so the route modules can use api_bp defined above.
from app.api import orders, products  # noqa: E402,F401
