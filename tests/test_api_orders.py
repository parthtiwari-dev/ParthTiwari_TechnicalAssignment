"""The orders API: create, edit, view, confirm, cancel. Status codes, JSON errors, stock and
ownership, checked through real HTTP requests.

The Part 12 order scenarios from the assignment are here at the API level (marked "Part 12").
The one about CSV import (one bad row imports nothing) is in test_csv_import.py, also marked.
"""
import re

import pytest

from app.extensions import db
from app.services import orders as order_service


def stock_of(product):
    """The product's stock as it is in the database right now."""
    db.session.refresh(product)
    return product.stock_quantity


def order_body(customer, lines, discount="0"):
    return {
        "customer_id": customer.id,
        "discount_percent": discount,
        "items": [{"product_id": product.id, "quantity": quantity} for product, quantity in lines],
    }


# ---------------------------------------------------------------------------
# Login, CSRF, malformed requests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method, url", [
    ("post", "/api/orders"),
    ("put", "/api/orders/1"),
    ("get", "/api/orders/1"),
    ("post", "/api/orders/1/confirm"),
    ("post", "/api/orders/1/cancel"),
])
def test_order_endpoints_need_login(client, method, url):
    response = getattr(client, method)(url, json={})
    assert response.status_code == 401
    assert response.get_json() == {"error": "Please log in first.", "details": {}}


def test_logged_out_call_gets_401_even_with_csrf_on(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    response = client.post("/api/orders", json={})
    assert response.status_code == 401


def test_csrf_token_from_page_meta_tag(app, client, login, sales_user, customer, make_product, monkeypatch):
    """With CSRF on (as in the real app), POST needs the X-CSRFToken header from the page."""
    product = make_product()
    login(client, sales_user)
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    body = order_body(customer, [(product, 1)])

    without_token = client.post("/api/orders", json=body)
    assert without_token.status_code == 400
    assert without_token.get_json()["error"] == "The CSRF token is missing."

    page = client.get("/orders/").get_data(as_text=True)
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page).group(1)
    with_token = client.post("/api/orders", json=body, headers={"X-CSRFToken": token})
    assert with_token.status_code == 201


def test_malformed_json_is_400(client, login, sales_user):
    login(client, sales_user)

    broken = client.post("/api/orders", data="{not json", content_type="application/json")
    assert broken.status_code == 400
    assert broken.get_json() == {"error": "The request body must be a JSON object.", "details": {}}

    a_list = client.post("/api/orders", json=[1, 2])
    assert a_list.status_code == 400

    no_body = client.post("/api/orders")
    assert no_body.status_code == 400


def test_unexpected_error_is_500_without_traceback(client, login, sales_user, monkeypatch):
    def broken_service(order_id, user):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(order_service, "confirm_order", broken_service)
    login(client, sales_user)

    response = client.post("/api/orders/1/confirm")

    assert response.status_code == 500
    assert response.get_json() == {
        "error": "Something went wrong on our side. Please try again.",
        "details": {},
    }
    assert "secret internal detail" not in response.get_data(as_text=True)
    assert "Traceback" not in response.get_data(as_text=True)


