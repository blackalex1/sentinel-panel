import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict

# Global store for active ACME HTTP-01 challenges (token -> key_authorization)
ACME_CHALLENGES: Dict[str, str] = {}

class AcmeChallengeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress request logging to avoid log pollution
        pass

    def do_GET(self):
        # Path is like: /.well-known/acme-challenge/some-token
        prefix = "/.well-known/acme-challenge/"
        if self.path.startswith(prefix):
            token = self.path[len(prefix):]
            from backend.ssl.challenge_server import ACME_CHALLENGES
            if token in ACME_CHALLENGES:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(ACME_CHALLENGES[token].encode("utf-8"))
                return
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

class TemporaryAcmeServer:
    def __init__(self, port=80):
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), AcmeChallengeHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logging.info(f"[ACME Server] Temporary HTTP server started on port {self.port}")
            return True
        except Exception as e:
            logging.warning(f"[ACME Server] Could not start temporary HTTP server on port {self.port}: {e}")
            return False

    def stop(self):
        if self.server:
            logging.info(f"[ACME Server] Stopping temporary HTTP server on port {self.port}")
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
