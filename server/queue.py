"""File de production par lots : SQLite persistant, worker, manifeste de livraison.

Un lot est créé depuis un plan (:func:`shortvideos.batch.build_plan) validé à
l'écran, puis rendu ligne par ligne par le worker. Trois propriétés comptent :

- **persistant** : ``batch/queue.sqlite3`` survive à un arrêt du serveur ; une
  ligne en cours d'écriture au moment de l'arrêt repasse en ``queued``, le lot
  est marqué ``paused`` et rien ne redémarre tout seul — c'est l'utilisateur
  qui reprend ;
- **une seule chaine de rendu** : chaque ligne passe par
  :func:`server.render.render_project_to_mp4`, exactement comme l'export
  unitaire, avec la même validation des références média avant lancement ;
- **pas d'écrasement silencieux** : un fichier de sortie déjà présent bloque la
  ligne (statut ``failed``) tant que l'option ``overwrite`` du lot n'est pas
  activée ; l'écriture réelle se fait dans un ``*.part.mp4`` renommé après
  succès.

Un seul lot tourne à la fois : le rendu est un sous-processus gourmand, deux
lots simultanés mentiraient sur la progression.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from . import media as media_mod
from . import mediacache
from . import render as render_mod
from .jobs import Job, JobCancelled, create_job, get_job
from .security import BATCH_DIR, safe_name

DB_PATH = BATCH_DIR / "queue.sqlite3"
MANIFEST_DIR = BATCH_DIR / "manifests"

_LOCK = threading.Lock()
_ACTIVE: dict[str, dict] = {}  # batch_id -> {"job_id": str, "cancel": threading.Event}

# Statuts de ligne : blocked = la ligne ne peut pas être rendue (données
# invalides), elle reste visible dans le lot et dans le manifeste.
ITEM_STATUSES = ("queued", "running", "done", "failed", "cancelled", "blocked")
BATCH_STATUSES = ("ready", "running", "paused", "done", "cancelled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _db():
    """Connexion courte : le worker et les requetes HTTP ne se les disputent pas."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init() -> None:
    with _LOCK, _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                model_id TEXT NOT NULL,
                csv_id TEXT,
                mapping TEXT,
                options TEXT,
                status TEXT NOT NULL,
                overwrite INTEGER NOT NULL DEFAULT 0,
                output_dir TEXT,
                total INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                message TEXT
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                name TEXT,
                filename TEXT NOT NULL,
                project TEXT NOT NULL,
                row_preview TEXT,
                assets TEXT,
                warnings TEXT,
                sources TEXT,
                status TEXT NOT NULL,
                error TEXT,
                output_path TEXT,
                size_bytes INTEGER,
                frames INTEGER,
                duration REAL,
                fps REAL,
                attempts INTEGER NOT NULL DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE (batch_id, position)
            );
            CREATE INDEX IF NOT EXISTS items_batch_idx ON items (batch_id, position);
            """
        )


def recover() -> dict:
    """A l'ouverture : une ligne ``running`` ne l'est plus jamais vraiment."""
    init()
    with _LOCK, _db() as conn:
        rows = conn.execute("SELECT id, name FROM items WHERE status = 'running'").fetchall()
        running_batches = conn.execute("SELECT id FROM batches WHERE status = 'running'").fetchall()
        for row in rows:
            conn.execute(
                "UPDATE items SET status = 'queued', started_at = NULL WHERE id = ?",
                (row["id"],),
            )
        for batch in running_batches:
            conn.execute(
                "UPDATE batches SET status = 'paused', message = ? WHERE id = ?",
                ("Reprise après arrêt du serveur : relancez le lot quand vous êtes prêt.", batch["id"]),
            )
    return {"items_requeued": len(rows), "batches_paused": [b["id"] for b in running_batches]}


def create_batch(
    plan: dict,
    *,
    name: str,
    model_id: str,
    csv_id: str = "",
    mapping: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> dict:
    """Enregistre un plan en lot prêt à rendre.

    Les lignes invalides du plan deviennent des items ``blocked`` : elles
    restent dans le manifeste, mais ne sont jamais rendues.
    """
    items = plan.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="Le plan ne contient aucune ligne à rendre.")

    batch_id = uuid.uuid4().hex[:12]
    with _LOCK, _db() as conn:
        conn.execute(
            "INSERT INTO batches (id, name, model_id, csv_id, mapping, options, status, overwrite,"
            " total, created_at) VALUES (?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?)",
            (
                batch_id,
                str(name or "lot").strip()[:80] or "lot",
                str(model_id),
                str(csv_id or "")[:40],
                json.dumps(mapping or {}, ensure_ascii=False),
                json.dumps(options or {}, ensure_ascii=False),
                1 if overwrite else 0,
                len(items),
                _now(),
            ),
        )
        for item in items:
            errors = item.get("errors") or []
            conn.execute(
                "INSERT INTO items (batch_id, position, name, filename, project, row_preview, assets,"
                " warnings, sources, status, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    batch_id,
                    int(item["index"]),
                    str(item.get("name") or "")[:120],
                    str(item["filename"]),
                    json.dumps(item["project"], ensure_ascii=False),
                    json.dumps(item.get("row_preview") or {}, ensure_ascii=False),
                    json.dumps(item.get("assets_used") or [], ensure_ascii=False),
                    json.dumps(item.get("warnings") or [], ensure_ascii=False),
                    json.dumps(
                        {
                            "background": item.get("background_source"),
                            "pass": item.get("background_pass"),
                            "music": item.get("music_source"),
                            "music_pass": item.get("music_pass"),
                        },
                        ensure_ascii=False,
                    ),
                    "blocked" if errors else "queued",
                    " | ".join(errors) if errors else "",
                ),
            )
    return get_batch(batch_id)


def _batch_row(conn: sqlite3.Connection, batch_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Lot introuvable.")
    return row


def _decode(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("mapping", "options", "row_preview", "assets", "warnings", "sources", "project"):
        if key in data and isinstance(data[key], str):
            try:
                data[key] = json.loads(data[key])
            except json.JSONDecodeError:
                data[key] = [] if key in ("assets", "warnings") else {}
    data["overwrite"] = bool(data.get("overwrite"))
    return data


def counters(conn: sqlite3.Connection, batch_id: str) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM items WHERE batch_id = ? GROUP BY status", (batch_id,)
    ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    total = sum(by_status.values())
    rendered = by_status.get("done", 0)
    return {
        "total": total,
        "rendered": rendered,
        **{status: by_status.get(status, 0) for status in ITEM_STATUSES},
        "progress": round(rendered / total, 4) if total else 0.0,
    }


def get_batch(batch_id: str, *, items: bool = False, status: str = "") -> dict:
    with _db() as conn:
        row = _batch_row(conn, batch_id)
        data = _decode(row)
        data["counters"] = counters(conn, batch_id)
        with _LOCK:
            active = _ACTIVE.get(batch_id)
        data["job_id"] = active["job_id"] if active else ""
        data["is_running"] = bool(active)
        if items:
            query = "SELECT * FROM items WHERE batch_id = ?"
            params: list[Any] = [batch_id]
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY position"
            data["items"] = [_decode(r) for r in conn.execute(query, params)]
    return data


def list_batches(limit: int = 30) -> list[dict]:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM batches ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for row in rows:
            data = _decode(row)
            data["counters"] = counters(conn, row["id"])
            with _LOCK:
                data["is_running"] = row["id"] in _ACTIVE
            out.append(data)
        return out


def start_batch(batch_id: str) -> dict:
    """Lance (ou relance) le rendu d'un lot dans un thread secondaire."""
    with _db() as conn:
        row = _batch_row(conn, batch_id)
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM items WHERE batch_id = ? AND status IN ('queued', 'failed', 'cancelled')",
            (batch_id,),
        ).fetchone()["n"]
    if pending == 0:
        raise HTTPException(status_code=400, detail="Aucune ligne en attente dans ce lot.")
    with _LOCK:
        if _ACTIVE:
            other = ", ".join(sorted(_ACTIVE))
            raise HTTPException(
                status_code=409,
                detail=f"Un lot est déjà en cours de rendu ({other}) : un seul lot à la fois.",
            )
        cancel_event = threading.Event()
        _ACTIVE[batch_id] = {"job_id": "", "cancel": cancel_event}

    job = create_job("batch", _worker(batch_id, cancel_event))
    with _LOCK:
        entry = _ACTIVE.get(batch_id)
        if entry is not None:
            entry["job_id"] = job.id
    return {"batch": get_batch(batch_id), "job_id": job.id, "status": job.status}


