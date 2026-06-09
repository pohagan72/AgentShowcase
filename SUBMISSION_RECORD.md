# Synzo → Anthropic MCP Directory: Submission Record

**Status:** SUBMITTED 2026-06-10 afternoon
**Submission form:** Google Forms (Anthropic-hosted)
**Form submitter email:** pohagan72@gmail.com
**Primary contact (correspondence):** paul@redmapleresearch.ca
**Confirmation expected at:** pohagan72@gmail.com (form submitter), then forwarded/escalated to paul@redmapleresearch.ca

---

## Purpose of this document

This is the **immutable record** of what was actually submitted — the historical truth, frozen at submission moment. Don't edit this file to "improve" answers later; if you need to update something, that's a separate revision tracked elsewhere.

The purpose is twofold:
1. **Reviewer correspondence reference** — when a reviewer asks "why did you select X for Y?", you have a single source to check what you actually said.
2. **Next-submission template** — if Synzo ships v1.1 with new tools, or if Red Maple Research submits a different MCP server later, this file is the starting point for the next form. Don't relearn the form from scratch.

For the *strategic reasoning* behind each answer, see `MCP_SUBMISSION_PLAN.md`. For the *current operational state* of the system, see the live code + the README.

---

## Page 1 — Company information

| Field | Submitted value |
|---|---|
| Company / Organization Name | Red Maple Research |
| Company / Organization URL | https://www.synzo.ai/ |
| Primary Contact Name | Paul O'Hagan |
| Primary Contact Email | paul@redmapleresearch.ca |
| Primary Contact Role | CTO |
| Anthropic Point of Contact (if known) | *Left blank* |

---

## Page 1 — Server details

| Field | Submitted value |
|---|---|
| MCP Server Name | Synzo Document Intelligence |
| MCP Server URL type | Universal URL |
| MCP Server URL | https://www.synzo.ai/mcp |

### Tagline (46 chars)
```
Document and image intelligence for AI agents.
```

### MCP Server Description (77 words)
```
Synzo gives AI agents six tools for working with documents and images: summarize, translate, redact PII, analyze images, blur faces, plus a helper to upload local files. Tools accept HTTPS URLs as input so chat hosts pass a short URL instead of multi-megabyte base64. Powered by Google Gemini, with Microsoft Presidio for PII detection and MTCNN for face detection. Multi-tenant with org-scoped quotas, rate limits, and atomic metering. Free tier available; API-key or OAuth auth (WorkOS AuthKit).
```

### Use Cases + Examples
```
1. Summarize a document
   "Use Synzo to summarize the document at https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf — give me the classification and a structured summary."
   Returns: { classification, summary, filename }

2. Redact PII from a document
   "Use Synzo to redact the PII from the document at https://www.synzo.ai/static/reviewer-samples/redact-sample.docx and give me the download URL."
   Returns: { result_url, mimetype, original_size_bytes, redacted_size_bytes }

3. Analyze an image
   "Use Synzo to analyze the image at https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg — describe the scene, list any visible text, and tell me the dominant colors."
   Returns: { analysis: { description, extracted_text, safety_flags, detected_objects }, dominant_colors }

4. Translate a document (bonus)
   "Use Synzo to translate the document at https://www.synzo.ai/static/reviewer-samples/translate-sample.docx into Spanish."
   Returns: { translated_text, target_language, filename }

5. Blur faces in an image (bonus)
   "Use Synzo to blur the faces in the image at https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg and give me the download URL."
   Returns: { result_url, mode, mimetype }
```

### Connection requirements
```
No special requirements. Add the connector at https://www.synzo.ai/mcp and paste the provided API key as a Bearer token. No admin seat needed, no custom URL, no geographic restriction. Sample-file URLs work from anywhere.
```

---

## Page 1 — Capability classification

| Field | Submitted value |
|---|---|
| Read/Write Capabilities | Read + Write |
| Is this an "MCP App"? | No |
| Third-party Connections — Web access (open web URL fetch) | ✅ Checked |
| Third-party Connections — Third-party AI model integration | ✅ Checked |
| Third-party Connections — Third-party data retrieval | ❌ Not checked |
| Third-party Connections — Third-party data modification | ❌ Not checked |
| Data Handling — Server only accesses data explicitly requested | ✅ Checked |
| Data Handling — No data stored beyond session requirements | ✅ Checked |
| Data Handling — Data transmission encrypted (HTTPS/TLS) | ✅ Checked |
| Data Handling — GDPR compliant | ✅ Checked |
| Personal health data? | No |
| Category | Business & Productivity |
| Sponsored content / ads? | No, there is no sponsored content or advertisements |

---

## Page 1 — Authentication

