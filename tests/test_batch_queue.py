"""File SQLite, worker et manifeste : rendu reel remplace par un faux moteur.

Le rendu Remotion est verifie ailleurs (test_export_short, test_api) : ici on
contrat ce qui compte pour un lot — persistance, progression, echecs isoles,
annulation, reprise, manifeste — avec un moteur de rendu simulé.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from server import mediacache
from server import queue as queue_mod
from server import render as render_mod
from shortvideos import batch
from shortvideos import schema

TEMPLATE = schema.new_project("quote_cinematique" if False else "quote_cinematic")

MAPPING = {"scene.s2.quote.text": "citation", "scene.s1.hook.text": "accroche"}


class FakeRender:
    """Faux moteur : ecrit un fichier, respecte l'annulation, peut echouer."""

    def __init__(self):
        self.calls: list[str] = []
        self.tmp_names: list[str] = []
        self.cancel_after = 0  # 0 = jamais interrompu
        self.fail_on: set[int] = set()

    def __call__(self, job, project, out_path: Path) -> dict:
        written = Path(out_path).name
        # le lot ecrit toujours dans un *.part.mp4 avant le renommage final
        self.tmp_names.append(written)
        stem = written[: -len(".part.mp4")] if written.endswith(".part.mp4") else written
        self.calls.append(stem + ".mp4")
        if len(self.calls) in self.fail_on:
            raise RuntimeError("simulateur: rendu interrompu")
        if self.cancel_after and len(self.calls) >= self.cancel_after:
            # l'utilisateur a annule pendant ce rendu-la
            job.cancel_event.set()
        out_path.write_bytes(b"MP4SIM" * 8)
        return {"path": str(out_path), "size_bytes": out_path.stat().st_size, "frames": 405,
                "duration": 13.5, "fps": 30, "composition": "quote-cinematic"}


@pytest.fixture()
def lot(tmp_path, monkeypatch):
    db = tmp_path / "queue.sqlite3"
    exports = tmp_path / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    manifests = tmp_path / "manifests"

    monkeypatch.setattr(queue_mod, "BATCH_DIR", tmp_path)
    monkeypatch.setattr(queue_mod, "DB_PATH", db)
    monkeypatch.setattr(queue_mod, "MANIFEST_DIR", manifests)
    monkeypatch.setattr(queue_mod.mediacache, "output_path", lambda name: exports / name)
    with queue_mod._LOCK:
        queue_mod._ACTIVE.clear()

    fake = FakeRender()
    monkeypatch.setattr(render_mod, "render_project_to_mp4", fake)
    queue_mod.init()
    return {"tmp": tmp_path, "exports": exports, "manifests": manifests, "fake": fake, "db": db}


def _plan(rows: list[dict], assets: dict | None = None, options: dict | None = None) -> dict:
    return batch.build_plan(TEMPLATE, rows, MAPPING, assets or {"video": [], "audio": [], "image": []},
                             options or {"background": "none", "music": "none"})


def _rows(n: int) -> list[dict]:
    return [{"citation": f"Citation {i}", "accroche": f"Accroche {i}"} for i in range(1, n + 1)]


def _wait(job_id: str, timeout: float = 20.0) -> dict:
    import time

    from server.jobs import get_job

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job is not None and job.status in ("done", "error", "cancelled"):
            return job.snapshot()
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} toujours en cours")


def test_create_batch_marque_les_lignes_invalides_blocked(lot):
    rows = _rows(3) + [{"citation": "", "accroche": "A"}]
    plan = _plan(rows)
    data = queue_mod.create_batch(plan, name="lot test", model_id="citation-cinematique")
    assert data["counters"]["total"] == 4
    assert data["counters"]["queued"] == 3
    assert data["counters"]["blocked"] == 1
    assert data["status"] == "ready"
    assert data["counters"]["progress"] == 0.0