def _worker(batch_id: str, cancel_event: threading.Event):
    def work(job: Job) -> dict:
        try:
            return _render_queue(batch_id, cancel_event, job)
        finally:
            with _LOCK:
                _ACTIVE.pop(batch_id, None)

    return work


def _render_queue(batch_id: str, cancel_event: threading.Event, job: Job) -> dict:
    with _db() as conn:
        batch = _decode(_batch_row(conn, batch_id))
        todo = [
            _decode(r)
            for r in conn.execute(
                "SELECT * FROM items WHERE batch_id = ? AND status IN ('queued', 'failed', 'cancelled')"
                " ORDER BY position",
                (batch_id,),
            )
        ]
        conn.execute(
            "UPDATE batches SET status = 'running', started_at = COALESCE(started_at, ?), message = ?,"
            " finished_at = NULL WHERE id = ?",
            (_now(), f"Rendu en cours ({len(todo)} ligne(s))…", batch_id),
        )
    total = len(todo)
    done = 0
    failures = 0
    for item in todo:
        if cancel_event.is_set():
            _finish_item(item["id"], "cancelled", error="Annulé avant le rendu.")
            continue
        done += 1
        job.set_progress(done - 1, total, f"{item['filename']} ({done}/{total})")
        try:
            info = _render_item(job, item, batch, cancel_event, done, total)
            _finish_item(
                item["id"],
                "done",
                output_path=info["path"],
                size_bytes=info.get("size_bytes"),
                frames=info.get("frames"),
                duration=info.get("duration"),
                fps=info.get("fps"),
            )
        except JobCancelled:
            _finish_item(item["id"], "cancelled", error="Rendu interrompu.")
            done -= 1
            _cancel_remaining(batch_id)
            break
        except Exception as e:  # noqa: BLE001 : la ligne échoue, le lot continue
            failures += 1
            _finish_item(item["id"], "failed", error=str(e)[:800])

        with _db() as conn:
            conn.execute(
                "UPDATE batches SET message = ? WHERE id = ?",
                (f"Ligne {done}/{total} rendue — {failures} échec(s).", batch_id),
            )
        job.set_progress(done, total, f"{done}/{total} lignes")

    summary = {"rendered": done, "failures": failures, "total": total}
    with _db() as conn:
        state = "cancelled" if cancel_event.is_set() else "done"
        conn.execute(
            "UPDATE batches SET status = ?, finished_at = ?, message = ? WHERE id = ?",
            (state, _now(), f"{done} ligne(s) sur {total} rendues, {failures} échec(s).", batch_id),
        )
        summary["counters"] = counters(conn, batch_id)
    if cancel_event.is_set():
        # le registre de jobs doit porter le meme etat que le lot
        raise JobCancelled()
    return summary


