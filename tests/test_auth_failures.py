# tests/test_auth_failures.py
# Failure-path coverage for @require_auth. Exercises the four paths the plan
# explicitly calls out: 402 (exhausted quota), 413 (oversized units), 429
# (rate-limited), and refund-on-handler-exception. All tests hit the
# /_test/auth_probe route registered in conftest.py — a thin handler wrapped
# by require_auth so we test the decorator, not the Gemini pipeline.

from datetime import datetime, timezone

from sqlalchemy import select


def _quota_remaining(app, quota_id):
    """Read back calls_remaining for a quota row, in its own app context."""
    from db import db
    from db.models import Quota

    with app.app_context():
        return db.session.get(Quota, quota_id).calls_remaining


def _usage_rows(app, org_id):
    from db import db
    from db.models import UsageEvent

    with app.app_context():
        return (
            db.session.execute(
                select(UsageEvent).where(UsageEvent.org_id == org_id).order_by(UsageEvent.id)
            )
            .scalars()
            .all()
        )


# --- 402: exhausted quota -----------------------------------------------------


def test_402_when_quota_exhausted(client, app, seeded_org):
    """When calls_remaining hits 0, the next call gets 402 and is metered as
    quota_exhausted with no further decrement."""
    from db import db
    from db.models import Quota

    # Drain the quota directly to avoid making 50 real requests.
    with app.app_context():
        quota = db.session.get(Quota, seeded_org["quota_id"])
        quota.calls_remaining = 0
        db.session.commit()

    resp = client.post("/_test/auth_probe", headers=seeded_org["auth_header"])

    assert resp.status_code == 402
    assert resp.is_json
    assert "error" in resp.get_json()
    # Still at 0 — exhausted path must not go negative or wrap.
    assert _quota_remaining(app, seeded_org["quota_id"]) == 0

    events = _usage_rows(app, seeded_org["org_id"])
    # Latest event is the 402; earlier rows (if any) are from setup paths.
    assert events[-1].status == "error"
    assert events[-1].error_code == "quota_exhausted"
    assert events[-1].tool == "test_probe"


# --- 413: oversized units -----------------------------------------------------


def test_413_when_units_exceed_per_call_cap(client, app, seeded_org):
    """units_fn returning more than the plan's pages_per_call must 413 BEFORE
    decrementing quota — customers can't be debited for rejected requests."""
    cap = seeded_org["plan_limits"]["pages_per_call"]  # free tier: 20
    before = _quota_remaining(app, seeded_org["quota_id"])

    resp = client.post(
        "/_test/auth_probe",
        headers={**seeded_org["auth_header"], "X-Test-Units": str(cap + 1)},
    )

    assert resp.status_code == 413
    assert resp.is_json
    # Quota untouched — 413 fires before _decrement_quota.
    assert _quota_remaining(app, seeded_org["quota_id"]) == before

    events = _usage_rows(app, seeded_org["org_id"])
    assert events[-1].status == "error"
    assert events[-1].error_code == "units_exceeded"
    assert events[-1].units == cap + 1


# --- 429: rate-limited --------------------------------------------------------


def test_429_when_rpm_exceeded(client, app, seeded_org):
    """Free plan is 10 RPM. Eleventh request inside the same minute must 429
    and not decrement quota."""
    rpm = seeded_org["plan_limits"]["rpm"]  # free tier: 10

    # Burn the budget. Each of these succeeds (quota=50 >> rpm=10).
    for _ in range(rpm):
        resp = client.post("/_test/auth_probe", headers=seeded_org["auth_header"])
        assert resp.status_code == 200, resp.get_json()

    quota_after_burn = _quota_remaining(app, seeded_org["quota_id"])

    # Next one in the same minute trips the in-memory bucket.
    resp = client.post("/_test/auth_probe", headers=seeded_org["auth_header"])
    assert resp.status_code == 429
    assert resp.is_json
    # 429 fires before _decrement_quota — quota untouched on this attempt.
    assert _quota_remaining(app, seeded_org["quota_id"]) == quota_after_burn

    events = _usage_rows(app, seeded_org["org_id"])
    # Look for at least one rate_limited event — there may be others from
    # the success burst above.
    rate_limited = [e for e in events if e.error_code == "rate_limited"]
    assert rate_limited, "expected a rate_limited usage_event"
    assert rate_limited[-1].status == "error"
    assert rate_limited[-1].tool == "test_probe"


# --- Refund on handler exception ----------------------------------------------


def test_refund_on_handler_exception(client, app, seeded_org):
    """When the wrapped handler raises, the decorator must refund the quota
    and record a `refunded` usage_event before re-raising.

    Flask's test client re-raises unhandled exceptions by default (TESTING
    propagates), so we drive the request through .test_client() with
    PROPAGATE_EXCEPTIONS off, and check the response. We care about the
    side-effects (refund + metering), not whether Flask returns 500 vs raises.
    """
    before = _quota_remaining(app, seeded_org["quota_id"])

    # Disable exception propagation just for this request so the unhandled
    # RuntimeError becomes a 500 response, matching production behavior under
    # gunicorn / waitress.
    app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        resp = client.post(
            "/_test/auth_probe",
            headers={**seeded_org["auth_header"], "X-Test-Explode": "1"},
        )
    finally:
        app.config["PROPAGATE_EXCEPTIONS"] = None

    assert resp.status_code == 500
    # Quota was decremented, then refunded — net zero.
    assert _quota_remaining(app, seeded_org["quota_id"]) == before

    events = _usage_rows(app, seeded_org["org_id"])
    refunded = [e for e in events if e.status == "refunded"]
    assert refunded, "expected a refunded usage_event"
    assert refunded[-1].error_code == "handler_error"
    assert refunded[-1].tool == "test_probe"


# --- Refund does NOT go above the original limit -----------------------------


def test_refund_clamped_to_limit(client, app, seeded_org):
    """Belt-and-braces: if the refund path ever fires when quota is already at
    its limit (shouldn't happen in practice — decrement runs first), the SQL
    guard `calls_remaining < calls_limit` must prevent overshoot.

    We simulate this by manually setting calls_remaining = calls_limit then
    calling _refund_quota directly. Tests the SQL clamp, not the decorator path.
    """
    from auth import _refund_quota
    from db import db
    from db.models import Quota

    with app.app_context():
        quota = db.session.get(Quota, seeded_org["quota_id"])
        quota.calls_remaining = quota.calls_limit
        db.session.commit()
        limit = quota.calls_limit

    with app.app_context():
        _refund_quota(seeded_org["org_id"])

    assert _quota_remaining(app, seeded_org["quota_id"]) == limit