| Field | Submitted value | Notes |
|---|---|---|
| Authentication Type | OAuth 2.0 | Form's only viable option — Synzo's actual flow is described in reviewer-instructions |
| Auth Client | Static OAuth Client | Mismatch acknowledged in reviewer-instructions; real auth is API-key-as-Bearer |
| Static Client ID (if applicable) | *Left blank* | Synzo has no pre-registered OAuth client; deliberate blank, explained in reviewer-instructions |
| Static Client Secret (if applicable) | *Left blank* | Same as above |
| Transport Support | Streamable HTTP | SSE not implemented; deferred to Phase 2.5.B |

---

## Page 1 — Documentation links

| Field | Submitted URL |
|---|---|
| MCP Server Documentation Link | https://www.synzo.ai/docs |
| Privacy Policy | https://www.synzo.ai/privacy |
| Data Processing Agreement URL | *Left blank* |
| Support Channel | https://www.synzo.ai/support |

---

## Page 2 — Testing Account Credentials

```
Authentication: Bearer API key (preferred for review)

API key: sk_synzo_<HELD_OUTSIDE_REPO>
Header to send: Authorization: Bearer <key>

This key is bound to a free-tier org with 50 calls/month, 20 pages/call, 10 RPM.
Issued for the test account paul@redmapleresearch.ca.

Test account (for dashboard / OAuth path / general access):
  Email: paul@redmapleresearch.ca
  Password: <HELD_OUTSIDE_REPO>
  Dashboard: https://www.synzo.ai/dashboard
  2FA: not required.

Note: the "Static Client ID / Secret" fields on the previous page were left
blank intentionally. Synzo does not have a pre-registered static OAuth client.
The form's auth options didn't cleanly match our setup — see the
reviewer-instructions field on this page for the complete picture (or use the
Bearer API key above for the fastest path).
```

**Privacy note:** the literal API key and reviewer password are NOT recorded here. They live in `.env` (key) and your password store (password). If you need to retrieve them for reviewer correspondence: see `.env`'s `SYNZO_API_KEY` line (key prefix `sk_synzo_tgO...`).

| Field | Submitted value |
|---|---|
| Test Account Server URL (if different from main) | *Left blank* (same as main URL) |

---

## Page 2 — Test Account Setup Instructions

This was the big paste-block. Verbatim content as submitted:

```markdown
## Quick start (60 seconds)

1. In claude.ai, open Settings → Connectors → Add custom connector.
2. Paste this URL: https://www.synzo.ai/mcp
3. Open Advanced Settings. The form labels are misleading — Synzo uses a
   Bearer API key, not an OAuth client. Configure auth as **Bearer token**
   and paste this key:

       sk_synzo_<KEY_HELD_OUTSIDE_REPO>

   (Key starts with sk_synzo_. Bound to a free-tier org for the reviewer
   account: 50 calls/month, 20 pages/call, 10 RPM.)

4. Click Add. All 6 tools should appear immediately: upload_file,
   summarize_document, translate_document, redact_pii, analyze_image,
   detect_faces.

No sign-in flow, no popup, no OAuth dance. Sample files are hosted at
public URLs (see below) so you don't need to upload anything to test.

## 5-prompt sweep — paste each one into a fresh chat

Each prompt names a public Synzo-hosted sample-file URL. The LLM passes
the URL through as the tool's content_url argument. Total quota burn:
5 of 50 free-tier calls.

1. summarize_document
   Prompt: "Use Synzo to summarize the document at
   https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf —
   give me the classification and the summary."
   Expect: structured Markdown summary + a classification label.

2. translate_document
   Prompt: "Use Synzo to translate the document at
   https://www.synzo.ai/static/reviewer-samples/translate-sample.docx
   into Spanish."
   Expect: Spanish-translated Markdown of the source text.

3. redact_pii
   Prompt: "Use Synzo to redact the PII from the document at
   https://www.synzo.ai/static/reviewer-samples/redact-sample.docx and
   give me the download URL."
   Expect: a result_url to a Synzo-hosted .docx with all PII replaced by
   U+2588 block characters. The result_url is downloadable for 1 hour.
   The source file is a synthetic HR memo with seeded fake PII — name,
   email, phone, SSN, passport number, credit card.

4. analyze_image
   Prompt: "Use Synzo to analyze the image at
   https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg —
   describe the scene, list any visible text, and tell me the dominant
   colors."
   Expect: scene description, OCR'd text, safety flags, detected objects,
   and a palette of dominant-color hex codes (claude.ai's UI will render
   color swatches inline).

5. detect_faces
   Prompt: "Use Synzo to blur the faces in the image at
   https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg
   and give me the download URL."
   Expect: a result_url to a PNG with faces blurred. First call may take
   10-30s on cold start as MTCNN/TensorFlow loads; subsequent calls are
   fast.

## Optional: local-file upload path

To test the local-file ingestion path:
- Attach any small file to the chat (e.g., one of the bundle files at
  https://www.synzo.ai/static/files/reviewer-bundle.zip).
- Prompt: "Use Synzo to upload this file and then summarize it."
- The LLM calls upload_file first to ingest the bytes, then chains to
  summarize_document with the returned content_url. This proves the
  local-file path works; the URL prompts above demonstrate the design's
  intent better (no base64 in the chat sandbox).

## Test account for the dashboard (optional)

Only needed if you want to inspect the Synzo dashboard (quota usage, API
key management, etc.) — not required for the tool sweep above.

- URL: https://www.synzo.ai/dashboard
- Email: paul@redmapleresearch.ca
- Password: <PASSWORD_HELD_OUTSIDE_REPO>
- 2FA: not required.

## If something doesn't work

- Tool returns isError=true with a message: that's the tool's own error
  channel — the message will name the problem (e.g., file fetch failed,
  unsupported extension). Quota is automatically refunded on these.
- Tool call returns -32001: API key was not set as a Bearer token. Re-check
  the Authorization header.
- Tool call returns -32002: quota exhausted. Contact paul@redmapleresearch.ca
  for a quota top-up.
- Tool call returns -32003: rate limit (10 req/min). Wait a moment and retry.
- Tool call returns -32005: server-side timeout (60s wall-clock). Try a
  smaller file. Quota is refunded.

## Direct verification (no claude.ai required)

If you'd rather test without claude.ai's chat UI:
  npx @modelcontextprotocol/inspector
  → Transport: Streamable HTTP
  → URL: https://www.synzo.ai/mcp
  → Auth: Bearer + the API key above
  → Click Connect.
All 6 tools render with full schemas and annotations.

## Documentation + contact

- Live tool docs: https://www.synzo.ai/docs
- Privacy policy: https://www.synzo.ai/privacy
- Support / questions during review: paul@redmapleresearch.ca
- Security disclosures: https://www.synzo.ai/security
```

