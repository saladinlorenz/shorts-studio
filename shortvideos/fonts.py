"""Catalogue des polices utilisables par le studio.

Source unique : ``web/src/remotion/fontCatalog.json``. Le serveur valide les
polices demandees contre ce catalogue ; le frontend l'utilise pour declarer
les @font-face. Les fichiers .ttf sont servis depuis ``web/public/fonts/``
sous le meme chemin relatif pour le Player et pour le navigateur de rendu.

Aucune police systeme Windows n'est proposee : la redistribution et
l'embarquement dans un rendu exigent une licence qui les autorise (OFL).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "web" / "src" / "remotion" / "fontCatalog.json"
FONTS_DIR = ROOT / "web" / "public" / "fonts"
FONT_URL_BASE = "/fonts/"


def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        raise RuntimeError(f"Catalogue de polices introuvable : {CATALOG_PATH}")
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def families() -> list[dict]:
    """Liste des familles, avec l'URL de service de chaque poids."""
    out = []
    for fam in load_catalog().get("families", []):
        weights = [
            {
                "weight": w["weight"],
                "style": w.get("style", "normal"),
                "file": w["file"],
                "url": FONT_URL_BASE + w["file"],
                "available": (FONTS_DIR / w["file"]).is_file(),
            }
            for w in fam.get("weights", [])
        ]
        out.append(
            {
                "id": fam["id"],
                "css_family": fam["css_family"],
                "label": fam.get("label", fam["css_family"]),
                "role": fam.get("role", "sans"),
                "license": fam.get("license", ""),
                "source": fam.get("source", ""),
                "retrieved": fam.get("retrieved", ""),
                "weights": weights,
                "complete": all(w["available"] for w in weights) if weights else False,
            }
        )
    return out


def family_ids() -> set[str]:
    return {f["id"] for f in load_catalog().get("families", [])}


def known_family(family_id: str) -> bool:
    return family_id in family_ids()


def weights_of(family_id: str) -> list[int]:
    for fam in load_catalog().get("families", []):
        if fam["id"] == family_id:
            return [int(w["weight"]) for w in fam.get("weights", [])]
    return []


def missing_files() -> list[str]:
    out = []
    for fam in load_catalog().get("families", []):
        for w in fam.get("weights", []):
            if not (FONTS_DIR / w["file"]).is_file():
                out.append(w["file"])
    return out
