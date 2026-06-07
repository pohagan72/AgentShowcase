# Synzo → Anthropic MCP Connector Directory: Submission Plan

> **Status as of 2026-06-07:** Phase 0, Phase 1, Phase 1.5, Phase 2, Phase 2.5.A complete and live. **Phase 3 ~75% shipped (12 commits across 2026-06-06 and 2026-06-07):** plus one /vision UX polish commit on 2026-06-07 (`11a2ff0` — scroll-to-result on HTMX swap, image-result grid breaks out of the narrow column, upload-label reset on swap — caught while preparing reviewer-bundle screenshots: the face-redaction success state was rendering 1500px below the spinner with portrait images clipped, so users couldn't tell processing had finished). **Reviewer test bundle (Phase 3.5) ~90% built (2026-06-07 end-of-day):** all 11 commits pushed and live on Railway as of `9219b22`. State at end-of-day: all 5 sample files staged + verified end-to-end (redact via [scripts/verify_redact_sample.py](scripts/verify_redact_sample.py) against the live `/mcp` endpoint); `reviewer-bundle.zip` deployed at `https://www.synzo.ai/static/files/reviewer-bundle.zip` (3.25 MB, tool-prefixed names inside the zip; verified 200 + 3,250,216 bytes after deploy); reviewer test account live (`paul@redmapleresearch.ca`, free tier 50/20/10, password held outside the repo); `/auth/logout` now properly terminates the AuthKit session too (was a Flask-cookie-only logout silently re-issuing the same identity; caught when trying to sign up a second account in the same browser; commit `bf4081c` stashes `claims['sid']` at callback and calls `workos.user_management.get_logout_url(session_id, return_to)` at logout, with two fallback paths for missing session id / SDK call failure; +2 regression tests, **142/142 tests green**). **Reviewer walkthrough page built then deleted, same day** (commits `6defeb7` build, `9219b22` revert): the page was wrapped in `noindex` / `Cache-Control: no-store` / unlisted-URL defenses, but a publicly-reachable URL that renders the literal password into the HTML body is security-by-obscurity for a one-viewer, one-day artifact. The deletion removed −211 lines (the partial) and the `REVIEWER_PASSWORD` env-var plumbing; `/reviewer-walkthrough` now returns 404 in production (verified 2026-06-07). **Credentials and the 5-prompt sweep are pasted inline into the Anthropic submission form's reviewer-instructions field** — text block lives in §6 Phase 3.5 "Reviewer test bundle". Zero attack surface, no env var to rotate, no URL to revoke. See Phase 3.5 "Reviewer test bundle" for the matrix, the inline-credentials block, and the remaining checklist (dry-run via InPrivate is the only bundle-side item left; the form pasting happens at submission time). Phase 3 ~75% shipped block continues: all five public pages — `/docs`, `/privacy`, `/terms`, `/support`, `/security` — are live on `www.synzo.ai`, wrapped in the canonical `.feature-container` card so visual language matches the feature pages exactly. The tools table on `/docs` is rendered once at `create_app()` startup from the live `mcp_tools.TOOLS` registry joined against a `docs/tool_examples.yaml` sidecar; missing entries raise `DocsExampleDrift` at boot so docs cannot silently go stale (see [docs_renderer.py](docs_renderer.py) + [tests/test_docs_renderer.py](tests/test_docs_renderer.py)). The privacy policy was reviewed line-by-line against the actual code paths and four inaccuracies corrected (the local `users` table stores no name; `usage_events` has no OAuth sub field; the HTMX surface does use S3-compatible scratch storage; S3-compatible was added to §4 providers). The `/about` Legal Notice tab was promoted to a canonical `/terms` URL alongside the other static legal pages. Global footer in [layout.html](templates/layout.html) renders Docs/Pricing/Support/Security/Privacy/Terms on every public page. Total Phase 3 commits: `99d483d` (scaffold), `ffdb73d` (tools-table renderer + guardrail), `abb1faa` (/terms promotion), `16a4b30` (privacy code-review corrections), `2647ac9` (first design-system pass), `c844753` (proper CSS reuse), `796bacc` (plan sync), `3a33950` (policy audits + RPM-cap fix), `6f48ab4` (OAuth-path test gap closed), `f63f00a` (remaining 9 test-suite gaps closed). 140/140 tests green (was 107/107 at the start of the Phase 3 review pass; +33 across the review). **Phase 3 remaining**: file-type magic bytes, tenacity retry around Gemini, `SECURITY.md`, Cloudflare Email Routing aliases (`support@`, `privacy@`, `security@`), live MCP Inspector validation, integration tests per remaining tool, and the API-ownership framing for Gemini. **The six policy-compliance audits all PASS as of 2026-06-06** — no blockers; the per-org RPM cap is now named in the `-32003` message ([auth.py:404](auth.py#L404)). **All nine test-suite gaps from the 2026-06-06 adversarial review are now CLOSED.** Total suite: 140/140 (was 107/107 at the start of the review pass). Coverage now pins: every `_resolve_oauth` raise site + happy + upsert + cross-tenant invariant, OAuth-bearer-through-`/mcp`, every `_resolve_api_key` raise site, `/api/v1/summarize` happy + every failure shape + HTTP-path 504, JSON-RPC body-size caps, `/.well-known/oauth-protected-resource` CORS + fallback, JSON-RPC `id` echo on errors, generic-Exception → `isError+refund`, 405+Allow on GET/DELETE, and a Policy 5.A split (401 for bad token vs 500 for unset env). Gap-list ledger in §6 Phase 3 "Test-suite gaps remaining" — all flipped `[x]` with the specific commit detail. **Repo will be made private before submission** — for MCP server submissions, a private repo is allowed; the "public GitHub repo" rule is scoped to Plugins, which we are not submitting. **No form answers are pre-locked** — every Phase 3.5 form field must be re-derived fresh against the current code/product state at submission time. Waitress runs 32 threads (`WAITRESS_THREADS` env-tunable in [run.py](run.py)); every metered tool invocation runs through a 60s wall-clock timeout in `auth.run_metered_tool()` that refunds the quota slot, meters as `refunded`/`timeout`, and surfaces as JSON-RPC `-32005` (or HTTP 504). All five tools (`summarize_document`, `translate_document`, `redact_pii`, `analyze_image`, `detect_faces`) are live at `https://www.synzo.ai/mcp`. `transcribe_audio` is dropped from submission scope; the submission lists 5 tools. **Gate (d): CLOSED.** API-key auth path: 5/5 tools returned SUCCESS via [scripts/sweep_tools.py](scripts/sweep_tools.py) on 2026-06-05. OAuth path: claude.ai successfully OAuth'd against `https://www.synzo.ai/mcp`, called `Synzo:summarize_document` on a uploaded test file, and Claude rendered the correct classification + summary on 2026-06-06 — end-to-end DCR + PKCE + WorkOS sign-in + tool dispatch + structured-output rendering all proven from the real production client. Three OAuth fixes shipped to make this work: commit `42de97e` (HTTP 401 + WWW-Authenticate on unauthenticated `tools/call`, per MCP spec §2.1 / RFC 9728), commit `49915d0` (host augmented `/.well-known/oauth-authorization-server` that proxies WorkOS AuthKit metadata and injects `registration_endpoint` — WorkOS supports DCR but doesn't advertise it), plus WorkOS dashboard config: **MCP Auth → Dynamic Client Registration must be enabled** and Railway env vars `WORKOS_ISSUER` + `WORKOS_JWKS_URL` must point at the AuthKit subdomain (`real-vine-49-staging.authkit.app`), NOT the `api.workos.com/user_management/<client_id>` URL — only AuthKit publishes the PKCE/scopes/grants metadata MCP clients need. **Next gates: Phase 3 remaining items above + Phase 3.5 (submission package) — both unblocked, can proceed in parallel — see §6.**
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
  - [ ] ~~`transcribe_audio`~~ **dropped from submission scope (2026-06-05)** — `features/transcription/routes.py` is a stub returning `f"'{filename}' would be transcribed by the AI"` with no actual Gemini wiring. Building the real Gemini-audio pipeline is non-trivial and the submission ships with 5 tools that cover document-intel + image use cases. If transcription becomes a customer ask later, the real pipeline (Gemini 1.5+ `inline_data` audio/*) gets built then and added to a future directory revision.
- [x] Each tool calls into the existing Flask feature code via internal function calls (not HTTP). `summarize_document` reuses `features.summarization.utils.read_text_from_file` + `analyst_agent.stream_analysis` so MCP and `/api/v1/*` paths return identical results.
- [x] Wire each tool handler through the auth/quota/metering pipeline. Introduced `auth.run_metered_tool(principal, tool_name, units, fn)` — extracted from `require_auth` — so the MCP layer can run the same pipeline but receive `AuthError` exceptions (translated to JSON-RPC error envelopes with codes `-32001` auth / `-32002` quota / `-32003` rpm / `-32004` units) instead of Flask HTTP responses.
- [x] **Tenancy contract for MCP tools:** every tool handler receives the resolved `Principal` (from `_identify_principal()`) and scopes any DB read/write on `principal.org_id`. Isolation test asserts Org A's MCP call records `usage_events` only against A's org_id, never B's.
- [x] Expose `/.well-known/oauth-protected-resource` (RFC 9728) pointing at WorkOS via `WORKOS_ISSUER`. Honors `SYNZO_PUBLIC_URL` env var so the resource URL is the externally-reachable one, not Railway's internal hostname.
- [x] CORS allowlist for `https://claude.ai` + localhost (MCP Inspector). DNS rebinding mitigation: Origin header validated on every POST before any tool runs.
- [x] **Deploy initial vertical slice to Railway; verify `/mcp` reachable on `synzo.ai` and discovery endpoint serves the WorkOS issuer.** Done 2026-06-05 (commits `1df8a15` + `bc54e5e` pushed to origin/master, Railway auto-deployed). Smoke tests against `https://www.synzo.ai/mcp`: initialize (200, `serverInfo.name=synzo`), tools/list (returns summarize_document + schema + annotations), tools/call without auth (JSON-RPC `-32001`), OPTIONS with `Origin: https://claude.ai` (204 + CORS allow), POST with disallowed Origin (403 + `-32600`), discovery (returns WorkOS issuer + `resource: https://www.synzo.ai`).
- [x] **Deploy the four new tools (translate / redact_pii / analyze_image / detect_faces) to Railway** and re-run smoke tests so `tools/list` returns all 5. Done 2026-06-05 (commit `13ded18` pushed; Railway auto-deployed). Verified live: `tools/list` returns all 5 tools with full schemas + annotations; `initialize` returns `serverInfo.name=synzo` and protocol `2025-06-18`; unauthenticated `tools/call` returns JSON-RPC `-32001`; OPTIONS preflight with `Origin: https://claude.ai` returns 204 + `access-control-allow-origin: https://claude.ai`; POST with disallowed Origin returns 403; discovery endpoint returns `authorization_servers: [<WORKOS_ISSUER>]` and `resource: https://www.synzo.ai`. `/api/v1/summarize` still returns clean 401 JSON envelopes (no regression). detect_faces' MTCNN/TensorFlow cold-start cost is real but not measured live yet — first paying call will pay ~10-30s; subsequent calls on the same replica are fast.
  - ⚠️ **`SYNZO_PUBLIC_URL=https://www.synzo.ai` is a hard requirement in Railway service vars.** Without it, the discovery endpoint's `resource` field falls back to `request.host_url` which sees `http://` (Railway terminates TLS at the edge, forwards plaintext). RFC 9728's `resource` is used by MCP clients for OAuth audience checks; an `http://` resource breaks token validation silently — Claude Desktop/web OAuth flows will reject every JWT. Captured + set 2026-06-05.
- [x] Tighten `initialize` instructions string — was claiming "transcribe audio" (deferred) and omitting "detect faces" (shipped). Fixed in [mcp_routes.py:158-160](mcp_routes.py#L158-L160).
- [x] Live MCP Inspector validation (API-key auth) — done 2026-06-05. Manual walkthrough surfaced one tooling gap (Inspector v0.22.0's OAuth panel can't drive DCR — only accepts a pre-registered client ID), so OAuth-path validation moves to Claude Desktop. To unblock end-to-end testing of every tool without manual base64 paste-and-click, added two scripts: [scripts/encode_for_inspector.py](scripts/encode_for_inspector.py) (one-shot file → base64 + filename for manual Inspector use) and [scripts/sweep_tools.py](scripts/sweep_tools.py) (automated tools/list + tools/call for all 5 tools, with response-shape assertions matching [mcp_tools.py](mcp_tools.py)'s contracts). Sweep ran 2026-06-05: 5/5 SUCCESS — see top-of-file status line for latencies.
- [x] Live OAuth path validation — done 2026-06-06 via **claude.ai web app** (not Claude Desktop; Desktop was blocked by the work account's org-level "connectors disabled" policy, and Inspector v0.22.0's OAuth panel only accepts pre-registered client IDs, not DCR). claude.ai exercised the full chain: DCR auto-registration → WorkOS sign-in → token issuance → bearer attached to `tools/call` → `Synzo:summarize_document` handler executed → structured-output summary rendered in the chat. Three OAuth bootstrap problems surfaced and fixed during this validation — see new §6.2 below for the lessons.

### 6.2 — OAuth bootstrap lessons (learned the hard way on 2026-06-06)

The day was substantially longer than expected because three issues stacked: each one masked the next. Documented here so a future re-implementer (or a different WorkOS environment) doesn't repeat them.

**Symptom that started the chase.** claude.ai's Add-Custom-Connector flow accepted `https://www.synzo.ai/mcp`, fetched `tools/list` successfully (5 tools rendered), but *no WorkOS sign-in prompt ever appeared*. When the user ran a tool, the response was "It looks like the Synzo connector isn't currently authorized in this session." Disconnect/reconnect, fresh browsers, InPrivate windows — none of it helped. Looked like nothing was happening at all.

**Why it was hard to diagnose.** Every failure mode in the OAuth bootstrap chain manifests as the *same* user-visible symptom: no sign-in prompt, plus a "not authorized" error on tool call. The actual problem could be at any of four layers, and at the surface they all look identical.

**The three actual problems, in the order they had to be fixed:**

1. **Server returned HTTP 200 for unauthenticated `tools/call`** (commit `42de97e`). The JSON-RPC error envelope correctly carried `-32001 Missing Authorization header`, but the HTTP layer returned 200 OK with no `WWW-Authenticate` header. Per MCP authorization spec §2.1 + RFC 9728: an unauthenticated `tools/call` MUST return HTTP 401 with `WWW-Authenticate: Bearer realm="...", resource_metadata="https://www.synzo.ai/.well-known/oauth-protected-resource"`. Without this, MCP clients (including claude.ai) treat the JSON-RPC error as a tool failure and never initiate OAuth.

   **Test that pins it:** `test_tools_call_without_auth_returns_401_with_www_authenticate` + `test_tools_call_without_auth_exposes_www_authenticate_via_cors` in [tests/test_mcp_server.py](tests/test_mcp_server.py). CORS exposure is the second half of the fix — browsers strip `WWW-Authenticate` from cross-origin responses unless it's listed in `Access-Control-Expose-Headers`. We learned that one the easy way (caught in test review), not the hard way.

2. **WorkOS discovery document omits `registration_endpoint`** (commit `49915d0`). After the 401 fix, claude.ai dutifully fetched `/.well-known/oauth-protected-resource`, followed the `authorization_servers` pointer to WorkOS, fetched WorkOS's discovery doc — and silently gave up. WorkOS's OAuth Authorization Server Metadata (RFC 8414) doesn't include the `registration_endpoint` field, even though the actual `/oauth2/register` endpoint on AuthKit fully implements RFC 7591 DCR (proven via curl). MCP clients read the discovery doc, see no registration endpoint, and abandon the bootstrap.

   **The fix:** host our own `/.well-known/oauth-authorization-server` route that proxies WorkOS's AuthKit metadata and *injects* `registration_endpoint: <authkit_subdomain>/oauth2/register`. Then change `/.well-known/oauth-protected-resource` to advertise OUR URL as the authorization server (so clients pull our augmented doc, not WorkOS's bare one). See `oauth_authorization_server()` in [mcp_routes.py](mcp_routes.py).

   **Subtlety: AuthKit subdomain vs `api.workos.com`.** WorkOS publishes two different discovery docs at two different URLs. The `api.workos.com/user_management/<client_id>` URL serves a minimal doc with no PKCE, no scopes, no grant types. The AuthKit hosted-UI subdomain (`<tenant>.authkit.app`) serves the RFC 8414 doc with PKCE/scopes/grants populated. **`WORKOS_ISSUER` and `WORKOS_JWKS_URL` env vars MUST point at the AuthKit subdomain.** Original Phase 1 setup used the `api.workos.com` URL because that's what the WorkOS docs initially surface; changing the env vars to the AuthKit URL was the second half of fixing this issue.

3. **WorkOS environment had DCR disabled by default** (config change in WorkOS dashboard, no commit). After commits 1 and 2 shipped, claude.ai *did* attempt to register at `/oauth2/register` — and WorkOS responded `{"error": "dynamic_client_registration_disabled", "error_description": "Dynamic client registration is disabled for this environment."}`. The fix: WorkOS dashboard → environment → Connect → Configuration → **MCP Auth → Manage → enable Dynamic Client Registration**.

**Test order matters when debugging this chain.** Each layer needs an authoritative live curl check before moving to the next. The right order is:

```bash
# 1. tools/call must return HTTP 401 with WWW-Authenticate present and CORS-exposed
curl -isS -X POST https://www.synzo.ai/mcp -H 'Origin: https://claude.ai' \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"summarize_document","arguments":{"filename":"x.pdf","content_base64":"YQ=="}}}' \
    | head -15
# Expect: HTTP/1.1 401 Unauthorized + www-authenticate + access-control-expose-headers includes WWW-Authenticate

# 2. protected-resource must advertise OUR URL as the auth server
curl -sS https://www.synzo.ai/.well-known/oauth-protected-resource | python -m json.tool
# Expect: authorization_servers: ["https://www.synzo.ai"], NOT a WorkOS URL

# 3. auth-server doc must have registration_endpoint
curl -sS https://www.synzo.ai/.well-known/oauth-authorization-server | python -m json.tool
# Expect: registration_endpoint, code_challenge_methods_supported, grant_types_supported

# 4. WorkOS DCR must actually accept registrations
curl -isS -X POST https://<tenant>.authkit.app/oauth2/register \
    -H 'Content-Type: application/json' \
    -d '{"client_name":"test","redirect_uris":["https://claude.ai/api/mcp/auth_callback"],"token_endpoint_auth_method":"none","grant_types":["authorization_code","refresh_token"],"response_types":["code"],"scope":"openid profile email offline_access"}' \
    | tail -3
# Expect: a real client_id back; NOT "dynamic_client_registration_disabled"
```

If all four pass, claude.ai will OAuth successfully. If any one fails, that's the layer to fix before retrying in claude.ai.

**Side effect: changing `WORKOS_ISSUER` invalidates existing dashboard sessions.** The dashboard's session JWT was issued under the old `api.workos.com` issuer; after the env-var swap, JWT validation in [auth.py](auth.py)'s `_resolve_oauth` rejects it. Sign out + sign back in resolves it. Caught us once on 2026-06-06; documented here so we expect it next time.

### Phase 2.5 — Concurrency hardening: thread bump → SSE streaming [must precede public-launch traffic]

**Why this phase exists.** The Phase 2 slice runs synchronously: a `tools/call` holds one Waitress worker thread for the entire Gemini turnaround. Default `threads=4`, so four concurrent summarize calls block every other request to the entire Flask app (homepage, dashboard, `/api/v1/*`, `/mcp` health). A 600-page PDF on the `pro` plan can hold a thread for 60-90 seconds. This is latent today (free-tier per-call cap is 20 pages, so reviewers can't trigger it), but becomes a real outage risk the moment paying customers exist.

**Phase 2.5.A — Thread bump + hard timeout (immediate, before any public launch). DONE 2026-06-05 (deployed live on commit `214e5f3`).**

- [x] Bump waitress to `threads=32` in the Railway start command. Implemented in [run.py](run.py) as `os.environ.get("WAITRESS_THREADS", "32")` — env-tunable so we can dial back without a redeploy if a replica is memory-constrained. 8× the headroom for blocking handlers.
- [x] Wrap every MCP tool handler (and `/api/v1/*` handler) in a hard wall-clock timeout (~60s). On timeout: refund quota, meter as `refunded`/`timeout`, return JSON-RPC error / HTTP 504. Implemented in [auth.py](auth.py) as `_run_with_timeout()` invoked from `run_metered_tool()` — covers both surfaces uniformly. Uses `concurrent.futures.ThreadPoolExecutor` (per-call, pool size 1) + `Future.result(timeout=...)` for portable cross-thread timeouts; `flask.copy_current_request_context` propagates both app and request context to the worker thread so handlers can keep reading `current_app.config` and `request.files`. On timeout, `pool.shutdown(wait=False)` releases the Waitress thread immediately; the worker thread leaks until its downstream call (Gemini HTTPS) unblocks naturally (CPython can't force-kill threads, but Gemini's HTTPS timeout bounds the leak). New JSON-RPC error code `MCP_TIMEOUT = -32005` (maps from `AuthError(status=504)`). Env-tunable via `MCP_TOOL_TIMEOUT_SECONDS` (default 60; 0 disables wrapping for tests).
- [x] Add a load test (locust or a simple asyncio script) that fires 32 concurrent `summarize_document` calls against a stubbed Gemini and confirms the homepage stays responsive throughout. Run before any public-launch deploy. Built as [scripts/concurrency_load_test.py](scripts/concurrency_load_test.py) — a runnable script (not a pytest test) that points at any base URL, fires N concurrent `tools/call` invocations while a background thread probes `GET /` every 200ms, and fails if homepage p99 > threshold. Operational gate, not a CI gate. **Still needs to be run live before the next deploy.**
- [x] Test coverage for the timeout pipeline added in [tests/test_mcp_concurrency.py](tests/test_mcp_concurrency.py) (5 tests): timeout fires → refund + `timeout` meter; fast handler → unaffected; handler exception → existing refund path still works; `TOOL_TIMEOUT_SECONDS=0` disables wrapping (handler runs inline); worker thread receives both app and request context. Test suite: 87/87 passing (was 82/82).
- [x] Document the cap: "single Railway replica = ~32 concurrent in-flight tool calls before backpressure." When we cross that, do Phase 2.5.B.
- [x] **Deploy** the threads-bump + timeout to Railway (commit `214e5f3` on origin/master 2026-06-05; Railway auto-deployed).
- [ ] Run [scripts/concurrency_load_test.py](scripts/concurrency_load_test.py) against the live deployment with `--concurrency 32` before any public launch.

**Phase 2.5.B — SSE streaming + background workers (before "real customer" traffic).** The proper fix. The 2025-06-18 Streamable HTTP spec already permits this — we picked the JSON branch for the slice because it was sufficient, not because the SSE branch was wrong.

- [ ] Add Redis to Railway (already deferred in Phase 0; this is the trigger).
- [ ] Add a worker process (RQ first — simpler than Celery; switch if we need scheduled jobs). One worker dyno on Railway alongside the Flask web dyno.
- [ ] Refactor `mcp_routes.py`'s `tools/call` to support the SSE branch: when a tool's expected duration > 5s (heuristic on `units_fn`), enqueue the job, hold the HTTP connection open, emit JSON-RPC `notifications/progress` events from the worker via Redis pub/sub, send the final JSON-RPC response when the worker finishes, then close the stream.
- [ ] `/api/v1/*` gets a parallel async surface: either keep synchronous + add an `Accept: text/event-stream` branch, or split into `POST /api/v1/jobs` + `GET /api/v1/jobs/<id>`. Decide at implementation time.
- [ ] Web workers stop blocking on Gemini entirely; one Waitress thread per *connection*, not per *Gemini call*. Concurrency ceiling becomes Redis + Postgres connection pool size, not Waitress thread count.
- [ ] **Tenancy invariant survives:** the worker reads `principal.org_id` from the enqueued job payload and scopes everything on it. Cross-tenant isolation tests get extended to cover the worker path (Org A's job never writes Org B's `usage_events`).

**Sequencing decision.** Phase 2.5.A ships with Phase 2 — it's the minimum to safely take Anthropic submission traffic. Phase 2.5.B is **not** required for submission (reviewers won't hammer us with 600-page PDFs) but **is** required before any "you can buy a `pro` plan" public launch. The trigger to start 2.5.B is the first of: (a) we hit the 32-thread ceiling in production logs, (b) a real customer asks about long-doc support, or (c) we're starting Phase 4.

### Phase 3 — Submission readiness [~3 days]

> **Phase 3 progress as of 2026-06-07:** 11 commits shipped on 2026-06-06 + 6 additional commits on 2026-06-07 (vision UX fix `11a2ff0`, sample-files matrix + plan lock `4af101f`, reviewer-bundle.zip + walkthrough `6defeb7`, email swap `8b1af35`, `/auth/logout` AuthKit-termination fix `bf4081c`, walkthrough revert + inline-credentials plan `9219b22`) + `SECURITY.md` authored 2026-06-07. Six policy-compliance audits completed (all PASS); all nine test-suite gaps from the 2026-06-06 adversarial review closed; +2 logout regression tests 2026-06-07 (**142/142 tests green**, was 107 at the start of the review pass; +35 total across the pass). Five public pages (`/docs`, `/privacy`, `/terms`, `/support`, `/security`) live and styled. Per-org RPM cap named in `-32003` (commit `3a33950`); `analyze_image` `fields` selector **skip for v1** (documented as a submission-note item). Remaining: **live MCP Inspector validation**, **integration tests for the four non-summarize tools**, **mailbox aliases via Cloudflare** (`support@`, `privacy@`, `security@`, `mcp-review@`) — gated on synzo.ai DNS migration to Cloudflare (deferred to post-submission, see locked-decisions box in Phase 3.5 "Reviewer test bundle"), **README ↔ /docs audit**, and **Gemini API-ownership framing for §7**.

**Technical hardening**
- [ ] Validate with MCP Inspector locally + against the deployed Railway URL.
- [ ] Write integration tests (pytest) for each MCP tool with mocked Gemini. (Partial: summarize_document is end-to-end through `/mcp`; translate/redact/analyze/detect are unit-tested only. Reviewer-blocker risk is low because the JSON-RPC plumbing is shared, but worth filling in.)
- [x] Write OAuth flow tests (mock WorkOS). **DONE 2026-06-06** as part of the test-suite review pass. [tests/test_oauth_resolver.py](tests/test_oauth_resolver.py) pins all seven `_resolve_oauth` raise sites + happy path + User/OrgMembership upsert + the §3.4 invariant that a misdirected token can't reassign a user across tenants (12 tests, mint signed RS256 JWTs against a generated keypair, stub `_get_jwks_client`). [tests/test_mcp_server.py](tests/test_mcp_server.py) adds three OAuth-bearer-through-`/mcp tools/call` tests proving (a) a non-`sk_` bearer routes to `_resolve_oauth` and meters the call with `auth_method='oauth'`, (b) `AuthError` from `_resolve_oauth` surfaces as HTTP 401 + WWW-Authenticate + JSON-RPC -32001 with no usage_events row, (c) cross-tenant isolation holds on the OAuth path — closing the §3.4 gap that the existing api_key-only isolation test left open. Total 122/122 tests green.
- [x] **`/auth/logout` properly terminates the AuthKit session, not just the Flask cookie.** **DONE 2026-06-07** (commit `bf4081c`). The original `/auth/logout` only called `session.clear()`, which dropped our local cookie but left AuthKit's own session cookie intact — so signing out and back in silently re-issued the same identity. Blocked the "switch to a different account" flow (caught while trying to sign up the reviewer test account in the same browser as the owner account). Fix: stash `claims['sid']` into the Flask session at `/auth/callback` (the AuthKit session id) and `/auth/logout` now reads it back, calls `workos.user_management.get_logout_url(session_id=..., return_to=request.url_root)`, and redirects the browser through AuthKit's logout endpoint so AuthKit terminates its cookie and bounces back to our site. Three fallback paths preserved: missing `workos_session_id` (legacy pre-fix logins, expired session) → local-only logout + redirect home; WorkOS SDK call raises (network blip, SDK shape drift) → logged warning + local-only logout; empty/None session id → same as the first path. None of them leaves a user on a 500 with their cookie intact. **+2 regression tests** in [tests/test_auth_routes.py](tests/test_auth_routes.py): `test_logout_redirects_to_workos_logout_when_session_id_present` pins the redirect target and the `session_id` / `return_to` passed to the SDK; `test_logout_falls_back_to_local_only_when_workos_call_fails` pins the SDK-raises path. The existing `test_logout_clears_session` keeps passing as-is (it exercises the no-session-id branch). **142/142 tests green** (was 140).
- [x] Add file-type detection via magic bytes. **DONE 2026-06-07.** Picked `filetype` (pure-Python, no libmagic system dep — works on Windows dev + Railway). New helper `_verify_magic_bytes(raw, ext)` in [mcp_tools.py](mcp_tools.py) wired into all 5 MCP tool sites after their existing ext-set check ([mcp_tools.py:192](mcp_tools.py#L192), [:280](mcp_tools.py#L280), [:351](mcp_tools.py#L351), [:416](mcp_tools.py#L416), [:503](mcp_tools.py#L503)). On mismatch raises `ToolError` → routes through the existing `isError=true` channel (NOT `-32004`; that code is units-exceeded). Plan-doc's `-32004` instinct was wrong: mismatched magic bytes are an argument problem, not a quota one, so the existing `ToolError` → `isError=true` path is the right shape — model can recover, quota is refunded by `run_metered_tool`. `filetype` distinguishes docx/pptx/xlsx by peeking inside the zip's directory listing (it doesn't just see "zip"). HEIC and HEIF map to the same `heic` detection result (both use the ISO BMFF container with `heic` brand). Feature-module sites at [features/summarization/utils.py:97](features/summarization/utils.py#L97) and [features/translation/routes.py:140](features/translation/routes.py#L140) intentionally left alone — they're dispatch-only and already gated by the MCP/HTMX layer above. New test file [tests/test_magic_bytes.py](tests/test_magic_bytes.py) (21 tests): every supported extension accepts genuine files; every cross-format combo rejects (PDF-in-docx, docx-in-pdf, jpg-in-png, docx-in-pptx, xlsx-in-docx, random text in pdf); error message includes detected type; end-to-end through `/mcp tools/call` for all 5 tools (mismatch → `isError=true` + quota refunded); unknown-extension no-op for defensive completeness. **163/163 tests green** (was 142; +21). One drive-by fix: 6 existing MCP tests used stub byte payloads (`b"PK fake docx"`, `b"\xff\xd8"`) that weren't real-shaped enough for magic-byte detection — swapped for a new `_minimal_ooxml_bytes()` helper in [tests/test_mcp_server.py](tests/test_mcp_server.py) (real zip with the right marker dir) and bumped the JPG stubs to `\xff\xd8\xff` (filetype's minimum).
- [x] Wrap Gemini calls with tenacity (retry + circuit breaker). **DONE 2026-06-07.** New module [gemini_retry.py](gemini_retry.py) exports `retry_gemini_call` — a tenacity decorator that retries on transient errors (`google.api_core.exceptions.ServiceUnavailable` / `DeadlineExceeded` / `InternalServerError` / `ResourceExhausted`) **only**, with 3 attempts and exponential backoff 1s/2s/4s (~7s worst case, well under `MCP_TOOL_TIMEOUT_SECONDS=60`). Terminal errors — `InvalidArgument`, safety-filter blocks (which arrive as a normal response with empty `.text` + populated `prompt_feedback.block_reason`), arbitrary `ValueError` / SDK bugs — propagate immediately on attempt 1. `reraise=True` so the underlying exception (not `tenacity.RetryError`) surfaces. Wrapped 3 non-streaming sites: [features/summarization/agents/analyst_agent.py:24](features/summarization/agents/analyst_agent.py#L24) (classification call), [features/translation/routes.py:32](features/translation/routes.py#L32) (`translate_text_util`'s Gemini call), [features/multimedia/analytics_utils.py:49](features/multimedia/analytics_utils.py#L49) (`analyze_image_with_gemini`'s Gemini call). **Streaming sites deliberately NOT wrapped**: [analyst_agent.py:79](features/summarization/agents/analyst_agent.py#L79) and [designer_agent.py:316](features/summarization/agents/designer_agent.py#L316) both use `stream=True`; mid-stream retry would yield duplicate content because chunks already emitted to the caller can't be replayed. Documented as a known gap; the v1 risk is bounded because the summarize streaming call is preceded by the classification call which IS retried, and a sustained streaming-side outage would hit the 60s `MCP_TOOL_TIMEOUT_SECONDS` ceiling and refund the quota. New test file [tests/test_gemini_retry.py](tests/test_gemini_retry.py) (13 tests): every transient class retries; `InvalidArgument` + arbitrary exception don't retry; 3-attempt budget is hard (4th call would never run); end-to-end through all 3 wrapped sites — flaky model raises once → success on retry → exactly 2 calls; terminal model raises → caller-appropriate error shape (`General Business Document` fallback, `("error", ...)` tuple, `{"error": ...}` dict) → exactly 1 call. Test fixture patches `tenacity.nap.time.sleep` to a no-op so the suite stays fast (~1.6s) without touching the decorator's retry decisions or attempt count. **176/176 tests green** (was 163; +13).

**Test-suite gaps remaining (from 2026-06-06 adversarial review)** — **ALL CLOSED 2026-06-06** (commit details below):
- [x] `/api/v1/summarize` end-to-end happy/failure paths. **DONE.** New [tests/test_api_summarize_e2e.py](tests/test_api_summarize_e2e.py) — 7 tests: happy path + 503 (Gemini off) + 415 (bad ext) + 413 (oversize) + 400 (missing file field) + 504 (HTTP-path timeout, closes gap #2 in the same file) + refund-on-handler-exception. Quota + usage_events assertions cover the metering invariant.
- [x] Timeout pipeline on HTTP path (504 + JSON body + refund). **DONE.** Included in `test_api_summarize_e2e.py::test_api_summarize_504_when_handler_exceeds_timeout` (same fixture as the rest of the e2e file).
- [x] `_resolve_api_key` raise sites: malformed key, revoked, orphan. **DONE.** Three new tests in [tests/test_auth_failures.py](tests/test_auth_failures.py): `test_401_when_api_key_lacks_sk_prefix` (drives via X-API-Key to force the api_key branch), `test_401_when_api_key_is_revoked` (sets `revoked_at` on the seeded key), `test_401_when_api_key_orphaned_from_org` (sets `org_id` to a non-existent id).
- [x] Tools/call >50MB transport cap + 10MB decoded-content cap at JSON-RPC layer. **DONE.** Two new tests in [tests/test_mcp_server.py](tests/test_mcp_server.py): `test_post_body_above_50mb_returns_413_without_parsing` (sends real 50MB+ JSON body so Werkzeug's test client doesn't strip Content-Length), `test_tools_call_decoded_content_above_10mb_returns_isError` (uses a **pro-plan** org so the units check at [auth.py:395](auth.py#L395) doesn't 413 the request before the handler runs — gotcha for the next person adding integration tests with large payloads).
- [x] `/.well-known/oauth-protected-resource` CORS + SYNZO_PUBLIC_URL fallback. **DONE.** Two new tests in `test_mcp_server.py`: `test_oauth_protected_resource_exposes_cors_to_claude_ai`, `test_oauth_protected_resource_falls_back_to_host_url_when_env_unset` — the second pins the *route* still returns well-formed output when the env var is missing; the deployment-time invariant (`SYNZO_PUBLIC_URL` MUST be set in Railway, see §6 Phase 2 "Railway config added 2026-06-05") stays documented in the plan, not in tests.
- [x] JSON-RPC `id` echo on error responses. **DONE.** `test_jsonrpc_error_response_echoes_request_id` — sends `id: "abc-123"` (string, to catch any int-conversion bug) on an unauth tools/call, asserts the error envelope echoes it.
- [x] Generic Exception inside handler → `isError=true` + refund. **DONE.** `test_tools_call_handler_raises_generic_exception_returns_isError_and_refunds` — uses `dataclasses.replace` to swap `summarize_document`'s handler with one that raises `RuntimeError`, asserts the response carries `isError=true` (NOT a JSON-RPC envelope error so the model can recover) AND the usage row records `status='refunded', error_code='handler_error'`.
- [x] `Allow: POST, OPTIONS` header on 405 response. **DONE.** Existing `test_get_on_mcp_returns_405` tightened to assert the Allow header content; plus `test_delete_on_mcp_returns_405_with_allow` covers DELETE.
- [x] **Policy 5.A leak split** in [tests/test_api_auth.py](tests/test_api_auth.py). **DONE.** The leaky `assert status_code in (401, 500)` is gone. Replaced with two pointed tests: `test_api_summarize_rejects_malformed_oauth_bearer_when_jwks_configured` (stubs `_get_jwks_client` to simulate the production state — a real `DecodeError` from PyJWKClient → must 401 with actionable message) and `test_api_summarize_returns_500_when_jwks_env_unset_for_operator_visibility` (proves operator misconfig stays 500 so it lights up in logs, with the env var name surfaced in the error body so an operator can fix it). Recommendation (b) shipped: operator config errors SHOULD be 500.

**Total suite: 140/140** (was 122/122 → +18 tests across 4 files; new file: `tests/test_api_summarize_e2e.py`).

**Docs (public-facing pages on `www.synzo.ai`)**

> **Repo-visibility decision (2026-06-06):** GitHub repo will be made **private** before submission. This rules out using the GitHub README as the form's "Server Documentation Link" — reviewers must click a publicly reachable URL. All three form-required external links (Docs / Privacy / Support) will live on `www.synzo.ai`.
>
> **For MCP server submissions, a private repo is allowed.** The pre-submission checklist's "must link a public GitHub repo" rule is scoped to **Plugins** (Claude Code plugins), and we are not submitting a plugin. Verify this is still the case at submission time by re-reading the current checklist.
>
> **Reference model: Harvey's MCP submission.** Harvey ships three artifacts that map 1-to-1 to our three required links: (1) `developers.harvey.ai/api-reference/mcp` — the docs page; (2) `harvey.ai/legal/privacy-policy` — the privacy policy; (3) listed support URL. We mirror the **structure** of Harvey's pages but **scope the content to what Synzo actually does** — Harvey is a much larger product with marketing, analytics, training-data use, customer agreements, and a DPO; Synzo is a single-purpose document-intel API. Do not copy Harvey's content; copy the shape.
>
> **Three GDPR/scope decisions locked 2026-06-06:**
> - Docs polish: **match Harvey's structure** — hand-authored intro, Setup guides per client, tools table, Troubleshooting, FAQ. The tools table is the only piece rendered from README to keep the source-of-truth invariant; the rest is static templates.
> - GDPR scope: **accept EU/UK users.** Privacy policy must be GDPR-compliant (lawful basis, data subject rights, international transfers via SCCs, DPO contact mailbox).
> - Support channel: **static page + mailbox + response SLA** at `synzo.ai/support`, mailbox `support@synzo.ai` via Cloudflare Email Routing.

The deliverable is three new public routes: `/docs`, `/privacy`, `/support`. All three are unauthenticated (public-site surface per §3.3), CSRF-protected (cookie-based — same as the rest of the public site), and linked from a new global footer in `templates/layout.html`. **Shipped as of 2026-06-06**: all three plus `/security` and `/terms` (lifted from the prior `/about` Legal Notice tab). Routes registered in [docs_routes.py](docs_routes.py); partials under [templates/partials/](templates/partials/) wrap content in the canonical `.feature-container` from [static/css/style.css](static/css/style.css) (commit `c844753` reused the app's CSS system instead of inventing new card classes).

**Route 1 — `/docs` (modeled on `developers.harvey.ai/api-reference/mcp`)**

- [x] **Build `templates/docs.html` with five sections, matching Harvey's structure:** **DONE** — [templates/partials/_docs_content.html](templates/partials/_docs_content.html). Lives in a `.feature-container` card; sections use the global `h2/h4/p` typography and the `.legal-section` helper added to [style.css](static/css/style.css).
  1. **Hero**: "Synzo MCP Server" (h1) + one-sentence pitch + one-paragraph description of what the MCP server does (what Anthropic's "Software Directory" purpose statement requires per Policy 3.C). Hand-authored.
  2. **What is Synzo MCP?** — One paragraph + a bulleted "What can you do with it" list with one bullet per tool (5 bullets). Hand-authored. Tool-name references must match the live registry in [mcp_tools.py](mcp_tools.py).
  3. **Setup guides** — Step-by-step for **Claude.ai (web)** and **Claude Desktop**, mirroring Harvey's numbered lists. Walk through: add custom connector, paste `https://www.synzo.ai/mcp`, OAuth sign-in via WorkOS, confirm 5 tools appear in `tools/list`. Hand-authored against the OAuth flow proven on 2026-06-06. **Note** Claude Desktop blocker for work accounts (per §6.2) somewhere visible.
  4. **Available tools** — **THIS IS THE ONE SECTION RENDERED FROM A CODE-DERIVED SOURCE.** Three-column table (Tool / Description / Example prompt) matching Harvey's table exactly. The tool list, descriptions, and schemas come from the live MCP registry in [mcp_tools.py](mcp_tools.py); example prompts are authored once in a sidecar file (`docs/tool_examples.yaml` or similar — see render model below).
  5. **Troubleshooting** + **FAQ** — Accordion-style sections (or plain `<details>` blocks if no JS framework is in use). Hand-authored. Seed troubleshooting items from the actual JSON-RPC error codes in [mcp_routes.py:60-64](mcp_routes.py#L60-L64): "Authentication fails or token is rejected" → re-authenticate per §6.2 curl checks; "Invalid file type" → file type derived from extension/magic bytes; "Quota exceeded (-32002)" → check `/dashboard/usage`; "Rate limit exceeded (-32003)" → wait or upgrade plan; "Tool timed out (-32005)" → file too large for plan tier. Seed FAQ from Harvey's pattern: "Can multiple users connect?" / "What data does the server have access to?" / "Does this support conversation history?" — re-author each answer against Synzo's actual code, not copied from Harvey.
- [x] **Render model for the tools table — render-once-and-cache, but from the MCP registry directly (not the README).** **DONE** — [docs_renderer.py](docs_renderer.py) walks `mcp_tools.TOOLS` and joins against [docs/tool_examples.yaml](docs/tool_examples.yaml) at `create_app()` startup. Raises `DocsExampleDrift` on any mismatch (extra tool, missing tool, missing `example_prompt` field, empty prompt). HTML cached on `app.config["DOCS_TOOLS_TABLE_HTML"]` and rendered into the partial as a Jinja `Markup` value. Plan refinement notes preserved below for context:
  - Earlier plan said: render README to HTML, cache, serve at `/docs`.
  - **New plan:** the README stays the canonical *developer* doc (lives in the private repo, audience = future maintainers). The public `/docs` page is a hand-authored Jinja template; the only dynamically-rendered piece is the tools table, which reads from [mcp_tools.py](mcp_tools.py)'s `TOOLS` list at app startup.
  - Why: Harvey's docs page is structured and product-like (intro → setup → tools → troubleshooting → FAQ), not a rendered README. Trying to express that structure inside `README.md` would warp the README for the wrong audience.
  - **Source-of-truth invariant for the tools table:** at startup in `create_app()`, walk [mcp_tools.py](mcp_tools.py)'s registry; for each tool, pull (`name`, `description`, `annotations.title`) and join against a sidecar file `docs/tool_examples.yaml` (one example prompt per tool, hand-authored). Build the HTML table once, cache as a module-level string, inject into `templates/docs.html` as a Jinja variable. If a tool is added to the registry without a matching example in the sidecar, raise at startup so the discrepancy can't ship to prod.
  - On `flask run --debug` (`FLASK_DEBUG=1`), re-render the cache each request so authoring locally doesn't require a restart. In prod (Waitress), the startup cache is final.
  - New deps in [requirements.txt](requirements.txt): `pyyaml` (for the sidecar). `markdown` is no longer needed for `/docs` (no README rendering); keep an eye on whether Phase 3 needs it for any other page (probably not).
- [x] **Tests for `/docs`:** **DONE** — [tests/test_docs_renderer.py](tests/test_docs_renderer.py) covers 8 cases (happy path, missing tool, extra tool, malformed entry, empty prompt, registry-order render, XSS escape, live-YAML-matches-registry); [tests/test_smoke.py](tests/test_smoke.py) `test_docs_page_lists_every_registered_tool` asserts every tool name + title renders on `GET /docs`. Note: the partial's section headings are `<h2>What is Synzo MCP?`, `<h2>Setup guides</h2>`, `<h2>Available tools</h2>`, `<h2>Troubleshooting</h2>`, `<h2>FAQ</h2>` — the smoke test currently asserts tool names only, not the section heading strings; if reviewers care about exact heading text consider adding an assertion at submission time.
- [ ] **Pre-submission audit:** read the rendered `/docs` against the live tool registry once. Confirm every tool name, description, and example prompt is accurate. Re-author setup guides if claude.ai's connector UI has shifted since 2026-06-06.

**Route 2 — `/privacy` (modeled on `harvey.ai/legal/privacy-policy`, scoped to Synzo)**

> **GDPR scope locked:** Synzo accepts EU/UK users at submission time. The policy is GDPR-compliant — not minimal-viable US-only.

- [x] **Build `templates/privacy.html` with the following sections** (mirroring Harvey's structure, scaled to Synzo's actual surface — Harvey's policy is ~7000 words across 12 sections; Synzo's should be ~2000-3000 words across the same skeleton because we have far fewer data flows): **DONE** — [templates/partials/_privacy_content.html](templates/partials/_privacy_content.html). All 12 sections present. **Code-review pass on 2026-06-06 corrected four inaccuracies** (commit `16a4b30`): the local `users` table stores email + WorkOS IDs only, not name; `usage_events` records `auth_method` (not "OAuth sub"); the HTMX upload surface uses S3-compatible scratch storage; S3-compatible was added to §4 providers. Verified no Sentry/Datadog/PostHog/GA SDKs are present — claim about no third-party trackers is grounded in a grep. The skeleton below documents the intended structure section by section:
  1. **Applicability** — what this policy covers (the website, the MCP server, the JSON API, the dashboard). What it doesn't cover (Gemini's processing of file contents on Google's side — link to Google's policy).
  2. **Personal Data we Collect** — three subsections:
     - *Account Information* — email, name (from WorkOS), org name, API key metadata. Source: the WorkOS sign-up flow + `users` + `orgs` tables.
     - *Usage Data* — `usage_events` rows: `org_id, api_key_id, auth_method, tool, units, status, error_code` per [auth.py:307-325](auth.py#L307-L325). **Explicit statement: file bodies are NEVER persisted; they exist only in memory during the tool call.**
     - *Log Data* — IP, user-agent, request timestamps (Railway edge logs + Flask access logs).
     - *Cookies* — Flask session cookie (set by [auth_session.py](auth_session.py)). No third-party trackers; no analytics. Confirm against the live site before publishing (the §1.D observability audit in Phase 3 will catch any drift here).
  3. **How we Use Personal Data** — bulleted list. Synzo's list is much shorter than Harvey's because we don't do marketing/research/personalization: (a) provide the service, (b) bill (Phase 4), (c) support, (d) security/fraud prevention, (e) legal compliance. Each bullet should be honest about what we *actually* do today; defer the Phase-4 ones with "if and when we launch paid plans."
  4. **Who we Share Data With** — Affiliates: none (we're a sole-prop / single-entity). Service providers: Google Gemini, WorkOS, Railway, Microsoft Presidio (runs in-process — clarify it's a library, not a data transfer). Each named with a link to their policy. Law enforcement: standard language.
  5. **Security** — short paragraph: TLS in transit (Railway edge), encrypted at rest (Postgres on Railway), API keys SHA-256 hashed per [auth.py](auth.py)'s `issue_api_key` / `_resolve_api_key`. Pointer to `SECURITY.md` / `/security` for vulnerability reporting.
  6. **International Data Transfers** — Synzo is hosted on Railway in the US; if we accept EU users, their data transits to the US. Rely on **Standard Contractual Clauses (SCCs)** for EU/UK/Swiss transfers (the simplest defensible mechanism for a small operator; Harvey relies on DPF certification but DPF certification is a non-trivial process Synzo isn't yet certified for). Disclose this honestly.
  7. **Data Retention** — `usage_events`: retained until billing dispute window closes (decide 90 days vs. indefinite; pick something defensible and live with it). User accounts + memberships: retained until deletion request; deleted within 30 days of request. Document body data: never retained.
  8. **Jurisdiction-specific provisions:**
     - *EEA/UK/Switzerland*: lawful bases — Contract (for providing the service), Legitimate Interest (for security/fraud), Consent (for any non-essential cookies — currently none). Data subject rights: access, rectification, erasure, portability, objection. Right to lodge complaint with supervisory authority.
     - *United States / California (CCPA)*: categories of PI collected (Account, Usage, Log, Cookies), purposes, "we do not sell or share PI" (true — verify against any current ad network integration). Right to know / delete / opt-out.
     - Defer Canada-specific PIPEDA section unless we have evidence of Canadian users.
  9. **Minors** — Services not directed to under-18; we do not knowingly collect from minors.
  10. **Your Data Protection Rights** — how to exercise: email `privacy@synzo.ai`.
  11. **Updates to this Policy** — versioning + how we notify (email all org owners).
  12. **How to Contact us** — `privacy@synzo.ai` (set up via Cloudflare Email Routing alongside `support@synzo.ai`). Optional: postal address — defer unless GDPR explicitly requires (it does for DPO-required orgs; Synzo is below the threshold for mandatory DPO appointment, but providing a contact is best practice).
- [x] **Decide retention windows before publishing.** **DONE** — 90 days for `usage_events`, 30 days for deletion processing. Cited in §7 of the published policy.
- [ ] **Set up `privacy@synzo.ai` mailbox** via Cloudflare Email Routing → Paul's real inbox. Same setup as `support@synzo.ai`. (No code change — Cloudflare dashboard config only.)
- [x] **Mirror the page at a stable URL** that won't change. **DONE** — `https://www.synzo.ai/privacy` (route in [docs_routes.py](docs_routes.py)). Sibling `/terms` also live, so we already implicitly have the namespace split.

**Route 3 — `/support` (static page + mailbox + response SLA)**

- [x] **Build `templates/support.html` with the following sections:** **DONE** — [templates/partials/_support_content.html](templates/partials/_support_content.html). All six sections present, including the "do not paste document contents" privacy-hygiene warning (uses the existing `.message-item.category-info` component from style.css for consistency). Also a separate `/security` page at [templates/partials/_security_content.html](templates/partials/_security_content.html) for vulnerability disclosure.
  1. **Hero**: "Synzo Support" + one-line "How to reach us when something isn't working."
  2. **Contact mailbox**: `support@synzo.ai` prominent on the page. Cloudflare Email Routing → Paul's inbox.
  3. **Response SLA**: explicit promise — "We respond to support requests within **2 business days**." Pick a number you can actually hit; Anthropic's Terms ("address issues within reasonable timeframes") sets the floor.
  4. **What to include in a report**: org ID (visible at `/dashboard`), tool name, approximate timestamp, error code (e.g. `-32001` thru `-32005`). **Explicitly tell users NOT to paste document contents into support emails** — this is both a policy compliance point and a basic privacy hygiene message.
  5. **Quick-reference troubleshooting**: cross-link to the `/docs` Troubleshooting section so users self-serve before emailing.
  6. **Security vulnerabilities**: separate disclosure path — `security@synzo.ai` (Cloudflare Email Routing alias) plus a link to `SECURITY.md` or `/security`. Anthropic's Terms require a mechanism for receiving security reports; this is it.
- [ ] **Set up `support@synzo.ai` and `security@synzo.ai` mailboxes** via Cloudflare Email Routing. Verify both deliver before publishing the page. (Note: the pages already reference these addresses; until the aliases exist, the links work but emails bounce — fix this before any external announcement.)

**Cross-cutting**

- [x] **Add a global footer to `templates/layout.html`** (currently has no footer per the 2026-06-06 audit). **DONE** — six links now (Docs, Pricing, Support, Security, Privacy, Terms) with brand-on-hover styling. Smoke test [tests/test_smoke.py](tests/test_smoke.py) `test_global_footer_links_present_on_homepage` guards against accidental removal.
- [x] **Promote the `/about` Legal Notice tab to a canonical `/terms` URL** (added scope, not in the original plan). **DONE** (commit `abb1faa`) — content lifted verbatim from `features/info/templates/info_content.html`; `/about` is now bio-only. Cross-link from `/terms` → `/privacy` for data-handling detail. Smoke test guards that `/about` no longer renders the old legal copy.
- [ ] **Audit `README.md` against `templates/docs.html`.** The README is now the developer-facing doc, not the public one. Confirm it still accurately covers the same tool list + auth flow + error codes — drift between README and `/docs` will hurt future maintainers. Aim for the README to be a superset of `/docs` (adds: running locally, test counts, stack details).
- [x] **Author `SECURITY.md`** scoped to the MCP server (existing `SAST_REPORT.md` is for the Flask app). **DONE 2026-06-07.** [SECURITY.md](SECURITY.md) at repo root mirrors the public `/security` page: scope (MCP / API / dashboard / website), reporting via `paul@redmapleresearch.ca` (the `security@synzo.ai` alias is deferred with the rest of the Cloudflare email work — see locked decision in Phase 3.5 reviewer-bundle), SLA matches `/security` (3 business days ack, 7 business days assessment), private-repo out-of-band fallback, no-PGP-by-default. Anthropic Software Directory Terms requirement ("implement and maintain a mechanism for receiving reports of security vulnerabilities") satisfied by the combination of `/security` (public) + `SECURITY.md` (in-repo for contributors).
- [ ] **Prepare reviewer test credentials + sample documents** — see Phase 3.5 "Reviewer test bundle" for the concrete artifact list.

**Policy-compliance audits (Anthropic Software Directory Policy §1, §2, §5)**

> **All six audits completed 2026-06-06.** Net result: 6/6 PASS, zero blockers. One small "while we're here" code tweak surfaced (rate-limit error message) and one Policy 5.B follow-up worth considering before submission (a `fields` selector on `analyze_image`). Both are noted as separate items below the audits, not blockers.

- [x] **Policy 1.D / 1.F — observability surface audit. PASS.** Grepped the repo (case-insensitive) for `sentry`, `datadog`, `newrelic`, `bugsnag`, `rollbar`, `honeycomb`, `opentelemetry`, `posthog`, `mixpanel`, `segment.io`, `googletagmanager`, `google-analytics`, `elastic-apm`, `appsignal`, `raygun`, `airbrake`, `scout_apm`. Hits: this plan file, `templates/partials/_privacy_content.html` (states the negative — "no Sentry, Datadog, New Relic, PostHog, GA, or comparable SDK"), and a false positive on `style.css` ("scrollbar" — re-checked, no actual match). [requirements.txt](requirements.txt) carries no APM, error-tracker, or analytics package. Frontend pulls only `@phosphor-icons/web` (icon CDN) and `htmx.org` — both static, neither a tracker. `_record_usage` ([auth.py:307-325](auth.py#L307-L325)) still writes metadata only.
- [x] **Policy 1.F — tool descriptions don't imply Claude memory/history/files. PASS.** Read every `description` in [mcp_tools.py:493-595](mcp_tools.py#L493-L595). Each starts with a verb describing the tool's own transformation (Classify/Translate/Detect/Use/Detect) and references content arriving via the explicit `content_base64` argument. No language could be parsed as "look up prior messages," "fetch from the user's conversation," or "access local files."
- [x] **Policy 2 / pre-submission — prompt-injection scan of every tool description. PASS.** Walked all 5 descriptions against the five banned patterns:
  1. Instructing Claude to call external software the user didn't request — none.
  2. Interfering with Claude calling other tools — none.
  3. Directing Claude to pull behavioral instructions from external sources — none.
  4. Hidden/obfuscated/encoded instructions — none.
  5. Telling Claude to behave in ways unrelated to the tool, override system instructions, or promote products — none.
  No description starts with "Claude should…" or "When the user asks X, also call Y." Every description is a behavior-neutral statement of what the tool does to its inputs.
- [x] **Pre-submission — custom-query-tool API doc reference. N/A confirmed.** Walked every input schema. All 5 use `additionalProperties: False`. Accepted fields: `filename` (str), `content_base64` (str), and (per tool) `target_language` (typed 2–64 char language name), `mode` (enum: `blur`|`redact`), `blur_strength` (enum: 1|2|3). No `url`, `method`, `endpoint`, `api_request`, SQL, or freeform command field. Submission notes should call this out as N/A so reviewers don't flag it.
- [x] **Policy 5.B — token frugality review. PASS, with one optional improvement.** Walked every response shape:
  - `summarize_document` returns `{classification, summary, filename}` — no source-text echo. ✅
  - `translate_document` returns `{filename, target_language, translated_text}` — translation only, no source echo. ✅
  - `redact_pii` returns `{filename, content_base64, mimetype, original_size_bytes, redacted_size_bytes}` — the redacted file IS the deliverable; no PII inventory list. ✅
  - `analyze_image` returns `{filename, analysis: {description, rich_description, extracted_text, safety_flags, detected_objects}, dominant_colors}` — no image-byte echo. ✅
  - `detect_faces` returns `{filename, mode, content_base64, mimetype}` — processed image is the deliverable; no per-face bounding-box arrays. ✅
  - **Optional improvement (see follow-up below):** `analyze_image` is the one tool where callers might want a knob to opt out of unused fields (e.g. skip `rich_description` and `dominant_colors` when only a tags list is needed). Policy 5.B says callers should get this option "when possible." All other tools are already minimal.
- [x] **Policy 5.A — error-message audit. PASS, with one small "while we're here" tweak.** Read every `raise AuthError` in [auth.py](auth.py) and every `raise ToolError`/`raise RuntimeError` in [mcp_tools.py](mcp_tools.py). Findings:
  - JSON-RPC `-32001` (auth): 12 distinct messages, all actionable. "Missing Authorization header", "Token expired", "API key revoked", "Org not provisioned", "Token missing org_id claim" (which directly maps to the §6.5.B WorkOS JWT-template config step), etc.
  - JSON-RPC `-32002` (quota): "Quota exhausted for this period" — actionable (upgrade plan / wait for reset).
  - JSON-RPC `-32003` (rpm): **"Rate limit exceeded"** — actionable but generic. Other quota-shaped errors include the actual cap (`-32004` includes `pages_per_call`, `-32005` includes `TOOL_TIMEOUT_SECONDS`). Worth one-line tweak: include the per-org RPM cap from `PLANS[principal.plan]["rpm"]`.
  - JSON-RPC `-32004` (units): includes the per-call cap. ✅
  - JSON-RPC `-32005` (timeout): includes the wall-clock value. ✅
  - `ToolError` raise sites in [mcp_tools.py](mcp_tools.py): every one names the exact problem (which arg is missing, the cap that was exceeded, the allowed extension list, the safety-filter reason). No generic "Bad Request" / "Internal Server Error" strings anywhere.
  - The remaining `RuntimeError` strings ("Translation failed", "PII redaction failed.", "Face detection / blurring failed.", "Image analysis failed (no response from AI service).") are last-resort fallbacks when downstream returned nothing usable; the structured `error_code` (`refunded`/`handler_error`) carries the disposition. Acceptable.
- [x] **MCP spec — Streamable HTTP transport confirmed; SSE not advertised. PASS.** [mcp_routes.py:279](mcp_routes.py#L279) returns `Content-Type: application/json` for every response; [mcp_routes.py:14](mcp_routes.py#L14) returns 405 for `GET`/`DELETE` on `/mcp` (no server-initiated SSE streams). Rationale is documented inline ([mcp_routes.py:8-21](mcp_routes.py#L8-L21)): the 2025-06-18 Streamable HTTP spec permits `application/json`-only for synchronous tool shapes; SSE is deferred to Phase 2.5.B. Phase 3.5 "Transport Support" form field should be answered "Streamable HTTP yes, SSE no" — submission notes should reference Phase 2.5.B as the future SSE work.

**Follow-up code tweaks surfaced by the audit (not blockers, but worth bundling into the next code commit):**
- [x] **Include the per-org RPM cap in the `-32003` message.** Done in this audit commit at [auth.py:404](auth.py#L404): `raise AuthError(f"Rate limit exceeded ({plan['rpm']} requests/min)", status=429)`. Matches the pattern used by `-32004` and `-32005`. No test update needed (the existing 429 test in [tests/test_auth_failures.py](tests/test_auth_failures.py) asserts on status code + `error_code == "rate_limited"`, not on the message string).
- [ ] **Decide whether to add a `fields` selector to `analyze_image`.** Policy 5.B's "when possible" wording is soft — defensible either way. If we add it: input schema gets `fields: { type: array, items: { enum: [description, rich_description, extracted_text, safety_flags, detected_objects, dominant_colors] }}`; handler filters its response by the selected fields. If we skip: document the decision in the submission notes ("response is already scoped to the task; per-field selection deferred until a user requests it"). My recommendation: **skip for v1**, document the decision, ship without the knob. The output is small enough (~hundreds of bytes of text + a 5–10-color hex list) that the marginal token saving isn't worth the API-surface complexity.

**Policy 1.E (intellectual property) — API ownership framing**
- [ ] Lock the answer to §7's open question. Anthropic policy 3.F: "Developers must verify that they own or control any API endpoint, domain, or user interface their Software connects to." Synzo's MCP server runs on `synzo.ai` (owned). Gemini is called server-to-server with our key as a legitimate proxy — the user never sees a Gemini endpoint, never authenticates against Gemini, and Gemini is named in the privacy policy. Document this framing in the submission notes: "Synzo's document-intelligence API, Gemini-powered. The MCP server is first-party; Gemini is a downstream model provider, analogous to how an SaaS app uses AWS." If a reviewer pushes back, the fallback is to add explicit "powered by Google Gemini" disclosure in the tool descriptions and listing copy.

### Phase 3.5 — Submission package (Anthropic Directory form deliverables) [~1–2 days]

Non-code deliverables for the submission form. Pull together in parallel with Phase 3. The form has six pages; the structure below mirrors them so nothing slips through.

> **Important:** every form answer below must be authored fresh against the *current* code and product state. Do not assume any answer carries over from prior unrelated form attempts. Verify each claim against the repo / live site before checking the box.

**Identity & contact (form page 1)**
- [ ] Company/Organization name + URL.
- [ ] Primary contact: name, email, role (Paul O'Hagan as owner; confirm reviewer-outreach email).
- [ ] Anthropic point of contact (if known) — likely blank.

**Listing copy (form page 1)**
- [ ] Server name (form rule: do NOT include "MCP" or "Server" in the name).
- [ ] Server URL — confirm which production URL is the submission target and whether it's a universal URL or per-user (form requires distinguishing; current implementation at `/mcp` is universal).
- [ ] Tagline — **≤55 characters including spaces**. Draft and count.
- [ ] Description — **50–100 words** covering what the server does + key capabilities.

**Capability classification (form page 1) — DECISIONS TO MAKE**

The form requires answers to all of the following. Each needs to be re-derived against the current code, not copied from any prior attempt:

- [ ] **Read/Write Capabilities** (Read Only / Write Only / Read+Write) — walk every tool in [mcp_tools.py](mcp_tools.py), classify each tool's effect on the *user's* data (not Synzo's internal metering), then pick the form option that matches. `redact_pii` and `detect_faces` return transformed copies of the input — decide whether that counts as "write" or just transformation.
- [ ] **Is this an "MCP App" (has interactive UI elements)?** (Yes / No) — current code in [mcp_routes.py](mcp_routes.py) does not implement `ui/open-link` or any interactive UI element. Confirm against the [MCP App specification](https://modelcontextprotocol.io/) before answering.
- [ ] **Third-party Connections and Web Access** (multi-select) — categorize against actual code paths:
  - Does any tool fetch from arbitrary URLs on the open web? (Check feature modules.)
  - Does any tool call Gemini? (Yes — `summarize_document`, `translate_document`, `analyze_image`. This is "third-party AI model integration.")
  - Does any tool call other third-party data services?
- [ ] **Data Handling checklist** — confirm each statement against current code before checking:
  - Server only accesses data explicitly requested by user — verify against the tool handlers.
  - No data is stored beyond session requirements — verify against [auth.py](auth.py)'s `_record_usage` (only metadata) and any file-handling code paths (S3 / temp dirs).
  - Data transmission is encrypted (HTTPS/TLS) — verify Railway edge + Gemini API call sites.
  - GDPR compliant (if applicable) — needs a real decision: do we accept EU users? If yes, the privacy policy must cover GDPR (lawful basis, data subject rights, retention) and we may need a DPA.
- [ ] **Personal health data?** (Yes / No) — decide whether Synzo is positioned to handle medical records / lab results / health metrics. The general-purpose document intelligence framing implies No, but confirm.
- [ ] **Category** (Business & Productivity / Communication / Data & Analytics / Development tools / Financial Services / Consumer Health / Health & Life Sciences / Media & Entertainment / Commerce & Shopping / Other) — pick one. Likely candidates given the toolset: Business & Productivity, Data & Analytics. Decide which best matches the listing copy.
- [ ] **Sponsored content / ads?** (No / banner ads / sponsored ranking) — verify against the listing implementation and product surface.

**Use cases (form page 1)**
- [ ] Draft **≥3 use cases**, each with an example user prompt that a reviewer can paste into Claude verbatim against the test account. Tool seeds, drawn from what's actually shipped in [mcp_tools.py](mcp_tools.py):
  - `summarize_document` — input file types and behavior per [mcp_tools.py](mcp_tools.py).
  - `translate_document` — supported source types and output shape per [mcp_tools.py](mcp_tools.py).
  - `redact_pii` — supported file types and output shape per [mcp_tools.py](mcp_tools.py).
  - `analyze_image` — supported image types and output shape per [mcp_tools.py](mcp_tools.py).
  - `detect_faces` — supported image types, modes, and output shape per [mcp_tools.py](mcp_tools.py).
  Re-read the tool descriptions before drafting the use cases so the prompts match actual behavior.
- [ ] Connection requirements field — derive from the actual sign-in flow shipped in [auth_routes.py](auth_routes.py) (WorkOS AuthKit; SSO providers configured per §6.5.B). Confirm what's truly required (e.g., no admin seat, no custom URL, no geographic restriction).

**Auth & test access (form page 2)**
- [ ] Authentication Type — derive from the live OAuth flow proven on 2026-06-06.
- [ ] Auth Client — **Dynamic** (locked 2026-06-07). §6.2 proved DCR works end-to-end via claude.ai; no static-client fallback in the reviewer bundle. Verify the form still offers Dynamic at submission time.
- [ ] Static Client ID / Secret — **leave blank** (Dynamic was chosen; see above and the Phase 3.5 reviewer-bundle locked decisions).
- [ ] Transport Support (Streamable HTTP / SSE) — verify against [mcp_routes.py](mcp_routes.py)'s response Content-Type and whether any SSE branch exists. As of the 2026-06-06 verification, the server returns `application/json` only; SSE is not implemented (planned for Phase 2.5.B).

**Reviewer test bundle (form page 2 — gates the review; if incomplete, review is blocked)**

This is the highest-risk Phase 3.5 item. The form explicitly says: "Incomplete or missing test credentials will block review of your server." Build the bundle fresh; do not assume any prior test account or sample data is still valid.

> **Locked decisions (2026-06-07):**
> - **Reviewer mailbox** — `paul@redmapleresearch.ca` (existing address Paul controls; updated 2026-06-07). Originally specced as `mcp-review@synzo.ai` via Cloudflare Email Routing, but `synzo.ai` DNS lives at a registrar (not Cloudflare) — setting up the alias requires either migrating synzo.ai's DNS to Cloudflare or configuring forwarding at the registrar, neither of which is reviewer-bundle-blocking. **Action item for after submission**: migrate `synzo.ai` to Cloudflare so `support@`, `privacy@`, `security@`, `mcp-review@` all become possible from one place; then swap the walkthrough's reviewer email back to `mcp-review@synzo.ai`. The Anthropic submission form's reviewer-contact field is separate and can still surface `mcp-review@anthropic.com` if asked.
> - **Plan tier** — **free (50 calls/month, 20 pages/call, 10 rpm)**. Reviewer sees the same plan a real signup gets — most honest demo of `redact_pii`-class behavior at submission. Quota risk: review window must stay under 50 total calls. Mitigation: walkthrough doc lists exactly one prompt per tool so a single end-to-end pass burns 5 calls.
> - **No static API-key fallback.** The form asks "Auth Type" + "Auth Client (Static vs Dynamic)"; shipping a key alongside OAuth muddies the answer and sidesteps the exact flow Anthropic is reviewing. OAuth via claude.ai was proven end-to-end on 2026-06-06 (see §6.2); if it breaks on the reviewer side we fix it and resubmit, not work around it.
> - **Bundle hosting** — `https://www.synzo.ai/reviewer-bundle.zip`, served from Flask static dir. Avoids Drive/external-vendor dependency in the review path; lives on our own domain.

- [ ] ~~Cloudflare: add `mcp-review@synzo.ai` alias~~ **Deferred** — synzo.ai DNS isn't on Cloudflare yet. Tracked as a separate post-submission item; not bundle-blocking. See Phase 3 Cross-cutting Cloudflare bullet for the broader DNS-migration follow-up.
- [ ] Sign up at `https://www.synzo.ai` as `paul@redmapleresearch.ca`. Confirm the org auto-provisions, free-tier plan attaches, and `/dashboard` renders cleanly. Capture the password for the `REVIEWER_PASSWORD` Railway env var.
- [ ] Verify the seeded org state in the WorkOS dashboard + Synzo `/dashboard/usage` page (calls_remaining=50, plan='free'). Cross-check against [scripts/seed_dev_org.py](scripts/seed_dev_org.py) if anything looks off.
- [x] **Walkthrough page deleted; credentials + sweep go inline in the submission form** (2026-06-07, commit pending). Earlier 2026-06-07 we built `/reviewer-walkthrough` with `noindex`/`no-store`/unlisted defenses, then deleted it the same day after re-reviewing the threat model: a publicly-reachable URL with the password rendered into the HTML response is security-by-obscurity, full stop. The page existed for one viewer on one day; inline-in-form has zero attack surface and no rotate-on-leak story to maintain. The partial template, the route, and the `REVIEWER_PASSWORD` env-var plumbing were all reverted. Reviewer-bundle download URL (the zip) stays public — the sample files are intentionally non-sensitive.

  **Paste this verbatim into the Anthropic submission form's reviewer-instructions field** (the form likely accepts markdown; if plain text only, strip the formatting):

  ````
  **Server URL:** https://www.synzo.ai/mcp
  **Transport:** Streamable HTTP (application/json). Protocol versions: 2025-06-18, 2025-03-26.
  **Auth:** OAuth 2.0 via WorkOS AuthKit. DCR per RFC 7591 (we host an augmented /.well-known/oauth-authorization-server that injects registration_endpoint — WorkOS supports DCR but doesn't advertise it).
  **Tools/Resources/Prompts:** 5 / 0 / 0. Live registry visible at https://www.synzo.ai/docs.

  **Test account** (free tier — 50 calls/month, 20 pages/call, 10 rpm):
  - Email: paul@redmapleresearch.ca
  - Password: <PASTE_AT_SUBMISSION_TIME>

  **Sample bundle:** https://www.synzo.ai/static/files/reviewer-bundle.zip (3.2 MB, 5 files; one per tool).

  **End-to-end sweep — one prompt per tool. Each burns ~1 call (full sweep = 5 of 50).**

  1. summarize_document → file: summarize-sample.pdf
     "Use Synzo to classify and summarize this document."
     Returns: { classification, summary, filename }. No source-text echo.

  2. translate_document → file: translate-sample.docx
     "Translate this document to Spanish using Synzo."
     Returns: { filename, target_language, translated_text }. Markdown output, no binary round-trip.

  3. redact_pii → file: redact-sample.docx (synthetic HR memo with seeded fake PII)
     "Redact the PII in this document using Synzo."
     Returns: { filename, content_base64, mimetype, original_size_bytes, redacted_size_bytes }.
     Presidio default English recognizers: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, US_SSN, CREDIT_CARD, US_PASSPORT, LOCATION, DATE_TIME, NRP, ORGANIZATION. All seeded entities are replaced with U+2588 block characters in place.

  4. analyze_image → file: analyze-sample.jpg
     "Analyze this image with Synzo."
     Returns: { filename, analysis: { description, rich_description, extracted_text, safety_flags, detected_objects }, dominant_colors }. Image is normalized + resized before the Gemini call.

  5. detect_faces → file: detect-faces-sample.jpg
     "Use Synzo to blur the faces in this image."
     Returns: { filename, mode, content_base64, mimetype } — PNG with faces blurred. Tool name describes the detect-and-obscure pipeline; response is the processed image, not bounding boxes.
     Cold-start note: first call on a fresh replica pays ~10–30s for MTCNN/TensorFlow graph load. Subsequent calls fast.

  **Error envelope (for reference):**
  - -32001 Auth (missing/expired/invalid bearer; orphan org; missing JWT claim)
  - -32002 Quota (monthly call cap exhausted)
  - -32003 Rate limit (per-org RPM cap surfaced in message)
  - -32004 Units exceeded (per-call cap, e.g. >20 pages on free tier)
  - -32005 Tool timeout (60s wall-clock; quota refunded, metered as 'timeout')
  Tool-internal failures (handler exception, downstream model error) come back as isError: true in the result envelope — not a JSON-RPC error — so Claude can recover. Quota is still refunded on the exception path.

  **Contact during review:** mcp-review@anthropic.com → forward to paul.ohagan@<address>. Security: security@synzo.ai (see https://www.synzo.ai/security).
  ````
- [x] **Sample file set built and locked, all five staged at `C:\Users\651802\Downloads\synzo-mcp-testing\`. Every file fits the free-tier `pages_per_call: 20` and `MAX_DOC_BYTES: 10 MB` caps.** (2026-06-07)

  | Tool | File | Size / dims | Source | Notes |
  |---|---|---|---|---|
  | `summarize_document` | `william-faulkner-the-tall-men.pdf` | 39 KB, 9 pages | external | In-copyright until 2037 (Faulkner d. 1962); acceptable risk for reviewer-only test bundle, not redistributed broadly. Demonstrates classification (literary text) + structured summary. |
  | `translate_document` | `Chapter V In Our Time.docx` | 14 KB, ~700 chars prose | external | Hemingway 1925; **US public domain since 2021** (pre-1929). Translates cleanly. |
  | `redact_pii` | `redact-sample.docx` | 36 KB | **generated by [scripts/build_redact_sample.py](scripts/build_redact_sample.py)** | Synthetic HR memo with seeded fake PII: John Doe, Jane Doe, `john.doe@example.com`, `(555) 123-4567`, SSN `211-61-2524` (structurally valid SSA range — `123-45-6789` is hard-rejected by Presidio as a known test value), passport `C12345678`, Visa `4111-1111-1111-1111` (universal Luhn-valid test card). Street address + driver's license intentionally omitted to avoid visible survivors (Presidio defaults don't catch street addresses or state DL numbers). |
  | `analyze_image` | `office-desk.jpg` | 2.9 MB, 4032×3024 | external | Renamed from `pohagan desk.jpg` to strip Paul's surname from the filename before public hosting. Rich scene for description + OCR + objects. |
  | `detect_faces` | `group-photo-caption.jpeg` | 324 KB, 1920×1280 | external | Two visible faces; proven against the live MTCNN pipeline on 2026-06-07. |

- [x] **`redact-sample.docx` verified end-to-end against the live `redact_pii` MCP tool via [scripts/verify_redact_sample.py](scripts/verify_redact_sample.py).** (2026-06-07) Every seeded PII string (name, email, phone, SSN, passport, credit card, location, dates, org names) is redacted to block characters in the output. The verify script posts to `https://www.synzo.ai/mcp` with `SYNZO_API_KEY`, downloads the redacted bytes, extracts the paragraph text, and asserts no seeded string survives. Re-run before bundling: `.venv/Scripts/python -m scripts.verify_redact_sample <path>`.

- [x] **Bundle zipped and staged at [static/files/reviewer-bundle.zip](static/files/reviewer-bundle.zip)** (2026-06-07, commit pending). 3.25 MB total. Files renamed inside the zip for reviewer-facing clarity: `summarize-sample.pdf`, `translate-sample.docx`, `redact-sample.docx`, `analyze-sample.jpg`, `detect-faces-sample.jpg` (the source `.jpeg` was renamed to `.jpg` for extension consistency — both are accepted by `detect_faces`). After deploy, served at `https://www.synzo.ai/static/files/reviewer-bundle.zip`; that URL goes into the Anthropic submission form's reviewer-bundle field.
- [ ] Dry-run the walkthrough end-to-end from a clean browser as the reviewer account: add the connector at `synzo.ai/mcp`, OAuth sign-in, fetch the bundle, run all 5 prompts, confirm each tool's output matches the walkthrough's "what to expect" text. Watch quota tick down: 50 → 45 after the full sweep.
- [ ] Check both "Test account includes sample data" and "All tools can be tested with provided data" form boxes only after the dry-run has been done end-to-end by someone other than the author. (If "someone other than the author" isn't available, dry-run from a fresh browser profile + different OS account as the closest substitute.)

**Server inventory (form page 3)**

The form requires the inventory in the exact format `tool_name (Human Readable Name)`.
- [ ] Tools — derive from the live registry in [mcp_tools.py](mcp_tools.py). The current 5 are `summarize_document`, `translate_document`, `redact_pii`, `analyze_image`, `detect_faces` (`transcribe_audio` formally out of scope per §6 footnote). Author a human-readable name for each.
- [ ] Tool Titles & Annotations — check both form boxes ("user-friendly titles" + "accurate tool annotations") only after re-confirming every tool has `title`, `readOnlyHint`, and `destructiveHint` set in [mcp_tools.py](mcp_tools.py) (verified 2026-06-06; re-verify at submission time).
- [ ] Resources — derive from current code. As of 2026-06-06 the server does not implement any MCP resources.
- [ ] Prompts — derive from current code. As of 2026-06-06 the server does not implement any MCP prompts.

**Docs & support (form page 1, bottom)**

> **Repo will be private at submission time** — all three links below must resolve on `www.synzo.ai`, not GitHub. The routes are built in Phase 3's "Docs" sub-section using the render-once-and-cache model (README is the single source of truth for `/docs`).
- [ ] Public documentation URL → `https://www.synzo.ai/docs`. Verify the route renders, the cache is populated, and content matches the live tool registry before checking the box.
- [ ] **Privacy Policy URL** → `https://www.synzo.ai/privacy`. Required field; missing this blocks submission. Verify the page covers data collection, retention, third-party processors, and contact for data requests.
- [ ] Data Processing Agreement URL — only fill if we have one. Default: leave blank.
- [ ] Support Channel → `https://www.synzo.ai/support` (or `mailto:support@synzo.ai` if the page just publishes the mailbox). Must be distinct from the docs URL. GitHub Issues is NOT an option because the repo is private.

**Branding & visuals (form page 4)**
- [ ] Square 1:1 logo, hosted publicly (Drive link OK). Form prefers SVG. Decide PNG vs commissioned SVG.
- [x] Site favicon at `www.synzo.ai` updated (commit `90218af`).
- [ ] Verify `https://www.google.com/s2/favicons?domain=synzo.ai&sz=64` after Google's 24–48h cache refresh. Check the box "I have verified that the favicon is correct" only after this confirms.
- [ ] 3–5 promotional screenshots of the server running inside claude.ai. Form requires ≥1000px wide, PNG, cropped to the response itself, each paired with the matching prompt. Demo video optional.
- [ ] Optional: Google Drive folder linking promo assets + matching prompts.

**Skills & Plugins (form page 5)**
- [ ] Skill submission — decide whether to ship an accompanying SKILL.md. Optional; leave blank if not.
- [ ] Related Plugin — N/A unless we also submit a Claude Code plugin.

**Launch readiness (form page 4)**
- [ ] Confirm testing in **Claude.ai (web)** — proven 2026-06-06 (OAuth path via claude.ai per §6.2). Check this box only if still true at submission time.
- [ ] **Claude Desktop** — not validated as of 2026-06-06 (work account's "connectors disabled" org policy blocked it; Inspector v0.22.0's OAuth panel can't drive DCR either). Form says Desktop is not required, so do NOT check this box unless validated against a non-blocked account before submission.
- [ ] **Claude Code / Cowork** — form says not required. Decide whether to validate or leave unchecked.
- [ ] Server GA Date — Synzo is GA on `www.synzo.ai` as of Phase 1.5 deploy. Confirm GA status at submission time and answer accordingly.

**Compliance & submission (form page 6)**
- [ ] **Pre-submission self-check against the [pre-submission checklist](https://docs.claude.com/connectors/building/submission/pre-submission-checklist)** — walk every item. Most are Phase 3 audits; this is the final read-through.
- [ ] Review and accept the [Anthropic Software Directory Terms](https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms). Key clauses being accepted (verify each against current state before signing):
  - Warranty: we own/control all API endpoints (Gemini called as legitimate proxy — see Phase 3 framing).
  - Indemnification of Anthropic for claims related to Synzo or user interactions with it.
  - Anthropic may review, test, and remove the connector at any time.
  - Anthropic gets a license to display Synzo's name/logo/screenshots in the directory.
  - We agree to maintain compliance with the Software Directory Policy as it updates.
- [ ] Review and confirm compliance with the [Anthropic Software Directory Policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy). Cross-reference against the Phase 3 policy-audit checklist — by Phase 3.5 every item should be ticked.
- [ ] Confirm Synzo is NOT on the §4 unsupported-use-cases list. Re-verify against current code, not against the plan's prior framing:
  - Does not transfer money/crypto.
  - Does not generate images/video/audio via AI (verify analyze_image still only *describes* and detect_faces still only *blurs*).
  - Does not serve ads or sponsored content.
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
- ~~**transcribe_audio.**~~ Resolved 2026-06-05: dropped from submission scope. Stub stays in the repo; tool not registered. Revisit if a customer asks.
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

**New in Phase 3 (public-facing docs — modeled on Harvey's MCP submission):**
- `templates/docs.html` — hand-authored Jinja page with five sections (Hero / What is Synzo MCP / Setup guides / Available tools / Troubleshooting + FAQ). The Available tools section is the only dynamically rendered piece.
- `templates/privacy.html` — static, GDPR-compliant privacy policy with the 12-section skeleton in Phase 3 Docs. ~2000-3000 words; scope tightly to Synzo's actual data flows.
- `templates/support.html` — static support page with mailbox, response SLA, what-to-include-in-a-report, security disclosure cross-link.
- `docs/tool_examples.yaml` (new) — one example prompt per tool, keyed by tool name. The sidecar that joins against [mcp_tools.py](mcp_tools.py)'s live registry to build the tools table.
- New module (likely `docs_renderer.py`) — at `create_app()` time, walks [mcp_tools.py](mcp_tools.py)'s `TOOLS` and joins against `docs/tool_examples.yaml`, builds the HTML table once, caches as module-level string. Raises at startup if a registered tool has no example in the sidecar (this is the guardrail against silent doc drift).
- New route handlers for `/docs`, `/privacy`, `/support`, `/security` (extend [main_routes.py](main_routes.py) or new `docs_routes.py` blueprint).
- Edits to `templates/layout.html` — global footer with Docs / Privacy / Support links (Terms deferred).
- Edits to [requirements.txt](requirements.txt) — pin `pyyaml`. (`markdown`/`pygments` no longer needed; the docs page is hand-authored Jinja, not rendered Markdown.)
- `SECURITY.md` — MCP-server-scoped security disclosures + `security@synzo.ai` vulnerability-reporting mailbox.
- `tests/test_docs_page.py` (new) — asserts `GET /docs` 200s, contains every tool name from the live registry, contains the five section headings, and does NOT contain dev-only language. Plus a startup-failure test: missing example in `tool_examples.yaml` → `create_app()` raises with a clear message.
- Cloudflare Email Routing rules — three new aliases: `support@synzo.ai`, `privacy@synzo.ai`, `security@synzo.ai` → Paul's real inbox. No new infra; one config edit in Cloudflare.

---

## 10. When picking this up later

1. Re-read this file end-to-end — the top-of-file status line tells you where we left off.
2. Check the Anthropic MCP spec page for any updates since the last edit date — auth and transport specs evolve.
3. Confirm `PLANS` numbers still make sense given current Gemini pricing.
4. **State as of 2026-06-06 (11 Phase 3 commits in):** Phase 0, 1, 1.5, 2, 2.5.A are done and live. **Gate (d) is fully closed** — API-key auth path proven via [scripts/sweep_tools.py](scripts/sweep_tools.py) on 2026-06-05 (5/5 tools SUCCESS), OAuth path proven via claude.ai on 2026-06-06. Three OAuth fixes shipped on 2026-06-06 (commits `42de97e` + `49915d0`, plus WorkOS dashboard config change) — see §6.2 for the detailed lessons; if reproducing OAuth setup elsewhere, run the four curl checks in §6.2 in order before touching code. `transcribe_audio` dropped from scope; the 5 shipped tools are the submission set. **Phase 3 progress on 2026-06-06 (11 commits, 140/140 tests, was 107 at start of review pass):** all five public pages — `/docs`, `/privacy`, `/terms`, `/support`, `/security` — built, styled to match the app design system (`.feature-container` + `.feature-grid` + `.message-item.category-info` reused; see [docs_routes.py](docs_routes.py), [templates/partials/](templates/partials/), and the `.legal-section`/`.page-hero` helpers in [static/css/style.css](static/css/style.css)); tools-table renderer + YAML sidecar + startup-fail guardrail wired in [docs_renderer.py](docs_renderer.py); `/about` Legal Notice promoted to canonical `/terms`; global footer in [layout.html](templates/layout.html); privacy policy code-reviewed and four inaccuracies corrected (commit `16a4b30`); six policy-compliance audits (all PASS, recorded inline in §6 Phase 3); per-org RPM cap now named in the `-32003` message ([auth.py:404](auth.py#L404), commit `3a33950`); OAuth-path test gap closed (commit `6f48ab4`: 12 resolver tests + 3 OAuth-through-`/mcp` tests pinning the path Anthropic's reviewer hits via claude.ai); all 9 remaining test-suite gaps from the same-day adversarial review closed (commit `f63f00a`: `/api/v1/summarize` e2e, HTTP-path 504, `_resolve_api_key` raise sites, body-size caps at JSON-RPC layer, discovery CORS + URL fallback, JSON-RPC `id` echo on errors, generic-Exception → `isError+refund`, 405+Allow on GET/DELETE, Policy 5.A split). Commit chain: `99d483d` → `ffdb73d` → `abb1faa` → `16a4b30` → `2647ac9` → `c844753` → `796bacc` → `3a33950` → `6f48ab4` → `f63f00a`. **Phase 3 remaining (in roughly suggested order):** (a) **technical hardening** — author `SECURITY.md` for the repo (the `/security` web route already exists; this is the in-repo Markdown for contributors); add file-type detection via magic bytes (currently extension-based at four sites named in Phase 3 technical-hardening section); wrap Gemini calls with tenacity for transient-5xx retry. (b) **Cloudflare Email Routing** — set up `support@`, `privacy@`, `security@` aliases pointing at Paul's real inbox (the pages already reference these addresses; until configured, mailto links open but emails bounce). (c) **README audit + pre-submission /docs read** — confirm README is a superset of `/docs` and every tool name/description/example prompt on `/docs` is still accurate. (d) **MCP Inspector live validation** + integration tests per remaining tool (translate / redact_pii / analyze_image / detect_faces at the JSON-RPC layer with mocked downstreams; summarize_document is already covered). (e) **API-ownership framing for Gemini** (§7 open question). (f) operationally validate Phase 2.5.A by running [scripts/concurrency_load_test.py](scripts/concurrency_load_test.py) against live with `--concurrency 32` before any public-launch traffic (consumes 32 quota slots per run). (g) revoke any API keys exposed during testing. **Phase 3.5 (submission package)** can run in parallel with the technical hardening — structured to mirror the submission form's six pages. **Every form answer is open and must be re-derived against the current code at submission time** — no answers from prior unrelated form attempts are assumed valid. Phase 3.5 also includes a concrete reviewer-test-bundle spec (one sample file per tool, walkthrough doc, dedicated WorkOS test account).
5. WorkOS staging credentials + `WORKOS_ISSUER` live in local `.env` (never committed) and in Railway service vars. Confirm they still work before relying on them.
6. The auth/quota/metering pipeline ([auth.py](auth.py), [auth_routes.py](auth_routes.py)) and the tenant-isolation test suite ([tests/test_multi_tenant_isolation.py](tests/test_multi_tenant_isolation.py)) are the foundation Phase 2's MCP tools sit on top of. Every MCP tool handler must (a) use `@require_auth` (b) read `Principal.org_id` from `g.principal` and scope DB reads/writes on it, and (c) get parallel cross-tenant isolation tests.
7. The audit prompt from the original conversation can be re-run any time against the repo to track progress against Anthropic's requirements matrix.
