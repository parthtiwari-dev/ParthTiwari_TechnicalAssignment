"""Error types the services raise, and how the app turns them into responses.

Services raise one of the errors below. They never build HTTP responses themselves.
The handlers at the bottom decide the response:
- under /api/: JSON {"error": "...", "details": {...}} with the right status code
- pages: a flash message, then back to the previous page (or an error page for 403/404)

Tracebacks are logged on the server and never sent to the browser.
"""
from urllib.parse import urlparse

from flask import flash, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from app.extensions import db


class AppError(Exception):
    """Base class. `details` carries extra data, e.g. {"quantity": "Must be more than zero."}."""

    status_code = 400

    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(AppError):
    """Bad input. `details` maps a field name to a message."""

    status_code = 422


class NotFoundError(AppError):
    status_code = 404


class ForbiddenError(AppError):
    status_code = 403


class ConflictError(AppError):
    """The request is valid but clashes with the current state (order not a draft, not enough stock)."""

    status_code = 409


def is_api_request():
    return request.path.startswith("/api/")


def json_error(message, status_code, details=None):
    return jsonify({"error": message, "details": details or {}}), status_code


def redirect_back():
    """Go back to the page the user came from, if it is on this site. Otherwise go home."""
    referrer = request.referrer
    if referrer and urlparse(referrer).netloc == request.host:
        return redirect(referrer)
    return redirect(url_for("home"))


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(error):
        if is_api_request():
            return json_error(error.message, error.status_code, error.details)
        if error.status_code in (403, 404):
            return render_template("errors.html", code=error.status_code, message=error.message), error.status_code
        # 422 and 409 on a page: show the message on the page the user came from.
        flash(error.message, "error")
        return redirect_back()

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        # Covers malformed JSON (400), missing CSRF token (400), unknown URL (404), wrong method (405).
        if is_api_request():
            return json_error(error.description, error.code)
        return render_template("errors.html", code=error.code, message=error.description), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception("Unhandled error on %s", request.path)
        db.session.rollback()
        message = "Something went wrong on our side. Please try again."
        if is_api_request():
            return json_error(message, 500)
        return render_template("errors.html", code=500, message=message), 500
