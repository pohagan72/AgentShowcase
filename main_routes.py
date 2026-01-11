# main_routes.py
from flask import Blueprint, render_template, redirect, url_for, current_app

# Define the Blueprint
bp = Blueprint('main', __name__)

# UI Configuration (The Sidebar Menu)
FEATURES_DATA = {
    "welcome": {
        "name": "Welcome", 
        "icon": "ph ph-house",  # Cleaner home icon
        "template": "partials/_welcome_content.html"
    },
    "summarization": {
        "name": "The Executive Briefer", 
        "icon": "ph ph-article", # Matches "Briefing" better than a briefcase
        "template": "summarization/templates/summarization_content.html"
    },
    "translation": {
        "name": "The Global Localizer", 
        "icon": "ph ph-translate", # Specific translation icon
        "template": "translation/templates/translation_content.html"
    },
    "pii_redaction": {
        "name": "The Compliance Guardian", 
        "icon": "ph ph-shield-check", # Modern security shield
        "template": "pii_redaction/templates/pii_redaction_content.html"
    },
    "multimedia": {
        "name": "The Visual Analyst", 
        "icon": "ph ph-aperture", # Camera aperture implies "Vision/AI"
        "template": "multimedia/templates/multimedia_content.html"
    },
    "info": {
        "name": "Meet the Architect", 
        "icon": "ph ph-fingerprint", # More personal/unique than "user tie"
        "template": "info/templates/info_content.html"
    },
}

DEFAULT_FEATURE_KEY = "welcome"

@bp.route('/')
def root_redirect():
    return redirect(url_for('main.index', feature_key=DEFAULT_FEATURE_KEY))

@bp.route('/feature/<feature_key>')
def index(feature_key):
    if feature_key not in FEATURES_DATA:
        feature_key = DEFAULT_FEATURE_KEY

    current_feature_data = FEATURES_DATA[feature_key]
    initial_content_template_path = current_feature_data["template"]

    # Gather global context variables
    template_context = {
        "gcs_available": current_app.config.get('GCS_AVAILABLE', False),
        "gemini_configured": current_app.config.get('GEMINI_CONFIGURED', False)
    }

    # Add Feature-Specific Context
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

    # Re-inject feature specific context for HTMX requests
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