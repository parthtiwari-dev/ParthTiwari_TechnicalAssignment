# Debugging exercise: `calculate_total`

The fixed function is in [`calculate_total.py`](calculate_total.py). The tests are in
[`tests/test_debugging.py`](../tests/test_debugging.py).

## The cause

```python
total = amount      # before: replaces the total with this item's amount
total += amount     # after: adds this item's amount to the total
```

Inside the loop, `total = amount` threw away the running total on every item. So the function
returned only the **last** item's amount. For the example, the items are 2 × 100 = 200 and
3 × 50 = 150. The old code returned 150. The fixed code returns 200 + 150 = 350.

## Empty list

`calculate_total([])` returns `0`. The loop never runs, so the starting total is returned.
No items means nothing to pay, so 0 is the right answer, not an error.

## Missing qty or rate

It raises `ValueError`, naming the item and the key, e.g. `Item 1 is missing 'rate'.`

Why raise instead of treating a missing value as 0: a missing rate usually means bad data
upstream. Using 0 would quietly under-charge, and the total would look normal, so nobody would
notice. An error stops the wrong number at once and says exactly which item to fix.

## Invalid qty or rate

- `qty` must be a whole number above zero. `0`, `-1`, `2.5`, `"2"` and `True` are rejected.
- `rate` must be a number, zero or more. `-10`, `"100"` and `None` are rejected. `0` is allowed
  (a free item). Decimals like `99.5` are allowed.
- `True` and `False` are rejected for both. Python treats them as 1 and 0, so without this
  check `{"qty": True}` would count as a quantity of 1.

Each case raises `ValueError` with the item's position and the bad value.
