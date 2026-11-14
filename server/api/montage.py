"""Montage footage : validation d'un EDL et rendu MP4 par FFmpeg.

Deux routes seulement ecrivent quelque chose : ``POST /api/montage/render``
cree un job, et ce job produit un fichier dans ``exports/``. L'EDL ne contient
que des references ``media://<id>`` : aucune source distante, aucun chemin
fourni par le client n'atteint FFmpeg.

Le rendu est confie a ``shortvideos.timeline.render_timeline()`` ; ce module ne
contient aucune logique FFmpeg.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from shortvideos import edl as edl_mod
from shortvideos.timeline import TimelineCancelled, TimelineError, render_timeline

from .. import media as media_mod
from ..jobs import Job, JobCancelled, create_job, get_job
from ..security import EXPORTS_DIR, assert_local_dir, safe_name

router = APIRouter(prefix="/api/montage", tags=["montage"])


class EDLPayload(BaseModel):
    edl: dict


class MontagePayload(EDLPayload):
    name: str = "montage"
    overwrite: bool = False


def _media_exists(media_id: str) -> bool:
    """Un identifiant resolu dans MEDIA_DIR ; toute erreur vaut « absent »."""
    try:
        media_mod.resolve_media(media_id)
        return True
    except HTTPException:
        return False


def _check(edl: dict) -> tuple[dict, list[str], list[str]]:
    """Normalise puis valide ; retourne (edl normalise, erreurs, avertissements)."""
    normalized = edl_mod.normalize(edl)
    errors, warnings = edl_mod.validate(normalized, media_exists=_media_exists)
    return normalized, errors, warnings


@router.post("/validate")
def validate_montage(payload: EDLPayload) -> dict:
    """Controle un EDL sans rien ecrire : erreurs indexees, duree, plan normalise."""
    normalized, errors, warnings = _check(payload.edl)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "duration_seconds": round(edl_mod.timeline_duration(normalized), 3) if not errors else 0.0,
        "cuts": len(normalized.get("cuts") or []),
        "edl": normalized,
    }


@router.post("")
def start_montage(payload: MontagePayload) -> dict:
    """Lance le rendu d'un EDL valide. Le fichier sort dans ``exports/``."""
    _, errors, warnings = _check(payload.edl)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Montage invalide.", "errors": errors, "warnings": warnings},
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

    # Copie figee : le plan ne peut pas changer pendant le rendu.
    frozen = json.loads(json.dumps(payload.edl))

    def work(job: Job) -> dict:
        tmp_out = EXPORTS_DIR / f"{out_name}.part.mp4"
        try:
            if tmp_out.exists():
                tmp_out.unlink()
            info = render_timeline(
                job,
                frozen,
                tmp_out,
                media_lookup=media_mod.resolve_media,
            )
            if out_path.exists():
                if not payload.overwrite:
                    raise RuntimeError(f"Le fichier existe déjà : {out_name}")
                out_path.unlink()
            tmp_out.replace(out_path)
            info["path"] = out_name
            info["warnings"] = warnings + list(info.get("warnings") or [])
            return info
        except TimelineCancelled as exc:
            tmp_out.unlink(missing_ok=True)
            raise JobCancelled() from exc
        except TimelineError as exc:
            tmp_out.unlink(missing_ok=True)
            raise RuntimeError(str(exc)) from exc
        finally:
            if tmp_out.exists():
                try:
                    tmp_out.unlink()
                except OSError:
                    pass

    job = create_job("montage", work)
    return {"job_id": job.id}


@router.get("/{job_id}")
def montage_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job de montage introuvable.")
    return job.snapshot()


@router.post("/{job_id}/cancel")
def montage_cancel(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job de montage introuvable.")
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
def montage_file(job_id: str) -> FileResponse:
    """Relit le montage produit ; le nom vient du job, jamais du client."""
    job = get_job(job_id)
    if job is None or job.status != "done":
        raise HTTPException(status_code=404, detail="Montage terminé introuvable.")
    name = (job.result or {}).get("path") if isinstance(job.result, dict) else None
    if not name:
        raise HTTPException(status_code=404, detail="Nom du fichier de sortie absent.")
    path = assert_local_dir(EXPORTS_DIR / safe_name(str(name)))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier de sortie supprimé.")
    return FileResponse(path, media_type="video/mp4")
