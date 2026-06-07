# tests/test_auth_routes.py
# Cover the cookie-session auth surface added in Phase 1.5:
#   - /auth/login redirects to a (mocked) WorkOS AuthKit URL and stashes state.
#   - /auth/callback exchanges the code (mocked), provisions orgs/quotas/
#     memberships, sets the session, redirects to /dashboard.
#   - /dashboard refuses without session.
#   - Dashboard mutations (issue/revoke keys, invite/role) enforce role gates.
#   - /dashboard/switch-org honors membership.
#   - Cross-tenant attempts return 404 (not 200 / leaked data).
#
# WorkOS SDK is mocked at the auth_routes._workos seam so no network IO happens.

import jwt
import pytest
from types import SimpleNamespace

from db import db
from db.models import ApiKey, Org, OrgMembership, Quota, User


# --- Helpers ------------------------------------------------------------------


def _fake_workos(monkeypatch, *, user_id="user_01", email="alice@example.com",
                  org_id_claim=None, created_org_id="org_new", create_calls=None,
                  invitation_calls=None):
    """Patch auth_routes._workos() to return a stub with the methods the
    callback / invite handlers call. Returns the stub for further assertions."""

    access_token = jwt.encode(
        {
            "sub": user_id,
            "org_id": org_id_claim,
            "iss": "https://api.workos.com/user_management/test",
            "exp": 9999999999,
            "iat": 1700000000,
        },
        "test-secret",
        algorithm="HS256",
    )

    auth_response = SimpleNamespace(
        user=SimpleNamespace(id=user_id, email=email),
        access_token=access_token,
    )

    def get_authorization_url(*, provider, redirect_uri, state, **kwargs):
        return f"https://authkit.test/?state={state}"

    def authenticate_with_code(*, code, **kwargs):
        return auth_response

    def create_organization(*, name, **kwargs):
        if create_calls is not None:
            create_calls.append(name)
        return SimpleNamespace(id=created_org_id, name=name)

    def create_organization_membership(*, user_id, organization_id, **kwargs):
        return SimpleNamespace(id="om_test")

    def send_invitation(*, email, organization_id, **kwargs):
        if invitation_calls is not None:
            invitation_calls.append((email, organization_id))
        return SimpleNamespace(id="inv_test")

    stub = SimpleNamespace(
        user_management=SimpleNamespace(
            get_authorization_url=get_authorization_url,
            authenticate_with_code=authenticate_with_code,
            send_invitation=send_invitation,
        ),
        organizations=SimpleNamespace(
            create_organization=create_organization,
        ),
        organization_membership=SimpleNamespace(
            create_organization_membership=create_organization_membership,
        ),
    )

    import auth_routes
    monkeypatch.setattr(auth_routes, "_workos", lambda: stub)
    monkeypatch.setattr(auth_routes, "_redirect_uri", lambda: "http://localhost:5001/auth/callback")
    return stub


def _seed_user_and_org(app, *, email="bob@example.com", workos_user_id="user_b",
                       workos_org_id="org_b", role="owner", plan="free"):
    """Helper for cross-tenant tests: create User + Org + membership + key
    directly in the DB so we can test isolation without running through the
    /auth/callback flow."""
    from auth import issue_api_key

    with app.app_context():
        user = User(workos_user_id=workos_user_id, email=email)
        db.session.add(user)
        org = Org(workos_org_id=workos_org_id, name=f"{email}'s Workspace", plan=plan)
        db.session.add(org)
        db.session.flush()
        db.session.add(OrgMembership(user_id=user.id, org_id=org.id, role=role))
        # Provision a quota row so the dashboard view has something to render.
        from datetime import datetime, timezone
        from auth import PLANS, _period_bounds
        period_start, period_end = _period_bounds(datetime.now(timezone.utc))
        # Avoid uq_quotas_org_period collisions in session-scoped DB.
        existing = db.session.query(Quota).filter_by(org_id=org.id, period_start=period_start).one_or_none()
        if existing is None:
            db.session.add(Quota(
                org_id=org.id, period_start=period_start, period_end=period_end,
                calls_remaining=PLANS[plan]["calls_per_month"],
                calls_limit=PLANS[plan]["calls_per_month"],
            ))
        db.session.commit()

        raw_key, key_record = issue_api_key(org_id=org.id, name="test")
        return {
            "user_id": user.id,
            "org_id": org.id,
            "workos_user_id": workos_user_id,
            "raw_key": raw_key,
            "api_key_id": key_record.id,
        }


