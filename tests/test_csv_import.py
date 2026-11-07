"""CSV product import: all rows or none, every error with its row number, admin only."""
import io
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.errors import ForbiddenError, ValidationError
from app.extensions import db
from app.models import MOVEMENT_OPENING, Product, StockMovement
from app.services.csv_import import MAX_FILE_BYTES, import_products

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
HEADER = "product_code,product_name,category,price,stock_quantity,status\n"


def csv_bytes(*rows, header=HEADER):
    return (header + "\n".join(rows) + "\n").encode("utf-8")


def product_count():
    return db.session.scalar(select(func.count(Product.id)))


def movement_count():
    return db.session.scalar(select(func.count(StockMovement.id)))


def messages(errors):
    return [(error["row"], error["message"]) for error in errors]


def test_valid_file_imports_every_product_with_opening_stock(admin_user):
    data = csv_bytes(
        "PRD-001,Keyboard,Accessories,1500,20,Active",
        "PRD-002, Mouse ,Accessories,500.50,0,inactive",  # spaces trimmed, status any case
    )

    imported, errors = import_products(data, admin_user)

    assert (imported, errors) == (2, [])
    keyboard = db.session.scalar(select(Product).where(Product.code == "PRD-001"))
    mouse = db.session.scalar(select(Product).where(Product.code == "PRD-002"))
    assert (keyboard.price, keyboard.stock_quantity, keyboard.is_active) == (Decimal("1500.00"), 20, True)
    assert (mouse.name, mouse.price, mouse.stock_quantity, mouse.is_active) == ("Mouse", Decimal("500.50"), 0, False)
    opening = db.session.scalars(select(StockMovement).where(StockMovement.product_id == keyboard.id)).all()
    assert [(m.movement_type, m.quantity_change, m.created_by) for m in opening] == [
        (MOVEMENT_OPENING, 20, admin_user.id)
    ]
    assert movement_count() == 1  # zero opening stock writes no movement


def test_one_bad_row_imports_nothing(admin_user):
    data = csv_bytes(
        "PRD-001,Keyboard,Accessories,1500,20,Active",
        "PRD-002,Mouse,Accessories,-5,50,Active",
        "PRD-003,Hub,Accessories,999,5,Active",
    )

    imported, errors = import_products(data, admin_user)

    assert imported == 0
    assert messages(errors) == [(3, "Price can't be negative.")]
    assert product_count() == 0
    assert movement_count() == 0


def test_every_error_is_reported_with_its_row_number(admin_user):
    data = csv_bytes(
        "PRD-001,,,,,",                                # row 2: everything but the code missing
        "PRD-002,Mouse,Accessories,abc,1.5,Maybe",     # row 3: three problems
        ",,,,,",                                       # row 4: blank, skipped but counted
        "PRD-005,Lamp,Accessories,10.999,-1,Active",   # row 5
        "PRD-006,Too,Few",                             # row 6
    )

    imported, errors = import_products(data, admin_user)

    assert imported == 0
    assert messages(errors) == [
        (2, "Product name is required."),
        (2, "Category is required."),
        (2, "Price is required."),
        (2, "Stock quantity is required."),
        (2, "Status is required."),
        (3, "Price must be a number."),
        (3, "Stock quantity must be a whole number."),
        (3, "Status must be Active or Inactive."),
        (5, "Price can have at most 2 decimal places."),
        (5, "Stock can't be negative."),
        (6, "The row must have 6 values, one per column."),
    ]


def test_duplicate_code_in_file_is_rejected_ignoring_case(admin_user):
    data = csv_bytes(
        "PRD-001,Keyboard,Accessories,1500,20,Active",
        "prd-001,Keyboard again,Accessories,1500,20,Active",
    )

    imported, errors = import_products(data, admin_user)

    assert imported == 0
    assert messages(errors) == [(3, "Product code prd-001 is repeated. It is already on row 2.")]
    assert product_count() == 0


def test_code_already_in_database_is_rejected_ignoring_case(admin_user, make_product):
    make_product(code="ACC-001")
    data = csv_bytes(
        "PRD-001,Keyboard,Accessories,1500,20,Active",
        "acc-001,Keyboard,Accessories,1500,20,Active",
    )

    imported, errors = import_products(data, admin_user)

    assert imported == 0
    assert messages(errors) == [(3, "Product code acc-001 already exists.")]
    assert product_count() == 1  # only the one made above


