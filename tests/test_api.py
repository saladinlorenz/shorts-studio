"""Tests du serveur FastAPI (routes, sécurité, projets, médias).

Exécutés avec les 39 tests existants : `python -m pytest tests -q`.
Le rendu Remotion complet n'est pas testé ici (trop long, navigateur de
rendu requis) : il est vérifié manuellement et documenté dans le rapport.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.app import app  # noqa: E402
from server import security  # noqa: E402

client = TestClient(app)

# Petit PNG valide (1x1) pour les tests d'import de média.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6360000000020001e221bc330000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def _clean_project():
    """Supprime le projet de test s'il existe (avant/après)."""
    name = "test_api_roundtrip"
    path = security.PROJECTS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()


def minimal_project() -> dict:
    from shortvideos.project import default_project

    proj = default_project()
    # Aucun média requis pour ces tests : on garde les chemins vides
    # (validate signalera l'absence de fond, ce qui est attendu côté export).
    proj["content"]["background_image"] = ""
    proj["content"]["logo"] = ""
    return proj


# ---------------------------------------------------------------- health
def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert isinstance(data["groq_configured"], bool)


# ------------------------------------------------------------- projets
def test_project_roundtrip():
    proj = minimal_project()

    res = client.post("/api/projects", json={"name": "test_api_roundtrip", "project": proj})
    assert res.status_code == 200, res.text

    res = client.get("/api/projects")
    assert res.status_code == 200
    names = [p["name"] for p in res.json()]
    assert "test_api_roundtrip" in names

    res = client.get("/api/projects/test_api_roundtrip")
    assert res.status_code == 200
    data = res.json()
    assert data["project"]["content"]["text"] == proj["content"]["text"]
    assert data["project"]["version"] == 1

    res = client.delete("/api/projects/test_api_roundtrip")
    assert res.status_code == 200
    res = client.get("/api/projects/test_api_roundtrip")
    assert res.status_code == 404


def test_project_name_cannot_escape_directory():
    proj = minimal_project()
    res = client.post(
        "/api/projects",
        json={"name": "../evil", "project": proj},
    )
    # safe_name réduit à un nom de fichier simple : aucun écriture hors dossier.
    assert res.status_code == 200
    written = list(security.PROJECTS_DIR.glob("evil*.json"))
    assert written, "le fichier doit être écrit dans PROJECTS_DIR uniquement"
    for p in written:
        p.unlink()


def test_validate_reports_missing_background():
    proj = minimal_project()  # fond vide -> erreur attendue
    res = client.post("/api/projects/validate", json={"project": proj})
    assert res.status_code == 200
    errors = res.json()["errors"]
    assert any("fond" in e.lower() for e in errors), errors


def test_load_missing_project_404():
    assert client.get("/api/projects/inexistant_xyz").status_code == 404


# --------------------------------------------------------------- médias
def test_media_upload_serve_and_traversal_blocked():
    res = client.post(
        "/api/media/upload",
        files={"file": ("fond de test.png", io.BytesIO(PNG_1PX), "image/png")},
    )
    assert res.status_code == 200, res.text
    media = res.json()
    assert media["id"] and media["url"] == f"/api/media/{media['id']}"

    # Le média est servi (même origine, pas de chemin Windows en URL).
    res = client.get(media["url"])
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")

    # Tentatives de traversée / identifiants invalides : refusées.
    # (httpx normalise ".." côté client : on teste le décodage serveur réel
    #  avec une URL encodée, plus les identifiants invalides en unitaire.)
    res = client.get("/api/media/%2e%2e%2fsettings")
    assert res.status_code in (400, 404), f"traversal encodée -> {res.status_code}"

    from server.media import resolve_media

    for bad in ("../settings", "a/b", "settings.json", "", ".."):
        with pytest.raises(Exception) as exc:
            resolve_media(bad)
        assert getattr(exc.value, "status_code", None) in (400, 404), bad

    # Segment supplémentaire : route API inconnue (404), jamais de fichier.
    assert client.get("/api/media/a/b").status_code == 404

    # Nettoyage du fichier créé.
    path = security.MEDIA_DIR / f"{media['id']}.png"
    if path.exists():
        path.unlink()


def test_media_upload_rejects_unsupported_type():
    res = client.post(
        "/api/media/upload",
        files={"file": ("script.exe", io.BytesIO(b"MZ fake"), "application/x-msdownload")},
    )
    assert res.status_code == 415


# -------------------------------------------------------------- sécurité
def test_mutating_request_with_foreign_origin_rejected():
    res = client.post(
        "/api/projects",
        json={"name": "x", "project": minimal_project()},
        headers={"Origin": "http://evil.example.com"},
    )
    assert res.status_code == 403
    assert "rigine" in res.text  # "Origine non autorisee."
    (security.PROJECTS_DIR / "x.json").unlink(missing_ok=True)


def test_mutating_request_with_local_origin_accepted():
    res = client.post(
        "/api/projects",
        json={"name": "test_api_roundtrip", "project": minimal_project()},
        headers={"Origin": "http://127.0.0.1:8000"},
    )
    assert res.status_code == 200


def test_local_origin_on_another_port_accepted():
    """Le port est un reglage : la propre origine du serveur passe, meme hors 8000."""
    other = TestClient(app, base_url="http://127.0.0.1:8123")
    res = other.post(
        "/api/projects",
        json={"name": "test_api_roundtrip", "project": minimal_project()},
        headers={"Origin": "http://127.0.0.1:8123"},
    )
    assert res.status_code == 200


def test_remote_self_claimed_origin_rejected():
    """Une origine distante qui imite l'hote du serveur (rebinding DNS) reste refusee."""
    rebound = TestClient(app, base_url="http://evil.example.com")
    res = rebound.post(
        "/api/projects",
        json={"name": "test_api_roundtrip", "project": minimal_project()},
        headers={"Origin": "http://evil.example.com"},
    )
    assert res.status_code == 403
    (security.PROJECTS_DIR / "test_api_roundtrip.json").unlink(missing_ok=True)


def test_settings_never_expose_api_key():
    res = client.get("/api/settings")
    assert res.status_code == 200
    body = res.text
    assert "groq_api_key" not in body
    assert "gsk_" not in body
    assert res.json()["groq_configured"] in (True, False)


# --------------------------------------------------------------- exports
def test_export_rejects_invalid_project():
    proj = minimal_project()
    proj["timing"]["text_start"] = 999.0  # > duration -> erreur de validation
    res = client.post("/api/exports", json={"name": "x", "project": proj})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["message"] == "Projet invalide."
    assert detail["errors"]


def test_export_job_404_when_unknown():
    assert client.get("/api/exports/nope").status_code == 404
    assert client.post("/api/exports/nope/cancel").status_code == 404


# ------------------------------------------------------------------ SPA
def test_root_serves_index_or_build_hint():
    res = client.get("/")
    if (ROOT / "web" / "dist" / "index.html").exists():
        assert res.status_code == 200
        assert "<div id=\"root\">" in res.text
    else:
        assert res.status_code == 503
        assert "npm run build" in res.text


def test_unknown_api_route_404():
    assert client.get("/api/inconnu").status_code == 404