def _cancel_remaining(batch_id: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE items SET status = 'cancelled', error = 'Annulé.' WHERE batch_id = ? AND status = 'queued'",
            (batch_id,),
        )


def _render_item(
    job: Job, item: dict, batch: dict, cancel_event: threading.Event, position: int, total: int
) -> dict:
    """Validation, puis rendu d'une ligne par la chaine unitaire."""
    project = item["project"]
    # la meme validation que l'export unitaire : donnees + existence des medias
    errors, _warnings = media_mod.validate_project_refs(project)
    if errors:
        raise RuntimeError("Projet de la ligne invalide : " + " ; ".join(errors[:6]))

    out_path = mediacache.output_path(item["filename"])
    if out_path.exists() and not batch["overwrite"]:
        raise RuntimeError(f"Le fichier existe déjà : {out_path.name} (activez « écraser » pour le lot).")

    handle = _ItemHandle(job, item["id"], cancel_event, position, total)
    tmp = out_path.parent / f"{out_path.stem}.part.mp4"
    tmp.unlink(missing_ok=True)
    _finish_item(item["id"], "running")
    try:
        info = render_mod.render_project_to_mp4(handle, project, tmp)
        if batch["overwrite"]:
            out_path.unlink(missing_ok=True)
        tmp.replace(out_path)
        info["path"] = str(out_path)
        return info
    finally:
        tmp.unlink(missing_ok=True)


class _ItemHandle:
    """Adaptateur ligne de lot : le moteur de rendu ne demande qu'un job."""

    def __init__(self, job: Job, item_id: int, cancel_event: threading.Event, position: int, total: int):
        self.id = f"lot{job.id}-{item_id}"
        self.cancel_event = cancel_event
        self._job = job
        self._position = position
        self._total = total

    def set_progress(self, current: int, frames_total: int, message: str = "") -> None:
        # progression du lot = lignes terminees + frames de la ligne en cours
        inside = (current / frames_total) if frames_total else 0.0
        self._job.set_progress(
            self._position - 1 + inside,
            self._total,
            f"ligne {self._position}/{self._total} — {message or ''}".strip(),
        )


