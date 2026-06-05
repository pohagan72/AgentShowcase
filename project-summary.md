# Synzo — Project Summary

> Living document. The authoritative roadmap is [MCP_SUBMISSION_PLAN.md](MCP_SUBMISSION_PLAN.md); the API contract lives in [README.md](README.md). This file is the one-page overview a new collaborator (or future-you) reads first to understand what Synzo is, why it exists in this shape, and where it stands today.

## What it is

Synzo is a multi-tenant document-intelligence platform built around five capabilities:

- **summarize_document** — classify and summarize PDF/DOCX/PPTX/XLSX
- **translate_document** — translate DOCX/PPTX/XLSX text into a target language
- **redact_pii** — Presidio-backed in-place PII redaction of DOCX/PPTX
- **analyze_image** — Gemini vision description, OCR, safety flags, dominant colors
- **detect_faces** — MTCNN face detection with blur or opaque-rectangle obscuring

(`transcribe_audio` is on the roadmap but not built — see [the plan](MCP_SUBMISSION_PLAN.md) §6.)

These run on a single Flask backend exposing **three URL surfaces**: a public HTMX portfolio site, a metered JSON API (`/api/v1/*`), and an MCP server (`/mcp`). All three share the same auth, quota, rate-limit, and metering pipeline. A fourth surface — the dashboard at `/dashboard/*` — uses cookie sessions so humans can manage their org.

## Why it exists in this shape

Synzo started as a portfolio app. It's now turning into something with two real goals:

1. **Ship as an approved connector in Anthropic's MCP Connector Directory.** Claude Desktop and claude.ai users will be able to add Synzo as an MCP server, authenticate over OAuth, and call the tools from any conversation.
2. **Build the foundation for a paid metered-API business** on the same backend. Same database, same decorator, same `Principal(org_id, plan)` abstraction — the MCP path and the paid-API path share their entire pipeline. The dashboard is the third path so paying customers can manage their own keys and members.

These two goals share the same backend by design. The MCP submission isn't a one-off; it's the first revenue-touching surface to land on infrastructure that's already org-scoped, quota-decremented, and metered.

## Architecture (one paragraph)

