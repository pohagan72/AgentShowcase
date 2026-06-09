# mcp_tools.py
# Tool implementations exposed via the MCP server (mcp_routes.py).
#
# Each tool is a callable that takes the Principal (already authed) plus the
# tool's JSON-RPC arguments dict and returns the structured result. The MCP
# layer wraps each call in `run_metered_tool()` so quota/rate-limit/metering
# happen identically to the /api/v1/* path. Anything tenant-scoped here MUST
# read principal.org_id and scope DB reads/writes on it — see s3.4 of
# MCP_SUBMISSION_PLAN.md.
#
# Each tool reuses the same feature-module internals the HTMX surface uses, so
# the MCP and HTMX results stay identical. The HTMX surface's GCS round-trip is
# skipped here — MCP callers pass bytes in and get bytes out via base64 in the
# JSON-RPC envelope.

from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import filetype
from flask import current_app
from werkzeug.datastructures import FileStorage

from auth import Principal
from blob_store import BlobStoreFull, BlobTooLarge, get_default_store
from url_fetcher import UrlFetchError, fetch_url_bytes

logger = logging.getLogger(__name__)


SUPPORTED_DOC_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}
SUPPORTED_TRANSLATE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
SUPPORTED_REDACT_EXTENSIONS = {".docx", ".pptx"}
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB — same cap as /api/v1/summarize
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ToolSpec:
    """Static metadata used to build the tools/list response.

    `units_fn` sizes a tool call before it runs so the quota check can 413 a
    too-big request without burning the handler. `handler` is the actual
    implementation; the MCP route wraps it in run_metered_tool().
    """
    name: str
    title: str
    description: str
    input_schema: dict
    annotations: dict
    units_fn: Callable[[dict], int]
    handler: Callable[[Principal, dict], dict]


class ToolError(Exception):
    """Raised by tool handlers for argument / input failures.

    The MCP route translates this to an isError=true tool result so the model
    can recover. Quota is still refunded via run_metered_tool's exception path.
    Tool-internal failures (e.g. Gemini returned an error event) re-raise as
    RuntimeError so the same refund path applies.
    """


# --- Shared helpers ------------------------------------------------------------


def _load_payload(args: dict, *, max_bytes: int) -> tuple[str, bytes, str]:
    """Pull (filename, raw_bytes, extension) out of a tool's arguments dict.

    Every binary-input tool takes `filename` + `content_url`. The URL is fetched
    via the SSRF-guarded fetcher (url_fetcher.fetch_url_bytes); the bytes must
    not exceed `max_bytes` decoded.

    Why URL-only (no inline base64): chat clients must construct tool-call
    arguments as LLM output tokens, and inlining a multi-MB base64 string into
    every tool call stalls the chat UI for minutes. The `upload_file` tool
    handles the one-time base64 upload; downstream tools reference the file
    by URL and get instant tool-call invocation.

    Raises ToolError on argument problems / fetch failures; the caller does
    the extension-set check itself because allowed extensions vary per tool.
    """
    filename = (args.get("filename") or "").strip()
    if not filename:
        raise ToolError("Missing 'filename'")

    _, ext = os.path.splitext(filename.lower())

    url = args.get("content_url")
    if not isinstance(url, str) or not url:
        raise ToolError("Missing 'content_url'")

    try:
        raw, _content_type = fetch_url_bytes(url, max_bytes=max_bytes)
    except UrlFetchError as e:
        raise ToolError(f"Could not fetch content_url: {e}") from e

    if len(raw) > max_bytes:
        # Defense in depth: fetch_url_bytes already enforces this.
        raise ToolError(f"Fetched content exceeds {max_bytes} bytes")

    return filename, raw, ext


def _units_from_url(args: dict) -> int:
    """Fixed nominal unit count for URL-input tools.

    We charge 1 unit on the URL path because we don't know the content size
    until after the fetch. The per-call quota guard runs again at the
    handler boundary (decoded-size cap) so oversized fetches are still
    rejected — they just don't 413 in pre-flight. Acceptable tradeoff for
    the chat-client UX win.
    """
    return 1


