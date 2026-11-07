"""Customer and product pages: admin CRUD, sales users read-only, safe delete, validation."""
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import MOVEMENT_OPENING, Customer, Product, StockMovement


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def test_admin_creates_edits_and_deletes_customer(client, login, admin_user):
    login(client, admin_user)

    response = client.post("/customers/new", data={
        "name": "Shah Traders", "email": "Shah@Example.com", "mobile": "9824011111", "city": "Surat",
    })
    assert response.status_code == 302
    customer = db.session.scalars(select(Customer).where(Customer.name == "Shah Traders")).one()
    assert customer.email == "shah@example.com"
    assert customer.is_active

    response = client.post(f"/customers/{customer.id}/edit", data={
        "name": "Shah Traders Pvt", "email": "", "mobile": "", "city": "Ahmedabad",
    })
    assert response.status_code == 302
    db.session.refresh(customer)
    assert customer.name == "Shah Traders Pvt"
    assert customer.email is None
    assert customer.city == "Ahmedabad"

    page = client.get(f"/customers/{customer.id}")
    assert b"Shah Traders Pvt" in page.data

    response = client.post(f"/customers/{customer.id}/delete")
    assert response.status_code == 302
    assert db.session.get(Customer, customer.id) is None


def test_customer_form_shows_field_errors(client, login, admin_user):
    login(client, admin_user)
    response = client.post("/customers/new", data={"name": "", "email": "not-an-email", "mobile": "abc"})
    assert response.status_code == 422
    assert b"Required." in response.data
    assert b"Enter a valid email address." in response.data
    assert db.session.scalar(select(Customer.id)) is None


def test_customer_search_and_status_filter(client, login, admin_user, make_customer):
    make_customer(name="Alpha Stores", mobile="9111111111")
    make_customer(name="Beta Mart", is_active=False)
    login(client, admin_user)

    page = client.get("/customers/?q=9111")
    assert b"Alpha Stores" in page.data
    assert b"Beta Mart" not in page.data

    page = client.get("/customers/?status=inactive")
    assert b"Beta Mart" in page.data
    assert b"Alpha Stores" not in page.data


def test_customer_with_orders_cannot_be_deleted_but_can_be_deactivated(
    client, login, admin_user, customer, make_product, make_order
):
    make_order(admin_user, customer, [(make_product(), 1)])
    login(client, admin_user)

    response = client.post(f"/customers/{customer.id}/delete", follow_redirects=True)
    assert b"has orders, so it can&#39;t be deleted. Deactivate it instead." in response.data
    assert db.session.get(Customer, customer.id) is not None

    client.post(f"/customers/{customer.id}/deactivate")
    db.session.refresh(customer)
    assert customer.is_active is False

    client.post(f"/customers/{customer.id}/activate")
    db.session.refresh(customer)
    assert customer.is_active is True


def test_sales_user_sees_only_active_customers(client, login, sales_user, make_customer):
    active = make_customer(name="Active Co")
    inactive = make_customer(name="Sleeping Co", is_active=False)
    login(client, sales_user)

    # Even asking for inactive ones in the URL shows active ones only.
    page = client.get("/customers/?status=inactive")
    assert b"Active Co" in page.data
    assert b"Sleeping Co" not in page.data
    assert b"New customer" not in page.data

    assert client.get(f"/customers/{active.id}").status_code == 200
    assert b"Edit" not in client.get(f"/customers/{active.id}").data
    assert client.get(f"/customers/{inactive.id}").status_code == 404


def test_sales_user_gets_403_on_customer_changes(client, login, sales_user, customer):
    login(client, sales_user)
    assert client.get("/customers/new").status_code == 403
    assert client.post("/customers/new", data={"name": "X"}).status_code == 403
    assert client.get(f"/customers/{customer.id}/edit").status_code == 403
    assert client.post(f"/customers/{customer.id}/edit", data={"name": "X"}).status_code == 403
    assert client.post(f"/customers/{customer.id}/delete").status_code == 403
    assert client.post(f"/customers/{customer.id}/deactivate").status_code == 403
    db.session.refresh(customer)
    assert customer.is_active and customer.name != "X"


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def _product_form(**changes):
    data = {"code": "NEW-001", "name": "Webcam", "category": "Accessories", "price": "2499.50",
            "stock_quantity": "15"}
    data.update(changes)
    return data


def test_new_product_records_opening_stock_movement(client, login, admin_user):
    login(client, admin_user)
    response = client.post("/products/new", data=_product_form())
    assert response.status_code == 302

    product = db.session.scalars(select(Product).where(Product.code == "NEW-001")).one()
    assert product.price == Decimal("2499.50")
    assert product.stock_quantity == 15
    movements = db.session.scalars(select(StockMovement).where(StockMovement.product_id == product.id)).all()
    assert [(m.movement_type, m.quantity_change) for m in movements] == [(MOVEMENT_OPENING, 15)]


