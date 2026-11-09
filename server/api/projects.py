"""Routes des projets Short Videos (JSON versionné).

Le format et la validation restent portés par ``shortvideos/project.py``
et ``shortvideos/validation.py`` : le serveur ne fait que de l'IO bornée.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shortvideos import project as project_mod

from .. import media as media_mod

from ..security import PROJECTS_DIR, assert_local_dir, safe_name

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectPayload(BaseModel):
    name: str
    project: dict


def _project_path(name: str) -> Path:
    filename = safe_name(name)
    if not filename.endswith(".json"):
        filename += ".json"
    return assert_local_dir(PROJECTS_DIR / filename)


@router.get("")
def list_projects() -> list[dict]:
    items = []
    for path in sorted(PROJECTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            version = data.get("version")
        except (OSError, json.JSONDecodeError):
            version = None
        items.append(
            {
                "name": path.stem,
                "version": version,
                "size": path.stat().st_size,
                "modified": path.stat().st_mtime,
            }
        )
    return items


@router.post("")
def save_project(payload: ProjectPayload, request=None) -> dict:
    path = _project_path(payload.name)
    try:
        project_mod.save_project(payload.project, path)
    except (OSError, ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Enregistrement impossible : {e}")
    return {"name": path.stem, "path": path.name}


@router.get("/{name}")
def load_project(name: str) -> dict:
    path = _project_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Projet introuvable : {name}")
    try:
        data = project_mod.load_project(path)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data, migrated = media_mod.migrate_media_refs(data)
    errors, warnings = media_mod.validate_project_refs(data)
    return {
        "name": path.stem,
        "project": data,
        "errors": errors,
        "warnings": warnings,
        "migrated_media": migrated,
    }


@router.delete("/{name}")
def delete_project(name: str) -> dict:
    path = _project_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Projet introuvable : {name}")
    path.unlink()
    return {"deleted": path.stem}


@router.post("/validate")
def validate(payload: dict) -> dict:
    """Valide un projet sans l'enregistrer (erreurs + avertissements)."""
    project = payload.get("project") if isinstance(payload, dict) else None
    if not isinstance(project, dict):
        raise HTTPException(status_code=400, detail="Champ 'project' manquant.")
    errors, warnings = media_mod.validate_project_refs(project)
    return {"errors": errors, "warnings": warnings}
