"""Packs de marque client : ce qui se retrouve d'une video a l'autre.

Un pack est un fichier JSON pose dans ``brands/<id>.json``. Il ne porte que des
champs qui existent deja dans le format de projet (voir ``shortvideos.branding``) :
``theme``, ``signature``, ``audio`` et la liste des ``models`` autorises. Comme la
bibliotheque de modeles, le dossier est editable a la main — deposer un JSON et
ouvrir la page Design suffit a le voir apparaitre.

Le principe « l'assistant propose, l'utilisateur applique » s'applique ici :
``apply_to_project`` ne fait que renvoyer le projet patche, il n'ecrit jamais dans
un projet de travail. C'est l'interface qui decide d'enregistrer le resultat.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from shortvideos import branding
from shortvideos.schema import SCHEMA_VERSION_V2

from .library import slugify
from .security import BRANDS_DIR, assert_local_dir, safe_name


def _brand_path(brand_id: str) -> Path:
    filename = safe_name(brand_id)
    if not filename.lower().endswith(".json"):
        filename += ".json"
    return assert_local_dir(BRANDS_DIR / filename)


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Pack illisible : {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Pack illisible : ce n'est pas un objet JSON.")
    return data


def _summary(brand_id: str, data: dict, path: Path | None) -> dict:
    pack = data.get("pack") or {}
    signature = pack.get("signature") or {}
    audio = pack.get("audio") or {}
    return {
        "id": brand_id,
        "label": pack.get("label") or brand_id,
        "notes": pack.get("notes") or "",
        "models": pack.get("models") or [],
        "has_logo": bool(signature.get("media")),
        "has_music": bool(audio.get("music")),
        "theme_keys": sorted(pack.get("theme") or {}),
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or "",
        "file": path.name if path else None,
    }


def list_brands() -> list[dict]:
    out: list[dict] = []
    for path in sorted(BRANDS_DIR.glob("*.json")):
        try:
            data = _read(path)
        except HTTPException:
            out.append({"id": path.stem, "label": path.stem, "unreadable": True, "file": path.name})
            continue
        out.append(_summary(path.stem, data, path))
    return out


def get_pack(brand_id: str) -> dict:
    path = _brand_path(brand_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Pack introuvable : {brand_id}")
    return _read(path).get("pack") or {}


def save_brand(raw: dict, brand_id: str | None = None) -> dict:
    """Normalise puis ecrit un pack ; les erreurs de ``branding.normalize`` bloquent."""
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Le pack doit etre un objet JSON.")
    pack, errors, warnings = branding.normalize(raw)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Pack invalide : corrigez les erreurs avant l'enregistrement.", "errors": errors},
        )
    target = slugify(brand_id or raw.get("id") or pack["label"])
    path = _brand_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    created = now
    if path.exists():
        created = _read(path).get("created_at") or now
    data = {"id": target, "pack": pack, "created_at": created, "updated_at": now}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"brand": _summary(target, data, path), "warnings": warnings}


def delete_brand(brand_id: str) -> dict:
    path = _brand_path(brand_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Pack introuvable : {brand_id}")
    path.unlink()
    return {"deleted": path.stem}


def apply_to_project(brand_id: str, project: dict) -> dict:
    """Renvoie le projet patche par le pack, sans jamais l'enregistrer.

    Le projet patche garde sa version et ses scenes : le pack n'ecrit que dans les
    cles ``theme`` / ``content.signature`` / ``audio``. Les avertissements remontent
    a l'interface, qui les montre avant que l'utilisateur decide de sauvegarder.
    """
    if not isinstance(project, dict) or project.get("version") != SCHEMA_VERSION_V2:
        raise HTTPException(
            status_code=400,
            detail="Seul un projet version 2 peut recevoir un pack de marque.",
        )
    pack = get_pack(brand_id)
    patched, warnings = branding.apply_brand(project, pack)
    return {"project": patched, "warnings": warnings}


def capture_from_project(project: dict, label: str, notes: str = "") -> dict:
    """Construit un pack avec ce que le projet affiche deja, puis l'enregistre.

    ``branding.from_project`` ne prend que les cles existantes (theme, signature,
    audio, modele) : aucun champ n'est invente, et le pack obtenu repasse par la
    meme normalisation qu'un pack saisi a la main.
    """
    if not isinstance(project, dict) or project.get("version") != SCHEMA_VERSION_V2:
        raise HTTPException(
            status_code=400,
            detail="Seul un projet version 2 peut servir de pack de marque.",
        )
    if not str(label or "").strip():
        raise HTTPException(status_code=400, detail="Un pack doit porter un nom de client.")
    pack = branding.from_project(project, str(label).strip(), str(notes or "").strip())
    return save_brand(pack)
