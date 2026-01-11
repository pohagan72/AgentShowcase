# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Flask Settings ---
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev_key_only_change_in_prod")
    
    # --- Cloud / AI Settings ---
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL")
    
    # Storage (Mapped from S3 env vars for compatibility with S3Adapter)
    GCS_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME") 
    GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "railway-deployment")
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