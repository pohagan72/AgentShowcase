# tests/test_mcp_concurrency.py
# Phase 2.5.A safety nets: the per-tool wall-clock timeout in auth.run_metered_tool.
#
# These are unit tests for the timeout pipeline. They drive run_metered_tool
# directly with a sleeping stub handler and assert the quota refund + 'timeout'
# meter outcome happen. The full real-Waitress concurrency test that the §6
# Phase 2.5.A plan asks for ("32 concurrent summarize_document calls + homepage
# stays responsive") lives in scripts/concurrency_load_test.py instead — it's
# an operational test ("run before any public-launch deploy" per the plan),
# not a CI signal, and bundling it as a pytest fixture has fragile interactions
# with the session-scoped in-memory SQLite app fixture from conftest.py.

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from db import db
from db.models import Org, OrgMembership, Quota, UsageEvent, User


def _seed_org(app, name="timeout-org", plan="free"):
    """Minimal seed copy of test_mcp_server._seed_org — kept inline so this file
    has no cross-test imports."""
    from auth import PLANS, _period_bounds, issue_api_key

    with app.app_context():
        org = Org(workos_org_id=f"workos_{name}", name=name, plan=plan)
        db.session.add(org)
        db.session.flush()

        user = User(workos_user_id=f"workos_user_{name}", email=f"{name}@example.com")
        db.session.add(user)
        db.session.flush()
        db.session.add(OrgMembership(user_id=user.id, org_id=org.id, role="owner"))

        period_start, period_end = _period_bounds(datetime.now(timezone.utc))
        db.session.add(
            Quota(
                org_id=org.id,
                period_start=period_start,
                period_end=period_end,
                calls_remaining=PLANS[plan]["calls_per_month"],
                calls_limit=PLANS[plan]["calls_per_month"],
            )
        )
        db.session.commit()

        raw_key, key_record = issue_api_key(org_id=org.id, name=f"{name}-key")
        return {
            "org_id": org.id,
            "raw_key": raw_key,
            "api_key_id": key_record.id,
            "auth_header": {"Authorization": f"Bearer {raw_key}"},
        }


def test_timeout_refunds_quota_and_meters_as_timeout(app, monkeypatch):
    """A handler that runs past TOOL_TIMEOUT_SECONDS must:
      - raise AuthError(504) at the caller,
      - refund the decremented quota slot,
      - record a usage_events row with status='refunded', error_code='timeout'.

    Set the timeout to 0.5s and stub a handler that sleeps 2s. The Future is
    abandoned on timeout (CPython can't kill threads), so the stub eventually
    finishes in the background — but the caller has already gotten its 504.
    """
    import auth

    seed = _seed_org(app, name="timeout-A")
    monkeypatch.setattr(auth, "TOOL_TIMEOUT_SECONDS", 0.5)

    def slow_handler():
        time.sleep(2.0)
        return {"never": "returned"}

    from auth import AuthError, Principal

    principal = Principal(
        org_id=seed["org_id"], plan="free", auth_method="api_key",
        api_key_id=seed["api_key_id"],
    )

    with app.app_context():
        with pytest.raises(AuthError) as exc_info:
            auth.run_metered_tool(principal, "test_tool", units=1, fn=slow_handler)

        assert exc_info.value.status == 504
        assert "timeout" in exc_info.value.message.lower()

        # Quota was decremented (50 -> 49) then refunded back (49 -> 50).
        quota = db.session.query(Quota).filter_by(org_id=seed["org_id"]).one()
        assert quota.calls_remaining == 50

        events = (
            db.session.query(UsageEvent)
            .filter_by(org_id=seed["org_id"])
            .order_by(UsageEvent.id)
            .all()
        )
        assert len(events) == 1
        assert events[0].status == "refunded"
        assert events[0].error_code == "timeout"


