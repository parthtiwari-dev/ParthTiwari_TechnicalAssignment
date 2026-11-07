"""Login and logout."""
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import User

auth_bp = Blueprint("auth", __name__)

# A hash of a password nobody has. When the email is unknown, login still checks the password
# against this, so a wrong email takes as long as a wrong password and timing can't reveal
# which emails exist. Made with the same method as real password hashes, so it costs the same.
DUMMY_PASSWORD_HASH = generate_password_hash("no-user-has-this-password")


def safe_next_url(target):
    """Only follow ?next= if it is a path on this site, so a link can't send users elsewhere.

    Browsers are forgiving: they drop tabs and newlines inside a URL and read a backslash as a
    slash. So "/<tab>/evil.example" or "/<backslash>evil.example" would really go to
    evil.example. Any backslash or control character is refused, and what is left must have
    no scheme ("https:") and no host ("//evil.example").
    """
    if not target or not target.startswith("/"):
        return url_for("home")
    if "\\" in target or any(ord(char) < 32 or ord(char) == 127 for char in target):
        return url_for("home")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return url_for("home")
    return target


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            check_password_hash(DUMMY_PASSWORD_HASH, password)  # same work as a real check
        # Same message whether the email or the password is wrong, so emails can't be guessed.
        if user is None or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email), 401
        login_user(user)
        return redirect(safe_next_url(request.args.get("next")))

    return render_template("auth/login.html", email="")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # POST, not GET, so another site can't log the user out with a plain link or image.
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