# --- /auth/login --------------------------------------------------------------


def test_login_redirects_to_authkit_with_state(client, monkeypatch):
    _fake_workos(monkeypatch)
    res = client.get("/auth/login")
    assert res.status_code == 302
    assert "authkit.test" in res.headers["Location"]
    assert "state=" in res.headers["Location"]
    with client.session_transaction() as sess:
        assert sess.get("oauth_state")


def test_login_preserves_next_param(client, monkeypatch):
    _fake_workos(monkeypatch)
    res = client.get("/auth/login?next=/dashboard/keys")
    assert res.status_code == 302
    with client.session_transaction() as sess:
        assert sess["post_login_next"] == "/dashboard/keys"


def test_login_rejects_external_next(client, monkeypatch):
    _fake_workos(monkeypatch)
    res = client.get("/auth/login?next=https://evil.com/x")
    assert res.status_code == 302
    with client.session_transaction() as sess:
        assert sess["post_login_next"] == "/dashboard"


# --- /auth/callback -----------------------------------------------------------


def test_callback_new_user_creates_org_and_membership(app, client, monkeypatch):
    create_calls = []
    _fake_workos(
        monkeypatch,
        user_id="user_new",
        email="newbie@example.com",
        org_id_claim=None,  # first-time signup
        created_org_id="org_brandnew",
        create_calls=create_calls,
    )

    with client.session_transaction() as sess:
        sess["oauth_state"] = "S"
        sess["post_login_next"] = "/dashboard"

    res = client.get("/auth/callback?code=abc&state=S")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/dashboard")

    assert create_calls == ["newbie's Workspace"]

    with app.app_context():
        user = db.session.query(User).filter_by(workos_user_id="user_new").one()
        org = db.session.query(Org).filter_by(workos_org_id="org_brandnew").one()
        membership = db.session.query(OrgMembership).filter_by(
            user_id=user.id, org_id=org.id
        ).one()
        assert membership.role == "owner"  # first member in the org
        quota = db.session.query(Quota).filter_by(org_id=org.id).one()
        assert quota.calls_remaining == 50

    with client.session_transaction() as sess:
        assert sess["user_id"] == user.id
        assert sess["current_org_id"] == org.id


def test_callback_returning_user_no_duplicate_org(app, client, monkeypatch):
    # First sign-in.
    _fake_workos(monkeypatch, user_id="user_repeat", email="r@example.com",
                  org_id_claim=None, created_org_id="org_repeat")
    with client.session_transaction() as sess:
        sess["oauth_state"] = "S1"
        sess["post_login_next"] = "/dashboard"
    client.get("/auth/callback?code=c&state=S1")

    with app.app_context():
        users_before = db.session.query(User).filter_by(workos_user_id="user_repeat").count()
        orgs_before = db.session.query(Org).filter_by(workos_org_id="org_repeat").count()
        quotas_before = db.session.query(Quota).count()

    # Second sign-in — now the JWT carries org_id (returning user with org).
    _fake_workos(monkeypatch, user_id="user_repeat", email="r@example.com",
                  org_id_claim="org_repeat")
    with client.session_transaction() as sess:
        sess.clear()
        sess["oauth_state"] = "S2"
        sess["post_login_next"] = "/dashboard"
    client.get("/auth/callback?code=c&state=S2")

    with app.app_context():
        assert db.session.query(User).filter_by(workos_user_id="user_repeat").count() == users_before
        assert db.session.query(Org).filter_by(workos_org_id="org_repeat").count() == orgs_before
        assert db.session.query(Quota).count() == quotas_before