A single Flask app on Waitress serves three URL surfaces; each surface has its own decorator (`@require_auth` for bearer-token paths, `@require_session` for cookie paths) but every authenticated request resolves to the same `Principal(org_id, plan, auth_method, …)`. Tenant-owned data (`api_keys`, `quotas`, `usage_events`, `org_memberships`) is partitioned by `org_id`; every query that touches it filters on `principal.org_id` and a cross-tenant isolation test suite enforces the rule. The MCP server is a hand-rolled JSON-RPC Flask blueprint (not `fastmcp` — that's ASGI-only and would force a uvicorn swap). WorkOS AuthKit owns identity; Postgres on Railway owns persistence; Google Gemini and Microsoft Presidio do the AI work; S3-compatible object storage handles ephemeral file round-trips for the HTMX surface.

Diagram, table-of-routes, and rationale: [MCP_SUBMISSION_PLAN.md §3](MCP_SUBMISSION_PLAN.md).

## Multi-tenancy

Multi-tenancy is structural, not optional. The seven-table model — `orgs`, `users`, `org_memberships`, `api_keys`, `quotas`, `usage_events`, and (Phase 4) `stripe_customers` — supports B2B teams from day one: an admin issues keys for a 10-seat org, members share the org's quota pool, billing will be per-org with per-seat pricing. The single non-negotiable invariant is `WHERE org_id = :principal_org_id` on every tenant-owned query; cross-tenant attempts return 404 (not 403, to avoid leaking existence). Roles are `owner` / `admin` / `member` with the usual escalation rules.

## Stack

- **Backend:** Python 3.14, Flask, Waitress (WSGI), SQLAlchemy + Alembic
- **Persistence:** Postgres on Railway; ephemeral S3-compatible object storage
- **Identity:** WorkOS AuthKit (OAuth 2.0 / OIDC, JWT bearer)
- **AI:** Google Gemini (text + vision), Microsoft Presidio + spaCy (PII), MTCNN + OpenCV (face detection)
- **Frontend:** HTMX over Jinja2 + Tailwind; PWA manifest
- **Hosting:** Railway (Postgres + app + edge TLS)
- **MCP transport:** hand-rolled JSON-RPC blueprint over Flask; Streamable HTTP 2025-06-18 spec, JSON responses (no SSE for v1)

## Status (2026-06-05)

- **Phase 0** — pre-work (WorkOS creds, Railway Postgres, Gemini spend cap): done
- **Phase 1** — auth + quota + metering pipeline, schema, POC `/api/v1/summarize`, failure-path test suite: done and verified live
- **Phase 1.5** — multi-tenant user/membership graph, WorkOS OAuth flow, dashboard, role-gated key/member management, cross-tenant isolation suite, public-site polish: done and verified live (signup → org auto-created → key issued → API call → quota decrement → `last_used_at` populated)
- **Phase 2** — MCP server: tool surface complete locally (5 tools, 82/82 tests passing). The `summarize_document` vertical slice is deployed and smoke-tested live on `https://www.synzo.ai/mcp` (initialize, tools/list, auth gating, CORS for claude.ai, DNS-rebinding 403, OAuth discovery all pass). The four new tools land in the next deploy.
- **Phase 2.5.A** — waitress thread bump + per-tool timeout — pending; gates public traffic
- **Phase 2.5.B** — SSE + background workers — deferred; gates paid `pro`-tier traffic
- **Phase 3** — submission readiness (MCP Inspector, integration tests, full README/SECURITY docs, magic-byte file detection) — in progress; README refreshed this session
- **Phase 3.5** — Anthropic Connector Directory submission package (logo, screenshots, listing copy, test credentials) — not started
- **Phase 4** — Stripe billing, customer dashboards, per-key rate limits — deferred until a real paying customer asks

## Known trade-offs

- **Synchronous request/response.** Every MCP tool call holds one Waitress worker thread for the entire Gemini turnaround. Acceptable today (free tier caps `pages_per_call` at 20), but Phase 2.5.B (Redis + SSE + background workers) is the proper fix and gates paid traffic. See [MCP_SUBMISSION_PLAN.md §6](MCP_SUBMISSION_PLAN.md) Phase 2.5 for the full sequencing.
- **`transcribe_audio` is not shipped.** The underlying transcription feature in the HTMX surface is a stub returning a hardcoded demo string; shipping a fake MCP tool would mislead Claude and reviewers. Either build the real Gemini-audio pipeline before submission or formally drop transcription from the Synzo capability set.
- **Single Railway replica.** The in-memory per-org RPM bucket and JWKS cache are per-process. Multi-replica needs Redis (deferred in Phase 0, triggered by Phase 2.5.B).

## How to use this repo

- [README.md](README.md) — the public-facing overview, MCP usage examples, error codes, how to run locally
- [MCP_SUBMISSION_PLAN.md](MCP_SUBMISSION_PLAN.md) — the authoritative roadmap, architecture decisions, design-rationale we don't want to re-litigate, and per-phase task lists
- [SAST_REPORT.md](SAST_REPORT.md) — Flask-scope security report. A separate `SECURITY.md` scoped to the MCP server is a Phase 3 deliverable.
- `auth.py` / `auth_routes.py` / `auth_session.py` — the auth/quota/metering pipeline and the dashboard auth surface
- `mcp_routes.py` / `mcp_tools.py` — the MCP server blueprint and the tool registry
- `db/models.py` + `migrations/versions/` — the tenant data model
- `features/` — six feature modules (`summarization`, `translation`, `pii_redaction`, `multimedia`, `transcription`, `info`); the MCP tools call their internals directly so MCP and HTMX results match
- `tests/` — 82 tests covering boot, blueprints, auth happy/edge paths, cross-tenant isolation, and the MCP envelope; run `.venv/Scripts/python.exe -m pytest -q`

## Owner

Paul O'Hagan.
