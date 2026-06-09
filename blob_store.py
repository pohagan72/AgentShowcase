# blob_store.py
# In-memory short-lived blob store backing the `upload_file` MCP tool.
#
# Why this exists:
# Chat clients (claude.ai, Claude Desktop) must construct tool-call arguments
# as LLM output tokens. Inlining a multi-MB base64 payload into every tool
# call (analyze_image, summarize_document, ...) is slow and visibly stalls the
# chat UI. The `upload_file` tool lets the chat client pay the base64 cost
# ONCE per file; subsequent tool calls reference the file by URL.
#
# Design:
# - Tokens are 256-bit url-safe strings (secrets.token_urlsafe(32)).
# - TTL is 1 hour from upload; expired entries are dropped on read AND by a
#   lazy sweep that runs on every put().
# - Total in-flight bytes are capped (BLOB_STORE_MAX_TOTAL_BYTES, default
#   ~100 MB) so a runaway caller can't OOM the replica.
# - Storage is a process-local dict. Single Railway replica only. When we move
#   to multi-replica (Phase 2.5.B), swap this for S3 with presigned URLs.
# - Thread-safe via a single RLock — Waitress runs handlers on many threads.

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass


# Knobs. Read at import time; tests override by reassigning module attributes
# (see tests/test_blob_store.py).
BLOB_STORE_TTL_SECONDS = 60 * 60  # 1h
BLOB_STORE_MAX_TOTAL_BYTES = 100 * 1024 * 1024  # 100 MB across the whole store
BLOB_STORE_MAX_SINGLE_BYTES = 10 * 1024 * 1024  # 10 MB per blob (matches tool caps)


class BlobStoreFull(Exception):
    """Raised when adding a blob would exceed BLOB_STORE_MAX_TOTAL_BYTES."""


class BlobTooLarge(Exception):
    """Raised when a single blob exceeds BLOB_STORE_MAX_SINGLE_BYTES."""


@dataclass(frozen=True)
class BlobEntry:
    token: str
    filename: str
    content_type: str
    data: bytes
    created_at: float  # epoch seconds
    expires_at: float  # epoch seconds


class BlobStore:
    """Process-local TTL blob store. Thread-safe."""

    def __init__(self) -> None:
        self._entries: dict[str, BlobEntry] = {}
        self._total_bytes: int = 0
        self._lock = threading.RLock()

    # --- core ops --------------------------------------------------------

    def put(self, *, filename: str, content_type: str, data: bytes) -> BlobEntry:
        """Store a blob and return the entry (with token + expires_at)."""
        size = len(data)
        if size > BLOB_STORE_MAX_SINGLE_BYTES:
            raise BlobTooLarge(
                f"Blob is {size} bytes; cap is {BLOB_STORE_MAX_SINGLE_BYTES}"
            )

        with self._lock:
            # Lazy sweep before admission so abandoned blobs free up room.
            self._sweep_expired_locked()

            if self._total_bytes + size > BLOB_STORE_MAX_TOTAL_BYTES:
                raise BlobStoreFull(
                    f"Adding {size} bytes would exceed total cap "
                    f"{BLOB_STORE_MAX_TOTAL_BYTES}"
                )

            now = time.time()
            token = secrets.token_urlsafe(32)
            entry = BlobEntry(
                token=token,
                filename=filename,
                content_type=content_type,
                data=data,
                created_at=now,
                expires_at=now + BLOB_STORE_TTL_SECONDS,
            )
            self._entries[token] = entry
            self._total_bytes += size
            return entry

    def get(self, token: str) -> BlobEntry | None:
        """Return the entry for `token`, or None if missing/expired.

        Expired entries are dropped from the store as a side effect.
        """
        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            if entry.expires_at <= time.time():
                self._drop_locked(token)
                return None
            return entry

    def drop(self, token: str) -> bool:
        """Remove a token unconditionally. Returns True if it existed."""
        with self._lock:
            return self._drop_locked(token)

    # --- introspection (used by tests + metrics later) -------------------

    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    # --- internals -------------------------------------------------------

    def _drop_locked(self, token: str) -> bool:
        entry = self._entries.pop(token, None)
        if entry is None:
            return False
        self._total_bytes -= len(entry.data)
        return True

    def _sweep_expired_locked(self) -> int:
        """Remove every expired entry. Returns the count dropped."""
        now = time.time()
        expired = [t for t, e in self._entries.items() if e.expires_at <= now]
        for t in expired:
            self._drop_locked(t)
        return len(expired)


# Module-level singleton. Bind to the Flask app at create_app() time so tests
# can swap in their own. (See app.py initialization.)
_default_store: BlobStore | None = None


def get_default_store() -> BlobStore:
    global _default_store
    if _default_store is None:
        _default_store = BlobStore()
    return _default_store


def reset_default_store() -> None:
    """Test helper: wipe the module-level singleton."""
    global _default_store
    _default_store = BlobStore()
