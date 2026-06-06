# tests/test_mcp_server.py
# Coverage for the MCP (Model Context Protocol) endpoint at /mcp.
# These tests exercise the Streamable HTTP transport's JSON-RPC envelope: the
# initialize handshake, tools/list, and tools/call. The summarize_document
# tool's Gemini call is monkeypatched so tests stay offline; what we're
# actually testing here is the JSON-RPC plumbing, the auth bridge, and the
# tenancy invariant (every metered call lands in the caller's org's
# usage_events, never the other org's).
#
# Spec: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from db import db
from db.models import ApiKey, Org, OrgMembership, Quota, UsageEvent, User


# --- Fixtures ------------------------------------------------------------------


def _seed_org(app, *, name, plan="free"):
    """Org + user + owner membership + quota + API key. Mirrors the helper in
    test_multi_tenant_isolation.py so the isolation test below uses the same
    seeding shape the rest of the suite already trusts."""
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
            "auth_header": {"Authorization": f"Bearer {raw_key}"},
        }


def _rpc(client, method, params=None, *, request_id=1, headers=None):
    """POST one JSON-RPC request to /mcp and return the parsed response.

    We pass force=True semantics by always sending application/json.
    """
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(
        "/mcp",
        data=json.dumps(body),
        headers={"Content-Type": "application/json", **(headers or {})},
    )


@pytest.fixture
def fake_gemini(monkeypatch, app):
    """Stub the summarization pipeline so tests don't call Gemini.

    - read_text_from_file: returns canned text + filename.
    - stream_analysis: yields a meta event + one chunk + EOF.
    - GEMINI_CONFIGURED: forced True so the handler doesn't 503.
    """
    app.config["GEMINI_CONFIGURED"] = True

    from features.summarization import utils as summarization_utils
    from features.summarization.agents import analyst_agent

    def fake_read(file_storage):
        return "extracted text from " + file_storage.filename, file_storage.filename

    def fake_stream(text, model_name, filename):
        yield json.dumps({"type": "meta", "classification": "TestDoc"})
        yield json.dumps({"type": "chunk", "content": "stub summary line 1\n"})
        yield json.dumps({"type": "chunk", "content": "stub summary line 2"})

    monkeypatch.setattr(summarization_utils, "read_text_from_file", fake_read)
    monkeypatch.setattr(analyst_agent, "stream_analysis", fake_stream)


# --- initialize / capabilities -------------------------------------------------


def test_initialize_handshake_returns_server_info_and_tool_capability(client):
    """initialize is the first call; no auth required. Verify the protocol
    version echo, the tools capability declaration, and the serverInfo shape."""
    resp = _rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})

    assert resp.status_code == 200
    assert resp.is_json
    body = resp.get_json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    result = body["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"]["tools"]["listChanged"] is False
    assert result["serverInfo"]["name"] == "synzo"


def test_initialize_falls_back_to_preferred_version_when_client_requests_unknown(client):
    """If the client requests a version we don't speak, we offer ours."""
    resp = _rpc(client, "initialize", {"protocolVersion": "2099-99-99", "capabilities": {}})
    assert resp.status_code == 200
    assert resp.get_json()["result"]["protocolVersion"] == "2025-06-18"


def test_initialized_notification_returns_202_with_no_body(client):
    """notifications/* have no id field, so the spec requires 202 Accepted."""
    resp = client.post(
        "/mcp",
        data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 202
    assert resp.data == b""


def test_ping_returns_empty_object(client):
    resp = _rpc(client, "ping")
    assert resp.status_code == 200
    assert resp.get_json()["result"] == {}


# --- tools/list ---------------------------------------------------------------


def test_tools_list_advertises_summarize_document_with_schema_and_annotations(client):
    """Phase 2 vertical slice: only summarize_document is registered.
    Verify the entry has the fields MCP clients (Claude Desktop, Inspector)
    expect: name, description, inputSchema, annotations."""
    resp = _rpc(client, "tools/list")
    assert resp.status_code == 200
    tools = resp.get_json()["result"]["tools"]

    by_name = {t["name"]: t for t in tools}
    assert "summarize_document" in by_name
    tool = by_name["summarize_document"]
    assert "description" in tool and tool["description"]
    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"filename", "content_base64"}
    ann = tool["annotations"]
    assert ann["destructiveHint"] is False
    assert ann["idempotentHint"] is True


# --- tools/call: auth gating --------------------------------------------------


def test_tools_call_without_auth_returns_401_with_www_authenticate(client, fake_gemini):
    """No Authorization header on tools/call -> HTTP 401 + WWW-Authenticate.

    Per MCP authorization spec (2025-06-18 §2.1) and RFC 9728, the resource
    server MUST return 401 with a WWW-Authenticate header pointing at the
    protected-resource-metadata URL. Without 401, MCP clients (notably
    claude.ai) don't know to start OAuth — they render the JSON-RPC error
    body as a tool failure instead. The JSON-RPC envelope still carries our
    private -32001 code so non-spec callers can branch on it too.
    """
    resp = _rpc(client, "tools/call", {
        "name": "summarize_document",
        "arguments": {
            "filename": "x.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.4 fake").decode(),
        },
    })
    # HTTP 401 — the spec-required transport-level signal.
    assert resp.status_code == 401

    # WWW-Authenticate must be present, identify Bearer, and carry the
    # resource_metadata URL pointer that lets the client discover our auth
    # server.
    www_auth = resp.headers.get("WWW-Authenticate", "")
    assert www_auth.startswith("Bearer "), www_auth
    assert "resource_metadata=" in www_auth
    assert "/.well-known/oauth-protected-resource" in www_auth

    # JSON-RPC envelope still parses; -32001 is our private code for the
    # same condition so non-browser clients can branch on it.
    body = resp.get_json()
    assert "error" in body
    assert body["error"]["code"] == -32001  # MCP_AUTH_REQUIRED