def _units_from_base64(args: dict, *, divisor_bytes: int = 50 * 1024) -> int:
    """Estimate units for the `upload_file` tool by base64 length."""
    encoded = args.get("content_base64") or ""
    approx_bytes = (len(encoded) * 3) // 4
    return max(1, approx_bytes // divisor_bytes)


# Maps the user-facing extension (lowercased, with dot) to the set of detection
# results `filetype.guess(...).extension` may return for a genuine file of that
# type. This lets us reject a `.docx` filename whose bytes are actually a JPG,
# without forcing the caller to know our internal detection lib's naming.
# .heif is accepted alongside .heic because real-world HEIF files use the same
# ISO BMFF container; `filetype` reports both as 'heic'. Same for jpg/jpeg.
_VALID_DETECTED_FOR_EXT: dict[str, set[str]] = {
    ".pdf": {"pdf"},
    ".docx": {"docx"},
    ".pptx": {"pptx"},
    ".xlsx": {"xlsx"},
    ".jpg": {"jpg"},
    ".jpeg": {"jpg"},
    ".png": {"png"},
    ".webp": {"webp"},
    ".heic": {"heic"},
    ".heif": {"heic"},
}


def _verify_magic_bytes(raw: bytes, ext: str) -> None:
    """Reject files whose magic bytes don't match the declared extension.

    `filetype.guess()` peeks at the first ~256 bytes; for OOXML it also peeks
    inside the zip's directory listing to distinguish docx/pptx/xlsx. If the
    bytes are unrecognized OR detected as a different format than the
    declared extension, raise ToolError so the MCP route can surface the
    problem as isError=true (and the quota is refunded by run_metered_tool).
    """
    expected = _VALID_DETECTED_FOR_EXT.get(ext)
    if expected is None:
        # Unknown extension shouldn't reach here — the per-tool ext-set check
        # runs first. Belt-and-braces: don't crash, just don't enforce.
        return

    kind = filetype.guess(raw)
    detected = kind.extension if kind else None
    if detected not in expected:
        raise ToolError(
            f"File content does not match extension {ext} "
            f"(detected: {detected or 'unknown'})"
        )


# --- summarize_document --------------------------------------------------------


_SUMMARIZE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the document with its extension (.pdf, .docx, .pptx, .xlsx).",
        },
        "content_url": {
            "type": "string",
            "format": "uri",
            "description": (
                "HTTPS URL the server will fetch the document from. Max 10 MB "
                "decoded. Use the upload_file tool to obtain a short-lived "
                "Synzo-hosted URL for a local file."
            ),
        },
    },
    "required": ["filename", "content_url"],
    "additionalProperties": False,
}


def _summarize_document(principal: Principal, args: dict) -> dict:
    """summarize_document tool implementation.

    Mirrors /api/v1/summarize behavior so MCP and direct-API callers get the
    same result. Tenancy: all metering inside run_metered_tool() scopes on
    principal.org_id; this handler does no direct DB writes.
    """
    if not current_app.config.get("GEMINI_CONFIGURED"):
        raise RuntimeError("Gemini AI service is not configured.")

    filename, raw, ext = _load_payload(args, max_bytes=MAX_DOC_BYTES)
    if ext not in SUPPORTED_DOC_EXTENSIONS:
        raise ToolError(
            f"Unsupported file type {ext}. Allowed: {sorted(SUPPORTED_DOC_EXTENSIONS)}"
        )
    _verify_magic_bytes(raw, ext)

    file = FileStorage(stream=io.BytesIO(raw), filename=filename)

    from features.summarization import utils as summarization_utils
    from features.summarization.agents import analyst_agent

    text, secure_name = summarization_utils.read_text_from_file(file)
    if not text:
        raise ToolError("Could not extract text from the file.")

    model_name = current_app.config.get("GEMINI_MODEL_NAME")

    classification: str | None = None
    chunks: list[str] = []
    for line in analyst_agent.stream_analysis(text, model_name, secure_name):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if event_type == "meta":
            classification = event.get("classification")
        elif event_type == "chunk":
            chunks.append(event.get("content", ""))
        elif event_type == "error":
            # RuntimeError -> run_metered_tool refunds the quota.
            raise RuntimeError(event.get("content", "AI service error"))

    return {
        "classification": classification,
        "summary": "".join(chunks),
        "filename": secure_name,
    }


