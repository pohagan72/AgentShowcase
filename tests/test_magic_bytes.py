# tests/test_magic_bytes.py
# Tests for the magic-byte verification added in Phase 3 technical hardening.
# Extension-only checks let a malicious or careless caller smuggle one file
# type inside another's wrapper (.docx whose bytes are actually a PDF, .jpg
# whose bytes are a zip bomb, etc.). mcp_tools._verify_magic_bytes uses the
# `filetype` lib to peek at the actual content and reject mismatches.
#
# These tests prove:
# 1. The helper accepts genuine files of every supported extension.
# 2. The helper rejects extension/content mismatches (PDF bytes inside .docx,
#    DOCX bytes inside .jpg, image bytes inside a document extension, etc.).
# 3. End-to-end through /mcp tools/call: a mismatched payload surfaces as
#    isError=true (not a JSON-RPC envelope error, so the model can recover)
#    AND the quota is refunded (the caller doesn't pay for our reject).

from __future__ import annotations

import base64
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from db import db
from db.models import ApiKey, Org, OrgMembership, Quota, UsageEvent, User


# --- helpers (mirror test_mcp_server.py's seed shape) -------------------------


def _seed_org(app, *, name, plan="free"):
    from auth import PLANS, _period_bounds, issue_api_key

    with app.app_context():
        org = Org(workos_org_id=f"workos_{name}", name=name, plan=plan)
        db.session.add(org)
        db.session.flush()
        user = User(workos_user_id=f"workos_user_{name}", email=f"{name}@example.com")
        db.session.add(user)
        db.session.flush()
        db.session.add(OrgMembership(user_id=user.id, org_id=org.id, role="owner"))

        period_start, period_end = _period_bounds(datetime.now(timezone.utc))
        existing = (
            db.session.query(Quota)
            .filter_by(org_id=org.id, period_start=period_start)
            .one_or_none()
        )
        if existing is None:
            db.session.add(
                Quota(
                    org_id=org.id,
                    period_start=period_start,
                    period_end=period_end,
                    calls_remaining=PLANS[plan]["calls_per_month"],
                    calls_limit=PLANS[plan]["calls_per_month"],
                )
            )
        db.session.commit()
        raw_key, key_record = issue_api_key(org_id=org.id, name=f"{name}-key")
        return {
            "org_id": org.id,
            "auth_header": {"Authorization": f"Bearer {raw_key}"},
        }


