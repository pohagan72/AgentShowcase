# Synzo → Anthropic Connector Directory — Form Fill Cheat Sheet

**Use this on submission day.** One section per form page, each field with the literal answer to paste (or `<TODO>` for the open ones). The strategic reasoning behind every decision is in `MCP_SUBMISSION_PLAN.md`; this file is the operational artifact.

**Last refreshed:** 2026-06-10 mid-day (after Phase 3.7 ships 6-tool URL-first state).

**Before you start:**
- Have the live reviewer API key (`sk_synzo_...`) ready — held outside the repo.
- Have the reviewer test-account password ready — also outside the repo.
- Verify the 6 tools are live: `curl -sS -X POST https://www.synzo.ai/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m json.tool` → should list 6 tools.
- Verify `/docs`, `/privacy`, `/support` all return 200.

---

## Form page 1 — Identity & contact

| Field | Answer |
|---|---|
| Company / Organization name | **Red Maple Research** |
| Company URL | `https://www.synzo.ai` |
| Primary contact name | **Paul O'Hagan** |
| Primary contact email | **paul@redmapleresearch.ca** |
| Primary contact role | **Owner / Maintainer** |
| Anthropic point of contact | *Leave blank* |

---

## Form page 1 — Listing copy

| Field | Answer | Notes |
|---|---|---|
| Server name | **Synzo** | Form rule satisfied: no "MCP" / no "Server" in the name. Matches live `serverInfo.title`. |
| Server URL | `https://www.synzo.ai/mcp` | Universal URL (not per-user). Live + verified. |
| Tagline | **Document and image intelligence for AI agents.** | 46 chars (≤55 allowed). |
| Description | See block below — 77 words, fits the 50–100 word window. |

**Description (paste verbatim):**

> Synzo gives AI agents six tools for working with documents and images: summarize, translate, redact PII, analyze images, blur faces, plus a helper to upload local files. Tools accept HTTPS URLs as input so chat hosts pass a short URL instead of multi-megabyte base64. Powered by Google Gemini, with Microsoft Presidio for PII detection and MTCNN for face detection. Multi-tenant with org-scoped quotas, rate limits, and atomic metering. Free tier available; API-key or OAuth auth (WorkOS AuthKit).

---

## Form page 1 — Capability classification

| Field | Answer | Reasoning |
|---|---|---|
| Read/Write Capabilities | **Read+Write** | Tools fetch user content (read) and return transformed copies via `result_url` for redact_pii / detect_faces (write — the redacted document and blurred image are new artifacts). `upload_file` writes to short-lived blob storage. |
| Is this an "MCP App"? | **No** | No `ui/open-link` or interactive UI elements implemented in `mcp_routes.py`. |
| Personal health data? | **No** | General document/image intelligence; not positioned for medical records. |
| Sponsored content / ads? | **No** | No advertising surface anywhere in the listing or product. |
| Category | **Business & Productivity** | Primary fit given document workflows. Secondary fit "Data & Analytics" — pick Business & Productivity if forced single-select. |

### Third-party Connections and Web Access (multi-select)

Check the boxes that apply, and add the SSRF-guard description in the submission notes:

