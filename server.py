"""Entry point — boots the Flask app from app.py.

Kept at the same path so existing `start.sh` / deployment scripts still work.
"""
import os
import sys

from app import app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"[{__file__}] Starting Flask server on port {port}...", flush=True)
    print(f"[{__file__}] Working directory: {os.getcwd()}", flush=True)
    print(f"  Public site:  http://0.0.0.0:{port}/", flush=True)
    print(f"  Admin login:  http://0.0.0.0:{port}/admin/login", flush=True)
    print(f"  Health:       http://0.0.0.0:{port}/health", flush=True)
    print(f"Press Ctrl+C to stop.", flush=True)
    try:
        # threaded=True so SMTP doesn't block other requests
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True,
                use_reloader=False)
    except KeyboardInterrupt:
        sys.exit(0)
