"""Bibliotheque de modeles : presets que l'utilisateur ajoute lui-meme.

Un modele est un projet version 2 complet, pose dans ``models/<id>.json``.
Il est rendu par la composition Remotion declaree dans ``model.id`` : ajouter
un modele ne demande donc aucun code — soit l'enregistrement depuis l'editeur,
soit un fichier JSON ecrit a la main dans ce dossier (il suffit alors d'ouvrir
la page Bibliotheque pour le voir apparaitre).

Le fichier porte deux champs de presentation supplementaires, ``label`` et
``description`` ; la validation du projet les ignore. Les modeles integrates
restent generes par ``shortvideos/schema.py`` et ne sont pas supprimables.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from shortvideos import schema
from shortvideos.schema import SCHEMA_VERSION_V2

from . import media as media_mod
from .security import MODELS_DIR, assert_local_dir, safe_name

# Modeles livrés avec le studio : générés par le code, jamais supprimés.
BUILTIN_MODELS: dict[str, dict] = {
    "citation-cinematique": {
        "label": "Citation cinématique",
        "description": (
            "Trois scènes : accroche révélée par masque, citation animée mot à mot "
            "avec mots mis en valeur, signature de marque."
        ),
        "model_id": "quote_cinematic",
    },
}


def _model_path(model_id: str) -> Path:
    filename = safe_name(model_id)
    if not filename.lower().endswith(".json"):
        filename += ".json"
    return assert_local_dir(MODELS_DIR / filename)


def slugify(label: str) -> str:
    """Identifiant de fichier stable à partir d'un libellé (sans accents ni espaces)."""
    cleaned = (
        str(label)
        .strip()
        .lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("ë", "e")
        .replace("à", "a")
        .replace("â", "a")
        .replace("ä", "a")
        .replace("ù", "u")
        .replace("û", "u")
        .replace("ï", "i")
        .replace("î", "i")
        .replace("ô", "o")
        .replace("ö", "o")
        .replace("ç", "c")
        .replace("œ", "oe")
    )
    out = "".join(ch if ch.isalnum() else "-" for ch in cleaned).strip("-")
    out = "-".join(part for part in out.split("-") if part)
    return out[:60] or "modele"


def _summary(model_id: str, project: dict, *, builtin: bool, path: Path | None) -> dict:
    export = project.get("export", {})
    scenes = project.get("content", {}).get("scenes", [])
    model = project.get("model", {})
    media_refs = [
        layer.get("media")
        for scene in scenes
        for layer in scene.get("layers", [])
        if isinstance(layer, dict) and layer.get("media")
    ]
    background = [sc.get("background", {}).get("media") for sc in scenes if sc.get("background", {}).get("media")]
    signature = project.get("content", {}).get("signature", {})
    if signature.get("media"):
        media_refs.append(signature["media"])
    modified = path.stat().st_mtime if path else 0.0
    return {
        "id": model_id,
        "builtin": builtin,
        "label": project.get("label") or BUILTIN_MODELS.get(model_id, {}).get("label", model_id),
        "description": project.get("description") or BUILTIN_MODELS.get(model_id, {}).get("description", ""),
        "model_id": model.get("id") if isinstance(model, dict) else model,
        "model_version": model.get("version") if isinstance(model, dict) else None,
        "version": project.get("version"),
        "scenes": len(scenes),
        "duration": round(schema.total_duration(project), 2),
        "width": export.get("width"),
        "height": export.get("height"),
        "fps": export.get("fps"),
        "media_count": len(set(media_refs + background)),
        "modified": modified,
        "file": path.name if path else None,
    }


def list_library() -> list[dict]:
    items = []
    for model_id, info in BUILTIN_MODELS.items():
        project = builtin_project(model_id)
        items.append(_summary(model_id, project, builtin=True, path=None))
    for path in sorted(MODELS_DIR.glob("*.json")):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            items.append(
                {
                    "id": path.stem,
                    "builtin": False,
                    "label": path.stem,
                    "description": "",
                    "model_id": None,
                    "model_version": None,
                    "version": None,
                    "scenes": 0,
                    "duration": 0,
                    "width": None,
                    "height": None,
                    "fps": None,
                    "media_count": 0,
                    "modified": path.stat().st_mtime,
                    "file": path.name,
                    "unreadable": True,
                }
            )
            continue
        if not isinstance(project, dict) or project.get("version") != SCHEMA_VERSION_V2:
            continue  # pas un modele du studio : ignore, jamais écrasé
        items.append(_summary(path.stem, project, builtin=False, path=path))
    return items


def builtin_project(model_id: str) -> dict:
    info = BUILTIN_MODELS.get(model_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Modèle intégré inconnu : {model_id}")
    project = schema.new_project(info["model_id"])
    project["label"] = info["label"]
    project["description"] = info["description"]
    return project


def get_project(model_id: str) -> dict:
    """Projet du modèle, prêt à devenir un projet de travail."""
    if model_id in BUILTIN_MODELS:
        return builtin_project(model_id)
    path = _model_path(model_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Modèle introuvable : {model_id}")
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Modèle illisible : {e}")
    if not isinstance(project, dict) or project.get("version") != SCHEMA_VERSION_V2:
        raise HTTPException(
            status_code=400,
            detail=f"Le modèle {model_id!r} n'est pas un projet version 2.",
        )
    return project


def save_model(project: dict, label: str, description: str, model_id: str | None = None) -> dict:
    """Enregistre (ou remplace) un modèle de la bibliothèque.

    Un modèle est un projet v2 : la meme validation que l'export s'applique,
    donc un modele casse ne peut pas etre ajoute a la bibliotheque.
    """
    if not isinstance(project, dict) or project.get("version") != SCHEMA_VERSION_V2:
        raise HTTPException(
            status_code=400,
            detail="Seuls les projets version 2 peuvent être enregistrés comme modèle.",
        )
    errors, warnings = media_mod.validate_project_refs(project)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Modèle invalide : corrigez les erreurs avant l'enregistrement.", "errors": errors},
        )
    clean_label = str(label or "").strip()
    if not clean_label:
        raise HTTPException(status_code=400, detail="Un modèle de la bibliothèque doit avoir un nom.")
    target = slugify(model_id or clean_label)
    if target in BUILTIN_MODELS:
        raise HTTPException(status_code=400, detail=f"{target} est un modèle intégré : choisissez un autre nom.")
    stored = dict(project)
    stored["label"] = clean_label[:80]
    stored["description"] = str(description or "").strip()[:400]
    path = _model_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"model": _summary(target, stored, builtin=False, path=path), "warnings": warnings}


def delete_model(model_id: str) -> dict:
    if model_id in BUILTIN_MODELS:
        raise HTTPException(status_code=400, detail="Un modèle intégré ne peut pas être supprimé.")
    path = _model_path(model_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Modèle introuvable : {model_id}")
    path.unlink()
    return {"deleted": path.stem}