def test_callback_state_mismatch_400(client, monkeypatch):
    _fake_workos(monkeypatch)
    with client.session_transaction() as sess:
        sess["oauth_state"] = "EXPECTED"
    res = client.get("/auth/callback?code=c&state=WRONG")
    assert res.status_code == 400


# --- /dashboard ---------------------------------------------------------------


def test_dashboard_without_session_redirects_to_login(client):
    res = client.get("/dashboard")
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]


def test_dashboard_with_session_renders(app, client):
    info = _seed_user_and_org(app, email="dash@example.com",
                                workos_user_id="user_dash", workos_org_id="org_dash")
    with client.session_transaction() as sess:
        sess["user_id"] = info["user_id"]
        sess["current_org_id"] = info["org_id"]
    res = client.get("/dashboard")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "dash@example.com" in body  # member email rendered
    # The key prefix appears in the API keys table
    assert info["raw_key"][:16] in body


# --- Key issue / revoke -------------------------------------------------------


def test_issue_key_owner_succeeds(app, client):
    info = _seed_user_and_org(app, email="o@example.com", workos_user_id="user_o",
                                workos_org_id="org_o", role="owner")
    with client.session_transaction() as sess:
        sess["user_id"] = info["user_id"]
        sess["current_org_id"] = info["org_id"]
    res = client.post("/dashboard/keys/issue", data={"name": "prod"})
    assert res.status_code == 302
    with app.app_context():
        keys = db.session.query(ApiKey).filter_by(org_id=info["org_id"], name="prod").all()
        assert len(keys) == 1


def test_issue_key_rejects_missing_name(app, client):
    """No name provided -> redirect with flash, no key created."""
    info = _seed_user_and_org(app, email="mn@example.com", workos_user_id="user_mn",
                                workos_org_id="org_mn", role="owner")
    with client.session_transaction() as sess:
        sess["user_id"] = info["user_id"]
        sess["current_org_id"] = info["org_id"]
    # Note: info already created one key in _seed_user_and_org; count before.
    with app.app_context():
        before = db.session.query(ApiKey).filter_by(org_id=info["org_id"]).count()
    res = client.post("/dashboard/keys/issue", data={"name": ""})
    assert res.status_code == 302  # redirect back to dashboard with flash
    with app.app_context():
        after = db.session.query(ApiKey).filter_by(org_id=info["org_id"]).count()
        assert after == before  # no new key issued


def test_issue_key_rejects_invalid_chars(app, client):
    """Special chars (emoji, brackets) rejected; no key created."""
    info = _seed_user_and_org(app, email="ic@example.com", workos_user_id="user_ic",
                                workos_org_id="org_ic", role="owner")
    with client.session_transaction() as sess:
        sess["user_id"] = info["user_id"]
        sess["current_org_id"] = info["org_id"]
    with app.app_context():
        before = db.session.query(ApiKey).filter_by(org_id=info["org_id"]).count()
    res = client.post("/dashboard/keys/issue", data={"name": "<script>alert(1)</script>"})
    assert res.status_code == 302
    with app.app_context():
        after = db.session.query(ApiKey).filter_by(org_id=info["org_id"]).count()
        assert after == before


def test_issue_key_member_forbidden(app, client):
    # Need an owner present in the org before adding a member, so the org row exists.
    owner = _seed_user_and_org(app, email="own@example.com", workos_user_id="user_own_1",
                                 workos_org_id="org_member_test", role="owner")
    # Add a second user with role 'member' to the same org.
    with app.app_context():
        member_user = User(workos_user_id="user_member", email="m@example.com")
        db.session.add(member_user)
        db.session.flush()
        db.session.add(OrgMembership(user_id=member_user.id, org_id=owner["org_id"], role="member"))
        db.session.commit()
        member_user_id = member_user.id

    with client.session_transaction() as sess:
        sess["user_id"] = member_user_id
        sess["current_org_id"] = owner["org_id"]
    res = client.post("/dashboard/keys/issue", data={"name": "fail"})
    assert res.status_code == 403


