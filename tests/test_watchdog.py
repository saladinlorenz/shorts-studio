"""Watchdog du lanceur : health-check périodique → sortie code 3 pour relance.

``start_web.bat`` relance le serveur uniquement quand le processus sort avec le
code 3. Ces tests exercent ``_start_watchdog`` sur un vrai serveur HTTP local
(puis sur un port mort), sans ouvrir de navigateur et sans toucher au vrai
studio. ``os._exit`` est remplacé : le thread est parqué au lieu de tuer pytest.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import app as app_mod  # noqa: E402


class _Health(BaseHTTPRequestHandler):
    """200 sauf sur la requête ``bad_hit`` (0 = jamais), pour simuler un accroc."""

    hits = 0
    bad_hit = 0

    def do_GET(self):  # noqa: N802 - nom impose par BaseHTTPRequestHandler
        cls = type(self)
        cls.hits += 1
        code = 503 if cls.hits == cls.bad_hit else 200
        self.send_response(code)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _serve(port: int = 0) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _stop(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.server_close()


def _wait(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture()
def watchdog(monkeypatch):
    monkeypatch.setattr(app_mod, "WATCHDOG_INTERVAL", 0.05)
    monkeypatch.setattr(app_mod, "WATCHDOG_TIMEOUT", 1.0)
    monkeypatch.setattr(app_mod, "WATCHDOG_FAILURES", 2)
    exits: list[int] = []
    done = threading.Event()
    park = threading.Event()

    def fake_exit(code: int) -> None:
        exits.append(code)
        done.set()
        # thread daemon parqué : il n'appellera jamais le vrai os._exit restauré
        park.wait()

    monkeypatch.setattr("os._exit", fake_exit)
    yield SimpleNamespace(exits=exits, done=done, start=app_mod._start_watchdog)


def test_healthy_server_is_never_killed_then_dead_socket_exits_3(watchdog):
    _Health.hits = 0
    _Health.bad_hit = 0
    server = _serve()
    port = server.server_address[1]
    try:
        watchdog.start("127.0.0.1", port)
        assert _wait(lambda: _Health.hits >= 4), "le serveur sain n'a pas été vu"
        assert watchdog.exits == [], "un serveur sain ne doit jamais être tué"
    finally:
        _stop(server)
    assert _wait(watchdog.done.is_set), "le watchdog n'a pas réagi au socket mort"
    assert app_mod.WATCHDOG_EXIT_CODE == 3, "start_web.bat ne relance que sur le code 3"
    assert watchdog.exits == [3]


def test_slow_startup_never_killed_before_first_success(watchdog):
    # port libre : aucun serveur n'a jamais répondu → jamais « armé »
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    watchdog.start("127.0.0.1", port)
    time.sleep((app_mod.WATCHDOG_FAILURES + 3) * app_mod.WATCHDOG_INTERVAL)
    assert watchdog.exits == [], "un démarrage lent ne doit pas être tué"
    # nettoyage : armer le watchdog puis provoquer la mort pour parquer le thread
    _Health.hits = 0
    _Health.bad_hit = 0
    server = _serve(port)
    try:
        assert _wait(lambda: _Health.hits >= 1), "le serveur de nettoyage n'a pas répondu"
    finally:
        _stop(server)
    assert _wait(watchdog.done.is_set)
    assert watchdog.exits == [3]


def test_one_transient_failure_does_not_kill(watchdog):
    _Health.hits = 0
    _Health.bad_hit = 2  # une seule 503, au 2e check ; les autres répondent 200
    server = _serve()
    port = server.server_address[1]
    try:
        watchdog.start("127.0.0.1", port)
        assert _wait(lambda: _Health.hits >= 6), "pas assez de checks observés"
        assert watchdog.exits == [], "un échec isolé ne doit pas tuer le serveur"
    finally:
        _stop(server)
    assert _wait(watchdog.done.is_set)
    assert watchdog.exits == [3]