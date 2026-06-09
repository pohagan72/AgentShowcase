# tests/conftest.py
# Smoke-test fixtures. We deliberately keep these tests fast and offline:
# - DATABASE_URL is forced to in-memory SQLite so we never touch Railway.
# - GOOGLE_API_KEY / S3 creds are left unset so Gemini and S3 stay disabled
#   (the app already handles their absence gracefully).
# - Presidio is skipped if its spaCy model isn't installed (try/except in
#   create_app() turns it into a warning).
import os
from datetime import datetime, timezone

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

    # Flask-Limiter's IP-based default ("30/min") fires when a single test
    # function issues several /mcp calls back-to-back (the cross-tenant
    # isolation tests do exactly that). Disable it at the limiter object level
    # since init_app() already captured the previous config. The per-org RPM
    # gate inside auth.py still runs, so quota / abuse defense is still
    # exercised by tests.
    from extensions import limiter
    limiter.enabled = False

    # Create the billing schema in the in-memory SQLite so auth.py queries
    # (api_keys lookup, etc.) hit real tables instead of raising NoSuchTable.
    # Real prod uses Alembic migrations; this is a test-only shortcut.
    from db import db

    with app.app_context():
        db.create_all()

    # Mount a tiny test-only handler under @require_auth so failure-path tests
    # exercise the decorator directly without dragging in Gemini, file uploads,
    # or the analyst-agent stream. The handler's behavior is controlled by
    # request headers so each test can drive it into success / explosion.
    from flask import jsonify, request
    from auth import require_auth

    def _test_units_fn(req):
        # Tests set X-Test-Units to drive the units-exceeded (413) path.
        try:
            return int(req.headers.get("X-Test-Units", "1"))
        except ValueError:
            return 1

    @app.route("/_test/auth_probe", methods=["POST"])
    @require_auth(tool_name="test_probe", units_fn=_test_units_fn)
    def _auth_probe():
        # X-Test-Explode=1 triggers the refund-on-exception path.
        if request.headers.get("X-Test-Explode") == "1":
            raise RuntimeError("handler boom")
        return jsonify({"ok": True})

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_blob_store():
    """Wipe the module-level blob store between tests so token reuse / TTL /
    cap state doesn't leak across cases. Autouse so every test sees a clean
    store; tests that don't care pay no attention."""
    import blob_store
    blob_store.reset_default_store()
    yield
    blob_store.reset_default_store()


@pytest.fixture
def url_for_bytes(monkeypatch):
    """Return a helper that stashes bytes in the blob store and returns a
    synzo.test URL the MCP tools can pass through _load_payload.

    Also monkeypatches url_fetcher.fetch_url_bytes so the tool handlers see
    the stashed bytes instead of trying a real network fetch. This lets the
    1000+ lines of test_mcp_server.py keep their existing intent — supply
    bytes to a tool handler — while exercising the URL-only code path in
    _load_payload.
    """
    import url_fetcher
    from blob_store import get_default_store

    TEST_URL_PREFIX = "https://synzo.test/u/"

    def _make(raw: bytes, filename: str = "x.bin", content_type: str = "application/octet-stream") -> str:
        entry = get_default_store().put(
            filename=filename, content_type=content_type, data=raw
        )
        return f"{TEST_URL_PREFIX}{entry.token}"

    def _fake_fetch(url: str, *, max_bytes: int):
        if not url.startswith(TEST_URL_PREFIX):
            raise url_fetcher.UrlFetchError(
                f"Test fetcher only accepts {TEST_URL_PREFIX} URLs (got {url})"
            )
        token = url[len(TEST_URL_PREFIX):]
        entry = get_default_store().get(token)
        if entry is None:
            raise url_fetcher.UrlFetchError("Test URL expired or unknown")
        if len(entry.data) > max_bytes:
            raise url_fetcher.UrlFetchError(
                f"Test blob {len(entry.data)} > max_bytes {max_bytes}"
            )
        return entry.data, entry.content_type

    import mcp_tools
    monkeypatch.setattr(mcp_tools, "fetch_url_bytes", _fake_fetch)

    return _make


@pytest.fixture
def seeded_org(app):
    """Create a fresh free-tier org + current-period quota + API key per test.

    Yields a dict so tests can grab whatever they need. Each test gets a brand
    new org id so the in-memory RPM bucket in auth.py (keyed on org_id) doesn't
    leak across tests. We don't bother tearing down rows — sqlite :memory: is
    session-scoped and the unique-bucket-per-org strategy handles isolation.
    """
    from auth import PLANS, _period_bounds, _rpm_buckets, issue_api_key
    from db import db
    from db.models import Org, Quota

    with app.app_context():
        org = Org(name=f"test-org-{datetime.now(timezone.utc).timestamp()}", plan="free")
        db.session.add(org)
        db.session.commit()

        period_start, period_end = _period_bounds(datetime.now(timezone.utc))
        plan_limits = PLANS[org.plan]
        quota = Quota(
            org_id=org.id,
            period_start=period_start,
            period_end=period_end,
            calls_remaining=plan_limits["calls_per_month"],
            calls_limit=plan_limits["calls_per_month"],
        )
        db.session.add(quota)
        db.session.commit()

        raw_key, key_record = issue_api_key(org_id=org.id, name="test")

        # Capture ids while still in the session, then yield plain values so
        # tests don't have to manage the app context themselves.
        org_id = org.id
        quota_id = quota.id
        key_id = key_record.id

    # Make sure no stale RPM stamps survive from a previous test that happened
    # to reuse this org_id (won't happen given timestamp-suffixed names, but
    # cheap belt-and-braces).
    _rpm_buckets.pop(org_id, None)

    yield {
        "org_id": org_id,
        "quota_id": quota_id,
        "api_key_id": key_id,
        "api_key": raw_key,
        "auth_header": {"Authorization": f"Bearer {raw_key}"},
        "plan": "free",
        "plan_limits": dict(plan_limits),
    }
