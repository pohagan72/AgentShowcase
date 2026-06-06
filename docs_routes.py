# docs_routes.py
# Public-facing documentation, privacy policy, support, and security pages.
# These are the three submission-form-required URLs (Docs / Privacy / Support)
# plus a /security page that backs `security@synzo.ai` disclosure per Anthropic
# Software Directory Terms.
#
# All routes are unauthenticated (public-site surface per MCP_SUBMISSION_PLAN §3.3),
# render layout.html with a partial as the `initial_content_template` (same shape
# as /pricing in main_routes.py), and are linked from the global footer.
#
# Phase 3 status: routes + footer + minimal stubs only. Content fill-in tracked
# in MCP_SUBMISSION_PLAN.md §6 Phase 3.
from flask import Blueprint, current_app, render_template
from markupsafe import Markup

from main_routes import FEATURES_DATA, DEFAULT_FEATURE_KEY

bp = Blueprint("docs", __name__)


def _render_static_page(active_key: str, partial: str, page_name: str, **extra):
    """Shared shell render for the four static public pages."""
    return render_template(
        "layout.html",
        features=FEATURES_DATA,
        current_feature={"name": page_name},
        active_feature_key=active_key,
        initial_content_template=partial,
        DEFAULT_FEATURE_KEY=DEFAULT_FEATURE_KEY,
        gcs_available=False,
        gemini_configured=False,
        **extra,
    )


@bp.route("/docs")
def docs():
    # Pre-rendered at create_app() startup from mcp_tools.TOOLS x docs/tool_examples.yaml;
    # wrap as Markup so Jinja emits the raw HTML instead of escaping it.
    tools_table_rows = Markup(current_app.config.get("DOCS_TOOLS_TABLE_HTML", ""))
    return _render_static_page(
        "docs",
        "partials/_docs_content.html",
        "Docs",
        tools_table_rows=tools_table_rows,
    )


@bp.route("/privacy")
def privacy():
    return _render_static_page("privacy", "partials/_privacy_content.html", "Privacy Policy")


@bp.route("/support")
def support():
    return _render_static_page("support", "partials/_support_content.html", "Support")


@bp.route("/security")
def security():
    return _render_static_page("security", "partials/_security_content.html", "Security")


@bp.route("/terms")
def terms():
    return _render_static_page("terms", "partials/_terms_content.html", "Terms of Service")
