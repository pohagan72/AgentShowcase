# mcp_routes.py
# MCP (Model Context Protocol) server endpoint, Streamable HTTP transport.
# Spec: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
#
# Why this is a hand-rolled Flask blueprint, not fastmcp:
#   fastmcp is ASGI-only and wouldn't slot onto our existing WSGI/waitress
#   deployment without an asgiref bridge + uvicorn swap. The Streamable HTTP
#   spec explicitly permits returning Content-Type: application/json for
#   request/response (no SSE), which is all we need for these tool shapes.
#   Implementing the JSON-RPC envelope directly keeps the auth/quota/metering
#   pipeline in process and the deployment topology unchanged.
#
# What this surface does and doesn't:
#   - Single endpoint at /mcp accepting POST. GET/DELETE return 405 (no SSE
#     stream for server-initiated messages; no session termination).
#   - Stateless: we don't issue Mcp-Session-Id headers. Each POST is identified
#     by its Authorization header (OAuth Bearer or API key), and Principal
#     resolution happens per request via auth._identify_principal.
#   - Returns application/json for every response (no SSE upgrade). For our
#     tool shapes (summarize a PDF: ~10-30s blocking call) this is acceptable;
#     SSE streaming is added later when we wire incremental progress events.
#   - DNS rebinding mitigation: we validate the Origin header against an
#     allowlist for browser-originated requests. Non-browser clients (Claude
#     Desktop) don't send Origin and pass through.

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from flask import Blueprint, current_app, jsonify, make_response, request

from auth import AuthError, _identify_principal, run_metered_tool
from mcp_tools import TOOLS, ToolError, list_tool_descriptors

logger = logging.getLogger(__name__)

bp = Blueprint("mcp", __name__)


# Latest MCP protocol version we implement. The initialize handshake echoes
# back whatever the client requested if we can speak it; otherwise we offer
# our preferred version and the client decides.
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26"}
PREFERRED_PROTOCOL_VERSION = "2025-06-18"

# JSON-RPC 2.0 error codes (https://www.jsonrpc.org/specification#error_object).
# We reuse the standard codes for transport-level errors and assign a private
# range (-32000 to -32099) for MCP-specific failures so clients can distinguish
# "your call was malformed" from "your quota is exhausted".
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

# Server-defined (private range)
MCP_AUTH_REQUIRED = -32001
MCP_QUOTA_EXHAUSTED = -32002
MCP_RATE_LIMITED = -32003
MCP_UNITS_EXCEEDED = -32004
MCP_TIMEOUT = -32005

# Maps the AuthError.status values raised by run_metered_tool to JSON-RPC codes.
_AUTH_STATUS_TO_RPC_CODE = {
    401: MCP_AUTH_REQUIRED,
    402: MCP_QUOTA_EXHAUSTED,
    413: MCP_UNITS_EXCEEDED,
    429: MCP_RATE_LIMITED,
    504: MCP_TIMEOUT,
}


# Origins allowed for browser-originated MCP requests. claude.ai is the only
# in-scope one for Anthropic's Connector Directory; localhost is for the MCP
# Inspector tool during local development. Non-browser clients (Claude Desktop
# native, curl, MCP CLI) don't send Origin and bypass this check.
_ALLOWED_ORIGINS = {
    "https://claude.ai",
    "https://www.claude.ai",
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:5001",
    "http://127.0.0.1:5001",
}


def _origin_allowed(origin: str) -> bool:
    """Match Origin against the allowlist. Used for both the rebinding check
    on POST and the CORS reply on OPTIONS."""
    if not origin:
        return True  # No Origin header -> non-browser caller; let through.
    return origin in _ALLOWED_ORIGINS


