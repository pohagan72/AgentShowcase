# Synzo

Synzo is a document-intelligence API for AI agents, applications, and people. It exposes five capabilities — summarize, translate, redact PII, analyze images, detect faces — through three surfaces sharing one backend: a public HTMX site, a metered JSON API, and an MCP server.

- **Live site:** [www.synzo.ai](https://www.synzo.ai)
- **MCP endpoint:** `https://www.synzo.ai/mcp`
- **OAuth discovery:** `https://www.synzo.ai/.well-known/oauth-protected-resource`
- **Full plan and architecture:** [MCP_SUBMISSION_PLAN.md](MCP_SUBMISSION_PLAN.md)

> Status: Phase 0 / 1 / 1.5 / 2 / 2.5.A shipped and verified live. All five MCP tools (`summarize_document`, `translate_document`, `redact_pii`, `analyze_image`, `detect_faces`) are live at `https://www.synzo.ai/mcp`. `transcribe_audio` is dropped from submission scope. Phase 3 is ~90% shipped — see [MCP_SUBMISSION_PLAN.md](MCP_SUBMISSION_PLAN.md) for the remaining items.

---

## What it does

| Capability | Tool name | Input | Output |
|---|---|---|---|
| Summarize a document | `summarize_document` | PDF / DOCX / PPTX / XLSX ≤10 MB | Classification + structured markdown summary |
| Translate a document | `translate_document` | DOCX / PPTX / XLSX ≤10 MB + target language | Translated markdown text |
| Redact PII | `redact_pii` | DOCX / PPTX ≤10 MB | Redacted document (base64, same format) |
| Analyze an image | `analyze_image` | JPG / PNG / WEBP / HEIC / HEIF ≤10 MB | Description, OCR text, safety flags, detected objects, dominant colors |
| Detect and obscure faces | `detect_faces` | JPG / PNG / WEBP / HEIC / HEIF ≤10 MB + mode | PNG with each face blurred or redacted |

All tools share the same auth, quota, rate-limit, and metering pipeline ([auth.py](auth.py)). Every call is scoped to a single organization; usage is tracked per-org in `usage_events`.

---

## The three surfaces

| Surface | Purpose | Auth |
|---|---|---|
| Public HTML/HTMX (`/`, `/summarizer`, `/translator`, ...) | Portfolio demo site | None |
| MCP (`/mcp`) | Claude Desktop / claude.ai / any MCP client | OAuth 2.0 bearer JWT (WorkOS AuthKit) or `sk_synzo_…` API key |
| JSON API (`/api/v1/*`) | Programmatic callers (paid customers, scripts) | Same as MCP |
| Dashboard (`/auth/*`, `/dashboard/*`) | Org management — issue keys, invite members, see usage | Flask session cookie (WorkOS-issued) |

Each surface uses a different decorator (`@require_auth` for bearer-token paths, `@require_session` for cookie paths) but resolves to the same `Principal(org_id, plan, …)`. Downstream business logic doesn't care which surface a request came in on.

See [MCP_SUBMISSION_PLAN.md §3](MCP_SUBMISSION_PLAN.md) for the architecture diagram.

---

## Using Synzo over MCP

### 1. Get an API key (during early access)

Sign up at [www.synzo.ai/auth/login](https://www.synzo.ai/auth/login) → land on the dashboard → click **Issue API key**. Keys are `sk_synzo_…` prefixed and shown exactly once. The free tier covers 50 calls/month, up to 20 pages per call.

OAuth via WorkOS AuthKit is wired for `claude.ai` and Claude Desktop; the directory listing will go live once the submission is approved.

### 2. Connect from an MCP client

The endpoint speaks the [2025-06-18 Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) over HTTP POST with `Content-Type: application/json` (no SSE upgrade — synchronous tool shapes).

```bash
# Initialize handshake
curl -X POST https://www.synzo.ai/mcp \
  -H "Authorization: Bearer sk_synzo_..." \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}'
```

```bash
# List tools
curl -X POST https://www.synzo.ai/mcp \
  -H "Authorization: Bearer sk_synzo_..." \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

```bash
# Call a tool — base64 the file and pass it as content_base64
B64=$(base64 -w0 contract.pdf)
curl -X POST https://www.synzo.ai/mcp \
  -H "Authorization: Bearer sk_synzo_..." \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"summarize_document\",\"arguments\":{\"filename\":\"contract.pdf\",\"content_base64\":\"$B64\"}}}"
```

### 3. Validate with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Point it at `https://www.synzo.ai/mcp` with your API key in the Authorization header. Confirm `initialize`, `tools/list`, and a `tools/call` round-trip work.

---

## Error shapes

The MCP layer surfaces auth / quota / rate-limit failures as JSON-RPC protocol errors (private code range `-32000..-32099`). Argument failures from inside a tool surface as `isError: true` in the tool-result envelope so a calling model can read the reason and recover.

| Condition | Where it shows up | Code / shape |
|---|---|---|
| Missing or invalid bearer | JSON-RPC error envelope | `-32001 MCP_AUTH_REQUIRED` |
| Monthly quota exhausted | JSON-RPC error envelope | `-32002 MCP_QUOTA_EXHAUSTED` |
| Per-org rate limit hit | JSON-RPC error envelope | `-32003 MCP_RATE_LIMITED` |
| Single call exceeds per-call cap | JSON-RPC error envelope | `-32004 MCP_UNITS_EXCEEDED` |
| Tool exceeded 60s wall-clock (quota refunded) | JSON-RPC error envelope | `-32005 MCP_TIMEOUT` |
| Bad argument (wrong file type, bad base64) | Tool result with `isError: true` | Human-readable text content |
| Unknown method / malformed JSON | JSON-RPC standard codes | `-32601` / `-32700` / `-32600` |

Quota is decremented atomically before a tool runs and refunded on any handler exception, so customers never pay for our bugs.

---

## Running locally

```bash
# clone, then from the repo root
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env  # fill in WorkOS + Gemini + DATABASE_URL
.venv/Scripts/python.exe -m alembic upgrade head

# On Windows PowerShell:
#   $env:FLASK_DEBUG = "1"; .venv/Scripts/python.exe app.py
# On macOS/Linux:
#   FLASK_DEBUG=1 .venv/bin/python app.py
```

The app boots on port 5001. Run tests with:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Currently 186/186 passing. The test suite forces `DATABASE_URL=sqlite:///:memory:` so it never touches Railway Postgres.

---

## Stack

- **Backend:** Python 3.14, Flask, Waitress (WSGI), SQLAlchemy + Alembic
- **Persistence:** Postgres on Railway (auth/quota/metering); ephemeral S3-compatible storage for file round-trips
- **Identity:** WorkOS AuthKit (OAuth 2.0 / OIDC, JWT bearer)
- **AI:** Google Gemini (summarization, translation, vision); Microsoft Presidio + spaCy (PII detection); MTCNN + OpenCV (face detection)
- **Frontend:** HTMX over Jinja2 templates; Tailwind utility classes
- **Hosting:** Railway (Postgres + app + edge TLS)
- **MCP:** hand-rolled JSON-RPC blueprint ([mcp_routes.py](mcp_routes.py)) over Flask; no `fastmcp` (would force an ASGI swap)

---

## Roadmap

The full plan, including the multi-tenant data model, abuse defense layers, and submission deliverables, lives in [MCP_SUBMISSION_PLAN.md](MCP_SUBMISSION_PLAN.md). Open items:

- Live MCP Inspector walkthrough against the deployed `/mcp` endpoint
- API-ownership framing for Gemini in the submission-form notes field
- Phase 3.5 submission package — Anthropic Directory form deliverables (listing copy, capability classification, 3–5 promotional screenshots, square logo, reviewer-bundle dry-run from a clean browser)
- Phase 2.5.B post-submission: Redis + SSE + worker dyno to stop blocking Waitress threads on Gemini calls
- Phase 4 post-submission: Stripe + paid tiers

## License & contact

Source-available; license TBD. Built by Paul O'Hagan.