def test_tools_call_without_auth_exposes_www_authenticate_via_cors(client, fake_gemini):
    """Browser clients (claude.ai) only see WWW-Authenticate on cross-origin
    responses if the server lists it under Access-Control-Expose-Headers.
    Pin this so future CORS edits don't silently break the OAuth bootstrap."""
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "x.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4 fake").decode(),
            },
        },
        headers={"Origin": "https://claude.ai"},
    )
    assert resp.status_code == 401
    exposed = resp.headers.get("Access-Control-Expose-Headers", "")
    assert "WWW-Authenticate" in exposed, exposed


def test_tools_call_unknown_tool_returns_method_not_found(client, app, fake_gemini):
    org = _seed_org(app, name="mcp_unknown")
    resp = _rpc(
        client,
        "tools/call",
        {"name": "does_not_exist", "arguments": {}},
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert "error" in body
    assert body["error"]["code"] == -32601  # JSONRPC_METHOD_NOT_FOUND


# --- tools/call: happy path ---------------------------------------------------


def test_tools_call_summarize_document_returns_structured_content_and_meters(
    client, app, fake_gemini
):
    """End-to-end MCP slice: API key -> Principal -> run_metered_tool ->
    summarize handler -> structuredContent + usage_events row."""
    org = _seed_org(app, name="mcp_happy")

    raw_pdf = b"%PDF-1.4 fake content"
    args = {
        "filename": "test.pdf",
        "content_base64": base64.b64encode(raw_pdf).decode(),
    }

    resp = _rpc(
        client,
        "tools/call",
        {"name": "summarize_document", "arguments": args},
        headers=org["auth_header"],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "error" not in body, body
    result = body["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["classification"] == "TestDoc"
    assert "stub summary line 1" in result["structuredContent"]["summary"]
    # Also has the legacy text-block fallback so older clients can read it.
    assert any(block["type"] == "text" for block in result["content"])

    # Metering: one usage_events row, status=ok, for our org only.
    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        assert len(events) == 1
        assert events[0].status == "ok"
        assert events[0].tool == "summarize_document"
        assert events[0].auth_method == "api_key"


def test_tools_call_invalid_base64_returns_isError_not_jsonrpc_error(
    client, app, fake_gemini
):
    """A ToolError (argument failure) surfaces through isError=true so the
    model can recover. The call STILL goes through the metering pipeline:
    quota is decremented, then the tool handler raises ToolError, then
    run_metered_tool refunds and meters as 'refunded'."""
    org = _seed_org(app, name="mcp_bad_b64")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "x.pdf",
                "content_base64": "!!!not base64!!!",
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert "error" not in body
    assert body["result"]["isError"] is True
    assert "base64" in body["result"]["content"][0]["text"].lower()

    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        # quota_exhausted/etc. pre-handler checks pass; handler raises ToolError;
        # refund-on-exception path runs; row recorded as 'refunded'.
        statuses = sorted(e.status for e in events)
        assert "refunded" in statuses


def test_tools_call_unsupported_extension_returns_isError(client, app, fake_gemini):
    org = _seed_org(app, name="mcp_bad_ext")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "secrets.exe",
                "content_base64": base64.b64encode(b"x").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "unsupported" in body["result"]["content"][0]["text"].lower()


# --- tools/call: tenancy invariant --------------------------------------------


def test_mcp_tools_call_records_usage_against_caller_org_only(client, app, fake_gemini):
    """The non-negotiable from Phase 1.5 (s3.4): every metered call lands in
    the caller's org's usage_events, never the other org's. If this test
    ever flips, multi-tenancy is broken at the MCP layer."""
    a = _seed_org(app, name="mcp_iso_a")
    b = _seed_org(app, name="mcp_iso_b")

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "a.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4 a").decode(),
            },
        },
        headers=a["auth_header"],
    )
    assert resp.status_code == 200
    assert resp.get_json()["result"]["isError"] is False

    with app.app_context():
        a_events = db.session.query(UsageEvent).filter_by(org_id=a["org_id"]).all()
        b_events = db.session.query(UsageEvent).filter_by(org_id=b["org_id"]).all()
        assert len(a_events) == 1
        assert a_events[0].tool == "summarize_document"
        assert b_events == []


# --- Transport-level error paths ----------------------------------------------


def test_invalid_json_body_returns_parse_error(client):
    resp = client.post(
        "/mcp",
        data="this is not json",
        headers={"Content-Type": "application/json"},
    )
    body = resp.get_json()
    assert body["error"]["code"] == -32700  # JSONRPC_PARSE_ERROR


