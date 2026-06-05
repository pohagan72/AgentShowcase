# Synzo → Anthropic MCP Connector Directory: Submission Plan

> **Status as of 2026-06-05:** Phase 0, Phase 1, Phase 1.5 complete and verified live. **Phase 2 tool surface is now complete locally** — five tools (`summarize_document`, `translate_document`, `redact_pii`, `analyze_image`, `detect_faces`) wired end-to-end through the existing auth/quota/metering pipeline, 33 MCP tests green / 82 total. `transcribe_audio` is deferred: its underlying `features/transcription/routes.py` is a stub (no Gemini wiring), so shipping it via MCP would be misleading — Phase 3.5 use-case copy and the §6 checklist are updated to reflect 5 tools, not 6. The Phase 2 vertical slice (just `summarize_document`) is deployed and smoke-tested live on `https://www.synzo.ai/mcp`; the four new tools are local-only pending the next deploy. Live MCP Inspector validation is still the gate to Phase 3 — see §6.
>
> Phase 1 shipped: baseline schema (`orgs`, `api_keys`, `quotas`, `usage_events`) on Railway Postgres at Alembic `0001_baseline`; [auth.py](auth.py) with `Principal`, `require_auth`, WorkOS JWT verification, API-key resolution, atomic quota decrement, refund-on-exception; POC endpoint `POST /api/v1/summarize` verified end-to-end; failure-path test suite (402/413/429/refund/refund-clamp) green.
>
> Phase 1.5 shipped: multi-tenant user/membership graph at Alembic `0002_users_memberships`; WorkOS AuthKit OAuth flow via `/auth/{login,callback,logout}` ([auth_routes.py](auth_routes.py)); cookie-session dashboard at `/dashboard/*` with role-gated key issuance, member invites, role updates, and org switching ([auth_session.py](auth_session.py) — `require_session` / `require_role`); `_resolve_oauth` now populates the membership graph for OAuth callers too; public-site polish (nav sign-in/sign-up, `/pricing` reading live from `PLANS`, homepage SaaS hero). Full test suite: 47/47 passing (including the cross-tenant isolation suite proving 404-not-200 on every dashboard mutation route). End-to-end verified live 2026-06-05: signed up as `paulohagan@…`, org auto-created, issued key from dashboard, called `/api/v1/summarize` against prod with that key, watched quota tick 50→49 and `last_used_at` populate. `WORKOS_ISSUER` captured and set in Railway + `.env`. One SDK-shape bug surfaced and fixed during deploy (`create_organization_membership` takes typed `role`, not `role_slug` — see commit `79b99a3`).
>
> **Path A (multi-tenant) is the model.** See §3.4 for the data model and §8 for why we rejected Path B.
>
> **Owner:** Paul O'Hagan
> **Goal:** Ship Synzo as an approved connector in Anthropic's MCP Connector Directory, while building the foundation for a paid metered-API business on the same backend.

---

## 1. Where we are

Synzo is a Flask + HTMX web app deployed on Railway. It exposes document intelligence features (summarization, translation, PII redaction, multimedia analysis, transcription) through an HTML UI. Backed by Google Gemini, Microsoft Presidio, S3-compatible storage.

Phase 1 turned the codebase from "Flask portfolio app" into "Flask portfolio app + authenticated metered JSON API." The MCP protocol layer still doesn't exist — that's Phase 2.

### Audit summary (what's missing for Anthropic submission)

| Category | Status |
|---|---|
| API-key auth + atomic quota + metering | **IMPLEMENTED** ([auth.py](auth.py)) |
| Failure-path test coverage (402/413/429/refund) | **IMPLEMENTED** ([tests/test_auth_failures.py](tests/test_auth_failures.py)) |
| OAuth JWT verification code | **IMPLEMENTED + VERIFIED LIVE** (`WORKOS_ISSUER` captured 2026-06-05) |
| Multi-tenant user/membership model | **IMPLEMENTED** ([db/models.py](db/models.py): `User`, `OrgMembership`; Alembic `0002_users_memberships`) |
| WorkOS signup/login flow + dashboard | **IMPLEMENTED + VERIFIED LIVE** ([auth_routes.py](auth_routes.py), [templates/dashboard.html](templates/dashboard.html)) |
| MCP server / protocol handlers | **IMPLEMENTED** ([mcp_routes.py](mcp_routes.py): JSON-RPC dispatch for `initialize` / `tools/list` / `tools/call` / `ping` / `notifications/initialized`) |
| Tool registry, JSON Schemas, annotations | **IMPLEMENTED** ([mcp_tools.py](mcp_tools.py): 5 tools shipped — summarize, translate, redact_pii, analyze_image, detect_faces; transcribe_audio deferred — see §6 footnote) |
| Streamable HTTP / SSE transport | **IMPLEMENTED** (Flask-native, `application/json` responses — synchronous tool shapes don't need SSE upgrade; see §6 Phase 2 footnote) |
| `/.well-known/oauth-protected-resource` + CORS for `claude.ai` | **IMPLEMENTED** ([mcp_routes.py](mcp_routes.py): RFC 9728 discovery, Origin allowlist with claude.ai + localhost for MCP Inspector) |
| MCP Inspector validation | MISSING — Phase 3 |
| Tenant-isolation test suite | **IMPLEMENTED** ([tests/test_multi_tenant_isolation.py](tests/test_multi_tenant_isolation.py)) |
| Security headers, rate limiting, CSRF | IMPLEMENTED (Flask side) |
| Logging | IMPLEMENTED |
| HTTPS / TLS | Handled by Railway edge |

---

## 2. The three audiences, one backend

We are building **one backend that serves three authentication paths**:

1. **MCP path** — Claude Desktop / claude.ai connects via OAuth 2.0, bearer JWTs. What Anthropic's audit cares about. Resolves to `Principal(org_id, plan, auth_method='oauth')`.
2. **Paid API path** — Developers buy quota, get an API key (`sk_synzo_...`), call the endpoints from their own code. Resolves to `Principal(org_id, plan, auth_method='api_key')`.
3. **Human-via-browser path** — A user signs into the dashboard with a WorkOS session cookie to manage their org: issue/revoke keys, invite teammates, see usage. **Not** bearer-authed; uses a Flask session. Doesn't pass through `require_auth`; uses a separate `require_session` decorator that resolves the same `Principal` from the cookie.

All three resolve to the same `Principal(org_id, plan)`. All downstream logic — quotas, rate limits, metering, audit logs, key management, member management — is shared and **always scoped on `Principal.org_id`**. That's the invariant the multi-tenant model rests on.

---

## 3. Architecture (decided)

```
                    Claude Desktop / claude.ai
                              │ OAuth bearer JWT (WorkOS-issued, carries org_id)
                              ▼
  curl / customer code  ──▶  Flask: @require_auth  ──▶  Principal(org_id, plan)
  sk_synzo_abc123              ├─ identify caller (OAuth or API key)
                               ├─ check per-org RPM (in-memory, Redis later)
                               ├─ atomic quota decrement (Postgres)
                               ├─ run handler → Gemini / Presidio
                               └─ insert usage_event (Postgres)

  Browser (cookie session) ─▶  Flask: @require_session  ──▶  Principal(org_id, plan)
                               ├─ dashboard: usage / keys / members
                               └─ org switcher if user is in >1 org
                              ▼
                       Postgres + Redis on Railway
```

### 3.1 Identity stack: **WorkOS AuthKit**

Free up to 1M MAU (we will never approach this). DCR + auth-server metadata out of the box. Purpose-built for MCP / AI-agent auth flows. Zero infra to operate vs. self-hosted Keycloak.

Rejected alternatives: Keycloak on Railway ($10–20/mo + day of yak-shaving); Stytch (viable backup); Auth0 (more config, no advantage at our scale); self-rolled OAuth (never).

### 3.2 Persistence

**Postgres on Railway** (~$5/mo). Same project as the Flask app. Reasons over alternatives:
- **Atomic quota decrement** — concurrent calls cannot both pass when 1 unit remains. Needs transactions.
- **Durability** — `quotas` is money; `usage_events` is the billing source of truth. Loss is unacceptable.
- **Queryability** — "show this org their usage this month" is a `WHERE org_id = ? AND created_at > ?` query.

| Option | Verdict | Reason |
|---|---|---|
| **Postgres on Railway** | **Chosen** | Same dashboard, sub-ms latency, ACID transactions, mature Python ecosystem |
| SQLite on a Railway volume | Rejected | Single-writer file lock breaks at 2 replicas; backups become ours; not safe for billing data |
| Neon / Supabase | Fallback if $5/mo matters | Same Postgres semantics, extra 10–30ms network hop, second vendor dashboard |
| Turso / LibSQL | Rejected for v1 | Newer ecosystem; not worth being early adopter |
| Redis only (no SQL) | Rejected | Redis is for ephemeral counters, not durable billing history |
| JSON file / in-memory dict | Hard no | Lose the file → lose all billing records |

**Redis on Railway** (~$5/mo) — **deferred**. Needed only when scaling past one Railway replica (Flask-Limiter + the in-memory per-org RPM bucket both want cross-replica state). Single-replica MVP works in-memory. JWKS for WorkOS token verification caches in process memory (rebuilt on restart, fine).

### 3.3 Two URL surfaces, one Flask app

Public HTML/HTMX routes (`/`, `/summarizer`, `/process/*`, etc.) stay unauthenticated and CSRF-protected — that's the portfolio site. The `/api/v1/*` JSON blueprint is `@require_auth`-protected and CSRF-exempt — for MCP tool handlers (Phase 2) and paid API customers. The `/auth/*` and `/dashboard/*` routes (Phase 1.5) are session-cookie-authenticated via `@require_session`, also CSRF-protected (they're cookie-based and human-driven).

