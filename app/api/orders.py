"""POST /api/orders, PUT/GET /api/orders/<id>, POST /api/orders/<id>/confirm and /cancel.

Each route reads the request, calls one function in services/orders.py and returns the
order as JSON. The services do every check (input, ownership, status, stock), so these
routes stay short. Errors they raise become JSON responses in app/errors.py.

Only customer_id, discount_percent and items [{product_id, quantity}] are read from the
body. Anything else the client sends (a rate, a total, a status) is ignored.
"""
from flask import jsonify
from flask_login import current_user

from app.api import api_bp, json_body
from app.permissions import get_order_for_user
from app.serializers import order_to_dict
from app.services import orders as order_service


@api_bp.route("/orders", methods=["POST"])
def create_order():
    data = json_body()
    order = order_service.create_draft_order(
        current_user,
        data.get("customer_id"),
        data.get("items"),
        data.get("discount_percent"),
    )
    return jsonify(order_to_dict(order)), 201


@api_bp.route("/orders/<int:order_id>", methods=["PUT"])
def update_order(order_id):
    data = json_body()
    order = order_service.update_draft_order(
        order_id,
        current_user,
        data.get("customer_id"),
        data.get("items"),
        data.get("discount_percent"),
    )
    return jsonify(order_to_dict(order))


@api_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    order = get_order_for_user(order_id, current_user)
    return jsonify(order_to_dict(order))


@api_bp.route("/orders/<int:order_id>/confirm", methods=["POST"])
def confirm_order(order_id):
    order = order_service.confirm_order(order_id, current_user)
    return jsonify(order_to_dict(order))


@api_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    order = order_service.cancel_order(order_id, current_user)
    return jsonify(order_to_dict(order))
