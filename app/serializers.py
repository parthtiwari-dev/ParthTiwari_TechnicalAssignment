"""Turn models into plain dicts for JSON. The API and any page that needs JSON share these.

Money goes out as a string with 2 decimal places ("1500.00"). A JSON number would be read
as a float by JavaScript and could lose cents.
"""
from app.services.pricing import round_money


def money(value):
    return str(round_money(value))


def product_to_dict(product):
    return {
        "id": product.id,
        "code": product.code,
        "name": product.name,
        "category": product.category,
        "price": money(product.price),
        "stock_quantity": product.stock_quantity,
    }


def order_to_dict(order):
    return {
        "id": order.id,
        "order_number": order.order_number,
        "customer": {"id": order.customer.id, "name": order.customer.name},
        "order_date": order.order_date.isoformat(),
        "status": order.status,
        "discount_percent": money(order.discount_percent),
        "subtotal": money(order.subtotal),
        "discount_amount": money(order.discount_amount),
        "grand_total": money(order.grand_total),
        "created_by": {"id": order.creator.id, "name": order.creator.name},
        "items": [
            {
                "id": item.id,
                "product": {
                    "id": item.product.id,
                    "code": item.product.code,
                    "name": item.product.name,
                },
                "quantity": item.quantity,
                "rate": money(item.rate),
                "amount": money(item.amount),
            }
            for item in order.items
        ],
    }
