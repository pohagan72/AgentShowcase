"""Verify a specific .docx file against the live redact_pii MCP tool.

Used to confirm the reviewer-bundle redact-sample.docx triggers Presidio's
default English recognizers (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, US_SSN,
CREDIT_CARD, US_PASSPORT) end-to-end through the production endpoint.

Reads SYNZO_API_KEY from .env. Posts to /mcp tools/call with the file as
base64. On success, downloads the redacted bytes, extracts paragraph text, and
prints which seeded strings survived (any survivor is a bug in the seed format
or a gap in Presidio's defaults).

Run:
    .venv/Scripts/python -m scripts.verify_redact_sample <path-to-docx>
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

# Force UTF-8 stdout so Windows cp1252 doesn't choke on Presidio's
# block-character replacement (U+2588) when we print the redacted text.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Reuse the live-call helper from the sweep so we hit the endpoint identically.
from scripts import sweep_tools
from scripts.sweep_tools import post_jsonrpc, DEFAULT_BASE_URL
from dotenv import load_dotenv
import os

# Corporate-proxy SSL inspection breaks cert verification on this machine; the
# sweep script supports a --insecure-skip-verify flag for the same reason.
# We're hitting our own production endpoint with a known-good key, not an
# untrusted third party, so this is safe for a one-shot verification.
sweep_tools.INSECURE_SKIP_VERIFY = True
import warnings
import urllib3
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

from docx import Document


# Strings I seeded in build_redact_sample.py. Any survivor in the redacted
# output is something Presidio missed (or my seed format is wrong).
SEEDED_PII = [
    "John Doe",
    "Jane Doe",
    "john.doe@example.com",
    "jane.doe@example.com",
    "(555) 123-4567",
    "(555) 987-6543",
    "211-61-2524",         # SSN — structurally valid; 123-45-6789 is hard-rejected by Presidio as a known test value
    "C12345678",           # US passport (9 alphanumeric)
    "4111-1111-1111-1111", # Visa test card (Luhn-valid)
]


def extract_text(docx_bytes: bytes) -> str:
    doc = Document(io.BytesIO(docx_bytes))
    return "\n".join(p.text for p in doc.paragraphs)


def main(path: Path) -> int:
    load_dotenv()
    api_key = os.environ.get("SYNZO_API_KEY")
    if not api_key:
        print("ERROR: SYNZO_API_KEY not set in .env", file=sys.stderr)
        return 2

    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 2

    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    print(f"Sending {path.name} ({len(raw)} bytes) to {DEFAULT_BASE_URL}/mcp ...")

    resp, elapsed = post_jsonrpc(
        DEFAULT_BASE_URL, api_key, "tools/call",
        {"name": "redact_pii", "arguments": {"filename": path.name, "content_base64": b64}},
    )
    print(f"Response in {elapsed:.2f}s")
    import json as _json
    print(f"Raw response: {_json.dumps(resp, indent=2)[:1500]}")

    if "error" in resp:
        print(f"JSON-RPC error: {resp['error']}", file=sys.stderr)
        return 1

    result = resp.get("result", {})
    if result.get("isError"):
        print(f"Tool returned isError=true: {result.get('content')}", file=sys.stderr)
        return 1

    # Tool returns structured content with content_base64 of the redacted file.
    structured = result.get("structuredContent") or {}
    if not structured:
        # Fall back to content[0].text — MCP servers may return either shape.
        content = result.get("content") or []
        if content and isinstance(content, list):
            import json as _json
            try:
                structured = _json.loads(content[0].get("text", "{}"))
            except Exception:
                pass

    redacted_b64 = structured.get("content_base64")
    if not redacted_b64:
        print(f"No content_base64 in result: {result}", file=sys.stderr)
        return 1

    redacted_bytes = base64.b64decode(redacted_b64)
    print(f"Redacted size: {len(redacted_bytes)} bytes")
    print(f"Reported sizes: orig={structured.get('original_size_bytes')}, "
          f"redacted={structured.get('redacted_size_bytes')}")

    redacted_text = extract_text(redacted_bytes)

    print("\n--- Redacted document text ---")
    print(redacted_text)
    print("--- end ---\n")

    # Survivor check: any seeded PII that's still present in the redacted output
    # means Presidio missed it.
    survivors = [pii for pii in SEEDED_PII if pii in redacted_text]
    if survivors:
        print("FAIL: the following seeded values survived redaction:")
        for s in survivors:
            print(f"  - {s!r}")
        return 1

    print("OK: every seeded PII string was redacted from the output.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: verify_redact_sample.py <path-to-docx>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
