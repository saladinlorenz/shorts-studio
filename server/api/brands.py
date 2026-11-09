"""Routes des packs de marque client.

Le dossier ``brands/`` est un depot de fichiers JSON ; ces routes ne font que
valider, normaliser et borner les identifiants. L'application d'un pack renvoie
toujours un projet a revoir : aucune route n'ecrit dans un projet de travail.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import brands as brands_mod
from ..security import BRANDS_DIR

router = APIRouter(prefix="/api/brands", tags=["brands"])


class BrandPayload(BaseModel):
    pack: dict
    brand_id: str | None = None


class ApplyPayload(BaseModel):
    project: dict


class CapturePayload(BaseModel):
    project: dict
    label: str = ""
    notes: str = ""


def _check_id(brand_id: str) -> None:
    if not brand_id or any(ch in brand_id for ch in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de pack invalide.")


@router.get("")
def list_brands() -> dict:
    return {"brands": brands_mod.list_brands(), "folder": BRANDS_DIR.name, "folder_path": str(BRANDS_DIR)}


@router.get("/{brand_id}")
def get_brand(brand_id: str) -> dict:
    _check_id(brand_id)
    return {"id": brand_id, "pack": brands_mod.get_pack(brand_id)}


@router.post("")
def save_brand(payload: BrandPayload) -> dict:
    if payload.brand_id is not None:
        _check_id(payload.brand_id)
    return brands_mod.save_brand(payload.pack, payload.brand_id)


@router.delete("/{brand_id}")
def delete_brand(brand_id: str) -> dict:
    _check_id(brand_id)
    return brands_mod.delete_brand(brand_id)


@router.post("/{brand_id}/apply")
def apply_brand(brand_id: str, payload: ApplyPayload) -> dict:
    """Applique le pack au projet soumis et renvoie le projet patche + avertissements."""
    _check_id(brand_id)
    return brands_mod.apply_to_project(brand_id, payload.project)


@router.post("/capture")
def capture_brand(payload: CapturePayload) -> dict:
    """Construit un pack depuis un projet version 2 et l'enregistre dans brands/."""
    return brands_mod.capture_from_project(payload.project, payload.label, payload.notes)
