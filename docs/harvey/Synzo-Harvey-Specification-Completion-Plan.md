# Plan: complete Harvey's MCP server specification for Synzo

Prepared: October 5, 2026  
Repository reviewed: `1adc36e`  
Template: `C:\Users\651802\Downloads\[Example] Ideal MCP Server Specification - Harvey AI (1).docx`

Use the existing Harvey technical documentation as the content base and the supplied Word document as the structure. Most service facts are already available. The main writing work is to expand each tool's return contract, document authentication precisely, and replace the fictional service's controls with Synzo's implemented controls.

The example illustrates the level of detail Harvey wants. Its fictional features are not evidence that Synzo must implement those features before documenting its server. Unsupported capabilities should be marked as such; any Harvey requirement for additional functionality should be resolved separately.

## 1. Evidence and findings from this review

| Source | How to use it |
|---|---|
| [Existing Harvey technical documentation](Synzo-Harvey-Technical-Documentation.md) | Primary narrative source: service, authentication, six tools, operations, data handling, and evaluation access. |
| [Harvey form preparation](../../HARVEY_SUBMISSION_FORM_FILL.md) | Align provider identity, product positioning, integration scope, and disclosures with the Harvey submission materials. It explicitly says the exact entered answers were not independently captured. |
| [Tool-definition snapshot](Synzo-MCP-Tool-Definitions.json) | Exact tool names, titles, descriptions, input schemas, defaults, and annotations. |
| [MCP routes](../../mcp_routes.py) and [tool implementation](../../mcp_tools.py) | Authoritative local behavior for protocol handling, discovery, return envelopes, and tool handlers. |
| [Authentication](../../auth.py), [dashboard controls](../../auth_routes.py), [blob storage](../../blob_store.py), and [URL fetcher](../../url_fetcher.py) | Evidence for authorization, quotas, file access, retention, and network restrictions. |
| [Harvey evaluation record](../../HARVEY_EVALUATION_PROVISIONING.md) | Dated evidence of provisioned identities and authenticated service checks. |
| [General submission record](../../SUBMISSION_RECORD.md) | Historical Anthropic submission, not the Harvey submission. Preserve it as historical evidence. |
| [README](../../README.md) and [original submission plan](../../MCP_SUBMISSION_PLAN.md) | Background only where consistent with current code. The README still describes five tools and older base64 processing inputs/outputs. |

Public, unauthenticated checks performed on October 5, 2026:

- `initialize` returned HTTP 200, server name `synzo`, server version `0.1.0`, protocol `2025-06-18`, and `tools.listChanged: false`.
- `tools/list` returned HTTP 200 and six descriptors exactly matching the saved Harvey JSON snapshot. None publishes an `outputSchema`.
- Both OAuth discovery endpoints returned HTTP 200. Authorization metadata advertises PKCE `S256`, identity scopes, DCR, and token endpoint authentication methods `none`, `client_secret_post`, and `client_secret_basic`.
- Metadata advertises authorization-code, refresh-token, and device-code grants. Discovery alone does not establish that each flow works with Harvey.

This review did not execute authenticated processing calls, inspect private provider settings, or rerun the application test suite. The September 10 six-tool checks remain historical evidence, not a fresh execution result. No source implementation or original Word document was changed.

## 2. Map the example to the completed document

