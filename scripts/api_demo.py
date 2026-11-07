"""Try the JSON API against a running app, using only the Python standard library.

Usage (start the app first with `flask run`):

    python scripts/api_demo.py                           # http://127.0.0.1:5000, customer id 1
    python scripts/api_demo.py http://127.0.0.1:5102 9   # another address and customer id

Ids keep growing after `seed.py --reset`, so pass the id of an active customer if 1 isn't one.

It logs in as the sample sales user from .env (SEED_SALES_EMAIL / SEED_SALES_PASSWORD), the
same way a browser does, then lists products, creates a Draft order, reads it back and cancels
it. Cancelling a Draft doesn't touch stock, so running this leaves stock as it was.

How the login works, so you can do the same in any tool:
1. GET /login and read the csrf_token hidden field.
2. POST /login with email, password and csrf_token. Keep the session cookie it sets.
3. Send the cookie with every API call. For POST and PUT also send the header X-CSRFToken,
   read from <meta name="csrf-token"> on any page.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from dotenv import load_dotenv

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:5000"
CUSTOMER_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 1

# One opener with a cookie jar: it keeps the session cookie between requests, like a browser.
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def csrf_token_from(html):
    match = re.search(r'name="csrf[-_]token"\s+(?:content|value)="([^"]+)"', html)
    return match.group(1)


def call(method, path, body=None, csrf_token=None):
    """Send one request. Returns (status, parsed JSON). Error statuses are returned, not raised."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE_URL + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if csrf_token:
        request.add_header("X-CSRFToken", csrf_token)
    try:
        with opener.open(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def show(title, status, body):
    print(f"--- {title}: {status}")
    print(json.dumps(body, indent=2))


def main():
    load_dotenv()

    # 1 and 2: log in through the normal login form.
    login_page = opener.open(BASE_URL + "/login").read().decode()
    form = urllib.parse.urlencode({
        "email": os.environ["SEED_SALES_EMAIL"],
        "password": os.environ["SEED_SALES_PASSWORD"],
        "csrf_token": csrf_token_from(login_page),
    }).encode()
    opener.open(BASE_URL + "/login", data=form)

    # 3: the token for API writes, from the meta tag on any page.
    token = csrf_token_from(opener.open(BASE_URL + "/orders/").read().decode())

    status, products = call("GET", "/api/products?per_page=2")
    show("GET /api/products?per_page=2", status, products)
    first_product = products["items"][0]

    status, error = call("POST", "/api/orders", {"customer_id": CUSTOMER_ID, "items": []})
    show("POST /api/orders without the CSRF header", status, error)

    status, order = call("POST", "/api/orders", {
        "customer_id": CUSTOMER_ID,
        "discount_percent": "10",
        "items": [{"product_id": first_product["id"], "quantity": 2}],
    }, csrf_token=token)
    show("POST /api/orders", status, order)
    if status != 201:
        sys.exit("Could not create the order. Pass the id of an active customer as the 2nd argument.")

    status, body = call("GET", f"/api/orders/{order['id']}")
    show(f"GET /api/orders/{order['id']}", status, body)

    status, body = call("POST", f"/api/orders/{order['id']}/cancel", csrf_token=token)
    show(f"POST /api/orders/{order['id']}/cancel", status, body)


if __name__ == "__main__":
    main()
