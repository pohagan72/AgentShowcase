# run.py
import os
from waitress import serve
from app import create_app # Import the factory function

# Create the app instance
app = create_app()

if __name__ == "__main__":
    # PORT is set by the hosting platform (Railway).
    port = int(os.environ.get("PORT", 8080))
    # MCP tool handlers (and /api/v1/* handlers) hold a worker thread for the
    # full Gemini turnaround. Waitress' default of 4 threads means 4 concurrent
    # tool calls block every other request to the whole app (homepage, dashboard,
    # /mcp health). 32 gives headroom for the blocking-handler tier; the real
    # fix (workers + SSE) lands in Phase 2.5.B. Env-tunable so we can dial back
    # without a redeploy if a replica is memory-constrained.
    threads = int(os.environ.get("WAITRESS_THREADS", "32"))
    print(f"Starting Waitress server on host 0.0.0.0, port {port} (threads={threads})")
    serve(app, host="0.0.0.0", port=port, threads=threads)