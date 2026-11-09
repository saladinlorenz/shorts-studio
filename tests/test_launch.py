"""Ouverture du navigateur par le lanceur : seulement quand le serveur répond.

``start_web.bat`` appelle ``python -m server.app --open``. Les imports du serveur
prennent plusieurs secondes : ouvrir la page avant l'écoute montrerait un site
inaccessible. Ces tests exercent ``_open_browser_when_ready`` sur un vrai serveur
HTTP local, sans ouvrir de navigateur et sans toucher aux données du projet.
"""
from __future__ import annotations

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import app as app_mod  # noqa: E402


class _Health(BaseHTTPRequestHandler):
    """Renvoie 503 tant que le serveur n'est pas « prêt », puis 200."""

    ready_after = 0
    hits = 0

    def do_GET(self):  # noqa: N802 - nom impose par BaseHTTPRequestHandler
        type(self).hits += 1
        ready = type(self).hits > type(self).ready_after and self.path == "/api/health"
        self.send_response(200 if ready else 503)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _wait_opened(opened: list[str], timeout: float = 10.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline and not opened:
        time.sleep(0.05)
    assert opened, "le navigateur n'a jamais été ouvert"
    return opened[0]


def test_browser_opens_only_after_health_and_on_configured_port(monkeypatch):
    _Health.ready_after = 3
    _Health.hits = 0
    server = _serve(_Health)
    port = server.server_address[1]
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    try:
        app_mod._open_browser_when_ready("127.0.0.1", port)
        url = _wait_opened(opened)
        assert url == f"http://127.0.0.1:{port}/"
        # les premiers 503 ont bien été essuyés avant l'ouverture
        assert _Health.hits > 3
        assert len(opened) == 1, "une seule ouverture, pas une par tentative"
    finally:
        server.shutdown()
        server.server_close()


def test_wildcard_host_is_browsed_on_loopback(monkeypatch):
    _Health.ready_after = 0
    _Health.hits = 0
    server = _serve(_Health)
    port = server.server_address[1]
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    try:
        app_mod._open_browser_when_ready("0.0.0.0", port)
        assert _wait_opened(opened) == f"http://127.0.0.1:{port}/"
    finally:
        server.shutdown()
        server.server_close()