---

## Page 3 — Server inventory

### Tools
```
upload_file (Upload a file for use by other Synzo tools), summarize_document (Summarize a document), translate_document (Translate a document), redact_pii (Redact PII from a document), analyze_image (Analyze an image), detect_faces (Detect and obscure faces in an image)
```

### Resources
```
None
```

### Prompts
```
None
```

### Tool Titles & Annotations checkboxes
- ✅ I've specified user-friendly titles for all tools in my server
- ✅ I've specified accurate tool annotations for all tools in my server

---

## Page 4 — Branding & launch readiness

| Field | Submitted value | Notes |
|---|---|---|
| Server Logo URL | https://www.synzo.ai/static/images/synzo-icon.svg | ⚠️ **At submission time this URL returned 404** — the SVG was on Paul's local disk but not committed/deployed. **Action required:** commit + push the SVG so the URL resolves. Tracked as a follow-up item in MCP_SUBMISSION_PLAN.md §Phase 3.5 post-submission. |

### Logo provenance
Auto-traced from `synzo-icon.png` (500×500 RGBA PNG, 180 KB) using an online vectorizer. Resulting SVG is 284 KB with 418 path elements (auto-traces are verbose by nature; hand-drawn SVGs of this complexity are typically 5-20 KB). No `viewBox` attribute — works in modern browsers but worth adding in a future polish pass. Visual quality matches the PNG closely enough for directory thumbnails.

### Promotional screenshots
Three screenshots uploaded:
1. `screenshot-3.png` (1245×897, PNG) — analyze_image URL prompt + Scene + Visible text + 5 dominant colors with hex swatches + safety flags. **Gold standard:** clean tool call, clear structured result, demo-grade.
2. `screenshot-2.png` (1279×1010, PNG) — summarize_document URL prompt captured at the "Always allow / Deny" permission step. **Demonstrates the human-in-the-loop consent UX** required by MCP spec (security-positive signal), though it doesn't show the tool's output. Considered borderline but submitted as-is per Paul's call.
3. `screenshot-1.png` (1919×1016, PNG) — Customize → Connectors page showing Synzo registered with all 6 tools and their Tool Permissions. **Proves the connector loads cleanly** and surfaces every tool with its user-friendly name. Functions as a connector-setup visual.

### Launch readiness checkboxes
- ✅ Tested in Claude.ai (web) — verified 2026-06-10 with `analyze_image` URL prompt
- ❌ Tested in Claude Desktop — work account's "connectors disabled" policy blocks; Form text says Desktop not required
- ❌ Tested in Claude Code / Cowork — form text says not required
- Server GA Date: 2026-06-05 (Phase 1.5 deploy when public site went live + MCP server stood up)