**Never put `@require_auth` on an HTMX endpoint:** it returns JSON 401, which the browser UI can't render, and instantly breaks the public site. New tool capabilities get wired into *both* the public HTMX surface and the `/api/v1/*` surface, sharing the same backing module under `features/`.

### 3.4 Multi-tenant data model

Synzo is **multi-tenant from row zero**: every user belongs to one or more organizations; every API call resolves to exactly one organization; every query that returns tenant-owned data scopes on `org_id`. WorkOS owns the identity layer; we mirror the parts we need into our DB.

Seven tables (four exist, three new in Phase 1.5, one deferred to Phase 4):

```sql
-- EXISTING (Phase 1, Alembic 0001_baseline):
orgs              -- one row per organization. mirrors WorkOS org via workos_org_id.
api_keys          -- hashed sk_synzo_... keys, FK to orgs.id
quotas            -- per-org per-period call counter, decremented atomically
usage_events      -- append-only audit log + billing source of truth

-- NEW (Phase 1.5, Alembic 0002_users_memberships):
users             -- mirrors WorkOS users via workos_user_id (unique). email, last_seen_at.
org_memberships   -- (user_id, org_id, role). role ∈ {'owner','admin','member'}.

-- DEFERRED (Phase 4):
stripe_customers  -- (org_id, stripe_customer_id, subscription_id, status, current_period_end)
```

**Role semantics:**
- `owner` — billing, delete org, transfer ownership, change other members' roles. Exactly one per org (the user who created it; transferable).
- `admin` — issue/revoke keys, invite/remove members, change non-owner roles to non-owner. Cannot promote to owner. Cannot delete the org.
- `member` — call the API using the org's keys, view their own usage. Cannot manage keys or members. Read-only on org settings.

**Invitation semantics:** invited members inherit the org's plan and share the org's quota pool. Quota is org-scoped, not user-scoped. (When Stripe lands in Phase 4, billing is per-org with per-seat pricing; this model lines up natively.)

