import os
import logging
import google.generativeai as genai
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from jinja2 import ChoiceLoader, FileSystemLoader

# Import Config
from config import Config

# Import S3 Adapter and Presidio
from s3_adapter import S3Client
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

# Import Blueprints
from main_routes import bp as main_bp
from features.info.routes import bp as info_bp
from features.multimedia.routes import bp as multimedia_bp
from features.pii_redaction.routes import bp as pii_bp
from features.summarization.routes import bp as summarization_bp
from features.translation.routes import bp as translation_bp

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Configure Jinja Loader (Preserves your folder structure)
    app.jinja_loader = ChoiceLoader([
        app.jinja_loader,
        FileSystemLoader('features')
    ])

    # 1a. CSRF protection on all state-changing requests.
    # GETs (sitemap, robots, downloads) are unaffected.
    csrf = CSRFProtect(app)

    # 1b. Security headers via Talisman: HSTS, X-Frame-Options, X-Content-Type-Options,
    # Referrer-Policy, and a CSP that allowlists the exact CDNs used in layout.html.
    Talisman(
        app,
        content_security_policy={
            'default-src': "'self'",
            'script-src': [
                "'self'",
                'https://unpkg.com',
                'https://cdn.jsdelivr.net',
                "'unsafe-inline'",  # inline onclick=/onchange= handlers used across templates; remove when migrated to addEventListener
            ],
            'script-src-elem': [
                "'self'",
                'https://unpkg.com',
                'https://cdn.jsdelivr.net',
                "'unsafe-inline'",
            ],
            'style-src': [
                "'self'",
                "'unsafe-inline'",  # required by inline style="..." attributes used across templates
                'https://fonts.googleapis.com',
                'https://unpkg.com',
            ],
            'style-src-elem': [
                "'self'",
                "'unsafe-inline'",
                'https://fonts.googleapis.com',
                'https://unpkg.com',
            ],
            'font-src': ["'self'", 'https://fonts.gstatic.com', 'https://unpkg.com', 'data:'],
            'img-src': ["'self'", 'data:', 'blob:'],
            'connect-src': ["'self'", 'https://cdn.jsdelivr.net'],  # allow DOMPurify source map fetch
            'frame-ancestors': "'none'",
            'base-uri': "'self'",
            'object-src': "'none'",
        },
        # Nonce-in script-src disabled: combined with 'unsafe-inline' it cancels out and
        # browsers ignore 'unsafe-inline', breaking all the existing inline handlers.
        content_security_policy_nonce_in=[],
        force_https=os.environ.get("FLASK_INSECURE_COOKIES") != "1",
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        session_cookie_secure=True,
        referrer_policy='strict-origin-when-cross-origin',
    )

    # 2. Initialize Google Gemini
    if app.config['GOOGLE_API_KEY']:
        try:
            genai.configure(api_key=app.config['GOOGLE_API_KEY'])
            app.config['GEMINI_CONFIGURED'] = True
            logging.info("Global: Google Gemini API configured successfully.")
        except Exception as e:
            logging.error(f"Global: Failed to configure Google Gemini API: {e}")
            app.config['GEMINI_CONFIGURED'] = False
    else:
        app.config['GEMINI_CONFIGURED'] = False
        logging.warning("Global: GOOGLE_API_KEY not found.")

    # 3. Initialize S3 Storage
    app.config['GCS_AVAILABLE'] = False
    app.storage_client = None
    app.gcs_bucket = None
    
    if app.config['GCS_BUCKET_NAME'] and app.config['AWS_ACCESS_KEY_ID']:
        try:
            app.storage_client = S3Client()
            app.gcs_bucket = app.storage_client.bucket(app.config['GCS_BUCKET_NAME'])
            app.gcs_bucket.reload() # Dummy call for adapter compatibility
            app.config['GCS_AVAILABLE'] = True
            logging.info(f"Global: S3 Storage initialized (Bucket: {app.config['GCS_BUCKET_NAME']}).")
        except Exception as e:
            logging.error(f"Global: Failed to initialize S3 Storage: {e}")
    else:
        logging.warning("Global: S3 Credentials or Bucket Name missing.")

    # 4. Initialize Presidio (PII)
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
    except Exception as e:
        logging.error(f"Global: Failed to initialize Presidio: {e}")

    # 5. Register Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(info_bp)
    app.register_blueprint(multimedia_bp)
    app.register_blueprint(pii_bp)
    app.register_blueprint(summarization_bp)
    app.register_blueprint(translation_bp)

    return app

# For local development compatibility
if __name__ == '__main__':
    app = create_app()
    debug_enabled = os.environ.get("FLASK_DEBUG") == "1"
    host = "0.0.0.0" if os.environ.get("FLASK_BIND_ALL") == "1" else "127.0.0.1"
    app.run(host=host, port=5001, debug=debug_enabled, use_reloader=False)