def test_disallowed_origin_returns_403(client):
    """DNS rebinding mitigation: a browser-originated request from a non-
    allowlisted origin is rejected before any tool can run."""
    resp = client.post(
        "/mcp",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        headers={"Content-Type": "application/json", "Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_allowed_origin_passes_through(client):
    resp = client.post(
        "/mcp",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        headers={"Content-Type": "application/json", "Origin": "https://claude.ai"},
    )
    assert resp.status_code == 200
    assert "tools" in resp.get_json()["result"]
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://claude.ai"


def test_options_preflight_returns_cors_headers(client):
    resp = client.options(
        "/mcp",
        headers={
            "Origin": "https://claude.ai",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert resp.status_code == 204
    assert resp.headers["Access-Control-Allow-Origin"] == "https://claude.ai"
    assert "POST" in resp.headers["Access-Control-Allow-Methods"]


def test_get_on_mcp_returns_405(client):
    """We don't implement server-initiated SSE streams; GET is 405.

    Also pin the Allow header (gap #8 from the test-suite review): per HTTP
    spec, a 405 response MUST include Allow listing the methods that are
    permitted. Without this, MCP clients that try a wrong method get a 405
    but can't discover what they should have used.
    """
    resp = client.get("/mcp")
    assert resp.status_code == 405
    allow = resp.headers.get("Allow", "")
    assert "POST" in allow
    assert "OPTIONS" in allow


def test_delete_on_mcp_returns_405_with_allow(client):
    """DELETE also 405s — no session termination in v1. Same Allow header
    invariant as GET."""
    resp = client.delete("/mcp")
    assert resp.status_code == 405
    allow = resp.headers.get("Allow", "")
    assert "POST" in allow
    assert "OPTIONS" in allow


# --- /.well-known/oauth-protected-resource ------------------------------------


def test_oauth_protected_resource_points_at_our_own_authorization_server(
    client, monkeypatch
):
    """The RFC 9728 resource doc must advertise OUR /.well-known/oauth-authorization-server,
    not WorkOS's directly.

    Reason (see oauth_authorization_server() in mcp_routes.py): WorkOS doesn't
    advertise its DCR endpoint in its own discovery doc, so MCP clients
    abandon the OAuth bootstrap. We host an augmented discovery doc and
    point clients at it instead.
    """
    monkeypatch.setenv(
        "WORKOS_ISSUER", "https://test-tenant.authkit.app",
    )
    monkeypatch.setenv("SYNZO_PUBLIC_URL", "https://www.synzo.ai")

    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["resource"] == "https://www.synzo.ai"
    # NOT the WORKOS_ISSUER — we advertise OURSELVES as the discoverable
    # authorization server so we can serve an augmented metadata doc.
    assert body["authorization_servers"] == ["https://www.synzo.ai"]
    assert "header" in body["bearer_methods_supported"]


# --- /.well-known/oauth-authorization-server (the augmented discovery doc) ----


def _stub_authkit_metadata(monkeypatch, doc: dict | None = None) -> None:
    """Patch the AuthKit metadata fetch so tests don't hit the network."""
    import mcp_routes

    # Clear any previously-cached metadata from earlier tests in this process.
    mcp_routes._AUTH_SERVER_METADATA_CACHE = None
    if doc is None:
        doc = {
            "issuer": "https://test-tenant.authkit.app",
            "authorization_endpoint": "https://test-tenant.authkit.app/oauth2/authorize",
            "token_endpoint": "https://test-tenant.authkit.app/oauth2/token",
            "jwks_uri": "https://test-tenant.authkit.app/oauth2/jwks",
            "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "response_types_supported": ["code"],
            "scopes_supported": ["openid", "profile", "email", "offline_access"],
            "token_endpoint_auth_methods_supported": [
                "none",
                "client_secret_basic",
                "client_secret_post",
            ],
        }
    monkeypatch.setattr(mcp_routes, "_fetch_authkit_metadata", lambda: doc)


def test_oauth_authorization_server_injects_registration_endpoint(client, monkeypatch):
    """The whole point of this endpoint: claude.ai needs `registration_endpoint`
    in the discovery doc to perform Dynamic Client Registration. WorkOS doesn't
    expose it; we inject it. Without this, OAuth never starts."""
    monkeypatch.setenv("WORKOS_ISSUER", "https://test-tenant.authkit.app")
    _stub_authkit_metadata(monkeypatch)

    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["registration_endpoint"] == (
        "https://test-tenant.authkit.app/oauth2/register"
    )
    # Issuer must match WORKOS_ISSUER — we don't blindly echo upstream, so
    # an upstream rename can't break audience checks in _resolve_oauth.
    assert body["issuer"] == "https://test-tenant.authkit.app"


def test_oauth_authorization_server_preserves_upstream_endpoints(client, monkeypatch):
    """We proxy WorkOS's endpoints unchanged so authorization / token / JWKS
    URLs route to AuthKit. The injection only adds; it doesn't replace."""
    monkeypatch.setenv("WORKOS_ISSUER", "https://test-tenant.authkit.app")
    _stub_authkit_metadata(monkeypatch)

    resp = client.get("/.well-known/oauth-authorization-server")
    body = resp.get_json()
    assert body["authorization_endpoint"] == (
        "https://test-tenant.authkit.app/oauth2/authorize"
    )
    assert body["token_endpoint"] == "https://test-tenant.authkit.app/oauth2/token"
    assert body["jwks_uri"] == "https://test-tenant.authkit.app/oauth2/jwks"
    assert "S256" in body["code_challenge_methods_supported"]


def test_oauth_authorization_server_503_when_upstream_unreachable(client, monkeypatch):
    """If we can't reach WorkOS, return 503 rather than serving an incomplete
    doc. Lets the client surface a real error instead of silently dying mid-
    OAuth."""
    monkeypatch.setenv("WORKOS_ISSUER", "https://test-tenant.authkit.app")
    _stub_authkit_metadata(monkeypatch, doc={})  # empty -> treated as fetch failure

    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 503


# --- tools/list now advertises all five Phase 2 tools -------------------------


def test_tools_list_advertises_all_phase2_tools(client):
    """All five Phase 2 tools must show up in tools/list with annotations.
    transcribe_audio is intentionally NOT shipped in Phase 2 — its underlying
    pipeline is a stub. If you're re-adding it, also update this list."""
    resp = _rpc(client, "tools/list")
    assert resp.status_code == 200
    tools = resp.get_json()["result"]["tools"]
    names = {t["name"] for t in tools}
    expected = {
        "summarize_document",
        "translate_document",
        "redact_pii",
        "analyze_image",
        "detect_faces",
    }
    assert expected.issubset(names), f"Missing tools: {expected - names}"
    # Every tool must declare destructiveHint=false (we never destroy state).
    for tool in tools:
        ann = tool.get("annotations") or {}
        assert ann.get("destructiveHint") is False, tool["name"]


# --- translate_document -------------------------------------------------------


@pytest.fixture
def fake_translate(monkeypatch, app):
    """Stub the Gemini call so translate_document tests stay offline."""
    app.config["GEMINI_CONFIGURED"] = True

    from features.summarization import utils as summarization_utils
    from features.translation import routes as translation_routes

    monkeypatch.setattr(
        summarization_utils, "extract_text_from_stream",
        lambda stream, ext: "Hello world. This is the source text.",
    )

    def fake_translate_util(text, target_lang, model_name):
        return ("success", f"[{target_lang}] {text}", None)

    monkeypatch.setattr(translation_routes, "translate_text_util", fake_translate_util)


def test_tools_call_translate_document_returns_translated_text(
    client, app, fake_translate
):
    org = _seed_org(app, name="mcp_translate_ok")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "translate_document",
            "arguments": {
                "filename": "memo.docx",
                "content_base64": base64.b64encode(b"PK fake docx").decode(),
                "target_language": "Spanish",
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert "error" not in body, body
    result = body["result"]
    assert result["isError"] is False
    sc = result["structuredContent"]
    assert sc["target_language"] == "Spanish"
    assert sc["filename"] == "memo.docx"
    assert "[Spanish]" in sc["translated_text"]

    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        assert len(events) == 1
        assert events[0].status == "ok"
        assert events[0].tool == "translate_document"


def test_translate_document_blocked_by_safety_filter_returns_isError(
    client, app, monkeypatch
):
    """If translate_text_util returns 'blocked', the tool surfaces it as a
    ToolError so the model can react, with the quota refunded."""
    app.config["GEMINI_CONFIGURED"] = True
    from features.summarization import utils as summarization_utils
    from features.translation import routes as translation_routes

    monkeypatch.setattr(
        summarization_utils, "extract_text_from_stream",
        lambda stream, ext: "some text",
    )
    monkeypatch.setattr(
        translation_routes, "translate_text_util",
        lambda text, lang, model: ("blocked", text, "blocked by safety filter"),
    )

    org = _seed_org(app, name="mcp_translate_blocked")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "translate_document",
            "arguments": {
                "filename": "memo.docx",
                "content_base64": base64.b64encode(b"PK fake").decode(),
                "target_language": "French",
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "safety" in body["result"]["content"][0]["text"].lower()

    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        statuses = sorted(e.status for e in events)
        assert "refunded" in statuses


def test_translate_document_unsupported_extension_returns_isError(
    client, app, fake_translate
):
    """PDFs aren't a supported source for translate (the HTMX route only does
    docx/pptx/xlsx). Make sure we don't accidentally accept them."""
    org = _seed_org(app, name="mcp_translate_bad_ext")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "translate_document",
            "arguments": {
                "filename": "doc.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4").decode(),
                "target_language": "Spanish",
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "unsupported" in body["result"]["content"][0]["text"].lower()


# --- redact_pii ---------------------------------------------------------------


@pytest.fixture
def fake_redact(monkeypatch, app):
    """Stub Presidio + the docx redactor so tests don't need spaCy installed."""
    import io as _io

    app.config["PRESIDIO_ANALYZER_AVAILABLE"] = True
    app.presidio_analyzer = object()  # sentinel; the stub doesn't call it

    from features.pii_redaction import routes as pii_routes

    def fake_word_redact(stream, analyzer):
        # Pretend we redacted; return a small distinct byte payload so tests
        # can spot it round-trip out via base64.
        return _io.BytesIO(b"REDACTED-DOCX-BYTES")

    def fake_pptx_redact(stream, analyzer):
        return _io.BytesIO(b"REDACTED-PPTX-BYTES")

    monkeypatch.setattr(pii_routes, "redact_word_document_pii", fake_word_redact)
    monkeypatch.setattr(pii_routes, "redact_powerpoint_document_pii", fake_pptx_redact)


def test_tools_call_redact_pii_returns_base64_redacted_document(
    client, app, fake_redact
):
    org = _seed_org(app, name="mcp_redact_ok")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "redact_pii",
            "arguments": {
                "filename": "contract.docx",
                "content_base64": base64.b64encode(b"PK original docx").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert "error" not in body, body
    result = body["result"]
    assert result["isError"] is False
    sc = result["structuredContent"]
    assert sc["filename"] == "redacted_contract.docx"
    # Round-trip the base64 and confirm the stub's output payload made it back.
    assert base64.b64decode(sc["content_base64"]) == b"REDACTED-DOCX-BYTES"
    assert "wordprocessingml" in sc["mimetype"]
    assert sc["original_size_bytes"] > 0
    assert sc["redacted_size_bytes"] > 0


def test_redact_pii_pptx_uses_pptx_pipeline(client, app, fake_redact):
    org = _seed_org(app, name="mcp_redact_pptx")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "redact_pii",
            "arguments": {
                "filename": "deck.pptx",
                "content_base64": base64.b64encode(b"PK pptx").decode(),
            },
        },
        headers=org["auth_header"],
    )
    sc = resp.get_json()["result"]["structuredContent"]
    assert base64.b64decode(sc["content_base64"]) == b"REDACTED-PPTX-BYTES"
    assert "presentationml" in sc["mimetype"]


def test_redact_pii_unsupported_extension_returns_isError(client, app, fake_redact):
    org = _seed_org(app, name="mcp_redact_bad_ext")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "redact_pii",
            "arguments": {
                "filename": "doc.pdf",
                "content_base64": base64.b64encode(b"%PDF").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "unsupported" in body["result"]["content"][0]["text"].lower()


def test_redact_pii_when_presidio_unavailable_refunds_quota(client, app, monkeypatch):
    """If Presidio isn't configured the handler raises RuntimeError; the MCP
    layer should refund the quota and surface isError=true to the model."""
    app.config["PRESIDIO_ANALYZER_AVAILABLE"] = False
    monkeypatch.setattr(app, "presidio_analyzer", None, raising=False)

    org = _seed_org(app, name="mcp_redact_no_presidio")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "redact_pii",
            "arguments": {
                "filename": "doc.docx",
                "content_base64": base64.b64encode(b"PK").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True

    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        statuses = sorted(e.status for e in events)
        assert "refunded" in statuses


# --- analyze_image ------------------------------------------------------------


@pytest.fixture
def fake_analyze_image(monkeypatch, app):
    """Stub the Gemini vision call + PIL normalization."""
    app.config["GEMINI_CONFIGURED"] = True

    from features.multimedia import routes as multimedia_routes
    from features.multimedia import analytics_utils

    monkeypatch.setattr(
        multimedia_routes, "normalize_and_resize_image",
        lambda data: data,
    )

    fake_analysis = {
        "description": "A test image.",
        "rich_description": "A short, fake description for a unit test.",
        "extracted_text": "",
        "safety_flags": {
            "contains_people": False,
            "contains_potential_pii": False,
            "is_graphic_or_violent": False,
        },
        "detected_objects": ["test", "image"],
    }
    monkeypatch.setattr(
        analytics_utils, "analyze_image_with_gemini",
        lambda image_bytes, model: fake_analysis,
    )
    monkeypatch.setattr(
        analytics_utils, "extract_dominant_colors",
        lambda image_bytes, num_colors=5: ["#aabbcc", "#112233"],
    )

    # Avoid instantiating a real Gemini model.
    import google.generativeai as genai
    monkeypatch.setattr(genai, "GenerativeModel", lambda name: object())


def test_tools_call_analyze_image_returns_structured_analysis(
    client, app, fake_analyze_image
):
    org = _seed_org(app, name="mcp_analyze_ok")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "analyze_image",
            "arguments": {
                "filename": "photo.jpg",
                "content_base64": base64.b64encode(b"\xff\xd8\xff\xe0 fake").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert "error" not in body, body
    sc = body["result"]["structuredContent"]
    assert sc["filename"] == "photo.jpg"
    assert sc["analysis"]["description"] == "A test image."
    assert sc["dominant_colors"] == ["#aabbcc", "#112233"]


def test_analyze_image_unsupported_extension_returns_isError(
    client, app, fake_analyze_image
):
    org = _seed_org(app, name="mcp_analyze_bad_ext")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "analyze_image",
            "arguments": {
                "filename": "doc.pdf",
                "content_base64": base64.b64encode(b"%PDF").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "unsupported" in body["result"]["content"][0]["text"].lower()


def test_analyze_image_when_model_returns_error_dict_returns_isError(
    client, app, monkeypatch
):
    """analytics_utils encodes some failures as {"error": "..."}. The MCP
    handler should surface those as isError=true (not a JSON-RPC error)."""
    app.config["GEMINI_CONFIGURED"] = True
    from features.multimedia import routes as multimedia_routes
    from features.multimedia import analytics_utils

    monkeypatch.setattr(multimedia_routes, "normalize_and_resize_image", lambda d: d)
    monkeypatch.setattr(
        analytics_utils, "analyze_image_with_gemini",
        lambda image_bytes, model: {"error": "AI model returned an invalid format."},
    )
    monkeypatch.setattr(analytics_utils, "extract_dominant_colors", lambda d, num_colors=5: [])
    import google.generativeai as genai
    monkeypatch.setattr(genai, "GenerativeModel", lambda name: object())

    org = _seed_org(app, name="mcp_analyze_model_err")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "analyze_image",
            "arguments": {
                "filename": "photo.png",
                "content_base64": base64.b64encode(b"\x89PNG fake").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "invalid format" in body["result"]["content"][0]["text"].lower()


# --- detect_faces -------------------------------------------------------------


@pytest.fixture
def fake_detect_faces(monkeypatch, app):
    """Stub MTCNN + OpenCV so the test doesn't pull TensorFlow into RAM."""
    from features.multimedia import routes as multimedia_routes
    from features.multimedia import blur_utils

    monkeypatch.setattr(multimedia_routes, "normalize_and_resize_image", lambda d: d)
    # Return a recognizable PNG-ish byte payload.
    monkeypatch.setattr(
        blur_utils, "blur_image_opencv",
        lambda image_bytes, blur_size: b"\x89PNG\r\n\x1a\nFAKE-PNG-" + str(blur_size).encode(),
    )


def test_tools_call_detect_faces_default_blur_returns_png(
    client, app, fake_detect_faces
):
    org = _seed_org(app, name="mcp_faces_ok")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "detect_faces",
            "arguments": {
                "filename": "group.jpg",
                "content_base64": base64.b64encode(b"\xff\xd8\xff\xe0").decode(),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert "error" not in body, body
    sc = body["result"]["structuredContent"]
    assert sc["filename"] == "group-faces-blurred.png"
    assert sc["mode"] == "blur"
    assert sc["mimetype"] == "image/png"
    out = base64.b64decode(sc["content_base64"])
    # blur_strength default = 2 -> blur_size=151
    assert b"FAKE-PNG-151" in out


def test_detect_faces_redact_mode_uses_opaque_rect(client, app, fake_detect_faces):
    org = _seed_org(app, name="mcp_faces_redact")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "detect_faces",
            "arguments": {
                "filename": "group.jpg",
                "content_base64": base64.b64encode(b"\xff\xd8").decode(),
                "mode": "redact",
            },
        },
        headers=org["auth_header"],
    )
    sc = resp.get_json()["result"]["structuredContent"]
    assert sc["mode"] == "redact"
    assert sc["filename"] == "group-faces-redacted.png"
    # blur_size=-1 is the redaction sentinel.
    out = base64.b64decode(sc["content_base64"])
    assert b"FAKE-PNG--1" in out


def test_detect_faces_invalid_mode_returns_isError(client, app, fake_detect_faces):
    org = _seed_org(app, name="mcp_faces_bad_mode")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "detect_faces",
            "arguments": {
                "filename": "x.jpg",
                "content_base64": base64.b64encode(b"\xff\xd8").decode(),
                "mode": "annihilate",
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "mode" in body["result"]["content"][0]["text"].lower()


def test_detect_faces_invalid_blur_strength_returns_isError(
    client, app, fake_detect_faces
):
    org = _seed_org(app, name="mcp_faces_bad_strength")
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "detect_faces",
            "arguments": {
                "filename": "x.jpg",
                "content_base64": base64.b64encode(b"\xff\xd8").decode(),
                "blur_strength": 9,
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True


# --- Cross-tenant isolation across the new tools ------------------------------


def test_mcp_new_tools_record_usage_against_caller_org_only(
    client, app, fake_translate, fake_redact, fake_analyze_image, fake_detect_faces
):
    """The Phase 1.5 non-negotiable extends to every new tool: a call from
    Org A must never write a usage_events row against Org B. This test runs
    one call of each tool from Org A and asserts Org B sees nothing."""
    a = _seed_org(app, name="mcp_iso_new_a")
    b = _seed_org(app, name="mcp_iso_new_b")

    calls = [
        ("translate_document", {
            "filename": "memo.docx",
            "content_base64": base64.b64encode(b"PK").decode(),
            "target_language": "Spanish",
        }),
        ("redact_pii", {
            "filename": "memo.docx",
            "content_base64": base64.b64encode(b"PK").decode(),
        }),
        ("analyze_image", {
            "filename": "p.jpg",
            "content_base64": base64.b64encode(b"\xff\xd8").decode(),
        }),
        ("detect_faces", {
            "filename": "p.jpg",
            "content_base64": base64.b64encode(b"\xff\xd8").decode(),
        }),
    ]

    for tool_name, args in calls:
        resp = _rpc(
            client,
            "tools/call",
            {"name": tool_name, "arguments": args},
            headers=a["auth_header"],
        )
        assert resp.status_code == 200, (tool_name, resp.get_json())
        assert resp.get_json()["result"]["isError"] is False, (
            tool_name,
            resp.get_json(),
        )

    with app.app_context():
        a_events = db.session.query(UsageEvent).filter_by(org_id=a["org_id"]).all()
        b_events = db.session.query(UsageEvent).filter_by(org_id=b["org_id"]).all()
        tools_recorded = sorted(e.tool for e in a_events)
        assert tools_recorded == sorted(c[0] for c in calls)
        assert b_events == []


# --- OAuth bearer path through /mcp tools/call --------------------------------
#
# The cookie-session OAuth flow is exercised in test_auth_routes.py. The raw
# JWT verification in _resolve_oauth is exercised in test_oauth_resolver.py.
# These tests prove the THIRD link in the chain: that a bearer token which
# isn't an API key reaches _resolve_oauth and produces a Principal that flows
# through run_metered_tool the same way the API-key path does. This is the
# path Anthropic's reviewer will exercise via claude.ai.


def _stub_oauth_for(monkeypatch, *, principals_by_token):
    """Stub auth._resolve_oauth so a chosen bearer string yields a chosen
    Principal without us having to mint signed RS256 tokens at this layer.

    The signed-token path is covered exhaustively in test_oauth_resolver.py;
    here we're testing the JSON-RPC plumbing.
    """
    import auth

    def fake_resolve(token: str):
        try:
            return principals_by_token[token]
        except KeyError as e:
            raise auth.AuthError("Invalid token: stubbed", status=401) from e

    monkeypatch.setattr(auth, "_resolve_oauth", fake_resolve)


def test_tools_call_with_oauth_bearer_meters_against_resolved_org(
    client, app, fake_gemini, monkeypatch
):
    """Bearer token that is NOT an API key (no sk_ prefix) routes to
    _resolve_oauth. The returned Principal threads through run_metered_tool
    and the usage_events row records auth_method='oauth'."""
    from auth import Principal

    org = _seed_org(app, name="mcp_oauth_happy")
    token = "oauth.bearer.token"
    principal = Principal(org_id=org["org_id"], plan="free", auth_method="oauth")
    _stub_oauth_for(monkeypatch, principals_by_token={token: principal})

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "doc.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4 oauth").decode(),
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert "error" not in body, body
    assert body["result"]["isError"] is False

    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        assert len(events) == 1
        assert events[0].status == "ok"
        assert events[0].tool == "summarize_document"
        # The critical assertion: the OAuth path metered the call under the
        # right auth_method. Without this, audit / billing can't distinguish
        # MCP traffic from /api/v1/* traffic.
        assert events[0].auth_method == "oauth"
        # API-key callers have an api_key_id; OAuth callers should not.
        assert events[0].api_key_id is None


def test_tools_call_with_invalid_oauth_bearer_returns_401_and_does_not_meter(
    client, app, fake_gemini, monkeypatch
):
    """An OAuth bearer that _resolve_oauth rejects should surface as HTTP 401
    with WWW-Authenticate (same as a missing header) — NOT a 200 with a
    JSON-RPC error envelope. Otherwise claude.ai treats it as a tool failure
    and never re-runs OAuth. Also: no usage_events row should be written for
    a request that never identified a principal."""
    org = _seed_org(app, name="mcp_oauth_reject")
    # The principals_by_token dict is empty so any bearer raises AuthError.
    _stub_oauth_for(monkeypatch, principals_by_token={})

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "x.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4 rejected").decode(),
            },
        },
        headers={"Authorization": "Bearer expired.or.bad.jwt"},
    )

    assert resp.status_code == 401, resp.get_json()
    www_auth = resp.headers.get("WWW-Authenticate", "")
    assert www_auth.startswith("Bearer "), www_auth
    assert "/.well-known/oauth-protected-resource" in www_auth

    body = resp.get_json()
    assert body["error"]["code"] == -32001  # MCP_AUTH_REQUIRED

    # Nothing should have been metered against any org — we never got a
    # principal in the first place.
    with app.app_context():
        all_events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        assert all_events == []


def test_mcp_oauth_path_records_usage_against_caller_org_only(
    client, app, fake_gemini, monkeypatch
):
    """Tenancy invariant (§3.4) for the OAuth path. The existing cross-tenant
    test uses API keys only; this one proves the same isolation holds when
    callers identify via OAuth bearer (the path Anthropic's reviewer hits).
    If this ever flips, multi-tenancy is broken at the MCP+OAuth seam."""
    from auth import Principal

    a = _seed_org(app, name="mcp_oauth_iso_a")
    b = _seed_org(app, name="mcp_oauth_iso_b")
    token_a = "oauth.token.for.a"
    token_b = "oauth.token.for.b"
    _stub_oauth_for(
        monkeypatch,
        principals_by_token={
            token_a: Principal(org_id=a["org_id"], plan="free", auth_method="oauth"),
            token_b: Principal(org_id=b["org_id"], plan="free", auth_method="oauth"),
        },
    )

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "a.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4 a-only").decode(),
            },
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["result"]["isError"] is False

    with app.app_context():
        a_events = db.session.query(UsageEvent).filter_by(org_id=a["org_id"]).all()
        b_events = db.session.query(UsageEvent).filter_by(org_id=b["org_id"]).all()
        assert len(a_events) == 1
        assert a_events[0].auth_method == "oauth"
        assert a_events[0].tool == "summarize_document"
        assert b_events == []


# --- Gap #4: body-size caps at the JSON-RPC layer -----------------------------


def test_post_body_above_50mb_returns_413_without_parsing(client, monkeypatch):
    """[mcp_routes.py:298] The hard 50MB body cap fires BEFORE we try to parse
    JSON. This protects against decompression bombs / oversized payloads from
    burning Waitress threads on parsing.

    Werkzeug's test client recomputes Content-Length from the actual body, so
    we can't lie about the header. Instead we lower the cap to 1KB via
    monkeypatch (the check is `request.content_length > MAX`, so a small
    constant lets a small body trip it) and send a body just above that."""
    import mcp_routes

    # The constant is inline in mcp_post (50 * 1024 * 1024). We can't
    # monkeypatch it directly. Instead, wrap mcp_post's content_length check by
    # patching the symbol mcp_routes pulls in. Simpler: skip until we refactor
    # the constant out — for now, document the gap.
    #
    # Build a 1KB+ body to send; if mcp_routes ever pulls MAX_BODY_BYTES out of
    # a module-level constant we can monkeypatch it then.
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"x": "y" * (51 * 1024 * 1024 - 200)},  # bloat past 50MB
        }
    )
    resp = client.post(
        "/mcp",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    parsed = resp.get_json()
    assert parsed["error"]["code"] == -32600  # JSONRPC_INVALID_REQUEST
    assert "too large" in parsed["error"]["message"].lower()


def test_tools_call_decoded_content_above_10mb_returns_isError(
    client, app, fake_gemini
):
    """[mcp_tools.py:95] Per-tool 10MB decoded-content cap. Free plan's
    pages_per_call (20 × 50KB ~1MB) would 413 at the units check before the
    handler runs, so we use a pro-plan org whose units cap (500 × 50KB ~25MB)
    allows the >10MB payload through to the handler's own cap check.

    The cap surfaces as ToolError -> isError=true (model-recoverable), not a
    JSON-RPC envelope error, so the model sees the failure reason."""
    org = _seed_org(app, name="mcp_decoded_cap", plan="pro")

    # 10MB + 1 byte of raw, then base64 it.
    raw = b"%PDF-1.4 " + b"x" * (10 * 1024 * 1024)
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "huge.pdf",
                "content_base64": base64.b64encode(raw).decode(),
            },
        },
        headers=org["auth_header"],
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "exceeds" in body["result"]["content"][0]["text"].lower()

    # Refund-on-ToolError ran — usage row recorded as 'refunded'.
    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        statuses = sorted(e.status for e in events)
        assert "refunded" in statuses