def _finish_item(item_id: int, status: str, **fields: Any) -> None:
    columns = ["status = ?"]
    values: list[Any] = [status]
    if status in ("done", "failed", "cancelled"):
        columns.append("finished_at = ?")
        values.append(_now())
    if status == "running":
        columns.append("attempts = attempts + 1")
        columns.append("started_at = ?")
        values.append(_now())
    for key, value in fields.items():
        columns.append(f"{key} = ?")
        values.append(value)
    values.append(item_id)
    with _db() as conn:
        conn.execute(f"UPDATE items SET {', '.join(columns)} WHERE id = ?", values)


def retry_failed(batch_id: str) -> dict:
    """Relance les échecs uniquement : les lignes déjà rendues ne sont pas refaites."""
    with _db() as conn:
        cur = conn.execute(
            "UPDATE items SET status = 'queued', error = '' WHERE batch_id = ? AND status = 'failed'",
            (batch_id,),
        )
        reset = cur.rowcount
    if reset == 0:
        raise HTTPException(status_code=400, detail="Aucune ligne en échec à relancer.")
    return {"batch": get_batch(batch_id), "requeued": reset}


def cancel(batch_id: str) -> dict:
    with _LOCK:
        active = _ACTIVE.get(batch_id)
        if active is None:
            raise HTTPException(status_code=400, detail="Ce lot n'est pas en cours de rendu.")
        active["cancel"].set()
    job = get_job(active["job_id"]) if active["job_id"] else None
    if job is not None:
        job.cancel_event.set()
        message = job.snapshot()["message"]
    else:
        message = "Annulation demandée…"
    return {"batch": get_batch(batch_id), "message": message}


def forget_batch(batch_id: str) -> dict:
    """Supprime le lot de la file : les MP4 déjà produits ne bougent pas."""
    with _LOCK:
        if batch_id in _ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Le lot est en cours de rendu : annulez-le d'abord.",
            )
    with _db() as conn:
        _batch_row(conn, batch_id)
        conn.execute("DELETE FROM items WHERE batch_id = ?", (batch_id,))
        conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
    return {"deleted": batch_id}


# --- manifeste de livraison ------------------------------------------------


def manifest_rows(batch_id: str) -> list[dict]:
    with _db() as conn:
        _batch_row(conn, batch_id)
        rows = [
            _decode(r)
            for r in conn.execute("SELECT * FROM items WHERE batch_id = ? ORDER BY position", (batch_id,))
        ]
    out = []
    for item in rows:
        sources = item.get("sources") or {}
        assets = item.get("assets") or []
        out.append(
            {
                "position": item["position"],
                "nom": item["name"] or "",
                "fichier": Path(item["filename"]).name,
                "statut": item["status"],
                "chemin": item.get("output_path") or "",
                "octets": item.get("size_bytes") or 0,
                "frames": item.get("frames") or 0,
                "duree_s": item.get("duration") or 0,
                "fps": item.get("fps") or 0,
                "fond": _asset_name(assets, ".background"),
                "fond_source": sources.get("background") or "",
                "fond_pass": sources.get("pass") or "",
                "musique": _asset_name(assets, "audio.music"),
                "musique_source": sources.get("music") or "",
                "musique_pass": sources.get("music_pass") or "",
                "titres": _titles(item),
                "avertissements": " | ".join(item.get("warnings") or []),
                "erreurs": item.get("error") or "",
            }
        )
    return out


def _asset_name(assets: list[dict], suffix: str) -> str:
    for asset in assets:
        if str(asset.get("field", "")).endswith(suffix):
            return str(asset.get("name") or asset.get("media_id") or "")
    return ""


def _titles(item: dict) -> str:
    texts = []
    for scene in item["project"].get("content", {}).get("scenes", []):
        for layer in scene.get("layers", []):
            if layer.get("type") == "text" and str(layer.get("text", "")).strip():
                texts.append(str(layer["text"]).strip())
    return " / ".join(texts)[:400]


def write_manifest(batch_id: str, fmt: str = "json") -> dict:
    """Ecrit le manifeste du lot dans ``batch/manifests/`` et le renvoie."""
    fmt = (fmt or "json").lower()
    if fmt not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="Manifeste demandé en json ou csv.")
    batch = get_batch(batch_id, items=False)
    rows = manifest_rows(batch_id)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{batch_id}-{safe_name(batch['name'])}"
    path = MANIFEST_DIR / f"{stem}.{fmt}"
    if fmt == "json":
        payload = {
            "batch": {k: v for k, v in batch.items() if k not in {"items"}},
            "summary": batch["counters"],
            "policy": {"column_wins": True, "cycling_announced": True, "overwrite": batch["overwrite"]},
            "rows": rows,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["position"])
            writer.writeheader()
            writer.writerows(rows)
    return {"manifest": str(path), "format": fmt, "rows": len(rows), "summary": batch["counters"]}


init()