def test_unknown_order_is_404(client, login, sales_user):
    login(client, sales_user)
    for method, url in [
        ("get", "/api/orders/999999"),
        ("put", "/api/orders/999999"),
        ("post", "/api/orders/999999/confirm"),
        ("post", "/api/orders/999999/cancel"),
    ]:
        response = getattr(client, method)(url, json={})
        assert response.status_code == 404, url
        assert response.get_json() == {"error": "Order not found.", "details": {}}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_order_with_items_and_discount(client, login, sales_user, customer, make_product):
    """Part 12: an order with several items and a discount gets the right totals."""
    keyboard = make_product(code="KEY-001", price="1500.00", stock=10)
    mouse = make_product(code="MOU-001", price="500.00", stock=10)
    login(client, sales_user)

    response = client.post(
        "/api/orders", json=order_body(customer, [(keyboard, 2), (mouse, 3)], discount="10")
    )

    assert response.status_code == 201
    order = response.get_json()
    assert order["status"] == "draft"
    assert order["order_number"] == f"SO-{order['id']:06d}"
    assert order["customer"] == {"id": customer.id, "name": customer.name}
    assert order["created_by"] == {"id": sales_user.id, "name": sales_user.name}
    assert order["discount_percent"] == "10.00"
    assert order["subtotal"] == "4500.00"
    assert order["discount_amount"] == "450.00"
    assert order["grand_total"] == "4050.00"
    assert [(i["product"]["code"], i["quantity"], i["rate"], i["amount"]) for i in order["items"]] == [
        ("KEY-001", 2, "1500.00", "3000.00"),
        ("MOU-001", 3, "500.00", "1500.00"),
    ]
    # A draft doesn't touch stock.
    assert stock_of(keyboard) == 10


def test_client_sent_money_status_and_owner_are_ignored(
    client, login, sales_user, other_sales_user, customer, make_product
):
    product = make_product(price="250.00")
    login(client, sales_user)
    body = order_body(customer, [(product, 2)])
    body["items"][0]["rate"] = "1.00"
    body["items"][0]["amount"] = "2.00"
    body.update({
        "subtotal": "2.00",
        "grand_total": "1.00",
        "status": "confirmed",
        "created_by": other_sales_user.id,
    })

    order = client.post("/api/orders", json=body).get_json()

    assert order["items"][0]["rate"] == "250.00"
    assert order["items"][0]["amount"] == "500.00"
    assert order["grand_total"] == "500.00"
    assert order["status"] == "draft"
    assert order["created_by"]["id"] == sales_user.id


@pytest.mark.parametrize("quantity", [0, -1])
def test_zero_or_negative_quantity_rejected(client, login, sales_user, customer, make_product, quantity):
    """Part 12: zero or negative quantity is rejected."""
    product = make_product()
    login(client, sales_user)

    response = client.post("/api/orders", json=order_body(customer, [(product, quantity)]))

    assert response.status_code == 422
    assert response.get_json()["details"] == {"items[0].quantity": "Must be more than zero."}


@pytest.mark.parametrize("discount", ["-1", "20.01", "25", 50])
def test_discount_outside_0_to_20_rejected(client, login, sales_user, customer, make_product, discount):
    """Part 12: a discount outside 0-20% is rejected."""
    product = make_product()
    login(client, sales_user)

    response = client.post("/api/orders", json=order_body(customer, [(product, 1)], discount=discount))

    assert response.status_code == 422
    assert response.get_json()["details"] == {"discount_percent": "Must be between 0 and 20."}


def test_discount_edges_accepted(client, login, sales_user, customer, make_product):
    product = make_product()
    login(client, sales_user)
    for discount in ("0", "20"):
        response = client.post("/api/orders", json=order_body(customer, [(product, 1)], discount=discount))
        assert response.status_code == 201


def test_every_bad_field_reported_at_once(client, login, sales_user, make_product):
    product = make_product()
    login(client, sales_user)

    response = client.post("/api/orders", json={
        "customer_id": "abc",
        "discount_percent": "x",
        "items": [{"product_id": product.id, "quantity": "2.5"}, {"product_id": None, "quantity": 1}],
    })

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "Please fix the problems in this order."
    assert body["details"] == {
        "customer_id": "Choose a customer.",
        "discount_percent": "Must be a number.",
        "items[0].quantity": "Must be a whole number.",
        "items[1].product_id": "Choose a product.",
    }


def test_missing_items_rejected(client, login, sales_user, customer):
    login(client, sales_user)
    response = client.post("/api/orders", json={"customer_id": customer.id, "items": []})
    assert response.status_code == 422
    assert response.get_json()["details"] == {"items": "Add at least one item."}


