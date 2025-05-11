# run.py
import os
from waitress import serve
from app import app # Your Flask app object from app.py

if __name__ == "__main__":
    # Cloud Run sets the PORT environment variable.
    port = int(os.environ.get("PORT", 8080)) # Default to 8080 if not set
    print(f"Starting Waitress server on host 0.0.0.0, port {port}")
    serve(app, host="0.0.0.0", port=port)