**Multi-org users:** a user can belong to multiple orgs (e.g., personal workspace + employer's workspace). AuthKit's hosted UI shows an org picker on sign-in if the user has memberships in more than one. The dashboard has a `/dashboard/switch-org/<org_id>` route that re-issues the session for a different org the user is a member of.

**The tenant-isolation invariant (non-negotiable):** every query in `/dashboard/*`, `/api/v1/*`, and (future) MCP tool handlers must include `WHERE org_id = :principal_org_id` for any tenant-owned table. Tests in `tests/test_multi_tenant_isolation.py` (Phase 1.5) enforce this by creating two orgs and asserting Org A can't read or mutate Org B's data through any public route.

---

## 4. Abuse defense (the layered model)

Threats that actually matter, ranked by expected cost:

1. **Gemini bill blowup** — someone scripts a free endpoint to burn quota.
2. **Bot signups farming free tier** — appears once a free tier exists.
3. **DoS via large uploads** — 500MB PDF, zip bomb, malformed PPTX.
4. **Credential stuffing** — relatively low impact for our shape.

Defense rings, cheapest first. **All free except Redis ($5/mo) and Cloudflare (only if needed).**

| Ring | What it stops | Tool |
|---|---|---|
| 1. Rate limiting (per-IP + per-org + per-key + global) | Bursts | Flask-Limiter + Redis |
| 2. Quotas (calls/month + units/call) | Sustained drain | Postgres |
| 3. Hard input limits (size, pages, time) | DoS, malformed files | Flask config + magic-byte check |
| 4. Email verification + Turnstile CAPTCHA | Bot signups | WorkOS + Cloudflare Turnstile |
| 5. Anomaly detection + Gemini spend cap | Catastrophic abuse | Google Cloud + log alerts |
| 6. Cloudflare in front of Railway | DDoS, scrapers | Cloudflare free tier (only if needed) |
| 7. API-key controls (rotation, per-key limits, auto-disable) | Compromised customer keys | Built into our schema |

**The single most important line of defense is the Gemini spend cap in Google Cloud Console.** Set it before going public. If free tier should cost ≤$50/mo, cap Gemini at $75/mo.

---

## 5. The middleware (shipped)

One decorator, used by Flask routes today and MCP tool handlers in Phase 2. Lives in [auth.py](auth.py).

```python
@require_auth(tool_name="summarize_document",
              units_fn=lambda req: estimate_pages(req.files["doc"]))
def handler(...):
    ...
```

The decorator handles, in order:
1. Identify caller (OAuth JWT or API key, distinguished by `sk_synzo_` prefix).
2. Reject if unit count exceeds plan's per-call cap → **413**.
3. Per-org-per-minute rate limit → **429**.
4. Atomic quota decrement in SQL → **402** if exhausted.
5. Run handler.
6. On error: refund quota.
7. Always: insert into `usage_events`.

Plans defined as a single dict (single source of truth, in `auth.py`):

```python
PLANS = {
    "free":    {"calls_per_month": 50,      "pages_per_call": 20,  "rpm": 10},
    "starter": {"calls_per_month": 10_000,  "pages_per_call": 100, "rpm": 60},
    "pro":     {"calls_per_month": 100_000, "pages_per_call": 500, "rpm": 300},
}
```

---

## 6. Roadmap

### Phase 0 — Pre-work [~1 hour, DONE]
- [x] **Gemini spend protection** — soft cap (budget alert) configured in Google Cloud Console. Convert to hard cap before public launch.
- [x] **WorkOS staging credentials captured** — `WORKOS_CLIENT_ID`, `WORKOS_API_KEY`, `WORKOS_JWKS_URL` in local `.env`. Production env credentials to be captured at submission time.
- [x] **Postgres provisioned on Railway** — same project as the Flask app. `DATABASE_URL` reads the public proxy locally and the internal hostname on Railway (one var name, two values).
- [x] **Railway Flask service variables staged.** `DATABASE_URL` + the three `WORKOS_*` vars. Deployed 2026-06-04 with the Phase 1 code.
- [x] **Redis deferred.** In-memory rate limiting until we run >1 Railway replica.

### Phase 1 — Foundation: auth + quota + metering [~1 week, DONE]
- [x] Four tables (`orgs`, `api_keys`, `quotas`, `usage_events`) + Alembic baseline. [db/models.py](db/models.py), [migrations/versions/0001_baseline_orgs_apikeys_quotas_usage.py](migrations/versions/0001_baseline_orgs_apikeys_quotas_usage.py).
- [x] [auth.py](auth.py) — `Principal`, `require_auth` decorator, JSON-only error responses (401/402/413/429). `PLANS` dict is the source of truth.
- [x] WorkOS JWT verification (`_resolve_oauth`) — `PyJWKClient` (1h cache), audience/issuer pinned via env vars, requires `exp`/`iat`/`sub`. Runtime-deferred: `WORKOS_ISSUER` captured in Phase 1.5.
- [x] API key resolution (`_resolve_api_key`) — sha256 lookup, `hmac.compare_digest`, sentinel-compare on miss to flatten timing curve, `revoked_at` honored. Issuance via `issue_api_key()` (`secrets.token_urlsafe(32)` → 256 bits).
- [x] Atomic SQL quota decrement (`UPDATE ... RETURNING` against `calls_remaining > 0`, range-match on period). Refund-on-error path.
- [x] POC endpoint `POST /api/v1/summarize` ([api_routes.py](api_routes.py)) protected by `@require_auth`. Verified end-to-end on Railway Postgres: real key → 50→49 → `usage_events` row with `status=ok`. Seed helper [scripts/seed_dev_org.py](scripts/seed_dev_org.py).
- [x] Failure-path test suite ([tests/test_auth_failures.py](tests/test_auth_failures.py)): 402 exhausted, 413 oversized, 429 rate-limited, refund-on-exception, refund-clamp-at-limit. Per-test `seeded_org` fixture in [tests/conftest.py](tests/conftest.py). 21/21 tests pass.
- [x] **Latent bugs surfaced and fixed during Phase 1:**
  - `UsageEvent.org` back-relationship missing in [db/models.py](db/models.py).
  - `_resolve_oauth` 500'd on non-JWT bearers instead of 401'ing.
  - `BigInteger` PK on SQLite (test backend) — added `BigInteger().with_variant(Integer(), "sqlite")` shim; no-op on Postgres.
  - `_decrement_quota` / `_refund_quota` keyed on exact `period_start =` equality — rewrote as range matches.

### Phase 1.5 — Multi-tenant auth wiring + public-site polish [DONE 2026-06-05]

Shipped as scoped in §6.5. Schema migration `0002_users_memberships` applied to Railway Postgres; `auth_routes.py` + `auth_session.py` wired; dashboard at `/dashboard/*` with role-gated key/member management; OAuth callback provisions WorkOS org + local mirror on first signup; `_resolve_oauth` populates membership graph for OAuth callers; nav sign-in/sign-up, `/pricing` (reads `PLANS` dynamically), and homepage hero refresh deployed. Test suite: 47/47 (was 21/21; +25 covering auth routes with mocked WorkOS + cross-tenant isolation). End-to-end verified live: signup → org creation → key issuance → API call → quota decrement.

One execution-time bug fixed during deploy: `create_organization_membership` in WorkOS SDK v8 takes a typed `role` (`RoleSingle`/`RoleMultiple`), not a string `role_slug` (commit `79b99a3`). Local `org_memberships.role` is the column that actually drives dashboard auth, so we omit the WorkOS-side role and let it default.

### Phase 2 — MCP server [~1 week]

> **Architectural footnote (decided 2026-06-05):** `fastmcp` is ASGI-only; mounting it on Flask requires an asgiref bridge + uvicorn swap. The 2025-06-18 Streamable HTTP spec permits returning `Content-Type: application/json` for request/response pairs (no SSE), which is sufficient for our synchronous tool shapes. We implement the JSON-RPC envelope directly as a Flask blueprint ([mcp_routes.py](mcp_routes.py)) — no new dep, no deployment topology change. SSE can be layered later if we wire incremental-progress notifications.

- [x] Stand up MCP server with Streamable HTTP transport on the same Flask app ([mcp_routes.py](mcp_routes.py): `/mcp` POST/OPTIONS, JSON-RPC 2.0, supports protocol versions 2025-06-18 + 2025-03-26).
- [x] Define tools (each with JSON Schema input, title, `readOnlyHint`, `destructiveHint`):
  - [x] `summarize_document` (annotations: idempotent, non-destructive, non-readOnly because quota is consumed)
  - [x] `translate_document` — text-only output (markdown). Source must be .docx/.pptx/.xlsx ≤10 MB; `target_language` is a plain English name. Reuses `features.translation.routes.translate_text_util` so prompt + safety-filter behavior matches the HTMX surface. The binary-file round-trip the HTMX route does (GCS → rebuilt .docx) is intentionally skipped here — Phase 4's `/api/v1/translate` will expose it for paid callers if a customer asks.
  - [x] `redact_pii` — Presidio-backed in-place redaction. Returns the redacted .docx/.pptx as base64 + mimetype. Uses the same `redact_word_document_pii` / `redact_powerpoint_document_pii` helpers as `/process/pii_redaction/redact`.
  - [x] `analyze_image` — Gemini vision + dominant colors. Same `analyze_image_with_gemini` + `extract_dominant_colors` pipeline as the HTMX surface. Supports JPG/PNG/WEBP/HEIC/HEIF ≤10 MB; calls `normalize_and_resize_image` first so giant uploads don't OOM Gemini.
  - [x] `detect_faces` — MTCNN face detection + blur/redact. `mode` ∈ {`blur`, `redact`} and `blur_strength` ∈ {1,2,3}; returns a PNG. Reuses `blur_image_opencv`. *Tool name is `detect_faces` to match the directory of capabilities, but the work is detection-then-obscure — the response is the processed image, not face bounding boxes.*
  - [ ] ~~`transcribe_audio`~~ **deferred** — `features/transcription/routes.py` is a stub returning `f"'{filename}' would be transcribed by the AI"` with no actual Gemini wiring. Shipping a fake tool would mislead Claude + reviewers. Two options before reinstating: (a) build the real transcription pipeline (Gemini 1.5+ supports audio input natively — pass `inline_data` MIME audio/* with the file bytes and the model returns a transcript) and wire it into both `/process/transcribe` AND a new `transcribe_audio` MCP tool, or (b) drop transcription from the Synzo capability set entirely. **Recommendation: (a) before Phase 3.5 submission, since "transcribe a meeting recording" is one of the strongest use-cases for an AI-agent connector.**
- [x] Each tool calls into the existing Flask feature code via internal function calls (not HTTP). `summarize_document` reuses `features.summarization.utils.read_text_from_file` + `analyst_agent.stream_analysis` so MCP and `/api/v1/*` paths return identical results.
- [x] Wire each tool handler through the auth/quota/metering pipeline. Introduced `auth.run_metered_tool(principal, tool_name, units, fn)` — extracted from `require_auth` — so the MCP layer can run the same pipeline but receive `AuthError` exceptions (translated to JSON-RPC error envelopes with codes `-32001` auth / `-32002` quota / `-32003` rpm / `-32004` units) instead of Flask HTTP responses.
- [x] **Tenancy contract for MCP tools:** every tool handler receives the resolved `Principal` (from `_identify_principal()`) and scopes any DB read/write on `principal.org_id`. Isolation test asserts Org A's MCP call records `usage_events` only against A's org_id, never B's.
- [x] Expose `/.well-known/oauth-protected-resource` (RFC 9728) pointing at WorkOS via `WORKOS_ISSUER`. Honors `SYNZO_PUBLIC_URL` env var so the resource URL is the externally-reachable one, not Railway's internal hostname.
- [x] CORS allowlist for `https://claude.ai` + localhost (MCP Inspector). DNS rebinding mitigation: Origin header validated on every POST before any tool runs.
- [x] **Deploy initial vertical slice to Railway; verify `/mcp` reachable on `synzo.ai` and discovery endpoint serves the WorkOS issuer.** Done 2026-06-05 (commits `1df8a15` + `bc54e5e` pushed to origin/master, Railway auto-deployed). Smoke tests against `https://www.synzo.ai/mcp`: initialize (200, `serverInfo.name=synzo`), tools/list (returns summarize_document + schema + annotations), tools/call without auth (JSON-RPC `-32001`), OPTIONS with `Origin: https://claude.ai` (204 + CORS allow), POST with disallowed Origin (403 + `-32600`), discovery (returns WorkOS issuer + `resource: https://www.synzo.ai`).
- [ ] **Deploy the four new tools (translate / redact_pii / analyze_image / detect_faces) to Railway** and re-run smoke tests so `tools/list` returns all 5. detect_faces will warm MTCNN (TensorFlow) on first call — expect a ~10-30s cold-start latency hit per replica. Confirm `/api/v1/summarize` still works (no regression in the existing path).
  - ⚠️ **`SYNZO_PUBLIC_URL=https://www.synzo.ai` is a hard requirement in Railway service vars.** Without it, the discovery endpoint's `resource` field falls back to `request.host_url` which sees `http://` (Railway terminates TLS at the edge, forwards plaintext). RFC 9728's `resource` is used by MCP clients for OAuth audience checks; an `http://` resource breaks token validation silently — Claude Desktop/web OAuth flows will reject every JWT. Captured + set 2026-06-05.
- [ ] Live MCP Inspector validation against the deployed URL — gate to Phase 3.

### Phase 2.5 — Concurrency hardening: thread bump → SSE streaming [must precede public-launch traffic]

**Why this phase exists.** The Phase 2 slice runs synchronously: a `tools/call` holds one Waitress worker thread for the entire Gemini turnaround. Default `threads=4`, so four concurrent summarize calls block every other request to the entire Flask app (homepage, dashboard, `/api/v1/*`, `/mcp` health). A 600-page PDF on the `pro` plan can hold a thread for 60-90 seconds. This is latent today (free-tier per-call cap is 20 pages, so reviewers can't trigger it), but becomes a real outage risk the moment paying customers exist.

**Phase 2.5.A — Thread bump + hard timeout (immediate, before any public launch).** Small, ships with the rest of Phase 2.

- [ ] Bump waitress to `--threads=32` in the Railway start command. 8× the headroom for blocking handlers.
- [ ] Wrap every MCP tool handler (and `/api/v1/*` handler) in a hard wall-clock timeout (~60s). On timeout: refund quota, meter as `refunded`/`timeout`, return JSON-RPC error / HTTP 504.
- [ ] Add a load test (locust or a simple asyncio script) that fires 32 concurrent `summarize_document` calls against a stubbed Gemini and confirms the homepage stays responsive throughout. Run before any public-launch deploy.
- [ ] Document the cap: "single Railway replica = ~32 concurrent in-flight tool calls before backpressure." When we cross that, do Phase 2.5.B.

**Phase 2.5.B — SSE streaming + background workers (before "real customer" traffic).** The proper fix. The 2025-06-18 Streamable HTTP spec already permits this — we picked the JSON branch for the slice because it was sufficient, not because the SSE branch was wrong.

- [ ] Add Redis to Railway (already deferred in Phase 0; this is the trigger).
- [ ] Add a worker process (RQ first — simpler than Celery; switch if we need scheduled jobs). One worker dyno on Railway alongside the Flask web dyno.
- [ ] Refactor `mcp_routes.py`'s `tools/call` to support the SSE branch: when a tool's expected duration > 5s (heuristic on `units_fn`), enqueue the job, hold the HTTP connection open, emit JSON-RPC `notifications/progress` events from the worker via Redis pub/sub, send the final JSON-RPC response when the worker finishes, then close the stream.
- [ ] `/api/v1/*` gets a parallel async surface: either keep synchronous + add an `Accept: text/event-stream` branch, or split into `POST /api/v1/jobs` + `GET /api/v1/jobs/<id>`. Decide at implementation time.
- [ ] Web workers stop blocking on Gemini entirely; one Waitress thread per *connection*, not per *Gemini call*. Concurrency ceiling becomes Redis + Postgres connection pool size, not Waitress thread count.
- [ ] **Tenancy invariant survives:** the worker reads `principal.org_id` from the enqueued job payload and scopes everything on it. Cross-tenant isolation tests get extended to cover the worker path (Org A's job never writes Org B's `usage_events`).

**Sequencing decision.** Phase 2.5.A ships with Phase 2 — it's the minimum to safely take Anthropic submission traffic. Phase 2.5.B is **not** required for submission (reviewers won't hammer us with 600-page PDFs) but **is** required before any "you can buy a `pro` plan" public launch. The trigger to start 2.5.B is the first of: (a) we hit the 32-thread ceiling in production logs, (b) a real customer asks about long-doc support, or (c) we're starting Phase 4.

### Phase 3 — Submission readiness [~3 days]
- [ ] Validate with MCP Inspector locally + against the deployed Railway URL.
- [ ] Write integration tests (pytest) for each MCP tool with mocked Gemini.
- [ ] Write OAuth flow tests (mock WorkOS).
- [ ] Replace one-line `README.md` with proper API docs (tool list, schemas, examples).
- [ ] Author `SECURITY.md` scoped to the MCP server (existing `SAST_REPORT.md` is for the Flask app).
- [ ] Audit `logging.info` call sites — confirm no document/prompt bodies are logged.
- [ ] Add file-type detection via magic bytes (currently extension-based).
- [ ] Wrap Gemini calls with tenacity (retry + circuit breaker).
- [ ] Prepare reviewer test credentials + sample documents.

### Phase 3.5 — Submission package (Anthropic Directory form deliverables) [~1–2 days]

Non-code deliverables for the submission form. Pull together in parallel with Phase 3.

**Identity & contact**
- [ ] Primary contact: name, email, role (Paul O'Hagan as owner; confirm reviewer-outreach email).
- [ ] Company info / submitting entity.

**Listing copy**
- [ ] Server name: `Synzo`.
- [ ] Server URL (production Railway URL of the MCP endpoint).
- [ ] Tagline — **≤55 characters**.
- [ ] Description — **50–100 words** covering what Synzo does + key capabilities.
- [ ] Capability classification: read/write, third-party data handling, category.

**Use cases**
- [ ] Draft **≥3 use cases**, each with an example user prompt. Seeds (matching what's shipped):
  - Summarize a long contract / classify it / produce a structured summary (`summarize_document`).
  - Translate the text content of a foreign-language docx/pptx/xlsx (`translate_document`).
  - Redact PII from a batch of docx/pptx documents before sharing (`redact_pii`).
  - Describe and tag an image, extract any visible text, flag safety concerns (`analyze_image`).
  - Anonymize a group photo by blurring or redacting all detected faces (`detect_faces`).
  - ~~Transcribe a meeting recording and summarize action items~~ — only after `transcribe_audio` is built (see §6 footnote).

**Server inventory (declared on the form)**
- [ ] Tools — `summarize_document, translate_document, redact_pii, analyze_image, detect_faces`. Add `transcribe_audio` only if the real pipeline ships before submission.
- [ ] Resources — declare "None" for v1.
- [ ] Prompts — declare "None" for v1.

**Auth & test access**
- [ ] Authentication summary: OAuth 2.0 via WorkOS AuthKit (PKCE + DCR), JWT bearer.
- [ ] Test account credentials + step-by-step connection instructions + sample docs.

**Docs & support**
- [ ] Public documentation URL.
- [ ] Recommended support channel — email or issue tracker distinct from docs.

**Branding & visuals**
- [ ] Square 1:1 logo, hosted publicly (Drive link OK). Decide PNG vs commissioned SVG.
- [x] Site favicon at `www.synzo.ai` updated to the Synzo icon (commit `90218af`).
- [ ] Verify `https://www.google.com/s2/favicons?domain=synzo.ai&sz=64` after Google's 24–48h cache refresh.
- [ ] 3–5 promotional screenshots of Synzo running inside claude.ai. Demo video optional.
- [ ] Optional: Google Drive folder linking promo assets + matching prompts.

**Compliance & submission**
- [ ] Review and confirm compliance with Anthropic's MCP integration guidelines.
- [ ] Review and accept the MCP Directory Terms.
- [ ] Launch readiness / GA confirmation on the form.
- [ ] Optional: package any Agent Skills that complement the connector.
- [ ] **Submit to Connector Directory.**

### Phase 4 — Paid API (deferred until a real customer asks) [~1 week]
- [ ] Stripe Checkout integration for plan upgrades (org-scoped — the org is the billable entity, not the user).
- [ ] `stripe_customers` table; Stripe webhook → updates `orgs.plan` + provisions `quotas` row.
- [ ] Customer dashboard: usage charts read from `usage_events`.
- [ ] Per-key (not just per-org) rate limits — trivial code change.
- [ ] Nightly aggregation job: `usage_events` → Stripe usage records (for metered billing).
- [ ] Anomaly cron: alert when any org spikes 10× baseline.

---

## 6.5 Phase 1.5 detail (shipped 2026-06-05 — kept as historical record)

Implementation matched this spec except where noted inline. Kept as the design rationale for what's now in `auth_routes.py` / `auth_session.py` / Alembic `0002_users_memberships`, and because the WorkOS SDK-shape footnotes (§6.5.E and the `role_slug` correction) are worth preserving for future maintenance.

### A. Schema additions

New Alembic migration `migrations/versions/0002_users_memberships.py`:

```python
def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),  # BigIntPk in models.py
        sa.Column("workos_user_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workos_user_id", name="uq_users_workos_user_id"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "org_memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.BigInteger(), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),  # 'owner' | 'admin' | 'member'
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "org_id", name="uq_org_memberships_user_org"),
        sa.CheckConstraint("role IN ('owner','admin','member')", name="ck_org_memberships_role"),
    )
    op.create_index("ix_org_memberships_user", "org_memberships", ["user_id"])
    op.create_index("ix_org_memberships_org", "org_memberships", ["org_id"])
```

Matching ORM models in [db/models.py](db/models.py):
- `User` model with `Mapped[int] id` (using `BigIntPk` for SQLite compatibility), `workos_user_id`, `email`, `created_at`, `last_seen_at`; relationships to `memberships` and (via memberships) `orgs`.
- `OrgMembership` model with `user_id`, `org_id`, `role`, `created_at`; relationships to `user` and `org`.
- `Org.memberships` and `User.memberships` back-relationships.

### B. WorkOS dashboard config

Already done 2026-06-04: redirect URIs (`http://localhost:5001/auth/callback`, `https://www.synzo.ai/auth/callback` as default), sign-out URIs (`http://localhost:5001/`, `https://www.synzo.ai/` as default), AuthKit hosted UI enabled, Email+Password + Google/MS/GitHub/Apple SSO enabled with WorkOS demo OAuth credentials. AuthKit URL: `real-vine-49-staging.authkit.app`.

**Still to do (5 min):**
- At `dashboard.workos.com/.../authentication/edit-jwt-template`, add `"org_id": "{{ organization.id }}"` to the JWT template so [auth.py:113](auth.py#L113)'s `_resolve_oauth` finds a value. If we want the WorkOS user ID propagated too (which we do, for the membership graph), the template already includes `sub` by default — that's the WorkOS user ID. Optionally add `"email": "{{ user.email }}"` for upsert convenience.

### C. Flask routes — new `auth_routes.py` blueprint

Registered under `/auth` and `/dashboard`. **CSRF-protected** (cookie-based, human-driven) and **NOT `@require_auth`-protected** — uses `@require_session` instead (see §6.5.D).

```python
# auth_routes.py (sketch)
from workos import WorkOSClient

bp = Blueprint("auth", __name__)

@bp.route("/auth/login")
def login():
    """Build the AuthKit URL and redirect. State param is a CSRF token."""
    # workos.user_management.get_authorization_url(...)
    # store state in session, redirect to AuthKit hosted UI

@bp.route("/auth/callback")
def callback():
    """Exchange auth code for tokens. Provision org/user/membership if new."""
    # 1. Verify state param matches session.
    # 2. workos.user_management.authenticate_with_code(code=...) -> (user, tokens)
    # 3. Upsert User row by workos_user_id (email may have changed).
    # 4. List user's WorkOS org memberships via workos.user_management.list_organization_memberships(user_id=...)
    # 5. If user has no memberships:
    #      org = workos.organizations.create_organization(name=f"{user.first_name or user.email}'s Workspace")
    #      workos.user_management.create_organization_membership(user_id=user.id, organization_id=org.id, role_slug='admin')
    #      # WorkOS doesn't have 'owner' as a built-in; we treat the creator as owner in our org_memberships table.
    #      Re-authenticate to get a token with the new org_id claim.
    # 6. Mirror each WorkOS org into our `orgs` table (idempotent on workos_org_id).
    # 7. Mirror each WorkOS membership into our `org_memberships` table.
    #    First membership created locally is 'owner'; subsequent ones default to 'member' unless they're an admin in WorkOS.
    # 8. Provision a free-tier `quotas` row for the current period for any newly created org.
    # 9. Set Flask session: workos_user_id, current_org_id, access_token (short-lived).
    # 10. On first successful sign-in only: log decoded JWT's iss claim for WORKOS_ISSUER capture.
    #     Remove this log line after the value is captured into .env.
    # 11. Redirect to /dashboard.

@bp.route("/auth/logout")
def logout():
    """Clear session, redirect to WorkOS logout."""
    # workos.user_management.get_logout_url(session_id=...) -> redirect

@bp.route("/dashboard")
@require_session
def dashboard():
    """Show current org's plan, usage, keys, and members."""
    # Principal already on g via require_session.
    # Query: api_keys WHERE org_id = principal.org_id AND revoked_at IS NULL
    # Query: quotas WHERE org_id = principal.org_id AND period_start <= now < period_end
    # Query: org_memberships JOIN users WHERE org_memberships.org_id = principal.org_id
    # Render dashboard.html.

@bp.route("/dashboard/keys/issue", methods=["POST"])
@require_session
@require_role("admin")  # owners + admins
def issue_key():
    """Issue an API key for the CURRENT org. Show raw key once."""
    # auth.issue_api_key(org_id=principal.org_id, name=request.form.get("name"))
    # Flash raw key, redirect.

@bp.route("/dashboard/keys/<int:key_id>/revoke", methods=["POST"])
@require_session
@require_role("admin")
def revoke_key(key_id):
    """Revoke a key in the CURRENT org. Tenant check is non-negotiable."""
    # ApiKey.query.filter_by(id=key_id, org_id=principal.org_id).first_or_404()
    # # The `org_id=principal.org_id` clause is what prevents Org B from revoking Org A's key.
    # key.revoked_at = utcnow(); commit.

@bp.route("/dashboard/members/invite", methods=["POST"])
@require_session
@require_role("admin")
def invite_member():
    """Invite a user (by email) to the current org via WorkOS."""
    # workos.user_management.send_invitation(email=..., organization_id=current_org.workos_org_id)
    # The invitee will get a WorkOS email; on accept, the callback handler above mirrors the membership.

@bp.route("/dashboard/members/<int:membership_id>/role", methods=["POST"])
@require_session
@require_role("owner")
def update_member_role(membership_id):
    """Owner-only: change a member's role. Cannot demote yourself; cannot create a second owner without transfer."""
    # OrgMembership.query.filter_by(id=membership_id, org_id=principal.org_id).first_or_404()
    # Validate new role; refuse owner unless transferring (separate flow).

@bp.route("/dashboard/switch-org/<int:org_id>", methods=["GET"])
@require_session
def switch_org(org_id):
    """If user is a member of <org_id>, switch active org."""
    # OrgMembership.query.filter_by(user_id=session.user_id, org_id=org_id).first_or_404()
    # session["current_org_id"] = org_id; redirect to /dashboard.
```

Template: a minimal `templates/dashboard.html` using the existing Tailwind layout. Sections: plan + usage bar, API keys table (issue / revoke buttons), members table (invite / role buttons), org switcher dropdown if `>1` orgs. No charts; just text + buttons.

### D. Session helper — extend `auth.py` (or new `auth_session.py`)

```python
def current_principal() -> Principal | None:
    """Read the Flask session, return a Principal or None. Used by @require_session."""
    user_id = session.get("user_id")
    org_id = session.get("current_org_id")
    if not user_id or not org_id:
        return None
    membership = OrgMembership.query.filter_by(user_id=user_id, org_id=org_id).one_or_none()
    if membership is None:
        # Session points at an org the user isn't a member of anymore; force re-login.
        return None
    org = db.session.get(Org, org_id)
    return Principal(org_id=org.id, plan=org.plan, auth_method="session", api_key_id=None, user_id=user_id, role=membership.role)

def require_session(fn):
    """Decorator: redirect to /auth/login if no session, else attach Principal to g."""
    # If no Principal, redirect.
    # Else g.principal = principal; call fn.

def require_role(min_role: str):
    """Decorator factory: assert g.principal.role ranks >= min_role.
    Ordering: owner > admin > member. Raises 403 (JSON) or HTML 403 page on failure."""
```

`Principal` dataclass gets two new fields: `user_id: int | None` (for session-authed callers) and `role: str | None` (only set when auth_method='session'). Old API-key and OAuth callers leave these at `None`. The role gate only fires for dashboard routes.

### E. `auth.py` changes

`_resolve_oauth` keys on `org_id` claim already (no functional change). **One new behavior:** when the JWT also carries `sub` (the WorkOS user ID — always present), upsert the `users` row and the `org_memberships` row so OAuth callers (Claude Desktop) populate the membership graph too. This keeps the membership graph complete regardless of which surface (browser, OAuth, or API key) created it.

Specifically, at the end of `_resolve_oauth`, before returning `Principal`:

```python
workos_user_id = claims["sub"]
user = User.query.filter_by(workos_user_id=workos_user_id).one_or_none()
if user is None:
    user = User(workos_user_id=workos_user_id, email=claims.get("email", "<unknown>"))
    db.session.add(user)
    db.session.flush()  # get user.id
membership = OrgMembership.query.filter_by(user_id=user.id, org_id=org.id).one_or_none()
if membership is None:
    db.session.add(OrgMembership(user_id=user.id, org_id=org.id, role="member"))
user.last_seen_at = utcnow()
db.session.commit()
```

(API-key callers don't have a `sub`/user concept; they leave `Principal.user_id=None`. That's correct — API keys belong to orgs, not to specific users.)

### F. Test additions

Two new test files.

**`tests/test_auth_routes.py`** (mocked WorkOS SDK; tests stay offline):
- `/auth/login` redirects to AuthKit URL with a state param.
- `/auth/callback` with mocked happy-path response: new user → org auto-created → membership inserted as `owner` → quota provisioned → session set → redirect to `/dashboard`.
- `/auth/callback` repeat sign-in: existing user → no duplicate orgs/quotas/memberships → session set.
- `/auth/callback` with state mismatch → 400.
- `/dashboard` without session → redirect to `/auth/login`.
- `/dashboard` with session → 200, includes the seeded org's plan + key prefix.
- `/dashboard/keys/issue` issues a key tied to `principal.org_id`. Verify the resulting key's `org_id` matches.
- `/dashboard/keys/<id>/revoke`: own org's key → 200; another org's key (cross-tenant attempt) → 404.
- `/dashboard/members/invite` calls the mocked WorkOS invitation API exactly once.
- `/dashboard/members/<id>/role` as `member` → 403; as `admin` → 200 unless trying to set role=`owner` → 403; as `owner` → 200.
- `/dashboard/switch-org/<org_id>`: own org → 302; non-member org → 404.
- `/auth/logout` clears the session.

**`tests/test_multi_tenant_isolation.py`** — the bug-prevention suite. Each test seeds two orgs (`org_a`, `org_b`) each with its own user + key + usage events. Then asserts:
- API key from Org A authenticated against `/api/v1/summarize` produces a `usage_events` row with `org_id=org_a.id`, never `org_b.id`.
- Session in Org A → `/dashboard` lists only Org A's keys and members.
- Session in Org A → POST to revoke a key whose ID belongs to Org B → 404 (not 403; we don't leak existence).
- Session in Org A → POST to demote a membership whose ID belongs to Org B → 404.
- Session in Org A → GET `/dashboard/switch-org/<org_b.id>` → 404 if Org A's user isn't also in Org B; 302 if they are.
- Org A's quota row is independent of Org B's: exhausting Org A's quota does not affect Org B.

These tests are short but they catch the bug class that hurts most.

### G. Manual verification checklist (run once before claiming Phase 1.5 done)

1. Sign up as **User1** (fresh email) via `/auth/login` → org auto-created (`User1's Workspace`) → land on `/dashboard` → issue a key → call `/api/v1/summarize` with `Authorization: Bearer <new_key>` → quota decrements 50→49.
2. Sign up as **User2** (different email) → separate org → separate quota. Confirm User1's dashboard does NOT show User2's org.
3. From User1's dashboard, invite `user2@email` → User2 accepts (via WorkOS email link) → User2's `/auth/callback` mirrors the new membership → User2 sees the org switcher with both orgs.
4. User2 in User1's org tries to promote themselves to `owner` via the dashboard → 403.
5. User1 (owner) demotes their own role to `admin` → blocked (need a transfer flow; out of scope for Phase 1.5).
6. Revoke a key from Org A's session targeting Org B's key ID (use a curl with the cookie + a guessed key ID) → 404.
7. Hit `/api/v1/summarize` with no auth → 401 JSON. With User1's session cookie (not a bearer) → 401 JSON. With User1's API key bearer → 200.

### H. Capturing `WORKOS_ISSUER` (one-time)

The `/auth/callback` handler logs `claims["iss"]` on the first successful sign-in (gated by a `WORKOS_ISSUER_CAPTURED` env var check, or simply by checking whether `os.environ.get("WORKOS_ISSUER")` is set). After the first sign-in:

1. Read the value from logs (`railway logs` or local console).
2. Paste into local `.env` and Railway service variables as `WORKOS_ISSUER`.
3. Remove the temporary log line.
4. Redeploy.

After this, `_resolve_oauth` will enforce `issuer` on every subsequent JWT.

### I. Dependencies

No new packages needed for Phase 1.5. The `workos` SDK is already in [requirements.txt](requirements.txt).

### J. Sequencing within Phase 1.5

The order that minimizes integration pain:

1. Schema migration (`0002_users_memberships`) + ORM models. Run locally; confirm tests still pass.
2. WorkOS JWT template edit.
3. Session helper + `Principal` extension.
4. `auth_routes.py` — start with `/auth/login` + `/auth/callback` only; verify happy-path against staging WorkOS; capture `WORKOS_ISSUER`.
5. `_resolve_oauth` user/membership upsert (now that the schema is in place).
6. `/dashboard` + key issue/revoke. Verify isolation manually.
7. `/dashboard/members/*` + org switcher.
8. `tests/test_auth_routes.py` + `tests/test_multi_tenant_isolation.py`.
9. **Public-site polish (§6.5.K)** — once the dashboard works, wire it into the public site so visitors can discover signup.
10. Apply migration + deploy to Railway. End-to-end smoke test in prod: sign up as a new user, get a key from the dashboard, call `/api/v1/summarize` with that key.

### K. Public-site polish

The goal of Phase 1.5 is "true multi-tenant SaaS that anyone can sign up for and use." That's only true end-to-end if a visitor to synzo.ai can actually find the sign-up flow. Three small additions to the existing public surface:

**K.1 — Auth entry points in the layout** (~30 min)

Edit [templates/layout.html](templates/layout.html) to add nav buttons in the top-right:

- If no session: `[Sign in]` `[Sign up free]` — both link to `/auth/login` (AuthKit's hosted UI handles both flows on one URL).
- If signed in: `[Dashboard]` (links to `/dashboard`) and `[Sign out]` (links to `/auth/logout`).
- Render via a `current_user` global injected by a Flask `@app.context_processor` that reads the session.

This is what makes the rest of Phase 1.5 reachable from the live site. Without it, the dashboard exists but nobody finds it.

**K.2 — `/pricing` page** (~1 hour)

A new public route in [main_routes.py](main_routes.py) (or a new `marketing_routes.py` if it grows) rendering `templates/pricing.html`. Three-column layout showing the `PLANS` dict tiers (`free` / `starter` / `pro`) with their actual numbers from [auth.py](auth.py):

- **Free**: "50 calls/month, 20 pages per call, 10 req/min — Sign up free" → links to `/auth/login`.
- **Starter**: "10,000 calls/month, 100 pages per call, 60 req/min — Coming soon" (no Stripe yet; the button is disabled or says "Contact us"). Email link to a real address you'll monitor.
- **Pro**: "100,000 calls/month, 500 pages per call, 300 req/min — Contact sales" (same — Phase 4 ships actual purchase).

**Crucial:** read the numbers from `PLANS` dynamically — pass the dict to the template and render the values in Jinja. That way when you tune the free tier later (open question in §7), the page updates automatically. No hardcoded marketing copy that drifts from the actual enforcement.

Add `/pricing` to the nav alongside `/about`.

**K.3 — Homepage hero refresh** (~3–4 hours, more if you iterate on copy)

The current landing emphasizes the AI features ("look what this app does"). For SaaS positioning, the hero should pitch Synzo as a product ("Document intelligence for AI agents and apps"). Three things to update in [templates/index.html](templates/index.html) (or wherever the homepage lives):

- **Headline** — one sentence pitch. Something like "Document intelligence APIs for agents, apps, and people." Don't try to write this in the plan; iterate when you get there.
- **Subhead** — one paragraph on what it does (summarize, translate, redact PII, analyze images, transcribe) and who it's for.
- **CTAs above the fold** — primary `[Sign up free]` → `/auth/login`, secondary `[View pricing]` → `/pricing`. Keep the existing feature demo links lower on the page; they're proof points, not the lead.

The feature showcase content stays — it's good portfolio material *and* good SaaS proof-of-capability. Just stops being the headline.

**What this does NOT include:**

- A separate "About Synzo" company-style page (the existing `/about` covers Paul as the developer; no need for a corporate "team" page).
- Customer logos, testimonials, case studies — we have none, so we don't fake them. SaaS sites that have these *earned* them; portfolio sites that fake them read as inauthentic.
- A blog. Defer.
- A status page. Defer until Phase 4 — Railway's built-in status is enough for now.
- Real OAuth credentials for Google/Microsoft. WorkOS demo creds are fine for staging + Anthropic review; swap to real Google/MS OAuth apps before going public to actual paying customers in Phase 4.

**Why this lives in Phase 1.5 and not Phase 3.5:**

Phase 3.5 is submission deliverables (screenshots, listing copy, reviewer credentials). The polish here is *site* polish, not *submission* polish. We want the live site to look like a SaaS during Phase 2/3 — that's also when we'll be taking screenshots for the submission, and screenshots of a portfolio-styled homepage with no signup button would be a self-inflicted wound.

---

## 7. Open questions

- **API ownership for Gemini.** Anthropic prefers connectors whose primary API is owned by the submitter. Synzo wraps Gemini. Mitigation: position the submission as "Synzo's document-intelligence API (Gemini-powered)" rather than "a Gemini connector." May or may not satisfy review.
- **MCP server deployment shape.** Same Flask app vs sidecar — leaning same-app for v1 (simpler, shares the auth decorator and DB connection pool natively).
- **Async processing.** Current Flask app processes synchronously. For MCP tools that take >30s (large PDFs), may need Celery/Redis before submission, or document timeout behavior.
- **Free tier sizing.** `PLANS["free"]` numbers are placeholders. Tune from real Gemini costs once we have any.
- **Tool granularity.** `summarize_document` vs `summarize_document_to_pptx`: leaning two tools for clearer annotations.
- **transcribe_audio.** Stub today; build the real Gemini-audio path before Phase 3.5 or drop transcription from the submission. Either is defensible; "build it" is the recommended option since Anthropic's connector audience cares about meeting/audio workflows.
- **Owner transfer flow.** Phase 1.5 ships role updates but not owner transfer. Likely a `/dashboard/transfer-ownership` route that updates both memberships in one transaction. Defer to Phase 4 unless a real reviewer ask forces it earlier.

---

## 8. Reference: design rationale we don't want to re-litigate

- **Two auth paths share one ledger; the dashboard is a third front door that resolves to the same `Principal`.** Don't split into "MCP backend" and "API backend." Same Flask app, same Postgres, same decorator.
- **Two URL surfaces.** See §3.3. Never put `@require_auth` on an HTMX endpoint; never put `@require_session` on a `/api/v1/*` endpoint.
- **API keys are `sk_synzo_` prefixed, sha256-hashed at rest.** Revocable via `revoked_at`, never deleted. Display the first 16 chars to customers.
- **402 Payment Required for quota exhaustion** — semantically correct and parses cleanly in customer code.
- **Refund quota on handler error.** Customers don't pay for our bugs.
- **Never log prompt/document contents.** `org_id`, `tool`, `units`, `status`, `cost_cents` only.
- **Plans dict is one source of truth.** Adding a tier is one line.
- **WorkOS over Keycloak** for v1. Revisit only if data sovereignty becomes a sales objection.
- **Multi-tenancy is structural, not optional.** Full model in §3.4. Every WorkOS user is a `users` row; every WorkOS organization is an `orgs` row; the bridge is `org_memberships` with a role enum. **Path B (single user = single org, key on JWT `sub`) was considered and rejected on 2026-06-04 — see git history for the rationale; condensed reasoning: schema is already org-scoped, Path B can't model B2B sales without a future migration, and the cost difference is only ~2 hours of code.**
- **Org-scoping is the invariant, not a convention.** Every query in `/dashboard/*`, `/api/v1/*`, and (future) MCP tool handlers must filter on `WHERE org_id = :principal_org_id` for any tenant-owned table. Bugs of omission here are tenant-crossing bugs. `tests/test_multi_tenant_isolation.py` is the safety net; new routes get parallel isolation tests in the same PR.
- **Org owns the quota; members share it.** When User1 invites User2, they share Org1's free-tier quota — they don't each get their own pool. Org is the billable entity from row zero; Stripe in Phase 4 will be per-org with per-seat pricing.
- **One env var name, environment-specific values.** Code reads `DATABASE_URL` everywhere — local `.env` sets it to the public proxy, Railway service variables set it to the internal hostname. No `if env == "prod"` branching.

---

## 9. File pointers

**Existing (Phase 0 / Phase 1):**
- [app.py](app.py) — Flask factory, Talisman, CSRF, rate limiter, blueprint registration.
- [config.py](config.py) — env-driven config.
- [extensions.py](extensions.py) — shared `limiter`.
- [auth.py](auth.py) — `Principal`, `require_auth`, OAuth + API-key resolvers, quota decrement/refund, metering.
- [api_routes.py](api_routes.py) — `/api/v1/*` JSON blueprint (Phase 2 will add MCP tools alongside).
- [db/models.py](db/models.py), [db/__init__.py](db/__init__.py) — ORM models, shared SQLAlchemy instance.
- [migrations/versions/0001_baseline_orgs_apikeys_quotas_usage.py](migrations/versions/0001_baseline_orgs_apikeys_quotas_usage.py).
- [requirements.txt](requirements.txt) — `pyjwt[crypto]`, `workos`, `psycopg[binary]`, `Flask-SQLAlchemy`, `alembic`, plus the pre-existing deps.
- [features/](features/) — six feature blueprints; their `routes.py` files contain the Gemini/Presidio logic that MCP tools will call into.
- [scripts/seed_dev_org.py](scripts/seed_dev_org.py) — idempotent dev org + quota + API key.
- [tests/conftest.py](tests/conftest.py) — `app`, `client`, `seeded_org` fixtures.
- [tests/test_smoke.py](tests/test_smoke.py), [tests/test_api_auth.py](tests/test_api_auth.py), [tests/test_auth_failures.py](tests/test_auth_failures.py).
- [SAST_REPORT.md](SAST_REPORT.md) — Flask-scope security report.
- [project-summary.md](project-summary.md) — broader product context.

**New in Phase 1.5:**
- `migrations/versions/0002_users_memberships.py` — `users` + `org_memberships` tables.
- `auth_routes.py` — `/auth/login`, `/auth/callback`, `/auth/logout`, `/dashboard/*`.
- `auth_session.py` (or extension to `auth.py`) — `require_session`, `require_role`, `current_principal`.
- `templates/dashboard.html` — minimal dashboard UI.
- `templates/pricing.html` — three-tier pricing page reading from `PLANS`.
- Edits to `templates/layout.html` — nav sign-in/sign-up/dashboard/sign-out buttons.
- Edits to `templates/index.html` (or wherever the homepage hero lives) — SaaS positioning, CTAs above the fold.
- `tests/test_auth_routes.py` — happy-path + role-gate + cross-tenant rejection.
- `tests/test_multi_tenant_isolation.py` — the bug-prevention suite.

---

## 10. When picking this up later

1. Re-read this file end-to-end — the top-of-file status line tells you where we left off.
2. Check the Anthropic MCP spec page for any updates since the last edit date — auth and transport specs evolve.
3. Confirm `PLANS` numbers still make sense given current Gemini pricing.
4. As of 2026-06-05: Phase 0, Phase 1, Phase 1.5 are done. **Phase 2 tool surface is complete locally (5 tools, 82/82 tests green); only the initial slice is deployed.** Next concrete actions, in order: (a) deploy `mcp_tools.py` with all 5 tools to Railway, (b) re-smoke-test `tools/list` on `https://www.synzo.ai/mcp`, (c) Phase 2.5.A (waitress threads + per-tool timeout — see [[feedback-synzo-concurrency-ceiling]]), (d) decide on `transcribe_audio` (build real pipeline or drop from submission), (e) MCP Inspector validation against the deployed URL — gate to Phase 3.
5. WorkOS staging credentials + `WORKOS_ISSUER` live in local `.env` (never committed) and in Railway service vars. Confirm they still work before relying on them.
6. The auth/quota/metering pipeline ([auth.py](auth.py), [auth_routes.py](auth_routes.py)) and the tenant-isolation test suite ([tests/test_multi_tenant_isolation.py](tests/test_multi_tenant_isolation.py)) are the foundation Phase 2's MCP tools sit on top of. Every MCP tool handler must (a) use `@require_auth` (b) read `Principal.org_id` from `g.principal` and scope DB reads/writes on it, and (c) get parallel cross-tenant isolation tests.
7. The audit prompt from the original conversation can be re-run any time against the repo to track progress against Anthropic's requirements matrix.
