"""Local production WSGI entrypoint. Put a trusted HTTPS reverse proxy in front."""
import os
from waitress import serve
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("BIND_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"Grade Analyzer is running at http://{browser_host}:{port}/")
    serve(app, host=host, port=port, threads=8, channel_timeout=60,
          max_request_body_size=2*1024*1024)
