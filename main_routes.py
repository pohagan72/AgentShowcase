# main_routes.py
from flask import Blueprint, render_template, current_app, request, make_response, url_for

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

@bp.route('/pricing')
def pricing():
    """Public marketing page. Reads plan numbers live from auth.PLANS so the
    page never drifts from the actual enforcement (plan s6.5.K.2)."""
    from auth import PLANS

    # Static descriptors (CTA target, marketing copy) keyed by plan id; the
    # numeric limits come from PLANS so a tuning change in auth.py updates this
    # page automatically.
    plan_meta = {
        "free": {
            "title": "Free",
            "tagline": "For evaluation and personal projects.",
            "cta_label": "Sign up free",
            "cta_href": url_for("auth.login"),
            "cta_disabled": False,
        },
        "starter": {
            "title": "Starter",
            "tagline": "For small teams and side projects in production.",
            "cta_label": "Contact us",
            "cta_href": "mailto:paul@synzo.ai?subject=Synzo%20Starter%20plan",
            "cta_disabled": False,
        },
        "pro": {
            "title": "Pro",
            "tagline": "For teams running Synzo as core infrastructure.",
            "cta_label": "Contact sales",
            "cta_href": "mailto:paul@synzo.ai?subject=Synzo%20Pro%20plan",
            "cta_disabled": False,
        },
    }

    tiers = []
    for key in ("free", "starter", "pro"):
        if key not in PLANS:
            continue
        tiers.append({
            "key": key,
            "limits": PLANS[key],
            **plan_meta.get(key, {}),
        })

    return render_template(
        "layout.html",
        features=FEATURES_DATA,
        current_feature={"name": "Pricing"},
        active_feature_key="pricing",
        initial_content_template="partials/_pricing_content.html",
        DEFAULT_FEATURE_KEY=DEFAULT_FEATURE_KEY,
        tiers=tiers,
        gcs_available=False,
        gemini_configured=False,
    )


@bp.route('/benchmark')
def benchmark():
    """Public research page presenting the TranslationBench results that
    inform Synzo's translation architecture. Numbers here come from a single
    500-segment run against Canadian Hansard EN↔FR on gemini-3.6-flash with
    adaptive thinking (same model Synzo runs in production); the raw JSON,
    per-segment scores, and harness source are on GitHub for verification.
    Keep this data in sync with `out-final/report.json` in the
    TranslationBench repo.
    """
    results = {
        "model": "gemini-3.6-flash (adaptive thinking, same model Synzo runs)",
        "corpus": "Canadian Hansard EN↔FR (parliamentary proceedings)",
        "segments": 500,
        "seed": 42,
        "sentence": {"bleu": 38.13, "chrf": 63.15, "comet": 0.8547, "cost_usd": 2.28},
        "context":  {"bleu": 38.63, "chrf": 62.94, "comet": 0.8595, "cost_usd": 0.71},
        "comet_delta": +0.0048,
        "comet_ci_low": +0.0003,
        "comet_ci_high": +0.0093,
        "bottom_50_sentence_avg_comet": 0.6314,
        "bottom_50_context_avg_comet":  0.6682,
        "wins": 155,
        "losses": 126,
        # Concrete before/after quotes — every one is a real segment from the
        # 500-run, chosen because its COMET delta shows the pattern clearly.
        "wins_examples": [
            {
                "en": "I do not believe this is what my constituents want.",
                "ref": "Je ne pense pas que c'est ce que mes électeurs recherchent.",
                "sentence": "Je ne crois pas que ce soit ce que mes commettants veulent.",
                "context": "Je ne crois pas que ce soit ce que mes électeurs veulent.",
                "sentence_comet": 0.6048,
                "context_comet": 0.9394,
                "note": "Sentence mode picked <em>commettants</em>, dated legalese. "
                        "Context saw the surrounding parliamentary register and "
                        "chose <em>électeurs</em>, which is what the reference used.",
            },
            {
                "en": "We are concerned with a statute.",
                "ref": "Il s'agit d'une loi.",
                "sentence": "Nous sommes concernés par une loi.",
                "context": "Il s'agit d'une loi.",
                "sentence_comet": 0.6902,
                "context_comet": 0.9849,
                "note": "&ldquo;Concerned with&rdquo; is idiomatic for &ldquo;this is about&rdquo;. "
                        "Sentence mode calqued it word-for-word. Context "
                        "produced the idiomatic French, matching the reference exactly.",
            },
        ],
        "losses_example": {
            "en": "Mr. Speaker, I ask that the remaining questions be allowed to stand.",
            "ref": "Monsieur le Président, je demande que les autres questions restent au Feuilleton.",
            "sentence": "Monsieur le Président, je demande que les autres questions restent en instance.",
            "context": "Monsieur le Président, je demande que les autres questions restent en souffrance.",
            "sentence_comet": 0.7970,
            "context_comet": 0.4873,
            "note": "Not every context-mode change is an improvement. Here, "
                    "<em>en souffrance</em> implies unpaid mail; the correct "
                    "parliamentary term is <em>en instance</em> (still deferred) — "
                    "which sentence mode produced. Twenty-four of 500 segments "
                    "regressed like this. We report both the wins and losses.",
        },
        "repo_url": "https://github.com/pohagan72/TranslationBench",
        "raw_json_url": "https://github.com/pohagan72/TranslationBench/blob/main/out-final/report.json",
    }
    return render_template(
        "layout.html",
        features=FEATURES_DATA,
        current_feature={"name": "Benchmark"},
        active_feature_key="benchmark",
        initial_content_template="partials/_benchmark_content.html",
        DEFAULT_FEATURE_KEY=DEFAULT_FEATURE_KEY,
        results=results,
        gcs_available=False,
        gemini_configured=False,
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

    # /pricing is a public marketing page; index it alongside the features.
    xml_sitemap.append(f"""
                <url>
                    <loc>{host}/pricing</loc>
                    <changefreq>weekly</changefreq>
                    <priority>0.9</priority>
                </url>
            """)

    # /benchmark is a public research page with our translation-quality data.
    xml_sitemap.append(f"""
                <url>
                    <loc>{host}/benchmark</loc>
                    <changefreq>monthly</changefreq>
                    <priority>0.7</priority>
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