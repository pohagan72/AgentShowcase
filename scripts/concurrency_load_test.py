"""Phase 2.5.A operational load test — runnable, not pytest-bound.

Fires N concurrent `summarize_document` MCP calls against a deployed Synzo
endpoint and confirms the homepage stays responsive while they're in flight.
This is the gate the MCP_SUBMISSION_PLAN.md §6 Phase 2.5.A asks for:

    "Add a load test (...) that fires 32 concurrent summarize_document calls
     against a stubbed Gemini and confirms the homepage stays responsive
     throughout. Run before any public-launch deploy."

Why it's not a pytest test: this is operational — you run it against a
deployment, not inside CI. Wiring it into pytest would require booting a
real Waitress server in a fixture, which conflicts with the session-scoped
in-memory SQLite app fixture used by the rest of the suite.

USAGE:
    # Against a Railway preview deployment with real Gemini (uses real quota!):
    python -m scripts.concurrency_load_test \\
        --base-url https://www.synzo.ai \\
        --api-key sk_synzo_<your_key> \\
        --concurrency 32 \\
        --doc-path tests/fixtures/sample.pdf

    # Against a local server with stubbed Gemini:
    python -m scripts.concurrency_load_test --base-url http://localhost:5001 ...

The test:
  1. Reads a small document, base64-encodes it.
  2. Spawns N threads, each firing a tools/call against /mcp.
  3. While in flight, probes GET / every 200ms and records its latency.
  4. After all tool calls complete, reports:
     - tool-call throughput + latency distribution
     - homepage GET latency distribution while load was applied
     - pass/fail against a threshold (homepage p99 < 2.0s)

A pre-Phase-2.5.A server (Waitress default threads=4) would block the
homepage entirely under concurrency >= 4. The new default (threads=32) gives
headroom for an Anthropic reviewer hammering us.
"""

from __future__ import annotations

import argparse
import base64
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


def _read_sample(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


def _tool_call(base_url: str, api_key: str, content_base64: str, filename: str,
               timeout: float = 120.0) -> tuple[float, int, str]:
    """One tools/call. Returns (latency_seconds, http_status, summary_of_body)."""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "summarize_document",
            "arguments": {"filename": filename, "content_base64": content_base64},
        },
    }
    start = time.monotonic()
    try:
        resp = requests.post(
            f"{base_url}/mcp",
            json=body,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            timeout=timeout,
        )
        duration = time.monotonic() - start
        try:
            payload = resp.json()
        except Exception:
            payload = None
        if payload and "error" in payload:
            return duration, resp.status_code, f"rpc_error:{payload['error'].get('code')}"
        if payload and payload.get("result", {}).get("isError"):
            return duration, resp.status_code, "tool_error"
        return duration, resp.status_code, "ok"
    except requests.RequestException as e:
        return time.monotonic() - start, 0, f"transport_error:{e.__class__.__name__}"


