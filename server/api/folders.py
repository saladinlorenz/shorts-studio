"""Routes des dossiers de médias connectés (fonds vidéo, musiques de fond).

Un dossier doit d'abord être enregistré (:meth:`server.folders.register`) pour
devenir une emplacement autorisé ; le scan l'importe ensuite média par média
dans ``media/`` sous forme de job, avec progression et annulation.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import folders as folders_mod
from ..jobs import Job, create_job
from ..security import BATCH_DIR

router = APIRouter(prefix="/api/folders", tags=["folders"])


class FolderPayload(BaseModel):
    path: str
    kind: str = "any"
    name: str = ""
    licence: str = ""


def _public(root: dict) -> dict:
    data = {
        "id": root["id"],
        "path": root["path"],
        "name": root["name"],
        "kind": root["kind"],
        "licence": root["licence"],
        "added_at": root["added_at"],
        "last_scan": root.get("last_scan"),
        "files": root.get("files") or [],
        "imported": len(root.get("files") or []),
        "present": Path(str(root.get("path") or "")).is_dir(),
    }
    return data


@router.get("")
def list_folders() -> dict:
    return {
        "folders": [_public(r) for r in folders_mod.list_roots()],
        "kinds": list(folders_mod.KINDS) + ["any"],
        "registry_path": str(BATCH_DIR / "folders.json"),
        "limits": {
            "max_files_per_folder": folders_mod.MAX_FILES_PER_FOLDER,
            "max_depth": folders_mod.MAX_DEPTH,
            "max_bytes": folders_mod.MAX_BYTES,
        },
    }


@router.get("/assets")
def assets(kind: str) -> dict:
    """Médias déjà importés depuis les dossiers connectés, filtrés par nature."""
    return {"kind": kind, "assets": folders_mod.assets_by_kind(kind)}


@router.post("")
def add_folder(payload: FolderPayload) -> dict:
    return _public(folders_mod.register(payload.path, payload.kind, payload.name, payload.licence))


@router.post("/{folder_id}/scan")
def start_scan(folder_id: str) -> dict:
    """Lance l'import du dossier comme job : la progression suit les fichiers,
    et une annulation conserve les médias déjà importés."""
    root = folders_mod.get_root(folder_id)

    def work(job: Job) -> dict:
        def on_progress(current: int, total: int) -> None:
            job.set_progress(current, total, f"{root['name']} · {current}/{total}")

        result = folders_mod.scan(folder_id, should_cancel=job.cancel_event.is_set, on_progress=on_progress)
        return {"summary": result["summary"], "skipped": result["skipped"]}

    job = create_job("folder-scan", work)
    return {"job_id": job.id, "folder_id": folder_id, "status": job.status}


@router.get("/{folder_id}")
def get_folder(folder_id: str) -> dict:
    return _public(folders_mod.get_root(folder_id))


@router.delete("/{folder_id}")
def remove_folder(folder_id: str) -> dict:
    if not folder_id or any(ch in folder_id for ch in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de dossier invalide.")
    root = folders_mod.unregister(folder_id)
    return {
        "id": root["id"],
        "removed": True,
        "note": "Les médias déjà importés restent disponibles dans la médiathèque.",
    }
