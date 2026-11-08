# Sales Order & Inventory Management

Technical assignment for the Fresher / Trainee Software Developer role at Savyant Systems.

A web app for a small trading company that has outgrown spreadsheets. Users keep customers and
products up to date, create sales orders with several products, confirm or cancel them, and read
sales and stock reports. Every total is calculated on the server and every stock change is
recorded.

**Contents:** [Features](#features) · [Stack](#stack) · [Setup](#setup) ·
[Sample accounts](#sample-accounts) · [Tests](#running-the-tests) · [Design](#design) ·
[Project layout](#project-layout) · [Assumptions](#assumptions) ·
[Known limitations](#known-limitations)

Other docs: [`docs/architecture.md`](docs/architecture.md) (full design) ·
[`docs/api.md`](docs/api.md) (API with real examples) · [`sql/queries.sql`](sql/queries.sql) ·
[`debugging/README.md`](debugging/README.md) · [`AI_USAGE.md`](AI_USAGE.md)

## Features

| Area | What it does |
|---|---|
| Login and roles | Login and logout. **Admin** manages everything. A **Sales User** sees active customers and products and manages only their own orders. All of this is enforced on the server. |
| Customers and products | Create, view, edit, search, filter, paginate. A record used by an order (or, for products, by a stock movement) can't be deleted, only deactivated. Product codes are unique, ignoring case. Prices and stock can't be negative. |
| Sales orders | Choose an active customer, add several active products, set a 0–20% discount. The rate is copied from the product's price and stored, so later price changes don't touch old orders. Drafts can be edited; confirmed and cancelled orders are read-only. A draft whose customer or product was deactivated since can't be confirmed until it is edited. |
| Stock | Confirm deducts stock, cancelling a confirmed order puts it back, and each change writes a stock movement. Admins can adjust stock up or down with a required reason. Stock can never go below zero, even when two users confirm at the same moment. |
| Order form (JS) | Fetches the chosen product's price and stock, adds and removes rows without reloading, shows live totals, validates input, asks before confirming or cancelling, and disables the button while a request runs. |
| REST API | `GET /api/products`, `GET /api/products/<id>`, `POST /api/orders`, `PUT /api/orders/<id>`, `GET /api/orders/<id>`, `POST /api/orders/<id>/confirm`, `POST /api/orders/<id>/cancel`. JSON errors with proper status codes. See [`docs/api.md`](docs/api.md). |
| Reports (Admin) | Customer sales summary (with date range, including customers with no sales), product sales summary, low stock below a threshold you type in, stock movement history. |
| SQL | The five standalone queries in [`sql/queries.sql`](sql/queries.sql). A test runs each one. |
| CSV import (Admin) | Checks every row first and lists all errors by row number. If any row is bad, nothing is imported. Opening stock is recorded as stock movements. Samples in [`samples/`](samples/). |
| Debugging exercise | Fixed function, explanation and tests in [`debugging/`](debugging/). |

## Stack

| Area | Choice | Tested with |
|---|---|---|
| Language | Python | 3.13.5 |
| Web | Flask, Jinja templates, Flask-Login, Flask-WTF (CSRF) | Flask 3.1.3 |
| Database | MySQL with SQLAlchemy and Flask-Migrate (Alembic) | MySQL 8.0.42 |
| Frontend | HTML, CSS, vanilla JavaScript (`fetch`) | Checked in headless Chrome |
| Tests | pytest, against a real MySQL test database | pytest 9.2.0 |

The direct dependencies are pinned to exact versions in [`requirements.txt`](requirements.txt).

## Setup

You need Python and a running MySQL 8 server. It was tested on Python 3.13.5. Python 3.11 or
newer is expected to work, but that is untested.

**1. Get the code and install the dependencies**

```bash
git clone https://github.com/parthtiwari-dev/ParthTiwari_TechnicalAssignment.git
cd ParthTiwari_TechnicalAssignment
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

**2. Create a MySQL user and the two databases**

Run this as a MySQL admin user (choose your own password):

```sql
CREATE DATABASE sales_inventory CHARACTER SET utf8mb4;
CREATE DATABASE sales_inventory_test CHARACTER SET utf8mb4;
CREATE USER 'app_user'@'localhost' IDENTIFIED BY 'choose-a-password';
GRANT ALL PRIVILEGES ON `sales_inventory%`.* TO 'app_user'@'localhost';
```

**3. Configure**

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Edit `.env`: set `SECRET_KEY` to a long random string, put your MySQL user, password, host and
port into `DATABASE_URL` and `TEST_DATABASE_URL`, and choose the sample account passwords
(`SEED_*`). `.env` is gitignored.

**4. Create the tables, load sample data, run**

```bash
flask db upgrade            # creates all tables from the migrations
python scripts/seed.py      # sample users, customers, products and orders
flask run                   # http://127.0.0.1:5000
```

`python scripts/seed.py --reset` wipes all rows and seeds again. Without `--reset` it refuses to
run on a database that already has users.

The schema is also exported to [`sql/schema.sql`](sql/schema.sql) for reading or a manual setup.
Its header says how to load it by hand. The migrations are the source of truth.

## Sample accounts

`scripts/seed.py` creates three users. Their emails and passwords come from your `.env`, so no
real credentials are stored in the repository.

| User | Role | Email (from `.env.example`) | Password |
|---|---|---|---|
| Asha Admin | Admin | `SEED_ADMIN_EMAIL` (admin@example.com) | `SEED_ADMIN_PASSWORD` |
| Ravi Sales | Sales User | `SEED_SALES_EMAIL` (sales1@example.com) | `SEED_SALES_PASSWORD` |
| Neha Sales | Sales User | `SEED_SALES2_EMAIL` (sales2@example.com) | `SEED_SALES2_PASSWORD` |

The seed also adds 8 customers (one inactive, some with no orders), 10 products in 3 categories
(one inactive, two with low stock) with opening stock movements, and 6 orders in every status.
Ravi and Neha each own orders, so you can check that one sales user can't open the other's.

## Running the tests

The tests need the MySQL test database from `TEST_DATABASE_URL`. They create the tables
themselves and empty them after each test. The test URL must contain the word `test`, as a guard
against wiping real data.

```bash
pytest -q
```

Result on the submitted code: **277 passed**.

| File | What it proves |
|---|---|
| `test_pricing.py` | The PDF example (4500 / 450 / 4050), rounding, bad quantity and discount rejected, totals too large for the database rejected |
| `test_orders_service.py` | Confirm deducts stock; one short item changes nothing; repeated confirm doesn't deduct again; cancel restores once; a deactivated customer or product blocks confirm; stored rates; ownership |
| `test_concurrency.py` | Two users confirming against the same limited stock: exactly one succeeds, stock never goes negative |
| `test_api_products.py`, `test_api_orders.py` | Every endpoint and every error status (400, 401, 403, 404, 409, 422, 500 without a traceback) |
| `test_web_master_data.py`, `test_web_orders.py`, `test_stock_adjust.py`, `test_auth.py` | Pages, permissions, safe delete, unique codes, search, stock adjustment and its limits, login and the `?next=` redirect |
| `test_query_params.py` | Huge, very long or non-ASCII numbers in the URL get a clear answer, never a 500 |
| `test_reports.py`, `test_sql_queries.py` | Report figures (a multi-item order counts once), the five SQL queries |
| `test_csv_import.py` | All-or-nothing import, row-numbered errors, duplicates in the file and in the database (including accented codes), upload size limits |
| `test_debugging.py` | The corrected `calculate_total`, including `Decimal` rates and NaN or infinity rejected |

Every test scenario the assignment lists in Part 12 is covered, and each of those tests is
marked "Part 12" in its docstring. The order scenarios are in `test_api_orders.py`, and most are
also tested at the service level in `test_orders_service.py`. The CSV one (one bad row imports
nothing) is in `test_csv_import.py`.

## Design

### Tables and how they connect

```
users ──< sales_orders >── customers
  │            │
  │            └──< sales_order_items >── products
  │                                         │
  └──────────< stock_movements >────────────┘
                     │
                     └── (optional) sales_orders
```

- A **customer** has many **sales orders**. A **user** creates many orders (`created_by`).
- An **order** has many **order items**, and each item points to one **product**. An order can't
  have the same product twice (unique `order_id, product_id`).
- A **stock movement** belongs to a product, was made by a user, and points to an order when the
  order caused it (`sale`, `cancellation`). Opening stock and manual adjustments have no order.
- Foreign keys use `ON DELETE RESTRICT`, so the database itself refuses to delete a customer or
  product that an order uses. The app checks first and shows a clear message suggesting
  deactivation instead.
- Money columns are `DECIMAL(12,2)`. The discount is `DECIMAL(5,2)`. Quantities are integers.
- CHECK constraints back up the rules in the database too: price ≥ 0, stock ≥ 0, quantity > 0,
  discount 0–20, and valid status, role and movement type values.
- Indexes cover the searches and reports: customer name, email and mobile; product code (unique),
  name and category; order status and date; movements by product and time.

### Key decisions

1. **The server calculates all money.** One module (`app/services/pricing.py`) computes every
   amount with Python `Decimal` and one rounding rule (half up to 2 decimal places). Pages, API
   and tests all use it. The browser shows a live preview, but the server ignores any rate,
   amount, total, status or owner the browser sends.
2. **Stock works like a bank account.** `stock_movements` is the statement and
   `products.stock_quantity` is the balance. One function (`change_stock`) changes stock, and it
   always writes the movement row in the same transaction. So the balance always equals the sum
   of the movements.
3. **Confirming locks the rows it depends on.** In one transaction it:
   1. locks the order (`SELECT ... FOR UPDATE`) and checks it's still a draft. A repeated
      confirm waits here, then sees "confirmed" and stops, so stock is never taken twice;
   2. locks the products sorted by id, so two users confirming at once queue up instead of both
      reading the same stock, and the fixed order prevents deadlocks;
   3. refuses, with nothing changed, if the customer or a product was deactivated after the
      draft was saved;
   4. checks every item. If any is short, nothing changes;
   5. deducts, writes the movements and sets the status, then commits.

   Cancelling works the same way in reverse. The connection uses `READ COMMITTED`, so each query
   sees the latest committed data. `test_concurrency.py` proves it: with the lock removed, the
   test oversells stock and fails.
4. **One place decides who can see an order.** `get_order_for_user()` loads every order for
   pages and API alike. Admins get any order. Sales users get their own or a 403.
5. **Routes are thin, services hold the rules.** `app/web/` (pages) and `app/api/` (JSON) read the
   request and call `app/services/`, which hold every business rule once. Each service function
   owns its transaction: it commits on success and rolls back on any error.
6. **Order numbers come from the row id** (`SO-000123`). They're unique with no extra counter and
   no race between two users.

More detail is in [`docs/architecture.md`](docs/architecture.md).

## Project layout

```
app/
  __init__.py        create_app(): config, extensions, blueprints, error handlers
  models.py          the six tables
  errors.py          error types and the JSON/HTML error handlers
  permissions.py     admin_required, get_order_for_user()
  serializers.py     order and product JSON
  services/          business rules: pricing, orders, stock, catalog, reports, csv_import
  web/               page routes
  api/               JSON routes under /api
  templates/         Jinja pages
  static/            css, js/order_form.js, js/api.js
migrations/          Alembic migrations
sql/                 schema.sql, queries.sql
samples/             products_valid.csv, products_invalid.csv
debugging/           the debugging exercise
scripts/             seed.py, api_demo.py
tests/
```

## Assumptions

- One currency and one stock location, as the assignment says. Amounts are shown without a
  currency symbol.
- The order date is the day the order is created. It isn't editable.
- Sales reports count **confirmed** orders only. The "customers who never placed any order"
  query counts orders of any status, since a draft is still an order placed.
- When a draft is edited, products already on it keep their stored rate. Newly added products
  take today's price.
- The low stock report lists **active** products with stock strictly below the threshold.
- CSV row numbers are line numbers in the file: the header is row 1.
- Product codes are compared ignoring case but not accents, everywhere: the form, the CSV import
  and the unique index (`products.code` uses MySQL's `utf8mb4_0900_as_ci`). So `PRD-1` and
  `prd-1` are the same code, while `CAFE-1` and `CAFÉ-1` are two different codes.
- A draft can be saved only with an active customer and active products. If one of them is
  deactivated later, confirming the draft is refused (409) until it is edited. Cancelling it
  still works.
- Limits, so a number can't overflow a database column: at most 1,000,000 of a product on one
  order line or as opening stock, and a stock adjustment can't raise stock above 1,000,000.
  Order amounts and totals go up to 9,999,999,999.99, the most `DECIMAL(12,2)` holds. In the
  customer, product and order lists (and the API), a page number above 100,000 is treated as
  100,000.
- A CSV upload can be at most 1 MB and 5,000 products. Any request over 2 MB is refused before
  it is read: the import page shows a message, and the API answers `413` in JSON.
- A product created with opening stock (by form or CSV) has a stock movement, so by the
  assignment's rule it can be deactivated but not deleted.
- Users are created by the seed script. There is no user management screen, since the
  assignment doesn't ask for one.

## Known limitations

- No user management UI and no password reset.
- The app runs locally. It is not deployed.
- Tested on Python 3.13.5 and MySQL 8.0.42 only.
- The tests build their tables with SQLAlchemy's `create_all()` from the models, not by running
  the migrations. The models and migrations are kept in step by hand.
- The order date is the app server's local date (`date.today()`), not the user's time zone.
- The JS order form is a convenience layer. All rules are enforced again on the server, so the
  app stays correct if the JS is bypassed, but the pages themselves need JS to create or edit
  orders.
