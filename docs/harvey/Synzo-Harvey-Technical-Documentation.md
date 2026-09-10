# Synzo
## MCP connector technical documentation

**Prepared for Harvey Partnerships, Product Security, and Trust teams**\
**September 10, 2026 | Server version 0.1.0**

Provider: Red Maple Research\
Primary and technical contact: Paul O'Hagan, Principal\
Email: paul@redmapleresearch.ca\
Organization: https://redmapleresearch.ca/

This document describes the six MCP tools submitted for review, their data flows, and evaluation access. It reflects the inspected implementation and the September 10, 2026 live verification. Organization-level tool execution has been verified. End-to-end authentication from Harvey and reviewer email verification remain pending. No passwords, API keys, OAuth tokens, or private download links are included.

## 1. Service and integration

| Item | Value |
|---|---|
| Connector name | Synzo |
| MCP endpoint | https://www.synzo.ai/mcp |
| Public documentation | https://www.synzo.ai/docs |
| Server version | 0.1.0 |
| Preferred MCP protocol | 2025-06-18; 2025-03-26 is also accepted |
| Transport | Streamable HTTP, JSON-RPC over HTTP POST, JSON responses |
| Capabilities | Tools; no MCP resources, prompts, roots, or sampling surface |
| Authentication | OAuth bearer tokens through WorkOS AuthKit; organization-scoped API keys are also accepted |

Use `Content-Type: application/json` and `Accept: application/json, text/event-stream`. The server returns JSON, does not create an MCP session ID, and does not provide a persistent server-initiated SSE stream. GET and DELETE on `/mcp` return 405. Initialize, ping, and tool discovery are available without authentication; tool execution requires authentication. Unknown tools are rejected.

**OAuth discovery**

- Protected resource: https://www.synzo.ai/.well-known/oauth-protected-resource
- Authorization server metadata: https://www.synzo.ai/.well-known/oauth-authorization-server

The live metadata advertises Authorization Code with PKCE S256, refresh tokens, and a Dynamic Client Registration endpoint. Identity scopes advertised include `openid`, `profile`, `email`, and `offline_access`; the server does not implement separate authorization scopes for each tool. API keys are accepted in `Authorization: Bearer <key>` or `X-API-Key`; OAuth tokens use the Bearer header.

The implementation validates signed OAuth tokens against its configured issuer and audience and requires a provisioned WorkOS organization claim. This is separate from restricting which Synzo organization a particular Harvey workspace may use; that customer-to-workspace restriction is not currently implemented.

Browser requests with an `Origin` header are checked against an explicit allowlist. Harvey origins are not currently configured. If Harvey sends an Origin header, the expected origin must be agreed and configured during onboarding. Requests without an Origin header are accepted subject to authentication and other controls.

## 2. Evaluation access

A dedicated **Harvey Connector Evaluation** organization is available on the hosted Synzo service. It has five provisioned accounts with active WorkOS memberships and corresponding Synzo memberships, each with the member role:

- connector_eval1@harvey.ai
- connector_eval2@harvey.ai
- connector_eval3@harvey.ai
- connector_eval4@harvey.ai
- connector_eval5@harvey.ai

**Access steps**

1. Visit https://www.synzo.ai/auth/login and complete password setup for a provisioned address. WorkOS accepted password-setup requests for all five accounts. If the setup link has expired, use **Forgot password** to request a fresh link.
2. Complete email verification and sign in. Choose **Harvey Connector Evaluation** if prompted to select an organization.
3. Configure the MCP endpoint `https://www.synzo.ai/mcp` in the evaluating client and complete OAuth authorization with the evaluation account.
4. Discover and enable the six tools described below. Use the public sample files or synthetic evaluation documents.

The shared quota is **10,000 calls per calendar month for September-November 2026**. September's balance was **9,994** immediately after the six service checks. Contact paul@redmapleresearch.ca for additional quota or a later evaluation window.

All five password-authentication checks returned `email_verification_required`. Email requirements were not bypassed; recipient completion and mailbox delivery were not independently verified. All six tools passed live checks using a temporary API key scoped to this evaluation organization. The key was revoked afterwards. These checks do not constitute completed per-user OAuth testing from Harvey.

## 3. Common tool contract