---

## Page 5 — Skills & Plugins

All fields *left blank* — Synzo doesn't ship with an accompanying Claude Skill or Claude Code plugin. The form text explicitly says this is not required for MCP server submission.

---

## Page 6 — Submission Requirements Checklist

### Policy Compliance (all 5 ticked)
- ✅ I have reviewed and agree to the Software Directory Policy
- ✅ My server does NOT enable coercive automation
- ✅ My server does NOT transfer money, cryptocurrency, or execute financial transactions
- ✅ My MCP server is live, published, and ready to accept production traffic
- ✅ I work for the company that owns or controls the API endpoint(s) that my server connects to

### Technical Requirements (all ticked)
- ✅ OAuth 2.0 is fully implemented for ALL tools requiring authentication — *implemented via WorkOS AuthKit + DCR; verified 2026-06-06; API-key-as-Bearer is the recommended path due to claude.ai's 2026-06-08 behavior change*
- ✅ All tools have proper safety annotations (readOnlyHint, destructiveHint)
- ✅ Server is accessible via HTTPS (not HTTP)
- ✅ CORS is properly configured for browser-based authentication
- ✅ Claude.ai and Claude Code IP addresses are allowlisted (if applicable) — no allowlist needed; any origin that passes auth is accepted
- ✅ I have tested this works with Claude.ai on the latest build — verified 2026-06-10

### Documentation Requirements (all 4 ticked)
- ✅ Complete server documentation is published and publicly accessible
- ✅ Documentation includes setup instructions, tool descriptions, and troubleshooting guide
- ✅ Company privacy policy is published and accessible
- ✅ Terms of service are published and accessible

### Testing Requirements (all 3 ticked)
- ✅ Test account with sample data is ready
- ✅ Test credentials are valid for at least 30 days — API key has no expiry; do not revoke for 30+ days
- ✅ All server tools are functional and tested in the surfaces in which they'll be available — claude.ai web verified; Desktop blocked by work account; per form qualifier, "surfaces in which they'll be available" = claude.ai web

### Additional Information (text field)
```
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
```

---

## Open follow-ups (post-submission)

These are items to handle while waiting for reviewer correspondence:

- [ ] **Commit + deploy `static/images/synzo-icon.svg`** so the form's Server Logo URL stops returning 404. **This is the most time-sensitive item** — reviewer will see a broken logo until fixed.
- [ ] **Add `viewBox="0 0 500 500"`** to the SVG for cleaner scaling (low priority, polish only).
- [ ] **Verify reviewer-org quota** at `https://www.synzo.ai/dashboard` — confirm calls_remaining ≥ 15 so reviewer's sweep doesn't exhaust it.
- [ ] **Save the form confirmation email** (will land at pohagan72@gmail.com) — link it from this file.
- [ ] **Watch paul@redmapleresearch.ca for reviewer questions.**
- [ ] **Don't push code to the MCP surface** until review concludes — drift between submission state and deployed state creates avoidable failure modes. The SVG fix is the one allowed exception (it's a static asset, not the MCP surface).

---

## Lessons captured for next submission

1. **The form's "Static Client ID / Secret" fields don't match a DCR-OAuth setup.** Both fields are "if applicable" — leave blank, explain in reviewer-instructions. Don't try to paste an API key into a field labeled OAuth client_id.

2. **The form's three auth options are limiting.** "OAuth 2.0" is the closest match even when API-key-as-Bearer is your real recommended path. Use the reviewer-instructions paste-block to bridge the gap honestly.

3. **Test the form-submitted URLs from a clean machine before submitting.** The SVG-404 issue would have been caught by a `curl -sI` of every URL in the form right before clicking Submit. Build this into the next pre-submission checklist.

4. **Screenshots should show tool output, not just connector state.** screenshot-2 was captured mid-execution (at the "Always allow" prompt) and shows process rather than result. For the next submission, capture only after the tool's response has rendered completely.

5. **Reviewer-instructions field is doing a lot of work.** It's the canonical place for credentials, the auth-mismatch explanation, the sweep prompts, and the troubleshooting reference. Treat it as the most important field on the entire form — far more impactful than any single checkbox.

6. **Tool count was 5 at original-spec time, became 6 mid-build.** The plan documented this clearly, but several form fields had to be edited at submission time to reflect 6. For a future submission that adds tools post-spec-lock, factor that update cost in.

7. **SVG auto-trace is acceptable when SVG is required.** ~30 minutes from PNG to deployed SVG. Quality matched the PNG closely enough that reviewers won't notice the difference at thumbnail size.
