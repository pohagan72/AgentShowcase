# Synzo - Harvey evaluation account provisioning

Prepared September 10, 2026. Provisioning is complete; reviewer email verification and end-to-end OAuth sign-in remain pending.

## Evaluation organization

- Name: **Harvey Connector Evaluation**.
- Five dedicated reviewer identities; each has an active WorkOS organization membership and a corresponding Synzo membership with the **member** role.
- Separate organization from existing Synzo customers; tool verification used a synthetic document and the public reviewer image samples.
- Shared evaluation quota: **10,000 calls per calendar month for September-November 2026**. September balance after testing: **9,994**.
- Organization rate limit: **60 tool calls/minute**. The endpoint's **30 requests/minute and 200/hour per source IP** limits still apply.
- Sign-in: https://www.synzo.ai/auth/login
- MCP: https://www.synzo.ai/mcp

## Account status

| Account | Provisioning and membership | Authentication check |
|---|---|---|
| connector_eval1@harvey.ai | Provisioned, active member | Email verification required |
| connector_eval2@harvey.ai | Provisioned, active member | Email verification required |
| connector_eval3@harvey.ai | Provisioned, active member | Email verification required |
| connector_eval4@harvey.ai | Provisioned, active member | Email verification required |
| connector_eval5@harvey.ai | Provisioned, active member | Email verification required |

WorkOS accepted password-reset/setup requests for all five accounts. Password-setup links expire approximately one hour after issue; reviewers can use **Forgot password** from the sign-in page to obtain a fresh link. Mailbox delivery and recipient completion have not been independently verified.

Because these users already have active memberships, WorkOS rejects redundant organization invitations with `user_already_organization_member`. Password setup is the appropriate onboarding path for these provisioned accounts.

Password-authentication requests for every account returned HTTP 403 with `email_verification_required`. Email-verification requirements were not bypassed, and setup/verification tokens were not redeemed on behalf of the recipients. Reviewers must complete that step themselves.

## Live service verification

The following checks used one temporary API key scoped to the evaluation organization. All six calls were recorded with `status=ok` and `auth_method=api_key` in that organization's usage ledger.

| Tool | Result |
|---|---|
| `upload_file` | Passed: synthetic DOCX uploaded and a temporary content URL returned. |
| `summarize_document` | Passed: non-empty summary returned for the synthetic document. |
| `translate_document` | Passed: non-empty French translation returned. |
| `redact_pii` | Passed: redacted DOCX downloaded and opened; the synthetic email address was removed. |
| `analyze_image` | Passed: structured analysis returned for the public reviewer image. |
| `detect_faces` | Passed: processed image downloaded and validated as a PNG. |

The temporary API key was revoked after the checks. A subsequent database check confirmed no active API keys remained in the evaluation organization.

These checks establish that the evaluation organization can execute all six tools. They do **not** establish that each reviewer has completed OAuth sign-in through Harvey.

## Accurate attestation wording

> All five requested accounts have been provisioned as active members of Synzo's dedicated Harvey evaluation organization. Shared evaluation quota is available, and all six tools have passed organization-level authenticated checks. Password setup has been requested for each account. Reviewer email verification and end-to-end OAuth access remain pending.

For a per-account field, replace "All five requested accounts" with the relevant email address and use the singular form.