All five content-processing tools accept a required `filename` and `content_url`. The filename identifies the supported file format. The HTTPS URL must be fetchable by Synzo without forwarding the caller's OAuth token, API key, or cookies. A public or suitably scoped temporary URL can be used. The `upload_file` helper accepts local file bytes and returns a Synzo URL for subsequent calls.

The maximum decoded input is **10 MB (10,485,760 bytes)**. URL fetching enforces HTTPS, rejects non-public destination IPs, pins connections to validated IPs, revalidates redirects, caps redirects at three, and applies a 30-second overall fetch deadline. Each tool call also passes through organization authentication, quota, and rate-limit checks.

Each input schema advertises `additionalProperties: false`. The accompanying **Synzo-MCP-Tool-Definitions.json** contains the server's machine-readable descriptors and input schemas captured from live discovery.

Successful tool responses contain `isError: false`, a `structuredContent` object, and a text content block containing the same object serialized as JSON. Validation or execution errors may instead return `isError: true` with explanatory text. Protocol, authentication, quota, rate, and timeout errors use JSON-RPC error envelopes.

Example request:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "summarize_document",
    "arguments": {
      "filename": "summarize-sample.pdf",
      "content_url": "https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf"
    }
  }
}
```

The connector creates new results and copies; it does not expose tools to overwrite or delete source files, send messages or emails, or administer external systems. Uploads and generated binary results create temporary sharing links. All six tools consume organization quota; failed executions are refunded by the metering pipeline.

## 4. Tool reference

### 4.1 upload_file — Upload a file for use by other Synzo tools

**Purpose:** Stage a local file once and receive a temporary HTTPS URL that other Synzo tools can use.

| Input | Type and requirement | Meaning |
|---|---|---|
| `filename` | String, required | Original filename including extension; used to infer content type. |
| `content_base64` | String, required | Base64-encoded file bytes, no more than 10 MB after decoding. |

**Processing and effects:** Decodes and stores the bytes in the Synzo process-local blob store. This tool does not itself invoke an AI model. It creates a new temporary file URL and consumes one metered call. Downstream tools independently check supported formats and file signatures.

**Output fields:** `filename`, `content_url`, `expires_at` (UTC timestamp), `size_bytes`, `content_type`.

**Access behavior:** Anyone holding the returned URL can retrieve the file until its one-hour expiry; a separate sign-in is not required. See retention and isolation details in Section 6.

### 4.2 summarize_document — Summarize a document

**Purpose:** Extract text, infer the document type, and generate a structured Markdown summary.

| Input | Type and requirement | Meaning |
|---|---|---|
| `filename` | String, required | PDF, DOCX, PPTX, or XLSX filename. |
| `content_url` | HTTPS URI string, required | Location of the document; maximum 10 MB. |

**Processing and effects:** Fetches the supplied document, extracts its text, and sends the text to Google Gemini for classification and summarization. It returns generated information without creating a downloadable binary artifact or modifying the source file.

**Output fields:** `classification` (inferred document type, potentially null if unavailable), `summary` (Markdown string), `filename`.

**Example prompt:** Use Synzo to summarize https://www.synzo.ai/static/reviewer-samples/summarize-sample.pdf and return its classification and summary.

### 4.3 translate_document — Translate a document

**Purpose:** Translate extracted document text into a requested language.

| Input | Type and requirement | Meaning |
|---|---|---|
| `filename` | String, required | DOCX, PPTX, or XLSX filename. |
| `content_url` | HTTPS URI string, required | Location of the document; maximum 10 MB. |
| `target_language` | String, required | English language name, such as French or Spanish; schema length 2-64 characters. |

**Processing and effects:** Fetches the document, extracts text, and sends it to Google Gemini for translation. The tool returns Markdown text, not a translated Office file. The source is not overwritten. PDF input is not supported by this tool.

**Output fields:** `filename`, `target_language`, `translated_text`.

**Example prompt:** Use Synzo to translate https://www.synzo.ai/static/reviewer-samples/translate-sample.docx into French.

### 4.4 redact_pii — Redact PII from a document

**Purpose:** Detect personally identifiable information in supported document text and produce a redacted copy.

| Input | Type and requirement | Meaning |
|---|---|---|
| `filename` | String, required | DOCX or PPTX filename. |
| `content_url` | HTTPS URI string, required | Location of the document; maximum 10 MB. |

**Processing and effects:** Fetches the file and runs Microsoft Presidio/spaCy within Synzo's service. Detected text characters are replaced with block symbols in a new copy. The handler does not send the file to Google Gemini or Microsoft. The result keeps the source file format and is stored temporarily for download. PDF input is not supported.

**Output fields:** `filename`, `result_url`, `expires_at`, `mimetype`, `original_size_bytes`, `redacted_size_bytes`.

**Limits:** Detection is probabilistic and depends on the configured recognizers and supported document structures. Results require review before disclosure; the tool does not guarantee complete anonymization of every part of a document.

**Example prompt:** Use Synzo to redact PII from https://www.synzo.ai/static/reviewer-samples/redact-sample.docx and return the download link.

### 4.5 analyze_image — Analyze an image

**Purpose:** Describe an image, extract visible text, flag potentially sensitive content, and identify objects and dominant colors.

| Input | Type and requirement | Meaning |
|---|---|---|
| `filename` | String, required | JPG/JPEG, PNG, WEBP, HEIC, or HEIF filename. |
| `content_url` | HTTPS URI string, required | Location of the image; maximum 10 MB. |

**Processing and effects:** Fetches the image, sends it to Google Gemini vision, and computes a dominant-color palette locally. Returns structured information without modifying the source image.

**Output fields:** `filename`, `analysis`, `dominant_colors` (list of hexadecimal color strings).

The requested `analysis` structure contains `description`, `rich_description`, `extracted_text`, `detected_objects`, and `safety_flags`. Safety flags include `contains_people`, `contains_potential_pii`, and `is_graphic_or_violent`. The analysis is model-generated and must be treated as potentially incomplete or inaccurate.

**Example prompt:** Use Synzo to analyze https://www.synzo.ai/static/reviewer-samples/analyze-sample.jpg and report the scene, visible text, and potential sensitive content.

### 4.6 detect_faces — Detect and obscure faces in an image

**Purpose:** Locate faces and generate a PNG in which detected faces are blurred or covered.

| Input | Type and requirement | Meaning |
|---|---|---|
| `filename` | String, required | JPG/JPEG, PNG, WEBP, HEIC, or HEIF filename. |
| `content_url` | HTTPS URI string, required | Location of the image; maximum 10 MB. |
| `mode` | String, optional | `blur` (default) or `redact`. Redact uses opaque rectangles. |
| `blur_strength` | Integer, optional | 1 = light; 2 = strong (default); 3 = opaque. Ignored in redact mode. |

**Processing and effects:** Fetches and normalizes the image; MTCNN/OpenCV run within Synzo to locate and obscure faces. This handler does not call a third-party AI API. It creates a new PNG and a temporary download URL. Detection does not identify named individuals. If no faces are detected, the returned PNG may show the original visual content.

**Output fields:** `filename`, `mode`, `result_url`, `expires_at`, `mimetype` (`image/png`).

**Example prompt:** Use Synzo to obscure faces in https://www.synzo.ai/static/reviewer-samples/detect-faces-sample.jpg using redact mode, and return the download link.

## 5. Operational limits and errors

| Limit | Scope |
|---|---|
| 30 HTTP requests/minute and 200/hour | Per source IP on the MCP endpoint, including initialization/discovery. |
| Free: 10; Starter: 60; Pro: 300 tool calls/minute | Per organization, shared across its users and tools. |
| Free: 50; Starter: 10,000; Pro: 100,000 calls/month | Organization plan quota. Evaluation allocation is described in Section 2. |
| 10 MB decoded input | Each uploaded or fetched file. |
| 60-second default tool timeout | Caller-facing tool-execution deadline. A downstream worker may continue until its operation unblocks. |
| 30-second fetch deadline, 3 redirects | Fetch of a supplied content URL. |
| 1-hour link lifetime | Uploads and generated binary results. |

All applicable limits must be observed; the IP cap still applies to organizations with a higher plan rate. On HTTP 429, honor `Retry-After` when present. The organization rate limit can also appear as a JSON-RPC error without HTTP 429. The implementation uses in-process rate buckets and a process-local file store; it does not claim a distributed file store or distributed rate enforcement.

| JSON-RPC code | Meaning |
|---|---|
| `-32001` | Missing or invalid authentication; HTTP 401 advertises OAuth resource metadata. |
| `-32002` | Organization quota exhausted. |
| `-32003` | Organization rate limit exceeded. |
| `-32004` | Request exceeds the plan's per-call unit limit. |
| `-32005` | Tool timeout. |
| `-32600`, `-32601`, `-32602`, `-32700` | Invalid request, unknown method/tool, invalid parameters, or JSON parse error. |

The public support commitment is a response within two business days at https://www.synzo.ai/support. No formal uptime SLA or operational status page is currently published.

## 6. Data handling, isolation, and review boundaries

### Processing and providers

| Component | Role and data received |
|---|---|
| Synzo on Railway | Application processing, temporary MCP file storage in memory, and Postgres account/usage metadata. |
| Google Gemini | Document text for summarization/translation; image content for image analysis. |
| WorkOS AuthKit | Identity, credentials, OAuth tokens, organization membership, and account setup. |
| Presidio/spaCy and MTCNN/OpenCV | Libraries running in the Synzo service, not remote Microsoft or facial-recognition services. |
| S3-compatible object storage | Separate public web UI scratch-file path; the submitted MCP binary-result path uses the in-memory blob store. |

HTTPS is used for the MCP endpoint and external service calls. The published privacy policy states that Postgres is encrypted at rest. API keys are stored as SHA-256 hashes. Provider-wide encryption, processing locations, retention, and contractual model-training treatment have not been independently verified in this submission package. The policy identifies US hosting; an exhaustive list of all provider processing locations remains to be confirmed.

### Temporary files and metadata

Uploaded files and binary results are kept in process memory. Link expiry is one hour from creation, independent of the chat or OAuth session. Expired entries are removed when accessed or during a later upload sweep; this is not a guarantee of physical deletion at exactly one hour. A process restart may remove files earlier.

File URLs contain high-entropy unguessable tokens. **Anyone holding the URL can download the file until expiry, without an additional user or organization check.** Links should therefore be handled as access credentials. File objects do not have per-organization ownership checks in the current store.

Account and usage metadata are stored separately in Postgres. The usage ledger records organization, authentication method, tool, units, status, error code, and timestamp rather than document bodies. Diagnostic logs can contain error details and, on some model-output parsing failures, returned model content; this package does not assert content-free logging or zero retention.

The published privacy policy states a 90-day usage-event retention period. The inspected implementation does not demonstrate an automated purge enforcing that period; deployed cleanup and retention alignment remain to be verified. Account deletion requests are handled through the published contact process.

### Organization and identity controls

Account records, memberships, keys, quotas, and usage records are logically scoped by organization in shared infrastructure. Dashboard operations check membership and role. OAuth requires a provisioned WorkOS organization claim. This is application-level isolation, not separate databases or physical infrastructure per customer, and it has the file-URL exception described above.

Customer-admin controls for allowed email domains or identity providers are not currently exposed. SSO-only access is not enforced; self-service accounts/workspaces are supported. The use of WorkOS does not by itself establish per-Harvey-workspace tenant restrictions or prevention of personal accounts.

### Tool metadata and assurance

The accompanying JSON preserves the registry's current tool annotations. Processing tools advertise `openWorldHint: false` even though they fetch caller-supplied HTTPS URLs, and three invoke Gemini. Their descriptions in Section 4 identify the actual network behavior; annotation alignment remains an integration review item. Generated results and temporary links should not be assumed strictly repeatable based solely on an idempotence hint.

No SOC 2 report, ISO 27001 certificate, completed penetration-test summary, or dedicated prompt-injection review is asserted in this package. An existing May 2026 static-analysis/dependency/container report has scope limitations and is not equivalent to those assessments. No separate published DPA or dedicated Trust Center has been identified in the current materials.

## 7. References and contact

- End-user documentation: https://www.synzo.ai/docs
- Terms of Service: https://www.synzo.ai/terms
- Privacy Policy: https://www.synzo.ai/privacy
- Support: https://www.synzo.ai/support
- Security disclosure policy: https://www.synzo.ai/security
- Source repository: https://github.com/pohagan72/AgentShowcase (public, MIT license)
- Technical coordination, access assistance, and evaluation extensions: **paul@redmapleresearch.ca**

Evidence used: live MCP initialization/discovery, the September 10, 2026 provisioning and six-tool verification record, public legal/support pages, and the connector's implementation. The accompanying tool-definition snapshot is intended to make the full submitted tool inventory explicit for Harvey's allowlist review.