def _cors_headers(origin: str) -> dict[str, str]:
    """Echo back the origin only if it's in the allowlist. Never use '*' here —
    these endpoints carry credentials (Authorization header) and the spec
    forbids wildcard with credentials."""
    if not origin or not _origin_allowed(origin):
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": (
            "Authorization, Content-Type, Accept, MCP-Protocol-Version, "
            "Mcp-Session-Id, Last-Event-ID"
        ),
        # WWW-Authenticate must be exposed so browser clients (claude.ai) can
        # read it on 401 responses. Without exposure the browser strips it,
        # the MCP client never sees the resource_metadata pointer, and the
        # OAuth flow never starts — the failure mode that lost a half day.
        "Access-Control-Expose-Headers": "Mcp-Session-Id, MCP-Protocol-Version, WWW-Authenticate",
        "Access-Control-Max-Age": "86400",
    }


def _rpc_response(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str, data: Any = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": err}


def _json_with_cors(payload: dict, status: int = 200):
    """Build a Flask response with our CORS headers attached."""
    resp = make_response(jsonify(payload), status)
    for header, value in _cors_headers(request.headers.get("Origin", "")).items():
        resp.headers[header] = value
    return resp


def _resource_metadata_url() -> str:
    """Absolute URL of our RFC 9728 protected-resource-metadata document.

    Used in the WWW-Authenticate header on 401 responses so MCP clients can
    discover the auth server. Matches the resource origin advertised by the
    discovery endpoint itself (oauth_protected_resource below), which is
    keyed on SYNZO_PUBLIC_URL so it survives Railway's edge TLS termination
    rewriting request.host_url to http://."""
    base = os.environ.get("SYNZO_PUBLIC_URL", request.host_url.rstrip("/"))
    return f"{base}/.well-known/oauth-protected-resource"


# --- Method handlers -----------------------------------------------------------


def _handle_initialize(params: dict) -> dict:
    """Handshake response. Echo the client's protocol version if supported,
    otherwise return our preferred one."""
    client_version = (params or {}).get("protocolVersion")
    protocol_version = (
        client_version
        if client_version in SUPPORTED_PROTOCOL_VERSIONS
        else PREFERRED_PROTOCOL_VERSION
    )
    return {
        "protocolVersion": protocol_version,
        "capabilities": {
            # We expose tools and no other capability surface for v1. No
            # resources, no prompts, no sampling, no roots.
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": "synzo",
            "title": "Synzo",
            "version": _server_version(),
        },
        "instructions": (
            "Synzo provides document-intelligence tools (summarize, translate, "
            "redact PII, analyze images, detect faces) via authenticated "
            "endpoints. All tools meter against the calling organization's quota."
        ),
    }


def _server_version() -> str:
    """Best-effort version string. Falls back to '0.1.0' if no env var is set."""
    return os.environ.get("SYNZO_VERSION", "0.1.0")


def _handle_tools_list() -> dict:
    return {"tools": list_tool_descriptors()}


def _handle_tools_call(params: dict):
    """Authenticate, run the tool through the metering pipeline, wrap the
    result in MCP's content envelope. Returns (result_dict, rpc_error_dict)
    where exactly one is None."""
    name = (params or {}).get("name")
    arguments = (params or {}).get("arguments") or {}

    spec = TOOLS.get(name)
    if spec is None:
        return None, ("Method not found: tool '{}'".format(name), JSONRPC_METHOD_NOT_FOUND)

    # Identify caller. We let _identify_principal pull from request.headers
    # exactly like the HTTP path does.
    try:
        principal = _identify_principal()
    except AuthError as e:
        return None, (e.message, _AUTH_STATUS_TO_RPC_CODE.get(e.status, JSONRPC_INTERNAL_ERROR))

    try:
        units = max(1, int(spec.units_fn(arguments)))
    except Exception as e:
        logger.warning("units_fn failed for %s: %s", spec.name, e)
        return None, ("Could not size request", JSONRPC_INVALID_PARAMS)

    try:
        payload = run_metered_tool(
            principal,
            spec.name,
            units,
            lambda: spec.handler(principal, arguments),
        )
    except AuthError as e:
        return None, (e.message, _AUTH_STATUS_TO_RPC_CODE.get(e.status, JSONRPC_INTERNAL_ERROR))
    except ToolError as e:
        # Argument failure surfaced by the tool itself (e.g. unsupported file
        # type). Different from a server-side exception in that the call is
        # still metered as an error and the quota was refunded.
        # We surface this through MCP's tool-result error channel (isError=true)
        # rather than a JSON-RPC envelope error, per the spec's guidance that
        # tool-level failures should be visible to the model so it can recover.
        return _tool_error_result(str(e)), None
    except Exception as e:
        # run_metered_tool already refunded the quota and metered as 'refunded'.
        # Surface as a tool-level error too (model-visible) so an LLM can see
        # what went wrong rather than just a transport error.
        logger.exception("MCP tool %s failed", spec.name)
        return _tool_error_result(f"Tool error: {e}"), None

    return _tool_success_result(payload), None


def _tool_success_result(payload: dict) -> dict:
    """Wrap a tool's structured output in MCP's content envelope.

    We emit BOTH a structuredContent block (machine-readable JSON the model
    can parse cleanly) AND a text block (human-readable fallback for older
    clients that don't yet consume structuredContent). Same data, two shapes.
    """
    import json as _json
    return {
        "content": [
            {"type": "text", "text": _json.dumps(payload, indent=2)},
        ],
        "structuredContent": payload,
        "isError": False,
    }


def _tool_error_result(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


# --- The transport entry point ------------------------------------------------


@bp.route("/mcp", methods=["POST", "OPTIONS"])
def mcp_post():
    """Single endpoint for all client->server JSON-RPC traffic.

    Spec compliance notes:
      - Client MUST send Accept: application/json, text/event-stream. We don't
        enforce this strictly (some clients ship with just one) — we always
        respond as application/json which the spec permits.
      - For JSON-RPC requests we return Content-Type: application/json.
      - For JSON-RPC notifications/responses we return 202 Accepted with no
        body (the spec's MUST when input has no `id`).
      - DNS rebinding: validate Origin against the allowlist.
    """
    origin = request.headers.get("Origin", "")

    if request.method == "OPTIONS":
        resp = make_response("", 204)
        for header, value in _cors_headers(origin).items():
            resp.headers[header] = value
        return resp

    if origin and not _origin_allowed(origin):
        return _json_with_cors(
            _rpc_error(None, JSONRPC_INVALID_REQUEST, f"Origin not allowed: {origin}"),
            status=403,
        )

    if request.content_length and request.content_length > 50 * 1024 * 1024:
        # Hard cap on body size. 50 MB lets a base64-encoded 10 MB doc through
        # with headroom for the JSON-RPC envelope.
        return _json_with_cors(
            _rpc_error(None, JSONRPC_INVALID_REQUEST, "Request body too large"),
            status=413,
        )

    try:
        body = request.get_json(force=True, silent=False)
    except Exception:
        return _json_with_cors(
            _rpc_error(None, JSONRPC_PARSE_ERROR, "Invalid JSON"),
            status=400,
        )

    if not isinstance(body, dict):
        # We don't support batched requests for v1. Clients that send arrays
        # get a clean error; the spec lets servers reject batches.
        return _json_with_cors(
            _rpc_error(None, JSONRPC_INVALID_REQUEST, "Expected a JSON-RPC object"),
            status=400,
        )

    jsonrpc = body.get("jsonrpc")
    method = body.get("method")
    request_id = body.get("id")  # absent -> notification
    params = body.get("params") or {}

    if jsonrpc != "2.0" or not isinstance(method, str):
        return _json_with_cors(
            _rpc_error(request_id, JSONRPC_INVALID_REQUEST, "Malformed JSON-RPC message"),
            status=400,
        )

    is_notification = "id" not in body

    # --- Dispatch ---

    if method == "initialize":
        result = _handle_initialize(params)
        return _json_with_cors(_rpc_response(request_id, result))

    if method == "notifications/initialized":
        # Client confirming the handshake. No response body, 202 Accepted.
        resp = make_response("", 202)
        for header, value in _cors_headers(origin).items():
            resp.headers[header] = value
        return resp

    if method == "ping":
        return _json_with_cors(_rpc_response(request_id, {}))

    if method == "tools/list":
        return _json_with_cors(_rpc_response(request_id, _handle_tools_list()))

    if method == "tools/call":
        result, error = _handle_tools_call(params)
        if error is not None:
            message, code = error
            # Per MCP authorization spec (2025-06-18 §2.1) and RFC 9728: an
            # unauthenticated tools/call MUST return HTTP 401 with a
            # WWW-Authenticate header pointing at the protected-resource-
            # metadata URL. Without this, MCP clients (including claude.ai)
            # don't know to initiate the OAuth flow — they read the body's
            # JSON-RPC error and surface it to the user as a tool failure.
            if code == MCP_AUTH_REQUIRED:
                resp = _json_with_cors(_rpc_error(request_id, code, message), status=401)
                resp.headers["WWW-Authenticate"] = (
                    f'Bearer realm="synzo", '
                    f'resource_metadata="{_resource_metadata_url()}"'
                )
                return resp
            return _json_with_cors(_rpc_error(request_id, code, message))
        return _json_with_cors(_rpc_response(request_id, result))

    # Notifications we don't recognize: per spec, server MUST return 202 if
    # it accepts the input; we accept (drop) any unknown notification.
    if is_notification:
        resp = make_response("", 202)
        for header, value in _cors_headers(origin).items():
            resp.headers[header] = value
        return resp

    return _json_with_cors(
        _rpc_error(request_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}"),
        status=404,
    )


@bp.route("/mcp", methods=["GET", "DELETE"])
def mcp_get_delete():
    """We don't implement server-initiated SSE streams or session termination
    for v1. Spec permits 405 on both."""
    resp = make_response(jsonify({"error": "Method not allowed"}), 405)
    resp.headers["Allow"] = "POST, OPTIONS"
    for header, value in _cors_headers(request.headers.get("Origin", "")).items():
        resp.headers[header] = value
    return resp


# --- OAuth discovery (RFC 9728 + MCP authorization spec) ----------------------


@bp.route("/.well-known/oauth-protected-resource", methods=["GET", "OPTIONS"])
def oauth_protected_resource():
    """Points MCP clients at our WorkOS authorization server.

    Spec: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
    RFC 9728: https://datatracker.ietf.org/doc/html/rfc9728

    The minimum field set per RFC 9728 is `resource` and `authorization_servers`.
    We also surface `bearer_methods_supported` so well-behaved clients know to
    use the Authorization header (not a query param).
    """
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        for header, value in _cors_headers(request.headers.get("Origin", "")).items():
            resp.headers[header] = value
        return resp

    # Resource URL is the externally-reachable URL of this server.
    # Prefer an explicit env var so we don't depend on Host header parsing
    # (which is unreliable behind Railway's edge proxy).
    resource = os.environ.get("SYNZO_PUBLIC_URL", request.host_url.rstrip("/"))

    # We advertise OUR OWN /.well-known/oauth-authorization-server as the
    # authorization-server discovery URL — not WorkOS's directly. Reason:
    # WorkOS's discovery doc does not include `registration_endpoint`, so MCP
    # clients (claude.ai) abandon the OAuth bootstrap silently. Our wrapper
    # endpoint proxies WorkOS's AuthKit metadata AND injects the registration
    # endpoint, restoring the flow. See oauth_authorization_server() below.
    payload = {
        "resource": resource,
        "authorization_servers": [resource],
        "bearer_methods_supported": ["header"],
        "resource_documentation": resource + "/docs",
    }

    origin = request.headers.get("Origin", "")
    resp = make_response(jsonify(payload), 200)
    # This endpoint is meant to be discoverable from any origin (MCP clients
    # fetch it before auth). Apply our same allowlist if Origin is present.
    for header, value in _cors_headers(origin).items():
        resp.headers[header] = value
    return resp


# Module-level cache for the upstream WorkOS metadata. WorkOS's discovery doc
# changes rarely (issuer, endpoints, JWKS URL). We fetch on first request and
# cache for the process lifetime; a Railway restart re-fetches. If WorkOS goes
# down mid-request we still serve the cached copy.
_AUTH_SERVER_METADATA_CACHE: dict | None = None


def _fetch_authkit_metadata() -> dict:
    """Fetch the AuthKit OAuth 2.0 Authorization Server Metadata (RFC 8414).

    The AuthKit hosted-UI subdomain (e.g. real-vine-49-staging.authkit.app)
    publishes a richer doc than the api.workos.com one — it includes
    code_challenge_methods_supported, grant_types_supported, scopes_supported,
    etc. that MCP clients require for the OAuth handshake.

    The AuthKit URL comes from WORKOS_ISSUER. Operator MUST set this to the
    authkit.app subdomain (not the api.workos.com URL) for OAuth to work.
    """
    global _AUTH_SERVER_METADATA_CACHE
    if _AUTH_SERVER_METADATA_CACHE is not None:
        return _AUTH_SERVER_METADATA_CACHE

    issuer = os.environ.get("WORKOS_ISSUER", "").rstrip("/")
    if not issuer:
        return {}

    url = f"{issuer}/.well-known/oauth-authorization-server"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        _AUTH_SERVER_METADATA_CACHE = r.json()
    except Exception as e:
        logger.error("Failed to fetch AuthKit metadata from %s: %s", url, e)
        return {}
    return _AUTH_SERVER_METADATA_CACHE


@bp.route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
def oauth_authorization_server():
    """RFC 8414 OAuth 2.0 Authorization Server Metadata, augmented for MCP.

    Why this exists (i.e. why we don't just point MCP clients at WorkOS
    directly):

    WorkOS supports Dynamic Client Registration (RFC 7591) — POSTing to
    /oauth2/register on the AuthKit subdomain succeeds — but does NOT
    advertise `registration_endpoint` in its discovery document. MCP clients
    (notably claude.ai) read the discovery doc, see no registration_endpoint,
    and silently abandon the OAuth bootstrap. The user never sees a sign-in
    prompt; tools/list works (anonymous) but tools/call fails with no
    indication why.

    Our wrapper proxies WorkOS's AuthKit metadata and injects the missing
    `registration_endpoint` field. claude.ai then finds the registration
    URL, performs DCR, drives PKCE + user consent, and obtains a bearer
    token. This makes Synzo work as a public MCP connector without requiring
    every client to pre-register.

    The injected URL points at AuthKit's actual DCR endpoint, so the work
    happens on WorkOS — we just advertise it correctly.
    """
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        for header, value in _cors_headers(request.headers.get("Origin", "")).items():
            resp.headers[header] = value
        return resp

    upstream = _fetch_authkit_metadata()
    if not upstream:
        # If we can't reach WorkOS, return 503 rather than serving garbage —
        # the client will surface a real error instead of silently failing
        # later in the OAuth dance.
        resp = make_response(
            jsonify({"error": "Authorization server metadata unavailable"}),
            503,
        )
        for header, value in _cors_headers(request.headers.get("Origin", "")).items():
            resp.headers[header] = value
        return resp

    issuer = os.environ.get("WORKOS_ISSUER", "").rstrip("/")

    # Start from WorkOS's doc, then override / inject the fields claude.ai
    # needs. We don't blindly trust upstream's `issuer` field — pin it to
    # what we control so a WorkOS-side rename doesn't break audience checks.
    payload = dict(upstream)
    payload["issuer"] = issuer
    payload["registration_endpoint"] = f"{issuer}/oauth2/register"

    # MCP clients expect these even if upstream omits them. Defensive: only
    # set defaults if upstream didn't already supply them.
    payload.setdefault("code_challenge_methods_supported", ["S256"])
    payload.setdefault("grant_types_supported", ["authorization_code", "refresh_token"])
    payload.setdefault("response_types_supported", ["code"])
    payload.setdefault("scopes_supported", ["openid", "profile", "email", "offline_access"])
    payload.setdefault(
        "token_endpoint_auth_methods_supported",
        ["none", "client_secret_basic", "client_secret_post"],
    )

    origin = request.headers.get("Origin", "")
    resp = make_response(jsonify(payload), 200)
    for header, value in _cors_headers(origin).items():
        resp.headers[header] = value
    return resp
