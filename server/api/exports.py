"""Export MP4 unitaire : la meme chaine que la production par lots.

Ce module ne contient plus de moteur de rendu : il applique la politique
fichier (validation, nom, ecrasement, sortie provisoire, menage) puis confie
l'execution a ``server.render.render_project_to_mp4()``, l'entree unique
egalement utilisee par la file de production.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import media as media_mod
from .. import render as render_mod
from ..jobs import Job, JobCancelled, create_job, get_job
from ..security import EXPORTS_DIR, assert_local_dir, safe_name

router = APIRouter(prefix="/api/exports", tags=["exports"])


class ExportPayload(BaseModel):
    name: str = "citation"
    project: dict
    overwrite: bool = False


def _validate_for_export(project: dict) -> tuple[list[str], list[str]]:
    """Le rendu doit trouver ses fichiers : la validation porte sur les
    references telles qu'editees (v2) ou resolues (v1 herite)."""
    return media_mod.validate_project_refs(project)


@router.post("")
def start_export(payload: ExportPayload) -> dict:
    project = payload.project
    errors, warnings = _validate_for_export(project)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Projet invalide.", "errors": errors, "warnings": warnings},
        )

    out_name = safe_name(payload.name)
    if not out_name.lower().endswith(".mp4"):
        out_name += ".mp4"
    out_path = EXPORTS_DIR / out_name
    if out_path.exists() and not payload.overwrite:
        raise HTTPException(
            status_code=409,
            detail={"message": f"Le fichier existe déjà : {out_name}", "code": "exists"},
        )

    # Copie figee : l'editeur peut changer pendant le rendu, le rendu ne voit
    # que l'etat du projet au moment de la demande.
    frozen = json.loads(json.dumps(project))

    def work(job: Job) -> dict:
        tmp_out = EXPORTS_DIR / f"{out_name}.part.mp4"
        try:
            if tmp_out.exists():
                tmp_out.unlink()
            info = render_mod.render_project_to_mp4(job, frozen, tmp_out)
            if out_path.exists():
                if not payload.overwrite:
                    raise RuntimeError(f"Le fichier existe déjà : {out_name}")
                out_path.unlink()
            tmp_out.replace(out_path)
            info["path"] = out_name
            info["warnings"] = warnings
            return info
        except JobCancelled:
            tmp_out.unlink(missing_ok=True)
            raise
        finally:
            if tmp_out.exists():
                try:
                    tmp_out.unlink()
                except OSError:
                    pass

    job = create_job("export", work)
    return {"job_id": job.id}


@router.get("/{job_id}")
def export_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job d'export introuvable.")
    return job.snapshot()


@router.post("/{job_id}/cancel")
def export_cancel(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job d'export introuvable.")
    if job.status != "running":
        return job.snapshot()
    job.cancel_event.set()
    proc = getattr(job, "result_process", None)
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass
    return job.snapshot()


@router.get("/{job_id}/file")
def export_file(job_id: str) -> FileResponse:
    """Relit la vidéo produite, pour vérification du rendu dans le navigateur.

    Le nom servi vient du job terminé : aucun chemin fourni par le client.
    """
    job = get_job(job_id)
    if job is None or job.status != "done":
        raise HTTPException(status_code=404, detail="Export terminé introuvable.")
    name = (job.result or {}).get("path") if isinstance(job.result, dict) else None
    if not name:
        raise HTTPException(status_code=404, detail="Nom du fichier de sortie absent.")
    path = assert_local_dir(EXPORTS_DIR / safe_name(str(name)))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier de sortie supprimé.")
    return FileResponse(path, media_type="video/mp4")