# --- translate_document --------------------------------------------------------
#
# Returns translated text (markdown) — NOT a rebuilt .docx/.pptx/.xlsx file.
# The HTMX surface ALSO produces a binary download via GCS round-trip; that
# path is skipped here to keep JSON-RPC payloads small. If a customer needs the
# binary back, they call /api/v1/translate (Phase 4 will wire that endpoint).


_TRANSLATE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the document with its extension (.docx, .pptx, .xlsx).",
        },
        "content_url": {
            "type": "string",
            "format": "uri",
            "description": (
                "HTTPS URL the server will fetch the document from. Max 10 MB "
                "decoded. Use the upload_file tool to obtain a short-lived "
                "Synzo-hosted URL for a local file."
            ),
        },
        "target_language": {
            "type": "string",
            "description": (
                "Target language for the translation (e.g. 'Spanish', 'French', "
                "'Japanese', 'Korean'). Plain English name of the language."
            ),
            "minLength": 2,
            "maxLength": 64,
        },
    },
    "required": ["filename", "content_url", "target_language"],
    "additionalProperties": False,
}


def _translate_document(principal: Principal, args: dict) -> dict:
    """Translate the text content of a .docx/.pptx/.xlsx into target_language.

    Reuses features.translation.routes.translate_text_util so the model name,
    prompt, and safety-filter behavior match the HTMX surface. We extract text
    in one pass (via summarization_utils.extract_text_from_stream) and submit
    it as a single Gemini call — simpler than the per-segment ThreadPoolExecutor
    pattern the HTMX route uses, at the cost of losing the in-place style
    preservation. That's intentional: MCP returns text, not a rebuilt binary.
    """
    if not current_app.config.get("GEMINI_CONFIGURED"):
        raise RuntimeError("Gemini AI service is not configured.")

    filename, raw, ext = _load_payload(args, max_bytes=MAX_DOC_BYTES)
    if ext not in SUPPORTED_TRANSLATE_EXTENSIONS:
        raise ToolError(
            f"Unsupported file type {ext}. Allowed: {sorted(SUPPORTED_TRANSLATE_EXTENSIONS)}"
        )
    _verify_magic_bytes(raw, ext)

    target_language = (args.get("target_language") or "").strip()
    if not target_language:
        raise ToolError("Missing 'target_language'")

    from features.summarization import utils as summarization_utils
    from features.translation import routes as translation_routes

    text = summarization_utils.extract_text_from_stream(io.BytesIO(raw), ext)
    if not text:
        raise ToolError("Could not extract text from the file.")

    model_name = current_app.config.get("GEMINI_MODEL_NAME")
    status, translated, error_message = translation_routes.translate_text_util(
        text, target_language, model_name
    )

    if status == "blocked":
        # Safety filter blocked the translation. Surface to the model as a tool
        # error so it can decide whether to retry with different content.
        raise ToolError(
            f"Translation blocked by AI safety filters: {error_message or 'unknown reason'}"
        )
    if status != "success":
        # RuntimeError -> run_metered_tool refunds.
        raise RuntimeError(error_message or "Translation failed")

    return {
        "filename": filename,
        "target_language": target_language,
        "translated_text": translated,
    }


# --- redact_pii ----------------------------------------------------------------


_REDACT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the document with its extension (.docx or .pptx).",
        },
        "content_url": {
            "type": "string",
            "format": "uri",
            "description": (
                "HTTPS URL the server will fetch the document from. Max 10 MB "
                "decoded. Use the upload_file tool to obtain a short-lived "
                "Synzo-hosted URL for a local file."
            ),
        },
    },
    "required": ["filename", "content_url"],
    "additionalProperties": False,
}


