"""Build Synzo-MCP-Server-Specification.docx from the Harvey example template.

Strategy: open the Harvey example .docx so we inherit its styles (Title, Heading 1/2/3,
normal, table style), wipe the body, and append the Synzo content using those same
styles. Keeps the look-and-feel the Harvey evaluators expect while replacing every
ACME-specific statement with verified Synzo facts.
"""

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt


TEMPLATE = Path(r"C:\Users\651802\Downloads\[Example] Ideal MCP Server Specification - Harvey AI (1).docx")
OUTPUT = Path(r"C:\Personal\AgentShowcase\docs\harvey\Synzo-MCP-Server-Specification.docx")


def wipe_body(doc):
    body = doc.element.body
    sectPr = body.find(qn("w:sectPr"))
    for child in list(body):
        if child is sectPr:
            continue
        body.remove(child)


def add_para(doc, text, style="Normal", bold=False):
    p = doc.add_paragraph(style=style)
    run = p.add_run(text)
    if bold:
        run.bold = True
    return p


def add_bullet(doc, text):
    # Template has no List Bullet style; render as a plain paragraph with a bullet glyph.
    p = doc.add_paragraph("• " + text, style="Normal")
    return p


def add_code(doc, text):
    """Monospace, left-aligned block for JSON examples."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    return p


def add_kv_table(doc, pairs, header=None):
    """Two-column key/value table."""
    rows = len(pairs) + (1 if header else 0)
    table = doc.add_table(rows=rows, cols=2)
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    r = 0
    if header:
        for c, text in enumerate(header):
            cell = table.rows[r].cells[c]
            cell.text = ""
            run = cell.paragraphs[0].add_run(text)
            run.bold = True
        r += 1
    for k, v in pairs:
        table.rows[r].cells[0].text = k
        table.rows[r].cells[1].text = v
        r += 1
    return table


def add_matrix_table(doc, header, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    for c, text in enumerate(header):
        cell = table.rows[0].cells[c]
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        run.bold = True
    for r, row in enumerate(rows, start=1):
        for c, text in enumerate(row):
            table.rows[r].cells[c].text = text
    return table


def add_tool_arg_table(doc, rows):
    return add_matrix_table(
        doc,
        ["Name", "Type", "Required / limits", "Description"],
        rows,
    )


def add_tool_result_table(doc, rows):
    return add_matrix_table(
        doc,
        ["Field", "Type", "Presence", "Description"],
        rows,
    )


def main():
    doc = Document(str(TEMPLATE))
    wipe_body(doc)

    # Core properties
    cp = doc.core_properties
    cp.title = "Synzo MCP Server Specification"
    cp.author = "Paul O'Hagan, Red Maple Research"
    cp.subject = "MCP connector specification for Harvey review"

    # ----- COVER -----
    add_para(doc, "Synzo MCP Server Specification", style="Title")
    add_para(
        doc,
        "Model Context Protocol connector for Synzo, a hosted document and image processing service.",
    )
    add_para(doc, "Provider: Red Maple Research")
    add_para(doc, "Primary technical contact: Paul O'Hagan, Principal — paul@redmapleresearch.ca")
    add_para(doc, "Document revision: 1.0")
    add_para(doc, "Last updated: 5 October 2026")
    add_para(
        doc,
        "Repository reviewed: commit 1adc36e. Server version at review time: 0.1.0.",
    )

    # ----- INTRODUCTION -----
    add_para(doc, "Introduction", style="Heading 1")
    add_para(
        doc,
        "Synzo is a hosted Model Context Protocol (MCP) connector offered by Red Maple "
        "Research. The connector lets an LLM-driven client stage caller-supplied "
        "documents and images and then invoke a small catalog of processing tools: "
        "document summarization, document translation, PII redaction, image analysis, "
        "and face obscuring. Billing is organization-based through metered calls.",
    )
    add_para(
        doc,
        "This document is written for engineers integrating Synzo as an MCP connector. "
        "It specifies the exact wire behavior, the authentication model, the six tools "
        "the server publishes, and the limits and controls that apply to tool execution. "
        "Where a fact depends on a provider configuration (WorkOS AuthKit) or on a "
        "deployment-time setting, that dependency is called out instead of being quoted "
        "as a hard value.",
    )
    add_para(doc, "Readers of this document should expect:")
    add_bullet(doc, "MCP protocol version and transport semantics the server actually implements.")
    add_bullet(doc, "Authentication model, including the two credential types the server accepts.")
    add_bullet(doc, "A complete catalog of the six tools, with typed arguments and typed results.")
    add_bullet(doc, "The organization-level controls that gate tool execution — Synzo does not use per-tool OAuth scopes.")
    add_bullet(doc, "Operational limits, error codes, and data-handling boundaries.")
    add_para(
        doc,
        "Many of the facts in this document are also returned dynamically through MCP "
        "discovery (initialize, tools/list, OAuth metadata). The written form here is the "
        "authoritative integration contract.",
    )

    # ----- ENDPOINT -----
    add_para(doc, "Endpoint", style="Heading 1")
    add_para(
        doc,
        "Synzo publishes one MCP endpoint over HTTPS. The transport is Streamable HTTP as "
        "defined by MCP, implemented as JSON-RPC 2.0 over HTTP POST with JSON responses. "
        "The server is stateless at the transport layer: it does not issue an "
        "Mcp-Session-Id, does not maintain a persistent server-initiated SSE stream, and "
        "does not send tool-list-change notifications.",
    )
    add_kv_table(
        doc,
        [
            ("URL", "https://www.synzo.ai/mcp"),
            ("Transport", "Streamable HTTP, JSON-RPC 2.0 over HTTP POST, JSON responses"),
            ("Server name", "synzo"),
            ("Server title", "Synzo"),
            ("Server version", "0.1.0"),
            ("Preferred MCP protocol revision", "2025-06-18"),
            ("Also accepted MCP protocol revision", "2025-03-26"),
            ("JSON-RPC version", "2.0"),
            ("tools.listChanged", "false"),
        ],
        header=["Field", "Value"],
    )
    add_para(
        doc,
        "Use Content-Type: application/json and Accept: application/json, text/event-stream "
        "on every request. GET and DELETE on /mcp return HTTP 405. The initialize method, "
        "the ping method, and tools/list are available without authentication. Any "
        "tools/call invocation requires authentication. Unknown tool names are rejected.",
    )
    add_para(
        doc,
        "The Synzo server version (0.1.0) and the MCP protocol revision are independent "
        "values. The protocol revision describes which wire specification the server "
        "complies with; the server version identifies the running implementation. Revisions "
        "to this document do not change either value.",
    )

    # ----- AUTHENTICATION -----
    add_para(doc, "Authentication", style="Heading 1")
    add_para(
        doc,
        "Synzo accepts two credential types for tool execution: OAuth 2.0 bearer tokens "
        "(Authorization Code with PKCE S256) issued through WorkOS AuthKit, and "
        "organization-scoped API keys issued through the Synzo dashboard. Both resolve to "
        "the same organization-level principal used for authorization, metering, and rate "
        "limiting. The authorization-server metadata is published under RFC 8414; Synzo "
        "does not advertise OAuth 2.1 specifically. Discovery (initialize, tools/list, "
        "OAuth metadata endpoints) is anonymous; tools/call requires authentication.",
    )
    add_para(doc, "Connection sequence:")
    add_bullet(doc, "Client POSTs initialize to https://www.synzo.ai/mcp. The server responds with its protocol version, serverInfo, and capabilities. No credential is required.")
    add_bullet(doc, "Client calls tools/list and receives the six tool descriptors. No credential is required.")
    add_bullet(doc, "Client calls tools/call. If the request is unauthenticated or the token is invalid, the server returns HTTP 401 with a WWW-Authenticate header pointing to its OAuth protected-resource metadata (JSON-RPC error -32001).")
    add_bullet(doc, "Client completes an OAuth 2.0 authorization-code flow with PKCE S256, or presents an organization-scoped API key, and retries the call.")
    add_para(doc, "OAuth discovery chain:")
    add_bullet(doc, "Protected-resource metadata: https://www.synzo.ai/.well-known/oauth-protected-resource. Its authorization_servers field lists Synzo's own public URL; the client is directed back to Synzo for the authorization-server document, not to WorkOS directly.")
    add_bullet(doc, "Authorization-server metadata: https://www.synzo.ai/.well-known/oauth-authorization-server. This Synzo endpoint fetches the upstream WorkOS AuthKit metadata and augments it: the issuer is pinned to the WORKOS_ISSUER value configured on the deployment (so a WorkOS-side rename cannot break audience checks), registration_endpoint is injected as <WORKOS_ISSUER>/oauth2/register, and defaults are set for code_challenge_methods_supported, grant_types_supported, response_types_supported, scopes_supported, and token_endpoint_auth_methods_supported where WorkOS does not already supply them. The response is therefore an augmented view of the upstream WorkOS document, not a pure forward and not a document whose issuer is Synzo's own URL.")
    add_para(
        doc,
        "The upstream WorkOS AuthKit host is determined entirely by the deployment's "
        "WORKOS_ISSUER environment variable (no fallback is compiled in). At the time of "
        "this review the live endpoint advertises real-vine-49-staging.authkit.app as the "
        "upstream host; whether that is the intended environment for Harvey submission "
        "must be confirmed on the deployed service before go-live.",
    )
    add_para(
        doc,
        "The augmented authorization-server metadata advertises Authorization Code with "
        "PKCE S256, refresh tokens, device-code grants, Dynamic Client Registration, and "
        "token endpoint authentication methods none, client_secret_post, and "
        "client_secret_basic. Advertising these methods in discovery does not establish "
        "that every advertised flow has been exercised end-to-end with Harvey; "
        "verification of the Harvey client registration is tracked as a pending "
        "onboarding item (see \"Outstanding verification\" in Appendix B).",
    )
    add_para(
        doc,
        "Access tokens are validated as signed JWTs against the configured issuer and "
        "audience and must carry both a sub (user) claim and an org_id (or "
        "organization_id) claim. The sub and org_id claims are used to resolve the "
        "Synzo user and organization membership; the token's email claim, if present, is "
        "used only for logging and account provisioning, not for membership resolution. "
        "API keys are accepted either in Authorization: Bearer <key> or in X-API-Key, "
        "SHA-256-hashed at rest, and compared with hmac.compare_digest in constant time. "
        "OAuth tokens must use the Bearer scheme.",
    )
    add_para(
        doc,
        "Requests containing an Origin header must match Synzo's allowlist. Harvey-"
        "specific Origin requirements will be confirmed during onboarding: whether "
        "Harvey's MCP client sends an Origin header at all depends on whether the client "
        "calls /mcp directly or proxies through a Harvey backend, and the exact value "
        "cannot be inferred from Harvey's website hostname. Requests without an Origin "
        "header remain subject to authentication and all other access controls.",
    )

    add_para(doc, "Scopes", style="Heading 2")
    add_para(
        doc,
        "Synzo does not define per-tool authorization scopes and does not filter the "
        "tool catalog by scope. Every one of the six tools uses the same authentication "
        "and metering path. The identity scopes advertised by the authorization server "
        "metadata are shown below; a client should request openid plus the identity "
        "scopes it needs to establish the user's email and session.",
    )
    add_matrix_table(
        doc,
        ["Scope", "Purpose", "Notes"],
        [
            ["openid", "Required for an OpenID Connect token.", "Identity scope. No tool is gated on it; standard OIDC behavior."],
            ["profile", "Lets the authorization server return basic profile claims.", "Identity scope."],
            ["email", "Lets the authorization server return the user's email claim.", "Identity scope. Provides email for account metadata. User and organization resolution uses the sub and organization claims."],
            ["offline_access", "Lets the client receive a refresh token.", "Identity scope. Required for long-lived agent sessions."],
        ],
    )
    add_para(
        doc,
        "The authorization-server metadata emits these scopes as a setdefault value: if "
        "the deployed WorkOS AuthKit tenant advertises a different scopes_supported list "
        "upstream, that list is served to clients. The authoritative source is a live "
        "fetch of the authorization-server metadata URL at integration time.",
    )
    add_para(
        doc,
        "Dashboard operations (invitations, membership changes, API-key creation and "
        "revocation) are gated by a membership-role check in the Synzo application; this "
        "is independent of MCP tool execution.",
    )

    add_para(doc, "Token Security", style="Heading 2")
    add_para(
        doc,
        "Token lifetimes for OAuth access and refresh tokens are controlled by the "
        "deployed WorkOS AuthKit tenant, not by Synzo application code. The values below "
        "are read from the WorkOS AuthKit application configuration backing the submitted "
        "endpoint (Synzo application, Sessions tab) as of October 5, 2026. The password-"
        "setup and email-verification link lifetimes are not surfaced in the WorkOS "
        "dashboard; they operate at WorkOS AuthKit defaults.",
    )
    add_matrix_table(
        doc,
        ["Component", "Time-to-live (TTL)", "Notes"],
        [
            ["OAuth access token", "5 minutes", "WorkOS AuthKit \"Access token duration\" for the Synzo application. Not a Synzo-controlled value; a WorkOS configuration change here changes the lifetime without a Synzo deploy."],
            ["Session / refresh envelope", "365 days maximum, with a 2-day inactivity timeout", "WorkOS AuthKit \"Maximum session length\" (365 days) and \"Inactivity timeout\" (2 days) for the Synzo application. The refresh token issued by WorkOS is bound to this session envelope; it is renewed on use and terminates at whichever of the maximum length or inactivity timeout fires first. Revocation behavior is governed by WorkOS AuthKit; Synzo application code does not implement its own refresh-token revocation."],
            ["Organization invitation", "7 days default expiry", "WorkOS AuthKit \"Default invitation expiry\" for the Synzo application. Invitations issued through the dashboard or API expire after this interval unless an explicit override is set per invitation."],
            ["Email verification / password-setup link", "WorkOS AuthKit default", "Issued by WorkOS during account provisioning. The dashboard does not surface a configurable TTL; the links use WorkOS AuthKit's default lifetime. Treat the exact value as a WorkOS-owned implementation detail; recipients who miss the window can request a fresh link through the sign-in flow."],
            ["Synzo API key", "No time-based expiry", "A dashboard-created API key remains valid until revoked. Revocation sets a revoked_at timestamp; subsequent authentications fail with -32001. Keys are SHA-256-hashed at rest and compared with hmac.compare_digest."],
        ],
    )
    add_para(
        doc,
        "Synzo API keys are 32 bytes of secrets.token_urlsafe randomness, which produces "
        "a 256-bit key. There is no in-application lifetime check: enforcement is entirely "
        "by revocation and by the organization-level request limits.",
    )

    # ----- MCP FEATURES -----
    add_para(doc, "MCP Features", style="Heading 1")
    add_para(
        doc,
        "Synzo implements the subset of the MCP specification needed to publish and call "
        "tools. The table below enumerates which optional features are supported and which "
        "are intentionally absent.",
    )
    add_matrix_table(
        doc,
        ["Feature", "Supported", "Notes"],
        [
            ["Tools", "Yes", "Six tools are published; see Tool Catalog."],
            ["Tool input schemas", "Yes", "Published in tools/list descriptors; see also Synzo-MCP-Tool-Definitions.json."],
            ["Tool output schemas", "No", "No tool publishes an outputSchema. Return shapes are documented in the Reference section."],
            ["Structured content on results", "Yes", "Successful calls return isError: false, structuredContent with the payload, and a text content block containing the same payload serialized as indented JSON."],
            ["Resources", "No", "The server does not publish MCP resources."],
            ["Prompts", "No", "The server does not publish MCP prompts."],
            ["Roots", "No", "No roots capability is advertised."],
            ["Sampling", "No", "The server does not request client sampling."],
            ["Persistent SSE stream", "No", "Every response is a JSON HTTP response. GET on /mcp returns 405."],
            ["Mcp-Session-Id", "No", "The server does not issue session IDs."],
            ["tools.listChanged notifications", "No", "The capability is explicitly advertised as false."],
            ["Argument validation", "Handler-side only", "The dispatcher does not run general JSON Schema validation. Each handler enforces its own required-field and enum checks. Published schemas (including additionalProperties: false and the target_language 2–64 bounds) are the advertised client contract."],
        ],
    )

    # ----- TOOL CATALOG -----
    add_para(doc, "Tool Catalog", style="Heading 1")
    add_para(
        doc,
        "This section lists every tool a properly authenticated MCP client can call. All "
        "six tools are visible to every authenticated client; Synzo does not use scope-based "
        "catalog filtering. Each tool is described in detail in the Reference section.",
    )
    add_matrix_table(
        doc,
        ["Tool", "Purpose", "Supported input", "Result form", "Access"],
        [
            ["upload_file", "Stage caller-supplied bytes and receive a Synzo HTTPS URL.", "Base64 content and filename.", "Structured JSON with content_url and expiry.", "Any authenticated organization principal."],
            ["summarize_document", "Classify a document and produce a Markdown summary.", "HTTPS URL to a PDF, DOCX, PPTX, or XLSX file.", "Structured JSON with classification and summary.", "Any authenticated organization principal."],
            ["translate_document", "Translate extracted document text into a target language.", "HTTPS URL to a DOCX, PPTX, or XLSX file plus target_language.", "Structured JSON with translated_text (Markdown).", "Any authenticated organization principal."],
            ["redact_pii", "Produce a redacted copy of a document in its original format.", "HTTPS URL to a DOCX or PPTX file.", "Structured JSON with a result_url to the redacted copy.", "Any authenticated organization principal."],
            ["analyze_image", "Describe an image and flag potentially sensitive content.", "HTTPS URL to a JPG, JPEG, PNG, WEBP, HEIC, or HEIF image.", "Structured JSON with description, OCR text, detected objects, safety flags, and a dominant-color palette.", "Any authenticated organization principal."],
            ["detect_faces", "Blur or redact faces in an image and return a PNG.", "HTTPS URL to a JPG, JPEG, PNG, WEBP, HEIC, or HEIF image.", "Structured JSON with a result_url to the obscured PNG.", "Any authenticated organization principal."],
        ],
    )

    # ----- REFERENCE -----
    add_para(doc, "Reference", style="Heading 1")
    add_para(
        doc,
        "This section documents each tool in detail. Every reference page uses the same "
        "subsections: Full Description, Scopes, Call Arguments, and Return Results. A "
        "representative request and response example closes each tool. Example credentials "
        "and URLs are placeholders unless noted otherwise.",
    )
    add_para(
        doc,
        "Every tool shares one authorization rule, one success envelope, and one error "
        "classification. Rather than repeat them per tool, they are stated once here:",
    )
    add_bullet(doc, "Authorization: a valid organization-scoped principal (OAuth JWT with a provisioned organization claim, or an organization-scoped API key). There is no additional per-tool scope and no catalog filtering by scope.")
    add_bullet(doc, "Success envelope: result.isError is false; result.structuredContent is the per-tool payload described below; result.content is a one-element array of type text whose text is the same payload serialized as indented JSON.")
    add_bullet(doc, "Errors: input-validation performed inside a tool handler (unknown enum values, oversized decoded uploads, non-HTTPS content URLs, URL-fetch timeouts, provider refusals) returns a result with isError: true and an explanatory text block. Protocol, authentication, organization-quota, organization-rate-limit, per-call unit-limit, and overall execution-deadline failures use JSON-RPC error envelopes with the codes documented in Appendix A. HTTP errors may contain JSON-RPC error envelopes: HTTP 400 (-32700 or -32600), 401 (-32001), 404 (-32601), and 413 (-32600) carry a JSON-RPC error body. HTTP 405 and the IP-level HTTP 429 response use ordinary JSON error objects, not JSON-RPC envelopes. Organization-level rate limiting returns JSON-RPC -32003 inside an HTTP 200 response. Clients should read both the HTTP status and the response body rather than treating them as mutually exclusive.")
    add_bullet(doc, "Side effects: every successful call consumes organization quota and counts toward the organization's rate limits. upload_file, redact_pii, and detect_faces create a temporary file whose URL is included in the result; see the Data Handling appendix for retention.")

    _write_upload_file(doc, add_para, add_bullet, add_code, add_tool_arg_table, add_tool_result_table)
    _write_summarize(doc, add_para, add_bullet, add_code, add_tool_arg_table, add_tool_result_table)
    _write_translate(doc, add_para, add_bullet, add_code, add_tool_arg_table, add_tool_result_table)
    _write_redact(doc, add_para, add_bullet, add_code, add_tool_arg_table, add_tool_result_table)
    _write_analyze_image(doc, add_para, add_bullet, add_code, add_tool_arg_table, add_tool_result_table)
    _write_detect_faces(doc, add_para, add_bullet, add_code, add_tool_arg_table, add_tool_result_table)

    # ----- APPENDIX A: OPERATIONAL LIMITS -----
    add_para(doc, "Appendix A: Operational Limits and Errors", style="Heading 1")
    add_para(
        doc,
        "This appendix consolidates the enforced limits and the error codes the server "
        "emits. The values are read from the server configuration at the time of this "
        "revision; where a value is a deployment setting, the source is called out.",
    )
    add_matrix_table(
        doc,
        ["Limit", "Value", "Scope"],
        [
            ["Per-IP request rate", "30 requests/minute and 200 requests/hour", "All requests to /mcp, including initialize and tools/list."],
            ["Per-organization tool call rate", "Free 10/min; Starter 60/min; Pro 300/min", "Shared across all users and all tools in the organization."],
            ["Per-organization monthly tool call quota", "Free 50; Starter 10,000; Pro 100,000", "Calendar-month plan quota. The Harvey evaluation allocation is described in the Data Handling appendix."],
            ["Decoded file size cap", "10,485,760 bytes (10 MB)", "Applies to upload_file bytes and to every content_url fetch. Rejected before processing."],
            ["Request body in the 25–50 MB range", "Rejected with HTTP 400 + JSON-RPC -32700", "Flask's MAX_CONTENT_LENGTH is 25 MB, but parsing above that limit raises an exception that the /mcp route catches as an invalid-JSON error. A reviewer-verified 26 MiB body returns HTTP 400 with a JSON-RPC envelope and code -32700 (\"Invalid JSON\"), not a bare transport error."],
            ["Request body above 50 MB", "Rejected with HTTP 413 + JSON-RPC -32600", "The /mcp route checks request.content_length against a 50 MB hard cap before parsing. A reviewer-verified 51 MiB body returns HTTP 413 with a JSON-RPC envelope and code -32600 (\"Request body too large\")."],
            ["Tool execution deadline", "60 seconds", "Caller-facing deadline. A timed-out worker may continue running until its external operation (for example a Gemini call) returns."],
            ["URL fetch deadline", "30 seconds", "Overall deadline across all redirects for a content_url fetch."],
            ["Redirect cap", "3 hops", "Each redirect is revalidated as HTTPS to a public destination."],
            ["Temporary file lifetime", "1 hour", "Nominal expiry for uploaded files and binary results. Cleanup is lazy (performed on next access and during subsequent uploads); a process restart may remove files sooner."],
        ],
    )
    add_para(
        doc,
        "All limits apply independently. The per-IP rate cap continues to apply to higher "
        "plans. The IP-level HTTP 429 response is an ordinary JSON error object (not a "
        "JSON-RPC envelope); clients should honor the Retry-After header when present. "
        "HTTP 405 responses to non-POST methods on /mcp are similarly ordinary JSON "
        "error objects. The organization-level rate limit instead surfaces as JSON-RPC "
        "-32003 inside an HTTP 200 response.",
    )
    add_matrix_table(
        doc,
        ["JSON-RPC code", "Meaning", "HTTP correlate"],
        [
            ["-32001", "Missing or invalid authentication for a tools/call request.", "401, with WWW-Authenticate pointing at the protected-resource metadata URL."],
            ["-32002", "Organization monthly quota exhausted.", "200 with JSON-RPC error body."],
            ["-32003", "Organization rate limit exceeded.", "200 with JSON-RPC error body. (The IP-level HTTP 429 enforced at the transport layer is separate and returns an ordinary JSON error object, not a JSON-RPC envelope.)"],
            ["-32004", "Request exceeds the plan's per-call unit limit.", "200 with JSON-RPC error body."],
            ["-32005", "Overall tool execution deadline (60 seconds) exceeded.", "200 with JSON-RPC error body. URL-fetch timeouts are returned as tool errors (isError: true), not under this code."],
            ["-32600", "Invalid JSON-RPC request structure (non-dict body, missing or wrong jsonrpc field, missing method).", "400."],
            ["-32601", "Unknown JSON-RPC method; also unknown tool name on tools/call.", "404 for an unknown method. An unknown tool name on tools/call returns the error inside a 200 response."],
            ["-32602", "Request-unit estimation failed. Returned by the dispatcher with the message \"Could not size request\" when a tool's units_fn raises. Handler-level invalid-parameter cases are surfaced as tool errors (isError: true), not under this code.", "200 with JSON-RPC error body."],
            ["-32700", "Request body is not valid JSON.", "400."],
        ],
    )
    add_para(
        doc,
        "The dispatcher does not run general JSON Schema validation on tool arguments. "
        "Shape, enum, and size checks happen inside each handler and surface as tool-level "
        "errors (result.isError: true) rather than as JSON-RPC -32602 errors. One "
        "dispatcher-level case still emits -32602: if the per-tool request-unit "
        "estimation (units_fn) raises, the dispatcher short-circuits with -32602 and the "
        "message \"Could not size request\". Clients should read both the HTTP status and "
        "the response body on every call: a non-200 HTTP response also carries a JSON-RPC "
        "error body in most cases, and a 200 response can still carry either a JSON-RPC "
        "error or a successful result with isError: true.",
    )

    # ----- APPENDIX B: DATA HANDLING AND EVALUATION ACCESS -----
    add_para(doc, "Appendix B: Data Handling and Evaluation Access", style="Heading 1")
    add_para(doc, "Processing flow", style="Heading 2")
    add_para(
        doc,
        "A typical tool call fans out to a small, documented set of components. Document "
        "and image summarization/translation/analysis invoke Google Gemini on the inferred "
        "extracted text or the fetched image bytes. PII redaction and face obscuring run "
        "locally inside the Synzo process using Microsoft Presidio with spaCy and "
        "MTCNN/OpenCV respectively; those tools do not call a third-party AI API.",
    )
    add_matrix_table(
        doc,
        ["Component", "Role", "Data received"],
        [
            ["MCP client (Harvey)", "Issues JSON-RPC calls over HTTPS to /mcp.", "Tool arguments: filenames, content URLs, target language, mode, blur strength."],
            ["Synzo on Railway", "Terminates HTTPS, authenticates the principal, dispatches tools, meters usage.", "Request bodies, decoded upload bytes (in process memory), fetched document/image bytes."],
            ["Google Gemini", "Backs summarize_document, translate_document, and analyze_image.", "Extracted document text (summarize/translate) or image bytes (analyze_image)."],
            ["Presidio + spaCy (in-process)", "Backs redact_pii.", "Extracted document text."],
            ["MTCNN + OpenCV (in-process)", "Backs detect_faces.", "Fetched image bytes."],
            ["WorkOS AuthKit", "Identity, OAuth authorization, organization membership, password and verification flows.", "User email, authentication factors, organization membership state."],
            ["PostgreSQL (Railway managed)", "Account, membership, API-key, quota, and usage-event metadata.", "Account rows, SHA-256 API-key hashes, per-call usage records (organization, tool, units, status, timestamps)."],
            ["In-process blob store", "Temporary upload bytes and generated binary results.", "Decoded upload bytes and generated PNG/DOCX/PPTX results."],
        ],
    )
    add_para(doc, "Isolation and the bearer-URL exception", style="Heading 2")
    add_para(
        doc,
        "Accounts, memberships, API keys, quotas, and usage events are logically scoped by "
        "organization in a shared PostgreSQL instance. Dashboard operations check "
        "membership and role. Tool execution checks that the request principal resolves to "
        "a valid organization. Isolation is enforced at the application layer; it is not "
        "based on separate databases or physical infrastructure per customer.",
    )
    add_para(
        doc,
        "Temporary file URLs returned by upload_file, redact_pii, and detect_faces embed a "
        "high-entropy unguessable token. Anyone holding the URL can download the file "
        "until its one-hour expiry: there is no per-organization ownership check on the "
        "blob store, and the URL is the capability. Clients must therefore treat these "
        "URLs as access credentials and avoid logging or forwarding them.",
    )
    add_para(doc, "Retention", style="Heading 2")
    add_para(
        doc,
        "Uploaded bytes and generated binaries live in process memory and are swept on "
        "subsequent uploads or on access past expiry; a process restart may evict them "
        "sooner. The one-hour value is a nominal expiry, not a guaranteed deletion deadline. "
        "Usage events are stored in PostgreSQL with the published 90-day retention target "
        "stated in the Synzo privacy policy; automated enforcement of that period is not "
        "demonstrated in the current implementation and remains a pending operational item.",
    )
    add_para(
        doc,
        "Document and image bytes are not stored in PostgreSQL. The usage ledger records "
        "organization, authentication method, tool, units, status, error code, and "
        "timestamp. Diagnostic logs may contain error details and, on model-output parsing "
        "failures, the raw model content returned by Gemini; this package does not claim "
        "content-free logging.",
    )
    add_para(doc, "Evaluation access", style="Heading 2")
    add_para(
        doc,
        "A dedicated Harvey Connector Evaluation organization is provisioned on the "
        "production Synzo service with five member accounts: connector_eval1@harvey.ai "
        "through connector_eval5@harvey.ai. The shared allocation is 10,000 metered tool "
        "calls per calendar month across September through November 2026. September's "
        "balance was 9,994 immediately after the September 10 verification run; current "
        "balance should be confirmed with paul@redmapleresearch.ca before reporting a "
        "live number.",
    )
    add_para(
        doc,
        "To activate an evaluation account, visit https://www.synzo.ai/auth/login, request "
        "password setup for the chosen address, complete email verification, and sign in "
        "selecting Harvey Connector Evaluation when prompted. Then point the MCP client at "
        "https://www.synzo.ai/mcp and complete OAuth authorization. For additional quota, "
        "a later evaluation window, or an organization-scoped API key for scripted "
        "verification, contact paul@redmapleresearch.ca.",
    )
    add_para(doc, "Outstanding verification", style="Heading 2")
    add_para(
        doc,
        "The following items are explicitly unverified in this submission package and "
        "should be treated as open until confirmed with the relevant evidence. They are "
        "listed here so a reviewer does not infer them from silence elsewhere in the "
        "document.",
    )
    add_bullet(doc, "WorkOS OAuth token lifetimes. The Synzo-application values (5-minute access token, 365-day session with 2-day inactivity timeout, 7-day invitations) were read from the WorkOS AuthKit dashboard on October 5, 2026 and are quoted in the Token Security table. The email verification / password-setup link lifetime is not surfaced in the dashboard and operates at the WorkOS AuthKit default; the exact value should be confirmed with WorkOS if a reviewer needs a hard number.")
    add_bullet(doc, "End-to-end Harvey OAuth verification. The authorization-server metadata advertises Authorization Code with PKCE S256, refresh tokens, device code, and Dynamic Client Registration, and the September 10, 2026 record confirms six-tool execution against the Harvey Connector Evaluation organization using a temporary API key. A completed end-to-end Harvey OAuth client registration and per-user authorization flow has not been exercised at the time of this revision.")
    add_bullet(doc, "Harvey Origin allowlist entry. Whether Harvey's MCP client sends an Origin header on requests to /mcp (and if so, what the exact value is for evaluation and production) has not been confirmed with Harvey. A Harvey backend-to-server call may send no Origin header, in which case no allowlist entry is required; a Harvey browser-direct call needs an exact Origin value added to Synzo's allowlist. This item will be resolved by direct confirmation with Harvey during onboarding, independent of any OAuth redirect-URI configuration.")
    add_bullet(doc, "Harvey-workspace to Synzo-organization restriction. The code base does not implement a mapping between a specific Harvey workspace identifier and a specific Synzo organization. Any Harvey user invited into a Synzo organization authenticates as a member of that organization in the normal way; organization membership is Synzo-side, not Harvey-side. A customer-admin control to restrict a Synzo organization to a particular Harvey workspace is not implemented.")
    add_bullet(doc, "Provider processing locations. Processing regions for Google Gemini, WorkOS AuthKit, and the Railway application and database are not pinned by Synzo application code (no region parameter is passed to the Gemini client; no WorkOS region is configured). The published Synzo privacy policy identifies US hosting; an exhaustive list of provider-side processing locations has not been independently verified.")
    add_bullet(doc, "Provider retention and model-training treatment. Google Gemini content-handling terms, WorkOS data-retention terms, and Railway database retention terms as they apply to the Synzo deployment have not been independently confirmed in this package. Reviewers should obtain the relevant provider agreements rather than infer behavior from the Synzo code.")
    add_bullet(doc, "90-day usage-event retention enforcement. The published Synzo privacy policy states a 90-day usage-event retention target. The inspected implementation does not demonstrate an automated purge enforcing that period; deployed cleanup is an open operational item.")
    add_bullet(doc, "Third-party assurance. This specification does not assert SOC 2 Type II, ISO 27001, a completed third-party penetration-test report, or a dedicated prompt-injection review. A May 2026 static-analysis, dependency, and container scan report is available on request and is not equivalent to any of the above. A published Data Processing Addendum and a dedicated Trust Center are not currently identified in the submission materials.")

    # ----- REVISION HISTORY -----
    add_para(doc, "Revision History", style="Heading 1")
    add_matrix_table(
        doc,
        ["Revision", "Date", "Author", "Notes"],
        [
            ["1.0", "5 October 2026", "Paul O'Hagan, Red Maple Research", "Initial Synzo MCP Server Specification. Prepared against repository commit 1adc36e and the September 10, 2026 verification record. Supersedes the September 10 Synzo Harvey technical documentation as the integration contract."],
        ],
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUTPUT))
    print(f"Wrote: {OUTPUT}")


# ---------------------- Per-tool reference writers ----------------------

def _write_upload_file(doc, add_para, add_bullet, add_code, add_arg_table, add_result_table):
    add_para(doc, "upload_file", style="Heading 1")
    add_para(doc, "Stage caller-supplied bytes and receive a temporary Synzo HTTPS URL for use by the other tools.")
    add_para(doc, "Full Description", style="Heading 2")
    add_para(
        doc,
        "The upload_file tool decodes a base64 payload and stores the resulting bytes in "
        "Synzo's in-process blob store. It returns a one-hour HTTPS URL that other Synzo "
        "tools can accept as a content_url, together with the inferred content type and "
        "the decoded byte count. upload_file does not itself call Google Gemini or any "
        "other external service; downstream tools independently enforce their own supported "
        "file-signature checks.",
    )
    add_para(
        doc,
        "The maximum decoded size is 10,485,760 bytes. upload_file estimates the "
        "request's unit cost from the base64 payload length and checks it against the "
        "organization plan's per-call unit limit before executing; a plan with a small "
        "per-call cap can reject an upload below the absolute 10 MB size cap. Successful "
        "execution then decrements the organization's monthly quota (one count per "
        "successful call). The returned URL is a bearer capability: anyone holding it "
        "can download the file until expiry.",
    )
    add_para(doc, "Scopes", style="Heading 2")
    add_para(doc, "Any valid organization-scoped principal. No additional scope is required.")
    add_para(doc, "Call Arguments", style="Heading 2")
    add_arg_table(doc, [
        ["filename", "string", "Required.", "Original filename, including extension. Used to infer content type."],
        ["content_base64", "string", "Required. Decoded bytes ≤ 10,485,760.", "Base64-encoded file bytes. The server rejects decoded payloads larger than 10 MB."],
    ])
    add_para(doc, "Return Results", style="Heading 2")
    add_para(doc, "On success, result.structuredContent contains:")
    add_result_table(doc, [
        ["filename", "string", "Always present.", "Echoed from the input."],
        ["content_url", "string (HTTPS URL)", "Always present.", "Bearer-access URL valid for one hour."],
        ["expires_at", "string (RFC 3339 UTC)", "Always present.", "Nominal expiry timestamp."],
        ["size_bytes", "integer", "Always present.", "Decoded byte count."],
        ["content_type", "string", "Always present.", "MIME type inferred from the filename extension."],
    ])
    add_para(doc, "Example request:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 1,\n'
        '  "method": "tools/call",\n'
        '  "params": {\n'
        '    "name": "upload_file",\n'
        '    "arguments": {\n'
        '      "filename": "sample.pdf",\n'
        '      "content_base64": "<base64>"\n'
        '    }\n'
        '  }\n'
        '}'
    )
    add_para(doc, "Example response:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 1,\n'
        '  "result": {\n'
        '    "isError": false,\n'
        '    "structuredContent": {\n'
        '      "filename": "sample.pdf",\n'
        '      "content_url": "https://www.synzo.ai/u/<token>",\n'
        '      "expires_at": "2026-10-05T18:12:00Z",\n'
        '      "size_bytes": 184231,\n'
        '      "content_type": "application/pdf"\n'
        '    },\n'
        '    "content": [{"type": "text", "text": "<same payload serialized as JSON>"}]\n'
        '  }\n'
        '}'
    )
    add_para(
        doc,
        "Representative failure: a decoded payload above 10,485,760 bytes returns a "
        "tool-level error (result.isError: true) with an explanatory text block, provided "
        "the request first passes the upstream admission checks (HTTP body size, "
        "authentication, organization quota, rate limits, and per-call unit limits). An "
        "HTTP body in the 25–50 MB range is rejected with HTTP 400 and JSON-RPC -32700, "
        "because Flask's parsing exception above MAX_CONTENT_LENGTH is caught by the /mcp "
        "route and reported as an invalid-JSON error. An HTTP body above 50 MB is "
        "rejected with HTTP 413 and JSON-RPC -32600 by the route's explicit size guard. "
        "See Appendix A.",
    )


def _write_summarize(doc, add_para, add_bullet, add_code, add_arg_table, add_result_table):
    add_para(doc, "summarize_document", style="Heading 1")
    add_para(doc, "Classify a document and produce a Markdown summary.")
    add_para(doc, "Full Description", style="Heading 2")
    add_para(
        doc,
        "summarize_document fetches the document at content_url over HTTPS, extracts its "
        "text, and sends the text to Google Gemini. Gemini returns both an inferred document "
        "classification and a Markdown summary. Supported file formats are PDF, DOCX, PPTX, "
        "and XLSX. The tool does not generate a downloadable binary and does not modify the "
        "source file.",
    )
    add_para(
        doc,
        "Text extraction is best-effort for the four supported formats. Scanned PDFs may "
        "produce empty extracted text; the tool does not perform OCR on arbitrary scanned "
        "PDFs. Gemini safety filters may cause the model to decline summarization on some "
        "content; those cases are returned as a tool-level error with isError: true and an "
        "explanatory text block, not as a JSON-RPC error.",
    )
    add_para(doc, "Scopes", style="Heading 2")
    add_para(doc, "Any valid organization-scoped principal. No additional scope is required.")
    add_para(doc, "Call Arguments", style="Heading 2")
    add_arg_table(doc, [
        ["filename", "string", "Required.", "PDF, DOCX, PPTX, or XLSX filename. Used to confirm the supported extension and signature."],
        ["content_url", "string (HTTPS URL)", "Required. Fetched file ≤ 10 MB.", "Location of the document. Must be reachable by Synzo without the caller's authentication headers."],
    ])
    add_para(doc, "Return Results", style="Heading 2")
    add_result_table(doc, [
        ["classification", "string | null", "May be null if the model does not return one.", "Inferred document type (e.g., Contract, Research Paper)."],
        ["summary", "string", "Always present on success.", "Markdown summary of the document."],
        ["filename", "string", "Always present.", "Echoed from the input."],
    ])
    add_para(doc, "Example request:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 2,\n'
        '  "method": "tools/call",\n'
        '  "params": {\n'
        '    "name": "summarize_document",\n'
        '    "arguments": {\n'
        '      "filename": "summarize-sample.pdf",\n'
        '      "content_url": "https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf"\n'
        '    }\n'
        '  }\n'
        '}'
    )
    add_para(doc, "Example response:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 2,\n'
        '  "result": {\n'
        '    "isError": false,\n'
        '    "structuredContent": {\n'
        '      "classification": "Research Paper",\n'
        '      "summary": "## Overview\\n...",\n'
        '      "filename": "summarize-sample.pdf"\n'
        '    },\n'
        '    "content": [{"type": "text", "text": "<same payload serialized as JSON>"}]\n'
        '  }\n'
        '}'
    )
    add_para(
        doc,
        "Representative failure: a content_url to a non-HTTPS host returns a tool error "
        "(isError: true) explaining the HTTPS requirement. A URL-fetch timeout (the "
        "30-second fetch deadline hit) also returns a tool error (isError: true), not a "
        "JSON-RPC error. The JSON-RPC -32005 code is reserved for the overall tool "
        "execution deadline (60 seconds) only.",
    )


def _write_translate(doc, add_para, add_bullet, add_code, add_arg_table, add_result_table):
    add_para(doc, "translate_document", style="Heading 1")
    add_para(doc, "Translate extracted document text into a target language.")
    add_para(doc, "Full Description", style="Heading 2")
    add_para(
        doc,
        "translate_document fetches the document at content_url, extracts its text, and "
        "sends the text to Google Gemini with the requested target_language. The tool "
        "returns the translation as Markdown text; it does not produce a translated Office "
        "file. Supported input formats are DOCX, PPTX, and XLSX. PDF is not supported by "
        "this tool.",
    )
    add_para(
        doc,
        "Target language is accepted as a human-readable English language name such as "
        "French, Spanish, or Simplified Chinese. The input schema advertises length bounds "
        "of 2 to 64 characters on target_language; the handler enforces presence of the "
        "field. A Gemini safety-filter refusal returns a tool error (isError: true) rather "
        "than a JSON-RPC error.",
    )
    add_para(doc, "Scopes", style="Heading 2")
    add_para(doc, "Any valid organization-scoped principal. No additional scope is required.")
    add_para(doc, "Call Arguments", style="Heading 2")
    add_arg_table(doc, [
        ["filename", "string", "Required.", "DOCX, PPTX, or XLSX filename. Used to confirm the supported extension and signature."],
        ["content_url", "string (HTTPS URL)", "Required. Fetched file ≤ 10 MB.", "Location of the document. Must be reachable by Synzo without the caller's authentication headers."],
        ["target_language", "string", "Required. Advertised length 2–64.", "English language name for the destination language."],
    ])
    add_para(doc, "Return Results", style="Heading 2")
    add_result_table(doc, [
        ["filename", "string", "Always present.", "Echoed from the input."],
        ["target_language", "string", "Always present.", "Echoed from the input."],
        ["translated_text", "string", "Always present on success.", "Markdown translation of the extracted document text."],
    ])
    add_para(doc, "Example request:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 3,\n'
        '  "method": "tools/call",\n'
        '  "params": {\n'
        '    "name": "translate_document",\n'
        '    "arguments": {\n'
        '      "filename": "translate-sample.docx",\n'
        '      "content_url": "https://www.synzo.ai/static/reviewer-samples/translate-sample.docx",\n'
        '      "target_language": "French"\n'
        '    }\n'
        '  }\n'
        '}'
    )
    add_para(doc, "Example response:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 3,\n'
        '  "result": {\n'
        '    "isError": false,\n'
        '    "structuredContent": {\n'
        '      "filename": "translate-sample.docx",\n'
        '      "target_language": "French",\n'
        '      "translated_text": "## Résumé\\n..."\n'
        '    },\n'
        '    "content": [{"type": "text", "text": "<same payload serialized as JSON>"}]\n'
        '  }\n'
        '}'
    )
    add_para(
        doc,
        "Representative failure: a PDF filename returns a tool error (isError: true) "
        "indicating the format is not supported by translate_document; use "
        "summarize_document instead.",
    )


def _write_redact(doc, add_para, add_bullet, add_code, add_arg_table, add_result_table):
    add_para(doc, "redact_pii", style="Heading 1")
    add_para(doc, "Detect and redact personally identifiable information in a document.")
    add_para(doc, "Full Description", style="Heading 2")
    add_para(
        doc,
        "redact_pii fetches the document at content_url and runs Microsoft Presidio with "
        "spaCy inside the Synzo process to locate personally identifiable text. Detected "
        "characters are replaced with block symbols. The output is a new copy of the "
        "document in its original format (DOCX or PPTX), stored in the in-process blob "
        "store with a one-hour expiry URL. The source file is not modified. redact_pii "
        "does not send document content to Google Gemini or to any Microsoft service.",
    )
    add_para(
        doc,
        "Detection is probabilistic and depends on the recognizers configured in Presidio "
        "and on the structural features of the input document. Text embedded in images, "
        "and text in document structures not covered by the extractor, may not be "
        "detected. Downstream review is required before disclosure; the tool does not "
        "claim complete anonymization. PDF is not supported.",
    )
    add_para(doc, "Scopes", style="Heading 2")
    add_para(doc, "Any valid organization-scoped principal. No additional scope is required.")
    add_para(doc, "Call Arguments", style="Heading 2")
    add_arg_table(doc, [
        ["filename", "string", "Required.", "DOCX or PPTX filename. Used to confirm the supported extension and signature."],
        ["content_url", "string (HTTPS URL)", "Required. Fetched file ≤ 10 MB.", "Location of the document. Must be reachable by Synzo without the caller's authentication headers."],
    ])
    add_para(doc, "Return Results", style="Heading 2")
    add_result_table(doc, [
        ["filename", "string", "Always present on success.", "Name of the generated redacted copy, formed as redacted_<input filename>. Not the input filename itself."],
        ["result_url", "string (HTTPS URL)", "Always present on success.", "Bearer-access URL to the redacted copy, valid for one hour."],
        ["expires_at", "string (RFC 3339 UTC)", "Always present on success.", "Nominal expiry timestamp."],
        ["mimetype", "string", "Always present on success.", "MIME type of the redacted copy (matches the input format)."],
        ["original_size_bytes", "integer", "Always present on success.", "Size of the fetched source document."],
        ["redacted_size_bytes", "integer", "Always present on success.", "Size of the generated redacted copy."],
    ])
    add_para(doc, "Example request:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 4,\n'
        '  "method": "tools/call",\n'
        '  "params": {\n'
        '    "name": "redact_pii",\n'
        '    "arguments": {\n'
        '      "filename": "redact-sample.docx",\n'
        '      "content_url": "https://www.synzo.ai/static/reviewer-samples/redact-sample.docx"\n'
        '    }\n'
        '  }\n'
        '}'
    )
    add_para(doc, "Example response:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 4,\n'
        '  "result": {\n'
        '    "isError": false,\n'
        '    "structuredContent": {\n'
        '      "filename": "redacted_redact-sample.docx",\n'
        '      "result_url": "https://www.synzo.ai/u/<token>",\n'
        '      "expires_at": "2026-10-05T18:30:00Z",\n'
        '      "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",\n'
        '      "original_size_bytes": 92310,\n'
        '      "redacted_size_bytes": 93102\n'
        '    },\n'
        '    "content": [{"type": "text", "text": "<same payload serialized as JSON>"}]\n'
        '  }\n'
        '}'
    )
    add_para(
        doc,
        "Representative failure: a PPTX whose content is entirely inside embedded images "
        "returns a successful call whose redacted copy is visually unchanged; this is a "
        "limitation of text-based detection and must be covered by human review.",
    )


def _write_analyze_image(doc, add_para, add_bullet, add_code, add_arg_table, add_result_table):
    add_para(doc, "analyze_image", style="Heading 1")
    add_para(doc, "Describe an image, extract visible text, and flag potentially sensitive content.")
    add_para(doc, "Full Description", style="Heading 2")
    add_para(
        doc,
        "analyze_image fetches the image at content_url and sends the bytes to Google "
        "Gemini vision. It returns a structured JSON object with a short description, a "
        "longer rich description, OCR-extracted text, detected objects, and three safety "
        "flags. In parallel, Synzo computes a dominant-color palette from the image "
        "locally. The source image is not modified and no binary result is generated.",
    )
    add_para(
        doc,
        "The analysis object is parsed from the Gemini response. Synzo does not currently "
        "publish an outputSchema for this tool, and the server does not validate the full "
        "nested analysis structure. The fields below describe the expected shape; "
        "individual values may be absent or empty when the model does not return them. The "
        "tool must be treated as model-generated: the OCR text, object list, and safety "
        "flags are useful signals, not ground truth.",
    )
    add_para(doc, "Supported formats: JPG, JPEG, PNG, WEBP, HEIC, HEIF.")
    add_para(doc, "Scopes", style="Heading 2")
    add_para(doc, "Any valid organization-scoped principal. No additional scope is required.")
    add_para(doc, "Call Arguments", style="Heading 2")
    add_arg_table(doc, [
        ["filename", "string", "Required.", "JPG, JPEG, PNG, WEBP, HEIC, or HEIF filename."],
        ["content_url", "string (HTTPS URL)", "Required. Fetched file ≤ 10 MB.", "Location of the image. Must be reachable by Synzo without the caller's authentication headers."],
    ])
    add_para(doc, "Return Results", style="Heading 2")
    add_result_table(doc, [
        ["filename", "string", "Always present.", "Echoed from the input."],
        ["analysis", "object", "Always present on success.", "Nested structure described below."],
        ["dominant_colors", "array of strings", "Always present on success.", "Hexadecimal color codes (for example #3F6BAE) ordered by prominence."],
        ["analysis.description", "string", "Expected; may be empty.", "One- to two-sentence summary of the scene."],
        ["analysis.rich_description", "string", "Expected; may be empty.", "Longer narrative description."],
        ["analysis.extracted_text", "string", "Expected; may be empty.", "OCR text visible in the image."],
        ["analysis.detected_objects", "array of strings", "Expected; may be empty.", "Named objects or entities detected."],
        ["analysis.safety_flags", "object", "Expected; may be absent.", "Flags described below."],
        ["analysis.safety_flags.contains_people", "boolean", "Expected when safety_flags is present.", "Whether people are visible."],
        ["analysis.safety_flags.contains_potential_pii", "boolean", "Expected when safety_flags is present.", "Whether PII (such as visible identity documents) is suspected."],
        ["analysis.safety_flags.is_graphic_or_violent", "boolean", "Expected when safety_flags is present.", "Whether the content appears graphic or violent."],
    ])
    add_para(doc, "Example request:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 5,\n'
        '  "method": "tools/call",\n'
        '  "params": {\n'
        '    "name": "analyze_image",\n'
        '    "arguments": {\n'
        '      "filename": "analyze-sample.jpg",\n'
        '      "content_url": "https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg"\n'
        '    }\n'
        '  }\n'
        '}'
    )
    add_para(doc, "Example response:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 5,\n'
        '  "result": {\n'
        '    "isError": false,\n'
        '    "structuredContent": {\n'
        '      "filename": "analyze-sample.jpg",\n'
        '      "analysis": {\n'
        '        "description": "A street scene at dusk.",\n'
        '        "rich_description": "Pedestrians cross a wet city street...",\n'
        '        "extracted_text": "ONE WAY",\n'
        '        "detected_objects": ["person", "traffic sign", "car"],\n'
        '        "safety_flags": {\n'
        '          "contains_people": true,\n'
        '          "contains_potential_pii": false,\n'
        '          "is_graphic_or_violent": false\n'
        '        }\n'
        '      },\n'
        '      "dominant_colors": ["#3F6BAE", "#141821", "#C9B57A"]\n'
        '    },\n'
        '    "content": [{"type": "text", "text": "<same payload serialized as JSON>"}]\n'
        '  }\n'
        '}'
    )
    add_para(
        doc,
        "Representative failure: a Gemini safety refusal on sensitive content returns a "
        "tool error (isError: true) explaining that the model declined, rather than a "
        "partially-populated analysis object.",
    )


def _write_detect_faces(doc, add_para, add_bullet, add_code, add_arg_table, add_result_table):
    add_para(doc, "detect_faces", style="Heading 1")
    add_para(doc, "Detect faces in an image and return a PNG with the faces blurred or redacted.")
    add_para(doc, "Full Description", style="Heading 2")
    add_para(
        doc,
        "detect_faces fetches the image at content_url, locates faces using MTCNN with "
        "OpenCV running inside the Synzo process, and generates a PNG in which detected "
        "faces are either blurred or covered with opaque rectangles. The source image is "
        "not modified. No face-recognition is performed: detected faces are not matched to "
        "named individuals and no identity attributes are returned.",
    )
    add_para(
        doc,
        "The response does not include face counts, bounding boxes, or confidence scores. "
        "If no faces are detected, the returned PNG shows the original visual content "
        "unobscured; a client should assume this outcome is possible on any input. "
        "detect_faces does not call a third-party AI API.",
    )
    add_para(doc, "Supported formats: JPG, JPEG, PNG, WEBP, HEIC, HEIF. Output is always PNG.")
    add_para(doc, "Scopes", style="Heading 2")
    add_para(doc, "Any valid organization-scoped principal. No additional scope is required.")
    add_para(doc, "Call Arguments", style="Heading 2")
    add_arg_table(doc, [
        ["filename", "string", "Required.", "JPG, JPEG, PNG, WEBP, HEIC, or HEIF filename."],
        ["content_url", "string (HTTPS URL)", "Required. Fetched file ≤ 10 MB.", "Location of the image."],
        ["mode", "string", "Optional. Enum: blur, redact. Default blur.", "blur applies a Gaussian blur to detected faces; redact overlays opaque rectangles."],
        ["blur_strength", "integer", "Optional. Enum: 1, 2, 3. Default 2.", "1 = light blur; 2 = strong blur; 3 = opaque fill. Ignored when mode is redact."],
    ])
    add_para(doc, "Return Results", style="Heading 2")
    add_result_table(doc, [
        ["filename", "string", "Always present on success.", "Name of the generated PNG, formed as <input basename>-faces-blurred.png when mode is blur or <input basename>-faces-redacted.png when mode is redact. Not the input filename itself."],
        ["mode", "string", "Always present.", "Echoed from the input (or the default)."],
        ["result_url", "string (HTTPS URL)", "Always present on success.", "Bearer-access URL to the generated PNG, valid for one hour."],
        ["expires_at", "string (RFC 3339 UTC)", "Always present on success.", "Nominal expiry timestamp."],
        ["mimetype", "string", "Always present on success.", "Always image/png."],
    ])
    add_para(doc, "Example request:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 6,\n'
        '  "method": "tools/call",\n'
        '  "params": {\n'
        '    "name": "detect_faces",\n'
        '    "arguments": {\n'
        '      "filename": "detect-faces-sample.jpg",\n'
        '      "content_url": "https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg",\n'
        '      "mode": "redact"\n'
        '    }\n'
        '  }\n'
        '}'
    )
    add_para(doc, "Example response:")
    add_code(doc,
        '{\n'
        '  "jsonrpc": "2.0",\n'
        '  "id": 6,\n'
        '  "result": {\n'
        '    "isError": false,\n'
        '    "structuredContent": {\n'
        '      "filename": "detect-faces-sample-faces-redacted.png",\n'
        '      "mode": "redact",\n'
        '      "result_url": "https://www.synzo.ai/u/<token>",\n'
        '      "expires_at": "2026-10-05T18:45:00Z",\n'
        '      "mimetype": "image/png"\n'
        '    },\n'
        '    "content": [{"type": "text", "text": "<same payload serialized as JSON>"}]\n'
        '  }\n'
        '}'
    )
    add_para(
        doc,
        "Representative failure: an unknown mode value is rejected before processing with "
        "a tool-level error (result.isError: true) identifying the invalid enum. A "
        "blur_strength value outside {1, 2, 3} returns the same tool-level error. These "
        "are tool errors, not JSON-RPC -32602 errors: the server's dispatcher does not run "
        "general JSON Schema validation, so argument-shape checks happen inside each "
        "handler.",
    )


if __name__ == "__main__":
    main()
