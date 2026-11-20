import os
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional

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
            token = self.path[len(prefix):].split("?")[0].strip()
            from backend.ssl.challenge_server import ACME_CHALLENGES
            if token and token in ACME_CHALLENGES:
                payload = ACME_CHALLENGES[token].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
                return
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "9")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"Not Found")

class _DualStackServer(HTTPServer):
    # On POSIX (Linux/macOS), SO_REUSEADDR allows quick rebind over TIME_WAIT sockets.
    # On Windows, SO_REUSEADDR allows port hijacking (CWE-605), so disable on NT and use SO_EXCLUSIVEADDRUSE.
    allow_reuse_address = (os.name != "nt")
    address_family = socket.AF_INET6

    def server_bind(self):
        if os.name == "nt":
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except (AttributeError, OSError):
                pass
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except (AttributeError, OSError):
            pass
        super().server_bind()

class _IPv4Server(HTTPServer):
    allow_reuse_address = (os.name != "nt")

    def server_bind(self):
        if os.name == "nt":
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except (AttributeError, OSError):
                pass
        super().server_bind()

class TemporaryAcmeServer:
    def __init__(self, port: int = 80):
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.last_error: Optional[str] = None

    def start(self) -> bool:
        self.last_error = None
        server = None

        # 1. Attempt dual-stack IPv6+IPv4 bind first
        try:
            server = _DualStackServer(("::", self.port), AcmeChallengeHandler)
            logging.info(f"[ACME Server] Dual-stack HTTP server listening on [::]:{self.port}")
        except Exception as e_v6:
            logging.debug(f"[ACME Server] Dual-stack bind to [::]:{self.port} skipped ({e_v6}), attempting IPv4 0.0.0.0...")

        # 2. Fall back to standard IPv4 bind if dual-stack failed
        if server is None:
            try:
                server = _IPv4Server(("0.0.0.0", self.port), AcmeChallengeHandler)
                logging.info(f"[ACME Server] IPv4 HTTP server listening on 0.0.0.0:{self.port}")
            except Exception as e_v4:
                self.last_error = str(e_v4)
                logging.warning(f"[ACME Server] Could not start temporary HTTP server on port {self.port}: {e_v4}")
                return False

        self.server = server
        try:
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logging.info(f"[ACME Server] Temporary HTTP challenge server successfully started on port {self.port}")
            return True
        except Exception as e:
            self.last_error = str(e)
            logging.warning(f"[ACME Server] Failed to start temporary HTTP server thread: {e}")
            if self.server:
                try:
                    self.server.server_close()
                except Exception:
                    pass
                self.server = None
            return False

    def stop(self):
        if self.server:
            logging.info(f"[ACME Server] Stopping temporary HTTP server on port {self.port}")
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                logging.debug(f"[ACME Server] Error stopping server: {e}")
            self.server = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
