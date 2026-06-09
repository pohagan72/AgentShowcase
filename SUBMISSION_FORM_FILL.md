# Synzo → Anthropic Connector Directory — Form Fill Template

> **POST-SUBMISSION STATUS (2026-06-10 afternoon):** This file was used to submit Synzo to the Anthropic MCP Directory on **2026-06-10 afternoon**. The actual answers submitted (with deltas) are recorded immutably in [SUBMISSION_RECORD.md](SUBMISSION_RECORD.md). This file has been **revised post-submission to become the template for the next submission** — answers updated to reflect what actually worked, lessons from the form walkthrough folded in, and a stricter pre-submission verification checklist added.

**Use this on submission day.** One section per form page, each field with the literal answer to paste (or `<PASTE_FROM_SECRET_STORE>` for credentials). The strategic reasoning behind every decision is in `MCP_SUBMISSION_PLAN.md`; this file is the operational artifact.

**Last refreshed:** 2026-06-10 afternoon (post-submission template update).

**Pre-submission verification checklist** — run every one of these BEFORE opening the form:

- [ ] Reviewer API key (`sk_synzo_...`) is at hand — from `.env` `SYNZO_API_KEY`.
- [ ] Reviewer test-account password is at hand — held outside the repo.
- [ ] Verify 6 tools are live:
      `curl -sS -X POST https://www.synzo.ai/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m json.tool`
      Should list 6 tools.
- [ ] Verify reviewer org has ≥15 calls_remaining at `https://www.synzo.ai/dashboard` (sign in as paul@redmapleresearch.ca).
- [ ] **Every URL you'll put in the form returns 200**. Run this curl block — every line should print `200`:
      ```bash
      for u in \
        https://www.synzo.ai/docs \
        https://www.synzo.ai/privacy \
        https://www.synzo.ai/support \
        https://www.synzo.ai/security \
        https://www.synzo.ai/terms \
        https://www.synzo.ai/static/images/synzo-icon.svg \
        https://www.synzo.ai/static/images/synzo-icon.png \
        https://www.synzo.ai/static/files/reviewer-bundle.zip \
        https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf \
        https://www.synzo.ai/static/reviewer-samples/translate-sample.docx \
        https://www.synzo.ai/static/reviewer-samples/redact-sample.docx \
        https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg \
        https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg ; \
      do printf "%s -> " "$u" ; curl -sS -o /dev/null -w "%{http_code}\n" "$u" ; done
      ```
      **Don't skip this** — Synzo's 2026-06-10 submission had a logo SVG URL that returned 404 because the file wasn't committed/deployed. The reviewer saw a broken logo. Catch this with curl BEFORE submitting.
- [ ] **Screenshots: ≥1000px wide, PNG, show actual tool output (not mid-execution permission prompts).** Verify dimensions:
      ```bash
      .venv/Scripts/python -c "from PIL import Image; import sys, glob; [print(f'{p}: {Image.open(p).size}') for p in sys.argv[1:]]" path/to/screenshot-*.png
      ```

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

> **2026-06-10 submission lesson:** The form's Authentication Type only offered three options: "No auth needed / OAuth 2.0 / Custom URL (not supported)". There is no "Bearer API key" option even though that's Synzo's primary path. **Select OAuth 2.0** — it's the closest match because Synzo does implement OAuth (DCR via WorkOS AuthKit), and use the reviewer-instructions field to bridge the gap honestly.
>
> The form also asks you to pick "Static OAuth Client" vs "Dynamic OAuth Client (DCR, CIMD)". Synzo's actual flow is DCR, so the technically-correct answer is **Dynamic OAuth Client**. We submitted Static and left the Static Client ID / Secret fields blank because that's how the original cheat sheet was written — both choices work because the reviewer-instructions field is the authoritative source of how-to-authenticate. **For next submission, pick Dynamic** so the form's logic and your actual flow match.

