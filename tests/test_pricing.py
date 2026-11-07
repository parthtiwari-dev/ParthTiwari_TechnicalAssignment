"""Money rules in services/pricing.py. These need no database."""
from decimal import Decimal

import pytest

from app.errors import ValidationError
from app.services.pricing import (
    calculate_totals,
    parse_discount,
    parse_price,
    parse_quantity,
    round_money,
)


def test_example_from_the_assignment():
    # Keyboard 2 x 1500 + Mouse 3 x 500, 10% discount.
    totals = calculate_totals([(2, Decimal("1500.00")), (3, Decimal("500.00"))], "10")

    assert totals["amounts"] == [Decimal("3000.00"), Decimal("1500.00")]
    assert totals["subtotal"] == Decimal("4500.00")
    assert totals["discount_amount"] == Decimal("450.00")
    assert totals["grand_total"] == Decimal("4050.00")


def test_no_discount():
    totals = calculate_totals([(1, Decimal("99.99"))], "0")
    assert totals["discount_amount"] == Decimal("0.00")
    assert totals["grand_total"] == Decimal("99.99")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2.345", "2.35"),   # half goes up
        ("2.344", "2.34"),
        ("0.005", "0.01"),
        ("10", "10.00"),
    ],
)
def test_round_money_half_up(value, expected):
    assert round_money(Decimal(value)) == Decimal(expected)


def test_discount_is_rounded_half_up():
    # 33.33 x 15% = 4.9995 -> 5.00
    totals = calculate_totals([(1, Decimal("33.33"))], "15")
    assert totals["discount_amount"] == Decimal("5.00")
    assert totals["grand_total"] == Decimal("28.33")


def test_grand_total_equals_subtotal_minus_discount():
    totals = calculate_totals([(3, Decimal("19.99")), (7, Decimal("0.35"))], "12.5")
    assert totals["subtotal"] == Decimal("62.42")
    assert totals["discount_amount"] == Decimal("7.80")  # 7.8025 -> 7.80
    assert totals["grand_total"] == totals["subtotal"] - totals["discount_amount"]


@pytest.mark.parametrize("quantity", [0, -1, "0", "-5"])
def test_zero_or_negative_quantity_rejected(quantity):
    with pytest.raises(ValidationError):
        calculate_totals([(quantity, Decimal("10.00"))], "0")


@pytest.mark.parametrize("quantity", [2.5, "2.5", "abc", "", None, True])
def test_non_whole_quantity_rejected(quantity):
    with pytest.raises(ValidationError):
        parse_quantity(quantity)


def test_quantity_accepts_whole_number_string():
    assert parse_quantity("3") == 3


@pytest.mark.parametrize("discount", ["-0.01", "-5", "20.01", "21", "100"])
def test_discount_outside_0_to_20_rejected(discount):
    with pytest.raises(ValidationError) as error:
        calculate_totals([(1, Decimal("10.00"))], discount)
    assert "discount_percent" in error.value.details


@pytest.mark.parametrize("discount, expected", [("0", "0.00"), ("20", "20.00"), ("7.5", "7.50"), ("", "0.00"), (None, "0.00")])
def test_discount_accepted(discount, expected):
    assert parse_discount(discount) == Decimal(expected)


@pytest.mark.parametrize("discount", ["abc", "10.555", "NaN", True])
def test_bad_discount_rejected(discount):
    with pytest.raises(ValidationError):
        parse_discount(discount)


@pytest.mark.parametrize("price", ["-1", "abc", "1.999", "", "1e999999"])
def test_bad_price_rejected(price):
    with pytest.raises(ValidationError):
        parse_price(price)


def test_price_parsed_to_two_places():
    assert parse_price("1500") == Decimal("1500.00")


def test_line_amount_too_large_for_the_database_rejected():
    # 1,000,000 x 100,000.00 = 100,000,000,000.00, more than DECIMAL(12,2) can hold.
    with pytest.raises(ValidationError) as error:
        calculate_totals([(1, Decimal("10.00")), (1_000_000, Decimal("100000.00"))], "0")
    assert list(error.value.details) == ["items[1].quantity"]


def test_subtotal_too_large_for_the_database_rejected():
    # Each line fits, but together they don't.
    with pytest.raises(ValidationError) as error:
        calculate_totals([(1, Decimal("6000000000.00")), (1, Decimal("6000000000.00"))], "0")
    assert list(error.value.details) == ["items"]


def test_largest_total_that_fits_is_accepted():
    totals = calculate_totals([(1, Decimal("9999999999.99"))], "0")
    assert totals["grand_total"] == Decimal("9999999999.99")
