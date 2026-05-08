# run.py
import os
from waitress import serve
from app import create_app # Import the factory function

# Create the app instance
app = create_app()

if __name__ == "__main__":
    # PORT is set by the hosting platform (Railway).
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Waitress server on host 0.0.0.0, port {port}")
    serve(app, host="0.0.0.0", port=port)