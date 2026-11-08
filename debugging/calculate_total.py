"""The debugging exercise: the corrected calculate_total. See README.md in this folder."""
import math
from decimal import Decimal


def _is_finite(number):
    """False for NaN ("not a number") and infinity, which would make the total meaningless."""
    if isinstance(number, Decimal):
        return number.is_finite()
    return math.isfinite(number)


def calculate_total(items):
    """Return the sum of qty x rate over all items. An empty list returns 0.

    Each item is a dict with:
        qty   a whole number above zero (an int, not True/False)
        rate  a finite number, zero or more: an int, float or Decimal (not True/False,
              NaN or infinity)

    A missing or invalid qty or rate raises ValueError naming the item, instead of
    quietly giving a wrong total.
    """
    total = 0
    for index, item in enumerate(items):
        for key in ("qty", "rate"):
            if key not in item:
                raise ValueError(f"Item {index} is missing '{key}'.")

        qty = item["qty"]
        rate = item["rate"]

        # bool is checked first because Python treats True as 1 and False as 0.
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise ValueError(f"Item {index}: qty must be a whole number above zero, got {qty!r}.")
        # The finite check comes before "rate < 0": comparing a Decimal NaN raises an error.
        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float, Decimal))
            or not _is_finite(rate)
            or rate < 0
        ):
            raise ValueError(f"Item {index}: rate must be a number, zero or more, got {rate!r}.")

        amount = qty * rate
        try:
            total += amount  # the fix: add to the running total (the bug was `total = amount`)
        except TypeError:
            # Python refuses to add a float to a Decimal, so a list can't mix the two.
            raise ValueError(f"Item {index}: rates can't mix float and Decimal, got {rate!r}.")
    return total
