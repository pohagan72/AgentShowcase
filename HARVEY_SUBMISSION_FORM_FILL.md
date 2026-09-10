# Synzo - Harvey Connector Partner form

Harvey has acknowledged receipt of the connector submission. This file contains the prepared answers and implementation notes; the exact values entered in the submitted form were not independently captured. Harvey requested that technical documentation also be emailed to partnerships@harvey.ai, prodsec@harvey.ai, and trust-team@harvey.ai. The documentation package and email draft are in `docs/harvey/`; email delivery has not been performed by the assistant.

## Organization and contacts

| Field | Answer |
|---|---|
| Organization name | Red Maple Research |
| Organization URL | https://redmapleresearch.ca/ |
| First name of primary contact | Paul |
| Last name of primary contact | O'Hagan |
| Email of primary contact | paul@redmapleresearch.ca |
| Title of primary contact | Principal |
| Harvey contact (if known) | Leave blank unless you have a named contact. |
| Email of technical contact to request dev accounts | paul@redmapleresearch.ca |
| Connector name | Synzo |

## Short description

Synzo helps legal teams summarize and translate documents, analyze images, and redact personal information from supported documents and photos.

## Long description

Synzo brings document and image intelligence to legal workflows, helping teams review materials, work across languages, and prepare copies for sharing. Its MCP connector provides tools to classify and summarize PDF and Office documents; translate text from Word, PowerPoint, and Excel files; detect and redact personally identifiable information in Word and PowerPoint files; analyze images for descriptions, visible text, objects, and potential sensitive content; and blur or obscure detected faces in photos.

Teams can use these capabilities to prepare summaries for matter review, understand foreign-language materials, examine visual exhibits, and reduce exposure of personal information before sharing documents or images. Files can be supplied through HTTPS URLs or uploaded using the connector's file-upload tool. Summaries and translations return as Markdown, while redacted documents and processed images are available through temporary download links. Supported files can be up to 10 MB. Automated results should be reviewed before use or disclosure.

## Required links

| Field | Answer |
|---|---|
| Detailed descriptions of every MCP tool call | https://www.synzo.ai/docs#available-tools |
| Connector information for end users | https://www.synzo.ai/ |
| MCP Server URL | https://www.synzo.ai/mcp |

## Tool coverage for Harvey's review

The public documentation lists all six tools currently advertised by the live server. Include all six in the requested integration scope, including the upload helper.

| Exact tool name | What it does |
|---|---|
| `upload_file` | Accepts a filename and base64 file bytes, up to 10 MB decoded; returns a temporary HTTPS `content_url` for use by other tools. The advertised expiry is one hour. |
| `summarize_document` | Accepts a filename and HTTPS `content_url` for a PDF, DOCX, PPTX, or XLSX file; returns an inferred document type and a structured Markdown summary. |
| `translate_document` | Accepts a filename, HTTPS `content_url`, and `target_language` for a DOCX, PPTX, or XLSX file; returns translated text as Markdown. |
| `redact_pii` | Accepts a filename and HTTPS `content_url` for a DOCX or PPTX file; detects PII using Microsoft Presidio and returns a temporary `result_url` for a redacted copy in the original file format. |
| `analyze_image` | Accepts a filename and HTTPS `content_url` for a JPG/JPEG, PNG, WEBP, HEIC, or HEIF image; uses Gemini vision to return a description, extracted text, safety flags, detected objects, and dominant colors. |
| `detect_faces` | Accepts a filename and HTTPS `content_url` for a supported image, with optional `mode` (`blur` or `redact`) and `blur_strength` (1, 2, or 3); returns a temporary `result_url` for a PNG with detected faces blurred or obscured. |

All five processing tools advertise a 10 MB input limit. Tool calls require authentication; anonymous tool discovery is available.

## Verification and integration notes

- The organization website, Synzo homepage, public docs, privacy page, and security page returned HTTP 200 during preparation.
- An anonymous POST to `https://www.synzo.ai/mcp` using `tools/list` returned the six tools above; each exact tool name also appears on the live documentation page.
- This check verifies reachability and advertised capabilities. It does not establish successful authenticated execution from Harvey.
- The implementation supports API-key and OAuth authentication. Harvey-specific authentication and client compatibility remain to be validated during onboarding.
- The current source has an explicit browser Origin allowlist in `mcp_routes.py`; it does not include Harvey origins. If Harvey sends an Origin header, the appropriate origin will need to be configured as part of onboarding.
- Summarization, translation, and image analysis use Google Gemini. Avoid adding unverified claims about certifications, data residency, model-training exclusions, or guaranteed anonymization to the listing.