def _redact_pii(principal: Principal, args: dict) -> dict:
    """Redact PII from a .docx or .pptx using Microsoft Presidio.

    Returns the redacted document as base64-encoded bytes so the caller can
    save it directly. PII characters are replaced with the block symbol (█)
    in-place so document structure / styling is preserved.
    """
    analyzer = getattr(current_app, "presidio_analyzer", None)
    if not current_app.config.get("PRESIDIO_ANALYZER_AVAILABLE") or analyzer is None:
        raise RuntimeError("PII redaction service (Presidio Analyzer) is not available.")

    filename, raw, ext = _load_payload(args, max_bytes=MAX_DOC_BYTES)
    if ext not in SUPPORTED_REDACT_EXTENSIONS:
        raise ToolError(
            f"Unsupported file type {ext}. Allowed: {sorted(SUPPORTED_REDACT_EXTENSIONS)}"
        )
    _verify_magic_bytes(raw, ext)

    from features.pii_redaction import routes as pii_routes

    file_stream = io.BytesIO(raw)
    if ext == ".docx":
        output = pii_routes.redact_word_document_pii(file_stream, analyzer)
        mimetype = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        output = pii_routes.redact_powerpoint_document_pii(file_stream, analyzer)
        mimetype = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

    if output is None:
        raise RuntimeError("PII redaction failed.")

    output.seek(0)
    redacted_bytes = output.read()
    out_name = f"redacted_{filename}"
    result_url, expires_at = _stash_output_bytes(
        data=redacted_bytes, filename=out_name, content_type=mimetype
    )
    return {
        "filename": out_name,
        "result_url": result_url,
        "expires_at": expires_at,
        "mimetype": mimetype,
        "original_size_bytes": len(raw),
        "redacted_size_bytes": len(redacted_bytes),
    }


# --- analyze_image -------------------------------------------------------------


_ANALYZE_IMAGE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the image with its extension (.jpg, .jpeg, .png, .webp, .heic, .heif).",
        },
        "content_url": {
            "type": "string",
            "format": "uri",
            "description": (
                "HTTPS URL the server will fetch the image from. Max 10 MB. "
                "Use the upload_file tool to obtain a short-lived Synzo-hosted "
                "URL for a local image."
            ),
        },
    },
    "required": ["filename", "content_url"],
    "additionalProperties": False,
}


def _analyze_image(principal: Principal, args: dict) -> dict:
    """Run Gemini vision analysis on an image plus extract dominant colors.

    Output structure matches features.multimedia.analytics_utils.analyze_image_with_gemini:
    description, rich_description, extracted_text, safety_flags, detected_objects,
    plus a dominant_colors palette as hex strings.
    """
    if not current_app.config.get("GEMINI_CONFIGURED"):
        raise RuntimeError("Gemini AI service is not configured.")

    filename, raw, ext = _load_payload(args, max_bytes=MAX_IMAGE_BYTES)
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ToolError(
            f"Unsupported file type {ext}. Allowed: {sorted(SUPPORTED_IMAGE_EXTENSIONS)}"
        )
    _verify_magic_bytes(raw, ext)

    from features.multimedia import routes as multimedia_routes
    from features.multimedia.analytics_utils import (
        analyze_image_with_gemini,
        extract_dominant_colors,
    )
    import google.generativeai as genai

    # Normalize/resize so we don't ship 10 MB raw to Gemini.
    image_bytes = multimedia_routes.normalize_and_resize_image(raw)

    model_name = current_app.config.get("GEMINI_MODEL_NAME", "gemini-1.5-flash-latest")
    gemini_model = genai.GenerativeModel(model_name)

    analysis = analyze_image_with_gemini(image_bytes, gemini_model)
    if analysis is None:
        raise RuntimeError("Image analysis failed (no response from AI service).")
    if isinstance(analysis, dict) and "error" in analysis:
        # analytics_utils encodes failure as {"error": "..."}; treat as a tool
        # error so the model can see the reason and decide whether to retry.
        raise ToolError(analysis["error"])

    dominant_colors = extract_dominant_colors(image_bytes)

    return {
        "filename": filename,
        "analysis": analysis,
        "dominant_colors": dominant_colors,
    }


# --- detect_faces --------------------------------------------------------------


