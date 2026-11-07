"""Login, logout, and the login requirement on pages and the API."""
import pytest

from tests.conftest import PASSWORD


def test_login_with_correct_password(client, sales_user):
    response = client.post("/login", data={"email": sales_user.email, "password": PASSWORD})
    assert response.status_code == 302

    page = client.get("/orders/")
    assert page.status_code == 200
    assert b"Sales One" in page.data


def test_email_is_matched_case_insensitively(client, sales_user):
    response = client.post("/login", data={"email": sales_user.email.upper(), "password": PASSWORD})
    assert response.status_code == 302


def test_wrong_password_rejected(client, sales_user):
    response = client.post("/login", data={"email": sales_user.email, "password": "wrong"})
    assert response.status_code == 401
    assert b"Invalid email or password." in response.data
    assert client.get("/orders/").status_code == 302


def test_unknown_email_rejected(client):
    response = client.post("/login", data={"email": "nobody@test.local", "password": "x"})
    assert response.status_code == 401


def test_unknown_email_still_checks_a_password_hash(client, monkeypatch):
    # So an unknown email takes as long as a wrong password, and timing can't reveal emails.
    from app.web import auth

    checked = []

    def fake_check(password_hash, password):
        checked.append(password_hash)
        return False

    monkeypatch.setattr(auth, "check_password_hash", fake_check)
    response = client.post("/login", data={"email": "nobody@test.local", "password": "x"})
    assert response.status_code == 401
    assert checked == [auth.DUMMY_PASSWORD_HASH]


def test_pages_require_login(client):
    response = client.get("/orders/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_api_requires_login_with_json_401(client):
    response = client.get("/api/products")
    assert response.status_code == 401
    assert response.get_json() == {"error": "Please log in first.", "details": {}}


def test_logout(client, login, sales_user):
    login(client, sales_user)
    response = client.post("/logout")
    assert response.status_code == 302
    assert client.get("/orders/").status_code == 302


def test_login_redirects_back_to_next_page(client, sales_user):
    response = client.post(
        "/login?next=/customers/", data={"email": sales_user.email, "password": PASSWORD}
    )
    assert response.headers["Location"] == "/customers/"


@pytest.mark.parametrize("next_url", [
    "//evil.example",
    "/\t/evil.example",      # browsers drop the tab and read //evil.example
    "/\n/evil.example",
    "/\\evil.example",       # browsers read the backslash as a slash
    "https://evil.example",
])
def test_login_ignores_offsite_next(client, sales_user, next_url):
    response = client.post(
        "/login",
        query_string={"next": next_url},
        data={"email": sales_user.email, "password": PASSWORD},
    )
    assert response.headers["Location"] == "/"


def test_login_follows_a_next_path_on_this_site(client, sales_user):
    response = client.post(
        "/login",
        query_string={"next": "/orders/"},
        data={"email": sales_user.email, "password": PASSWORD},
    )
    assert response.headers["Location"] == "/orders/"


def test_sales_user_cannot_open_admin_pages(client, login, sales_user):
    login(client, sales_user)
    assert client.get("/stock/").status_code == 403
    assert client.get("/reports/").status_code == 403
    assert client.get("/import/").status_code == 403


def test_admin_sees_admin_pages_and_nav(client, login, admin_user):
    login(client, admin_user)
    assert client.get("/stock/").status_code == 200
    page = client.get("/orders/")
    assert b'href="/reports/"' in page.data


def test_sales_nav_hides_admin_links(client, login, sales_user):
    login(client, sales_user)
    page = client.get("/orders/")
    assert b'href="/reports/"' not in page.data


def test_app_refuses_to_start_without_a_secret_key():
    from app import create_app
    from app.config import TestConfig

    class NoSecretConfig(TestConfig):
        SECRET_KEY = None

    with pytest.raises(RuntimeError, match="SECRET_KEY is not set"):
        create_app(NoSecretConfig)
