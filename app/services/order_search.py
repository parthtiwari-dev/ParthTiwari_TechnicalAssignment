"""Listing orders for the orders page. Read-only; the order rules live in services/orders.py."""
from sqlalchemy import select

from app.models import STATUS_CANCELLED, STATUS_CONFIRMED, STATUS_DRAFT, SalesOrder
from app.services.catalog import DEFAULT_PER_PAGE, _paginate

ORDER_STATUSES = (STATUS_DRAFT, STATUS_CONFIRMED, STATUS_CANCELLED)


def search_orders(user, status=None, page=1, per_page=DEFAULT_PER_PAGE):
    """Orders the user may see, newest first. Admins see all; sales users only their own.

    status: "draft", "confirmed", "cancelled", or anything else for all.
    Returns (orders, total, page, per_page).
    """
    query = select(SalesOrder)
    if not user.is_admin:
        query = query.where(SalesOrder.created_by == user.id)
    if status in ORDER_STATUSES:
        query = query.where(SalesOrder.status == status)
    return _paginate(query.order_by(SalesOrder.id.desc()), page, per_page)
