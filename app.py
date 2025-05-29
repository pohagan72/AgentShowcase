from flask import Flask, render_template, request, url_for, current_app
import os
from jinja2 import ChoiceLoader, FileSystemLoader # ADDED: For multiple template folders
from dotenv import load_dotenv # Uncomment if you use a .env file for local dev

# --- For Translation Feature Global Imports ---
import google.generativeai as genai
from google.cloud import storage
from google.cloud.exceptions import NotFound
# --- End Translation Feature Global Imports ---

load_dotenv() # Uncomment if you use a .env file for local dev

app = Flask(__name__)

# --- Configure Jinja2 Template Loader ---
# This tells Flask to look for templates in the default 'templates' folder
# AND also within the 'features' directory (relative to the app root).
app.jinja_loader = ChoiceLoader([
    app.jinja_loader,  # This is Flask's default (looks in 'templates/' at app root)
    FileSystemLoader('features') # Adds 'features/' as a root for template searching
])
# --- End of Jinja2 Configuration ---


# --- Application Configuration from Environment Variables ---
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_strong_default_secret_key_for_dev_only_32_chars_long_replace_this")
if app.secret_key == "a_very_strong_default_secret_key_for_dev_only_32_chars_long_replace_this" and os.environ.get("FLASK_ENV") != "development":
    print("WARNING: Using default FLASK_SECRET_KEY. Set a strong, unique key in your environment for production!")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-latest") # Consistent with standalone app's GEMINI_MODEL
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")


# --- Store main config on app.config for easier access in features ---
app.config['GOOGLE_API_KEY'] = GOOGLE_API_KEY
app.config['GEMINI_MODEL_NAME'] = GEMINI_MODEL_NAME
app.config['GCS_BUCKET_NAME'] = GCS_BUCKET_NAME
app.config['GOOGLE_CLOUD_PROJECT'] = GOOGLE_CLOUD_PROJECT

# --- Initialize Google Services (Gemini & GCS) Globally ---
# These will be accessible via current_app.config['GEMINI_CONFIGURED'], current_app.storage_client etc.
app.config['GEMINI_CONFIGURED'] = False
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        app.config['GEMINI_CONFIGURED'] = True
        print("Global: Google Gemini API configured successfully.")
    except Exception as e:
        print(f"Global: Failed to configure Google Gemini API: {e}")
else:
    print("Global: GOOGLE_API_KEY not found. Gemini-dependent features may be affected.")

app.config['GCS_AVAILABLE'] = False
app.storage_client = None # Will hold the storage.Client instance
app.gcs_bucket = None     # Will hold the bucket object
if GCS_BUCKET_NAME and GOOGLE_CLOUD_PROJECT:
    try:
        app.storage_client = storage.Client(project=GOOGLE_CLOUD_PROJECT)
        app.gcs_bucket = app.storage_client.bucket(GCS_BUCKET_NAME)
        app.gcs_bucket.reload() # Check existence and permissions
        app.config['GCS_AVAILABLE'] = True
        print(f"Global: GCS client initialized (Bucket: gs://{GCS_BUCKET_NAME}).")
    except NotFound:
        print(f"Global: GCS Bucket '{GCS_BUCKET_NAME}' not found. GCS-dependent features will fail.")
        app.storage_client = None; app.gcs_bucket = None
    except Exception as e:
        print(f"Global: Failed to initialize GCS client: {e}. GCS-dependent features will fail.")
        app.storage_client = None; app.gcs_bucket = None
else:
    if not GCS_BUCKET_NAME: print("Global: GCS_BUCKET_NAME env var not found.")
    if not GOOGLE_CLOUD_PROJECT: print("Global: GOOGLE_CLOUD_PROJECT env var not found.")
    print("Global: GCS client not initialized. GCS-dependent features may be affected.")
# --- End Google Services Initialization ---


