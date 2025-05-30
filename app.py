from flask import Flask, render_template, request, url_for, current_app, redirect
import os
from jinja2 import ChoiceLoader, FileSystemLoader
from dotenv import load_dotenv

# --- For Translation & Summarization Feature Global Imports ---
import google.generativeai as genai
from google.cloud import storage
from google.cloud.exceptions import NotFound

# --- For PII Redaction Feature Global Imports ---
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
import logging # For Presidio and general logging
# --- End PII Redaction Imports ---

load_dotenv()

app = Flask(__name__)

# --- Configure Logging (Optional but good practice) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# --- End Logging Configuration ---


# --- Configure Jinja2 Template Loader ---
app.jinja_loader = ChoiceLoader([
    app.jinja_loader,
    FileSystemLoader('features')
])
# --- End Jinja2 Configuration ---


# --- Application Configuration from Environment Variables ---
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_strong_default_secret_key_for_dev_only_32_chars_long_replace_this")
if app.secret_key == "a_very_strong_default_secret_key_for_dev_only_32_chars_long_replace_this" and os.environ.get("FLASK_ENV") != "development":
    print("WARNING: Using default FLASK_SECRET_KEY. Set a strong, unique key in your environment for production!")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-latest")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")

app.config['GOOGLE_API_KEY'] = GOOGLE_API_KEY
app.config['GEMINI_MODEL_NAME'] = GEMINI_MODEL_NAME
app.config['GCS_BUCKET_NAME'] = GCS_BUCKET_NAME
app.config['GOOGLE_CLOUD_PROJECT'] = GOOGLE_CLOUD_PROJECT


# --- Initialize Google Services (Gemini & GCS) Globally ---
app.config['GEMINI_CONFIGURED'] = False
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        app.config['GEMINI_CONFIGURED'] = True
        logging.info("Global: Google Gemini API configured successfully.")
    except Exception as e:
        logging.error(f"Global: Failed to configure Google Gemini API: {e}")
else:
    logging.warning("Global: GOOGLE_API_KEY not found. Gemini-dependent features may be affected.")

app.config['GCS_AVAILABLE'] = False
app.storage_client = None
app.gcs_bucket = None
if GCS_BUCKET_NAME and GOOGLE_CLOUD_PROJECT:
    try:
        app.storage_client = storage.Client(project=GOOGLE_CLOUD_PROJECT)
        app.gcs_bucket = app.storage_client.bucket(GCS_BUCKET_NAME)
        app.gcs_bucket.reload()
        app.config['GCS_AVAILABLE'] = True
        logging.info(f"Global: GCS client initialized (Bucket: gs://{GCS_BUCKET_NAME}).")
    except NotFound:
        logging.error(f"Global: GCS Bucket '{GCS_BUCKET_NAME}' not found. GCS-dependent features will fail.")
        app.storage_client = None; app.gcs_bucket = None # Clear on error
    except Exception as e:
        logging.error(f"Global: Failed to initialize GCS client: {e}. GCS-dependent features will fail.")
        app.storage_client = None; app.gcs_bucket = None # Clear on error
else:
    if not GCS_BUCKET_NAME: logging.warning("Global: GCS_BUCKET_NAME env var not found.")
    if not GOOGLE_CLOUD_PROJECT: logging.warning("Global: GOOGLE_CLOUD_PROJECT env var not found.")
    logging.warning("Global: GCS client not initialized. GCS-dependent features may be affected.")


# --- Initialize Presidio Analyzer Engine Globally ---
app.config['PRESIDIO_ANALYZER_AVAILABLE'] = False
app.presidio_analyzer = None
try:
    logging.info("Global: Initializing Presidio Analyzer Engine...")
    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}]
    })
    app.presidio_analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    app.config['PRESIDIO_ANALYZER_AVAILABLE'] = True
    logging.info("Global: Presidio Analyzer Engine initialized successfully.")
except Exception as e:
    logging.error(f"Global: Failed to initialize Presidio Analyzer Engine: {e}. PII Redaction feature will be affected.", exc_info=True)
    app.presidio_analyzer = None
# --- End Presidio Analyzer Initialization ---