def _rpc(client, method, params=None, *, headers=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(
        "/mcp",
        data=json.dumps(body),
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def _ooxml(kind: str) -> bytes:
    """Tiny valid OOXML zip for kind in {'docx','pptx','xlsx'}."""
    marker = {"docx": "word/", "pptx": "ppt/", "xlsx": "xl/"}[kind]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr(marker + "document.xml", "<x/>")
    return buf.getvalue()


# Minimum byte stubs that filetype.guess() recognizes for each type.
PDF_BYTES = b"%PDF-1.4 stub"
JPG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF stub"
PNG_BYTES = b"\x89PNG\r\n\x1a\n stub"
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8  stub"
# Real-shaped HEIC ftyp box (size=0x20, type=ftyp, brand=heic).
HEIC_BYTES = bytes.fromhex("0000002066747970686569630000000068656963") + b"\x00" * 100


# --- 1. Helper unit-level: accepts genuine files ------------------------------


def test_verify_magic_bytes_accepts_genuine_pdf():
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(PDF_BYTES, ".pdf")  # must not raise


def test_verify_magic_bytes_accepts_genuine_docx():
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(_ooxml("docx"), ".docx")


def test_verify_magic_bytes_accepts_genuine_pptx():
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(_ooxml("pptx"), ".pptx")


def test_verify_magic_bytes_accepts_genuine_xlsx():
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(_ooxml("xlsx"), ".xlsx")


def test_verify_magic_bytes_accepts_genuine_jpg_for_both_jpg_and_jpeg_exts():
    """filetype reports JPG bytes as 'jpg'; we accept both .jpg and .jpeg
    filenames since they're the same format."""
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(JPG_BYTES, ".jpg")
    _verify_magic_bytes(JPG_BYTES, ".jpeg")


def test_verify_magic_bytes_accepts_genuine_png():
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(PNG_BYTES, ".png")


def test_verify_magic_bytes_accepts_genuine_webp():
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(WEBP_BYTES, ".webp")


def test_verify_magic_bytes_accepts_genuine_heic_for_both_heic_and_heif_exts():
    """HEIF files in the wild use the same ISO BMFF container; filetype
    reports both as 'heic'. We accept either filename extension."""
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(HEIC_BYTES, ".heic")
    _verify_magic_bytes(HEIC_BYTES, ".heif")


# --- 2. Helper unit-level: rejects mismatches ---------------------------------


def test_verify_magic_bytes_rejects_pdf_bytes_inside_docx_extension():
    from mcp_tools import _verify_magic_bytes, ToolError
    with pytest.raises(ToolError, match="does not match extension .docx"):
        _verify_magic_bytes(PDF_BYTES, ".docx")


def test_verify_magic_bytes_rejects_docx_bytes_inside_pdf_extension():
    from mcp_tools import _verify_magic_bytes, ToolError
    with pytest.raises(ToolError, match="does not match extension .pdf"):
        _verify_magic_bytes(_ooxml("docx"), ".pdf")


def test_verify_magic_bytes_rejects_jpg_inside_png_extension():
    from mcp_tools import _verify_magic_bytes, ToolError
    with pytest.raises(ToolError, match="does not match extension .png"):
        _verify_magic_bytes(JPG_BYTES, ".png")


def test_verify_magic_bytes_rejects_docx_bytes_inside_pptx_extension():
    """The OOXML peek MUST distinguish docx from pptx — both are zips but
    have different marker directories. A .pptx with word/ inside is wrong."""
    from mcp_tools import _verify_magic_bytes, ToolError
    with pytest.raises(ToolError, match="does not match extension .pptx"):
        _verify_magic_bytes(_ooxml("docx"), ".pptx")


def test_verify_magic_bytes_rejects_xlsx_inside_docx_extension():
    from mcp_tools import _verify_magic_bytes, ToolError
    with pytest.raises(ToolError, match="does not match extension .docx"):
        _verify_magic_bytes(_ooxml("xlsx"), ".docx")


def test_verify_magic_bytes_rejects_random_garbage_inside_pdf_extension():
    from mcp_tools import _verify_magic_bytes, ToolError
    with pytest.raises(ToolError, match="does not match extension .pdf"):
        _verify_magic_bytes(b"this is just plain text not a pdf", ".pdf")


def test_verify_magic_bytes_message_includes_detected_type():
    """Error message must name what the bytes actually were so the model can
    react sensibly (e.g. retry with the correct extension)."""
    from mcp_tools import _verify_magic_bytes, ToolError
    with pytest.raises(ToolError, match=r"detected: pdf"):
        _verify_magic_bytes(PDF_BYTES, ".docx")


# --- 3. End-to-end through /mcp: mismatch -> isError + quota refunded --------


def test_mcp_summarize_with_jpg_inside_pdf_extension_isError_and_refunds(
    client, app, url_for_bytes
):
    """A .pdf filename whose bytes are actually a JPG must surface to the
    model as a tool error (isError=true), and the quota must be refunded so
    the caller doesn't pay for our reject."""
    app.config["GEMINI_CONFIGURED"] = True
    org = _seed_org(app, name="magic_summarize_pdf_with_jpg")

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "summarize_document",
            "arguments": {
                "filename": "actually-a-photo.pdf",
                "content_url": url_for_bytes(JPG_BYTES, filename="actually-a-photo.pdf"),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert "error" not in body, body
    assert body["result"]["isError"] is True
    text = body["result"]["content"][0]["text"]
    assert "does not match extension" in text.lower()

    with app.app_context():
        events = db.session.query(UsageEvent).filter_by(org_id=org["org_id"]).all()
        assert "refunded" in {e.status for e in events}
        quota = db.session.query(Quota).filter_by(org_id=org["org_id"]).one()
        assert quota.calls_remaining == quota.calls_limit


def test_mcp_translate_with_pdf_inside_docx_extension_isError_and_refunds(
    client, app, url_for_bytes
):
    app.config["GEMINI_CONFIGURED"] = True
    org = _seed_org(app, name="magic_translate_docx_with_pdf")

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "translate_document",
            "arguments": {
                "filename": "actually-a-pdf.docx",
                "content_url": url_for_bytes(PDF_BYTES, filename="actually-a-pdf.docx"),
                "target_language": "Spanish",
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True

    with app.app_context():
        quota = db.session.query(Quota).filter_by(org_id=org["org_id"]).one()
        assert quota.calls_remaining == quota.calls_limit


def test_mcp_redact_pii_with_jpg_inside_docx_extension_isError(client, app, url_for_bytes):
    app.config["PRESIDIO_ANALYZER_AVAILABLE"] = True
    app.presidio_analyzer = object()
    org = _seed_org(app, name="magic_redact_docx_with_jpg")

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "redact_pii",
            "arguments": {
                "filename": "actually-a-photo.docx",
                "content_url": url_for_bytes(JPG_BYTES, filename="actually-a-photo.docx"),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True
    assert "does not match extension" in body["result"]["content"][0]["text"].lower()


def test_mcp_analyze_image_with_pdf_inside_jpg_extension_isError(client, app, url_for_bytes):
    app.config["GEMINI_CONFIGURED"] = True
    org = _seed_org(app, name="magic_analyze_jpg_with_pdf")

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "analyze_image",
            "arguments": {
                "filename": "actually-a-pdf.jpg",
                "content_url": url_for_bytes(PDF_BYTES, filename="actually-a-pdf.jpg"),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True


def test_mcp_detect_faces_with_docx_inside_jpg_extension_isError(client, app, url_for_bytes):
    org = _seed_org(app, name="magic_faces_jpg_with_docx")

    resp = _rpc(
        client,
        "tools/call",
        {
            "name": "detect_faces",
            "arguments": {
                "filename": "actually-a-doc.jpg",
                "content_url": url_for_bytes(_ooxml("docx"), filename="actually-a-doc.jpg"),
            },
        },
        headers=org["auth_header"],
    )
    body = resp.get_json()
    assert body["result"]["isError"] is True


# --- 4. Helper: ext not in our matrix is a no-op (defensive) ------------------


def test_verify_magic_bytes_unknown_extension_is_a_no_op():
    """Belt-and-braces: per-tool ext-set check runs first, so the helper
    should never see an extension not in _VALID_DETECTED_FOR_EXT. If it
    does, don't crash — the per-tool ext check will reject it already."""
    from mcp_tools import _verify_magic_bytes
    _verify_magic_bytes(b"random bytes", ".xyz")  # must not raise
