# gemini_retry.py
# Retry wrapper around non-streaming Gemini calls.
#
# Transient 5xx / connection-reset errors from Gemini are surfaced via
# google.api_core.exceptions. Without retry, a single hiccup at Google's edge
# turns into a refunded tool call — fine for one user, but the equivalent of a
# free outage from the caller's perspective. With three short retries we
# absorb the common case (transient ServiceUnavailable / DeadlineExceeded /
# 500) without papering over genuine failures (4xx, safety-filter rejections,
# falsy response.text).
#
# Budget: 3 attempts max, exponential backoff 1s / 2s / 4s. Worst case ~7s of
# wall-clock burn, well under MCP_TOOL_TIMEOUT_SECONDS=60 (which is the outer
# bound for the whole tool call including the Gemini turnaround).
#
# Scope: ONLY non-streaming Gemini calls (model.generate_content(prompt)).
# Streaming calls (stream=True) are NOT wrapped because mid-stream failures
# would require start-over semantics — the chunks already yielded to the
# caller can't be replayed. The submission ships with streaming-retry
# deferred; documented as a known gap in MCP_SUBMISSION_PLAN.md.

from __future__ import annotations

import logging

from google.api_core import exceptions as gax
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


# Only retry on errors that are plausibly transient: 503 ServiceUnavailable,
# 504 DeadlineExceeded, 500 InternalServerError, and 429 ResourceExhausted
# (Google's term for upstream rate limiting). Everything else — 400
# InvalidArgument, 401/403, safety-filter blocks (which arrive as a normal
# response with an empty .text and a populated prompt_feedback.block_reason)
# — is terminal and should propagate immediately.
_TRANSIENT = (
    gax.ServiceUnavailable,
    gax.DeadlineExceeded,
    gax.InternalServerError,
    gax.ResourceExhausted,
)


retry_gemini_call = retry(
    retry=retry_if_exception_type(_TRANSIENT),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