@pytest.mark.parametrize("header, message", [
    ("product_code,product_name,category,price,status\n", "missing stock_quantity"),
    ("product_code,product_name,category,price,stock_quantity,status,cost\n", "unexpected cost"),
    ("product_name,product_code,category,price,stock_quantity,status\n", "wrong order"),
])
def test_bad_header_is_rejected(admin_user, header, message):
    with pytest.raises(ValidationError) as error:
        import_products(csv_bytes("PRD-001,Keyboard,Accessories,1500,20,Active", header=header), admin_user)
    assert "The header must be exactly: product_code,product_name,category,price,stock_quantity,status" in error.value.message
    assert message in error.value.message


@pytest.mark.parametrize("data, message", [
    (b"", "The file is empty."),
    (HEADER.encode(), "no product rows"),
    ("product_code,product_name\n\xe9".encode("latin-1"), "isn't UTF-8 text"),
    (b"x" * (MAX_FILE_BYTES + 1), "too large"),
])
def test_unusable_files_are_rejected(admin_user, data, message):
    with pytest.raises(ValidationError, match=message):
        import_products(data, admin_user)


def test_excel_byte_order_mark_is_accepted(admin_user):
    data = "﻿".encode("utf-8") + csv_bytes("PRD-001,Keyboard,Accessories,1500,20,Active")
    assert import_products(data, admin_user) == (1, [])


def test_sales_user_cannot_import(sales_user):
    with pytest.raises(ForbiddenError):
        import_products(csv_bytes("PRD-001,Keyboard,Accessories,1500,20,Active"), sales_user)


# ---------- the sample files ----------

def test_valid_sample_imports_all_rows(admin_user):
    imported, errors = import_products((SAMPLES / "products_valid.csv").read_bytes(), admin_user)
    assert errors == []
    assert imported == 6
    assert product_count() == 6


def test_invalid_sample_imports_nothing_and_lists_each_problem(admin_user, make_product):
    make_product(code="ACC-001")  # in the seed data; the sample clashes with it on purpose
    imported, errors = import_products((SAMPLES / "products_invalid.csv").read_bytes(), admin_user)

    assert imported == 0
    assert messages(errors) == [
        (3, "Price can't be negative."),
        (4, "Stock quantity must be a whole number."),
        (5, "Status must be Active or Inactive."),
        (6, "Product code PRD-101 is repeated. It is already on row 2."),
        (7, "Product name is required."),
        (8, "Product code ACC-001 already exists."),
    ]
    assert product_count() == 1


# ---------- the page ----------

def upload(client, data, filename="products.csv"):
    return client.post("/import/", data={"file": (io.BytesIO(data), filename)},
                       content_type="multipart/form-data")


def test_sales_user_gets_403_on_the_import_page(client, login, sales_user):
    login(client, sales_user)
    assert client.get("/import/").status_code == 403
    response = upload(client, csv_bytes("PRD-001,Keyboard,Accessories,1500,20,Active"))
    assert response.status_code == 403
    assert product_count() == 0


def test_page_imports_a_valid_file(client, login, admin_user):
    login(client, admin_user)
    response = upload(client, csv_bytes("PRD-001,Keyboard,Accessories,1500,20,Active"))
    assert response.status_code == 302
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Imported 1 products from products.csv" in page
    assert product_count() == 1


def test_page_shows_row_errors(client, login, admin_user):
    login(client, admin_user)
    response = upload(client, csv_bytes("PRD-001,Keyboard,Accessories,-1,20,Active"))
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Nothing was imported." in page
    assert "Price can&#39;t be negative." in page
    assert "the header is row 1" in page


@pytest.mark.parametrize("filename, data, message", [
    ("products.xlsx", b"anything", "Only .csv files can be imported."),
    ("products.csv", b"\xff\xfe\x00bad", "isn&#39;t UTF-8 text"),
])
def test_page_rejects_wrong_files(client, login, admin_user, filename, data, message):
    login(client, admin_user)
    assert message in upload(client, data, filename).get_data(as_text=True)


def test_page_needs_a_file(client, login, admin_user):
    login(client, admin_user)
    response = client.post("/import/", data={}, content_type="multipart/form-data")
    assert "Choose a CSV file to upload." in response.get_data(as_text=True)
