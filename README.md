# Sales Order & Inventory Management

Technical assignment for the Fresher / Trainee Software Developer role at Savyant Systems.

A web app for a small trading company to manage customers, products, sales orders and stock.
Users keep master data up to date, create orders with several products, confirm or cancel them,
and read sales and stock reports.

> **Status: in progress.** This README describes the target design. Setup steps, sample accounts,
> API examples and known limitations are added as each part is built.

## Stack

| Area | Choice |
|---|---|
| Backend | Python 3.12+, Flask, SQLAlchemy, Flask-Migrate (Alembic), Flask-Login, Flask-WTF |
| Frontend | Server-rendered Jinja templates, plain CSS, vanilla JavaScript (`fetch`) |
| Database | MySQL 8 |
| Tests | pytest, against a real MySQL test database |
| Version control | Git |

## Design in one paragraph

All money is `Decimal` and every total is computed on the server by one pricing module. Stock
works like a bank account: `stock_movements` is the statement and `products.stock_quantity` is
the balance, and the two only change together inside one database transaction. Confirming an
order locks the order row and the product rows (`SELECT ... FOR UPDATE`) before checking stock,
so a double click or two users confirming at once can never deduct twice or push stock below zero.

The full design is in [`docs/architecture.md`](docs/architecture.md).

## Setup

_To be added._

## Running the tests

_To be added._
