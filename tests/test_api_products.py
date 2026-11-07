"""GET /api/products and GET /api/products/<id>: active products only, search, pagination."""


def test_products_need_login(client):
    response = client.get("/api/products")
    assert response.status_code == 401
    assert response.get_json() == {"error": "Please log in first.", "details": {}}


def test_lists_only_active_products(client, login, sales_user, make_product):
    active = make_product(code="KEY-001", name="Keyboard", price="1500.00", stock=7)
    make_product(code="OLD-001", name="Old keyboard", is_active=False)
    login(client, sales_user)

    response = client.get("/api/products")

    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["per_page"] == 20
    assert body["items"] == [{
        "id": active.id,
        "code": "KEY-001",
        "name": "Keyboard",
        "category": "Accessories",
        "price": "1500.00",
        "stock_quantity": 7,
    }]


def test_admin_also_gets_only_active_products(client, login, admin_user, make_product):
    make_product(code="KEY-001")
    make_product(code="OLD-001", is_active=False)
    login(client, admin_user)

    codes = [item["code"] for item in client.get("/api/products").get_json()["items"]]
    assert codes == ["KEY-001"]


def test_search_by_code_or_name_and_category(client, login, sales_user, make_product):
    make_product(code="KEY-001", name="Keyboard", category="Accessories")
    make_product(code="MOU-001", name="Mouse", category="Accessories")
    make_product(code="MON-001", name="Monitor", category="Displays")
    login(client, sales_user)

    def codes(url):
        return [item["code"] for item in client.get(url).get_json()["items"]]

    assert codes("/api/products?q=mouse") == ["MOU-001"]
    assert codes("/api/products?q=MO") == ["MON-001", "MOU-001"]
    assert codes("/api/products?category=Displays") == ["MON-001"]
    assert codes("/api/products?q=key&category=Displays") == []


def test_pagination(client, login, sales_user, make_product):
    for number in range(1, 6):
        make_product(code=f"P-{number:03d}")
    login(client, sales_user)

    body = client.get("/api/products?page=2&per_page=2").get_json()

    assert body["page"] == 2
    assert body["per_page"] == 2
    assert body["total"] == 5
    assert [item["code"] for item in body["items"]] == ["P-003", "P-004"]


def test_per_page_is_capped_at_100(client, login, sales_user):
    login(client, sales_user)
    body = client.get("/api/products?per_page=500").get_json()
    assert body["per_page"] == 100


def test_non_number_page_is_rejected(client, login, sales_user):
    login(client, sales_user)

    response = client.get("/api/products?page=abc&per_page=2.5")

    assert response.status_code == 422
    assert response.get_json() == {
        "error": "Page and per_page must be whole numbers.",
        "details": {"page": "Must be a whole number.", "per_page": "Must be a whole number."},
    }


def test_get_one_product(client, login, sales_user, make_product):
    product = make_product(code="KEY-001", price="1500.00")
    login(client, sales_user)

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 200
    assert response.get_json()["code"] == "KEY-001"
    assert response.get_json()["price"] == "1500.00"


def test_inactive_or_missing_product_is_404(client, login, sales_user, make_product):
    inactive = make_product(is_active=False)
    login(client, sales_user)

    for product_id in (inactive.id, inactive.id + 1000):
        response = client.get(f"/api/products/{product_id}")
        assert response.status_code == 404
        assert response.get_json() == {"error": "Product not found.", "details": {}}
