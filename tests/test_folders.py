"""Dossiers de médias connectés : enregistrement borné, import, dédoublonnage.

Les chemins réels du projet (media/, batch/) sont remplacés par un répertoire
temporaire : aucun test n'écrit dans la médiathèque de travail.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from server import folders, media
from server import mediacache


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    provenance_dir = media_dir / "provenance"
    batch_dir = tmp_path / "batch"
    for d in (media_dir, provenance_dir, batch_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(media, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(media, "PROVENANCE_DIR", provenance_dir)
    monkeypatch.setattr(folders, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(folders, "PROVENANCE_DIR", provenance_dir)
    monkeypatch.setattr(folders, "BATCH_DIR", batch_dir)
    monkeypatch.setattr(folders, "FOLDERS_FILE", batch_dir / "folders.json")
    # le cache de rendu écrit dans web/ : hors du périmètre de ces tests
    monkeypatch.setattr(mediacache, "ensure_cached", lambda media_id: None)
    return {"media": media_dir, "batch": batch_dir, "root": tmp_path}


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_register_refuses_relative_missing_and_drive_root(sandbox):
    with pytest.raises(HTTPException) as exc:
        folders.register("medias/fonds")
    assert "absolu" in str(exc.value.detail)

    with pytest.raises(HTTPException) as exc:
        folders.register(str(sandbox["root"] / "inexistant"))
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        folders.register("C:\\")
    assert "racine de lecteur" in str(exc.value.detail).lower()


def test_register_is_idempotent_and_stays_in_registry(sandbox):
    source = sandbox["root"] / "fonds"
    _write(source / "a.mp4", b"video-a")
    first = folders.register(str(source), kind="video")
    second = folders.register(str(source.resolve()), kind="video")
    assert first["id"] == second["id"]
    assert len(folders.load_roots()) == 1
    # rien n'est importé avant un scan explicite
    assert first["files"] == []
    assert list(sandbox["media"].glob("*.mp4")) == []


def test_scan_imports_only_allowed_kinds_with_unknown_licence(sandbox):
    source = sandbox["root"] / "dossier au nom avec espaces"
    _write(source / "fond 1.mp4", b"fundamentale-1")
    _write(source / "musique.mp3", b"boucle-stereo")
    _write(source / "note.txt", b"pas un media")
    _write(source / ".cache.mp4", b"cache")
    _write(source / "sous-dossier" / "fond 2.mov", b"fundamentale-2")

    root = folders.register(str(source), kind="any")
    result = folders.scan(root["id"])

    names = [f["rel"] for f in result["imported"]]
    assert names == ["fond 1.mp4", "musique.mp3", "sous-dossier/fond 2.mov"]  # ordre déterministe
    assert result["summary"]["new"] == 3
    assert result["skipped"] == []

    for entry in result["imported"]:
        assert entry["ref"].startswith("media://")
        assert entry["licence"] == "inconnue"
        stored = sandbox["media"] / f"{entry['media_id']}{Path(entry['name']).suffix}"
        assert stored.exists()
        prov = json.loads((sandbox["media"] / "provenance" / f"{entry['media_id']}.json").read_text(encoding="utf-8"))
        assert prov["licence"] == "inconnue"
        assert prov["content_hash"] == entry["content_hash"]
        assert "dossier au nom avec espaces" in prov["source"]

    # le fichier non média n'a pas été copié
    assert list(sandbox["media"].glob("*.txt")) == []


def test_rescan_never_duplicates_bytes(sandbox):
    source = sandbox["root"] / "musiques"
    _write(source / "loop.wav", b"une-boucle-audio")
    root = folders.register(str(source), kind="audio")

    first = folders.scan(root["id"])
    ids_before = sorted(p.name for p in sandbox["media"].glob("*.wav"))
    second = folders.scan(root["id"])

    assert first["summary"]["new"] == 1
    assert second["summary"]["new"] == 0
    assert second["summary"]["existing"] == 1
    assert second["imported"][0]["already_present"] is True
    assert second["imported"][0]["media_id"] == first["imported"][0]["media_id"]
    assert sorted(p.name for p in sandbox["media"].glob("*.wav")) == ids_before


def test_same_content_in_two_folders_shares_one_media(sandbox):
    alpha = sandbox["root"] / "alpha"
    beta = sandbox["root"] / "beta"
    _write(alpha / "fond.mp4", b"contenu-partage")
    _write(beta / "copie-de-fond.mp4", b"contenu-partage")

    a = folders.scan(folders.register(str(alpha), kind="video")["id"])
    b = folders.scan(folders.register(str(beta), kind="video")["id"])

    assert b["imported"][0]["media_id"] == a["imported"][0]["media_id"]
    assert b["imported"][0]["already_present"] is True
    assert len(list(sandbox["media"].glob("*.mp4"))) == 1


def test_oversized_and_empty_files_are_skipped(sandbox, monkeypatch):
    source = sandbox["root"] / "mixtes"
    _write(source / "video-lourde.mp4", b"x" * 40)
    _write(source / "vide.mp3", b"")
    _write(source / "leger.mp4", b"ok")
    monkeypatch.setattr(folders, "MAX_BYTES", 32)

    root = folders.register(str(source), kind="any")
    result = folders.scan(root["id"])

    reasons = {s["reason"] for s in result["skipped"]}
    assert any("max 32" in r for r in reasons)
    assert "fichier vide" in reasons
    assert [f["rel"] for f in result["imported"]] == ["leger.mp4"]


def test_assets_by_kind_and_missing_media(sandbox):
    source = sandbox["root"] / "ressources"
    _write(source / "fond.mp4", b"fond-unique")
    _write(source / "boucle.mp3", b"boucle-unique")
    root = folders.register(str(source), kind="any")
    folders.scan(root["id"])

    videos = folders.assets_by_kind("video")
    audios = folders.assets_by_kind("audio")
    assert [v["name"] for v in videos] == ["fond.mp4"]
    assert [a["folder"] for a in audios] == [root["name"]]

    # un média disparu du disque n'est pas proposé au lot
    victim = audios[0]["media_id"]
    for path in sandbox["media"].glob(f"{victim}.*"):
        path.unlink()
    assert folders.assets_by_kind("audio") == []


def test_scan_reports_interruption_without_losing_imported_media(sandbox):
    source = sandbox["root"] / "long"
    for i in range(4):
        _write(source / f"fond-{i}.mp4", f"contenu-{i}".encode())
    root = folders.register(str(source), kind="video")

    calls = {"n": 0}

    def cancel_after_two():
        calls["n"] += 1
        return calls["n"] > 2

    result = folders.scan(root["id"], should_cancel=cancel_after_two)
    assert result["summary"]["interrupted"] is True
    assert result["summary"]["found"] == 4
    assert len(result["imported"]) == 2
    assert len(list(sandbox["media"].glob("*.mp4"))) == 2


def test_unregister_keeps_imported_media(sandbox):
    source = sandbox["root"] / "a-supprimer"
    _write(source / "fond.mp4", b"a-supprimer")
    root = folders.register(str(source), kind="video")
    media_id = folders.scan(root["id"])["imported"][0]["media_id"]

    folders.unregister(root["id"])
    assert folders.load_roots() == []
    assert list(sandbox["media"].glob(f"{media_id}.*"))


def test_api_exposes_folders_and_assets(sandbox):
    from fastapi.testclient import TestClient

    from server.app import app

    client = TestClient(app)
    source = sandbox["root"] / "fonds api"
    _write(source / "fond.mp4", b"fond-pour-api")

    listed = client.get("/api/folders").json()
    assert "video" in listed["kinds"] and "any" in listed["kinds"]
    assert listed["limits"]["max_depth"] == folders.MAX_DEPTH

    created = client.post("/api/folders", json={"path": str(source), "kind": "any"})
    assert created.status_code == 200
    folder_id = created.json()["id"]

    folders.scan(folder_id)
    body = client.get("/api/folders").json()["folders"]
    entry = next(f for f in body if f["id"] == folder_id)
    assert entry["present"] is True and entry["imported"] == 1

    assets = client.get("/api/folders/assets", params={"kind": "video"}).json()["assets"]
    assert [a["name"] for a in assets] == ["fond.mp4"]
    assert assets[0]["ref"].startswith("media://")

    assert client.get("/api/folders/assets", params={"kind": "inconnu"}).status_code == 400
    assert client.get("/api/folders/..%5Cserver").status_code == 400
    assert client.delete(f"/api/folders/{folder_id}").json()["removed"] is True
