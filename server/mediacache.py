"""Cache local des medias pour le rendu.

Probleme : le Player est servi par FastAPI (127.0.0.1:8000) alors que le
navigateur de rendu Remotion sert le dossier ``web/public`` a la racine de son
propre serveur interne. Les deux comprennent neanmoins le MEME chemin relatif
``/media-cache/<id>.<ext>`` :

- Player : ``web/dist`` est servi par l'app FastAPI (route statique) et Vite
  sert ``public/`` en developpement ;
- rendu : Remotion sert ``web/public`` a la racine.

Un media est donc copie une seule fois dans le cache, jamais re-embarque en
data-URI dans chaque fichier de props, et aucun chemin Windows n'apparait
dans une URL. Le projet enregistre conserve les references ``media://<id>``.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .security import EXPORTS_DIR, MEDIA_DIR, ROOT, safe_name

WEB_DIR = ROOT / "web"
CACHE_DIRS = (WEB_DIR / "public" / "media-cache", WEB_DIR / "dist" / "media-cache")

MEDIA_REF = re.compile(r"^media://([0-9a-zA-Z_-]{4,64})$")

# Champs de projet qui portent une reference media (v1 et v2).
_MEDIA_KEYS = ("media", "background_image", "logo", "music", "voice")


def media_file(media_id: str) -> Path | None:
    candidates = sorted(MEDIA_DIR.glob(f"{media_id}.*"))
    return candidates[0] if candidates else None


def ensure_cached(media_id: str) -> str | None:
    """Copie le media dans les dossiers de cache et retourne son URL locale."""
    src = media_file(media_id)
    if src is None:
        return None
    name = f"{media_id}{src.suffix.lower()}"
    size = src.stat().st_size
    for cache_dir in CACHE_DIRS:
        cache_dir.mkdir(parents=True, exist_ok=True)
        dest = cache_dir / name
        if dest.exists() and dest.stat().st_size == size:
            continue
        shutil.copyfile(src, dest)
    return f"/media-cache/{name}"


def clear_cache() -> int:
    removed = 0
    for cache_dir in CACHE_DIRS:
        if not cache_dir.is_dir():
            continue
        for f in cache_dir.glob("*"):
            if f.is_file():
                f.unlink()
                removed += 1
    return removed


def _ref_to_url(value: str) -> str:
    match = MEDIA_REF.match(value.strip())
    if not match:
        return value  # reference heritee ou vide : laissée, la validation la signale
    url = ensure_cached(match.group(1))
    return url if url else value


def _walk(node):
    if isinstance(node, dict):
        return {
            key: (_ref_to_url(value) if key in _MEDIA_KEYS and isinstance(value, str) else _walk(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_walk(item) for item in node]
    return node


def to_render_urls(project: dict) -> dict:
    """Copie du projet avec des URLs de rendu resolvables par le Player et
    par le navigateur de rendu (meme chaine pour les deux)."""
    return _walk(json.loads(json.dumps(project)))


def write_props(resolved: dict, job_id: str) -> Path:
    """Ecrit le fichier de props du rendu dans le dossier borne des exports."""
    props_path = EXPORTS_DIR / f"props-{job_id}.json"
    props_path.write_text(
        json.dumps({"project": resolved}, ensure_ascii=False), encoding="utf-8"
    )
    return props_path


def output_path(name: str) -> Path:
    """Chemin de sortie borne a EXPORTS_DIR, nom assaini, extension .mp4."""
    out_name = safe_name(name)
    if not out_name.lower().endswith(".mp4"):
        out_name += ".mp4"
    return EXPORTS_DIR / out_name