_DETECT_FACES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the image with its extension (.jpg, .jpeg, .png, .webp, .heic, .heif).",
        },
        "content_url": {
            "type": "string",
            "format": "uri",
            "description": (
                "HTTPS URL the server will fetch the image from. Max 10 MB. "
                "Use the upload_file tool to obtain a short-lived Synzo-hosted "
                "URL for a local image."
            ),
        },
        "mode": {
            "type": "string",
            "enum": ["blur", "redact"],
            "default": "blur",
            "description": (
                "How to obscure detected faces. 'blur' applies a Gaussian blur "
                "with padding; 'redact' draws a solid black rectangle. Defaults to 'blur'."
            ),
        },
        "blur_strength": {
            "type": "integer",
            "enum": [1, 2, 3],
            "default": 2,
            "description": (
                "When mode='blur': 1=light, 2=strong (default), 3=opaque "
                "(equivalent to mode='redact'). Ignored when mode='redact'."
            ),
        },
    },
    "required": ["filename", "content_url"],
    "additionalProperties": False,
}


# Mirrors the strength map in features.multimedia.routes.process_multimedia_blur_image_route.
_BLUR_STRENGTH_MAP = {1: 35, 2: 151, 3: -1}


def _detect_faces(principal: Principal, args: dict) -> dict:
    """Detect faces in an image and return a copy with them obscured.

    Wraps features.multimedia.blur_utils.blur_image_opencv (MTCNN + OpenCV).
    Returns a PNG with faces blurred or redacted; if no faces are detected the
    original image is returned as PNG (call still costs quota — the detection
    is the work).
    """
    filename, raw, ext = _load_payload(args, max_bytes=MAX_IMAGE_BYTES)
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ToolError(
            f"Unsupported file type {ext}. Allowed: {sorted(SUPPORTED_IMAGE_EXTENSIONS)}"
        )
    _verify_magic_bytes(raw, ext)

    mode = (args.get("mode") or "blur").lower()
    if mode not in ("blur", "redact"):
        raise ToolError("'mode' must be 'blur' or 'redact'")

    if mode == "redact":
        blur_size = -1
    else:
        strength = args.get("blur_strength", 2)
        if strength not in _BLUR_STRENGTH_MAP:
            raise ToolError("'blur_strength' must be 1, 2, or 3")
        blur_size = _BLUR_STRENGTH_MAP[strength]

    from features.multimedia import routes as multimedia_routes
    from features.multimedia.blur_utils import blur_image_opencv

    normalized = multimedia_routes.normalize_and_resize_image(raw)
    processed = blur_image_opencv(normalized, blur_size)
    if processed is None:
        raise RuntimeError("Face detection / blurring failed.")

    root, _ = os.path.splitext(filename)
    suffix = "blurred" if mode == "blur" else "redacted"
    out_name = f"{root}-faces-{suffix}.png"
    result_url, expires_at = _stash_output_bytes(
        data=processed, filename=out_name, content_type="image/png"
    )

    return {
        "filename": out_name,
        "mode": mode,
        "result_url": result_url,
        "expires_at": expires_at,
        "mimetype": "image/png",
    }


# --- upload_file ---------------------------------------------------------------
#
# The one tool that still takes base64 — by design. Chat clients call this
# ONCE per file; downstream tools (summarize/translate/redact/analyze/detect)
# reference the file by URL. That single base64-laden call is unavoidable for
# a chat-client workflow because the client doesn't have a "give me a URL for
# this attachment" affordance. After this call, every subsequent tool call is
# instant — they just pass the URL string.


_UPLOAD_FILE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Original filename (with extension) used to set the response Content-Type and inform downstream tools.",
        },
        "content_base64": {
            "type": "string",
            "description": (
                "Base64-encoded file bytes. Decoded size must not exceed 10 MB. "
                "The server stores the bytes in memory and returns a short-lived "
                "HTTPS URL you can pass to the other Synzo tools as `content_url`."
            ),
        },
    },
    "required": ["filename", "content_base64"],
    "additionalProperties": False,
}


