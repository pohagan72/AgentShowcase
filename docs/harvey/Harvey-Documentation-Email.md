To: partnerships@harvey.ai; prodsec@harvey.ai; trust-team@harvey.ai

Subject: Synzo connector resubmission - direct-upload contract (revision 1.3)

Attachments:
- Synzo-MCP-Server-Specification.docx (revision 1.3, 5 October 2026)
- Synzo-MCP-Tool-Definitions.json

Hello Harvey team,

Following Kaushal's note that the previous submission could not be approved because the processing tools accepted caller-supplied URLs, we have revised the connector to require direct document upload and are resubmitting the integration contract.

The attached specification supersedes the September 2026 Synzo Harvey technical documentation. The September PDF describes the earlier URL-based interface and should be treated as retired.

Summary of what changed on the server:

- The upload_file tool has been removed from the catalog.
- All five processing tools (summarize_document, translate_document, redact_pii, analyze_image, detect_faces) now require the document or image bytes directly as a content_base64 argument.
- The server rejects the legacy content_url argument explicitly, including on requests that also contain valid content_base64. There is no silent fallback.
- The URL-fetch code path has been removed from the server; see the Negative verification table in the specification's Client Operating Guidance section.

Live verification: on 5 October 2026 all five tools were exercised end-to-end against the production endpoint using a temporary API key issued against the Harvey Connector Evaluation organization. The temporary key was revoked after the run. Full per-tool results (HTTP status, isError, latency, output checks) are in Appendix B of the specification.

MCP endpoint: https://www.synzo.ai/mcp
Documentation: https://www.synzo.ai/docs
Evaluation sign-in: https://www.synzo.ai/auth/login

All five requested accounts, connector_eval1@harvey.ai through connector_eval5@harvey.ai, remain provisioned in the Harvey Connector Evaluation organization. The current period's shared allowance is 9,995 of 10,000 calls remaining; the five calls consumed are the verification run itself.

Reviewer email verification/password setup and end-to-end OAuth validation from Harvey remain pending. Reviewers can use Forgot password on the sign-in page if their setup link has expired.

Please contact me for access assistance, any required client configuration, confirmation of the Harvey Origin header value for the allowlist, or an extension to the evaluation window.

Best regards,
Paul O'Hagan
Principal, Red Maple Research
paul@redmapleresearch.ca
https://redmapleresearch.ca/