def test_start_rend_toutes_les_lignes_et_remplit_la_file(lot):
    data = queue_mod.create_batch(_plan(_rows(3)), name="lot 3", model_id="citation-cinematique")
    started = queue_mod.start_batch(data["id"])
    snapshot = _wait(started["job_id"])

    assert snapshot["status"] == "done"          # statut reel du registre de jobs
    assert snapshot["progress"] == 1.0
    after = queue_mod.get_batch(data["id"], items=True)
    assert after["status"] == "done"
    assert after["counters"]["done"] == 3
    assert after["counters"]["failed"] == 0
    assert sorted(lot["exports"].glob("*.mp4"))
    first = after["items"][0]
    assert first["status"] == "done" and first["attempts"] == 1
    assert first["frames"] == 405 and first["duration"] == 13.5
    assert Path(first["output_path"]).exists()
    assert lot["fake"].calls == [i["filename"] for i in after["items"]]
    assert all(name.endswith(".part.mp4") for name in lot["fake"].tmp_names)


def test_une_ligne_en_echec_narrete_pas_le_lot_et_retry_la_relance(lot):
    lot["fake"].fail_on = {2}
    data = queue_mod.create_batch(_plan(_rows(3)), name="echec isole", model_id="citation-cinematique")
    snapshot = _wait(queue_mod.start_batch(data["id"])["job_id"])

    assert snapshot["status"] == "done"
    after = queue_mod.get_batch(data["id"], items=True)
    assert [i["status"] for i in after["items"]] == ["done", "failed", "done"]
    assert "simul" in after["items"][1]["error"]
    assert after["counters"]["done"] == 2 and after["counters"]["failed"] == 1

    lot["fake"].fail_on = set()
    lot["fake"].calls.clear()
    retried = queue_mod.retry_failed(data["id"])
    assert retried["requeued"] == 1
    _wait(queue_mod.start_batch(data["id"])["job_id"])
    final = queue_mod.get_batch(data["id"], items=True)
    assert final["counters"]["done"] == 3
    assert lot["fake"].calls == [final["items"][1]["filename"]]  # seulement l'echec relance


def test_fichier_existiant_nest_jamais_ecrase_sans_regle(lot):
    data = queue_mod.create_batch(_plan(_rows(1)), name="protection", model_id="citation-cinematique")
    item = queue_mod.get_batch(data["id"], items=True)["items"][0]
    (lot["exports"] / item["filename"]).write_bytes(b"deja-la")

    _wait(queue_mod.start_batch(data["id"])["job_id"])
    blocked = queue_mod.get_batch(data["id"], items=True)["items"][0]
    assert blocked["status"] == "failed"
    assert "existe déjà" in blocked["error"]
    assert (lot["exports"] / item["filename"]).read_bytes() == b"deja-la"

    # avec la regle d'ecrasement du lot, le rendu remplace le fichier
    with queue_mod._db() as conn:
        conn.execute("UPDATE batches SET overwrite = 1 WHERE id = ?", (data["id"],))
        conn.execute("UPDATE items SET status = 'queued', error = '' WHERE batch_id = ?", (data["id"],))
    _wait(queue_mod.start_batch(data["id"])["job_id"])
    replaced = queue_mod.get_batch(data["id"], items=True)["items"][0]
    assert replaced["status"] == "done"
    assert (lot["exports"] / item["filename"]).read_bytes().startswith(b"MP4SIM")


def test_annulation_interrompt_le_rendu_et_marque_le_reste(lot):
    from server.jobs import JobCancelled

    fake = lot["fake"]

    def engine(job, project, out_path):
        fake.calls.append(Path(out_path).name)
        if job.cancel_event.is_set():
            raise JobCancelled()  # le moteur reel tue le sous-processus
        out_path.write_bytes(b"MP4SIM" * 8)
        if len(fake.calls) == 1:
            job.cancel_event.set()  # l'utilisateur annule pendant la premiere ligne
        return {"path": str(out_path), "size_bytes": out_path.stat().st_size,
                "frames": 405, "duration": 13.5, "fps": 30}

    render_mod.render_project_to_mp4 = engine  # remplacement du moteur de rendu
    try:
        data = queue_mod.create_batch(_plan(_rows(4)), name="annulation", model_id="citation-cinematique")
        snapshot = _wait(queue_mod.start_batch(data["id"])["job_id"])
    finally:
        render_mod.render_project_to_mp4 = fake

    after = queue_mod.get_batch(data["id"], items=True)
    assert snapshot["status"] == "cancelled"
    assert after["status"] == "cancelled"
    assert [i["status"] for i in after["items"]] == ["done", "cancelled", "cancelled", "cancelled"]
    assert after["counters"]["queued"] == 0
    assert len(list(lot["exports"].glob("*.mp4"))) == 1


