"""Gestion des médias : import et service limité.

Règles :
- aucun chemin Windows en URL : le frontend ne voit que ``/api/media/<id>`` ;
- les fichiers sont stockés dans ``media/<uuid>.<ext>`` (dossier borné) ;
- l'upload accepte uniquement des types MIME d'images/vidéos autorisés ;
- la résolution des médias côté serveur est bornée à MEDIA_DIR.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from shortvideos.schema import SCHEMA_VERSION_V2
from shortvideos.validation import validate_project

from .security import MEDIA_DIR, ROOT, safe_name

# Champs de projet qui portent une reference media (v1 et v2).
_PROJECT_MEDIA_KEYS = ("media", "background_image", "logo", "music", "voice")
PROVENANCE_DIR = MEDIA_DIR / "provenance"

# Types acceptés pour un import de média.
ALLOWED_PREFIXES = ("image/", "video/", "audio/")
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".mp4", ".mov", ".webm", ".mkv",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
}


def _guess_extension(filename: str, content_type: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_EXTENSIONS:
        return ext
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed and guessed.lower() in ALLOWED_EXTENSIONS:
        return guessed.lower()
    raise HTTPException(
        status_code=415,
        detail=f"Type de média non autorisé : {content_type or filename}",
    )


def content_type_of(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def write_provenance(media_id: str, data: dict) -> Path:
    PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
    path = PROVENANCE_DIR / f"{media_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def import_file_to_media(path: Path, source: str, licence: str = "", digest: str = "") -> str:
    """Importe un fichier déjà présent sur le disque dans ``media/``.

    Même chemin que l'upload (copie bornée, provenance, cache de rendu) : un
    dossier connecté ne produit que des références ``media://<id>``, jamais un
    chemin Windows. Retourne l'identifiant du média.
    """
    original = safe_name(path.name)
    ext = _guess_extension(original, content_type_of(original))
    size = path.stat().st_size
    if size == 0:
        raise HTTPException(status_code=400, detail=f"Fichier vide : {original}")
    if size > 500 * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Fichier trop volumineux (max 500 Mo) : {original}")

    media_id = uuid.uuid4().hex
    dest = MEDIA_DIR / f"{media_id}{ext}"
    tmp = MEDIA_DIR / f"{media_id}{ext}.part"
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as src, tmp.open("wb") as out:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                hasher.update(chunk)
                out.write(chunk)
        tmp.replace(dest)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Import impossible : {e}") from e

    write_provenance(
        media_id,
        {
            "id": media_id,
            "filename": original,
            "content_type": content_type_of(original),
            "size": size,
            "source": (source or "").strip() or "import local",
            "licence": (licence or "").strip() or "inconnue",
            "content_hash": digest or hasher.hexdigest(),
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    from . import mediacache

    mediacache.ensure_cached(media_id)
    return media_id


async def save_upload(file: UploadFile, source: str = "", licence: str = "") -> dict:
    """Enregistre un média importé, sa provenance, et le met en cache de rendu."""
    if file.content_type and not file.content_type.startswith(ALLOWED_PREFIXES):
        raise HTTPException(
            status_code=415,
            detail=f"Type de média non autorisé : {file.content_type}",
        )
    original = safe_name(file.filename or "media")
    ext = _guess_extension(original, file.content_type or "")

    media_id = uuid.uuid4().hex
    dest = MEDIA_DIR / f"{media_id}{ext}"

    size = 0
    hasher = hashlib.sha256()
    max_bytes = 500 * 1024 * 1024  # 500 Mo par fichier
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 500 Mo).")
            hasher.update(chunk)
            out.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Fichier vide.")

    content_type = file.content_type or content_type_of(original)
    write_provenance(
        media_id,
        {
            "id": media_id,
            "filename": original,
            "content_type": content_type,
            "size": size,
            "source": (source or "").strip() or "import local",
            "licence": (licence or "").strip() or "inconnue",
            "content_hash": hasher.hexdigest(),
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    from . import mediacache

    mediacache.ensure_cached(media_id)
    return {
        "id": media_id,
        "url": f"/api/media/{media_id}",
        "render_url": f"/media-cache/{media_id}{dest.suffix.lower()}",
        "filename": original,
        "size": size,
        "content_type": content_type,
    }


def provenance_of(media_id: str) -> dict:
    """Provenance d'un media. Une licence non renseignee reste « inconnue » :
    elle n'est jamais consideree comme validee."""
    path = PROVENANCE_DIR / f"{media_id}.json"
    if not path.exists():
        return {"id": media_id, "licence": "inconnue", "declared": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"id": media_id, "licence": "inconnue", "declared": False}
    data.setdefault("licence", "inconnue")
    data["declared"] = True
    return data