# --- Data for our features (UI driven for sidebar and content loading) ---
FEATURES_DATA = {
    "welcome": {"name": "Welcome", "icon": "fas fa-home", "template": "partials/_welcome_content.html"},
    "transcription": {"name": "Transcription", "icon": "fas fa-microphone-alt", "template": "transcription/templates/transcription_content.html"},
    "translation": {"name": "Translation", "icon": "fas fa-language", "template": "translation/templates/translation_content.html"},
    "summarization": {"name": "Summarization", "icon": "fas fa-file-alt", "template": "summarization/templates/summarization_content.html"},
    "pii_redaction": {"name": "PII Redaction", "icon": "fas fa-user-shield", "template": "pii_redaction/templates/pii_redaction_content.html"},
    "blurring": {"name": "Blurring", "icon": "fas fa-eye-slash", "template": "blurring/templates/blurring_content.html"},
    "info": {"name": "Information", "icon": "fas fa-info-circle", "template": "info/templates/info_content.html"},
}
DEFAULT_FEATURE_KEY = "welcome"

# --- For Translation Feature: Language List ---
app.config['TRANSLATION_LANGUAGES'] = [
    "English", "Spanish", "French", "German", "Chinese", "Japanese",
    "Hindi", "Bengali", "Marathi", "Telugu", "Tamil"
]

# --- For PII Redaction: Allowed File Extensions ---
app.config['PII_ALLOWED_EXTENSIONS'] = {'docx', 'pptx'}


# --- Import and Register Feature Routes ---
from features.transcription.routes import define_transcription_routes
from features.translation.routes import define_translation_routes
from features.summarization.routes import define_summarization_routes
from features.pii_redaction.routes import define_pii_redaction_routes
from features.blurring.routes import define_blurring_routes
from features.info.routes import define_info_routes

define_transcription_routes(app)
define_translation_routes(app)
define_summarization_routes(app)
define_pii_redaction_routes(app)
define_blurring_routes(app)
define_info_routes(app)


# --- Main Layout & Content Swapping Routes ---
@app.route('/')
def root_redirect():
    """Redirects the root path to the default welcome feature."""
    return redirect(url_for('index', feature_key=DEFAULT_FEATURE_KEY))

@app.route('/feature/<feature_key>')
def index(feature_key): 
    """Displays the main layout and the content for the specified feature."""
    if feature_key not in FEATURES_DATA:
        feature_key_to_render = DEFAULT_FEATURE_KEY
    else:
        feature_key_to_render = feature_key
    
    current_feature_data = FEATURES_DATA[feature_key_to_render]
    initial_content_template_path = current_feature_data["template"]

    return render_template(
        'layout.html',
        features=FEATURES_DATA,
        current_feature=current_feature_data,
        active_feature_key=feature_key_to_render,
        initial_content_template=initial_content_template_path,
        DEFAULT_FEATURE_KEY=DEFAULT_FEATURE_KEY
    )


@app.route('/content/<feature_key>')
def get_feature_content(feature_key):
    """Serves the HTML content for a specific feature, used by HTMX."""
    if feature_key not in FEATURES_DATA:
        return "Feature content not found", 404
    
    feature_data = FEATURES_DATA[feature_key]
    template_to_render = feature_data["template"]
    
    context = {}
    if feature_key == "translation":
        context["languages"] = current_app.config.get('TRANSLATION_LANGUAGES', [])
        context["gcs_available"] = current_app.config.get('GCS_AVAILABLE', False)
        context["gemini_configured"] = current_app.config.get('GEMINI_CONFIGURED', False)
    elif feature_key == "summarization":
        context["summary"] = "" 
        context["hx_target_is_result"] = False 
    elif feature_key == "pii_redaction":
        context["redacted_file_url"] = None
        context["original_filename"] = None
        context["presidio_available"] = current_app.config.get('PRESIDIO_ANALYZER_AVAILABLE', False)
        context["gcs_available"] = current_app.config.get('GCS_AVAILABLE', False) # <<< --- THIS LINE WAS ADDED ---
        context["hx_target_is_result"] = False

    return render_template(template_to_render, **context)


if __name__ == '__main__':
    logging.info(f"Starting Flask development server on http://localhost:5001")
    print(f"FLASK_SECRET_KEY is {'SET (hopefully not the default)' if app.secret_key != 'a_very_strong_default_secret_key_for_dev_only_32_chars_long_replace_this' else 'USING DEFAULT DEV KEY - NOT FOR PRODUCTION'}")
    print(f"GOOGLE_API_KEY is {'SET' if GOOGLE_API_KEY else 'NOT SET (will be needed for AI features)'}")
    app.run(host="0.0.0.0", port=5001, debug=True)