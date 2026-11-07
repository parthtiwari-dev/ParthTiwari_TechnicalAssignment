"""Login, logout, and the login requirement on pages and the API."""
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


def test_pages_require_login(client):
    response = client.get("/orders/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_api_requires_login_with_json_401(app):
    # The API routes are added later; this checks the shared "not logged in" answer for /api/.
    from app.extensions import login_manager

    with app.test_request_context("/api/orders/1"):
        response, status = login_manager.unauthorized()
    assert status == 401
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


def test_login_ignores_offsite_next(client, sales_user):
    response = client.post(
        "/login?next=//evil.example", data={"email": sales_user.email, "password": PASSWORD}
    )
    assert response.headers["Location"] == "/"


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
