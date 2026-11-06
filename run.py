<<<<<<< HEAD
"""Local production WSGI entrypoint. Put a trusted HTTPS reverse proxy in front."""
import os
from waitress import serve
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
from app import create_app

app = create_app()

if __name__ == "__main__":
<<<<<<< HEAD
    host = os.getenv("BIND_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"Grade Analyzer is running at http://{browser_host}:{port}/")
    serve(app, host=host, port=port, threads=8, channel_timeout=60,
          max_request_body_size=2*1024*1024)
=======
    app.run(host="0.0.0.0", port=5000, debug=True)
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
