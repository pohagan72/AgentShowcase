# Synzo → Anthropic MCP Connector Directory: Submission Plan

> **Status as of 2026-06-04:** Phase 0 complete. Phase 1 code complete (signup/login UI still TODO). Baseline schema (`orgs`, `api_keys`, `quotas`, `usage_events`) is live on Railway Postgres at Alembic revision `0001_baseline`. SQLAlchemy + Alembic wired into the Flask app via `db/` and `migrations/`. `auth.py` ships `Principal` + `require_auth` decorator + WorkOS JWT verification (pyjwt + PyJWKClient) + API key resolution (sha256 + `hmac.compare_digest` + `secrets.token_urlsafe(32)`) + atomic quota decrement. `pyjwt[crypto]` and `workos` added to requirements.txt. **POC endpoint `/api/v1/summarize` verified end-to-end against Railway Postgres: real API key → quota decrement 50→49 → `usage_events` row inserted with `status=ok`, `tool=summarize_document`, `units=15`.** Failure-path test suite landed: 402 / 413 / 429 / refund-on-exception all covered in [tests/test_auth_failures.py](tests/test_auth_failures.py); 21/21 tests pass. Two bugs surfaced and fixed while writing the suite — `BigInteger` PK didn't autoincrement under SQLite (test backend), and `_decrement_quota`/`_refund_quota` keyed on exact `period_start =` equality which is brittle on tz round-trip; rewrote both as range matches (`period_start <= now < period_end`). OAuth path still wired but unverified — `WORKOS_ISSUER` deferred until AuthKit sign-in produces a real token (Phase 1 signup/login step). Next: WorkOS signup/login + minimal dashboard.
> **Owner:** Paul O'Hagan
> **Goal:** Ship Synzo as an approved connector in Anthropic's MCP Connector Directory, while building the foundation for a paid metered-API business on the same backend.

---

## 1. Where we are

Synzo is currently a Flask + HTMX web app deployed on Railway. It exposes document intelligence features (summarization, translation, PII redaction, multimedia analysis, transcription) through an HTML UI. Backed by Google Gemini, Microsoft Presidio, S3-compatible storage.

**The repo as it stands today will be rejected by Anthropic immediately.** Not because the app is bad — because it is not an MCP server at all. There is no MCP protocol surface, no OAuth, no tool registry, no schemas.

The good news: the existing Flask code is reasonable groundwork. It becomes the *backing implementation* that an MCP layer calls into.

### Audit summary (what's missing)

| Category | Status |
|---|---|
| MCP server / protocol handlers | MISSING |
| Tool registry, schemas, annotations | MISSING |
| Streamable HTTP / SSE transport | MISSING |
| OAuth 2.0 (discovery, PKCE, DCR, bearer validation) | MISSING |
| CORS for `claude.ai` | MISSING |
| MCP Inspector validation | MISSING |
| Tests (any kind) | MISSING |
| Security headers, rate limiting, CSRF | IMPLEMENTED (Flask side) |
| Logging | IMPLEMENTED |
| HTTPS / TLS | Handled by Railway edge |

Full audit lives in the conversation that produced this doc. Re-run the audit prompt against the repo any time to refresh.

---

## 2. The two goals, and why they share an architecture

We are building **one backend that serves two authentication paths**:

1. **MCP path** — Claude Desktop / claude.ai connects via OAuth 2.0, bearer JWTs. This is what Anthropic's audit cares about.
2. **Paid API path** — Developers buy quota, get an API key (`sk_synzo_...`), call the same endpoints from their own code.

Both resolve to the same `Principal` (org_id + plan). All downstream logic — quotas, rate limits, metering, audit logs — is shared. The MCP submission and the side business reuse one codebase, one DB, one decorator.

---

## 3. Architecture (decided)

```
                    Claude Desktop / claude.ai
                              │ OAuth bearer JWT (WorkOS-issued)
                              ▼
  curl / customer code  ──▶  Flask: @require_auth
  sk_synzo_abc123              ├─ identify caller (OAuth or API key)
                               ├─ check rate limit (Redis)
                               ├─ atomic quota decrement (Postgres)
                               ├─ run handler → Gemini / Presidio
                               └─ insert usage_event (Postgres)
                              ▼
                       Postgres + Redis on Railway
```

