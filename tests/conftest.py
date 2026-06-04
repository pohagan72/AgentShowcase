# tests/conftest.py
# Smoke-test fixtures. We deliberately keep these tests fast and offline:
# - DATABASE_URL is forced to in-memory SQLite so we never touch Railway.
# - GOOGLE_API_KEY / S3 creds are left unset so Gemini and S3 stay disabled
#   (the app already handles their absence gracefully).
# - Presidio is skipped if its spaCy model isn't installed (try/except in
#   create_app() turns it into a warning).
import os

import pytest


@pytest.fixture(scope="session")
def app():
    # Override env BEFORE create_app() / Config import so the test process never
    # talks to Railway Postgres or production services.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["FLASK_DEBUG"] = "1"  # allow the dev SECRET_KEY fallback
    os.environ.setdefault("FLASK_INSECURE_COOKIES", "1")  # tests run over plain http

    from app import create_app

    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    yield app


@pytest.fixture
def client(app):
    return app.test_client()