# --- Gap #5: /.well-known/oauth-protected-resource CORS + URL fallback --------


def test_oauth_protected_resource_exposes_cors_to_claude_ai(client, monkeypatch):
    """Browser MCP clients (claude.ai) fetch the discovery doc cross-origin
    BEFORE auth. The CORS allowlist must let them through. Pin this so a
    future CORS edit doesn't silently break the OAuth bootstrap."""
    monkeypatch.setenv("WORKOS_ISSUER", "https://test-tenant.authkit.app")
    monkeypatch.setenv("SYNZO_PUBLIC_URL", "https://www.synzo.ai")

    resp = client.get(
        "/.well-known/oauth-protected-resource",
        headers={"Origin": "https://claude.ai"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == "https://claude.ai"


def test_oauth_protected_resource_falls_back_to_host_url_when_env_unset(
    client, monkeypatch
):
    """[mcp_routes.py:422] If SYNZO_PUBLIC_URL is unset, fall back to
    request.host_url. In prod behind Railway's edge proxy this resolves to
    'http://' (TLS terminated upstream) — that's the §6 Phase 2 'CRITICAL'
    operator note: clients will reject the OAuth flow when audience is http.
    But the route still has to RETURN something well-formed, not crash. This
    test pins the fallback path; the deployment-time invariant
    (SYNZO_PUBLIC_URL must be set in Railway) is documented in the plan, not
    in tests."""
    monkeypatch.delenv("SYNZO_PUBLIC_URL", raising=False)

    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.get_json()
    # The resource field is a non-empty URL — we don't care about the scheme
    # because the Werkzeug test client returns http://localhost/, which is
    # exactly what the prod fallback would also return (without TLS info).
    assert body["resource"].startswith(("http://", "https://"))
    assert body["resource"].rstrip("/") == body["resource"]
    # authorization_servers must match the resource (we advertise ourselves).
    assert body["authorization_servers"] == [body["resource"]]


# --- Gap #6: JSON-RPC `id` echo on error responses ----------------------------


def test_jsonrpc_error_response_echoes_request_id(client):
    """JSON-RPC 2.0 §5.1: the response MUST contain the same id as the request,
    even for error responses. The happy-path tests assert id==1; this test
    proves the same is true for error envelopes, using a string id to also
    catch any naive int-conversion bug."""
    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "x.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4 fake").decode(),
            },
        },
        request_id="abc-123",  # string id, not int
    )
    # Auth failure -> JSON-RPC error envelope. We don't care about the code
    # here; we care about the id round-trip.
    body = resp.get_json()
    assert body.get("id") == "abc-123", body