### Identity stack: **WorkOS AuthKit**

Decision rationale:
- Free up to 1M MAU (we will never approach this)
- DCR + auth-server metadata + (mostly) protected-resource metadata out of the box
- Purpose-built for MCP / AI-agent auth flows
- Zero infra to operate vs. self-hosted Keycloak (~$10–20/mo + day of setup + ongoing ops)

We rejected:
- **Keycloak on Railway** — works technically, but $10–20/mo and a day of yak-shaving for no narrative benefit on a portfolio submission
- **Stytch Connected Apps** — viable alternative if WorkOS doesn't work out
- **Auth0** — DCR available but more config; no advantage over WorkOS at our scale
- **Self-rolled OAuth** — never. Don't write your own OAuth server.

### Persistence

**Postgres on Railway** (~$5/mo). Flask app is currently stateless; we add Postgres in the same Railway project.

Why a real database and not alternatives:

| Option | Verdict | Reason |
|---|---|---|
| **Postgres on Railway** | **Chosen** | Same dashboard as the app, sub-ms query latency on the hot path (atomic quota decrement runs on every MCP call), ACID transactions handle concurrent decrements correctly, mature Python ecosystem (SQLAlchemy/Alembic), every Railway tutorial uses this shape |
| **SQLite on a Railway volume** | Rejected | Single-writer file lock breaks the moment we scale to 2 replicas; backups become our problem; we'd migrate to Postgres within months anyway. Not safe for billing data. |
| **Neon / Supabase (managed Postgres elsewhere)** | Fallback if $5/mo matters | Same Postgres semantics, generous free tiers, but adds 10–30ms network hop on every query and a second vendor dashboard. Neon's branching is genuinely nice for test environments. |
| **Turso / LibSQL** | Rejected for v1 | Newer, smaller ecosystem; not worth being early adopter when boring Postgres works |
| **Redis only (no SQL)** | Rejected | Redis is for ephemeral counters, not durable queryable billing history. Complement, not replacement. |
| **JSON file / in-memory dict** | Hard no | Lose the file → lose all billing records |

The three things that force a real DB:
1. **Atomic quota decrement** — concurrent calls cannot both pass when 1 unit remains. Needs transactions.
2. **Durability** — `quotas` is money; `usage_events` is the billing source of truth. Loss is unacceptable.
3. **Queryability** — "show this customer their usage this month" is a `WHERE org_id = ? AND created_at > ?` query.

**Redis on Railway** (~$5/mo) — **deferred**. Needed only when we scale past a single Railway replica (Flask-Limiter and the rate-limit counter both want cross-replica state). Single-replica MVP works with in-memory. Add Redis the week we turn on horizontal scaling. JWKS for WorkOS token verification cache in process memory in the meantime (rebuilt on restart, fine).

### Schema (five tables)

```sql
orgs           -- one row per customer (human signup or paying org)
api_keys       -- hashed sk_synzo_... keys, revocable, one org → many keys
quotas         -- current period's remaining calls/pages, decremented atomically
usage_events   -- append-only audit log + billing source of truth
-- (one more later: stripe_customers / subscriptions when billing lands)
```

`usage_events` is the most important table. It is simultaneously:
- Audit log (privacy review evidence)
- Analytics feed
- Billing source of truth
- Abuse detection input

Never delete from it.

---

## 4. Abuse defense (the layered model)

The threats that actually matter, ranked by expected cost:

1. **Gemini bill blowup** — someone scripts a free endpoint to burn quota
2. **Bot signups farming free tier** — appears once a free tier exists
3. **DoS via large uploads** — 500MB PDF, zip bomb, malformed PPTX
4. **Credential stuffing** — relatively low impact for our shape

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

## 5. The middleware (sketch — to be implemented)

One decorator, used by both Flask routes and MCP tool handlers. The full sketch is in the conversation; the key shape is:

```python
@require_auth(tool_name="summarize_document",
              units_fn=lambda req: estimate_pages(req.files["doc"]))
def handler(...):
    ...
```

