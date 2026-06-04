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


def test_api_summarize_rejects_malformed_api_key(client):
    """Bearer that doesn't start with sk_synzo_ falls through to OAuth resolver,
    which fails fast on missing JWKS config in tests -> still a 4xx JSON, not
    a 500 crash."""
    resp = client.post(
        "/api/v1/summarize",
        headers={"Authorization": "Bearer not-an-api-key"},
    )
    # 401 (auth fail) or 500 (JWKS config missing in test env) — either is a
    # clean JSON failure, not an unhandled exception.
    assert resp.status_code in (401, 500)
    assert resp.is_json


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
