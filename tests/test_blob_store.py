# tests/test_blob_store.py
# Pins the BlobStore TTL / size-cap / threading contract that the upload_file
# tool relies on. The TTL tests monkeypatch time.time() rather than sleeping so
# the suite stays fast.

from __future__ import annotations

import threading

import pytest

import blob_store
from blob_store import (
    BlobStore,
    BlobStoreFull,
    BlobTooLarge,
)


@pytest.fixture
def store():
    return BlobStore()


def test_put_returns_entry_with_token_and_expiry(store):
    entry = store.put(filename="a.pdf", content_type="application/pdf", data=b"hello")
    assert entry.token
    assert entry.filename == "a.pdf"
    assert entry.content_type == "application/pdf"
    assert entry.data == b"hello"
    assert entry.expires_at > entry.created_at
    assert entry.expires_at - entry.created_at == pytest.approx(
        blob_store.BLOB_STORE_TTL_SECONDS, abs=1
    )


def test_get_returns_same_entry_within_ttl(store):
    entry = store.put(filename="a.pdf", content_type="application/pdf", data=b"x")
    fetched = store.get(entry.token)
    assert fetched is not None
    assert fetched.token == entry.token
    assert fetched.data == b"x"


def test_get_returns_none_for_unknown_token(store):
    assert store.get("does-not-exist") is None


def test_tokens_are_unique(store):
    seen = set()
    for _ in range(50):
        e = store.put(filename="f", content_type="text/plain", data=b"x")
        assert e.token not in seen
        seen.add(e.token)


def test_tokens_are_high_entropy(store):
    # secrets.token_urlsafe(32) → 43-char base64. Lower-bound this so a regression
    # from urlsafe(32) → urlsafe(8) gets caught.
    e = store.put(filename="f", content_type="text/plain", data=b"x")
    assert len(e.token) >= 40


# --- TTL expiry --------------------------------------------------------------


def test_get_returns_none_after_ttl_and_drops_entry(store, monkeypatch):
    fake_now = [1_000_000.0]
    monkeypatch.setattr(blob_store.time, "time", lambda: fake_now[0])

    entry = store.put(filename="a.pdf", content_type="application/pdf", data=b"x")
    assert store.get(entry.token) is not None

    fake_now[0] += blob_store.BLOB_STORE_TTL_SECONDS + 1
    assert store.get(entry.token) is None
    # Side effect: entry was dropped from the store, freeing the bytes.
    assert len(store) == 0
    assert store.total_bytes() == 0


def test_put_sweeps_expired_entries(store, monkeypatch):
    fake_now = [1_000_000.0]
    monkeypatch.setattr(blob_store.time, "time", lambda: fake_now[0])

    old = store.put(filename="old", content_type="text/plain", data=b"old-bytes")
    assert len(store) == 1

    fake_now[0] += blob_store.BLOB_STORE_TTL_SECONDS + 1
    # New put runs the sweep; the old entry should be gone after.
    store.put(filename="new", content_type="text/plain", data=b"new-bytes")
    assert len(store) == 1
    assert store.get(old.token) is None


# --- Size caps ---------------------------------------------------------------


def test_put_rejects_blob_larger_than_single_cap(store, monkeypatch):
    monkeypatch.setattr(blob_store, "BLOB_STORE_MAX_SINGLE_BYTES", 100)
    with pytest.raises(BlobTooLarge):
        store.put(filename="big", content_type="application/octet-stream", data=b"x" * 101)


def test_put_rejects_when_total_cap_would_be_exceeded(store, monkeypatch):
    # 1 KB per blob, 2.5 KB total → third put must fail.
    monkeypatch.setattr(blob_store, "BLOB_STORE_MAX_SINGLE_BYTES", 1024)
    monkeypatch.setattr(blob_store, "BLOB_STORE_MAX_TOTAL_BYTES", 2 * 1024 + 512)

    store.put(filename="a", content_type="text/plain", data=b"x" * 1024)
    store.put(filename="b", content_type="text/plain", data=b"x" * 1024)
    with pytest.raises(BlobStoreFull):
        store.put(filename="c", content_type="text/plain", data=b"x" * 1024)


def test_total_bytes_tracks_active_blobs(store):
    store.put(filename="a", content_type="text/plain", data=b"x" * 10)
    store.put(filename="b", content_type="text/plain", data=b"x" * 20)
    assert store.total_bytes() == 30


def test_drop_releases_bytes(store):
    e = store.put(filename="a", content_type="text/plain", data=b"x" * 10)
    assert store.total_bytes() == 10
    assert store.drop(e.token) is True
    assert store.total_bytes() == 0
    assert len(store) == 0


def test_drop_unknown_token_returns_false(store):
    assert store.drop("nope") is False


# --- Concurrency -------------------------------------------------------------


def test_concurrent_puts_do_not_corrupt_total_bytes(store):
    # Hammer the store from N threads. The total must equal sum of sizes.
    threads = []
    sizes = [1024 * i for i in range(1, 21)]  # 1..20 KB each
    barrier = threading.Barrier(len(sizes))

    def _do_put(size: int) -> None:
        barrier.wait()
        store.put(filename="f", content_type="text/plain", data=b"x" * size)

    for size in sizes:
        t = threading.Thread(target=_do_put, args=(size,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert store.total_bytes() == sum(sizes)
    assert len(store) == len(sizes)


# --- Module-level singleton --------------------------------------------------


def test_get_default_store_is_idempotent():
    blob_store.reset_default_store()
    a = blob_store.get_default_store()
    b = blob_store.get_default_store()
    assert a is b


def test_reset_default_store_replaces_singleton():
    blob_store.reset_default_store()
    a = blob_store.get_default_store()
    a.put(filename="x", content_type="text/plain", data=b"x")
    assert len(a) == 1

    blob_store.reset_default_store()
    b = blob_store.get_default_store()
    assert b is not a
    assert len(b) == 0