def test_handler_under_timeout_runs_normally_and_meters_ok(app, monkeypatch):
    """The fast path: handler finishes well under the timeout. Quota stays
    decremented, usage event is 'ok', and the handler's return value reaches
    the caller."""
    import auth

    seed = _seed_org(app, name="timeout-B")
    monkeypatch.setattr(auth, "TOOL_TIMEOUT_SECONDS", 5)

    def fast_handler():
        return {"ok": True, "tag": "fast"}

    from auth import Principal

    principal = Principal(
        org_id=seed["org_id"], plan="free", auth_method="api_key",
        api_key_id=seed["api_key_id"],
    )

    with app.app_context():
        result = auth.run_metered_tool(principal, "test_tool", units=1, fn=fast_handler)
        assert result == {"ok": True, "tag": "fast"}

        quota = db.session.query(Quota).filter_by(org_id=seed["org_id"]).one()
        assert quota.calls_remaining == 49  # decremented, not refunded

        events = db.session.query(UsageEvent).filter_by(org_id=seed["org_id"]).all()
        assert len(events) == 1
        assert events[0].status == "ok"
        assert events[0].error_code is None


def test_handler_exception_under_timeout_still_refunds(app, monkeypatch):
    """The handler raises a normal exception before the timeout fires. The
    existing refund-on-error path must still work (this is the pre-Phase-2.5.A
    behavior; we're confirming the timeout wrapping didn't break it)."""
    import auth

    seed = _seed_org(app, name="timeout-C")
    monkeypatch.setattr(auth, "TOOL_TIMEOUT_SECONDS", 5)

    def boom():
        raise RuntimeError("kaboom")

    from auth import Principal

    principal = Principal(
        org_id=seed["org_id"], plan="free", auth_method="api_key",
        api_key_id=seed["api_key_id"],
    )

    with app.app_context():
        with pytest.raises(RuntimeError, match="kaboom"):
            auth.run_metered_tool(principal, "test_tool", units=1, fn=boom)

        quota = db.session.query(Quota).filter_by(org_id=seed["org_id"]).one()
        assert quota.calls_remaining == 50  # refunded

        events = db.session.query(UsageEvent).filter_by(org_id=seed["org_id"]).all()
        assert len(events) == 1
        assert events[0].status == "refunded"
        assert events[0].error_code == "handler_error"


def test_timeout_disabled_when_set_to_zero(app, monkeypatch):
    """TOOL_TIMEOUT_SECONDS=0 disables the executor wrapping entirely (handler
    runs inline). Useful for tests that don't want the extra thread overhead
    and as an escape hatch in prod."""
    import auth

    seed = _seed_org(app, name="timeout-D")
    monkeypatch.setattr(auth, "TOOL_TIMEOUT_SECONDS", 0)

    ran_on_thread = {"tid": None}

    def check_thread():
        ran_on_thread["tid"] = threading.get_ident()
        return {"ok": True}

    from auth import Principal

    principal = Principal(
        org_id=seed["org_id"], plan="free", auth_method="api_key",
        api_key_id=seed["api_key_id"],
    )

    caller_tid = threading.get_ident()
    with app.app_context():
        auth.run_metered_tool(principal, "test_tool", units=1, fn=check_thread)

    # With timeout disabled, the handler runs on the caller's thread, not a
    # worker thread.
    assert ran_on_thread["tid"] == caller_tid


def test_handler_can_access_current_app_through_executor(app, monkeypatch):
    """Tool handlers in mcp_tools.py use `current_app.config[...]` and
    `current_app.presidio_analyzer`. When the timeout wrapping submits the
    handler to a worker thread, the Flask app context must be pushed onto
    that thread or the handler will see RuntimeError: working outside of
    application context."""
    import auth
    from flask import current_app

    seed = _seed_org(app, name="timeout-E")
    monkeypatch.setattr(auth, "TOOL_TIMEOUT_SECONDS", 5)
    app.config["SYNZO_TEST_MARKER"] = "phase-2.5.A"

    def handler():
        # If app context isn't propagated, this throws RuntimeError.
        return {"marker": current_app.config["SYNZO_TEST_MARKER"]}

    from auth import Principal

    principal = Principal(
        org_id=seed["org_id"], plan="free", auth_method="api_key",
        api_key_id=seed["api_key_id"],
    )

    with app.app_context():
        result = auth.run_metered_tool(principal, "test_tool", units=1, fn=handler)
        assert result == {"marker": "phase-2.5.A"}
