"""The stock adjustment page: reason required, never below zero, one movement per adjustment."""
from sqlalchemy import func, select

from app.extensions import db
from app.models import MOVEMENT_ADJUSTMENT, StockMovement


def _movement_count(product):
    return db.session.scalar(
        select(func.count()).select_from(StockMovement).where(StockMovement.product_id == product.id)
    )


def test_adjustment_with_reason_changes_stock_and_records_movement(client, login, admin_user, make_product):
    product = make_product(stock=10)
    login(client, admin_user)

    response = client.post("/stock/", data={
        "product_id": product.id, "quantity_change": "-3", "reason": "Damaged in transit",
    })
    assert response.status_code == 302
    db.session.refresh(product)
    assert product.stock_quantity == 7

    movement = db.session.scalars(
        select(StockMovement).where(StockMovement.movement_type == MOVEMENT_ADJUSTMENT)
    ).one()
    assert movement.quantity_change == -3
    assert movement.reason == "Damaged in transit"
    assert movement.created_by == admin_user.id

    page = client.get(f"/stock/?product_id={product.id}")
    assert b"Damaged in transit" in page.data


def test_adjustment_without_reason_rejected(client, login, admin_user, make_product):
    product = make_product(stock=10)
    login(client, admin_user)
    response = client.post("/stock/", data={"product_id": product.id, "quantity_change": "5", "reason": "  "})
    assert response.status_code == 422
    assert b"A reason is required." in response.data
    db.session.refresh(product)
    assert product.stock_quantity == 10
    assert _movement_count(product) == 1  # only the opening stock


def test_adjustment_below_zero_rejected(client, login, admin_user, make_product):
    product = make_product(stock=2)
    login(client, admin_user)
    response = client.post("/stock/", data={"product_id": product.id, "quantity_change": "-3", "reason": "Count"})
    assert response.status_code == 422
    assert b"Stock can&#39;t go below zero." in response.data
    db.session.refresh(product)
    assert product.stock_quantity == 2
    assert _movement_count(product) == 1


def test_adjustment_needs_a_product(client, login, admin_user):
    login(client, admin_user)
    response = client.post("/stock/", data={"product_id": "", "quantity_change": "1", "reason": "x"})
    assert response.status_code == 422
    assert b"Choose a product." in response.data


def test_sales_user_cannot_adjust_stock(client, login, sales_user, make_product):
    product = make_product(stock=5)
    login(client, sales_user)
    response = client.post("/stock/", data={"product_id": product.id, "quantity_change": "5", "reason": "x"})
    assert response.status_code == 403
    db.session.refresh(product)
    assert product.stock_quantity == 5