The decorator handles, in order:
1. Identify caller (OAuth JWT or API key, distinguished by `sk_synzo_` prefix)
2. Reject if unit count exceeds plan's per-call cap → 413
3. Per-org-per-minute rate limit → 429
4. Atomic quota decrement in SQL → 402 if exhausted
5. Run handler
6. On error: refund quota
7. Always: insert into `usage_events`

Plans defined as a single dict (single source of truth):

```python
PLANS = {
    "free":    {"calls_per_month": 50,     "pages_per_call": 20,  "rpm": 10},
    "starter": {"calls_per_month": 10_000, "pages_per_call": 100, "rpm": 60},
    "pro":     {"calls_per_month": 100_000,"pages_per_call": 500, "rpm": 300},
}
```

Full sketch lives in the conversation under "The middleware" — recover it and drop it into `auth.py` when starting implementation.

---

## 6. Roadmap

### Phase 0 — Pre-work (do before any code) [~1 hour]
- [x] **Gemini spend protection** — soft cap (budget alert) configured in Google Cloud Console. Acceptable for portfolio stage; revisit and convert to hard cap before the MCP server is live to public traffic.
- [x] **WorkOS staging credentials captured** — AuthKit account created, default application named (auto-generated), JWKS endpoint verified to return valid RS256 keys. Values stored in local `.env` as `WORKOS_CLIENT_ID`, `WORKOS_API_KEY`, `WORKOS_JWKS_URL`. Production environment credentials still to be captured at submission time.
- [x] **Postgres provisioned on Railway** — service is `Online` in the same project as `AgentShowcase` (Flask app). Convention: code reads a single env var `DATABASE_URL` everywhere; the value differs per environment:
  - **Local `.env`:** `DATABASE_URL` = public proxy (`acela.proxy.rlwy.net:54776`) — laptop can reach it
  - **Railway Flask service variables:** `DATABASE_URL` = internal hostname (`postgres.railway.internal:5432`) — no egress cost, only resolves inside Railway's network
  - `DATABASE_INTERNAL_URL` is also captured in local `.env` as a reference value, not for code to read
- [x] **Railway Flask service variables staged.** On the `AgentShowcase` service: `DATABASE_URL` set to the internal Postgres hostname; `WORKOS_CLIENT_ID`, `WORKOS_API_KEY`, `WORKOS_JWKS_URL` added with values matching local `.env`. **Changes are staged, not yet deployed** — deliberately holding the Deploy until Phase 1 code lands that actually reads these vars, so we ship one bundled change instead of an empty restart. If Railway later asks "Apply 3 changes," it's fine to deploy whenever; just no value to doing it before there's code.
- [x] **Redis deferred.** Use in-memory rate limiting until we run >1 Railway replica. Revisit when horizontal scaling becomes necessary.

