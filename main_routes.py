# main_routes.py
from flask import Blueprint, render_template, current_app, request, make_response

# Define the Blueprint
bp = Blueprint('main', __name__)

# UI Configuration with SEO-Friendly Routes
FEATURES_DATA = {
    "welcome": {
        "name": "Welcome", 
        "icon": "synzo-welcome-icon.png", # Updated
        "template": "partials/_welcome_content.html",
        "route": "/" 
    },
    "summarization": {
        "name": "The Executive Briefer", 
        "icon": "synzo-executive-briefer-icon.png", # Updated
        "template": "summarization/templates/summarization_content.html",
        "route": "/summarizer" 
    },
    "translation": {
        "name": "The Global Localizer", 
        "icon": "synzo-translation-icon.png", # Updated
        "template": "translation/templates/translation_content.html",
        "route": "/translator" 
    },
    "pii_redaction": {
        "name": "The Compliance Guardian", 
        "icon": "synzo-guardian-icon.png", # Updated
        "template": "pii_redaction/templates/pii_redaction_content.html",
        "route": "/redactor" 
    },
    "multimedia": {
        "name": "The Visual Analyst", 
        "icon": "synzo-visual-analyst-icon.png", # Updated
        "template": "multimedia/templates/multimedia_content.html",
        "route": "/vision" 
    },
    "info": {
        "name": "Meet the Architect", 
        "icon": "synzo-about-me-icon.png", # Updated
        "template": "info/templates/info_content.html",
        "route": "/about"
    },
}

DEFAULT_FEATURE_KEY = "welcome"

# --- NEW: SEO-Friendly Route Definitions ---
# We map multiple URLs to the same 'index' function, but pass different defaults.

@bp.route('/', defaults={'feature_key': 'welcome'})
@bp.route('/summarizer', defaults={'feature_key': 'summarization'})
@bp.route('/translator', defaults={'feature_key': 'translation'})
@bp.route('/redactor', defaults={'feature_key': 'pii_redaction'})
@bp.route('/vision', defaults={'feature_key': 'multimedia'})
@bp.route('/about', defaults={'feature_key': 'info'})
# Keep the old route for internal HTMX calls if needed, but don't link to it
@bp.route('/feature/<feature_key>') 
def index(feature_key):
    # Fallback if an invalid key is forced via URL
    if feature_key not in FEATURES_DATA:
        feature_key = DEFAULT_FEATURE_KEY

    current_feature_data = FEATURES_DATA[feature_key]
    initial_content_template_path = current_feature_data["template"]

    # Gather global context variables
    template_context = {
        "gcs_available": current_app.config.get('GCS_AVAILABLE', False),
        "gemini_configured": current_app.config.get('GEMINI_CONFIGURED', False)
    }

    # Feature-Specific Context (Same logic as before)
    if feature_key == "translation":
        template_context["languages"] = current_app.config.get('TRANSLATION_LANGUAGES', [])
    elif feature_key == "summarization":
        ppt_services_ready = template_context["gemini_configured"] and template_context["gcs_available"]
        template_context["ppt_api_key_configured"] = ppt_services_ready
        template_context["ppt_max_files"] = current_app.config.get('PPT_MAX_FILES')
        template_context["ppt_max_file_size_mb"] = current_app.config.get('PPT_MAX_FILE_SIZE_MB')
        template_context["ppt_allowed_extensions_str"] = current_app.config.get('PPT_ALLOWED_EXTENSIONS_STR')
        template_context["ppt_default_template"] = current_app.config.get('PPT_DEFAULT_TEMPLATE_NAME')
        template_context["ppt_config_warning"] = None
        if not ppt_services_ready:
            if not template_context["gemini_configured"]:
                template_context["ppt_config_warning"] = "Gemini AI service is not configured."
            elif not template_context["gcs_available"]:
                template_context["ppt_config_warning"] = "Cloud Storage is not configured."
    elif feature_key == "pii_redaction":
        template_context["presidio_available"] = current_app.config.get('PRESIDIO_ANALYZER_AVAILABLE', False)
        template_context["services_ready"] = template_context["presidio_available"] and template_context["gcs_available"]

    return render_template(
        'layout.html',
        features=FEATURES_DATA,
        current_feature=current_feature_data,
        active_feature_key=feature_key,
        initial_content_template=initial_content_template_path,
        DEFAULT_FEATURE_KEY=DEFAULT_FEATURE_KEY,
        **template_context
    )

@bp.route('/sitemap.xml')
def sitemap():
    host = request.host_url.rstrip('/')
    xml_sitemap = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_sitemap.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # Iterate through your FEATURES_DATA to build links
    for key, data in FEATURES_DATA.items():
        # Skip internal/hidden routes if any
        route = data.get('route')
        if route:
            url = f"{host}{route}"
            xml_sitemap.append(f"""
                <url>
                    <loc>{url}</loc>
                    <changefreq>weekly</changefreq>
                    <priority>{'1.0' if route == '/' else '0.8'}</priority>
                </url>
            """)
    
    xml_sitemap.append('</urlset>')
    response = make_response('\n'.join(xml_sitemap))
    response.headers["Content-Type"] = "application/xml"
    return response

@bp.route('/robots.txt')
def robots():
    host = request.host_url.rstrip('/')
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {host}/sitemap.xml"
    ]
    response = make_response('\n'.join(lines))
    response.headers["Content-Type"] = "text/plain"
    return response

# HTMX Specific Endpoint (Keep this for partial reloads)
@bp.route('/content/<feature_key>')
def get_feature_content(feature_key):
    if feature_key not in FEATURES_DATA:
        return "Feature content not found", 404

    feature_data = FEATURES_DATA[feature_key]
    template_to_render = feature_data["template"]

    context = {
        "gcs_available": current_app.config.get('GCS_AVAILABLE', False),
        "gemini_configured": current_app.config.get('GEMINI_CONFIGURED', False)
    }

    # Re-inject feature specific context (Same logic as above)
    if feature_key == "translation":
        context["languages"] = current_app.config.get('TRANSLATION_LANGUAGES', [])
    elif feature_key == "summarization":
        context["summary"] = ""
        context["hx_target_is_result"] = False
        context["ppt_max_files"] = current_app.config.get('PPT_MAX_FILES')
        context["ppt_max_file_size_mb"] = current_app.config.get('PPT_MAX_FILE_SIZE_MB')
        context["ppt_allowed_extensions_str"] = current_app.config.get('PPT_ALLOWED_EXTENSIONS_STR')
        context["ppt_templates"] = current_app.config.get('PPT_TEMPLATES')
        context["ppt_default_template"] = current_app.config.get('PPT_DEFAULT_TEMPLATE_NAME')
        ppt_services_ready = context["gemini_configured"] and context["gcs_available"]
        context["ppt_api_key_configured"] = ppt_services_ready
        context["ppt_config_warning"] = None
        if not ppt_services_ready:
            if not context["gemini_configured"]: context["ppt_config_warning"] = "Gemini AI service is not configured."
            elif not context["gcs_available"]: context["ppt_config_warning"] = "Cloud Storage is not configured."
            else: context["ppt_config_warning"] = "Core services for PPT generation are unavailable."
    elif feature_key == "pii_redaction":
        context["redacted_file_url"] = None
        context["original_filename"] = None
        context["presidio_available"] = current_app.config.get('PRESIDIO_ANALYZER_AVAILABLE', False)
        context["hx_target_is_result"] = False
        context["services_ready"] = context["presidio_available"] and context["gcs_available"]

    return render_template(template_to_render, **context)