"""Routes de la livraison : etat d'un lot, preparation du paquet, telechargement.

Le client ne choisit jamais un chemin : l'identifiant de lot est verifie, et le nom
du paquet est retrouve depuis le serveur. Le travail lourd (sous-titres, miniatures,
compression) part dans un job, la page le suit avec le polling deja utilise pour les
lots.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import delivery as delivery_mod
from .. import queue as queue_mod
from ..jobs import create_job
from ..security import assert_local_dir

router = APIRouter(prefix="/api/delivery", tags=["delivery"])


def _check_id(batch_id: str) -> None:
    if not batch_id or not batch_id.isalnum():
        raise HTTPException(status_code=400, detail="Identifiant de lot invalide.")


@router.get("/{batch_id}")
def delivery_status(batch_id: str) -> dict:
    _check_id(batch_id)
    return delivery_mod.status(batch_id)


@router.post("/{batch_id}/package")
def package_batch(batch_id: str) -> dict:
    """Lance l'assemblage du ZIP dans un job ; renvoie l'identifiant du job."""
    _check_id(batch_id)
    state = delivery_mod.status(batch_id)
    if state["is_packaging"]:
        raise HTTPException(status_code=409, detail="Un paquet de livraison est déjà en cours pour ce lot.")
    if state["rendered"] == 0:
        raise HTTPException(status_code=400, detail="Aucune vidéo rendue dans ce lot : rien à livrer.")
    job = create_job("delivery", lambda running: delivery_mod.build_package(batch_id, job=running))
    return {"job_id": job.id, "items": state["rendered"]}


@router.get("/{batch_id}/package/file")
def package_file(batch_id: str) -> FileResponse:
    _check_id(batch_id)
    batch = queue_mod.get_batch(batch_id, items=False)
    path = assert_local_dir(delivery_mod.package_path(batch_id, batch["name"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Paquet introuvable : préparez le livrable.")
    return FileResponse(path, filename=path.name, media_type="application/zip")