- ✅ **Server fetches from URLs on the open web** — *all 5 content-processing tools accept a `content_url` HTTPS URL and fetch the bytes server-side via the SSRF-guarded fetcher in `url_fetcher.py`. Constraints: HTTPS only, public IPs only (loopback/private/link-local/cloud-metadata rejected via Python's `ipaddress` library), 10 MB max, 30 s wall-clock timeout, max 3 redirects each re-validated. No internal/private-network access is possible.*
- ✅ **Third-party AI model integration** — *Google Gemini (called server-to-server with Synzo's own API key) powers `summarize_document`, `translate_document`, `analyze_image`.*
- ❌ Other third-party data services — *none.*

### Data Handling checklist

- ✅ **Server only accesses data explicitly requested by user** — every tool acts on either a `content_url` the user supplied or an `upload_file` payload the user passed in. No background fetches, no implicit data access.
- ✅ **No data is stored beyond session requirements** — `usage_events` records metadata only (org_id, tool, units, status, timestamp); file bodies are never persisted to the database. `upload_file` keeps bytes in memory for 1 hour (TTL-bound), then drops them. `result_url` outputs from `redact_pii` / `detect_faces` follow the same 1-hour TTL.
- ✅ **Data transmission is encrypted (HTTPS/TLS)** — Railway edge terminates TLS; outbound Gemini calls are HTTPS; SSRF fetcher refuses non-HTTPS schemes.
- ✅ **GDPR compliant** — `/privacy` is GDPR-scoped: lawful bases declared, data-subject rights documented, retention windows specified (90 days `usage_events`, 30 days for deletion processing), international transfers via SCCs disclosed. EU users accepted.

---

## Form page 1 — Use cases

Paste **≥3 use cases**, each pairing a one-line description with a reviewer-runnable prompt. **All prompts use URL-bearing form** (per Phase 3.7 — chat hosts handle URL strings instantly; attached files force base64 generation that stalls the UI).

### Use case 1 — Summarize a document
**Description:** Extract the document type and a structured summary from a PDF or Office file in one shot.
**Prompt:**
> Use Synzo to summarize the document at https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf — give me the classification and the summary.

### Use case 2 — Redact PII from a document
**Description:** Detect and redact personal information in a Word document; receive a downloadable URL of the redacted file.
**Prompt:**
> Use Synzo to redact the PII from the document at https://www.synzo.ai/static/reviewer-samples/redact-sample.docx and give me the download URL.

### Use case 3 — Analyze an image
**Description:** Get a structured description, OCR'd text, safety flags, detected objects, and a dominant-color palette from a photo.
**Prompt:**
> Use Synzo to analyze the image at https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg — describe the scene, list any visible text, and tell me the dominant colors.

### Optional bonus prompts (use if the form accepts more than 3)
- **Translate** — *Use Synzo to translate the document at https://www.synzo.ai/static/reviewer-samples/translate-sample.docx into Spanish.*
- **Blur faces** — *Use Synzo to blur the faces in the image at https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg and give me the download URL.*

### Connection requirements field
**Answer:** *Add the connector at `https://www.synzo.ai/mcp` and paste the provided API key as a Bearer token. No admin seat, no custom URL, no geographic restriction. Sample-file URLs above resolve from anywhere; tool calls work immediately after the API key is set.*

---

## Form page 1 (bottom) — Docs & support links

| Field | URL |
|---|---|
| Public documentation URL | `https://www.synzo.ai/docs` |
| Privacy Policy URL | `https://www.synzo.ai/privacy` |
| Data Processing Agreement URL | *Leave blank — we don't have one yet* |
| Support Channel URL | `https://www.synzo.ai/support` |
| Security disclosure URL | `https://www.synzo.ai/security` (in case the form asks separately) |

---

## Form page 2 — Auth & test access

| Field | Answer |
|---|---|
| Authentication Type | **API key (Bearer)** |
| Auth Client | **Static** |
| Static Client ID / Secret / API Key | `<PASTE_REVIEWER_API_KEY>` — `sk_synzo_...` for the reviewer org. From `.env` `SYNZO_API_KEY`. |
| Transport Support | **Streamable HTTP yes, SSE no** (server returns `Content-Type: application/json`; SSE is deferred to Phase 2.5.B). |

---

## Form page 2 — Reviewer test bundle / reviewer instructions

**Paste this verbatim into the form's reviewer-instructions field** (form likely accepts markdown; if plain text only, strip the backticks):

````
**Server URL:** https://www.synzo.ai/mcp
**Transport:** Streamable HTTP (application/json). Protocol versions: 2025-06-18, 2025-03-26.
**Auth:** Bearer API key (recommended for review) OR OAuth 2.0 via WorkOS AuthKit.
**Tools/Resources/Prompts:** 6 / 0 / 0. Live registry visible at https://www.synzo.ai/docs.

## Recommended auth: paste this API key

When adding Synzo as a custom MCP connector, configure auth as **Bearer token** and paste:

    <PASTE_REVIEWER_API_KEY>

(Key starts with `sk_synzo_`. Issued from the dashboard for the reviewer account
paul@redmapleresearch.ca; bound to a free-tier org with 50 calls/month, 20 pages/call,
10 RPM. Verified end-to-end via MCP Inspector + automated sweep on 2026-06-10.)

This is the fastest, lowest-friction path. The six tools are immediately callable;
no sign-in flow, no popup. If your MCP client only supports OAuth, see fallback below.

## Fallback: OAuth 2.0 via WorkOS AuthKit (optional)

Synzo also implements OAuth 2.0 with Dynamic Client Registration (RFC 7591) against
WorkOS AuthKit. This was verified end-to-end via claude.ai web on 2026-06-06 (a real
user signed in, consented, and invoked a tool through claude.ai's chat UI).
Disclosure: as of 2026-06-08 we observed claude.ai web no longer triggering the
WorkOS sign-in popup when the connector is added — root cause not isolated on our
side; the server-side discovery chain (RFC 9728 / RFC 8414) is intact per direct
curl probes. We've therefore made the API key the primary path. If your client does
initiate OAuth: sign in with the reviewer credentials in the "Test account" section
below.

## Test account (for dashboard / OAuth path / general access)

- Email: paul@redmapleresearch.ca
- Password: <PASTE_REVIEWER_PASSWORD>
- Dashboard: https://www.synzo.ai/dashboard
- Plan: free (50 calls/month, 20 pages/call, 10 req/min)

## Sample files (public URLs — recommended for the review sweep)

Synzo's content-processing tools accept HTTPS URLs as input. The chat host LLM
passes a short URL string to the tool's `content_url` argument; Synzo fetches the
file server-side via an SSRF-guarded fetcher. This is instant — no base64
generation in the chat sandbox. We host the five reviewer samples at:

- https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf  (39 KB)
- https://www.synzo.ai/static/reviewer-samples/translate-sample.docx (14 KB)
- https://www.synzo.ai/static/reviewer-samples/redact-sample.docx    (36 KB)
- https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg    (2.9 MB)
- https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg (324 KB)

Same files also available as a zip: https://www.synzo.ai/static/files/reviewer-bundle.zip

## End-to-end sweep — paste each prompt into claude.ai with the connector enabled.

Each prompt names a public sample-file URL. The LLM passes that URL through as the
tool's `content_url` argument. Total quota burn: 5 of 50 free-tier calls.

1. summarize_document
   "Use Synzo to summarize the document at
   https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf — give me the
   classification and the summary."
   Returns: { classification, summary, filename }. No source-text echo.

2. translate_document
   "Use Synzo to translate the document at
   https://www.synzo.ai/static/reviewer-samples/translate-sample.docx into Spanish."
   Returns: { filename, target_language, translated_text }. Markdown output.

3. redact_pii (synthetic HR memo with seeded fake PII)
   "Use Synzo to redact the PII from the document at
   https://www.synzo.ai/static/reviewer-samples/redact-sample.docx and give me the
   download URL."
   Returns: { filename, result_url, expires_at, mimetype,
   original_size_bytes, redacted_size_bytes }. result_url is a Synzo-hosted HTTPS
   URL with a 1-hour TTL. Presidio default English recognizers redact PERSON,
   EMAIL_ADDRESS, PHONE_NUMBER, US_SSN, CREDIT_CARD, US_PASSPORT, LOCATION,
   DATE_TIME, NRP, ORGANIZATION to U+2588 block characters in place.

4. analyze_image
   "Use Synzo to analyze the image at
   https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg — describe the
   scene, list any visible text, and tell me the dominant colors."
   Returns: { filename, analysis: { description, rich_description, extracted_text,
   safety_flags, detected_objects }, dominant_colors }.

5. detect_faces
   "Use Synzo to blur the faces in the image at
   https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg and give
   me the download URL."
   Returns: { filename, mode, result_url, expires_at, mimetype } — result_url
   points at a PNG with faces blurred (1-hour TTL).
   Cold-start note: first call on a fresh replica pays ~10–30s for MTCNN/TensorFlow
   graph load. Subsequent calls fast.

## Optional: exercise the local-file upload path

If you want to test the local-file path too, attach one of the bundle files (or any
small file) to the chat and say:

   "Use Synzo to upload this file and then summarize it."

The LLM will call upload_file (one-time base64 cost — slower than the URL path for
multi-MB files) and chain to the target tool. The URL prompts above are the
recommended sweep because they better demonstrate the tool design's intent.

## Direct verification (no connector required)

MCP Inspector path: `npx @modelcontextprotocol/inspector` → Transport: Streamable HTTP
→ URL: https://www.synzo.ai/mcp → Auth: Bearer + the API key above. Click Connect;
all 6 tools render with full schemas and annotations. We sweep this path on every
deploy via `scripts/sweep_tools.py` (which exercises the full upload-then-tool
chain plus URL-only calls).

## Error envelope (for reference)

- -32001 Auth (missing/expired/invalid bearer; orphan org; missing JWT claim)
- -32002 Quota (monthly call cap exhausted)
- -32003 Rate limit (per-org RPM cap surfaced in message)
- -32004 Units exceeded (per-call cap, e.g. >20 pages on free tier)
- -32005 Tool timeout (60s wall-clock; quota refunded, metered as 'timeout')
Tool-internal failures (handler exception, downstream model error) come back as
isError: true in the result envelope — not a JSON-RPC error — so Claude can recover.
Quota is still refunded on the exception path.

## Contact during review

paul@redmapleresearch.ca. Security disclosures: same address, but please use the
disclosure flow at https://www.synzo.ai/security so it lands with the right
framing + SLA.
````

---

## Form page 3 — Server inventory

The form requires the inventory in the exact format `tool_name (Human Readable Name)`.

**Tools (6):**
- `upload_file` (Upload a file for use by other Synzo tools)
- `summarize_document` (Summarize a document)
- `translate_document` (Translate a document)
- `redact_pii` (Redact PII from a document)
- `analyze_image` (Analyze an image)
- `detect_faces` (Detect and obscure faces in an image)

**Resources:** 0 (none implemented)
**Prompts:** 0 (none implemented)

**Checkboxes to tick after re-verifying:**
- ✅ User-friendly titles (every tool has a non-empty `title` field — verified by `tests/test_smoke.py::test_docs_page_lists_every_registered_tool`)
- ✅ Accurate tool annotations (every tool has `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` set in `mcp_tools.py`)

---

## Form page 4 — Branding & visuals

| Field | Answer |
|---|---|
| Logo URL (1:1 square, ≥500×500) | `https://www.synzo.ai/static/images/synzo-icon.png` (500×500 PNG, ~180 KB) |
| Favicon verified | ✅ Re-check `https://www.google.com/s2/favicons?domain=synzo.ai&sz=64` before checking the form box |
| Promotional screenshots (3–5, ≥1000px PNG) | `<TODO>` — captured one in 2026-06-10 claude.ai test (analyze_image with URL prompt). Capture 2–4 more after rate-limit reset. Pair each with its prompt. |
| Optional Google Drive folder | Decide at submission time |

**Screenshots captured so far:**
1. ✅ analyze_image — *"Use Synzo to analyze the image at https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg — describe the scene, list any visible text, and tell me the dominant colors."* (clean single tool call, structured result, hex color swatches rendered)
2. `<TODO>` — summarize_document
3. `<TODO>` — translate_document
4. `<TODO>` — redact_pii (shows result_url download)
5. `<TODO>` — detect_faces (shows result_url download)

---

## Form page 4 — Launch readiness

| Field | Answer | Notes |
|---|---|---|
| Tested in Claude.ai (web) | **✅ Yes** | Verified 2026-06-10 with URL-bearing prompt against `analyze_image`. |
| Tested in Claude Desktop | **❌ Leave unchecked** | Work account's org-level "connectors disabled" policy blocks it. Form says Desktop not required. |
| Tested in Claude Code / Cowork | **❌ Leave unchecked** | Form says not required. |
| Server GA Date | **Choose:** Synzo's public site has been live since Phase 1.5 deploy (2026-06-05). MCP server live since 2026-06-05. Pick the earlier date that fits the form's intent. |

---

## Form page 5 — Skills & Plugins

| Field | Answer |
|---|---|
| Skill submission (SKILL.md) | *Leave blank* — not submitting a skill |
| Related Plugin | *Leave blank* — not submitting a Claude Code plugin |

---

## Form page 6 — Compliance & submission

### Pre-submission checklist

Walk every item in https://docs.claude.com/connectors/building/submission/pre-submission-checklist. Phase 3 audits should cover most; this is the final read-through.

### Anthropic Software Directory Terms

Review and accept https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms. Key clauses being accepted (verified against current state):

- ✅ Warranty: we own/control all API endpoints — see the Policy 3.F note below.
- ✅ Indemnification of Anthropic for claims related to Synzo or user interactions with it.
- ✅ Anthropic may review, test, and remove the connector at any time.
- ✅ Anthropic gets a license to display Synzo's name/logo/screenshots in the directory.
- ✅ We agree to maintain compliance with the Software Directory Policy as it updates.

### Anthropic Software Directory Policy

Review and confirm compliance with https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy. All Phase 3 policy audits PASS as of 2026-06-06:

- ✅ Policy 1.D / 1.F observability surface — no Sentry/Datadog/PostHog/GA/etc.
- ✅ Policy 1.F tool descriptions — no implication of Claude memory/history/files.
- ✅ Policy 2 prompt-injection scan — no instructions to call other tools, no override of system instructions.
- ✅ Policy 3.F API ownership — paste-block below.
- ✅ Policy 5.B token frugality — every response shape minimal; no source-text echo.
- ✅ Policy 5.A error messages — every raise site actionable; per-org RPM cap named in -32003.

### Unsupported-use-cases (§4)

- ✅ Does not transfer money/crypto.
- ✅ Does not generate images/video/audio via AI (`analyze_image` only *describes*; `detect_faces` only *blurs/redacts*).
- ✅ Does not serve ads or sponsored content.

### Submit

- [ ] **Submit to Connector Directory.**

---

## Submission notes paste-blocks

Several form fields ask for free-form notes. The blocks below are pre-written; paste them where they fit best.

### Block A — URL-first design rationale (paste into "Additional notes" or wherever submission-notes are accepted)

> **URL-first tool surface (deliberate design).** Synzo's five content-processing tools accept HTTPS URLs as input via a `content_url` argument — the chat-host LLM passes a short URL string in the tool call rather than a multi-megabyte base64 payload. For files already at an HTTPS URL the cost is near-zero. For local-only files, the `upload_file` tool ingests one file and returns a Synzo-hosted URL (1 hour TTL) the other tools can reference. The server fetches `content_url` through an SSRF-guarded fetcher: HTTPS only, public IPs only (loopback / private / link-local / cloud-metadata addresses rejected via Python's `ipaddress` library), 10 MB max, 30 s wall-clock timeout, max 3 redirects each re-validated against the IP allowlist. We host the reviewer-facing sample files at `https://www.synzo.ai/static/reviewer-samples/*` so the directory review experience needs no upload step. `redact_pii` and `detect_faces` follow the same pattern for output: they return `result_url` pointing at a Synzo-hosted HTTPS download with the same 1-hour TTL, rather than inlining the bytes in the response.

### Block B — API ownership (Policy 3.F) (paste into "Reviewer notes on API ownership" or similar)

> **API ownership (Policy 3.F).** Synzo's MCP server is first-party — all endpoints (`/mcp`, `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`, OAuth callbacks, `/u/<token>` blob-serve, `/static/reviewer-samples/*`) run on synzo.ai, which Paul O'Hagan (Red Maple Research) owns and operates. Users authenticate to synzo.ai via WorkOS AuthKit, not to any downstream provider. Google Gemini is a downstream model provider called server-to-server with Synzo's own API key (analogous to how an SaaS app uses AWS or Stripe); Gemini is named explicitly in the privacy policy under "Service providers." Microsoft Presidio (PII detection) and MTCNN/OpenCV (face detection) run in-process from Synzo's Python environment. When a tool fetches a `content_url` supplied by the user, the fetch is constrained by the SSRF guard described above — only public-internet HTTPS endpoints are reachable. The Synzo tool surface is contract-stable across model providers: swapping Gemini for Claude or another model is an internal config change at the wrapped Gemini call sites, not a tool-surface change.

### Block C — Multi-tenancy + metering posture (use if asked about isolation)

> **Multi-tenant from row zero.** Every API call resolves to exactly one organization; every query that returns tenant-owned data scopes on `org_id` (enforced by `tests/test_multi_tenant_isolation.py` and the OAuth-path test in `tests/test_mcp_server.py`). Quotas, rate limits, and metering are org-scoped. WorkOS AuthKit owns identity; Synzo mirrors the user/org graph locally for atomic billing-grade metering. The `usage_events` table records metadata only (org_id, tool, units, status, timestamp, auth_method); file bodies are never persisted.

---

## Post-submission

After clicking submit:

1. Save a copy of every paste-block in case the form asks for resubmission.
2. Record the submission ID / confirmation email in `MCP_SUBMISSION_PLAN.md` so future-us can correlate.
3. Watch `paul@redmapleresearch.ca` for reviewer questions.
4. Don't push code changes to the MCP surface until the review concludes — drift between the submission state and the deployed state creates avoidable failure modes.