def _homepage_prober(base_url: str, stop: threading.Event, latencies: list[float],
                     errors: list[str]) -> None:
    """Hit GET / every 200ms while load is running. Record latencies."""
    while not stop.is_set():
        start = time.monotonic()
        try:
            resp = requests.get(f"{base_url}/", timeout=5.0)
            duration = time.monotonic() - start
            if resp.status_code == 200:
                latencies.append(duration)
            else:
                errors.append(f"status_{resp.status_code}")
        except requests.RequestException as e:
            errors.append(e.__class__.__name__)
        stop.wait(0.2)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = int(len(s) * pct / 100)
    return s[min(k, len(s) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Synzo MCP concurrency load test.")
    parser.add_argument("--base-url", required=True,
                        help="Target Synzo deployment, e.g. https://www.synzo.ai")
    parser.add_argument("--api-key", required=True,
                        help="API key (sk_synzo_...) issued from the dashboard")
    parser.add_argument("--concurrency", type=int, default=32,
                        help="Number of concurrent tools/call invocations (default: 32)")
    parser.add_argument("--doc-path", type=Path, required=True,
                        help="Local path to a sample PDF/DOCX/PPTX/XLSX to upload")
    parser.add_argument("--filename", default=None,
                        help="Filename to send (default: doc-path basename)")
    parser.add_argument("--homepage-p99-threshold", type=float, default=2.0,
                        help="Fail if homepage p99 latency exceeds this (seconds, default 2.0)")
    args = parser.parse_args()

    if not args.doc_path.exists():
        print(f"ERROR: doc-path does not exist: {args.doc_path}", file=sys.stderr)
        return 2

    filename = args.filename or args.doc_path.name
    content_base64 = _read_sample(args.doc_path)
    decoded_size_kb = len(args.doc_path.read_bytes()) / 1024

    print(f"=== Synzo MCP concurrency load test ===")
    print(f"  target          : {args.base_url}")
    print(f"  concurrency     : {args.concurrency}")
    print(f"  document        : {filename} ({decoded_size_kb:.1f} KB)")
    print(f"  homepage p99 max: {args.homepage_p99_threshold:.1f}s")
    print()

    # Start the homepage prober.
    stop_probing = threading.Event()
    homepage_latencies: list[float] = []
    homepage_errors: list[str] = []
    prober = threading.Thread(
        target=_homepage_prober,
        args=(args.base_url, stop_probing, homepage_latencies, homepage_errors),
        daemon=True,
    )
    prober.start()

    # Fire N concurrent tool calls.
    pool = ThreadPoolExecutor(max_workers=args.concurrency)
    started = time.monotonic()
    futures = [
        pool.submit(_tool_call, args.base_url, args.api_key, content_base64, filename)
        for _ in range(args.concurrency)
    ]
    results = []
    for fut in as_completed(futures):
        results.append(fut.result())
    total_duration = time.monotonic() - started
    pool.shutdown(wait=True)

    # Stop probing.
    stop_probing.set()
    prober.join(timeout=2.0)

    # --- Tool-call stats ---
    tool_latencies = [r[0] for r in results]
    tool_ok = sum(1 for r in results if r[2] == "ok")
    tool_errors = [r[2] for r in results if r[2] != "ok"]

    print("=== Tool-call results ===")
    print(f"  total wall-clock      : {total_duration:.2f}s")
    print(f"  ok / total            : {tool_ok}/{len(results)}")
    print(f"  latency mean / p50 / p99 / max:")
    print(f"      {statistics.mean(tool_latencies):.2f}s / "
          f"{_percentile(tool_latencies, 50):.2f}s / "
          f"{_percentile(tool_latencies, 99):.2f}s / "
          f"{max(tool_latencies):.2f}s")
    if tool_errors:
        print(f"  errors                : {dict((e, tool_errors.count(e)) for e in set(tool_errors))}")
    print()

    # --- Homepage stats ---
    print("=== Homepage stats (probed every 200ms during load) ===")
    print(f"  samples               : {len(homepage_latencies)}")
    if homepage_latencies:
        print(f"  latency mean / p50 / p99 / max:")
        print(f"      {statistics.mean(homepage_latencies):.2f}s / "
              f"{_percentile(homepage_latencies, 50):.2f}s / "
              f"{_percentile(homepage_latencies, 99):.2f}s / "
              f"{max(homepage_latencies):.2f}s")
    if homepage_errors:
        print(f"  errors                : {dict((e, homepage_errors.count(e)) for e in set(homepage_errors))}")
    print()

    # --- Pass/fail ---
    homepage_p99 = _percentile(homepage_latencies, 99) if homepage_latencies else 0.0
    if homepage_p99 > args.homepage_p99_threshold:
        print(f"FAIL: homepage p99 {homepage_p99:.2f}s exceeds threshold "
              f"{args.homepage_p99_threshold:.1f}s — Waitress thread pool likely "
              f"undersized for {args.concurrency} concurrent tool calls.")
        return 1
    if homepage_errors:
        print(f"FAIL: homepage requests errored during load ({len(homepage_errors)} times).")
        return 1
    print("PASS: homepage stayed responsive while load was applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
