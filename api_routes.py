# api_routes.py
# JSON API surface, distinct from the HTML/HTMX feature blueprints. These routes
# are the proving ground for `@require_auth` and the eventual backing for the
# MCP server's tool handlers (Phase 2). All endpoints are protected by an
# `sk_synzo_...` API key in the `Authorization: Bearer ...` header.
import io
import json
import logging
import os

import google.generativeai as genai
from flask import Blueprint, current_app, jsonify, request

from auth import require_auth
from features.summarization import utils as summarization_utils
from features.summarization.agents import analyst_agent

logger = logging.getLogger(__name__)

bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Per-call cap on document size (bytes). Above this we 413 before spending Gemini.
MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}


def _estimate_units(req) -> int:
    """Rough page-count estimate from upload size: 1 unit per ~50 KB.

    Used by `require_auth(units_fn=...)` to enforce the plan's per-call cap
    before we run the handler. Conservative — we'd rather 413 a small doc than
    blow through quota on a large one.
    """
    file = req.files.get("file")
    if not file:
        return 1
    file.stream.seek(0, io.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    return max(1, size // (50 * 1024))


@bp.route("/summarize", methods=["POST"])
@require_auth(tool_name="summarize_document", units_fn=_estimate_units)
def api_summarize():
    """JSON summarization endpoint — POC for the auth + quota pipeline.

    Request:  multipart/form-data with `file` field. PDF/DOCX/PPTX/XLSX.
    Response: {"classification": str, "summary": str} on success.
    Auth:     Authorization: Bearer sk_synzo_<key>
    """
    if not current_app.config.get("GEMINI_CONFIGURED"):
        return jsonify({"error": "Gemini AI service is not configured."}), 503

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Missing 'file' in request"}), 400

    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type {ext}. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        }), 415

    file.stream.seek(0, io.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > MAX_DOC_BYTES:
        return jsonify({"error": f"File exceeds {MAX_DOC_BYTES} bytes"}), 413

    text, filename = summarization_utils.read_text_from_file(file)
    if not text:
        return jsonify({"error": "Could not extract text from the file."}), 400

    model_name = current_app.config.get("GEMINI_MODEL_NAME")

    # Reuse the existing analyst generator but collect into one response. The
    # generator yields NDJSON lines: `{"type": "meta", ...}`, `{"type": "chunk", ...}`,
    # `{"type": "error", ...}`. We fold them into a single non-streamed reply
    # that's easy to consume from curl and from the MCP tool handler later.
    classification = None
    chunks: list[str] = []
    for line in analyst_agent.stream_analysis(text, model_name, filename):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "meta":
            classification = event.get("classification")
        elif event.get("type") == "chunk":
            chunks.append(event.get("content", ""))
        elif event.get("type") == "error":
            # Let require_auth's refund-on-exception path handle metering.
            raise RuntimeError(event.get("content", "AI service error"))

    return jsonify({
        "classification": classification,
        "summary": "".join(chunks),
    })
