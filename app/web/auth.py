"""Login and logout."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from app.extensions import db
from app.models import User

auth_bp = Blueprint("auth", __name__)


def safe_next_url(target):
    """Only follow ?next= if it is a path on this site, so a link can't send users elsewhere."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("home")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.execute(select(User).where(User.email == email)).scalar_one_or_none()
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
