"""The debugging exercise: the fixed calculate_total, compared with the original buggy one."""
from decimal import Decimal

import pytest

from debugging.calculate_total import calculate_total

EXAMPLE = [{"qty": 2, "rate": 100}, {"qty": 3, "rate": 50}]


def buggy_calculate_total(items):
    """The original code from the assignment, kept here only to show what was wrong."""
    total = 0
    for item in items:
        amount = item["qty"] * item["rate"]
        total = amount
    return total


def test_example_gives_350():
    assert calculate_total(EXAMPLE) == 350


def test_buggy_version_returned_only_the_last_amount():
    assert buggy_calculate_total(EXAMPLE) == 150  # 3 x 50, the last item


def test_empty_list_returns_zero():
    assert calculate_total([]) == 0


def test_decimal_rate_and_free_item():
    assert calculate_total([{"qty": 2, "rate": 99.5}, {"qty": 1, "rate": 0}]) == 199.0


def test_decimal_rates_are_accepted_and_stay_exact():
    items = [{"qty": 2, "rate": Decimal("100.10")}, {"qty": 3, "rate": Decimal("50")}]
    total = calculate_total(items)
    assert total == Decimal("350.20")
    assert isinstance(total, Decimal)


def test_mixing_float_and_decimal_rates_raises():
    with pytest.raises(ValueError, match="Item 1: rates can't mix float and Decimal"):
        calculate_total([{"qty": 1, "rate": 10.5}, {"qty": 1, "rate": Decimal("2")}])


@pytest.mark.parametrize("item, message", [
    ({"rate": 100}, "Item 0 is missing 'qty'."),
    ({"qty": 2}, "Item 0 is missing 'rate'."),
])
def test_missing_key_raises(item, message):
    with pytest.raises(ValueError) as error:
        calculate_total([item])
    assert str(error.value) == message


def test_error_names_the_right_item():
    with pytest.raises(ValueError, match="Item 1 is missing 'rate'"):
        calculate_total([{"qty": 1, "rate": 10}, {"qty": 2}])


@pytest.mark.parametrize("qty", [0, -1, 2.5, "2", True, None])
def test_invalid_qty_raises(qty):
    with pytest.raises(ValueError, match="qty must be a whole number above zero"):
        calculate_total([{"qty": qty, "rate": 10}])


@pytest.mark.parametrize("rate", [
    -10, "100", True, None, Decimal("-1"),
    float("nan"), float("inf"), float("-inf"),
    Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"),
])
def test_invalid_rate_raises(rate):
    with pytest.raises(ValueError, match="rate must be a number, zero or more"):
        calculate_total([{"qty": 1, "rate": rate}])
