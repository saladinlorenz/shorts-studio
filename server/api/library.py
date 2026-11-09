"""Routes de la bibliotheque de modeles.

La bibliotheque est un dossier de fichiers JSON (``models/``) : l'utilisateur
peut y deposer ou y retirer des modeles lui-meme, sans toucher au code. Ces
routes ne font que naire, valider et borner les chemins.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import library as library_mod
from ..security import MODELS_DIR

router = APIRouter(prefix="/api/library", tags=["library"])


class ModelPayload(BaseModel):
    project: dict
    label: str = ""
    description: str = ""
    model_id: str | None = None


@router.get("")
def list_models() -> dict:
    return {
        "models": library_mod.list_library(),
        "folder": MODELS_DIR.name,
        "folder_path": str(MODELS_DIR),
    }


@router.get("/{model_id}")
def get_model(model_id: str) -> dict:
    return {"id": model_id, "project": library_mod.get_project(model_id)}


@router.post("")
def save_model(payload: ModelPayload) -> dict:
    return library_mod.save_model(
        payload.project, payload.label, payload.description, payload.model_id
    )


@router.delete("/{model_id}")
def delete_model(model_id: str) -> dict:
    if not model_id or any(ch in model_id for ch in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de modèle invalide.")
    return library_mod.delete_model(model_id)