### Phase 1 — Foundation: auth + quota + metering on the existing Flask app [~1 week]
- [x] Add four tables (`orgs`, `api_keys`, `quotas`, `usage_events`) + Alembic migrations setup. Schema lives in [db/models.py](db/models.py); baseline migration [migrations/versions/0001_baseline_orgs_apikeys_quotas_usage.py](migrations/versions/0001_baseline_orgs_apikeys_quotas_usage.py) applied to Railway Postgres. Fifth table (`stripe_customers` / `subscriptions`) deferred to Phase 4.
- [x] Build `auth.py` with the `Principal` dataclass and `require_auth` decorator. Lives in [auth.py](auth.py). JSON-only error responses (402/413/429/401). `PLANS` dict is the single source of truth for tier limits.
- [x] Wire WorkOS JWT verification (`_resolve_oauth`) — JWKS caching via `PyJWKClient` (1h lifespan), `audience`/`issuer` pinned via env vars, requires `exp`/`iat`/`sub`. **Runtime-deferred:** `WORKOS_ISSUER` env var not yet set; OAuth path will return 500 until captured from a real AuthKit token during the signup/login implementation below.
- [x] Wire API key resolution (`_resolve_api_key`) — sha256 lookup, `hmac.compare_digest` belt-and-braces check, sentinel compare on miss to flatten timing curve, `revoked_at` honored. Issuance helper `issue_api_key()` uses `secrets.token_urlsafe(32)` → 256 bits of entropy.
- [x] Implement atomic SQL quota decrement (single `UPDATE ... RETURNING` against `calls_remaining > 0` to avoid races). Refund-on-error path also implemented.
- [x] Apply `@require_auth` to a POC endpoint. New JSON blueprint [api_routes.py](api_routes.py) registered at `/api/v1/*` (CSRF-exempt, JSON-only errors). `POST /api/v1/summarize` wraps the existing analyst agent. Verified end-to-end against Railway Postgres on 2026-06-04: real `sk_synzo_` key → atomic quota decrement (50→49) → `usage_events` row inserted (`status=ok`, `units=15`). Seed helper at [scripts/seed_dev_org.py](scripts/seed_dev_org.py) creates a free-tier `dev` org + current-period quota + issues a key; idempotent. Also fixed two latent bugs surfaced by exercising the path: `UsageEvent.org` back-relationship missing from [db/models.py](db/models.py); `_resolve_oauth` raising `jwt.DecodeError` on non-JWT bearer instead of returning 401.
- [x] Add `auth.py` tests: 402 exhausted quota, 413 oversized, 429 rate-limited, refund-on-handler-exception. All in [tests/test_auth_failures.py](tests/test_auth_failures.py); driven through a `/_test/auth_probe` route registered on the test app so the decorator is exercised without the Gemini pipeline. Per-test `seeded_org` fixture in [tests/conftest.py](tests/conftest.py) creates a fresh org + quota + raw key. Each test also verifies the metered side-effect (`usage_events.status` + `error_code`). Two bugs found and fixed during this work: `BigInteger` PK on SQLite (test backend) — added `BigInteger().with_variant(Integer(), "sqlite")` shim in [db/models.py](db/models.py) (no-op on Postgres); `_decrement_quota` / `_refund_quota` keyed on exact `period_start =` equality, which is brittle on tz round-trip — rewrote both as range matches in [auth.py](auth.py). 21/21 tests pass.
- [ ] Add WorkOS signup/login flow + basic dashboard (org settings, API key issue/revoke). Capture `WORKOS_ISSUER` from the first real AuthKit token here.

### Phase 2 — MCP server [~1 week]
- [ ] Add `mcp` (Python SDK) or `fastmcp` dependency
- [ ] Stand up MCP server with Streamable HTTP transport, mounted on the same Flask app (or sidecar)
- [ ] Define tools (each with JSON Schema input, title, `readOnlyHint`, `destructiveHint`):
  - `summarize_document` (write — produces new content)
  - `translate_document`
  - `redact_pii`
  - `analyze_image`
  - `detect_faces`
  - `transcribe_audio`
- [ ] Each tool calls into the existing Flask feature code via internal function calls (not HTTP)
- [ ] Apply `@require_auth` to every tool handler
- [ ] Expose discovery endpoints — `/.well-known/oauth-protected-resource` on the MCP server pointing at WorkOS
- [ ] Add CORS allowing `https://claude.ai` and Anthropic-documented origins