| Example section | Synzo content to write | Evidence or remaining work |
|---|---|---|
| Cover and Introduction | **Synzo MCP Server Specification**; Red Maple Research; Paul O'Hagan; actual revision date. Explain processing of caller-supplied documents/images, five processing capabilities plus one upload helper, and organization-level metering. | Existing Harvey document and form. Remove fictional ACME branding, example-only notice, and the claim that the connector is free to all customers. |
| Endpoint | URL `https://www.synzo.ai/mcp`; HTTPS; JSON-RPC 2.0; Streamable HTTP with JSON responses; server name `synzo`; current version `0.1.0`; preferred protocol `2025-06-18`, also accepting `2025-03-26`. | Live initialization and `mcp_routes.py`. Separate server version, protocol revision, and JSON-RPC version. Do not copy the example's inconsistent MCP 2.0/2.1 or fictional revision. |
| Authentication | WorkOS OAuth bearer JWTs and organization-scoped API keys. Describe anonymous initialization/discovery, authenticated execution, discovery URLs, JWT validation, organization resolution, and the 401 challenge. | `auth.py`, `mcp_routes.py`, live metadata. Add a short connection sequence. |
| Authentication / Scopes | List `openid`, `profile`, `email`, and `offline_access` as advertised identity scopes. State that Synzo has no custom per-tool scope enforcement or scope-filtered tool catalog. | All six tools use the common authentication/metering path. Do not invent a mandatory `synzo_mcp` scope. |
| Authentication / Token Security | Table for access tokens, refresh tokens, relevant email verification/setup tokens, and API keys. Separate provider-managed token lifetime from Synzo's API-key revocation behavior. | Access/refresh/email token lifetimes require confirmation from the deployed WorkOS configuration. API keys have no implemented time-based expiry check and remain usable until revoked, subject to a valid organization and request limits. |
| MCP Features | Tools: yes. Input schemas: yes. Output schemas: no. Structured results: yes. Resources and prompts: no. No persistent SSE stream, session IDs, or server tool-list change notifications. | Route implementation and live descriptors. Describe supported behavior without claiming blanket protocol conformance. |
| Tool Catalog | Six rows, one for every exact machine name below, with title, purpose, supported input, result form, and access requirement. | Live descriptors and handlers. Replace all seven fictional ACME tools. |
| Reference | Six dedicated references using the same subsections: summary, description, access/scopes, typed arguments, typed results, limits/effects, and request/response examples. | Expand existing Harvey Section 4; use the concrete checklist below. |
| Revision History | Initial Synzo specification revision and preparation date; optionally mention the September 10 source package as a predecessor. | Do not carry over ACME's revision history or imply the document revision changes the running server version. |

Add two short appendices: **Operational limits and errors** and **Data handling and evaluation access**. These preserve useful material from the existing Harvey package that the example does not fully cover.

## 3. Build the six tool reference pages

Use the template's four-column argument/result tables: **Name | Type | Required/presence and limits | Description**. List every field, including nested image-analysis fields. Distinguish a field that is always included from one whose value can be null or empty.

| Tool | Arguments | Successful result fields | Details to make explicit |
|---|---|---|---|
| `upload_file` | Required strings: `filename`, `content_base64`. | `filename`, `content_url`, `expires_at`, `size_bytes`, `content_type`. | Decoded file cap 10,485,760 bytes; stores a temporary copy; returns a bearer-access URL. Upload itself does not enforce the processing tools' extension/signature checks. Plan-based unit admission can reject an upload below the absolute size cap. |
| `summarize_document` | Required strings: `filename`, `content_url`. | `classification`, `summary`, `filename`. | PDF/DOCX/PPTX/XLSX. `classification` may be null; summary is Markdown. Sends extracted text to Gemini. Document any extraction limitations; do not imply OCR of every scanned PDF. |
| `translate_document` | Required strings: `filename`, `content_url`, `target_language`. | `filename`, `target_language`, `translated_text`. | DOCX/PPTX/XLSX. Target language is advertised as 2–64 characters. Returns Markdown text, not a translated Office file. Explain provider safety-filter failures. |
| `redact_pii` | Required strings: `filename`, `content_url`. | `filename`, `result_url`, `expires_at`, `mimetype`, `original_size_bytes`, `redacted_size_bytes`. | DOCX/PPTX. Creates a new copy in the original format using local Presidio/spaCy. Describe supported document structures and limitations without guaranteeing complete anonymization. |
| `analyze_image` | Required strings: `filename`, `content_url`. | `filename`, `analysis`, `dominant_colors`. | JPG/JPEG/PNG/WEBP/HEIC/HEIF. Document expected descriptions, OCR text, detected-object strings, and nested safety flags. These are model-generated fields without strict output-schema validation. |
| `detect_faces` | Required strings: `filename`, `content_url`; optional `mode` string and `blur_strength` integer. | `filename`, `mode`, `result_url`, `expires_at`, `mimetype`. | Same image formats. `mode`: `blur` default or `redact`. Strength: 1/2/3, default 2; ignored in redact mode. Returns PNG. No face-count or bounding-box fields are returned. No detected faces can leave the visual content unobscured. |

