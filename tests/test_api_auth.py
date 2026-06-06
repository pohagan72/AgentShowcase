# tests/test_api_auth.py
# Smoke tests for the new JSON API surface + @require_auth wiring.
# Full auth-flow tests (issue key -> seed quota -> call endpoint -> assert
# 200 / 402 / 413 / 429 / refund) land later when we have a fixture that
# creates DB rows. For now we verify the endpoint exists and rejects
# unauthenticated calls with the JSON 401 shape the MCP layer will expect.


def test_api_summarize_requires_auth(client):
    """No Authorization header -> JSON 401 with {error: ...}."""
    resp = client.post("/api/v1/summarize")
    assert resp.status_code == 401
    assert resp.is_json
    assert "error" in resp.get_json()


def test_api_summarize_rejects_malformed_oauth_bearer_when_jwks_configured(
    client, monkeypatch
):
    """A non-sk_ bearer routes to _resolve_oauth. With JWKS config present
    (the real production state), garbage tokens must 401 with a clean JSON
    body — NOT 500. Policy 5.A: error messages must be actionable, and a
    500 with no message is the failure mode reviewers fail us for.

    The OAuth resolver suite (test_oauth_resolver.py) covers the per-claim
    raise sites in detail; here we're proving the HTTP boundary returns 401
    for the most common reviewer case (a wrong token while config is sane)."""
    # Provide JWKS URL so we hit the rejection path, not the config-missing path.
    monkeypatch.setenv(
        "WORKOS_JWKS_URL",
        "https://test-tenant.authkit.app/.well-known/jwks.json",
    )
    monkeypatch.setenv("WORKOS_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("WORKOS_ISSUER", "https://test-tenant.authkit.app")

    # Stub _get_jwks_client so the resolver doesn't hit the network. The
    # token itself is garbage; we want the resolver to surface 401, not 500.
    import auth

    class _FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            # Real PyJWKClient raises DecodeError on a non-JWT string here.
            # That maps to auth.py:109 -> AuthError(401, "Malformed token").
            import jwt
            raise jwt.DecodeError("Not enough segments")

    auth._jwks_client = None
    monkeypatch.setattr(auth, "_get_jwks_client", lambda: _FakeJwksClient())

    resp = client.post(
        "/api/v1/summarize",
        headers={"Authorization": "Bearer not-an-api-key"},
    )
    assert resp.status_code == 401, resp.get_json()
    assert resp.is_json
    body = resp.get_json()
    assert "error" in body
    # Actionable message — names the failure (Malformed token), not a generic
    # "Bad Request" / "Internal Server Error". Policy 5.A.
    assert "Malformed" in body["error"] or "Invalid" in body["error"]


def test_api_summarize_returns_500_when_jwks_env_unset_for_operator_visibility(
    client, monkeypatch
):
    """[auth.py:94] OAuth path with WORKOS_JWKS_URL unset is an OPERATOR
    CONFIG FAILURE, not a user-input failure. The correct response is 500 so
    it lights up in logs / monitoring — a 401 here would silently hide a
    misdeploy. Reviewer-facing surface (claude.ai) never hits this branch
    because the deploy guards on the env var at startup time.

    Pinning this so a future 'tighten everything to 401' refactor doesn't
    accidentally mask operator misconfiguration."""
    monkeypatch.delenv("WORKOS_JWKS_URL", raising=False)

    # Force the cached client to be rebuilt with the (now-missing) env var.
    import auth
    auth._jwks_client = None

    resp = client.post(
        "/api/v1/summarize",
        headers={"Authorization": "Bearer not-an-api-key"},
    )
    assert resp.status_code == 500
    assert resp.is_json
    body = resp.get_json()
    # The message must name the missing env var so an operator can fix it.
    assert "WORKOS_JWKS_URL" in body["error"]


def test_api_summarize_rejects_bogus_api_key(client):
    """sk_synzo_ prefix but no matching row -> 401 from _resolve_api_key."""
    resp = client.post(
        "/api/v1/summarize",
        headers={"Authorization": "Bearer sk_synzo_definitely_not_real_xxxxxxxxxxxxxxxxxxxxxx"},
    )
    assert resp.status_code == 401
    assert resp.is_json
    assert "error" in resp.get_json()


def test_api_blueprint_is_registered(app):
    """The /api/v1/summarize rule exists with the api_routes blueprint."""
    rules = [str(r) for r in app.url_map.iter_rules()]
    assert "/api/v1/summarize" in rules
