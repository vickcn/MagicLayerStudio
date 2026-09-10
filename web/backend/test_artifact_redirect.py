"""Studio resolves an authenticated Core artifact endpoint without proxying bytes."""
from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(307)
        self.send_header("Location", "https://storage.example.invalid/signed-object")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def run_test() -> None:
    from web.backend.core_client import MagicLayerCoreClient

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = MagicLayerCoreClient(f"http://127.0.0.1:{server.server_port}", token="test-token")
        assert client.artifact_redirect("job-1", "page-1/source.png") == "https://storage.example.invalid/signed-object"
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == "__main__":
    run_test()
