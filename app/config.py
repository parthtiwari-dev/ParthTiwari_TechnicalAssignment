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
