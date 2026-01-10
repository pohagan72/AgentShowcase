# config.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask Settings
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev_key_only_change_in_prod")
    
    # Cloud / AI Settings
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL")
    GCS_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME") # Mapped from S3 var
    GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "railway-deployment")
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")

    # Translation
    TRANSLATION_LANGUAGES = [
        "English", "Spanish", "French", "German", "Chinese", "Japanese",
        "Hindi", "Bengali", "Marathi", "Telugu", "Tamil"
    ]
    
    # PII Redaction
    PII_ALLOWED_EXTENSIONS = {'docx', 'pptx'}

    # PPT Builder Configuration Logic
    try:
        from features.summarization.ppt_builder_logic.file_processor import MAX_FILES, MAX_FILE_SIZE_BYTES, DEFAULT_ALLOWED_EXTENSIONS_PPT
        from features.summarization.ppt_builder_logic.presentation_generator import TEMPLATES, DEFAULT_TEMPLATE_NAME
        
        PPT_MAX_FILES = MAX_FILES
        PPT_MAX_FILE_SIZE_MB = int(MAX_FILE_SIZE_BYTES / (1024*1024))
        PPT_ALLOWED_EXTENSIONS_STR = ', '.join(sorted(list(f".{ext}" for ext in DEFAULT_ALLOWED_EXTENSIONS_PPT)))
        PPT_TEMPLATES = list(TEMPLATES.keys())
        PPT_DEFAULT_TEMPLATE_NAME = DEFAULT_TEMPLATE_NAME
    except ImportError:
        logging.warning("Could not import PPT Builder constants. Using defaults.")
        PPT_MAX_FILES = 5
        PPT_MAX_FILE_SIZE_MB = 10
        PPT_ALLOWED_EXTENSIONS_STR = ".docx, .pdf, .py"
        PPT_TEMPLATES = ['professional', 'creative', 'minimalist']
        PPT_DEFAULT_TEMPLATE_NAME = 'professional'