def test_new_product_with_zero_stock_has_no_movement_and_can_be_deleted(client, login, admin_user):
    login(client, admin_user)
    client.post("/products/new", data=_product_form(stock_quantity="0"))
    product = db.session.scalars(select(Product).where(Product.code == "NEW-001")).one()
    assert db.session.scalar(select(StockMovement.id).where(StockMovement.product_id == product.id)) is None

    response = client.post(f"/products/{product.id}/delete")
    assert response.status_code == 302
    assert db.session.get(Product, product.id) is None


def test_duplicate_product_code_rejected(client, login, admin_user, make_product):
    make_product(code="DUP-001")
    login(client, admin_user)
    # products.code ignores case, so "dup-001" is the same code.
    response = client.post("/products/new", data=_product_form(code="dup-001"))
    assert response.status_code == 422
    assert b"Code dup-001 is already used by another product." in response.data
    assert db.session.scalar(select(Product.id).where(Product.name == "Webcam")) is None


def test_product_codes_ignore_case_but_not_accents(client, login, admin_user, make_product):
    make_product(code="CAFE-1")
    login(client, admin_user)

    response = client.post("/products/new", data=_product_form(code="CAFÉ-1"))
    assert response.status_code == 302

    response = client.post("/products/new", data=_product_form(code="café-1"))
    assert response.status_code == 422
    assert "Code café-1 is already used by another product.".encode() in response.data


def test_editing_product_to_another_products_code_rejected(client, login, admin_user, make_product):
    make_product(code="KEEP-001")
    other = make_product(code="KEEP-002")
    login(client, admin_user)
    response = client.post(f"/products/{other.id}/edit", data=_product_form(code="KEEP-001"))
    assert response.status_code == 422
    db.session.refresh(other)
    assert other.code == "KEEP-002"


def test_negative_price_and_stock_rejected(client, login, admin_user):
    login(client, admin_user)
    response = client.post("/products/new", data=_product_form(price="-1", stock_quantity="-5"))
    assert response.status_code == 422
    assert b"Can&#39;t be negative." in response.data
    assert db.session.scalar(select(Product.id)) is None


def test_editing_product_changes_price_but_not_stock(client, login, admin_user, make_product):
    product = make_product(price="100.00", stock=10)
    login(client, admin_user)
    response = client.post(f"/products/{product.id}/edit", data=_product_form(
        code=product.code, price="120.00", stock_quantity="999",
    ))
    assert response.status_code == 302
    db.session.refresh(product)
    assert product.price == Decimal("120.00")
    assert product.stock_quantity == 10


def test_product_with_history_cannot_be_deleted_but_can_be_deactivated(client, login, admin_user, make_product):
    product = make_product(stock=5)  # has an opening movement
    login(client, admin_user)

    response = client.post(f"/products/{product.id}/delete", follow_redirects=True)
    assert b"Deactivate it instead." in response.data
    assert db.session.get(Product, product.id) is not None

    client.post(f"/products/{product.id}/deactivate")
    db.session.refresh(product)
    assert product.is_active is False


def test_product_search_and_filters(client, login, admin_user, make_product):
    make_product(code="KB-1", name="Keyboard", category="Accessories")
    make_product(code="MN-1", name="Monitor", category="Monitors")
    make_product(code="KB-OLD", name="Old Keyboard", category="Accessories", is_active=False)
    login(client, admin_user)

    page = client.get("/products/?q=keyboard")
    assert b"KB-1" in page.data and b"MN-1" not in page.data and b"KB-OLD" not in page.data

    page = client.get("/products/?category=Monitors")
    assert b"MN-1" in page.data and b"KB-1" not in page.data

    page = client.get("/products/?q=keyboard&status=all")
    assert b"KB-1" in page.data and b"KB-OLD" in page.data


def test_product_list_paginates(client, login, admin_user, make_product):
    for number in range(25):
        make_product(code=f"PG-{number:03d}", stock=0)
    login(client, admin_user)
    first = client.get("/products/")
    assert b"PG-019" in first.data and b"PG-020" not in first.data
    assert b"Page 1 of 2" in first.data
    second = client.get("/products/?page=2")
    assert b"PG-020" in second.data and b"PG-000" not in second.data


def test_sales_user_sees_only_active_products_and_cannot_change_them(client, login, sales_user, make_product):
    active = make_product(code="SEE-001")
    inactive = make_product(code="HIDE-001", is_active=False)
    login(client, sales_user)

    page = client.get("/products/?status=all")
    assert b"SEE-001" in page.data and b"HIDE-001" not in page.data
    assert client.get(f"/products/{inactive.id}").status_code == 404

    assert client.get("/products/new").status_code == 403
    assert client.post("/products/new", data=_product_form()).status_code == 403
    assert client.post(f"/products/{active.id}/edit", data=_product_form()).status_code == 403
    assert client.post(f"/products/{active.id}/delete").status_code == 403
    assert client.post(f"/products/{active.id}/deactivate").status_code == 403
    db.session.refresh(active)
    assert active.is_active
