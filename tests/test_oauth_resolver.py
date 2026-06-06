# tests/test_oauth_resolver.py
# Pin _resolve_oauth (auth.py) — the OAuth-bearer path through /mcp tools/call
# that Anthropic's reviewer will exercise via claude.ai. The cookie-session
# WorkOS flow is covered by test_auth_routes.py with HS256 stubs; this file
# exercises the RS256 production verification by minting our own RSA keypair
# and stubbing PyJWKClient to hand back our public key.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from db import db
from db.models import Org, OrgMembership, User


_TEST_AUDIENCE = "client_test_audience"
_TEST_ISSUER = "https://test-tenant.authkit.app"


@pytest.fixture(scope="module")
def rsa_keypair():
    """Generate a 2048-bit RSA keypair once per test module.

    Slow enough to be worth caching at module scope (~0.3s on a laptop).
    """
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private.public_key()
    return private_pem, public_key


@pytest.fixture
def oauth_env(monkeypatch):
    monkeypatch.setenv("WORKOS_CLIENT_ID", _TEST_AUDIENCE)
    monkeypatch.setenv("WORKOS_ISSUER", _TEST_ISSUER)
    monkeypatch.setenv("WORKOS_JWKS_URL", "https://test-tenant.authkit.app/.well-known/jwks.json")


@pytest.fixture
def stub_jwks(monkeypatch, rsa_keypair):
    """Make _get_jwks_client().get_signing_key_from_jwt(...) hand back our test key.

    _get_jwks_client is cached as a module-level singleton in auth.py, so we
    swap out the function itself (cleanest) and reset the cache.
    """
    _, public_key = rsa_keypair
    import auth

    class _FakeSigningKey:
        def __init__(self, key):
            self.key = key

    class _FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return _FakeSigningKey(public_key)

    auth._jwks_client = None
    monkeypatch.setattr(auth, "_get_jwks_client", lambda: _FakeJwksClient())
    yield
    auth._jwks_client = None


def _mint_token(rsa_keypair, claims: dict) -> str:
    private_pem, _ = rsa_keypair
    return jwt.encode(claims, private_pem, algorithm="RS256")


def _base_claims(*, workos_org_id="org_workos_A", sub="user_workos_1", email="alice@example.com"):
    now = datetime.now(timezone.utc)
    return {
        "sub": sub,
        "email": email,
        "org_id": workos_org_id,
        "iss": _TEST_ISSUER,
        "aud": _TEST_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }


def _seed_org(app, workos_org_id: str = "org_workos_A", plan: str = "free") -> int:
    """Insert an Org and return its primary-key id. Provisions one alongside it.

    test_resolves_happy_path / cross_tenant tests need a real Org row so
    `_resolve_oauth`'s `Org.query.filter_by(workos_org_id=...)` matches.
    """
    from auth import _period_bounds, _rpm_buckets
    from db.models import Quota

    with app.app_context():
        org = Org(
            name=f"oauth-test-{workos_org_id}-{datetime.now(timezone.utc).timestamp()}",
            workos_org_id=workos_org_id,
            plan=plan,
        )
        db.session.add(org)
        db.session.commit()
        org_id = org.id
        # We don't need a Quota row for _resolve_oauth itself, but seeding one
        # keeps these orgs symmetric with the seeded_org fixture in conftest.
        from auth import PLANS
        period_start, period_end = _period_bounds(datetime.now(timezone.utc))
        plan_limits = PLANS[plan]
        quota = Quota(
            org_id=org_id,
            period_start=period_start,
            period_end=period_end,
            calls_remaining=plan_limits["calls_per_month"],
            calls_limit=plan_limits["calls_per_month"],
        )
        db.session.add(quota)
        db.session.commit()
    _rpm_buckets.pop(org_id, None)
    return org_id


# --- Negative paths: each raise site in _resolve_oauth -------------------------


