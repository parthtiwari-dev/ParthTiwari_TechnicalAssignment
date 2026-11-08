"""Settings, read from environment variables.

python-dotenv loads the `.env` file in the project root, so locally you only edit `.env`.
Nothing secret is written in this file.
"""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Refuse any request body over 2 MB before reading it (413). The CSV import allows 1 MB.
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    # The login cookie: JavaScript can't read it (HttpOnly, Flask's default, kept on), and
    # the browser doesn't send it with forms posted from other sites (SameSite=Lax).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SQLALCHEMY_ENGINE_OPTIONS = {
        # READ COMMITTED: every query sees the latest committed data. The rows we change
        # are protected by SELECT ... FOR UPDATE locks (see services/orders.py), not by
        # MySQL's default REPEATABLE READ snapshot, which could show an old copy of a row.
        "isolation_level": "READ COMMITTED",
        # Check a pooled connection is still alive before using it.
        "pool_pre_ping": True,
    }


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL")
    # Tests post forms without a CSRF token. CSRF stays on everywhere else.
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-only-secret"
