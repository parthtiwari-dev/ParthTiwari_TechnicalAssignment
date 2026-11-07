"""The app factory. create_app() builds the Flask app: settings, extensions, routes, errors."""
from flask import Flask, redirect, request, url_for
from flask_login import current_user

from app.config import Config
from app.errors import is_api_request, json_error, register_error_handlers
from app.extensions import csrf, db, login_manager, migrate

# Routes anyone may open without logging in.
PUBLIC_ENDPOINTS = {"auth.login", "static"}


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    register_blueprints(app)
    register_error_handlers(app)
    setup_login(app)
    # After setup_login, so the login check runs first: a logged-out API call gets 401,
    # not a "missing CSRF token" 400.
    csrf.init_app(app)

    @app.route("/")
    def home():
        return redirect(url_for("orders.index"))

    return app


def register_blueprints(app):
    from app.api import api_bp
    from app.web.auth import auth_bp
    from app.web.customers import customers_bp
    from app.web.imports import imports_bp
    from app.web.orders import orders_bp
    from app.web.products import products_bp
    from app.web.reports import reports_bp
    from app.web.stock import stock_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(api_bp)


def setup_login(app):
    from app.models import User
    from app.extensions import db

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        # API callers get JSON. A person in the browser goes to the login page and comes back after.
        if is_api_request():
            return json_error("Please log in first.", 401)
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("auth.login", next=next_url))

    @app.before_request
    def require_login():
        """Every route needs a logged-in user, except the ones in PUBLIC_ENDPOINTS.

        Doing this once here means a new route can't be left open by forgetting a decorator.
        request.endpoint is None for an unknown URL; that falls through to a normal 404.
        """
        if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        return None