For all processing tools, document the HTTPS URL requirement, supported file signatures, 10,485,760-byte input cap, and fetch behavior. The server does not forward the caller's authentication headers or cookies to the source URL. A source requiring those credentials needs a separately fetchable URL or the upload workflow.

For all six tools, specify:

- **Authorization:** a valid organization-scoped principal; no separate tool-specific scope. Dashboard membership/role controls are separate from MCP tool execution.
- **Success envelope:** `result.isError = false`, `result.structuredContent` containing the payload, and `result.content` containing the same payload serialized as a JSON text block.
- **Errors:** distinguish tool results with `isError: true` from JSON-RPC errors and HTTP transport failures. Give one representative failure for each tool.
- **Side effects:** successful calls consume organization quota. Upload and binary-result tools create temporary files/URLs. Repeated calls can consume additional quota and return different generated text or new URLs.
- **Limits:** specify actual bounds only. Where filenames, generated text, or object counts have no explicit enforced application limit, say so rather than copying fictional limits from the example.

Provide a complete synthetic request and success response for each tool, with placeholders for credentials and private URLs. Include one upload-to-processing sequence and one binary-result download sequence. Label examples illustrative unless they are captured from a dated verification run.

## 4. Close the factual gaps before final wording

| Priority | Issue | Action and drafting treatment |
|---|---|---|
| Required for a precise Token Security section | WorkOS access-token, refresh-token, and relevant verification-token TTLs are not established by the repo or discovery. | Check deployed WorkOS settings and applicable provider documentation. Record TTL, refresh/rotation behavior, and revocation behavior with evidence. Keep fields explicitly unverified if that evidence is unavailable. The example's 1-hour/30-day values must not be reused. |
| Required to describe Harvey onboarding as verified | Harvey client authentication and Origin behavior remain unverified in the records. | Establish expected client registration, token authentication method, redirect URIs, organization claim/audience behavior, and whether an Origin header is sent. Run an end-to-end Harvey flow before claiming compatibility. The source allowlist currently has no Harvey origin. |
| Confirm intended deployment identity | Live metadata uses `real-vine-49-staging.authkit.app`. | Confirm whether this is the intended authorization environment for the submitted connector. Record actual public endpoint metadata; do not infer production identity-provider configuration from the hostname. |
| Required for honest argument restrictions | Input schemas advertise `additionalProperties: false` and language length bounds, but the MCP dispatcher does not run general JSON Schema validation. | Label schema constraints as the advertised client contract and describe implemented handler checks separately. If strict enforcement is wanted, treat that as a code change with focused tests before updating the claim. |
| Required for honest return types | No published output schemas; image-analysis JSON is parsed without validating its full nested structure. | Provide descriptive return tables now. Mark nested analysis structure as expected, not guaranteed. Adding validated `outputSchema` support is a separate enhancement if Harvey requires it. |
| Required for accurate access/retention description | Temporary URLs authorize downloads by possession; blobs have no organization ownership check. | State this in both common controls and URL-producing tools. One-hour link expiry is not guaranteed physical deletion at exactly one hour; cleanup is lazy and restart can remove files sooner. |
| Required for accurate advertised limits | Upload sizing uses a base64-length unit estimate against plan caps; processing URL calls use one nominal unit. | Document the additional upload admission limit and distinguish unit accounting from actual page count and the one-call monthly quota decrement. Avoid saying every plan accepts every 10 MB upload. |
| Integration review | Processing tools advertise `openWorldHint: false` despite external URL fetching; three use Gemini. Idempotence hints do not guarantee identical outputs or no further quota consumption. | Describe actual network and repeat-call behavior. Review metadata corrections separately and refresh the descriptor attachment if code changes. |
| Confirm only if making these assurances | Processing regions, provider retention/training terms, and automated enforcement of the published 90-day usage retention are not established here. | Reuse the existing qualified disclosures. Obtain deployed/provider evidence before making stronger claims. Keep MCP in-memory storage distinct from the public UI's object-storage path. |
| Refresh dated evaluation details | September records show five provisioned users and six passing API-key checks, with email verification/OAuth pending. | Present those as September 10 evidence. Verify current account readiness and October quota if reporting current status; do not reuse September's 9,994 balance as today's balance. |

