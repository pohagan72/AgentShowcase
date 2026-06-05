"""Encode a file for paste into MCP Inspector's tool-call form.

Inspector expects every MCP tool's binary input as `content_base64` (or
`image_base64` / `audio_base64`, depending on the tool). The form is a plain
textarea, so the typical browser file-picker UX doesn't apply — you have to
paste a literal base64 string.

USAGE:
    python -m scripts.encode_for_inspector path/to/sample.docx

Prints two things:
  1. The filename to paste into the `filename` field.
  2. The base64 string to paste into the `content_base64` (or equivalent) field.

The base64 is written between BEGIN/END markers so you can select-all between
them without accidentally grabbing the size warning text above.

The script aborts if the decoded size exceeds Synzo's 10 MB per-call limit,
so you don't waste a tool call on a payload the server will 413 on.
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

MAX_DECODED_BYTES = 10 * 1024 * 1024  # matches PLANS[plan]["pages_per_call"] gating


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="Path to the file you want to encode.")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: not a file: {path}", file=sys.stderr)
        return 1

    raw = path.read_bytes()
    size_mb = len(raw) / 1024 / 1024
    if len(raw) > MAX_DECODED_BYTES:
        print(
            f"ERROR: file is {size_mb:.2f} MB; Synzo rejects >10 MB per call. "
            f"Pick a smaller file.",
            file=sys.stderr,
        )
        return 1

    encoded = base64.b64encode(raw).decode("ascii")

    print()
    print(f"  filename:        {path.name}")
    print(f"  decoded size:    {size_mb:.2f} MB ({len(raw):,} bytes)")
    print(f"  base64 length:   {len(encoded):,} chars")
    print()
    print("  Paste the filename above into Inspector's `filename` field.")
    print("  Paste the base64 between the markers below into `content_base64`")
    print("  (or `image_base64` / `audio_base64` for image/audio tools).")
    print()
    print("---BEGIN BASE64---")
    print(encoded)
    print("---END BASE64---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