def test_inactive_product_rejected(client, login, sales_user, customer, make_product):
    product = make_product(is_active=False)
    login(client, sales_user)
    response = client.post("/api/orders", json=order_body(customer, [(product, 1)]))
    assert response.status_code == 422
    assert response.get_json()["details"] == {"items[0].product_id": "Choose an active product."}


# ---------------------------------------------------------------------------
# View and edit
# ---------------------------------------------------------------------------

def test_get_own_order(client, login, sales_user, customer, make_product, make_order):
    product = make_product(price="100.00")
    order = make_order(sales_user, customer, [(product, 3)])
    login(client, sales_user)

    response = client.get(f"/api/orders/{order.id}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == order.id
    assert body["grand_total"] == "300.00"
    assert len(body["items"]) == 1
    assert "password" not in response.get_data(as_text=True)


def test_sales_user_cannot_touch_another_users_order(
    client, login, sales_user, other_sales_user, customer, make_product, make_order
):
    """Part 12: a sales user opening another user's order is refused, and nothing changes."""
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 2)])
    login(client, other_sales_user)

    attempts = [
        client.get(f"/api/orders/{order.id}"),
        client.put(f"/api/orders/{order.id}", json=order_body(customer, [(product, 5)])),
        client.post(f"/api/orders/{order.id}/confirm"),
        client.post(f"/api/orders/{order.id}/cancel"),
    ]

    for response in attempts:
        assert response.status_code == 403
        assert response.get_json() == {"error": "You do not have access to this order.", "details": {}}
    db.session.refresh(order)
    assert order.status == "draft"
    assert order.items[0].quantity == 2
    assert stock_of(product) == 10


def test_admin_can_see_any_order(client, login, admin_user, sales_user, customer, make_product, make_order):
    order = make_order(sales_user, customer, [(make_product(), 1)])
    login(client, admin_user)
    assert client.get(f"/api/orders/{order.id}").status_code == 200


def test_update_draft(client, login, sales_user, customer, make_customer, make_product, make_order):
    keyboard = make_product(price="1500.00")
    mouse = make_product(price="500.00")
    order = make_order(sales_user, customer, [(keyboard, 1)])
    new_customer = make_customer()
    login(client, sales_user)

    response = client.put(
        f"/api/orders/{order.id}",
        json=order_body(new_customer, [(keyboard, 2), (mouse, 3)], discount="10"),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["customer"]["id"] == new_customer.id
    assert body["status"] == "draft"
    assert len(body["items"]) == 2
    assert body["grand_total"] == "4050.00"


def test_update_with_bad_input_is_422(client, login, sales_user, customer, make_product, make_order):
    product = make_product()
    order = make_order(sales_user, customer, [(product, 1)])
    login(client, sales_user)
    response = client.put(f"/api/orders/{order.id}", json=order_body(customer, [(product, 0)]))
    assert response.status_code == 422


def test_confirmed_order_cannot_be_edited(client, login, sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 2)])
    login(client, sales_user)
    client.post(f"/api/orders/{order.id}/confirm")

    response = client.put(f"/api/orders/{order.id}", json=order_body(customer, [(product, 5)]))

    assert response.status_code == 409
    assert response.get_json() == {
        "error": f"Order {order.order_number} is confirmed and can't be edited.",
        "details": {"status": "confirmed"},
    }
    assert stock_of(product) == 8


# ---------------------------------------------------------------------------
# Confirm and cancel
# ---------------------------------------------------------------------------

def test_confirm_with_enough_stock(client, login, sales_user, customer, make_product, make_order):
    """Part 12: confirming with enough stock confirms the order and takes the stock."""
    keyboard = make_product(stock=10)
    mouse = make_product(stock=3)
    order = make_order(sales_user, customer, [(keyboard, 2), (mouse, 3)])
    login(client, sales_user)

    response = client.post(f"/api/orders/{order.id}/confirm")

    assert response.status_code == 200
    assert response.get_json()["status"] == "confirmed"
    assert stock_of(keyboard) == 8
    assert stock_of(mouse) == 0