def _public_base_url() -> str:
    """Externally-reachable base URL for blob serve links.

    Mirrors mcp_routes._resource_metadata_url's preference for SYNZO_PUBLIC_URL
    over request.host_url, because Railway's edge TLS termination rewrites the
    request host scheme to http:// internally.
    """
    base = os.environ.get("SYNZO_PUBLIC_URL")
    if base:
        return base.rstrip("/")
    # Best-effort fallback for tests / local dev.
    try:
        from flask import request as _request
        return _request.host_url.rstrip("/")
    except Exception:
        return "http://localhost:5001"


def _content_type_for_extension(ext: str) -> str:
    """Map the supported extensions to canonical content types."""
    ext = ext.lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }.get(ext, "application/octet-stream")


def _stash_output_bytes(*, data: bytes, filename: str, content_type: str) -> tuple[str, str]:
    """Park `data` in the blob store and return (url, expires_at_iso).

    Used by tools that produce binary output (redact_pii, detect_faces) so
    they can return a URL instead of a multi-MB base64 string. Same TTL +
    cap behavior as upload_file uploads.
    """
    store = get_default_store()
    try:
        entry = store.put(filename=filename, content_type=content_type, data=data)
    except BlobTooLarge as e:
        raise ToolError(f"Output too large to store: {e}") from e
    except BlobStoreFull as e:
        raise RuntimeError(f"Blob store is full: {e}") from e

    url = f"{_public_base_url()}/u/{entry.token}"
    expires_iso = datetime.fromtimestamp(entry.expires_at, tz=timezone.utc).isoformat()
    return url, expires_iso


