"""Banques de contenu : les clés restent côté serveur, le test est réel mais borné.

Aucun réseau pendant les tests : httpx.Client est remplace par un faux client
qui capture l'appel (URL, parametres, en-tetes) et rejoue une reponse choisie.
Le stockage est redirige vers un fichier temporaire — le sources.json de
l'utilisateur n'est jamais touche.

Lois verifiees ici :

- la cle ne sort jamais du serveur : seul l'indice des 4 derniers caracteres ;
- un champ vide laisse la cle en place, « clear_key » est le seul effacement ;
- le navigateur ne choisit ni l'URL ni les parametres du test (catalogue fixe) ;
- NASA teste avec DEMO_KEY sans cle, Internet Archive sans cle du tout ;
- un echec signale dans le corps avec un HTTP 200 (Jamendo) reste un echec.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import sources
from server.api import sources as sources_api

KEY = "ABCD1234wxyz"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("pas du JSON")
        return self._payload


class _FakeClient:
    response = _FakeResponse(payload={})
    error: Exception | None = None
    calls: list[dict] = []

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None, headers=None):
        type(self).calls.append(
            {"url": url, "params": dict(params or {}), "headers": dict(headers or {})}
        )
        if type(self).error is not None:
            raise type(self).error
        return type(self).response


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "SOURCES_PATH", tmp_path / "sources.json")
    fake = type("BoundFakeClient", (_FakeClient,), {"calls": [], "error": None, "response": _FakeResponse(payload={})})
    monkeypatch.setattr(sources.httpx, "Client", fake)
    app = FastAPI()
    app.include_router(sources_api.router)
    with TestClient(app) as test_client:
        test_client.fake = fake
        yield test_client


def _save(client, source_id, **payload):
    return client.post(f"/api/sources/{source_id}", json=payload)


def _provider(client, source_id):
    data = client.get("/api/sources").json()
    return next(p for p in data["providers"] if p["id"] == source_id)


def test_catalog_public_no_secrets(client):
    res = client.get("/api/sources")
    assert res.status_code == 200
    data = res.json()
    ids = [p["id"] for p in data["providers"]]
    assert ids == ["pexels", "pixabay", "unsplash", "nasa", "freesound", "jamendo", "archive"]
    for provider in data["providers"]:
        assert "key" not in provider
        assert "test" not in provider
    assert data["configured"] == 0
    # NASA (DEMO_KEY) et Internet Archive (sans cle) sont prets d'emblee.
    assert data["ready"] == 2
    assert "Terrain préparé" in data["note"]


def test_save_key_hint_only(client, tmp_path):
    res = _save(client, "pexels", key=KEY)
    assert res.status_code == 200
    provider = res.json()["provider"]
    assert provider["key_configured"] is True
    assert provider["key_hint"] == "••••wxyz"
    assert provider["ready"] is True
    assert KEY not in res.text
    assert KEY not in client.get("/api/sources").text
    # La cle complete vit uniquement dans le fichier serveur.
    stored = json.loads((tmp_path / "sources.json").read_text(encoding="utf-8"))
    assert stored["pexels"]["key"] == KEY


def test_empty_key_keeps_stored(client):
    _save(client, "pexels", key=KEY)
    res = _save(client, "pexels", key="")
    assert res.json()["provider"]["key_configured"] is True
    assert res.json()["provider"]["key_hint"] == "••••wxyz"


def test_clear_key_erases(client):
    _save(client, "pexels", key=KEY)
    res = _save(client, "pexels", clear_key=True)
    provider = res.json()["provider"]
    assert provider["key_configured"] is False
    assert provider["key_hint"] == ""
    assert provider["ready"] is False


@pytest.mark.parametrize("bad", ["abc", "cle avec espace", "clé-accents!", "x" * 201])
def test_invalid_key_rejected(client, bad):
    res = _save(client, "pexels", key=bad)
    assert res.status_code == 400
    assert "Clé invalide" in res.json()["detail"]


def test_enabled_toggle_recomputes_ready(client):
    _save(client, "pexels", key=KEY)
    assert _save(client, "pexels", enabled=False).json()["provider"]["ready"] is False
    assert _provider(client, "pexels")["key_configured"] is True
    assert _save(client, "pexels", enabled=True).json()["provider"]["ready"] is True


def test_unknown_source_404(client):
    assert _save(client, "inconnu", key=KEY).status_code == 404
    assert client.post("/api/sources/inconnu/test").status_code == 404


def test_extra_payload_field_rejected(client):
    res = client.post("/api/sources/pexels", json={"key": KEY, "url": "http://autre.example"})
    assert res.status_code == 422


def test_connection_success_uses_catalog_url(client):
    _save(client, "pexels", key=KEY)
    client.fake.response = _FakeResponse(payload={"photos": [{"alt": "Forêt dans la brume"}]})
    res = client.post("/api/sources/pexels/test")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["sample"] == "Forêt dans la brume"
    assert data["latency_ms"] >= 0
    call = client.fake.calls[0]
    assert call["url"] == "https://api.pexels.com/v1/curated"
    assert call["headers"]["Authorization"] == KEY
    assert KEY not in res.text


def test_unsplash_client_id_prefix(client):
    _save(client, "unsplash", key=KEY)
    client.fake.response = _FakeResponse(payload=[{"alt_description": "Vague au crépuscule"}])
    data = client.post("/api/sources/unsplash/test").json()
    assert data["ok"] is True
    assert data["sample"] == "Vague au crépuscule"
    assert client.fake.calls[0]["headers"]["Authorization"] == f"Client-ID {KEY}"


def test_refused_key(client):
    _save(client, "pexels", key=KEY)
    client.fake.response = _FakeResponse(status_code=401)
    data = client.post("/api/sources/pexels/test").json()
    assert data["ok"] is False
    assert "Clé refusée par Pexels" in data["message"]


def test_quota_reached(client):
    _save(client, "pixabay", key=KEY)
    client.fake.response = _FakeResponse(status_code=429)
    data = client.post("/api/sources/pixabay/test").json()
    assert data["ok"] is False
    assert "Quota" in data["message"]


def test_network_error(client):
    _save(client, "pexels", key=KEY)
    client.fake.error = httpx.ConnectError("boom")
    data = client.post("/api/sources/pexels/test").json()
    assert data["ok"] is False
    assert "injoignable" in data["message"]


def test_malformed_proxy_env_fallback(client, monkeypatch):
    # Certaines machines ont un NO_PROXY invalide : httpx.Client leve alors
    # InvalidURL des la construction ; le test doit retenter sans environnement.
    _save(client, "pexels", key=KEY)
    client.fake.response = _FakeResponse(payload={"photos": [{"alt": "Forêt"}]})
    base = client.fake

    class PickyClient(base):
        def __init__(self, **kwargs):
            if kwargs.get("trust_env", True):
                raise httpx.InvalidURL("Invalid port: ':1]'")
            super().__init__(**kwargs)

    monkeypatch.setattr(sources.httpx, "Client", PickyClient)
    data = client.post("/api/sources/pexels/test").json()
    assert data["ok"] is True
    assert data["sample"] == "Forêt"


def test_non_json_response(client):
    _save(client, "pexels", key=KEY)
    client.fake.response = _FakeResponse(bad_json=True)
    data = client.post("/api/sources/pexels/test").json()
    assert data["ok"] is False
    assert "non JSON" in data["message"]


def test_nasa_demo_key_without_registration(client):
    client.fake.response = _FakeResponse(payload={"title": "Aurora over Iceland"})
    data = client.post("/api/sources/nasa/test").json()
    assert data["ok"] is True
    assert data["sample"] == "Aurora over Iceland"
    assert client.fake.calls[0]["params"]["api_key"] == "DEMO_KEY"


def test_archive_keyless(client):
    client.fake.response = _FakeResponse(payload={"response": {"docs": [{"title": "Night of the Living Dead"}]}})
    data = client.post("/api/sources/archive/test").json()
    assert data["ok"] is True
    assert data["sample"] == "Night of the Living Dead"
    call = client.fake.calls[0]
    assert call["url"] == "https://archive.org/advancedsearch.php"
    assert not call["headers"]
    assert set(call["params"]) == {"q", "rows", "output"}


def test_jamendo_http200_body_failure(client):
    _save(client, "jamendo", key=KEY)
    client.fake.response = _FakeResponse(
        payload={"headers": {"status": "failed", "error_message": "Invalid client id"}}
    )
    data = client.post("/api/sources/jamendo/test").json()
    assert data["ok"] is False
    assert "Invalid client id" in data["message"]


def test_missing_required_key_400(client):
    res = client.post("/api/sources/freesound/test")
    assert res.status_code == 400
    assert "Aucune clé enregistrée" in res.json()["detail"]


def test_storage_robust_to_garbage(client, tmp_path):
    (tmp_path / "sources.json").write_text(
        json.dumps({"pexels": {"key": KEY}, "fantome": {"key": "x"}, "nasa": "pas-un-dict"}),
        encoding="utf-8",
    )
    data = client.get("/api/sources").json()
    assert data["configured"] == 1
    assert _provider(client, "pexels")["key_hint"] == "••••wxyz"
    (tmp_path / "sources.json").write_text("{cassé", encoding="utf-8")
    assert client.get("/api/sources").status_code == 200