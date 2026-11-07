"""Numbers typed into the URL: huge, very long, or not ASCII digits. None may give a 500."""
import pytest

from app.errors import ValidationError
from app.services.pricing import parse_int

HUGE = "99999999999999999999999"
VERY_LONG = "9" * 5000  # Python's int() refuses more than 4300 digits
FULLWIDTH = "１２"         # digits from another script; \d would match these


@pytest.mark.parametrize("value", [HUGE, VERY_LONG, 10 ** 30, -(10 ** 30)])
def test_parse_int_rejects_huge_numbers(value):
    with pytest.raises(ValidationError) as error:
        parse_int(value, "page")
    assert error.value.details == {"page": "Too large."}


def test_parse_int_rejects_non_ascii_digits():
    with pytest.raises(ValidationError) as error:
        parse_int(FULLWIDTH, "page")
    assert error.value.details == {"page": "Must be a whole number."}


def test_parse_int_accepts_18_digits():
    assert parse_int("999999999999999999", "page") == 999_999_999_999_999_999


@pytest.mark.parametrize("value", [HUGE, VERY_LONG, FULLWIDTH])
@pytest.mark.parametrize("param", ["page", "per_page"])
def test_api_products_rejects_bad_numbers_with_422(client, login, sales_user, param, value):
    login(client, sales_user)
    response = client.get("/api/products", query_string={param: value})
    assert response.status_code == 422
    assert param in response.get_json()["details"]


def test_api_products_moves_page_and_per_page_into_range(client, login, sales_user, make_product):
    make_product()
    login(client, sales_user)

    data = client.get("/api/products?page=99999999999&per_page=0").get_json()
    assert data["page"] == 100000
    assert data["per_page"] == 1
    assert data["items"] == []

    data = client.get("/api/products?page=0&per_page=500").get_json()
    assert data["page"] == 1
    assert data["per_page"] == 100
    assert len(data["items"]) == 1


@pytest.mark.parametrize("value", [HUGE, VERY_LONG, FULLWIDTH])
@pytest.mark.parametrize("url", [
    "/products/?page={}",
    "/customers/?page={}",
    "/orders/?page={}",
    "/reports/stock-movements?page={}",
    "/reports/stock-movements?product_id={}",
])
def test_pages_never_500_on_odd_numbers(client, login, admin_user, url, value):
    login(client, admin_user)
    response = client.get(url.format(value))
    assert response.status_code == 200


@pytest.mark.parametrize("value", [HUGE, VERY_LONG, FULLWIDTH])
def test_low_stock_threshold_odd_numbers_show_a_message(client, login, admin_user, value):
    login(client, admin_user)
    response = client.get("/reports/low-stock", query_string={"threshold": value})
    assert response.status_code == 200
    assert b"Threshold" in response.data


@pytest.mark.parametrize("value", [HUGE, VERY_LONG])
def test_huge_ids_in_the_path_never_500(client, login, admin_user, value):
    login(client, admin_user)
    for url in ("/orders/", "/products/", "/customers/", "/api/orders/", "/api/products/"):
        # 404 (no such record), or 405 when Flask can't even read the id as a number.
        assert client.get(url + value).status_code in (404, 405)
