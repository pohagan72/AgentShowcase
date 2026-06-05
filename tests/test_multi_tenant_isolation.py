# tests/test_multi_tenant_isolation.py
# Cross-tenant attack surface — the bug class that hurts most.
# Each test seeds two orgs (A and B) and proves Org A cannot read or mutate
# Org B's data through any public route.
#
# Conftest already mounts /_test/auth_probe under @require_auth, so we can
# exercise the API-key path without needing Gemini or real summarization.

from datetime import datetime, timezone

from db import db
from db.models import ApiKey, Org, OrgMembership, Quota, UsageEvent, User


def _seed_org(app, *, name, plan="free"):
    """Bare-bones org factory. Returns dict with org_id + a fresh API key
    and a single 'owner' user attached to the org."""
    from auth import PLANS, _period_bounds, issue_api_key

    with app.app_context():
        org = Org(workos_org_id=f"workos_{name}", name=name, plan=plan)
        db.session.add(org)
        db.session.flush()

        user = User(workos_user_id=f"workos_user_{name}", email=f"{name}@example.com")
        db.session.add(user)
        db.session.flush()
        db.session.add(OrgMembership(user_id=user.id, org_id=org.id, role="owner"))

        now = datetime.now(timezone.utc)
        period_start, period_end = _period_bounds(now)
        existing = (
            db.session.query(Quota)
            .filter_by(org_id=org.id, period_start=period_start)
            .one_or_none()
        )
        if existing is None:
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
            "user_id": user.id,
            "raw_key": raw_key,
            "api_key_id": key_record.id,
        }


# --- API path: usage_events get the right org_id ------------------------------


def test_api_call_records_usage_against_caller_org_only(app, client):
    """Org A's key calling /_test/auth_probe produces a usage_events row for
    Org A — never for Org B."""
    a = _seed_org(app, name="iso_a1")
    b = _seed_org(app, name="iso_b1")

    res = client.post(
        "/_test/auth_probe",
        headers={"Authorization": f"Bearer {a['raw_key']}"},
    )
    assert res.status_code == 200

    with app.app_context():
        a_events = db.session.query(UsageEvent).filter_by(org_id=a["org_id"]).all()
        b_events = db.session.query(UsageEvent).filter_by(org_id=b["org_id"]).all()
        assert len(a_events) == 1
        assert a_events[0].auth_method == "api_key"
        assert b_events == []


def test_api_quota_pools_are_independent(app, client):
    """Exhausting Org A's quota does not affect Org B's. We don't drain via 50
    real HTTP calls — that would trip the 10 req/min RPM ceiling. Just set Org
    A's remaining count to 0 directly and confirm the 402/200 split."""
    from auth import _rpm_buckets

    a = _seed_org(app, name="iso_a_q")
    b = _seed_org(app, name="iso_b_q")

    with app.app_context():
        a_quota = db.session.query(Quota).filter_by(org_id=a["org_id"]).one()
        a_quota.calls_remaining = 0
        db.session.commit()

    # Belt-and-braces: don't carry stale RPM stamps from prior tests.
    _rpm_buckets.pop(a["org_id"], None)
    _rpm_buckets.pop(b["org_id"], None)

    # Org A → 402 because quota is exhausted.
    r = client.post(
        "/_test/auth_probe",
        headers={"Authorization": f"Bearer {a['raw_key']}"},
    )
    assert r.status_code == 402

    # Org B → 200, full quota.
    r = client.post(
        "/_test/auth_probe",
        headers={"Authorization": f"Bearer {b['raw_key']}"},
    )
    assert r.status_code == 200

    with app.app_context():
        a_quota = db.session.query(Quota).filter_by(org_id=a["org_id"]).one()
        b_quota = db.session.query(Quota).filter_by(org_id=b["org_id"]).one()
        assert a_quota.calls_remaining == 0
        assert b_quota.calls_remaining == 49


# --- Dashboard path: keys, members, switch-org --------------------------------


def test_dashboard_session_sees_only_own_keys(app, client):
    a = _seed_org(app, name="iso_a_keys")
    b = _seed_org(app, name="iso_b_keys")

    with client.session_transaction() as sess:
        sess["user_id"] = a["user_id"]
        sess["current_org_id"] = a["org_id"]

    res = client.get("/dashboard")
    assert res.status_code == 200
    body = res.get_data(as_text=True)

    # Org A's key prefix is visible.
    assert a["raw_key"][:16] in body
    # Org B's key prefix is NOT.
    assert b["raw_key"][:16] not in body
    # Org A's member email visible; Org B's is not.
    assert "iso_a_keys@example.com" in body
    assert "iso_b_keys@example.com" not in body


def test_revoke_other_orgs_key_returns_404_and_does_nothing(app, client):
    a = _seed_org(app, name="iso_a_rev")
    b = _seed_org(app, name="iso_b_rev")

    with client.session_transaction() as sess:
        sess["user_id"] = a["user_id"]
        sess["current_org_id"] = a["org_id"]

    res = client.post(f"/dashboard/keys/{b['api_key_id']}/revoke")
    assert res.status_code == 404

    with app.app_context():
        # Org B's key is untouched (404, not silently revoked).
        key = db.session.get(ApiKey, b["api_key_id"])
        assert key.revoked_at is None


def test_update_membership_in_other_org_returns_404(app, client):
    a = _seed_org(app, name="iso_a_mem")
    b = _seed_org(app, name="iso_b_mem")

    # Find Org B's owner membership id.
    with app.app_context():
        b_membership = (
            db.session.query(OrgMembership).filter_by(org_id=b["org_id"]).first()
        )
        b_membership_id = b_membership.id

    with client.session_transaction() as sess:
        sess["user_id"] = a["user_id"]
        sess["current_org_id"] = a["org_id"]

    res = client.post(
        f"/dashboard/members/{b_membership_id}/role",
        data={"role": "admin"},
    )
    assert res.status_code == 404

    with app.app_context():
        # Role unchanged in Org B.
        m = db.session.get(OrgMembership, b_membership_id)
        assert m.role == "owner"


def test_switch_to_non_member_org_returns_404(app, client):
    a = _seed_org(app, name="iso_a_sw")
    b = _seed_org(app, name="iso_b_sw")

    with client.session_transaction() as sess:
        sess["user_id"] = a["user_id"]
        sess["current_org_id"] = a["org_id"]

    res = client.get(f"/dashboard/switch-org/{b['org_id']}")
    assert res.status_code == 404

    with client.session_transaction() as sess:
        assert sess["current_org_id"] == a["org_id"]  # session unchanged
