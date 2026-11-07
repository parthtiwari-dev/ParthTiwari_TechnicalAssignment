"""Shared test setup. Tests run against a real MySQL database (TEST_DATABASE_URL), never SQLite,
because the stock logic depends on MySQL row locks.

Fixtures you can ask for in any test:

    app               the Flask app, with an app context already pushed, so services and
                      db.session work directly in the test. Tables are emptied after each test.
    client            Flask test client (CSRF is off in TestConfig)
    login             login(client, user) -> logs that user in through the real /login form
    admin_user        role admin,  password PASSWORD
    sales_user        role sales,  password PASSWORD
    other_sales_user  a second sales user, to test "can't touch someone else's order"
    customer          one active customer
    make_customer     make_customer(name=..., is_active=True, ...) -> Customer
    make_product      make_product(code=..., price="100.00", stock=10, is_active=True, ...)
                      -> Product, with its opening stock written as an 'opening' movement
    make_order        make_order(user, customer, [(product, qty), ...], discount="0")
                      -> a Draft order made through services.orders.create_draft_order

Gotchas:
- Ids keep growing between tests (rows are deleted, the auto-increment isn't reset).
  Never hard-code an id.
- The test and the requests from `client` share one database session. After a request,
  objects you hold are refreshed from the database when you read them.
- Services commit, so data they save is really in the database (other connections see it).
"""
from decimal import Decimal
from itertools import count

import pymysql
import pytest
from flask import g
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import MOVEMENT_OPENING, ROLE_ADMIN, ROLE_SALES, Customer, Product, User
from app.services.orders import create_draft_order
from app.services.stock import change_stock

PASSWORD = "test-password-123"

_unique = count(1)


def _create_test_database():
    """CREATE DATABASE IF NOT EXISTS for the test database, so a fresh machine just works."""
    url_string = TestConfig.SQLALCHEMY_DATABASE_URI
    if not url_string:
        raise RuntimeError("Set TEST_DATABASE_URL in .env before running the tests.")
    url = make_url(url_string)
    # Every test deletes all rows. Refuse to run against anything that isn't clearly a test database.
    if "test" not in url.database:
        raise RuntimeError("TEST_DATABASE_URL must point at a database with 'test' in its name.")
    connection = pymysql.connect(
        host=url.host, port=url.port or 3306, user=url.username, password=url.password
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{url.database}` CHARACTER SET utf8mb4")
    finally:
        connection.close()


@pytest.fixture(scope="session")
def _app():
    """Build the app and the tables once for the whole test run."""
    _create_test_database()
    app = create_app(TestConfig)

    @app.before_request
    def _fresh_login_cache():
        # Tests keep one app context open, and Flask-Login caches the user in `g`, which belongs
        # to that context. Clear it so every request reads the user from its own session cookie,
        # as it would in production.
        g.pop("_login_user", None)

    # Run our hook before require_login, which is the first thing to read the user.
    app.before_request_funcs[None].insert(0, app.before_request_funcs[None].pop())

    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


@pytest.fixture
def app(_app):
    context = _app.app_context()
    context.push()
    yield _app
    db.session.remove()
    # Children before parents, so foreign keys never block a delete.
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(text(f"DELETE FROM `{table.name}`"))
    db.session.commit()
    db.session.remove()
    context.pop()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login():
    def _login(client, user):
        response = client.post("/login", data={"email": user.email, "password": PASSWORD})
        assert response.status_code == 302, "login failed in test helper"
        return response

    return _login


def _make_user(name, role):
    user = User(name=name, email=f"{name.lower().replace(' ', '.')}{next(_unique)}@test.local", role=role)
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    return _make_user("Admin", ROLE_ADMIN)


@pytest.fixture
def sales_user(app):
    return _make_user("Sales One", ROLE_SALES)


@pytest.fixture
def other_sales_user(app):
    return _make_user("Sales Two", ROLE_SALES)


@pytest.fixture
def make_customer(app):
    def _make_customer(name=None, email=None, mobile="9000000000", city="Ahmedabad", is_active=True):
        number = next(_unique)
        customer = Customer(
            name=name or f"Customer {number}",
            email=email or f"customer{number}@test.local",
            mobile=mobile,
            city=city,
            is_active=is_active,
        )
        db.session.add(customer)
        db.session.commit()
        return customer

    return _make_customer


@pytest.fixture
def customer(make_customer):
    return make_customer()


@pytest.fixture
def make_product(app, admin_user):
    def _make_product(code=None, name=None, category="Accessories", price="100.00", stock=10, is_active=True):
        number = next(_unique)
        product = Product(
            code=code or f"TST-{number:04d}",
            name=name or f"Product {number}",
            category=category,
            price=Decimal(price),
            stock_quantity=0,
            is_active=is_active,
        )
        db.session.add(product)
        if stock:
            change_stock(product, stock, MOVEMENT_OPENING, admin_user, reason="Opening stock")
        db.session.commit()
        return product

    return _make_product


@pytest.fixture
def make_order(app):
    def _make_order(user, customer, lines, discount="0"):
        items = [{"product_id": product.id, "quantity": quantity} for product, quantity in lines]
        return create_draft_order(user, customer.id, items, discount)

    return _make_order
