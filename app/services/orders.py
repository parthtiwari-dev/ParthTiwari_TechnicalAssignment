"""Sales order rules: create and edit drafts, confirm, cancel.

Every public function here owns its transaction: it commits when everything worked and
rolls back on any error, so a half-finished change is never saved.

Nothing the browser sends about money is trusted. The browser sends only customer_id,
discount_percent and items [{product_id, quantity}]. Rates come from the database and all
totals come from services/pricing.py.
"""
from datetime import date

from app.errors import ConflictError, ValidationError
from app.extensions import db
from app.models import (
    MOVEMENT_CANCELLATION,
    MOVEMENT_SALE,
    STATUS_CANCELLED,
    STATUS_CONFIRMED,
    STATUS_DRAFT,
    Customer,
    Product,
    SalesOrder,
    SalesOrderItem,
)
from app.permissions import get_order_for_user
from app.services.pricing import calculate_totals, parse_discount, parse_int, parse_quantity
from app.services.stock import change_stock, lock_products


# ---------------------------------------------------------------------------
# Input checks shared by create and update
# ---------------------------------------------------------------------------

def _validate_order_input(customer_id, items, discount_percent):
    """Check everything the user sent. Returns (customer, [(product, quantity)], discount).

    Collects every problem into one ValidationError, so the user can fix them all at once.
    Error keys: "customer_id", "discount_percent", "items", and "items[0].product_id",
    "items[0].quantity" for a single row (0 is the row's position in the list).
    """
    errors = {}

    customer = None
    try:
        customer = db.session.get(Customer, parse_int(customer_id, "customer_id"))
        if customer is None or not customer.is_active:
            errors["customer_id"] = "Choose an active customer."
    except ValidationError:
        errors["customer_id"] = "Choose a customer."

    discount = None
    try:
        discount = parse_discount(discount_percent)
    except ValidationError as error:
        errors.update(error.details)

    lines = []
    if not isinstance(items, list) or len(items) == 0:
        errors["items"] = "Add at least one item."
    else:
        seen_product_ids = set()
        for index, item in enumerate(items):
            product_field = f"items[{index}].product_id"
            quantity_field = f"items[{index}].quantity"
            if not isinstance(item, dict):
                errors[product_field] = "Each item needs a product and a quantity."
                continue

            product = None
            try:
                product_id = parse_int(item.get("product_id"), product_field)
                product = db.session.get(Product, product_id)
                if product is None or not product.is_active:
                    errors[product_field] = "Choose an active product."
                    product = None
                elif product_id in seen_product_ids:
                    errors[product_field] = "This product is already in the order."
                    product = None
                else:
                    seen_product_ids.add(product_id)
            except ValidationError:
                errors[product_field] = "Choose a product."

            try:
                quantity = parse_quantity(item.get("quantity"), quantity_field)
            except ValidationError as error:
                errors.update(error.details)
                quantity = None

            if product is not None and quantity is not None:
                lines.append((product, quantity))

    if errors:
        raise ValidationError("Please fix the problems in this order.", errors)
    return customer, lines, discount


def _set_items_and_totals(order, lines):
    """Make the order's items match `lines`, then work out every amount.

    A product already on the order keeps its row and its stored rate; only the quantity
    changes. A new product gets a new row with today's price as its rate. Products no longer
    in `lines` are deleted (delete-orphan on the relationship).
    """
    existing_items = {item.product_id: item for item in order.items}
    new_items = []
    for product, quantity in lines:
        item = existing_items.get(product.id)
        if item is None:
            item = SalesOrderItem(product=product, rate=product.price)
        item.quantity = quantity
        new_items.append(item)
    order.items = new_items

    totals = calculate_totals(
        [(item.quantity, item.rate) for item in new_items], order.discount_percent
    )
    for item, amount in zip(new_items, totals["amounts"]):
        item.amount = amount
    order.subtotal = totals["subtotal"]
    order.discount_amount = totals["discount_amount"]
    order.grand_total = totals["grand_total"]


# ---------------------------------------------------------------------------
# Draft orders
# ---------------------------------------------------------------------------

