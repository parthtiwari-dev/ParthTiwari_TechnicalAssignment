"""CSV product import: check every row first, then save all rows or none.

The steps:
1. read_rows():     decode the file, check the header, split it into rows
2. validate_rows(): check every row and collect every error, with its row number
3. import_products(): if there is any error, save nothing and return the errors.
                      Otherwise create every product and its opening stock movement in one
                      transaction, so either all of them are saved or none are.

Row numbers are the line numbers in the file: the header is row 1, the first product is row 2.
Blank lines are skipped but still counted, so the numbers match what a text editor shows.
"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.errors import ConflictError, ForbiddenError, ValidationError
from app.extensions import db
from app.models import MOVEMENT_OPENING, Product
from app.services.pricing import parse_price, parse_stock_quantity
from app.services.stock import change_stock

COLUMNS = ["product_code", "product_name", "category", "price", "stock_quantity", "status"]
LABELS = {
    "product_code": "Product code",
    "product_name": "Product name",
    "category": "Category",
    "price": "Price",
    "stock_quantity": "Stock quantity",
    "status": "Status",
}
# The longest text each column of the products table can hold.
MAX_LENGTHS = {"product_code": 50, "product_name": 150, "category": 100}
STATUSES = {"active": True, "inactive": False}

MAX_FILE_BYTES = 1024 * 1024  # 1 MB is thousands of products
MAX_ROWS = 5000


def read_rows(data):
    """Turn the uploaded bytes into [(row_number, {column: value}), ...].

    Raises ValidationError for problems with the file as a whole: too big, not UTF-8 text,
    not readable as CSV, a wrong header, no product rows, too many rows.
    A row with the wrong number of values is returned as (row_number, None), so it is
    reported with the other row errors.
    """
    if len(data) > MAX_FILE_BYTES:
        raise ValidationError("The file is too large. The limit is 1 MB.")
    try:
        # utf-8-sig also removes the invisible marker (BOM) Excel puts at the start of "CSV UTF-8".
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("The file isn't UTF-8 text. Save it as \"CSV UTF-8\" and try again.")

    reader = csv.reader(io.StringIO(text, newline=""))
    rows = []
    try:
        header = [cell.strip() for cell in next(reader, [])]
        check_header(header)
        for cells in reader:
            cells = [cell.strip() for cell in cells]
            if all(cell == "" for cell in cells):
                continue  # a blank line
            if len(cells) != len(COLUMNS):
                rows.append((reader.line_num, None))
            else:
                rows.append((reader.line_num, dict(zip(COLUMNS, cells))))
            if len(rows) > MAX_ROWS:
                raise ValidationError(f"The file has more than {MAX_ROWS} products. Split it into smaller files.")
    except csv.Error:
        raise ValidationError(f"The file can't be read as CSV (problem near row {reader.line_num}).")

    if not rows:
        raise ValidationError("The file has a header but no product rows.")
    return rows


def check_header(header):
    """The header must be exactly the six expected columns, in order."""
    expected = ",".join(COLUMNS)
    if not any(header):
        raise ValidationError(f"The file is empty. The first row must be the header: {expected}")
    if header == COLUMNS:
        return
    problems = []
    missing = [column for column in COLUMNS if column not in header]
    unexpected = [column for column in header if column not in COLUMNS]
    if missing:
        problems.append("missing " + ", ".join(missing))
    if unexpected:
        problems.append("unexpected " + ", ".join(column or "(blank)" for column in unexpected))
    if not problems:
        problems.append("the columns are repeated or in the wrong order")
    raise ValidationError(f"The header must be exactly: {expected} ({'; '.join(problems)}).")


def validate_rows(rows):
    """Check every row. Returns (products, errors).

    products: one dict of clean values per row (only meaningful when errors is empty)
    errors:   [{"row": 3, "column": "Price", "message": "Price can't be negative."}, ...],
              sorted by row number
    """
    products = []
    errors = []
    first_seen = {}  # lower-case code -> the clean values of the row it first appeared on

    def add_error(row_number, column, message):
        errors.append({"row": row_number, "column": LABELS.get(column, ""), "message": message})

    for row_number, values in rows:
        if values is None:
            add_error(row_number, "", f"The row must have {len(COLUMNS)} values, one per column.")
            continue

        clean = {"row": row_number}
        for column in COLUMNS:
            if values[column] == "":
                add_error(row_number, column, f"{LABELS[column]} is required.")
        for column, limit in MAX_LENGTHS.items():
            if len(values[column]) > limit:
                add_error(row_number, column, f"{LABELS[column]} can be at most {limit} characters.")
        clean["code"] = values["product_code"]
        clean["name"] = values["product_name"]
        clean["category"] = values["category"]

        if values["price"] != "":
            try:
                clean["price"] = parse_price(values["price"])
            except ValidationError as error:
                add_error(row_number, "price", error.message)

        if values["stock_quantity"] != "":
            try:
                clean["stock_quantity"] = parse_stock_quantity(values["stock_quantity"])
            except ValidationError as error:
                add_error(row_number, "stock_quantity", error.message)

        if values["status"] != "":
            if values["status"].lower() in STATUSES:
                clean["is_active"] = STATUSES[values["status"].lower()]
            else:
                add_error(row_number, "status", "Status must be Active or Inactive.")

        # Codes are compared ignoring case but not accents, as the products.code column does
        # (utf8mb4_0900_as_ci): PRD-001 and prd-001 are the same code, CAFE-1 and CAFÉ-1 are not.
        code_key = clean["code"].lower()
        if code_key:
            if code_key in first_seen:
                add_error(row_number, "product_code",
                          f"Product code {clean['code']} is repeated. It is already on row "
                          f"{first_seen[code_key]['row']}.")
            else:
                first_seen[code_key] = clean
        products.append(clean)

    # One query for all the codes, to find the ones already in the database. MySQL does the
    # comparing, with the column's own rules, so this agrees with the unique index.
    if first_seen:
        file_codes = [row["code"] for row in first_seen.values()]
        existing = db.session.scalars(select(Product.code).where(Product.code.in_(file_codes))).all()
        for existing_code in existing:
            row = first_seen.get(existing_code.lower())
            if row is None:
                # MySQL matched a code that lower() sees as different (rare, e.g. "ß" and "ss").
                # Ask MySQL which file row it was.
                row = _row_matching_code(first_seen.values(), existing_code)
            if row is not None:
                add_error(row["row"], "product_code", f"Product code {row['code']} already exists.")

    errors.sort(key=lambda error: error["row"])  # stable: keeps column order within a row
    return products, errors


def _row_matching_code(rows, existing_code):
    """The first row whose code MySQL counts as equal to existing_code, or None."""
    for row in rows:
        same = db.session.scalar(
            select(Product.id).where(Product.code == row["code"], Product.code == existing_code).limit(1)
        )
        if same is not None:
            return row
    return None


def import_products(data, user):
    """Check the file and, only if every row is valid, save every product.

    Returns (imported_count, errors). When errors is not empty, imported_count is 0 and
    nothing was saved. Problems with the whole file raise ValidationError.
    """
    if not user.is_admin:
        raise ForbiddenError("Only an admin can import products.")

    products, errors = validate_rows(read_rows(data))
    if errors:
        return 0, errors

    try:
        for values in products:
            product = Product(
                code=values["code"],
                name=values["name"],
                category=values["category"],
                price=values["price"],
                stock_quantity=0,
                is_active=values["is_active"],
            )
            db.session.add(product)
            # Opening stock goes through change_stock, so it is recorded as an 'opening' movement.
            if values["stock_quantity"] > 0:
                change_stock(product, values["stock_quantity"], MOVEMENT_OPENING, user,
                             reason="Opening stock (CSV import)")
        db.session.commit()  # one commit: all products and movements, or none
    except IntegrityError:
        # The unique key on products.code refused a code, and the rollback undoes every row
        # from this file. Usually someone added one of these codes between our check and our
        # save. Rarely, the file has two codes MySQL counts as the same but lower() doesn't.
        db.session.rollback()
        raise ConflictError("A product code in the file clashed with another code when saving, "
                            "so nothing was imported. Someone may have added it just now: "
                            "upload the file again to see which one.")
    except Exception:
        db.session.rollback()
        raise
    return len(products), []
