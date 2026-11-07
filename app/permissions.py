"""Who may do what. Pages and the API both use these, so the rules exist once.

Login itself is required for every route by the check in app/__init__.py (require_login).
"""
from functools import wraps

from flask_login import current_user
from sqlalchemy import select

from app.errors import ForbiddenError, NotFoundError
from app.extensions import db, login_manager
from app.models import SalesOrder


def admin_required(view):
    """Allow the view only for admins. Others get 403 (JSON under /api, an error page otherwise)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            # require_login normally catches this first; this keeps the decorator safe on its own.
            return login_manager.unauthorized()
        if not current_user.is_admin:
            raise ForbiddenError("Only an admin can do this.")
        return view(*args, **kwargs)

    return wrapped


def require_admin():
    """For a whole admin-only blueprint: `bp.before_request(require_admin)`.

    Runs before every route in that blueprint, so no route in it can be left unguarded.
    """
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if not current_user.is_admin:
        raise ForbiddenError("Only an admin can do this.")
    return None


def check_order_access(order, user):
    """Admins can see every order. Sales users only the orders they created."""
    if user.is_admin or order.created_by == user.id:
        return
    raise ForbiddenError("You do not have access to this order.")


def get_order_for_user(order_id, user, lock=False):
    """The only way routes and services load an order.

    Raises NotFoundError if it doesn't exist, ForbiddenError if the user may not see it.
    lock=True runs SELECT ... FOR UPDATE, so no other request can change this order until
    the current transaction ends. populate_existing makes SQLAlchemy use the fresh row from
    the database instead of a copy it may already hold in memory.
    """
    query = select(SalesOrder).where(SalesOrder.id == order_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    order = db.session.execute(query).scalar_one_or_none()
    if order is None:
        raise NotFoundError("Order not found.")
    check_order_access(order, user)
    if lock:
        # Forget any item rows loaded earlier in this request; read them again under the lock.
        db.session.expire(order, ["items"])
    return order
