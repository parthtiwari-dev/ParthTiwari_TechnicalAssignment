# Architecture

This is the design the code follows. When the code changes, this file changes with it.

## Layers

```
browser ──► routes (web pages + JSON API)
               │  read the request, check login and role, call a service, render or return JSON
               ▼
            services            ← all business rules live here, once
               │  pricing, orders, stock, csv import, reports
               ▼
            models + database   ← SQLAlchemy models, MySQL
```

Pages and API endpoints are both thin. They call the same service functions, so a rule
(a discount limit, a stock check, an ownership check) is written once and enforced in both places.

## Layout

```
app/
  __init__.py          create_app(): config, extensions, blueprints, error handlers
  config.py            settings from environment variables
  extensions.py        db, migrate, login_manager, csrf
  models.py            User, Customer, Product, SalesOrder, SalesOrderItem, StockMovement
  permissions.py       admin_required, require_admin, get_order_for_user()
  errors.py            error types and the handlers that turn them into responses
  serializers.py       models -> dicts for JSON (order_to_dict, product_to_dict)
  services/
    pricing.py         money rounding and order totals (the only place totals are computed)
    orders.py          create/edit Draft, confirm, cancel
    stock.py           stock adjustment and movement records
    csv_import.py      validate then import, all or nothing
    reports.py         report queries
  web/                 page routes (auth, customers, products, orders, stock, reports)
  api/                 JSON routes under /api
  templates/           Jinja pages
  static/              css, js/order_form.js
migrations/            Alembic migrations
sql/                   schema.sql (exported) and queries.sql (the five standalone queries)
samples/               products_valid.csv, products_invalid.csv
debugging/             the corrected calculate_total and its explanation
scripts/seed.py        sample users, customers and products
tests/
```

## Data model

| Table | Key columns | Rules |
|---|---|---|
| `users` | id, name, email, password_hash, role | email unique; role is `admin` or `sales` |
| `customers` | id, name, email, mobile, city, is_active | index on name, email, mobile |
| `products` | id, code, name, category, price, stock_quantity, is_active | code unique; price ≥ 0; stock ≥ 0 (CHECK constraints) |
| `sales_orders` | id, order_number, customer_id, order_date, status, discount_percent, subtotal, discount_amount, grand_total, created_by | order_number unique; status `draft`/`confirmed`/`cancelled`; discount 0–20; index on (status, order_date) and created_by |
| `sales_order_items` | id, order_id, product_id, quantity, rate, amount | unique (order_id, product_id), so no duplicate product per order; quantity > 0 |
| `stock_movements` | id, product_id, movement_type, quantity_change, order_id, reason, created_by, created_at | type is `opening`, `adjustment`, `sale`, `cancellation`; index on (product_id, created_at) |

Money columns are `DECIMAL(12,2)`, and `discount_percent` is `DECIMAL(5,2)`. Foreign keys from
orders and items to customers and products use `ON DELETE RESTRICT`. The database itself refuses
to delete a customer or product that an order uses. The app checks first so it can show a clear
message, and offers deactivation instead.

`rate` is copied from the product's price when the item is added, so later price changes don't
alter existing orders. Editing a Draft keeps the stored rate for products already on it; only a
newly added product takes today's price.

## Money

- Every amount is a Python `Decimal`, never a float.
- One rounding rule: `quantize(Decimal("0.01"), ROUND_HALF_UP)`.
- `amount = round(qty × rate)`, `subtotal = sum(amounts)`,
  `discount = round(subtotal × percent / 100)`, `grand_total = subtotal − discount`.
- The browser shows live totals for convenience. The server ignores any totals or rates it sends
  and works them out again.

## Order lifecycle and stock

| From | Action | To | Stock |
|---|---|---|---|
| draft | edit | draft | no change |
| draft | confirm | confirmed | deduct each item's quantity |
| draft | cancel | cancelled | no change |
| confirmed | cancel | cancelled | restore each item's quantity |
| cancelled | anything | — | rejected |

**Confirm, step by step (one transaction):**

1. `SELECT ... FOR UPDATE` on the order row. If it isn't `draft`, stop and change nothing.
   A second click waits here, then sees `confirmed` and stops. That's why stock can't be taken twice.
2. `SELECT ... FOR UPDATE` on the products in the order, **sorted by id**. A second user confirming
   an order with the same products waits here until the first commits. Locking in the same order
   every time means two users can't each hold one lock and wait forever for the other's (a deadlock).
3. Check every item's quantity against the locked stock. If any item is short, roll back with an
   error that lists the short items. Nothing changes.
4. Lower each product's stock, insert one `sale` movement per item, set status to `confirmed`, commit.

**Cancel** works the same way. It locks the order, then:
- if the order is `draft`, it just sets `cancelled`;
- if it's `confirmed`, it locks the products, adds the stock back, writes `cancellation`
  movements and sets `cancelled`;
- if it's already `cancelled`, it changes nothing and reports a conflict (409).

Stock adjustments by an Admin lock the product row too, and refuse to go below zero.

The database connection uses `READ COMMITTED`, so every query sees the latest committed data.
The locks above, not MySQL's default `REPEATABLE READ` snapshot, are what keep stock correct.
`tests/test_concurrency.py` holds a product lock, starts two confirms against it, then releases
it: exactly one confirm succeeds. With the lock removed, both succeed and stock is oversold.

## Permissions

