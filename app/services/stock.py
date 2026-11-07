"""Stock changes. Stock works like a bank account:

- stock_movements is the statement: one row per change, with a type and a reason
- products.stock_quantity is the balance

change_stock() is the only function that changes stock_quantity, and it always writes the
movement row in the same step. So the balance always equals the sum of the movements.
"""
from sqlalchemy import select

from app.errors import ForbiddenError, NotFoundError, ValidationError
from app.extensions import db
from app.models import MOVEMENT_ADJUSTMENT, Product, StockMovement
from app.services.pricing import parse_int

MAX_REASON_LENGTH = 255


def change_stock(product, quantity_change, movement_type, user, reason, order=None):
    """Add quantity_change to the product's stock and record a movement for it.

    Does not commit: the caller owns the transaction, so the stock change, the movement and
    anything else (like an order's new status) are saved together or not at all.
    For sales, cancellations and adjustments the caller must already hold a lock on the
    product row (lock_products below). For a brand new product no lock is needed.
    """
    new_quantity = product.stock_quantity + quantity_change
    if new_quantity < 0:
        # Callers check first and give a friendlier message. This is the last safety net.
        raise ValidationError(f"Stock for {product.code} can't go below zero.")
    product.stock_quantity = new_quantity
    movement = StockMovement(
        product=product,
        movement_type=movement_type,
        quantity_change=quantity_change,
        order=order,
        reason=reason,
        created_by=user.id,
    )
    db.session.add(movement)
    return movement


def lock_products(product_ids):
    """SELECT ... FOR UPDATE the given products, always in id order. Returns {id: product}.

    The lock makes any other transaction that wants these rows wait until we commit or roll
    back. Locking in id order every time means two transactions can't each hold one row and
    wait for the other's (a deadlock).
    """
    query = (
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    products = db.session.execute(query).scalars().all()
    return {product.id: product for product in products}


def adjust_stock(product_id, quantity_change, reason, user):
    """Admin action: raise or lower a product's stock by hand, with a reason.

    One transaction: lock the product, check the result stays at zero or above, change the
    stock, write an 'adjustment' movement, commit. Returns the product.
    """
    try:
        if not user.is_admin:
            raise ForbiddenError("Only an admin can adjust stock.")

        quantity_change = parse_int(quantity_change, "quantity_change")
        if quantity_change == 0:
            raise ValidationError(
                "Enter a change other than zero.", {"quantity_change": "Can't be zero."}
            )
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required.", {"reason": "Required."})
        if len(reason) > MAX_REASON_LENGTH:
            raise ValidationError(
                f"Reason can be at most {MAX_REASON_LENGTH} characters.",
                {"reason": f"At most {MAX_REASON_LENGTH} characters."},
            )

        product = lock_products([product_id]).get(product_id)
        if product is None:
            raise NotFoundError("Product not found.")

        if product.stock_quantity + quantity_change < 0:
            raise ValidationError(
                f"Stock can't go below zero. {product.code} has {product.stock_quantity} in stock.",
                {"quantity_change": f"Can't remove more than {product.stock_quantity}."},
            )

        change_stock(product, quantity_change, MOVEMENT_ADJUSTMENT, user, reason)
        db.session.commit()
        return product
    except Exception:
        db.session.rollback()
        raise
