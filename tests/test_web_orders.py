"""Order pages: who sees which orders, read-only after confirm/cancel, the form page."""
from app.services.orders import cancel_order, confirm_order


def test_sales_user_lists_only_own_orders(client, login, sales_user, other_sales_user, customer, make_product, make_order):
    product = make_product()
    mine = make_order(sales_user, customer, [(product, 1)])
    theirs = make_order(other_sales_user, customer, [(product, 1)])
    login(client, sales_user)

    page = client.get("/orders/")
    assert mine.order_number.encode() in page.data
    assert theirs.order_number.encode() not in page.data


def test_admin_lists_all_orders_and_filters_by_status(client, login, admin_user, sales_user, customer, make_product, make_order):
    product = make_product()
    draft = make_order(sales_user, customer, [(product, 1)])
    confirmed = confirm_order(make_order(sales_user, customer, [(product, 1)]).id, sales_user)
    login(client, admin_user)

    page = client.get("/orders/")
    assert draft.order_number.encode() in page.data and confirmed.order_number.encode() in page.data

    page = client.get("/orders/?status=confirmed")
    assert confirmed.order_number.encode() in page.data
    assert draft.order_number.encode() not in page.data


def test_sales_user_gets_403_on_another_users_order_pages(client, login, sales_user, other_sales_user, customer, make_product, make_order):
    order = make_order(other_sales_user, customer, [(make_product(), 1)])
    login(client, sales_user)
    assert client.get(f"/orders/{order.id}").status_code == 403
    assert client.get(f"/orders/{order.id}/edit").status_code == 403


def test_missing_order_is_404(client, login, admin_user):
    login(client, admin_user)
    assert client.get("/orders/999999999").status_code == 404


def test_draft_order_page_shows_items_totals_and_actions(client, login, sales_user, customer, make_product, make_order):
    keyboard = make_product(name="Keyboard", price="1500.00")
    mouse = make_product(name="Mouse", price="500.00")
    order = make_order(sales_user, customer, [(keyboard, 2), (mouse, 3)], discount="10")
    login(client, sales_user)

    page = client.get(f"/orders/{order.id}")
    assert page.status_code == 200
    for text in [b"4500.00", b"450.00", b"4050.00", b"Sales One", customer.name.encode(),
                 b"Edit draft", b"Confirm order", b"Cancel order"]:
        assert text in page.data


def test_confirmed_order_is_read_only(client, login, sales_user, customer, make_product, make_order):
    order = confirm_order(make_order(sales_user, customer, [(make_product(), 1)]).id, sales_user)
    login(client, sales_user)

    page = client.get(f"/orders/{order.id}")
    assert b"Edit draft" not in page.data
    assert b"Confirm order" not in page.data
    assert b"Cancel order" in page.data  # a confirmed order can still be cancelled

    response = client.get(f"/orders/{order.id}/edit")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/orders/{order.id}")


def test_cancelled_order_has_no_actions(client, login, sales_user, customer, make_product, make_order):
    order = cancel_order(make_order(sales_user, customer, [(make_product(), 1)]).id, sales_user)
    login(client, sales_user)

    page = client.get(f"/orders/{order.id}")
    assert b"Confirm order" not in page.data and b"Cancel order" not in page.data
    response = client.get(f"/orders/{order.id}/edit", follow_redirects=True)
    assert b"can&#39;t be edited" in response.data


def test_new_order_form_lists_only_active_customers_and_products(client, login, sales_user, make_customer, make_product):
    make_customer(name="Live Customer")
    make_customer(name="Gone Customer", is_active=False)
    make_product(code="LIVE-001")
    make_product(code="GONE-001", is_active=False)
    login(client, sales_user)

    page = client.get("/orders/new")
    assert page.status_code == 200
    assert b"Live Customer" in page.data and b"Gone Customer" not in page.data
    assert b"LIVE-001" in page.data and b"GONE-001" not in page.data
    assert b"js/order_form.js" in page.data


def test_edit_form_carries_the_order_for_the_script(client, login, sales_user, customer, make_product, make_order):
    product = make_product(code="EDIT-001")
    order = make_order(sales_user, customer, [(product, 4)])
    login(client, sales_user)

    page = client.get(f"/orders/{order.id}/edit")
    assert page.status_code == 200
    assert f'data-order-id="{order.id}"'.encode() in page.data
    assert order.order_number.encode() in page.data