def test_missing_jwks_url_returns_500_with_actionable_message(app, monkeypatch):
    """auth.py:94 — operator-config failure. Surfaces as 500 so a misconfigured
    deployment is visible in logs; reviewer-visible only if env vars are wrong."""
    from auth import _resolve_oauth, AuthError
    import auth

    monkeypatch.delenv("WORKOS_JWKS_URL", raising=False)
    auth._jwks_client = None

    with app.app_context(), pytest.raises(AuthError) as exc:
        _resolve_oauth("anything")

    assert exc.value.status == 500
    assert "WORKOS_JWKS_URL" in exc.value.message


def test_garbage_token_returns_401_with_actionable_message(app, oauth_env, stub_jwks):
    """Random string isn't a well-formed JWT. Real production path catches this
    at PyJWKClient (auth.py:109 → 'Malformed token'); the stubbed-JWKS test
    path lets it reach jwt.decode which raises InvalidTokenError (auth.py:128
    → 'Invalid token: …'). Either way we MUST return 401, not 500 — and the
    message must name the actual failure, not a generic 'Bad Request'."""
    from auth import _resolve_oauth, AuthError

    with app.app_context(), pytest.raises(AuthError) as exc:
        _resolve_oauth("not-a-jwt-at-all")

    assert exc.value.status == 401
    assert exc.value.message in ("Malformed token",) or exc.value.message.startswith(
        "Invalid token"
    )


