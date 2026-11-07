"""Order rules in services/orders.py: drafts, confirm, cancel, stock and ownership."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.errors import ConflictError, ForbiddenError, ValidationError
from app.extensions import db
from app.models import (
    MOVEMENT_CANCELLATION,
    MOVEMENT_SALE,
    STATUS_CANCELLED,
    STATUS_CONFIRMED,
    STATUS_DRAFT,
    SalesOrder,
    StockMovement,
)
from app.services.orders import (
    cancel_order,
    confirm_order,
    create_draft_order,
    update_draft_order,
)


def movements(product, movement_type):
    query = select(StockMovement).where(
        StockMovement.product_id == product.id, StockMovement.movement_type == movement_type
    )
    return db.session.execute(query).scalars().all()


def test_create_draft_computes_totals_and_number(sales_user, customer, make_product):
    keyboard = make_product(price="1500.00", stock=10)
    mouse = make_product(price="500.00", stock=10)

    order = create_draft_order(
        sales_user,
        customer.id,
        [{"product_id": keyboard.id, "quantity": 2}, {"product_id": mouse.id, "quantity": 3}],
        "10",
    )

    assert order.status == STATUS_DRAFT
    assert order.order_number == f"SO-{order.id:06d}"
    assert order.subtotal == Decimal("4500.00")
    assert order.discount_amount == Decimal("450.00")
    assert order.grand_total == Decimal("4050.00")
    assert [item.amount for item in order.items] == [Decimal("3000.00"), Decimal("1500.00")]
    # Drafts don't touch stock.
    assert keyboard.stock_quantity == 10


def test_client_rate_is_ignored(sales_user, customer, make_product):
    product = make_product(price="250.00")
    order = create_draft_order(
        sales_user, customer.id, [{"product_id": product.id, "quantity": 1, "rate": "1.00"}], "0"
    )
    assert order.items[0].rate == Decimal("250.00")


def test_confirm_with_enough_stock(sales_user, customer, make_product, make_order):
    keyboard = make_product(stock=10)
    mouse = make_product(stock=5)
    order = make_order(sales_user, customer, [(keyboard, 2), (mouse, 5)])

    confirm_order(order.id, sales_user)

    assert order.status == STATUS_CONFIRMED
    assert keyboard.stock_quantity == 8
    assert mouse.stock_quantity == 0
    sale = movements(keyboard, MOVEMENT_SALE)
    assert len(sale) == 1
    assert sale[0].quantity_change == -2
    assert sale[0].order_id == order.id


def test_confirm_with_one_short_item_changes_nothing(sales_user, customer, make_product, make_order):
    plenty = make_product(stock=10)
    short = make_product(stock=1)
    order = make_order(sales_user, customer, [(plenty, 2), (short, 3)])

    with pytest.raises(ConflictError) as error:
        confirm_order(order.id, sales_user)

    assert error.value.details["shortages"] == [
        {"product_id": short.id, "code": short.code, "requested": 3, "available": 1}
    ]
    assert order.status == STATUS_DRAFT
    assert plenty.stock_quantity == 10
    assert short.stock_quantity == 1
    assert movements(plenty, MOVEMENT_SALE) == []


def test_repeated_confirm_does_not_deduct_again(sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])
    confirm_order(order.id, sales_user)

    with pytest.raises(ConflictError):
        confirm_order(order.id, sales_user)

    assert product.stock_quantity == 6
    assert len(movements(product, MOVEMENT_SALE)) == 1


def test_cancel_confirmed_restores_stock_once(sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])
    confirm_order(order.id, sales_user)

    cancel_order(order.id, sales_user)
    assert order.status == STATUS_CANCELLED
    assert product.stock_quantity == 10

    with pytest.raises(ConflictError):
        cancel_order(order.id, sales_user)
    assert product.stock_quantity == 10
    restored = movements(product, MOVEMENT_CANCELLATION)
    assert len(restored) == 1
    assert restored[0].quantity_change == 4


def test_cancel_draft_leaves_stock_alone(sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 4)])

    cancel_order(order.id, sales_user)

    assert order.status == STATUS_CANCELLED
    assert product.stock_quantity == 10
    assert movements(product, MOVEMENT_CANCELLATION) == []


def test_cancelled_order_cannot_be_confirmed(sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 1)])
    cancel_order(order.id, sales_user)

    with pytest.raises(ConflictError):
        confirm_order(order.id, sales_user)
    assert product.stock_quantity == 10


def test_duplicate_product_rejected(sales_user, customer, make_product):
    product = make_product()
    with pytest.raises(ValidationError) as error:
        create_draft_order(
            sales_user,
            customer.id,
            [{"product_id": product.id, "quantity": 1}, {"product_id": product.id, "quantity": 2}],
            "0",
        )
    assert "items[1].product_id" in error.value.details
    assert db.session.scalar(select(func.count()).select_from(SalesOrder)) == 0


def test_at_least_one_item_required(sales_user, customer):
    with pytest.raises(ValidationError) as error:
        create_draft_order(sales_user, customer.id, [], "0")
    assert "items" in error.value.details


def test_inactive_product_rejected(sales_user, customer, make_product):
    product = make_product(is_active=False)
    with pytest.raises(ValidationError) as error:
        create_draft_order(sales_user, customer.id, [{"product_id": product.id, "quantity": 1}], "0")
    assert "items[0].product_id" in error.value.details


def test_inactive_customer_rejected(sales_user, make_customer, make_product):
    inactive = make_customer(is_active=False)
    product = make_product()
    with pytest.raises(ValidationError) as error:
        create_draft_order(sales_user, inactive.id, [{"product_id": product.id, "quantity": 1}], "0")
    assert "customer_id" in error.value.details


def test_bad_quantity_and_discount_reported_together(sales_user, customer, make_product):
    product = make_product()
    with pytest.raises(ValidationError) as error:
        create_draft_order(sales_user, customer.id, [{"product_id": product.id, "quantity": 0}], "25")
    assert set(error.value.details) == {"items[0].quantity", "discount_percent"}


def test_stored_rate_survives_price_change(sales_user, customer, make_product, make_order):
    product = make_product(price="100.00")
    order = make_order(sales_user, customer, [(product, 2)])

    product.price = Decimal("150.00")
    db.session.commit()
    # Editing the draft keeps the rate for a product already on it.
    update_draft_order(order.id, sales_user, customer.id, [{"product_id": product.id, "quantity": 3}], "0")

    assert order.items[0].rate == Decimal("100.00")
    assert order.grand_total == Decimal("300.00")


def test_update_draft_replaces_items(sales_user, customer, make_product, make_order):
    first = make_product(price="10.00")
    second = make_product(price="20.00")
    order = make_order(sales_user, customer, [(first, 1)])

    update_draft_order(order.id, sales_user, customer.id, [{"product_id": second.id, "quantity": 2}], "5")

    assert [item.product_id for item in order.items] == [second.id]
    assert order.subtotal == Decimal("40.00")
    assert order.discount_amount == Decimal("2.00")
    assert order.grand_total == Decimal("38.00")


def test_confirmed_order_cannot_be_edited(sales_user, customer, make_product, make_order):
    product = make_product()
    order = make_order(sales_user, customer, [(product, 1)])
    confirm_order(order.id, sales_user)

    with pytest.raises(ConflictError):
        update_draft_order(order.id, sales_user, customer.id, [{"product_id": product.id, "quantity": 2}], "0")


def test_sales_user_cannot_confirm_another_users_order(
    sales_user, other_sales_user, customer, make_product, make_order
):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 2)])

    with pytest.raises(ForbiddenError):
        confirm_order(order.id, other_sales_user)
    with pytest.raises(ForbiddenError):
        cancel_order(order.id, other_sales_user)

    assert order.status == STATUS_DRAFT
    assert product.stock_quantity == 10


def test_admin_can_confirm_any_order(admin_user, sales_user, customer, make_product, make_order):
    product = make_product(stock=10)
    order = make_order(sales_user, customer, [(product, 2)])

    confirm_order(order.id, admin_user)

    assert order.status == STATUS_CONFIRMED
    assert product.stock_quantity == 8
