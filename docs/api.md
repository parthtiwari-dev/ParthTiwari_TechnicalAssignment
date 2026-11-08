# REST API

JSON endpoints under `/api`. They call the same service functions as the web pages, so the
validation, stock and permission rules are the same.

Every example below is a real response from the app, captured with the seed data
(`scripts/seed.py`) logged in as the sample sales user Ravi. Ids depend on your database.

## The basics

- **Login is required** for every endpoint. Not logged in gives `401`.
- **Auth is the normal session cookie.** Log in through the login form, then send the cookie.
- **POST and PUT need a CSRF token** in the `X-CSRFToken` header. Read it from
  `<meta name="csrf-token" content="...">` on any page. Without it you get `400`.
- **Money is a string with 2 decimal places** (`"1500.00"`), so no cents are lost to floats.
- **The server works out every rate and total.** If the client sends `rate`, `amount`,
  `subtotal`, `grand_total`, `status` or `created_by`, they are ignored.

### Trying it by hand

1. `GET /login`, read the hidden `csrf_token` field.
2. `POST /login` with `email`, `password` and `csrf_token` as a form. Keep the session cookie.
3. Send the cookie with every API call. For POST and PUT, also send `X-CSRFToken` (from the
   meta tag on any page, e.g. `/orders/`) and `Content-Type: application/json`.

`scripts/api_demo.py` does exactly this with the Python standard library. Start the app, then:

```
python scripts/api_demo.py http://127.0.0.1:5000 <active customer id>
```

It lists products, creates a Draft order, reads it and cancels it (no stock change).
In a logged-in browser tab you can also call the API from the dev tools console with `fetch()`.

### Errors

Every error has the same shape: `{"error": "<message>", "details": {...}}`.

| Status | When | `details` |
|---|---|---|
| 400 | body isn't a JSON object, or CSRF token missing | `{}` |
| 401 | not logged in | `{}` |
| 403 | a sales user opening another user's order | `{}` |
| 404 | the order or product doesn't exist (or the product is inactive) | `{}` |
| 409 | order isn't in the right status, not enough stock, or its customer or a product was deactivated after the draft was saved | `status`, `shortages`, or `customer_id` / `inactive_products` |
| 413 | the request body is over 2 MB | `{}` |
| 422 | invalid input | one message per field |
| 500 | an unexpected error | `{}`, and never a traceback |

These are the same for every endpoint:

```
401  {"details": {}, "error": "Please log in first."}
400  {"details": {}, "error": "The request body must be a JSON object."}
400  {"details": {}, "error": "The CSRF token is missing."}
500  {"details": {}, "error": "Something went wrong on our side. Please try again."}
```

## Products

### `GET /api/products`

Active products only, sorted by code. Query parameters, all optional:

| Param | Meaning |
|---|---|
| `q` | text in the code or name |
| `category` | exact category |
| `page` | page number, from 1 (default 1; below 1 is treated as 1, above 100000 as 100000) |
| `per_page` | 1 to 100 (default 20; below 1 is treated as 1, above 100 as 100) |

`page` and `per_page` must be whole numbers written with the digits 0–9, at most 18
characters. Anything else gives `422`. The response says which `page` and `per_page` were used.

`GET /api/products?page=1&per_page=3` → `200`

```json
{
  "items": [
    {"category": "Accessories", "code": "ACC-001", "id": 1, "name": "Keyboard", "price": "1500.00", "stock_quantity": 38},
    {"category": "Accessories", "code": "ACC-002", "id": 2, "name": "Mouse", "price": "500.00", "stock_quantity": 57},
    {"category": "Accessories", "code": "ACC-003", "id": 3, "name": "USB-C Hub", "price": "1899.00", "stock_quantity": 3}
  ],
  "page": 1,
  "per_page": 3,
  "total": 9
}
```

`GET /api/products?q=monitor&category=Monitors` → `200`, 3 items (`MON-001`, `MON-002`,
`MON-003`), `"total": 3`.

`GET /api/products?page=abc` → `422`

```json
{"details": {"page": "Must be a whole number."}, "error": "Page and per_page must be whole numbers."}
```

### `GET /api/products/<id>`

`GET /api/products/1` → `200`

```json
{"category": "Accessories", "code": "ACC-001", "id": 1, "name": "Keyboard", "price": "1500.00", "stock_quantity": 38}
```

`GET /api/products/10` (an inactive product) → `404`

```json
{"details": {}, "error": "Product not found."}
```

## Orders

Order body for create and edit. Only these three fields are read:

```json
{"customer_id": 1, "discount_percent": "10", "items": [{"product_id": 1, "quantity": 2}, {"product_id": 2, "quantity": 3}]}
```