def test_expired_token_returns_401(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:126 — exp in the past."""
    from auth import _resolve_oauth, AuthError

    now = datetime.now(timezone.utc)
    expired = _base_claims()
    expired["iat"] = int((now - timedelta(hours=2)).timestamp())
    expired["exp"] = int((now - timedelta(hours=1)).timestamp())
    token = _mint_token(rsa_keypair, expired)

    with app.app_context(), pytest.raises(AuthError) as exc:
        _resolve_oauth(token)

    assert exc.value.status == 401
    assert exc.value.message == "Token expired"


def test_wrong_audience_returns_401(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:128 — replay attempt from a token issued for some other WorkOS app."""
    from auth import _resolve_oauth, AuthError

    claims = _base_claims()
    claims["aud"] = "some_other_clients_audience"
    token = _mint_token(rsa_keypair, claims)

    with app.app_context(), pytest.raises(AuthError) as exc:
        _resolve_oauth(token)

    assert exc.value.status == 401
    assert "Invalid token" in exc.value.message


def test_wrong_issuer_returns_401(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:128 — token issued by a different identity provider."""
    from auth import _resolve_oauth, AuthError

    claims = _base_claims()
    claims["iss"] = "https://evil.example.com/issuer"
    token = _mint_token(rsa_keypair, claims)

    with app.app_context(), pytest.raises(AuthError) as exc:
        _resolve_oauth(token)

    assert exc.value.status == 401
    assert "Invalid token" in exc.value.message


def test_missing_org_id_claim_returns_401(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:132 — the §6.5.B WorkOS JWT-template misconfiguration. Without
    `org_id` (or `organization_id`) in the claims, we can't resolve a tenant."""
    from auth import _resolve_oauth, AuthError

    claims = _base_claims()
    claims.pop("org_id")
    token = _mint_token(rsa_keypair, claims)

    with app.app_context(), pytest.raises(AuthError) as exc:
        _resolve_oauth(token)

    assert exc.value.status == 401
    assert exc.value.message == "Token missing org_id claim"


def test_unprovisioned_org_returns_401(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:136 — claim names a workos_org_id we've never seen locally."""
    from auth import _resolve_oauth, AuthError

    claims = _base_claims(workos_org_id="org_workos_unknown")
    token = _mint_token(rsa_keypair, claims)

    with app.app_context(), pytest.raises(AuthError) as exc:
        _resolve_oauth(token)

    assert exc.value.status == 401
    assert exc.value.message == "Org not provisioned"


# --- Happy path + side-effects -------------------------------------------------


def test_happy_path_returns_oauth_principal(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:170 — well-formed token → Principal(auth_method='oauth')."""
    from auth import _resolve_oauth

    workos_org = "org_workos_happy"
    org_id = _seed_org(app, workos_org_id=workos_org)

    token = _mint_token(rsa_keypair, _base_claims(workos_org_id=workos_org))
    with app.app_context():
        principal = _resolve_oauth(token)

    assert principal.org_id == org_id
    assert principal.auth_method == "oauth"
    assert principal.plan == "free"
    assert principal.api_key_id is None
    assert principal.user_id is not None  # the upsert ran


def test_first_oauth_call_upserts_user_and_membership(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:144-167 — new sub claim creates User + OrgMembership(role='member')
    so Claude Desktop / claude.ai callers populate the membership graph the
    same way browser callers do."""
    from auth import _resolve_oauth

    workos_org = "org_workos_upsert"
    org_id = _seed_org(app, workos_org_id=workos_org)

    workos_sub = "user_workos_brand_new"
    token = _mint_token(
        rsa_keypair,
        _base_claims(workos_org_id=workos_org, sub=workos_sub, email="bob@example.com"),
    )
    with app.app_context():
        _resolve_oauth(token)
        user = db.session.query(User).filter_by(workos_user_id=workos_sub).one()
        assert user.email == "bob@example.com"
        membership = (
            db.session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org_id)
            .one()
        )
        assert membership.role == "member"


def test_returning_user_does_not_duplicate_membership(app, oauth_env, stub_jwks, rsa_keypair):
    """Idempotency: a second OAuth call from the same user shouldn't double-
    insert the membership row. last_seen_at should refresh though."""
    from auth import _resolve_oauth

    workos_org = "org_workos_returning"
    org_id = _seed_org(app, workos_org_id=workos_org)

    workos_sub = "user_workos_returning"
    token = _mint_token(rsa_keypair, _base_claims(workos_org_id=workos_org, sub=workos_sub))
    with app.app_context():
        _resolve_oauth(token)
        _resolve_oauth(token)
        memberships = (
            db.session.query(OrgMembership)
            .join(User)
            .filter(User.workos_user_id == workos_sub, OrgMembership.org_id == org_id)
            .all()
        )
        assert len(memberships) == 1


def test_token_with_organization_id_alias_also_resolves(app, oauth_env, stub_jwks, rsa_keypair):
    """auth.py:131 accepts BOTH `org_id` and `organization_id` because WorkOS
    JWT templates can be configured to use either. Lock the fallback."""
    from auth import _resolve_oauth

    workos_org = "org_workos_alias"
    org_id = _seed_org(app, workos_org_id=workos_org)

    claims = _base_claims(workos_org_id=workos_org)
    claims["organization_id"] = claims.pop("org_id")
    token = _mint_token(rsa_keypair, claims)
    with app.app_context():
        principal = _resolve_oauth(token)
    assert principal.org_id == org_id


def test_oauth_does_not_reassign_existing_membership_across_orgs(
    app, oauth_env, stub_jwks, rsa_keypair
):
    """Tenancy invariant (§3.4): a user who already has a membership in Org A
    must NOT have it silently reassigned if they later sign in via a token
    bound to Org B. They should end up with TWO memberships, not one rewritten
    one. Catches a class of bug where a misdirected token grafts a user into
    the wrong tenant."""
    from auth import _resolve_oauth

    workos_org_a = "org_workos_A_reassign"
    workos_org_b = "org_workos_B_reassign"
    org_a_id = _seed_org(app, workos_org_id=workos_org_a)
    org_b_id = _seed_org(app, workos_org_id=workos_org_b)

    workos_sub = "user_workos_two_orgs"

    # First sign-in: bound to Org A.
    token_a = _mint_token(rsa_keypair, _base_claims(workos_org_id=workos_org_a, sub=workos_sub))
    # Second sign-in: same user, now bound to Org B.
    token_b = _mint_token(rsa_keypair, _base_claims(workos_org_id=workos_org_b, sub=workos_sub))

    with app.app_context():
        p_a = _resolve_oauth(token_a)
        p_b = _resolve_oauth(token_b)
        assert p_a.org_id == org_a_id
        assert p_b.org_id == org_b_id

        memberships = (
            db.session.query(OrgMembership)
            .join(User)
            .filter(User.workos_user_id == workos_sub)
            .all()
        )
        org_ids = {m.org_id for m in memberships}
        assert org_ids == {org_a_id, org_b_id}, (
            "expected both memberships preserved, got "
            f"{org_ids}"
        )
