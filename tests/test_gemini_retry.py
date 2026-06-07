# tests/test_gemini_retry.py
# Tests for the tenacity retry wrapper added in Phase 3 technical hardening.
#
# The wrapper retries Gemini calls on transient 5xx / rate-limit errors only;
# everything else (4xx, safety-filter blocks expressed via empty response.text)
# is terminal and must propagate immediately so we don't burn budget on calls
# that will never succeed.
#
# Tests live at two levels:
# 1. The decorator itself: retries transient, doesn't retry terminal, gives up
#    after N attempts, propagates the underlying exception (not RetryError).
# 2. End-to-end through the three wrapped sites (analyst classification,
#    translate_text_util, analyze_image_with_gemini): a flaky model that
#    raises once then succeeds produces a successful tool result and exactly
#    two calls on the model.

from __future__ import annotations

import io
import logging

import pytest
from google.api_core import exceptions as gax


# --- 1. Decorator-level tests -------------------------------------------------


@pytest.fixture(autouse=True)
def _zero_sleep(monkeypatch):
    """Tenacity's wait_exponential calls time.sleep between attempts.
    Patching tenacity.nap.time.sleep to a no-op skips the real wall-clock
    sleeps without changing the decorator's retry decisions or attempt
    counts — production behavior is unchanged, tests just stop spending
    ~3s each sleeping."""
    import tenacity.nap
    monkeypatch.setattr(tenacity.nap.time, "sleep", lambda _seconds: None)


def test_retry_gemini_call_retries_on_service_unavailable_then_succeeds():
    from gemini_retry import retry_gemini_call

    attempts = {"n": 0}

    @retry_gemini_call
    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise gax.ServiceUnavailable("upstream 503")
        return "ok"

    assert flaky() == "ok"
    assert attempts["n"] == 3  # two failures + one success


def test_retry_gemini_call_retries_on_deadline_exceeded():
    from gemini_retry import retry_gemini_call

    attempts = {"n": 0}

    @retry_gemini_call
    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise gax.DeadlineExceeded("504 from gemini edge")
        return "ok"

    assert flaky() == "ok"
    assert attempts["n"] == 2


def test_retry_gemini_call_retries_on_internal_server_error():
    from gemini_retry import retry_gemini_call

    attempts = {"n": 0}

    @retry_gemini_call
    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise gax.InternalServerError("500 boom")
        return "ok"

    assert flaky() == "ok"
    assert attempts["n"] == 2


def test_retry_gemini_call_retries_on_resource_exhausted():
    """ResourceExhausted is Gemini's term for upstream rate-limiting (429).
    Backing off and retrying is the right move."""
    from gemini_retry import retry_gemini_call

    attempts = {"n": 0}

    @retry_gemini_call
    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise gax.ResourceExhausted("429 upstream rate-limited")
        return "ok"

    assert flaky() == "ok"
    assert attempts["n"] == 2


def test_retry_gemini_call_does_NOT_retry_on_invalid_argument():
    """InvalidArgument is a 4xx terminal error: the prompt itself is the
    problem and retrying will produce the same failure. Must NOT retry."""
    from gemini_retry import retry_gemini_call

    attempts = {"n": 0}

    @retry_gemini_call
    def terminal():
        attempts["n"] += 1
        raise gax.InvalidArgument("400 bad prompt")

    with pytest.raises(gax.InvalidArgument):
        terminal()
    assert attempts["n"] == 1


def test_retry_gemini_call_does_NOT_retry_on_arbitrary_exception():
    """A non-transient exception (e.g. an attribute error in the SDK,
    a parsing bug downstream) is terminal and must propagate on attempt 1."""
    from gemini_retry import retry_gemini_call

    attempts = {"n": 0}

    @retry_gemini_call
    def terminal():
        attempts["n"] += 1
        raise ValueError("unrelated failure")

    with pytest.raises(ValueError):
        terminal()
    assert attempts["n"] == 1


def test_retry_gemini_call_gives_up_after_3_attempts():
    """The retry budget is bounded so a sustained outage doesn't pin
    waitress threads under MCP_TOOL_TIMEOUT_SECONDS=60. After 3 attempts
    the original exception (NOT tenacity.RetryError, due to reraise=True)
    propagates."""
    from gemini_retry import retry_gemini_call

    attempts = {"n": 0}

    @retry_gemini_call
    def always_503():
        attempts["n"] += 1
        raise gax.ServiceUnavailable("perma-down")

    with pytest.raises(gax.ServiceUnavailable):
        always_503()
    assert attempts["n"] == 3


# --- 2. End-to-end through the three wrapped sites ----------------------------


