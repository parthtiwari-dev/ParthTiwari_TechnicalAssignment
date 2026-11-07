"""Two users confirm orders for the same product at the same moment. Stock covers only one.

How the test forces a real race:
1. The test itself locks the product row (SELECT ... FOR UPDATE on its own connection).
2. Two threads start, each confirming a different order. Each locks its own order, then
   blocks waiting for the product lock the test is holding.
3. The test waits until both are stuck, then releases its lock.
4. MySQL lets one thread through. It takes the stock and commits. The other then gets the
   lock, sees the new (lower) stock and refuses with a shortage.
"""
import threading
import time

from sqlalchemy import select

from app.errors import ConflictError
from app.extensions import db
from app.models import MOVEMENT_SALE, STATUS_CONFIRMED, STATUS_DRAFT, Product, SalesOrder, StockMovement, User
from app.services.orders import confirm_order


def test_two_confirms_cannot_oversell(app, sales_user, other_sales_user, customer, make_product, make_order):
    product = make_product(stock=5)
    first_order = make_order(sales_user, customer, [(product, 4)])
    second_order = make_order(other_sales_user, customer, [(product, 4)])
    jobs = [(first_order.id, sales_user.id), (second_order.id, other_sales_user.id)]
    product_id = product.id

    results = []
    start = threading.Barrier(len(jobs))

    def confirm_in_own_session(order_id, user_id):
        # A new app context gives this thread its own database session and connection.
        with app.app_context():
            user = db.session.get(User, user_id)
            start.wait()
            try:
                confirm_order(order_id, user)
                results.append("confirmed")
            except ConflictError:
                results.append("conflict")

    # Hold the product lock on a separate connection so both threads pile up behind it.
    blocker = db.engine.connect()
    blocker_transaction = blocker.begin()
    blocker.execute(select(Product).where(Product.id == product_id).with_for_update())

    threads = [threading.Thread(target=confirm_in_own_session, args=job) for job in jobs]
    for thread in threads:
        thread.start()
    time.sleep(1.0)  # both threads are now waiting for the product row
    assert results == [], "a thread finished while the product row was locked"
    blocker_transaction.rollback()
    blocker.close()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(results) == ["confirmed", "conflict"]

    db.session.expire_all()
    product = db.session.get(Product, product_id)
    assert product.stock_quantity == 1
    statuses = sorted(db.session.get(SalesOrder, order_id).status for order_id, _ in jobs)
    assert statuses == [STATUS_CONFIRMED, STATUS_DRAFT]
    sales = db.session.execute(
        select(StockMovement).where(
            StockMovement.product_id == product_id, StockMovement.movement_type == MOVEMENT_SALE
        )
    ).scalars().all()
    assert [movement.quantity_change for movement in sales] == [-4]
