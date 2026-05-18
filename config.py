# config.py
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

def _resolve_secret_key():
    key = os.environ.get("FLASK_SECRET_KEY")
    if key:
        return key
    if os.environ.get("FLASK_DEBUG") == "1":
        return "dev_key_only_change_in_prod"
    raise RuntimeError(
        "FLASK_SECRET_KEY is required in production. "
        "Set it in the environment, or set FLASK_DEBUG=1 for local development."
    )

class Config:
    # --- Flask Settings ---
    SECRET_KEY = _resolve_secret_key()

    # --- Request / Upload limits (defense against DoS via large uploads) ---
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB

    # --- Session cookie hardening ---
    # Secure=True requires HTTPS at the platform edge (Railway terminates TLS).
    # Opt-out only when explicitly running over plain HTTP for local dev.
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_INSECURE_COOKIES") != "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    
    # --- Cloud / AI Settings ---
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL")
    
    # Storage (S3-compatible; Railway provides bucket + credentials via env vars)
    GCS_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")

    # --- Feature: Translation ---
    TRANSLATION_LANGUAGES = [
        "English", "Spanish", "French", "German", "Chinese", "Japanese",
        "Hindi", "Bengali", "Marathi", "Telugu", "Tamil"
    ]
    
    # --- Feature: PII Redaction ---
    PII_ALLOWED_EXTENSIONS = {'docx', 'pptx'}

    # --- Feature: Summarization & PPT Builder ---
    # Constants defined directly here to decouple from logic folders
    PPT_MAX_FILES = 5
    PPT_MAX_FILE_SIZE_MB = 10
    PPT_ALLOWED_EXTENSIONS_STR = ".docx, .pdf, .pptx, .xlsx"
    PPT_TEMPLATES = ['professional', 'creative', 'minimalist']
    PPT_DEFAULT_TEMPLATE_NAME = 'professional'