Most of these issues do not prevent drafting the specification. Unsupported features can be documented directly. Provider-controlled facts and unperformed client checks must remain clearly identified until verified.

## 5. Complete the appendices

**Operational limits and errors:** consolidate the default 60-second caller-facing tool deadline, 30-second URL-fetch deadline, three-redirect cap, file-size limits, plan quotas, per-organization rates, and endpoint IP limits. State that a timed-out worker may continue running. Explain that upload plus processing costs two successful calls. Document codes `-32001` through `-32005`, applicable standard JSON-RPC errors, and HTTP 401/403/405/413/429 behavior; application body-size limits should be reconciled with the route's separate guard before publishing a single transport maximum.

**Data handling and controls:** include a compact flow showing client → Synzo → Gemini for summarization/translation/image analysis; local processing for redaction/face obscuring; process-memory storage for uploaded/generated files; WorkOS for identity; and Postgres for account/usage metadata. Explain organization scoping and the bearer-URL exception. Do not import the example's ethical walls, user-owned document repository, malware scanning, or per-tool administrator switches.

**Evaluation access:** reuse the dedicated Harvey organization and five account identities, login/reset instructions, September–November allocation, and accurately dated verification status. Keep all credentials and usable private links out of the specification.

## 6. Execution order and acceptance criteria

1. Create a new working document named `Synzo-MCP-Server-Specification.docx`, preserving the original example. Reuse its headings/table style; remove all fictional content, including tables embedded in Word content controls.
2. Populate cover, introduction, endpoint, features, and six-tool catalog from the verified evidence above.
3. Write authentication and controls, including an explicit evidence-needed list for provider settings and Harvey client validation. Resolve those facts when available.
4. Expand the six references into typed argument/result tables and complete synthetic examples. Add the operational/data-handling appendices and revision history.
5. Check each statement against live descriptors, handlers, or provider evidence. Preserve the distinction between current behavior, historical test results, advertised metadata, and proposed enhancements.
6. Render and inspect the Word document and PDF: readable tables, repeated header rows, sensible page breaks, working links, consistent terminology, and no leftover ACME tools/scopes/names. Check document properties, comments, headers, and footers as well as visible body text.
7. Deliver the Word file, a matching PDF, and the machine-readable tool-definition attachment, with matching versions and explicit evidence dates.

For documentation-only completion, validation should focus on schema/example consistency and document rendering. If implementation changes are made, run the affected existing tests in `test_mcp_server.py`, `test_oauth_resolver.py`, `test_auth_failures.py`, `test_multi_tenant_isolation.py`, `test_blob_store.py`, or `test_url_fetcher.py` as appropriate. A live synthetic six-tool check can supply current execution examples, but it must be reported separately from discovery and from end-to-end Harvey OAuth validation.

The document is ready to hand over when all six tools have complete references, every example section is replaced or explicitly marked unsupported, unresolved provider facts are visible, and no statement presents a proposed feature or historical check as current verified behavior.

Planned output location: `docs/harvey/`. This plan prepares the specification; sending it to Harvey is a separate action.