def test_revoke_own_org_key(app, client):
    info = _seed_user_and_org(app, email="rev@example.com", workos_user_id="user_rev",
                                workos_org_id="org_rev")
    with client.session_transaction() as sess:
        sess["user_id"] = info["user_id"]
        sess["current_org_id"] = info["org_id"]
    res = client.post(f"/dashboard/keys/{info['api_key_id']}/revoke")
    assert res.status_code == 302
    with app.app_context():
        key = db.session.get(ApiKey, info["api_key_id"])
        assert key.revoked_at is not None


def test_revoke_cross_tenant_returns_404(app, client):
    # Two distinct orgs.
    org_a = _seed_user_and_org(app, email="a@example.com", workos_user_id="user_a",
                                 workos_org_id="org_aaa")
    org_b = _seed_user_and_org(app, email="b@example.com", workos_user_id="user_b",
                                 workos_org_id="org_bbb")

    # Session as Org A; attempt to revoke Org B's key id.
    with client.session_transaction() as sess:
        sess["user_id"] = org_a["user_id"]
        sess["current_org_id"] = org_a["org_id"]
    res = client.post(f"/dashboard/keys/{org_b['api_key_id']}/revoke")
    assert res.status_code == 404

    with app.app_context():
        # Org B's key untouched.
        key = db.session.get(ApiKey, org_b["api_key_id"])
        assert key.revoked_at is None


# --- Member invite + role -----------------------------------------------------


def test_invite_member_calls_workos_once(app, client, monkeypatch):
    invitation_calls = []
    _fake_workos(monkeypatch, invitation_calls=invitation_calls)
    info = _seed_user_and_org(app, email="inv@example.com", workos_user_id="user_inv",
                                workos_org_id="org_inv")
    with client.session_transaction() as sess:
        sess["user_id"] = info["user_id"]
        sess["current_org_id"] = info["org_id"]
    res = client.post("/dashboard/members/invite", data={"email": "newhire@example.com"})
    assert res.status_code == 302
    assert invitation_calls == [("newhire@example.com", "org_inv")]


def test_update_role_member_forbidden(app, client):
    # Two members of the same org: owner + non-owner.
    owner = _seed_user_and_org(app, email="ow@example.com", workos_user_id="user_ow_x",
                                 workos_org_id="org_role_test", role="owner")
    with app.app_context():
        target_user = User(workos_user_id="user_target", email="t@example.com")
        db.session.add(target_user)
        db.session.flush()
        target_membership = OrgMembership(user_id=target_user.id, org_id=owner["org_id"], role="member")
        db.session.add(target_membership)
        db.session.commit()
        target_user_id = target_user.id
        target_membership_id = target_membership.id

    # Session as the 'member' target — they can't change roles.
    with client.session_transaction() as sess:
        sess["user_id"] = target_user_id
        sess["current_org_id"] = owner["org_id"]
    res = client.post(f"/dashboard/members/{target_membership_id}/role",
                       data={"role": "admin"})
    assert res.status_code == 403


def test_update_role_owner_can_promote_admin(app, client):
    owner = _seed_user_and_org(app, email="op@example.com", workos_user_id="user_op",
                                 workos_org_id="org_promote", role="owner")
    with app.app_context():
        target = User(workos_user_id="user_promote_t", email="tt@example.com")
        db.session.add(target)
        db.session.flush()
        target_mem = OrgMembership(user_id=target.id, org_id=owner["org_id"], role="member")
        db.session.add(target_mem)
        db.session.commit()
        target_mem_id = target_mem.id

    with client.session_transaction() as sess:
        sess["user_id"] = owner["user_id"]
        sess["current_org_id"] = owner["org_id"]

    res = client.post(f"/dashboard/members/{target_mem_id}/role", data={"role": "admin"})
    assert res.status_code == 302
    with app.app_context():
        assert db.session.get(OrgMembership, target_mem_id).role == "admin"