| Field | Answer | Notes |
|---|---|---|
| Authentication Type | **OAuth 2.0** | Closest match the form offers. API-key-as-Bearer is documented in reviewer-instructions. |
| Auth Client | **Dynamic OAuth Client (DCR / CIMD)** | Matches Synzo's actual DCR implementation. (Synzo's 2026-06-10 submission used Static — both work because reviewer-instructions documents the API-key fallback, but Dynamic is the cleaner answer.) |
| Static Client ID | *Leave blank* | Synzo has no pre-registered static OAuth client. Marked "if applicable" — deliberately blank. |
| Static Client Secret | *Leave blank* | Same as above. |
| Transport Support | **Streamable HTTP** (only — don't check SSE) | Server returns `Content-Type: application/json`; SSE is deferred to Phase 2.5.B. |

---

## Form page 2 — Reviewer test bundle / reviewer instructions

> **2026-06-10 submission lesson:** The form actually has **two separate fields** here, not one. The first is "Testing Account Credentials" (a short bare-credentials answer). The second is "Test Account Setup Instructions" (the long narrative onboarding doc). Don't paste the long block into the short field — it'll look out of place and the next field will look empty.
>
> **There is also a "Test Account Server URL (if different from main server URL)" field** — leave it blank for Synzo since testing happens on the same `/mcp` endpoint as production.

### Field A: Testing Account Credentials (short answer)

**Paste verbatim, then substitute the two placeholders:**

````
Authentication: Bearer API key (preferred for review)

API key: <PASTE_REVIEWER_API_KEY>
Header to send: Authorization: Bearer <key>

This key is bound to a free-tier org with 50 calls/month, 20 pages/call, 10 RPM.
Issued for the test account paul@redmapleresearch.ca.

Test account (for dashboard / OAuth path / general access):
  Email: paul@redmapleresearch.ca
  Password: <PASTE_REVIEWER_PASSWORD>
  Dashboard: https://www.synzo.ai/dashboard
  2FA: not required.

Note: the "Static Client ID / Secret" fields on the previous page were left
blank intentionally. Synzo does not have a pre-registered static OAuth client.
The form's auth options didn't cleanly match our setup — see the
test-account-setup-instructions field below for the complete picture (or use
the Bearer API key above for the fastest path).
````

### Field B: Test Account Setup Instructions (long answer)

**Paste verbatim, then substitute the two placeholders:**

````
## Quick start (60 seconds)

1. In claude.ai, open Settings → Connectors → Add custom connector.
2. Paste this URL: https://www.synzo.ai/mcp
3. Open Advanced Settings. The form labels are misleading — Synzo uses a
   Bearer API key, not an OAuth client. Configure auth as **Bearer token**
   and paste this key:

       <PASTE_REVIEWER_API_KEY>

   (Key starts with sk_synzo_. Bound to a free-tier org for the reviewer
   account: 50 calls/month, 20 pages/call, 10 RPM.)

4. Click Add. All 6 tools should appear immediately: upload_file,
   summarize_document, translate_document, redact_pii, analyze_image,
   detect_faces.

No sign-in flow, no popup, no OAuth dance. Sample files are hosted at
public URLs (see below) so you don't need to upload anything to test.

(Note: this is the fastest, lowest-friction path. The six tools are
immediately callable; no sign-in flow, no popup. If your MCP client only
supports OAuth, see fallback below.)

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

The form has **three separate fields** (Tools / Resources / Prompts) plus a checkbox pair for annotations.

### Field: List of tools in your MCP Server

Form format: `tool_name (human-readable name)`, **comma-separated** (everything on one line).

**Paste this single line into the field:**

```
upload_file (Upload a file for use by other Synzo tools), summarize_document (Summarize a document), translate_document (Translate a document), redact_pii (Redact PII from a document), analyze_image (Analyze an image), detect_faces (Detect and obscure faces in an image)
```

### Field: List of resources in your MCP Server (optional, not required)

**Type:** `None`

(Synzo doesn't implement the MCP Resources capability — `resources/list` would return method-not-found.)

### Field: List of prompts in your MCP Server (optional, not required)

**Type:** `None`

(Synzo doesn't implement the MCP Prompts capability — these are reusable parameterized prompt templates per the spec, not system prompts. Different concept; we don't expose any.)

### Checkbox: Tool Titles & Annotations

- ✅ I've specified user-friendly titles for all tools in my server (every tool has a non-empty `title` field, verified by `tests/test_smoke.py::test_docs_page_lists_every_registered_tool`)
- ✅ I've specified accurate tool annotations for all tools in my server (every tool has `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` set in `mcp_tools.py`)

---

## Form page 4 — Branding & visuals

> **2026-06-10 submission lesson:** Form explicitly says "SVG format" for the logo. Synzo's first plan was to submit PNG with a "we'll upgrade to SVG in v1.1" caveat, but the SVG was generated via auto-tracer at submission time and used instead. The trace was 284 KB / 418 path elements (auto-traces are verbose vs hand-drawn SVGs). **Quality was acceptable for thumbnails; the SVG was the right call.**
>
> **CRITICAL LESSON:** the SVG URL submitted on 2026-06-10 returned **404 in production** because the file was on local disk but not committed/deployed. Reviewer saw a broken logo. Caught post-submission. The pre-submission verification checklist at the top of this file now mandates a curl of every URL before submitting — don't skip it.

| Field | Answer |
|---|---|
| Server Logo URL (1:1 square SVG, hosted) | `https://www.synzo.ai/static/images/synzo-icon.svg` |
| Favicon verified | Re-check `https://www.google.com/s2/favicons?domain=synzo.ai&sz=64` before submitting |
| Promotional screenshots (3–5, ≥1000px PNG) | See breakdown below — capture in a session with claude.ai connector enabled, replace placeholders |
| Optional Google Drive folder | Decide at submission time |

### Screenshots — what to capture and what to avoid

**Form requires 3–5 screenshots, each ≥1000px wide, PNG, paired with the prompt that produced it. They go in the form's screenshot-upload UI (one slot per file).**

For the 2026-06-10 Synzo submission, the three uploaded were:

1. ✅ **analyze_image at URL prompt** (1245×897 PNG) — Gold standard: clean tool call, structured result with hex color swatches, safety flags note. Demo-grade.
2. ⚠️ **summarize_document mid-execution at permission prompt** (1279×1010 PNG) — Captured at the "Always allow / Deny" step before tool ran. Shows MCP consent UX (security-positive) but NOT the tool's output. **For next submission, click "Always allow" first and wait for the response to fully render before capturing.**
3. ⚠️ **Connector Customize page** (1919×1016 PNG) — Setup view showing all 6 tools registered. Useful as connector-setup visual; doesn't show tool execution. Goes in the "promo screenshots" slot only because the form doesn't have a dedicated connector-setup field.

**For next submission, aim for 5 in-chat screenshots (one per content-processing tool):**

| Slot | Prompt | Expected on-screen result |
|---|---|---|
| #1 | "Use Synzo to summarize the document at https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf — give me the classification and the summary." | Classification + multi-paragraph Markdown summary |
| #2 | "Use Synzo to translate the document at https://www.synzo.ai/static/reviewer-samples/translate-sample.docx into Spanish." | Translated Markdown |
| #3 | "Use Synzo to redact the PII from the document at https://www.synzo.ai/static/reviewer-samples/redact-sample.docx and give me the download URL." | result_url + size info + PII categories named |
| #4 | "Use Synzo to analyze the image at https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg — describe the scene, list any visible text, and tell me the dominant colors." | Scene + extracted text + hex color swatches (claude.ai auto-renders swatches) |
| #5 | "Use Synzo to blur the faces in the image at https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg with blur_strength 2, and give me the download URL." | result_url + mode + mimetype |

**Recapture tips:**
- Use browser zoom Ctrl++ to ensure ≥1000px wide
- Click "Always allow" on the first connector use so subsequent captures don't pause at consent
- Wait for the full response before snipping (no partial renders)
- Win+Shift+S, drag from above the prompt to just above the message-input box

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

## Form page 6 — Submission Requirements Checklist

> **2026-06-10 submission lesson:** Page 6 is the actual final page and it's substantive — every checkbox is a self-attestation Anthropic can hold you to. The cheat sheet originally treated this as a generic "agree to terms" page but it's structured as four checkbox groups + an "Additional Information" text field + the Submit button.

### Policy Compliance (5 checkboxes — tick all)

- ✅ I have reviewed and agree to the Software Directory Policy
- ✅ My server does NOT enable coercive automation — *no tool initiates outbound action on user data without explicit user-prompted invocation*
- ✅ My server does NOT transfer money, cryptocurrency, or execute financial transactions
- ✅ My MCP server is live, published, and ready to accept production traffic — *verified via the pre-submission curl checklist at the top of this file*
- ✅ I work for the company that owns or controls the API endpoint(s) that my server connects to — *Policy 3.F: Synzo's MCP server runs on synzo.ai which Paul O'Hagan / Red Maple Research owns; Gemini is a downstream provider analogous to AWS/Stripe*

### Technical Requirements (6 checkboxes — tick all)

- ✅ OAuth 2.0 is fully implemented for ALL tools requiring authentication — *implemented via WorkOS AuthKit + DCR; verified end-to-end 2026-06-06*
- ✅ All tools have proper safety annotations (readOnlyHint, destructiveHint) — *all 6 tools have all 4 annotations*
- ✅ Server is accessible via HTTPS (not HTTP)
- ✅ CORS is properly configured for browser-based authentication
- ✅ Claude.ai and Claude Code IP addresses are allowlisted (if applicable) — *no allowlist needed; any origin that passes auth is accepted, hence "if applicable"*
- ✅ I have tested this works with Claude.ai on the latest build — *verified with at least one URL-bearing prompt before submitting*

### Documentation Requirements (4 checkboxes — tick all)

- ✅ Complete server documentation is published and publicly accessible — `/docs`
- ✅ Documentation includes setup instructions, tool descriptions, and troubleshooting guide — `/docs` has all three
- ✅ Company privacy policy is published and accessible — `/privacy`
- ✅ Terms of service are published and accessible — `/terms`

### Testing Requirements (3 checkboxes)

- ✅ Test account with sample data is ready (if relevant)
- ✅ Test credentials are valid for at least 30 days (if relevant) — *Synzo API key has no expiry; do not revoke for 30+ days post-submission*
- ✅ All server tools are functional and tested in the surfaces in which they'll be available (claude.ai, Claude Code, etc) — *the qualifier "in the surfaces in which they'll be available" gives wiggle room; verify in claude.ai web before ticking*

### Additional Information (text field)

**Paste this block to surface the things the form didn't have a clean place for:**

````
A few notes the form didn't have a clean place for:

1. URL-first tool design. Synzo's content-processing tools (summarize_document,
translate_document, redact_pii, analyze_image, detect_faces) accept HTTPS URLs
as content_url rather than inline base64. This avoids the chat-host base64
construction stall on multi-megabyte files — the LLM passes a short URL string
instead of generating tens of thousands of base64 tokens inline. For local files
with no URL, the upload_file tool ingests once and returns a Synzo-hosted URL
(1-hour TTL) the other tools can reference. Server-side URL fetching is
SSRF-guarded: HTTPS only, public IPs only (loopback/private/link-local/cloud-
metadata addresses rejected), 10 MB max, 30-second timeout. Reviewer sample
files are hosted at https://www.synzo.ai/static/reviewer-samples/* so the
directory review experience needs no upload step.

2. Auth choice rationale. The form's Auth section asked for OAuth 2.0 + Static
OAuth Client, and the Static Client ID/Secret fields were left blank. This was
intentional. Synzo implements OAuth 2.0 with Dynamic Client Registration (RFC
7591) against WorkOS AuthKit — proven end-to-end via claude.ai web on 2026-06-06.
On 2026-06-08 we observed claude.ai web no longer triggering the WorkOS sign-in
popup on add-connector; root cause not isolated on our side, server-side
discovery chain remains RFC-correct. We therefore made the API key the
recommended review path. See the test-account-setup-instructions field on page
2 for the operational details.

3. Tool count is 6, not 5. upload_file was added in 2026-06-10 alongside the
URL-first refactor; the other 5 tools (summarize_document, translate_document,
redact_pii, analyze_image, detect_faces) are unchanged in behavior.
````

### Submit

- [ ] **Final sanity pass:** click Back through every page, verify no `<PASTE_...>` placeholders survived in any field. The two most likely culprits: the API key and the reviewer password in the page-2 paste-blocks.
- [ ] **Click Submit (green button, bottom-left).**
- [ ] **Save a screenshot of the confirmation page** — confirmation email will land at the form-submitter email (Gmail or whichever account was logged into Google Forms).

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