### Phase 3 — Submission readiness [~3 days]
- [ ] Validate with MCP Inspector locally + against the deployed Railway URL
- [ ] Write integration tests (pytest) for each MCP tool with mocked Gemini
- [ ] Write OAuth flow tests (mock WorkOS)
- [ ] Replace one-line `README.md` with proper API docs (tool list, schemas, examples)
- [ ] Author `SECURITY.md` scoped to the MCP server (existing `SAST_REPORT.md` is for the Flask app)
- [ ] Audit `logging.info` call sites — confirm no document/prompt bodies are logged
- [ ] Add file-type detection via magic bytes (currently extension-based — see [project-summary.md:154-156](project-summary.md#L154-L156))
- [ ] Wrap Gemini calls with tenacity (retry + circuit breaker)
- [ ] Prepare reviewer test credentials + sample documents

### Phase 3.5 — Submission package (Anthropic Directory form deliverables) [~1–2 days]

These are the non-code deliverables Anthropic's submission form requires. None block engineering work — pull them together in parallel with Phase 3. Single MCP server, single Synzo brand throughout.

**Identity & contact**
- [ ] Primary contact: name, email, role (Paul O'Hagan as owner per top of doc — confirm reviewer-outreach email)
- [ ] Company info / submitting entity

**Listing copy**
- [ ] Server name: `Synzo`
- [ ] Server URL (production Railway URL of the MCP endpoint)
- [ ] Tagline — **≤55 characters**. Distillation of the description.
- [ ] Description — **50–100 words** covering what Synzo does + key capabilities (summarization, translation, PII redaction, image/face analysis, transcription)
- [ ] Capability classification: read/write, third-party data handling, category — fill in form checkboxes

**Use cases**
- [ ] Draft **≥3 use cases**, each with an example user prompt that exercises one or more tools. Suggested seeds:
  - Summarize a long contract / produce a deck from it (`summarize_document` → PPT)
  - Translate a foreign-language document while preserving structure (`translate_document`)
  - Redact PII from a batch of documents before sharing (`redact_pii`)
  - Transcribe a meeting recording and summarize action items (`transcribe_audio` + `summarize_document`)

**Server inventory (declared on the form)**
- [ ] **Tools** — comma-separated list with human-readable names. Current set: Summarize Document, Translate Document, Redact PII, Analyze Image, Detect Faces, Transcribe Audio. Reconcile with whatever ships in Phase 2.
- [ ] **Resources** — declare explicitly, even if "None" for v1
- [ ] **Prompts** — declare explicitly, even if "None" for v1

**Auth & test access**
- [ ] Authentication summary: OAuth 2.0 via WorkOS AuthKit (PKCE + DCR), JWT bearer
- [ ] Test account credentials + step-by-step connection instructions for the reviewer. **Incomplete creds block review** — include sample docs they can run each tool against.

**Docs & support**
- [ ] Public documentation URL (the proper README from Phase 3, hosted somewhere reviewers can reach)
- [ ] Recommended support channel — email address or issue tracker URL distinct from docs

**Branding & visuals**
- [ ] Square **1:1 logo** for Synzo, hosted at a public URL (Google Drive link acceptable). Form prefers SVG; we currently have [static/images/synzo-icon.png](static/images/synzo-icon.png) (purple gradient shield). **Decide:** submit the PNG as-is, or commission/export an SVG version before submitting.
- [x] Site favicon at `www.synzo.ai` updated to the Synzo icon (commit `90218af`). [layout.html](templates/layout.html) now serves `synzo-icon.png`; `favicon.ico` replaced to match.
- [ ] Verify `https://www.google.com/s2/favicons?domain=synzo.ai&sz=64` returns the new purple shield once Google's cache refreshes (24–48h after Railway deploy).
- [ ] **3–5 promotional screenshots** of Synzo running inside claude.ai (each tool exercised at least once is ideal). Short demo video optional.
- [ ] Optional: Google Drive folder linking promo assets + matching prompts used to generate the screenshots

**Compliance & submission**
- [ ] Review and confirm compliance with Anthropic's MCP integration guidelines
- [ ] Review and accept the MCP Directory Terms
- [ ] Launch readiness / GA confirmation on the form
- [ ] Optional: package any Agent Skills that complement the connector ([Skills & Plugins](https://docs.claude.com/) — TBD if we want to ship one alongside)
- [ ] **Submit to Connector Directory**

### Phase 4 — Paid API (deferred until a real customer asks) [~1 week]
- [ ] Stripe Checkout integration for plan upgrades
- [ ] Stripe webhook → updates `orgs.plan` + provisions `quotas` row
- [ ] Customer dashboard: usage charts read from `usage_events`
- [ ] Per-key (not just per-org) rate limits — trivial code change
- [ ] Nightly aggregation job: `usage_events` → Stripe usage records (for metered billing)
- [ ] Anomaly cron: alert when any org spikes 10x baseline

---

## 7. Open questions (decide before/during implementation)

- **API ownership for Gemini.** Anthropic prefers connectors whose primary API is owned by the submitter. Synzo wraps Gemini. Mitigation: position the submission as "Synzo's document-intelligence API (Gemini-powered)" rather than "a Gemini connector." May or may not satisfy review — be prepared to discuss.
- **MCP server deployment shape.** Mount on the existing Flask app (same Railway service) or separate service? Same-service is simpler for v1.
- **Async processing.** Current Flask app processes synchronously. For MCP tools that take >30s (large PDFs), we may need Celery/Redis before submission, or document timeout behavior. Already on the roadmap in [project-summary.md:148-152](project-summary.md#L148-L152).
- **Free tier sizing.** `PLANS["free"]` numbers above are placeholders. Tune from real Gemini costs once we have any.
- **Tool granularity.** Should `summarize_document` and `summarize_document_to_pptx` be one tool with a `format` param, or two? Leaning two for clearer annotations and easier audit.

---

## 8. Reference: design rationale we don't want to re-litigate

- **Two auth paths, one ledger.** Don't ever split into "MCP backend" and "API backend." Same Flask app, same Postgres, same decorator.
- **Two URL surfaces, one Flask app.** Public HTML/HTMX routes (`/`, `/summarizer`, `/process/*`, etc.) stay unauthenticated and CSRF-protected — that's the portfolio site. The `/api/v1/*` JSON blueprint is `@require_auth`-protected and CSRF-exempt — that's for MCP tool handlers (Phase 2) and paid API customers. **Never put `@require_auth` on an HTMX endpoint:** it returns JSON 401, which the browser UI can't render, and instantly breaks the public site. New tool capabilities get wired into *both* surfaces (HTMX for visitors, `/api/v1/*` for API/MCP), sharing the same backing module under `features/`. Reason: the MCP and paid-API work must not disturb the live site at synzo.ai.
- **API keys are `sk_synzo_` prefixed, sha256-hashed at rest.** Revocable via `revoked_at`, never deleted. Display the first 16 chars to customers.
- **402 Payment Required for quota exhaustion** — semantically correct and parses cleanly in customer code.
- **Refund quota on handler error.** Customers don't pay for our bugs.
- **Never log prompt/document contents.** `org_id`, `tool`, `units`, `status`, `cost_cents` only.
- **Plans dict is one source of truth.** Adding a tier is one line.
- **WorkOS over Keycloak** for v1. Revisit only if data sovereignty becomes a sales objection.
- **One env var name, environment-specific values.** Code reads `DATABASE_URL` everywhere — local `.env` sets it to the public proxy, Railway service variables set it to the internal hostname. Same code path, no `if env == "prod"` branching. Same pattern applies if other infra ever gains a public/private hostname split.

---

## 9. File pointers (existing repo)

- [app.py](app.py) — Flask factory, Talisman, CSRF, rate limiter, blueprint registration
- [config.py](config.py) — env-driven config
- [extensions.py](extensions.py) — shared `limiter`
- [requirements.txt](requirements.txt) — current deps (no `mcp`, no `workos`, no `jwt` yet)
- [features/](features/) — six feature blueprints; their `routes.py` files contain the Gemini/Presidio logic the MCP tools will call into
- [s3_adapter.py](s3_adapter.py) — ephemeral file storage
- [SAST_REPORT.md](SAST_REPORT.md) — existing security report (Flask scope only)
- [project-summary.md](project-summary.md) — broader product context

---

## 10. When picking this up later

1. Re-read this file end-to-end — the top-of-file status line tells you where we left off.
2. Check the Anthropic MCP spec page for any updates since the last edit date — auth and transport specs evolve.
3. Confirm `PLANS` numbers still make sense given current Gemini pricing.
4. Resume at the first unchecked item in the roadmap. As of 2026-06-04 the Phase 1 code is done (schema, `auth.py`, POC endpoint, failure-path test suite); the only Phase 1 item left is WorkOS signup/login + a minimal dashboard, which also captures `WORKOS_ISSUER`. After that, on to Phase 2 (MCP server).
5. WorkOS staging credentials live in local `.env` (never committed). Confirm they still work before relying on them — if the application was deleted or rotated, recapture from the WorkOS dashboard.
6. The audit prompt from the original conversation can be re-run any time against the repo to track progress against Anthropic's requirements matrix.
