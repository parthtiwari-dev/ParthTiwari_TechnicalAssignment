"""Money and quantity rules. The only place order totals are computed.

Pages, the API, the CSV import and the tests all call these functions, so a rule like
"discount is 0 to 20" or "round half up to 2 places" is written exactly once.

Every amount is a Decimal. Floats can't hold 0.1 exactly, so they are never used for money.
"""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.errors import ValidationError

CENT = Decimal("0.01")
MAX_DISCOUNT_PERCENT = Decimal("20")
MAX_PRICE = Decimal("9999999999.99")  # the largest value DECIMAL(12,2) can hold
MAX_QUANTITY = 1_000_000  # keeps quantity x rate far inside DECIMAL(12,2) and MySQL INT

WHOLE_NUMBER = re.compile(r"-?\d+")


def _label(field):
    """"stock_quantity" -> "Stock quantity", for messages."""
    return field.replace("_", " ").capitalize()


def round_money(value):
    """Round to 2 decimal places, halves going up (2.345 -> 2.35). The one rounding rule."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_int(value, field):
    """Turn input into a whole number, or raise ValidationError.

    Accepts an int, or a string like "3" (HTML forms and CSV files send strings).
    Rejects True/False (Python treats them as 1/0), floats like 2.5, and text like "2.5" or "abc".
    """
    if isinstance(value, bool):
        raise ValidationError(f"{_label(field)} must be a whole number.", {field: "Must be a whole number."})
    if isinstance(value, int):
        return value
    if isinstance(value, str) and WHOLE_NUMBER.fullmatch(value.strip()):
        return int(value.strip())
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise ValidationError(f"{_label(field)} is required.", {field: "Required."})
    raise ValidationError(f"{_label(field)} must be a whole number.", {field: "Must be a whole number."})


def parse_quantity(value, field="quantity"):
    """An order item quantity: a whole number from 1 to MAX_QUANTITY."""
    quantity = parse_int(value, field)
    if quantity <= 0:
        raise ValidationError("Quantity must be more than zero.", {field: "Must be more than zero."})
    if quantity > MAX_QUANTITY:
        raise ValidationError(
            f"Quantity can't be more than {MAX_QUANTITY}.", {field: f"Can't be more than {MAX_QUANTITY}."}
        )
    return quantity


def parse_stock_quantity(value, field="stock_quantity"):
    """A stock level, e.g. opening stock: a whole number, zero or more."""
    quantity = parse_int(value, field)
    if quantity < 0:
        raise ValidationError("Stock can't be negative.", {field: "Can't be negative."})
    if quantity > MAX_QUANTITY:
        raise ValidationError(
            f"Stock can't be more than {MAX_QUANTITY}.", {field: f"Can't be more than {MAX_QUANTITY}."}
        )
    return quantity


def _parse_decimal(value, field):
    """Turn input into a finite Decimal with at most 2 decimal places, or raise ValidationError."""
    if isinstance(value, bool) or value is None or (isinstance(value, str) and value.strip() == ""):
        raise ValidationError(f"{_label(field)} must be a number.", {field: "Must be a number."})
    try:
        # str() first, so a float like 0.1 becomes Decimal("0.1"), not 0.1000000000000000055...
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValidationError(f"{_label(field)} must be a number.", {field: "Must be a number."})
    if not number.is_finite():
        raise ValidationError(f"{_label(field)} must be a number.", {field: "Must be a number."})
    if abs(number) > MAX_PRICE:
        # Also stops "1e999999" before quantize() below, which can't handle numbers that big.
        raise ValidationError(f"{_label(field)} is too large.", {field: "Too large."})
    if number != number.quantize(CENT, rounding=ROUND_HALF_UP):
        raise ValidationError(
            f"{_label(field)} can have at most 2 decimal places.", {field: "At most 2 decimal places."}
        )
    return number.quantize(CENT)


def parse_price(value, field="price"):
    """A product price: zero or more, at most 2 decimal places."""
    price = _parse_decimal(value, field)
    if price < 0:
        raise ValidationError("Price can't be negative.", {field: "Can't be negative."})
    return price


def parse_discount(value, field="discount_percent"):
    """A discount percentage from 0 to 20, at most 2 decimal places. Blank means no discount."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return Decimal("0.00")
    discount = _parse_decimal(value, field)
    if discount < 0 or discount > MAX_DISCOUNT_PERCENT:
        raise ValidationError(
            "Discount must be between 0 and 20 percent.", {field: "Must be between 0 and 20."}
        )
    return discount


def calculate_totals(lines, discount_percent):
    """Work out an order's money from its lines.

    lines: a list of (quantity, rate) pairs. rate must be a Decimal (it comes from the database).
    Returns a dict:
        amounts          one amount per line, same order as `lines`
        subtotal         sum of the amounts
        discount_amount  subtotal x discount / 100, rounded
        grand_total      subtotal - discount_amount

    Each amount is rounded before it is added up, so the subtotal always equals the sum of
    the amounts the user sees on screen.
    """
    discount_percent = parse_discount(discount_percent)
    amounts = []
    for quantity, rate in lines:
        quantity = parse_quantity(quantity)
        amounts.append(round_money(quantity * Decimal(rate)))
    subtotal = round_money(sum(amounts, Decimal("0")))
    discount_amount = round_money(subtotal * discount_percent / 100)
    grand_total = subtotal - discount_amount
    return {
        "amounts": amounts,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "grand_total": grand_total,
    }
