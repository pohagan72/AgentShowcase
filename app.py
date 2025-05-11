from flask import Flask, render_template, request, url_for
import os
from jinja2 import ChoiceLoader, FileSystemLoader # ADDED: For multiple template folders
# from dotenv import load_dotenv # Uncomment if you use a .env file for local dev

# load_dotenv() # Uncomment if you use a .env file for local dev

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
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-latest")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")


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

# --- Import and Register Feature Routes ---
# These imports will execute the code in each routes.py, defining routes on the 'app' object
from features.transcription.routes import define_transcription_routes
from features.translation.routes import define_translation_routes
from features.summarization.routes import define_summarization_routes
from features.blurring.routes import define_blurring_routes
from features.info.routes import define_info_routes # info might not have process routes

define_transcription_routes(app)
define_translation_routes(app)
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
    # Always load the welcome template structure initially; HTMX loads the specific feature content.
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
    # import time # For simulating delay during dev if needed
    # time.sleep(0.5)
    return render_template(template_to_render) # Jinja will now search both 'templates/' and 'features/'

# Note: Individual /process/<action> routes are now defined within each
# feature's routes.py file by the define_xxx_routes(app) functions.

if __name__ == '__main__':
    # This is for running locally with `python app.py` (Flask's dev server)
    # Your `run.py` will use Waitress for a more production-like local server or for deployment.
    print(f"Starting Flask development server on http://localhost:5001")
    print(f"FLASK_SECRET_KEY is {'SET (hopefully not the default)' if app.secret_key != 'a_very_strong_default_secret_key_for_dev_only_32_chars_long_replace_this' else 'USING DEFAULT DEV KEY - NOT FOR PRODUCTION'}")
    print(f"GOOGLE_API_KEY is {'SET' if GOOGLE_API_KEY else 'NOT SET (will be needed for AI features)'}")
    app.run(host="0.0.0.0", port=5001, debug=True)