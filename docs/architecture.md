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

## Planned layout

```
app/
  __init__.py          create_app(): config, extensions, blueprints, error handlers
  config.py            settings from environment variables
  extensions.py        db, migrate, login_manager, csrf
  models.py            User, Customer, Product, SalesOrder, SalesOrderItem, StockMovement
  permissions.py       admin_required, get_order_for_user()
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
alter existing orders.

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
- if it's already `cancelled`, it changes nothing.

Stock adjustments by an Admin lock the product row too, and refuse to go below zero.

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