def test_confirm_with_one_short_item_changes_nothing(
    client, login, sales_user, customer, make_product, make_order
):
    """Part 12: one item short -> 409 with the shortages, no stock or status change."""
    plenty = make_product(stock=10)
    short = make_product(code="SHORT-1", stock=1)
    order = make_order(sales_user, customer, [(plenty, 2), (short, 3)])
    login(client, sales_user)

    response = client.post(f"/api/orders/{order.id}/confirm")

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "Not enough stock to confirm this order.",
        "details": {"shortages": [
            {"product_id": short.id, "code": "SHORT-1", "requested": 3, "available": 1},
        ]},
    }
    assert stock_of(plenty) == 10
    assert stock_of(short) == 1
    assert client.get(f"/api/orders/{order.id}").get_json()["status"] == "draft"


def test_confirm_with_a_deactivated_product_gives_409(
    client, login, sales_user, customer, make_product, make_order
):
    product = make_product(code="OLD-2", stock=10)
    order = make_order(sales_user, customer, [(product, 1)])
    product.is_active = False
    db.session.commit()
    login(client, sales_user)

    response = client.post(f"/api/orders/{order.id}/confirm")

    assert response.status_code == 409
    assert response.get_json() == {
        "error": f"Order {order.order_number} can't be confirmed: these products are inactive: OLD-2. "
                 "Edit the draft first.",
        "details": {"inactive_products": ["OLD-2"]},
    }
    assert stock_of(product) == 10
    assert client.get(f"/api/orders/{order.id}").get_json()["status"] == "draft"


def test_repeated_confirm_does_not_deduct_again(client, login, sales_user, customer, make_product, make_order):
    """Part 12: confirming twice takes the stock only once."""
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])
    login(client, sales_user)

    first = client.post(f"/api/orders/{order.id}/confirm")
    second = client.post(f"/api/orders/{order.id}/confirm")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.get_json() == {
        "error": f"Order {order.order_number} is already confirmed.",
        "details": {"status": "confirmed"},
    }
    assert stock_of(product) == 6


def test_cancel_confirmed_restores_stock_once(client, login, sales_user, customer, make_product, make_order):
    """Part 12: cancelling a confirmed order gives the stock back exactly once."""
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])
    login(client, sales_user)
    client.post(f"/api/orders/{order.id}/confirm")
    assert stock_of(product) == 6

    first = client.post(f"/api/orders/{order.id}/cancel")
    second = client.post(f"/api/orders/{order.id}/cancel")

    assert first.status_code == 200
    assert first.get_json()["status"] == "cancelled"
    assert second.status_code == 409
    assert second.get_json() == {
        "error": f"Order {order.order_number} is already cancelled.",
        "details": {"status": "cancelled"},
    }
    assert stock_of(product) == 10


def test_cancel_draft_leaves_stock_alone(client, login, sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])
    login(client, sales_user)

    response = client.post(f"/api/orders/{order.id}/cancel")

    assert response.status_code == 200
    assert response.get_json()["status"] == "cancelled"
    assert stock_of(product) == 10


def test_cancelled_order_cannot_be_confirmed(client, login, sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])
    login(client, sales_user)
    client.post(f"/api/orders/{order.id}/cancel")

    response = client.post(f"/api/orders/{order.id}/confirm")

    assert response.status_code == 409
    assert stock_of(product) == 10


def test_admin_can_confirm_a_sales_users_order(
    client, login, admin_user, sales_user, customer, make_product, make_order
):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])
    login(client, admin_user)
    assert client.post(f"/api/orders/{order.id}/confirm").status_code == 200
    assert stock_of(product) == 6


def test_order_too_large_for_the_database_gives_422_not_500(client, login, sales_user, customer, make_product):
    product = make_product(price="100000.00")
    login(client, sales_user)

    response = client.post("/api/orders", json=order_body(customer, [(product, 1_000_000)]))

    assert response.status_code == 422
    assert "items[0].quantity" in response.get_json()["details"]