def _upload_file(principal: Principal, args: dict) -> dict:
    """Park an uploaded file in the blob store; return a fetchable URL.

    The principal is the calling org. We don't bind the blob to the org —
    the URL is the token, and the token is the auth. This matches the
    S3-presigned-URL pattern (anyone with the URL can fetch). The blob
    expires after BLOB_STORE_TTL_SECONDS (default 1h).
    """
    filename = (args.get("filename") or "").strip()
    if not filename:
        raise ToolError("Missing 'filename'")

    _, ext = os.path.splitext(filename.lower())

    encoded = args.get("content_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ToolError("Missing 'content_base64'")

    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as e:
        raise ToolError(f"content_base64 is not valid base64: {e}") from e

    # Single source of truth for the cap: matches MAX_DOC_BYTES / MAX_IMAGE_BYTES.
    if len(raw) > MAX_DOC_BYTES:
        raise ToolError(f"Uploaded content exceeds {MAX_DOC_BYTES} bytes")

    content_type = _content_type_for_extension(ext)
    store = get_default_store()
    try:
        entry = store.put(filename=filename, content_type=content_type, data=raw)
    except BlobTooLarge as e:
        raise ToolError(str(e)) from e
    except BlobStoreFull as e:
        raise RuntimeError(f"Blob store is full: {e}") from e

    url = f"{_public_base_url()}/u/{entry.token}"
    expires_iso = datetime.fromtimestamp(entry.expires_at, tz=timezone.utc).isoformat()
    return {
        "filename": filename,
        "content_url": url,
        "expires_at": expires_iso,
        "size_bytes": len(raw),
        "content_type": content_type,
    }


# --- Registry ------------------------------------------------------------------


TOOLS: dict[str, ToolSpec] = {
    "upload_file": ToolSpec(
        name="upload_file",
        title="Upload a file for use by other Synzo tools",
        description=(
            "Upload a file to Synzo and receive a short-lived HTTPS URL. "
            "Use this FIRST when you need to operate on a local file: call "
            "upload_file once with the file's base64 bytes, then pass the "
            "returned content_url to any of the other Synzo tools "
            "(summarize_document, translate_document, redact_pii, "
            "analyze_image, detect_faces). The URL expires in 1 hour. "
            "Decoded size must not exceed 10 MB."
        ),
        input_schema=_UPLOAD_FILE_INPUT_SCHEMA,
        annotations={
            "title": "Upload a file for use by other Synzo tools",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
        units_fn=lambda args: _units_from_base64(args),
        handler=_upload_file,
    ),
    "summarize_document": ToolSpec(
        name="summarize_document",
        title="Summarize a document",
        description=(
            "Classify and summarize a PDF, DOCX, PPTX, or XLSX file. "
            "Returns the inferred document type and a structured Markdown summary. "
            "Pass `content_url` — an HTTPS URL the server will fetch from "
            "(max 10 MB). For local files, call upload_file first to get a URL."
        ),
        input_schema=_SUMMARIZE_INPUT_SCHEMA,
        # Tool annotations per MCP spec: a summarize call produces new content
        # but does not modify any state on the server -> read-ish, idempotent,
        # non-destructive. We mark readOnlyHint=false because we DO consume
        # quota (an observable side effect), and destructiveHint=false.
        annotations={
            "title": "Summarize a document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        units_fn=_units_from_url,
        handler=_summarize_document,
    ),
    "translate_document": ToolSpec(
        name="translate_document",
        title="Translate a document",
        description=(
            "Translate the text content of a DOCX, PPTX, or XLSX file into a "
            "target language. Returns the translated text as Markdown (no "
            "binary file round-trip). Pass `content_url` — an HTTPS URL the "
            "server will fetch from (max 10 MB). For local files, call "
            "upload_file first to get a URL."
        ),
        input_schema=_TRANSLATE_INPUT_SCHEMA,
        annotations={
            "title": "Translate a document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        units_fn=_units_from_url,
        handler=_translate_document,
    ),
    "redact_pii": ToolSpec(
        name="redact_pii",
        title="Redact PII from a document",
        description=(
            "Detect and redact personally identifiable information (PII) in a "
            "DOCX or PPTX file using Microsoft Presidio. Returns a short-lived "
            "HTTPS URL (`result_url`) where the redacted document can be "
            "downloaded. PII characters are replaced with the block symbol in "
            "place so formatting is preserved. Pass `content_url` — an HTTPS "
            "URL the server will fetch from (max 10 MB). For local files, call "
            "upload_file first to get a URL."
        ),
        input_schema=_REDACT_INPUT_SCHEMA,
        annotations={
            "title": "Redact PII from a document",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        units_fn=_units_from_url,
        handler=_redact_pii,
    ),
    "analyze_image": ToolSpec(
        name="analyze_image",
        title="Analyze an image",
        description=(
            "Use Gemini vision to analyze an image and return a structured "
            "description, extracted text, safety flags (people / PII / "
            "graphic content), a list of detected objects, and a palette of "
            "the dominant colors. Supports JPG, PNG, WEBP, HEIC, HEIF up to "
            "10 MB. Pass `content_url` — an HTTPS URL the server will fetch "
            "from. For local files, call upload_file first to get a URL."
        ),
        input_schema=_ANALYZE_IMAGE_INPUT_SCHEMA,
        annotations={
            "title": "Analyze an image",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        units_fn=_units_from_url,
        handler=_analyze_image,
    ),
    "detect_faces": ToolSpec(
        name="detect_faces",
        title="Detect and obscure faces in an image",
        description=(
            "Detect human faces in an image (MTCNN) and return a short-lived "
            "HTTPS URL (`result_url`) where the processed PNG can be "
            "downloaded — each face either blurred or covered with an opaque "
            "rectangle. Useful for anonymizing photos before sharing. Pass "
            "`content_url` — an HTTPS URL the server will fetch from "
            "(JPG/PNG/WEBP/HEIC/HEIF, max 10 MB). For local files, call "
            "upload_file first to get a URL."
        ),
        input_schema=_DETECT_FACES_INPUT_SCHEMA,
        annotations={
            "title": "Detect and obscure faces in an image",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        units_fn=_units_from_url,
        handler=_detect_faces,
    ),
}


def list_tool_descriptors() -> list[dict[str, Any]]:
    """Build the tools/list response payload."""
    return [
        {
            "name": spec.name,
            "title": spec.title,
            "description": spec.description,
            "inputSchema": spec.input_schema,
            "annotations": spec.annotations,
        }
        for spec in TOOLS.values()
    ]
