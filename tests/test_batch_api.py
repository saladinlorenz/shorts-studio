"""Route complete d'un lot : CSV -> plan -> rendu -> manifeste, par HTTP.

Rend la chaine verifiable de bout en bout sans appeler Remotion : le moteur de
rendu est simule, tout le reste (dossier connecte, import CSV, mapping, plan,
file SQLite, manifeste) est le code de production.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import csv_source
from server import folders
from server import queue as queue_mod
from server import render as render_mod
from server.app import app
from shortvideos import validation

CSV = "titre;citation;auteur\nCourage;« Avancer. »;Amelia\nLiberte;« Choisir. »;Bruno\nPatience;« Attendre. »;Cloe\n".encode(
    "cp1252"
)


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    provenance = media_dir / "provenance"
    batch_dir = tmp_path / "batch"
    exports = tmp_path / "exports"
    for path in (media_dir, provenance, batch_dir, exports):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(render_mod, "render_project_to_mp4", _fake_render(exports))
    monkeypatch.setattr(queue_mod.mediacache, "output_path", lambda name: exports / name)
    monkeypatch.setattr(queue_mod, "BATCH_DIR", batch_dir)
    monkeypatch.setattr(queue_mod, "DB_PATH", batch_dir / "queue.sqlite3")
    monkeypatch.setattr(queue_mod, "MANIFEST_DIR", batch_dir / "manifests")
    monkeypatch.setattr(csv_source, "BATCH_DIR", batch_dir)
    monkeypatch.setattr(folders, "BATCH_DIR", batch_dir)
    monkeypatch.setattr(folders, "FOLDERS_FILE", batch_dir / "folders.json")
    monkeypatch.setattr(folders, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(folders, "PROVENANCE_DIR", provenance)
    monkeypatch.setattr("server.media.MEDIA_DIR", media_dir)
    monkeypatch.setattr("server.media.PROVENANCE_DIR", provenance)
    monkeypatch.setattr("server.mediacache.ensure_cached", lambda media_id: None)
    # les fichiers de sortie du lot sont servis depuis EXPORTS_DIR : ici le dossier temporaire
    monkeypatch.setattr("server.api.batch.EXPORTS_DIR", exports)
    monkeypatch.setattr("server.api.batch.assert_local_dir", lambda path: path)
    # la validation resolve media:// depuis le dossier media/ du projet
    monkeypatch.setattr(validation, "MEDIA_STORE", media_dir)
    with queue_mod._LOCK:
        queue_mod._ACTIVE.clear()
    queue_mod.init()
    return {"tmp": tmp_path, "exports": exports, "batch": batch_dir, "media": media_dir}


def _fake_render(exports: Path):
    calls: list[str] = []

    def engine(job, project, out_path):
        calls.append(Path(out_path).name)
        for frame in (0, 250, 405):
            job.set_progress(frame, 405, f"Rendu {frame}/405")
        Path(out_path).write_bytes(b"MP4SIM" * 16)
        return {
            "path": str(out_path),
            "size_bytes": Path(out_path).stat().st_size,
            "frames": 405,
            "duration": 13.5,
            "fps": 30,
            "composition": "quote-cinematic",
        }

    engine.calls = calls
    return engine


def _wait_job(client: TestClient, job_id: str) -> dict:
    deadline = time.time() + 20
    while time.time() < deadline:
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] in ("done", "error", "cancelled"):
            return snapshot
        time.sleep(0.05)
    raise AssertionError("job jamais termine")


def _connect_two_backgrounds(tmp_path: Path, client: TestClient) -> dict:
    source = tmp_path / "fonds de video"
    source.mkdir(parents=True, exist_ok=True)
    for name, payload in (("fond-1.mp4", b"premier-fond"), ("fond-2.mp4", b"deuxieme-fond")):
        (source / name).write_bytes(payload)
    folder = client.post("/api/folders", json={"path": str(source), "kind": "video", "name": "mes fonds"}).json()
    scan = client.post(f"/api/folders/{folder['id']}/scan").json()
    assert _wait_job(client, scan["job_id"])["status"] == "done"
    return client.get(f"/api/folders/{folder['id']}").json()


def test_lot_de_bout_en_bout(studio):
    client = TestClient(app)
    folder = _connect_two_backgrounds(studio["tmp"], client)

    setup = client.get("/api/batch/setup").json()
    assert any(m["id"] == "citation-cinematique" for m in setup["models"])
    assert setup["folders"][0]["id"] == folder["id"]
    assert setup["policy"]["cycling"].startswith("le cycle")
    assert len(setup["assets"]["video"]) == 2

    uploaded = client.post(
        "/api/batch/csv",
        files={"file": ("citations.csv", CSV, "text/csv")},
        data={"model": "citation-cinematique"},
    )
    assert uploaded.status_code == 200
    csv_body = uploaded.json()
    assert csv_body["columns"] == ["titre", "citation", "auteur"]
    assert csv_body["row_count"] == 3
    assert csv_body["suggested_mapping"]["scene.s2.quote.text"] == "citation"

    mapping = {
        "title": "titre",
        "scene.s2.quote.text": "citation",
        "scene.s2.author.text": "auteur",
    }
    planned = client.post(
        "/api/batch/plan",
        json={"model": "citation-cinematique", "csv_id": csv_body["csv_id"], "mapping": mapping,
              "options": {"background": "auto", "music": "auto"}},
    ).json()
    assert planned["summary"]["rows"] == 3
    assert planned["summary"]["ready"] == 3
    assert planned["summary"]["cycled_background"] is True  # 2 fonds pour 3 lignes
    assert [i["filename"] for i in planned["items"]] == [
        "001-courage.mp4",
        "002-liberte.mp4",
        "003-patience.mp4",
    ]
    assert "project" not in planned["items"][0]
    assert any("cycle reprend" in w for w in planned["warnings"])

    line = client.post(
        "/api/batch/line",
        json={"model": "citation-cinematique", "csv_id": csv_body["csv_id"], "mapping": mapping,
              "options": {"background": "auto", "music": "auto"}},
        params={"position": 3},
    ).json()
    first_fond = folder["files"][0]
    scene_media = [s["background"]["media"] for s in line["project"]["content"]["scenes"]]
    # ligne 3 sur 2 fonds : le cycle reprend au premier fichier pour toutes les scenes vides
    assert scene_media == [first_fond["ref"]] * 3
    assert line["item"]["background_pass"] == 2
    assert line["item"]["index"] == 3

    started = client.post(
        "/api/batch/start",
        json={"model": "citation-cinematique", "csv_id": csv_body["csv_id"], "mapping": mapping,
              "name": "livraison client", "options": {"background": "auto", "music": "auto"}},
    )
    assert started.status_code == 200
    body = started.json()
    snapshot = _wait_job(client, body["job_id"])
    assert snapshot["status"] == "done"
    assert snapshot["progress"] == 1.0

    batch_id = body["batch"]["id"]
    detail = client.get(f"/api/batch/{batch_id}", params={"items": "true"}).json()
    assert detail["status"] == "done"
    assert detail["counters"]["done"] == 3
    assert [i["status"] for i in detail["items"]] == ["done", "done", "done"]
    assert sorted(p.name for p in studio["exports"].glob("*.mp4")) == [
        "001-courage.mp4",
        "002-liberte.mp4",
        "003-patience.mp4",
    ]
    # aucun fichier provisoire ne traine
    assert list(studio["exports"].glob("*.part.mp4")) == []

    listed = client.get("/api/batch").json()["batches"]
    assert listed[0]["id"] == batch_id and listed[0]["counters"]["done"] == 3

    manifest = client.get(f"/api/batch/{batch_id}/manifest", params={"format": "json"}).json()
    payload = json.loads(Path(manifest["manifest"]).read_text(encoding="utf-8"))
    assert payload["summary"]["done"] == 3
    assert payload["rows"][0]["fichier"] == "001-courage.mp4"
    assert payload["rows"][0]["fond_source"] == "rotation"
    assert payload["rows"][2]["fond_pass"] == 2  # le 3e lot boucle sur le 1er fond

    csv_manifest = client.get(f"/api/batch/{batch_id}/manifest", params={"format": "csv"}).json()
    assert Path(csv_manifest["manifest"]).read_text(encoding="utf-8-sig").splitlines()[0].startswith("position,")

    # telechargement du manifeste et relecture d'une ligne depuis le navigateur
    download = client.get(f"/api/batch/{batch_id}/manifest/file", params={"format": "csv"})
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    # BOM conserve : Excel ouvre le manifeste sans gabarit de colonnes
    assert download.content.startswith("position,".encode("utf-8-sig"))

    playable = client.get(f"/api/batch/{batch_id}/file", params={"position": 1})
    assert playable.status_code == 200
    assert playable.content == b"MP4SIM" * 16
    assert client.get(f"/api/batch/{batch_id}/file", params={"position": 99}).status_code == 404


def test_routes_refusent_les_identifiants_douteux_et_un_lot_inexistant(studio):
    client = TestClient(app)
    assert client.get("/api/batch/..%5Cqueue").status_code == 400
    assert client.get("/api/batch/zzzzzzzzzzzz").status_code == 404
    assert client.get("/api/batch/csv/zzzzzzzzzzzz").status_code == 404
    assert client.post("/api/batch/csv", files={"file": ("vide.csv", b"", "text/csv")}).status_code == 400


def test_plan_sans_mapping_texte_bloque_le_demarrage(studio):
    client = TestClient(app)
    uploaded = client.post("/api/batch/csv", files={"file": ("c.csv", CSV, "text/csv")}).json()
    plan = client.post(
        "/api/batch/plan",
        json={"model": "citation-cinematique", "csv_id": uploaded["csv_id"], "mapping": {},
              "options": {"background": "none", "music": "none"}},
    ).json()
    # aucun champ requis vide : les projets gardent les textes du modele
    assert plan["summary"]["ready"] == 3
    assert plan["summary"]["auto_background"] is False

    started = client.post(
        "/api/batch/start",
        json={"model": "citation-cinematique", "csv_id": uploaded["csv_id"], "mapping": {"title": "absente"},
              "options": {"background": "none", "music": "none"}},
    )
    assert started.status_code == 400
    assert started.json()["detail"]["invalid_rows"] == [1, 2, 3]
