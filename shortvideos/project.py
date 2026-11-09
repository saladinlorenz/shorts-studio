"""Modele de projet JSON pour l'onglet Short Videos.

Format documente dans shortvideos/PROJECT_FORMAT.md.

Un projet est un dictionnaire JSON simple avec un champ obligatoire
``version`` (schema version). La sauvegarde/chargement est fait ici,
sans dependance a Tkinter ni a la composition.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

SCHEMA_VERSION = 1
SUPPORTED_VERSIONS = (1, 2)

SUPPORTED_TEMPLATES = ("quote_vertical",)
TEXT_EFFECTS = ("fade", "slide")
BACKGROUND_EFFECTS = ("static", "zoom_slow")


def default_project() -> dict:
    """Projet par defaut : une citation cinematique verticale 1080x1920."""
    return {
        "version": SCHEMA_VERSION,
        "template": "quote_vertical",
        "content": {
            "text": "Le courage est le premier des vertus.",
            "author": "",
            "background_image": "",
            "logo": "",
        },
        "theme": {
            "font_family": "arialbd.ttf",
            "font_size": 72,
            "text_color": "#FFFFFF",
            "author_color": "#F2C14E",
            "accent_color": "#F2C14E",
            "shadow": True,
        },
        "position": {
            "x": 0.5,
            "y": 0.45,
            "width": 0.85,
        },
        "timing": {
            "duration": 8.0,
            "text_start": 0.5,
            "fade_in": 0.8,
            "fade_out": 0.8,
        },
        "animation": {
            "text_in": "fade",
            "background": "zoom_slow",
        },
        "export": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "output_dir": "",
        },
    }


def snapshot(project: dict) -> dict:
    """Copie figee (deep copy) d'un projet, pour figer les reglages a l'export."""
    return copy.deepcopy(project)


def load_project(path: str | Path) -> dict:
    """Charge un projet JSON. Leve une RuntimeError avec un message clair."""
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"Fichier de projet introuvable : {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise RuntimeError(f"Impossible de lire le projet {p} : {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"JSON invalide dans {p} (ligne {e.lineno}, colonne {e.colno}) : {e.msg}"
        ) from e
    if not isinstance(data, dict):
        raise RuntimeError(f"Projet invalide dans {p} : le contenu n'est pas un objet JSON.")
    version = data.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise RuntimeError(
            f"Version de projet non prise en charge : {version!r} "
            f"(versions acceptees : {', '.join(str(v) for v in SUPPORTED_VERSIONS)})."
        )
    return data


def save_project(project: dict, path: str | Path) -> Path:
    """Enregistre le projet en JSON (UTF-8). Le chemin peut contenir des espaces."""
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    data = snapshot(project)
    version = data.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise RuntimeError(
            f"Version de projet non prise en charge a l'enregistrement : {version!r} "
            f"(versions acceptees : {', '.join(str(v) for v in SUPPORTED_VERSIONS)})."
        )
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