def test_update_role_owner_cannot_set_owner(app, client):
    owner = _seed_user_and_org(app, email="oxx@example.com", workos_user_id="user_oxx",
                                 workos_org_id="org_no_owner_promo", role="owner")
    with app.app_context():
        target = User(workos_user_id="user_block_o", email="b@example.com")
        db.session.add(target)
        db.session.flush()
        target_mem = OrgMembership(user_id=target.id, org_id=owner["org_id"], role="admin")
        db.session.add(target_mem)
        db.session.commit()
        target_mem_id = target_mem.id

    with client.session_transaction() as sess:
        sess["user_id"] = owner["user_id"]
        sess["current_org_id"] = owner["org_id"]

    res = client.post(f"/dashboard/members/{target_mem_id}/role", data={"role": "owner"})
    assert res.status_code == 403


# --- /dashboard/switch-org ----------------------------------------------------


def test_switch_org_to_own_succeeds(app, client):
    a = _seed_user_and_org(app, email="sa@example.com", workos_user_id="user_sa",
                             workos_org_id="org_sa")
    # Same user is in another org too.
    b = _seed_user_and_org(app, email="sa@example.com", workos_user_id="user_sb_ignored",
                             workos_org_id="org_sb")
    with app.app_context():
        # Add Org B membership for user A so they're multi-org.
        db.session.add(OrgMembership(user_id=a["user_id"], org_id=b["org_id"], role="member"))
        db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = a["user_id"]
        sess["current_org_id"] = a["org_id"]
    res = client.get(f"/dashboard/switch-org/{b['org_id']}")
    assert res.status_code == 302
    with client.session_transaction() as sess:
        assert sess["current_org_id"] == b["org_id"]


def test_switch_org_to_non_member_404(app, client):
    a = _seed_user_and_org(app, email="ssa@example.com", workos_user_id="user_ssa",
                             workos_org_id="org_ssa")
    b = _seed_user_and_org(app, email="ssb@example.com", workos_user_id="user_ssb",
                             workos_org_id="org_ssb")
    with client.session_transaction() as sess:
        sess["user_id"] = a["user_id"]
        sess["current_org_id"] = a["org_id"]
    res = client.get(f"/dashboard/switch-org/{b['org_id']}")
    assert res.status_code == 404


# --- /auth/logout -------------------------------------------------------------


def test_logout_clears_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 999
        sess["current_org_id"] = 999
    res = client.get("/auth/logout")
    assert res.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "current_org_id" not in sess


def test_logout_redirects_to_workos_logout_when_session_id_present(client, monkeypatch):
    """When the AuthKit session id was stashed at callback time, /auth/logout
    must redirect to the WorkOS-issued logout URL so AuthKit terminates its
    own cookie too — otherwise the user gets silently re-signed-in next time
    and can't switch accounts. Regression guard for the bug caught 2026-06-07
    while creating the reviewer test account."""
    captured = {}

    def fake_get_logout_url(*, session_id, return_to=None, **_):
        captured["session_id"] = session_id
        captured["return_to"] = return_to
        return f"https://test.authkit.app/sessions/logout?session_id={session_id}"

    stub = SimpleNamespace(
        user_management=SimpleNamespace(get_logout_url=fake_get_logout_url)
    )
    import auth_routes
    monkeypatch.setattr(auth_routes, "_workos", lambda: stub)

    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["current_org_id"] = 1
        sess["workos_session_id"] = "session_abc123"

    res = client.get("/auth/logout")
    assert res.status_code == 302
    assert res.location.startswith("https://test.authkit.app/sessions/logout")
    assert captured["session_id"] == "session_abc123"
    assert captured["return_to"]  # whatever url_root resolves to in tests
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "workos_session_id" not in sess


def test_logout_falls_back_to_local_only_when_workos_call_fails(client, monkeypatch):
    """If WorkOS get_logout_url raises (network blip, SDK shape drift), we
    must still drop the local session and redirect home — never leave the
    user stuck on a Flask 500 with their cookie intact."""
    def boom(*, session_id, return_to=None, **_):
        raise RuntimeError("network down")
    stub = SimpleNamespace(user_management=SimpleNamespace(get_logout_url=boom))
    import auth_routes
    monkeypatch.setattr(auth_routes, "_workos", lambda: stub)

    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["workos_session_id"] = "session_abc"

    res = client.get("/auth/logout")
    assert res.status_code == 302
    assert res.location.endswith("/")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