def test_reprise_apres_arret_du_serveur(lot):
    data = queue_mod.create_batch(_plan(_rows(2)), name="reprise", model_id="citation-cinematique")
    items = queue_mod.get_batch(data["id"], items=True)["items"]
    with queue_mod._db() as conn:
        conn.execute("UPDATE batches SET status = 'running' WHERE id = ?", (data["id"],))
        conn.execute("UPDATE items SET status = 'running' WHERE id = ?", (items[0]["id"],))

    recovered = queue_mod.recover()
    assert recovered["items_requeued"] == 1
    after = queue_mod.get_batch(data["id"])
    assert after["status"] == "paused"
    assert "relancez" in (after["message"] or "").lower()
    assert after["counters"]["queued"] == 2


def test_un_seul_lot_tourne_a_la_fois(lot):
    data = queue_mod.create_batch(_plan(_rows(2)), name="verrou", model_id="citation-cinematique")
    with queue_mod._LOCK:
        queue_mod._ACTIVE[data["id"]] = {"job_id": "autre", "cancel": __import__("threading").Event()}
    with pytest.raises(HTTPException) as exc:
        queue_mod.start_batch(data["id"])
    assert exc.value.status_code == 409
    assert "déjà en cours" in str(exc.value.detail)


def test_ligne_invalide_nest_pas_rendue(lot):
    rows = [{"citation": "Valide", "accroche": "A"}]
    plan = _plan(rows)
    # une ref media qui ne pointe sur aucun fichier : bloquee par la validation
    project = plan["items"][0]["project"]
    project["content"]["scenes"][0]["background"]["media"] = f"media://{'f' * 32}"
    data = queue_mod.create_batch(plan, name="media absent", model_id="citation-cinematique")
    _wait(queue_mod.start_batch(data["id"])["job_id"])
    item = queue_mod.get_batch(data["id"], items=True)["items"][0]
    assert item["status"] == "failed"
    assert "invalide" in item["error"] or "introuvable" in item["error"]
    assert lot["fake"].calls == []


def test_manifeste_json_et_csv_incluent_les_lignes_bloquees(lot):
    rows = _rows(2) + [{"citation": "", "accroche": "A"}]
    plan = _plan(rows)
    data = queue_mod.create_batch(plan, name="livraison", model_id="citation-cinematique")
    _wait(queue_mod.start_batch(data["id"])["job_id"])

    result = queue_mod.write_manifest(data["id"], "json")
    payload = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert payload["summary"]["done"] == 2 and payload["summary"]["blocked"] == 1
    assert len(payload["rows"]) == 3
    assert payload["policy"]["cycling_announced"] is True
    assert payload["rows"][2]["statut"] == "blocked"
    assert payload["rows"][0]["fichier"].endswith(".mp4")

    csv_result = queue_mod.write_manifest(data["id"], "csv")
    text = Path(csv_result["manifest"]).read_text(encoding="utf-8-sig")
    parsed = list(csv.DictReader(text.splitlines()))
    assert len(parsed) == 3
    assert parsed[0]["statut"] == "done"
    assert "fichier" and parsed[2]["erreurs"]

    with pytest.raises(HTTPException):
        queue_mod.write_manifest(data["id"], "xlsx")


def test_forget_supprime_le_lot_sans_toucher_aux_mp4(lot):
    data = queue_mod.create_batch(_plan(_rows(1)), name="oubli", model_id="citation-cinematique")
    _wait(queue_mod.start_batch(data["id"])["job_id"])
    produced = list(lot["exports"].glob("*.mp4"))
    assert produced

    queue_mod.forget_batch(data["id"])
    assert queue_mod.list_batches() == []
    assert list(lot["exports"].glob("*.mp4")) == produced