Sources: live `/mcp` tool discovery, live `/docs`, and local `mcp_tools.py` / `mcp_routes.py`.

## Second form page - agreements, data handling, and distribution

| Field | Answer |
|---|---|
| MCP version | `0.1.0` (server version returned by the live `initialize` response). |
| Countries or regions where data is processed or stored | Incomplete: the published privacy policy identifies the United States for Synzo hosting. Confirm the actual application/database region and the processing/storage locations applicable to Google Gemini, WorkOS, and the object-storage provider before submitting the complete list. Do not use "All allowed regions" as a substitute for locations. |
| User/customer agreement(s), including any DPA | https://www.synzo.ai/terms |
| Maintained privacy policy | https://www.synzo.ai/privacy |
| Support contact | paul@redmapleresearch.ca (or https://www.synzo.ai/support). |
| How do you handle data? | Select **is retained** from the supplied options. |
| Publish and distribute outside your organization? | **Yes**, consistent with applying for public distribution to Harvey customers. This permits publication in all Harvey customer workspaces if approved. |

### Version clarification

`0.1.0` is the connector/server version. The live server also negotiates MCP protocol version `2025-06-18`; these are separate version identifiers.

### Agreement status

The terms, privacy, and support pages returned HTTP 200. No separate DPA was found in the repository or linked submission materials; the existing submission template explicitly records that one was not yet available. The Terms of Service link should not be described as a DPA. If the form accepts explanatory text, use: "Terms of Service: https://www.synzo.ai/terms. No separate DPA is currently published."

### Data-handling explanation

Synzo processes user-supplied documents and images to perform the requested tool calls. Uploaded files and generated binary outputs are held temporarily in process memory and exposed through links that expire after one hour. Expired entries are removed when accessed or during a subsequent upload sweep; link expiry is not a guarantee of physical deletion at exactly one hour. Account and usage metadata are stored separately. Summarization, translation, and image analysis send content to Google Gemini; PII redaction and face detection run within the Synzo service.

Given the supplied choices ("not retained", "is retained", "is not used to train models"), **is retained** describes the implemented storage behavior. If multiple choices are allowed, confirm the applicable Gemini account/service terms before also selecting the no-training option. Synzo's published Terms of Service prohibit model training, but that policy statement alone does not verify the downstream provider's contractual treatment.

### Region information still needed

The published United States hosting statement does not establish an exhaustive list of all processing locations. Google Gemini is configured through its API key without a region setting in the inspected application code. Confirm provider locations from the deployed service settings and applicable provider agreements, including object storage used by the public web application. Do not infer Canada from the organization's address or Ontario governing law, and do not assert United States-only processing without provider confirmation.

## Third form page - MCP capabilities and user actions

### Capabilities dropdown

Select **read & write** from the supplied choices (`read only`, `write only`, `read & write`). The connector fetches files, creates stored copies, and creates temporary download links.

### All tools (comma-separated, ready to paste)

```text
[upload_file] (Upload a file for use by other Synzo tools), [summarize_document] (Summarize a document), [translate_document] (Translate a document), [redact_pii] (Redact PII from a document), [analyze_image] (Analyze an image), [detect_faces] (Detect and obscure faces in an image)
```

These machine-readable names and human-readable titles were checked against the live `tools/list` response.

### User-action checkboxes

| Option | Selection | Reason |
|---|---|---|
| Retrieve user files or information from my platform or other external services | Select | Processing tools fetch files from supplied HTTPS URLs, including Synzo upload URLs. |
| Delete or edit user files or information in my platform or other external services | Leave unchecked | The exposed tools create new processed copies. They do not overwrite or delete existing source files or records. Automatic expiry of temporary files is internal lifecycle management. |
| Create new user files or information in my platform or other external services | Select | Uploads create temporary stored files; redaction and face-obscuring tools create new downloadable documents/images. |
| Send messages or emails on behalf of others | Leave unchecked | None of the six MCP tools sends messages or emails. |
| Create or modify public URLs/sharing links | Select | `upload_file`, `redact_pii`, and `detect_faces` create temporary HTTPS links. Anyone holding the URL can download the file until expiry; a separate login is not required. |
| Connect to external services (including your platform) that can independently create, edit, ... | Recommend selecting based on the wording available | The label supplied remains truncated. Synzo is itself an external platform that creates processed files and sharing links and calls Google Gemini for content generation. This is a disclosure recommendation, not a claim that Synzo autonomously takes actions in unrelated systems. |

## Fourth form page - operations, security, and authentication

### Rate limits (paste)

The MCP endpoint is limited to 30 HTTP requests per minute and 200 per hour per source IP, including initialization and tool discovery. Tool invocations have an additional shared organization-wide limit across tools and users: Free 10 requests/minute, Starter 60 requests/minute, Pro 300 requests/minute. All applicable limits must be honored. Monthly organization quotas are Free 50 calls, Starter 10,000 calls, and Pro 100,000 calls. On HTTP 429, honor Retry-After when present; MCP error -32003 also signals an organization rate limit. File inputs are limited to 10 MB; the default tool timeout is 60 seconds.

Evidence: `extensions.py` and `auth.py`; the live MCP response returned `x-ratelimit-limit: 30`. No separate per-user or per-tool rate bucket is implemented. The production evaluation account plan/quota has not been verified.

### SLA or status page

Existing support URL: https://www.synzo.ai/support

Suggested explanation: "Published support response commitment: within two business days. No formal uptime SLA or public operational status page is currently published."

The support URL is not an operational status page or an uptime guarantee. `/status` and `/sla` returned HTTP 404. If Harvey requires a formal availability SLA or status dashboard specifically, this remains a missing deliverable; do not invent a URL or availability percentage.

### Evaluation account attestations

Provisioned on September 10, 2026 after explicit authorization. All five identities exist in WorkOS, have active memberships in the dedicated **Harvey Connector Evaluation** organization, and have matching Synzo membership records. Each was assigned the member role. Shared quota is 10,000 calls per calendar month for September, October, and November 2026; September has 9,994 calls remaining after verification.

| Required identity | Attestation status |
|---|---|
| connector_eval1@harvey.ai | Provisioned; active member; email verification/password setup pending |
| connector_eval2@harvey.ai | Provisioned; active member; email verification/password setup pending |
| connector_eval3@harvey.ai | Provisioned; active member; email verification/password setup pending |
| connector_eval4@harvey.ai | Provisioned; active member; email verification/password setup pending |
| connector_eval5@harvey.ai | Provisioned; active member; email verification/password setup pending |

WorkOS returned `email_verification_required` for each account's password-authentication check. Password-setup requests were accepted for all five accounts. WorkOS rejects organization invitations for users who are already active members, so the password-reset/setup flow was used instead. Mailbox delivery was not independently verified. Reviewers can visit https://www.synzo.ai/auth/login and use Forgot password to request a fresh setup link if needed. Do not claim that the reviewers have completed email verification or end-to-end OAuth testing.

All six tools passed authenticated live checks using a temporary API key belonging only to the evaluation organization. Redacted DOCX and processed PNG downloads were validated; the synthetic email address was absent from the redacted document. The temporary key was revoked after testing. These checks establish organization-level tool access, not completed per-user OAuth sign-in.

Current accurate attestation: "[email] has been provisioned as an active member of Synzo's dedicated Harvey evaluation organization. Evaluation quota is available and all six tools have passed organization-level authenticated checks. The user must complete email verification/password setup before end-to-end OAuth access can be confirmed."

See [HARVEY_EVALUATION_PROVISIONING.md](HARVEY_EVALUATION_PROVISIONING.md) for the provisioning and verification record.

### Data-handling selections

These statements explicitly cover connected providers as well as Synzo. A published policy is evidence of a commitment, not independent verification of every provider configuration.

| Statement | Recommendation |
|---|---|
| Encrypt user information and data in transit and at rest | Confirm before attesting across the entire chain. HTTPS is implemented and the privacy policy states Postgres encryption at rest. Verify Railway storage/backups, the object-storage configuration, and applicable Google/WorkOS controls. |
| Store user information and data received from Harvey until deleted by users/customers | Do not select as a blanket retention policy: files use temporary expiry, while account/usage metadata have different retention rules. If Harvey means that *any* metadata is retained, explain this distinction. |
| Deletes user information and data received from Harvey following session expiration | Leave unchecked. File link expiry is based on upload/creation time, not OAuth or chat-session termination; metadata is retained separately and expired blobs are removed lazily. |
| Only uses user information and data to provide services used by Harvey users | Synzo's terms commit to this. Confirm the applicable Gemini account/service terms and the other providers' terms before making the same attestation for all connected services. |

The privacy policy says usage events are deleted after 90 days, but no automated purge implementation was found in the inspected code; the model's docstring calls them append-only/never deleted. Do not attest to an enforced 90-day deletion schedule without verifying the deployed cleanup process. No code or policy changes were made during this review.

### Codebase maintenance

- Select **Actively maintained (not archived)**.
- Select **Company/commercially-built project**, consistent with Synzo being offered by Red Maple Research.
- Select **Open-source**: the GitHub API confirms https://github.com/pohagan72/AgentShowcase is public, not archived, and MIT-licensed.
- Select **Single-developer project with no external review** if that describes the human review process. Automated SAST is not external human review; no established external review process was identified in the inspected materials.

### Certifications and security testing

Select **None of the above** based on the evidence currently available. No SOC 2 report, ISO 27001 certificate, shareable penetration-test summary, or dedicated prompt-injection assessment was found. A privacy policy and a previous form's GDPR checkbox do not establish a substantiated GDPR compliance assessment.

`SAST_REPORT.md` documents a May 8, 2026 static-analysis, dependency, and container scan with explicit scope limitations and remaining findings. It is not evidence of the penetration-testing or prompt-injection-review options and should not be represented as a current blanket clean bill of health.

### Trust Center

Leave blank: no dedicated Trust Center was identified. Related security disclosure page, if explanatory text is allowed: https://www.synzo.ai/security (vulnerability reporting policy, not a certification portal).

### Tenant isolation

Select **Row-level or org-level isolation enforced in code** from the supplied choices. This means application-enforced organization checks in shared infrastructure, not separate databases per customer or PostgreSQL row-level security policies. Disclose the temporary-download-link exception below; this is not a claim that every file download requires organization membership.

Explanation to paste if available:

"OAuth tokens require a provisioned WorkOS organization claim, and API keys are associated with one organization. Account records, memberships, API keys, quotas, and usage records are scoped by organization in a shared database. Dashboard access uses membership and role checks. Temporary file storage is shared; download URLs contain unguessable tokens and expire after one hour. Downloads are authorized by possession of the URL, without an additional user or organization check."

### Hosting

Select **Cloud-hosted (submitter manages infra)** for the Synzo application deployment on Railway and its managed Postgres database. Synzo also uses WorkOS AuthKit and Google Gemini as third-party SaaS providers; disclose these separately if the form's hosting selection is intended to include connected providers. No self-hosted/on-premises deployment is being submitted.

### Authentication type, Auth client, and transport

- Authentication type: **OAuth 2.0 / OpenID Connect via WorkOS AuthKit**. Synzo also accepts organization-scoped API keys; include API key if the field allows multiple authentication methods.
- Auth client: **Dynamic Client Registration (DCR)** if that is one of the choices. The live discovery document advertises an AuthKit registration endpoint and Authorization Code with PKCE S256. If the dropdown instead distinguishes public/confidential clients, the exact answer depends on the registered Harvey client's configuration; the discovery metadata advertises multiple token-endpoint authentication methods.
- Transport: **Streamable HTTP** at https://www.synzo.ai/mcp. Requests use HTTP POST and responses are JSON. The server does not provide a persistent server-initiated SSE stream.

The data-isolation dropdown has been mapped to the supplied choices. Exact Authentication type and Auth client dropdown choices are still pending. Live OAuth discovery is reachable; Harvey's authenticated flow has not been tested.

### Identity / anti-exfiltration (paste)

a. OAuth access tokens must include a provisioned WorkOS organization ID, which Synzo uses to scope account, quota, and usage access. Synzo does not currently bind each Harvey customer workspace to an approved Synzo organization; therefore a per-Harvey-customer tenant restriction is not currently configured.

b. Synzo does not currently expose a customer-admin control to allowlist OAuth identity providers or email domains. Customer-specific WorkOS policy configuration and enforcement would need to be established and validated before claiming this capability.

c. SSO-only authentication is not currently enforced in the inspected implementation. The application allows self-service account/workspace creation. WorkOS's SAML/OIDC capabilities do not by themselves establish that personal accounts are blocked from connecting to Synzo.