# --- Gap #7: Generic Exception in handler -> isError + refund ------------------


def test_tools_call_handler_raises_generic_exception_returns_isError_and_refunds(
    client, app, monkeypatch
):
    """[mcp_routes.py:234-239] If a tool handler raises a NON-ToolError
    Exception, the layer must:
      - refund the quota (via run_metered_tool's except path)
      - surface it as isError=true so the model can see the failure, NOT as
        a JSON-RPC error envelope (which would hide it from the model).

    The existing 'invalid base64' test (line 290) covers the ToolError branch.
    This pins the generic-Exception branch — the path a flaky internal helper
    or an unexpected feature-module bug would hit."""
    org = _seed_org(app, name="mcp_generic_exc")

    # Replace summarize_document's handler with one that raises RuntimeError.
    # Reach into the TOOLS registry to monkeypatch; ToolSpec is frozen so we
    # rebuild the entry rather than mutate the dataclass.
    import dataclasses

    from mcp_tools import TOOLS

    original_spec = TOOLS["summarize_document"]

    def boom_handler(principal, args):
        raise RuntimeError("downstream service exploded")

    new_spec = dataclasses.replace(original_spec, handler=boom_handler)
    monkeypatch.setitem(TOOLS, "summarize_document", new_spec)

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "ok.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.4 fake").decode(),
            },
        },
        headers=org["auth_header"],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "error" not in body, body
    # isError must be True, NOT a JSON-RPC envelope error.
    assert body["result"]["isError"] is True
    assert "downstream service exploded" in body["result"]["content"][0]["text"]

    # Refund happened — usage_events row recorded as 'refunded' with
    # error_code='handler_error'.
    with app.app_context():
        events = (
            db.session.query(UsageEvent)
            .filter_by(org_id=org["org_id"])
            .order_by(UsageEvent.id)
            .all()
        )
        assert events, "expected at least one usage_event"
        last = events[-1]
        assert last.status == "refunded"
        assert last.error_code == "handler_error"
