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


def test_tools_call_without_auth_returns_jsonrpc_auth_error(client, fake_gemini):
    """No Authorization header -> JSON-RPC error with our auth-required code,
    not an HTTP 401. JSON-RPC envelope still returns 200 (transport succeeded)."""
    resp = _rpc(client, "tools/call", {
        "name": "summarize_document",
        "arguments": {
            "filename": "x.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.4 fake").decode(),
        },
    })
    # Transport succeeded; protocol-level error is in the envelope.
    body = resp.get_json()
    assert "error" in body
    # MCP_AUTH_REQUIRED = -32001
    assert body["error"]["code"] == -32001


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
    """We don't implement server-initiated SSE streams; GET is 405."""
    resp = client.get("/mcp")
    assert resp.status_code == 405


# --- /.well-known/oauth-protected-resource ------------------------------------


def test_oauth_protected_resource_returns_resource_and_authorization_servers(
    client, monkeypatch
):
    monkeypatch.setenv("WORKOS_ISSUER", "https://api.workos.com/user_management/client_abc")
    monkeypatch.setenv("SYNZO_PUBLIC_URL", "https://www.synzo.ai")

    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["resource"] == "https://www.synzo.ai"
    assert body["authorization_servers"] == [
        "https://api.workos.com/user_management/client_abc"
    ]
    assert "header" in body["bearer_methods_supported"]
