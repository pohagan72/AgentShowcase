from flask import Flask, render_template, request, url_for
# from waitress import serve # No longer needed here if run.py or Docker CMD handles it
import time
import os
# from dotenv import load_dotenv # Optional: For local .env loading during development

# Optional: Load .env file for local development if you're not setting env vars manually
# load_dotenv()

app = Flask(__name__)

# --- Application Configuration from Environment Variables ---
# FLASK_SECRET_KEY: Essential for session security. Set this in your Cloud Run environment.
# For local development, you can set it in your .env or directly here (less secure for shared code).
# Generate a strong key using: import secrets; print(secrets.token_hex(32))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_strong_default_secret_key_for_dev_only_32_chars_long")
if app.secret_key == "a_very_strong_default_secret_key_for_dev_only_32_chars_long" and os.environ.get("FLASK_ENV") != "development":
    # In a real production scenario, you might want to raise an error or log a critical warning
    # if the default dev key is used in a non-dev environment.
    # For now, we'll just print a warning if not in explicit development mode.
    print("WARNING: Using default FLASK_SECRET_KEY. Set a strong, unique key in your environment for production!")


# --- Google Cloud / AI Configuration (read from environment variables) ---
# These will be used by your actual AI processing functions when you implement them.
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-latest") # Default if not set
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")

# You might want to add a check here for essential keys in a production environment
# if not GOOGLE_API_KEY and os.environ.get("FLASK_ENV") != "development":
#     raise ValueError("GOOGLE_API_KEY environment variable not set.")


# --- Data for our features (UI driven) ---
FEATURES_DATA = {
    "welcome": {"name": "Welcome", "icon": "fas fa-home", "template": "partials/_welcome_content.html"},
    "transcription": {"name": "Transcription", "icon": "fas fa-microphone-alt", "template": "partials/_transcription_content.html"},
    "translation": {"name": "Translation", "icon": "fas fa-language", "template": "partials/_translation_content.html"},
    "summarization": {"name": "Summarization", "icon": "fas fa-file-alt", "template": "partials/_summarization_content.html"},
    "blurring": {"name": "Blurring", "icon": "fas fa-eye-slash", "template": "partials/_blurring_content.html"},
    "info": {"name": "Information", "icon": "fas fa-info-circle", "template": "partials/_info_content.html"},
}

DEFAULT_FEATURE_KEY = "welcome"

# --- Main Routes ---
@app.route('/')
@app.route('/feature/<feature_key>')
def index(feature_key=None):
    if feature_key is None or feature_key not in FEATURES_DATA:
        feature_key = DEFAULT_FEATURE_KEY

    current_feature = FEATURES_DATA[feature_key]
    initial_content_template = current_feature["template"]

    return render_template(
        'layout.html',
        features=FEATURES_DATA,
        current_feature=current_feature,
        active_feature_key=feature_key,
        initial_content_template=initial_content_template,
        # Pass DEFAULT_FEATURE_KEY to layout.html for JavaScript logic
        DEFAULT_FEATURE_KEY=DEFAULT_FEATURE_KEY
    )

@app.route('/content/<feature_key>')
def get_feature_content(feature_key):
    if feature_key not in FEATURES_DATA:
        return "Feature not found", 404
    # time.sleep(0.5) # Simulate delay - can be removed for production
    feature = FEATURES_DATA[feature_key]
    return render_template(feature["template"])

# --- Dummy Processing Endpoints (for HTMX forms) ---
# When you implement real AI logic, you'll use GOOGLE_API_KEY, GEMINI_MODEL_NAME, etc. here
@app.route('/process/<action>', methods=['POST'])
def process_action(action):
    # time.sleep(1) # Simulate work - can be removed for production

    # Example of how you might access the config (though these dummy endpoints don't use them)
    # print(f"Processing action '{action}' with API Key: {'SET' if GOOGLE_API_KEY else 'NOT SET'}")
    # print(f"Using Gemini Model: {GEMINI_MODEL_NAME}")

    if action == "transcribe":
        audio_file = request.files.get('audio_file')
        if audio_file and audio_file.filename:
            # TODO: Implement actual transcription logic using an AI model
            return f"<p><strong>Transcription Result (Demo):</strong> '{audio_file.filename}' would be transcribed here by the AI.</p>"
        return "<p class='error-message'>No audio file submitted for transcription.</p>"

    elif action == "translate":
        text = request.form.get('text_to_translate', '')
        lang = request.form.get('target_lang', 'es')
        if text:
            # TODO: Implement actual translation logic
            return f"<p><strong>Translation to {lang} (Demo):</strong> '{text}' would be translated here by the AI.</p>"
        return "<p class='error-message'>No text submitted for translation.</p>"

    elif action == "summarize":
        text = request.form.get('text_to_summarize', '')
        if text:
            # TODO: Implement actual summarization logic
            summary = text[:150] + "..." if len(text) > 150 else text # Simple truncation for demo
            return f"<p><strong>Summary (Demo):</strong> {summary}</p>"
        return "<p class='error-message'>No text submitted for summarization.</p>"

    elif action == "blur_video":
        video_file = request.files.get('video_file')
        if video_file and video_file.filename:
            # TODO: Implement actual video blurring (likely asynchronous)
            # You might save to GCS_BUCKET_NAME, trigger a background task
            return f"""
                <p><strong>Video Blurring Status (Demo):</strong></p>
                <p>Video '{video_file.filename}' has been received for face blurring.</p>
                <p><em>(This is a placeholder. Real processing would occur, potentially in the background.)</em></p>
            """
        return "<p class='error-message'>No video file submitted. Please select a video.</p>"

    elif action == "blur_image":
        image_file = request.files.get('image_file')
        if image_file and image_file.filename:
            # TODO: Implement actual image blurring
            # You might save to GCS_BUCKET_NAME temporarily if needed
            return f"""
                <p><strong>Image Blurring Result (Demo):</strong></p>
                <p>Image '{image_file.filename}' has been processed.</p>
                <img src="https://via.placeholder.com/400x300.png?text=Blurred+Image+Preview+(Demo)" alt="Blurred Image Preview (placeholder)" style="max-width: 100%; max-height:300px; margin-top: 10px; border: 1px solid #ccc; display: block; border-radius: 4px;">
                <p><em>(This is a placeholder image. The actual blurred image would be displayed here.)</em></p>
            """
        return "<p class='error-message'>No image file submitted. Please select an image.</p>"

    return "Unknown action", 400

# The following block is for running the app with Flask's built-in dev server
# (e.g., python app.py).
# For production (like Cloud Run with Waitress), run.py or Docker CMD will be used.
if __name__ == '__main__':
    # This ensures that when you run `python app.py` locally, it uses a suitable dev port.
    # Cloud Run will use the PORT env var via run.py/Waitress.
    print(f"Starting Flask development server on http://localhost:5001")
    print(f"FLASK_SECRET_KEY is {'SET' if app.secret_key != 'a_very_strong_default_secret_key_for_dev_only_32_chars_long' else 'USING DEFAULT DEV KEY - NOT FOR PRODUCTION'}")
    print(f"GOOGLE_API_KEY is {'SET' if GOOGLE_API_KEY else 'NOT SET (will be needed for AI features)'}")
    app.run(host="0.0.0.0", port=5001, debug=True)