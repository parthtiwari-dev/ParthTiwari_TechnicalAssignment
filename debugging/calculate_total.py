"""The debugging exercise: the corrected calculate_total. See README.md in this folder."""


def calculate_total(items):
    """Return the sum of qty x rate over all items. An empty list returns 0.

    Each item is a dict with:
        qty   a whole number above zero (not True/False)
        rate  a number, zero or more (not True/False)

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
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate < 0:
            raise ValueError(f"Item {index}: rate must be a number, zero or more, got {rate!r}.")

        amount = qty * rate
        total += amount  # the fix: add to the running total (the bug was `total = amount`)
    return total