def test_analyst_agent_classify_document_retries_on_transient_failure():
    """The classification call in analyst_agent should now survive one
    transient 5xx and still produce a real classification on retry."""
    from features.summarization.agents import analyst_agent

    attempts = {"n": 0}

    class FakeResponse:
        def __init__(self, text):
            self.text = text

    class FlakyModel:
        def generate_content(self, prompt):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise gax.ServiceUnavailable("transient")
            return FakeResponse("FINANCIAL_REPORT")

    # parse_classification_response returns a string; whatever the model
    # produced doesn't matter much for this test, only that it ran twice.
    result = analyst_agent.classify_document("some text", FlakyModel(), filename="f.pdf")
    assert attempts["n"] == 2
    assert isinstance(result, str) and result  # non-empty result on retry


def test_analyst_agent_classify_document_does_not_retry_on_terminal_failure():
    """Pre-existing bare `except Exception` in classify_document defaults to
    'General Business Document' on any exception. Retry must NOT happen on
    a terminal error — assert exactly one call to the model."""
    from features.summarization.agents import analyst_agent

    attempts = {"n": 0}

    class TerminalModel:
        def generate_content(self, prompt):
            attempts["n"] += 1
            raise gax.InvalidArgument("400 bad prompt")

    result = analyst_agent.classify_document("some text", TerminalModel())
    assert attempts["n"] == 1
    assert result == "General Business Document"


def test_translate_text_util_retries_on_transient_failure(monkeypatch):
    """translate_text_util's Gemini call is wrapped; a one-off 5xx must
    succeed on retry and return ('success', ...). Without retry the same
    flake would return ('error', text, '...') on the first try."""
    from features.translation import routes as translation_routes

    attempts = {"n": 0}

    class FakeResponse:
        def __init__(self, text):
            self.text = text

    class FlakyModel:
        def generate_content(self, prompt):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise gax.DeadlineExceeded("transient")
            return FakeResponse("hola mundo")

    monkeypatch.setattr(
        translation_routes.genai,
        "GenerativeModel",
        lambda name: FlakyModel(),
    )

    status, translated, err = translation_routes.translate_text_util(
        "hello world", "Spanish", "gemini-1.5-flash"
    )
    assert status == "success"
    assert translated == "hola mundo"
    assert err is None
    assert attempts["n"] == 2


def test_translate_text_util_does_not_retry_on_terminal_failure(monkeypatch):
    """Terminal exception inside translate_text_util should surface as
    ('error', ...) after exactly one model call."""
    from features.translation import routes as translation_routes

    attempts = {"n": 0}

    class TerminalModel:
        def generate_content(self, prompt):
            attempts["n"] += 1
            raise gax.InvalidArgument("400 bad input")

    monkeypatch.setattr(
        translation_routes.genai,
        "GenerativeModel",
        lambda name: TerminalModel(),
    )

    status, _text, err = translation_routes.translate_text_util(
        "hello world", "Spanish", "gemini-1.5-flash"
    )
    assert status == "error"
    assert "InvalidArgument" in err or "400" in err
    assert attempts["n"] == 1


def test_analyze_image_with_gemini_retries_on_transient_failure():
    """analyze_image_with_gemini wraps the gemini_model.generate_content
    call. A one-off 5xx must succeed on retry and return the parsed dict."""
    from features.multimedia import analytics_utils

    attempts = {"n": 0}

    # The smallest valid PNG (1x1 transparent) so PIL.Image.open succeeds.
    one_px_png = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000D49444154789C636400000000050001A5F8A86F0000000049454E44AE426082"
    )

    class FakeResponse:
        def __init__(self, text):
            self.text = text

    class FlakyModel:
        def generate_content(self, parts):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise gax.ServiceUnavailable("transient")
            return FakeResponse(
                '{"description":"x","rich_description":"y","extracted_text":"",'
                '"safety_flags":{"contains_people":false,"contains_potential_pii":false,'
                '"is_graphic_or_violent":false},"detected_objects":[]}'
            )

    result = analytics_utils.analyze_image_with_gemini(one_px_png, FlakyModel())
    assert attempts["n"] == 2
    assert result is not None
    assert "error" not in result
    assert result["description"] == "x"


def test_analyze_image_with_gemini_does_not_retry_on_terminal_failure():
    """Terminal exception surfaces as {"error": "..."} after one call."""
    from features.multimedia import analytics_utils

    attempts = {"n": 0}

    one_px_png = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000D49444154789C636400000000050001A5F8A86F0000000049454E44AE426082"
    )

    class TerminalModel:
        def generate_content(self, parts):
            attempts["n"] += 1
            raise gax.InvalidArgument("400 bad image")

    result = analytics_utils.analyze_image_with_gemini(one_px_png, TerminalModel())
    assert attempts["n"] == 1
    assert result is not None
    assert "error" in result
