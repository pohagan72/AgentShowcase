# Security Policy

This file is the in-repo mirror of the public security disclosure page at
[https://www.synzo.ai/security](https://www.synzo.ai/security). Both exist so
researchers and contributors can find the disclosure process from either the
running product or the source.

## Scope

This policy covers:

- The Synzo MCP server at `https://www.synzo.ai/mcp` (JSON-RPC, OAuth, tools).
- The Synzo JSON API at `https://www.synzo.ai/api/v1/*`.
- The Synzo dashboard at `https://www.synzo.ai/dashboard/*`.
- The Synzo public website at `https://www.synzo.ai`.

Out of scope: vulnerabilities in third-party dependencies (please report
those to the upstream maintainers), social engineering of Synzo users or
staff, and denial-of-service attacks against the running service.

## How to report

Email reports to **paul@redmapleresearch.ca**. This is the address Synzo's
maintainer monitors directly.

Please include:

- A description of the issue and its impact.
- Steps to reproduce (or a proof-of-concept).
- The affected URL, endpoint, tool name, or commit.
- Your preferred name and contact for credit (or "anonymous").

Please do not disclose the issue publicly until we've had a chance to
investigate and ship a fix.

## What to expect

- **Acknowledgement** within 3 business days.
- **Initial assessment** within 7 business days.
- Updates as the fix progresses; coordinated disclosure timing on request.

## Out-of-band paths

If for any reason the email path is unavailable, open a minimal issue in the
private repo (only the maintainer has access) titled "security: please
contact me" — no details — and the maintainer will follow up by email.

## Encryption

PGP is not currently offered. If you need an encrypted channel, mention it
in your initial email and we'll arrange one.
