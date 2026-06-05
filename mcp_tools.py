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
# Phase 2 minimal vertical slice: one tool (summarize_document) end-to-end.
# Remaining tools (translate, redact_pii, analyze_image, detect_faces,
# transcribe_audio) get added in follow-up commits using the same shape.

from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from flask import current_app
from werkzeug.datastructures import FileStorage

from auth import Principal

logger = logging.getLogger(__name__)


SUPPORTED_DOC_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}
MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB — same cap as /api/v1/summarize


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


# --- summarize_document --------------------------------------------------------


_SUMMARIZE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the document with its extension (.pdf, .docx, .pptx, .xlsx).",
        },
        "content_base64": {
            "type": "string",
            "description": "Base64-encoded contents of the document. Decoded size must not exceed 10 MB.",
        },
    },
    "required": ["filename", "content_base64"],
    "additionalProperties": False,
}


def _summarize_units(args: dict) -> int:
    """Estimate units before calling Gemini: ~1 unit per 50 KB of decoded bytes."""
    encoded = args.get("content_base64") or ""
    # Length of base64 -> approx bytes without decoding (4 chars per 3 bytes).
    approx_bytes = (len(encoded) * 3) // 4
    return max(1, approx_bytes // (50 * 1024))


class ToolError(Exception):
    """Raised by tool handlers for argument / input failures.

    The MCP route translates this to a JSON-RPC error with code -32602
    (Invalid params). Note: tool-internal failures (e.g. Gemini returned an
    error event) re-raise as RuntimeError so run_metered_tool's refund path
    kicks in and the call is metered as 'refunded'.
    """


def _summarize_document(principal: Principal, args: dict) -> dict:
    """summarize_document tool implementation.

    Mirrors /api/v1/summarize behavior so MCP and direct-API callers get the
    same result. Tenancy: all metering inside run_metered_tool() scopes on
    principal.org_id; this handler does no direct DB writes.
    """
    if not current_app.config.get("GEMINI_CONFIGURED"):
        raise RuntimeError("Gemini AI service is not configured.")

    filename = (args.get("filename") or "").strip()
    if not filename:
        raise ToolError("Missing 'filename'")

    _, ext = os.path.splitext(filename.lower())
    if ext not in SUPPORTED_DOC_EXTENSIONS:
        raise ToolError(
            f"Unsupported file type {ext}. Allowed: {sorted(SUPPORTED_DOC_EXTENSIONS)}"
        )

    encoded = args.get("content_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ToolError("Missing 'content_base64'")

    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as e:
        raise ToolError(f"content_base64 is not valid base64: {e}") from e

    if len(raw) > MAX_DOC_BYTES:
        raise ToolError(f"Decoded content exceeds {MAX_DOC_BYTES} bytes")

    # Wrap in a FileStorage so the existing extractor (which uses werkzeug's
    # file interface) works unchanged.
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


# --- Registry ------------------------------------------------------------------


TOOLS: dict[str, ToolSpec] = {
    "summarize_document": ToolSpec(
        name="summarize_document",
        title="Summarize a document",
        description=(
            "Classify and summarize a PDF, DOCX, PPTX, or XLSX file. "
            "Returns the inferred document type and a structured Markdown summary. "
            "Accepts the file as base64-encoded bytes (max 10 MB decoded)."
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
        units_fn=_summarize_units,
        handler=_summarize_document,
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