`discount_percent` is 0 to 20 (blank or missing means 0). Each `quantity` is a whole number,
1 or more. The same product can't appear twice. The customer and products must be active.

A sales user can only see and change their own orders. An admin can see and change any order.

### `POST /api/orders` — create a Draft

The body above → `201`. This is the assignment's example: 2 × 1500 + 3 × 500 = 4500, 10% off
= 450, total 4050.

```json
{
  "created_by": {"id": 2, "name": "Ravi Sales"},
  "customer": {"id": 1, "name": "Sharma Traders"},
  "discount_amount": "450.00",
  "discount_percent": "10.00",
  "grand_total": "4050.00",
  "id": 7,
  "items": [
    {"amount": "3000.00", "id": 13, "product": {"code": "ACC-001", "id": 1, "name": "Keyboard"}, "quantity": 2, "rate": "1500.00"},
    {"amount": "1500.00", "id": 14, "product": {"code": "ACC-002", "id": 2, "name": "Mouse"}, "quantity": 3, "rate": "500.00"}
  ],
  "order_date": "2026-11-07",
  "order_number": "SO-000007",
  "status": "draft",
  "subtotal": "4500.00"
}
```

Every endpoint below returns an order in this same shape.

Bad input → `422`. All problems are reported at once. Item fields are keyed by position
(`items[0]` is the first item):

```
POST /api/orders
{"customer_id": 1, "discount_percent": "25", "items": [{"product_id": 1, "quantity": 0}]}
```

```json
{
  "details": {"discount_percent": "Must be between 0 and 20.", "items[0].quantity": "Must be more than zero."},
  "error": "Please fix the problems in this order."
}
```

Other `details` keys you can get: `customer_id`, `items` (`"Add at least one item."`) and
`items[0].product_id`.

Numbers too big for the database are refused the same way. A quantity above 1,000,000 gives
`"items[0].quantity": "Can't be more than 1000000."`. A line amount over 9,999,999,999.99 (the most
`DECIMAL(12,2)` holds) gives `"items[0].quantity": "Amount too large (at most 9,999,999,999.99)."`,
and an order total over it gives `"items": "Order total too large (at most 9,999,999,999.99)."`.

### `GET /api/orders/<id>`

`GET /api/orders/7` → `200`, the order.

| Case | Status | Body |
|---|---|---|
| another sales user's order | 403 | `{"details": {}, "error": "You do not have access to this order."}` |
| no such order | 404 | `{"details": {}, "error": "Order not found."}` |

### `PUT /api/orders/<id>` — edit a Draft

Same body as create. Replaces the customer, discount and items, and works out the totals again.
A product already on the order keeps the rate it was added at.

```
PUT /api/orders/7
{"customer_id": 1, "discount_percent": "5", "items": [{"product_id": 1, "quantity": 1}]}
```

→ `200`, the order with `"subtotal": "1500.00"`, `"discount_amount": "75.00"`,
`"grand_total": "1425.00"`, `"status": "draft"`.

Errors: `422` for bad input (as above), `403`, `404`, and `409` if the order isn't a Draft:

```json
{"details": {"status": "confirmed"}, "error": "Order SO-000007 is confirmed and can't be edited."}
```

### `POST /api/orders/<id>/confirm` — confirm and take the stock

No body. `POST /api/orders/7/confirm` → `200`, the order with `"status": "confirmed"`. Each
item's quantity is taken from stock, in one transaction.

If any item is short, nothing changes (no stock, no status) → `409`:

```json
{
  "details": {"shortages": [{"available": 3, "code": "ACC-003", "product_id": 3, "requested": 10}]},
  "error": "Not enough stock to confirm this order."
}
```

If the customer or a product on the order was deactivated after the draft was saved, nothing
changes → `409`. Edit the draft to replace them, then confirm:

```json
{
  "details": {"inactive_products": ["ACC-003"]},
  "error": "Order SO-000007 can't be confirmed: these products are inactive: ACC-003. Edit the draft first."
}
```

For an inactive customer, `details` has `"customer_id": "This customer is inactive."` and the
message says `customer <name> is inactive`.

Confirming again (or confirming a cancelled order) takes nothing → `409`:

```json
{"details": {"status": "confirmed"}, "error": "Order SO-000007 is already confirmed."}
```

Also `403` and `404` as above.

### `POST /api/orders/<id>/cancel` — cancel

No body. `POST /api/orders/7/cancel` → `200`, the order with `"status": "cancelled"`.
A confirmed order gets its stock back. A Draft had taken no stock, so none changes.

Cancelling again gives nothing back twice → `409`:

```json
{"details": {"status": "cancelled"}, "error": "Order SO-000007 is already cancelled."}
```

Also `403` and `404` as above.
