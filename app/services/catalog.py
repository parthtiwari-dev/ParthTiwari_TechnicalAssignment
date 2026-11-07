"""Searching customers and products. The pages and the API both use these, so the
search rules live in one place.

Create, edit, delete and deactivate for customers and products also belong in this module
(added by the master data work).
"""
from sqlalchemy import func, or_, select

from app.extensions import db
from app.models import Customer, Product

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def _paginate(query, page, per_page):
    """Run query for one page. Returns (rows, total). Bad page numbers fall back to safe values."""
    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or DEFAULT_PER_PAGE), 1), MAX_PER_PAGE)
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(query.limit(per_page).offset((page - 1) * per_page)).all()
    return rows, total, page, per_page


def search_products(q=None, category=None, status="active", page=1, per_page=DEFAULT_PER_PAGE):
    """Products matching q (code or name), category and status ("active", "inactive" or "all").

    Returns (products, total, page, per_page), ordered by code.
    """
    query = select(Product)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Product.code.like(like), Product.name.like(like)))
    if category:
        query = query.where(Product.category == category)
    if status == "active":
        query = query.where(Product.is_active.is_(True))
    elif status == "inactive":
        query = query.where(Product.is_active.is_(False))
    return _paginate(query.order_by(Product.code), page, per_page)


def search_customers(q=None, status="active", page=1, per_page=DEFAULT_PER_PAGE):
    """Customers matching q (name, email or mobile) and status ("active", "inactive" or "all").

    Returns (customers, total, page, per_page), ordered by name.
    """
    query = select(Customer)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(Customer.name.like(like), Customer.email.like(like), Customer.mobile.like(like))
        )
    if status == "active":
        query = query.where(Customer.is_active.is_(True))
    elif status == "inactive":
        query = query.where(Customer.is_active.is_(False))
    return _paginate(query.order_by(Customer.name), page, per_page)


def product_categories():
    """Distinct categories, for the filter dropdown."""
    return db.session.scalars(select(Product.category).distinct().order_by(Product.category)).all()