# --- Data for our features (UI driven for sidebar and content loading) ---
# IMPORTANT: Template paths for features are now relative to the 'features' directory
# due to the FileSystemLoader('features') configuration above.
FEATURES_DATA = {
    "welcome": {"name": "Welcome", "icon": "fas fa-home", "template": "partials/_welcome_content.html"}, # Found by default loader
    "transcription": {"name": "Transcription", "icon": "fas fa-microphone-alt", "template": "transcription/templates/transcription_content.html"}, # Relative to 'features/'
    "translation": {"name": "Translation", "icon": "fas fa-language", "template": "translation/templates/translation_content.html"}, # Relative to 'features/'
    "summarization": {"name": "Summarization", "icon": "fas fa-file-alt", "template": "summarization/templates/summarization_content.html"}, # Relative to 'features/'
    "blurring": {"name": "Blurring", "icon": "fas fa-eye-slash", "template": "blurring/templates/blurring_content.html"}, # Relative to 'features/'
    "info": {"name": "Information", "icon": "fas fa-info-circle", "template": "info/templates/info_content.html"}, # Relative to 'features/'
}
DEFAULT_FEATURE_KEY = "welcome"

# --- For Translation Feature: Language List (from standalone app) ---
app.config['TRANSLATION_LANGUAGES'] = [
    "English", "Spanish", "French", "German", "Chinese", "Japanese",
    "Hindi", "Bengali", "Marathi", "Telugu", "Tamil"
]


# --- Import and Register Feature Routes ---
# These imports will execute the code in each routes.py, defining routes on the 'app' object
from features.transcription.routes import define_transcription_routes
from features.translation.routes import define_translation_routes # Our new feature routes
from features.summarization.routes import define_summarization_routes
from features.blurring.routes import define_blurring_routes
from features.info.routes import define_info_routes # info might not have process routes

define_transcription_routes(app)
define_translation_routes(app) # Registering the translation routes
define_summarization_routes(app)
define_blurring_routes(app)
define_info_routes(app) # Call this even if it only defines a simple route or no new routes

# --- Main Layout & Content Swapping Routes ---
@app.route('/')
@app.route('/feature/<feature_key>')
def index(feature_key=None):
    if feature_key is None or feature_key not in FEATURES_DATA:
        feature_key = DEFAULT_FEATURE_KEY
    
    current_feature_data = FEATURES_DATA[feature_key]
    initial_content_template_path = FEATURES_DATA[DEFAULT_FEATURE_KEY]["template"]

    return render_template(
        'layout.html',
        features=FEATURES_DATA,
        current_feature=current_feature_data, # Pass the data for the selected/default feature
        active_feature_key=feature_key,
        initial_content_template=initial_content_template_path,
        DEFAULT_FEATURE_KEY=DEFAULT_FEATURE_KEY
    )

@app.route('/content/<feature_key>')
def get_feature_content(feature_key):
    if feature_key not in FEATURES_DATA:
        return "Feature content not found", 404
    
    feature_data = FEATURES_DATA[feature_key]
    template_to_render = feature_data["template"]
    
    # Context specific to the translation feature when its content is loaded
    context = {}
    if feature_key == "translation":
        context["languages"] = current_app.config.get('TRANSLATION_LANGUAGES', [])
        context["gcs_available"] = current_app.config.get('GCS_AVAILABLE', False)
        context["gemini_configured"] = current_app.config.get('GEMINI_CONFIGURED', False)
        context["file_id"] = None # No file processed yet on initial load
        # Flashed messages are handled by Flask's get_flashed_messages in the template itself

    return render_template(template_to_render, **context) # Jinja will now search both 'templates/' and 'features/'

# Note: Individual /process/<action> routes are now defined within each
# feature's routes.py file by the define_xxx_routes(app) functions.

if __name__ == '__main__':
    # This is for running locally with `python app.py` (Flask's dev server)
    # Your `run.py` will use Waitress for a more production-like local server or for deployment.
    print(f"Starting Flask development server on http://localhost:5001")
    print(f"FLASK_SECRET_KEY is {'SET (hopefully not the default)' if app.secret_key != 'a_very_strong_default_secret_key_for_dev_only_32_chars_long_replace_this' else 'USING DEFAULT DEV KEY - NOT FOR PRODUCTION'}")
    print(f"GOOGLE_API_KEY is {'SET' if GOOGLE_API_KEY else 'NOT SET (will be needed for AI features)'}")
    app.run(host="0.0.0.0", port=5001, debug=True)