def create_draft_order(user, customer_id, items, discount_percent):
    """Create a Draft order for `user`. Draft orders don't touch stock.

    The order number is built from the row id ("SO-000123"), so it is unique without any
    counter table. flush() sends the INSERT so MySQL hands us the id before we commit.
    """
    try:
        customer, lines, discount = _validate_order_input(customer_id, items, discount_percent)
        order = SalesOrder(
            customer=customer,
            order_date=date.today(),
            status=STATUS_DRAFT,
            discount_percent=discount,
            created_by=user.id,
        )
        db.session.add(order)
        _set_items_and_totals(order, lines)
        db.session.flush()
        order.order_number = f"SO-{order.id:06d}"
        db.session.commit()
        return order
    except Exception:
        db.session.rollback()
        raise


def update_draft_order(order_id, user, customer_id, items, discount_percent):
    """Replace a Draft order's customer, discount and items. Only drafts can change.

    The order row is locked first, so an edit can't slip in while someone confirms it.
    """
    try:
        order = get_order_for_user(order_id, user, lock=True)
        if order.status != STATUS_DRAFT:
            raise ConflictError(
                f"Order {order.order_number} is {order.status} and can't be edited.",
                {"status": order.status},
            )
        customer, lines, discount = _validate_order_input(customer_id, items, discount_percent)
        order.customer = customer
        order.discount_percent = discount
        _set_items_and_totals(order, lines)
        db.session.commit()
        return order
    except Exception:
        db.session.rollback()
        raise


# ---------------------------------------------------------------------------
# Confirm and cancel
# ---------------------------------------------------------------------------

def confirm_order(order_id, user):
    """Draft -> Confirmed, taking the stock. All in one transaction:

    1. Lock the order row (SELECT ... FOR UPDATE). If it isn't a draft, stop. A double click
       waits here, then sees "confirmed" and stops, so stock is never taken twice.
    2. Lock the order's products in id order. A second user confirming an order for the same
       products waits here until we finish.
    3. If any item is short, stop with a list of shortages. Nothing has changed yet.
    4. Take the stock, write one 'sale' movement per item, mark confirmed, commit.
    """
    try:
        order = get_order_for_user(order_id, user, lock=True)
        if order.status != STATUS_DRAFT:
            raise ConflictError(
                f"Order {order.order_number} is already {order.status}.", {"status": order.status}
            )

        products = lock_products([item.product_id for item in order.items])

        shortages = []
        for item in order.items:
            product = products[item.product_id]
            if product.stock_quantity < item.quantity:
                shortages.append({
                    "product_id": product.id,
                    "code": product.code,
                    "requested": item.quantity,
                    "available": product.stock_quantity,
                })
        if shortages:
            raise ConflictError("Not enough stock to confirm this order.", {"shortages": shortages})

        for item in order.items:
            change_stock(
                products[item.product_id],
                -item.quantity,
                MOVEMENT_SALE,
                user,
                reason=f"Order {order.order_number} confirmed",
                order=order,
            )
        order.status = STATUS_CONFIRMED
        db.session.commit()
        return order
    except Exception:
        db.session.rollback()
        raise


def cancel_order(order_id, user):
    """Draft -> Cancelled (no stock change), or Confirmed -> Cancelled (stock given back).

    Same locking as confirm_order. An order that is already cancelled is refused, so stock
    can't be given back twice.
    """
    try:
        order = get_order_for_user(order_id, user, lock=True)
        if order.status == STATUS_CANCELLED:
            raise ConflictError(
                f"Order {order.order_number} is already cancelled.", {"status": order.status}
            )

        if order.status == STATUS_CONFIRMED:
            products = lock_products([item.product_id for item in order.items])
            for item in order.items:
                change_stock(
                    products[item.product_id],
                    item.quantity,
                    MOVEMENT_CANCELLATION,
                    user,
                    reason=f"Order {order.order_number} cancelled",
                    order=order,
                )

        order.status = STATUS_CANCELLED
        db.session.commit()
        return order
    except Exception:
        db.session.rollback()
        raise