- Every page and endpoint except login needs a logged-in user.
- `admin_required` guards master data, stock adjustment, CSV import and reports.
- `get_order_for_user(order_id, user)` is the only way routes load an order. Admins get any order.
  Sales users get only their own. Anyone else gets 403. Pages and API both use it.
- Sales users only see active customers and products.

## API errors

The API always returns JSON: `{"error": "<message>", "details": {...}}`, with status codes
400/422 (bad input), 401 (not logged in), 403 (not allowed), 404 (missing), 409 (conflict, e.g.
not enough stock or the order isn't a draft). Unexpected errors return 500 with a generic
message. Tracebacks are only logged, never sent.

## Service functions and API contract

### Services

Every service function that changes data owns its transaction: it commits on success and rolls
back on any error. Routes never commit. Errors come from `app/errors.py`:

| Error | Status | When |
|---|---|---|
| `ValidationError(message, details)` | 422 | bad input; `details` maps field -> message |
| `NotFoundError(message)` | 404 | record doesn't exist |
| `ForbiddenError(message)` | 403 | logged in, but not allowed |
| `ConflictError(message, details)` | 409 | valid request that clashes with current state |

`services/orders.py`
- `create_draft_order(user, customer_id, items, discount_percent) -> SalesOrder`
- `update_draft_order(order_id, user, customer_id, items, discount_percent) -> SalesOrder` (draft only, else ConflictError)
- `confirm_order(order_id, user) -> SalesOrder` (not draft -> ConflictError; short stock -> ConflictError with `details.shortages = [{product_id, code, requested, available}]`)
- `cancel_order(order_id, user) -> SalesOrder` (already cancelled -> ConflictError)
- `items` is a list of `{"product_id": ..., "quantity": ...}`. Anything else in an item (a rate, an amount) is ignored.
- Validation `details` keys: `customer_id`, `discount_percent`, `items`, `items[0].product_id`, `items[0].quantity` (0 = the row's position in the list).
- Ownership: all four use `get_order_for_user`, so a sales user on someone else's order gets ForbiddenError.

`services/stock.py`
- `adjust_stock(product_id, quantity_change, reason, user) -> Product` (admin; non-zero whole number; reason required; never below zero)
- `change_stock(product, quantity_change, movement_type, user, reason, order=None)` changes `stock_quantity` and adds the movement row. It doesn't commit. It is the only code that changes stock. For opening stock: create the product with `stock_quantity=0`, then call `change_stock(product, qty, "opening", user, "Opening stock")` if qty > 0.
- `lock_products(product_ids) -> {id: Product}` (SELECT ... FOR UPDATE, in id order)

`services/pricing.py`
- `round_money(value)`, `calculate_totals(lines, discount_percent)` with `lines = [(quantity, rate), ...]` -> `{"amounts", "subtotal", "discount_amount", "grand_total"}`
- Input parsers, each returns a clean value or raises ValidationError: `parse_int`, `parse_quantity` (1 or more), `parse_stock_quantity` (0 or more), `parse_price` (0 or more, 2 dp), `parse_discount` (0 to 20, 2 dp, blank = 0)

`permissions.py`
- `get_order_for_user(order_id, user, lock=False)` -> order, or NotFoundError / ForbiddenError ("You do not have access to this order.")
- `admin_required` decorator for one route; `bp.before_request(require_admin)` for a whole admin-only blueprint

Login is required for every route by `require_login` in `app/__init__.py`; only `auth.login` and
`static` are open. Page forms that POST include
`<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.

### API

- All JSON. Money is a string with 2 decimal places (`"1500.00"`). Session-cookie auth (log in
  through the normal login page). POST and PUT need the header `X-CSRFToken`, read from
  `<meta name="csrf-token">` in `base.html`.
- Errors: `{"error": "<message>", "details": {...}}` with 400 malformed JSON, 401 not logged in,
  403 not allowed, 404 missing, 409 conflict, 422 validation (`details` maps field -> message).
  Unexpected errors: 500 with a generic message, no traceback.
- Read request bodies with `app.api.json_body()` (400 if the body isn't a JSON object).

| Method | Path | Body | Success |
|---|---|---|---|
| GET | `/api/products?q=&category=&page=1&per_page=20` | | 200 `{"items": [product], "page", "per_page", "total"}`, active products only |
| GET | `/api/products/<id>` | | 200 product (active only, else 404) |
| POST | `/api/orders` | order body | 201 order |
| PUT | `/api/orders/<id>` | order body | 200 order (draft only) |
| GET | `/api/orders/<id>` | | 200 order |
| POST | `/api/orders/<id>/confirm` | | 200 order, or 409 with `details.shortages` |
| POST | `/api/orders/<id>/cancel` | | 200 order |

Order body: `{"customer_id": 1, "discount_percent": "10", "items": [{"product_id": 1, "quantity": 2}]}`

Product: `{"id", "code", "name", "category", "price", "stock_quantity"}` (`serializers.product_to_dict`)

Order (`serializers.order_to_dict`):

```json
{"id": 7, "order_number": "SO-000007", "customer": {"id": 1, "name": "Sharma Traders"},
 "order_date": "2026-11-07", "status": "draft", "discount_percent": "10.00",
 "subtotal": "4500.00", "discount_amount": "450.00", "grand_total": "4050.00",
 "created_by": {"id": 2, "name": "Ravi Sales"},
 "items": [{"id": 1, "product": {"id": 1, "code": "ACC-001", "name": "Keyboard"},
            "quantity": 2, "rate": "1500.00", "amount": "3000.00"}]}
```