def resolve_media(media_id: str) -> Path:
    """Resout un identifiant de média en chemin, strictement dans MEDIA_DIR."""
    if not media_id or any(c in media_id for c in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de média invalide.")
    matches = list(MEDIA_DIR.glob(f"{media_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Média introuvable.")
    return matches[0]


def media_path_for_project(value: str) -> str:
    """Convertit une reference de projet en chemin absolu resolvable.

    Accepte :
    - ``media://<id>``  : reference web (resolue ici, dans MEDIA_DIR) ;
    - chemin absolu v1  : conserve pour compatibilité, mais verifie
      qu'il s'agit bien d'un fichier existant (pas de traversal since
      c'est un chemin deja stocke dans le projet, pas un parametre URL).
    """
    if value.startswith("media://"):
        return str(resolve_media(value[len("media://"):]))
    return value


def resolve_project_media(project: dict) -> dict:
    """Copie profonde du projet avec les references ``media://`` resolues
    en chemins absolus (pour la validation et les traitements Python).

    Le projet d'origine n'est pas modifie. La marche est generique : elle
    couvre les projets v1 (content.background_image / logo) et les projets
    v2 (content.scenes[].background.media, calques image, signature.media).
    """
    import copy

    def walk(node):
        if isinstance(node, dict):
            return {
                key: (_abs(value) if key in _PROJECT_MEDIA_KEYS and isinstance(value, str) else walk(value))
                for key, value in node.items()
            }
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    def abs_or_empty(value: str) -> str:
        if not value.startswith("media://"):
            return value
        try:
            return media_path_for_project(value)
        except HTTPException:
            return ""  # media manquant : la validation signalera l'erreur

    def _abs(value: str) -> str:
        return abs_or_empty(value)

    return walk(project)


def validate_project_refs(project: dict) -> tuple[list[str], list[str]]:
    """Valide un projet tel qu'il est edite ou tel qu'il est servi.

    Les projets v2 portent des references ``media://`` que la validation v2
    verifie elle-meme dans le dossier ``media/`` : les remplacer d'abord par
    des chemins absolus ferait croire a un « chemin Windows interdit ». Les
    projets v1, eux, peuvent porter un chemin herite : il est resolu avant la
    validation pour controler l'existence reelle du fichier.
    """
    if isinstance(project, dict) and project.get("version") == SCHEMA_VERSION_V2:
        return validate_project(project)
    return validate_project(resolve_project_media(project))


def media_to_data_uris(project: dict) -> dict:
    """Copie du projet avec les médias convertis en ``data:`` URI (base64).

    Utilisé pour le rendu Remotion : le navigateur de rendu sert la page
    sur un port local interne, il ne peut donc pas résoudre /api/media/…
    Les data-URI suppriment toute dépendance réseau pendant le rendu.
    Le projet d'origine (refs media://) n'est pas modifié.
    """
    import base64
    import copy
    import mimetypes

    out = copy.deepcopy(project)
    content = out.get("content")
    if not isinstance(content, dict):
        return out
    for key in ("background_image", "logo"):
        value = content.get(key, "")
        if not isinstance(value, str) or not value.startswith("media://"):
            continue
        try:
            path = resolve_media(value[len("media://"):])
        except HTTPException:
            continue  # média manquant : validation l'aura signalé avant
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content[key] = f"data:{mime};base64,{encoded}"
    return out


def migrate_media_refs(project: dict) -> tuple[dict, list[str]]:
    """Recopie les medias herites (chemins Windows) vers le stockage web et
    reecrit les references en ``media://<id>``.

    Marche sur v1 (content.background_image / logo) et v2 (media des scenes,
    des calques image et de la signature). Le chemin provient du fichier de
    projet stocke, pas d'un parametre de requete : aucun acces arbitraire
    n'est ouvert. Les fichiers absents sont laisses tels quels (la validation
    les signale comme ressources manquantes).
    """
    import shutil

    migrated: list[str] = []

    def walk(node, trail=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _PROJECT_MEDIA_KEYS and isinstance(value, str) and value.strip() and not value.startswith("media://"):
                    src = Path(value)
                    if not src.is_file():
                        continue
                    ext = src.suffix.lower() or ".png"
                    media_id = uuid.uuid4().hex
                    dest = MEDIA_DIR / f"{media_id}{ext}"
                    try:
                        shutil.copy2(src, dest)
                    except OSError:
                        continue
                    write_provenance(
                        media_id,
                        {
                            "id": media_id,
                            "filename": src.name,
                            "content_type": mimetypes.guess_type(src.name)[0] or "application/octet-stream",
                            "size": dest.stat().st_size,
                            "source": f"repris du projet herite ({trail or 'content'})",
                            "licence": "inconnue",
                            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        },
                    )
                    node[key] = f"media://{media_id}"
                    migrated.append(f"{trail}{key} : {src.name}")
                elif isinstance(value, (dict, list)):
                    walk(value, trail=f"{trail}{key}." if not isinstance(value, list) else f"{trail}{key}[].")
        elif isinstance(node, list):
            for item in node:
                walk(item, trail=trail)

    walk(project)
    return project, migrated
