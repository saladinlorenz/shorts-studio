"""Dossiers de médias connectés pour la production par lots.

L'utilisateur peut connecter un dossier de vidéos de fond ou un dossier de
musiques de fond. Deux règles commandent l'implémentation :

1. **Aucun accès libre au disque.** Un dossier n'est lisible que s'il a été
   enregistré explicitement dans ``batch/folders.json``. Les chemins demandés
   sont vérifiés sous une racine enregistrée, jamais ailleurs ; les
   enregistrements refusent une racine de lecteur (``C:\\``).
2. **Les fichiers du dossier ne vont jamais dans un projet.** Ils sont importés
   dans ``media/<uuid>.<ext>`` par le même chemin que l'upload : le projet ne
   porte que ``media://<id>``, et le rendu passe par ``/media-cache/``.

L'empreinte sha256 est calculée à l'import : un même fichier re-scanne n'est
jamais copié deux fois, même s'il apparaît dans deux dossiers connectés.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from .media import PROVENANCE_DIR, import_file_to_media
from .security import BATCH_DIR, MEDIA_DIR, safe_name

FOLDERS_FILE = BATCH_DIR / "folders.json"

# Extensions retenues lors d'un scan, par nature de ressource.
EXTENSIONS: dict[str, set[str]] = {
    "video": {".mp4", ".mov", ".webm", ".mkv"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"},
}
KINDS = ("video", "audio", "image")

MAX_FILES_PER_FOLDER = 500
MAX_DEPTH = 3
MAX_BYTES = 500 * 1024 * 1024  # même plafond que l'upload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_roots() -> list[dict]:
    if not FOLDERS_FILE.exists():
        return []
    try:
        data = json.loads(FOLDERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_roots(roots: list[dict]) -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FOLDERS_FILE.with_suffix(".json.part")
    tmp.write_text(json.dumps(roots, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(FOLDERS_FILE)


def _find(roots: list[dict], root_id: str) -> dict:
    for root in roots:
        if root.get("id") == root_id:
            return root
    raise HTTPException(status_code=404, detail="Dossier introuvable.")


def get_root(root_id: str) -> dict:
    if not root_id or any(ch in root_id for ch in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de dossier invalide.")
    return _find(load_roots(), root_id)


def _as_directory(path: str) -> Path:
    """Chemin absolu d'un dossier existant ; refuse une racine de lecteur."""
    raw = (path or "").strip().strip('"')
    if not raw:
        raise HTTPException(status_code=400, detail="Chemin de dossier requis.")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Chemin absolu requis.")
    try:
        resolved = candidate.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Dossier illisible : {e}") from e
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Dossier introuvable : {resolved}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Le chemin indiqué n'est pas un dossier.")
    if len(resolved.parts) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Racine de lecteur refusée : choisissez un dossier précis.",
        )
    return resolved


def register(path: str, kind: str = "any", name: str = "", licence: str = "") -> dict:
    """Enregistre un dossier comme source de médias autorisée."""
    kind = (kind or "any").strip().lower()
    if kind not in (*KINDS, "any"):
        raise HTTPException(status_code=400, detail=f"Type de dossier inconnu : {kind}")
    resolved = _as_directory(path)

    roots = load_roots()
    for root in roots:
        if Path(root["path"]).resolve() == resolved:
            return dict(root)

    root = {
        "id": uuid.uuid4().hex[:12],
        "path": str(resolved),
        "name": safe_name(name or resolved.name or "dossier"),
        "kind": kind,
        "licence": (licence or "").strip() or "inconnue",
        "added_at": _now(),
        "last_scan": None,
        "files": [],
    }
    roots.append(root)
    save_roots(roots)
    return root


def unregister(root_id: str) -> dict:
    roots = load_roots()
    root = _find(roots, root_id)
    # Les médias déjà importés restent dans media/ : déconnecter un dossier ne
    # supprime aucune vidéo utilisée par un projet.
    save_roots([r for r in roots if r.get("id") != root_id])
    return root


def list_roots() -> list[dict]:
    out = []
    for root in load_roots():
        entry = dict(root)
        entry["present"] = Path(root["path"]).is_dir()
        entry["imported"] = len(root.get("files") or [])
        out.append(entry)
    return out


def _kind_of(path: Path) -> str | None:
    ext = path.suffix.lower()
    for kind, extensions in EXTENSIONS.items():
        if ext in extensions:
            return kind
    return None


def _walk(root: Path) -> list[Path]:
    """Fichiers médias du dossier, ordre déterministe, profondeur bornée."""
    found: list[Path] = []
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if len(current.parts) - root_depth >= MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not d.startswith("~$")]
        for filename in filenames:
            if filename.startswith("."):
                continue
            file_path = current / filename
            if _kind_of(file_path) is None:
                continue
            found.append(file_path)
            if len(found) >= MAX_FILES_PER_FOLDER:
                return sorted(found, key=lambda p: p.as_posix().lower())
    return sorted(found, key=lambda p: p.as_posix().lower())


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def known_digests() -> dict[str, str]:
    """Empreinte -> identifiant média, à partir des provenances enregistrées."""
    index: dict[str, str] = {}
    if not PROVENANCE_DIR.is_dir():
        return index
    for file_path in PROVENANCE_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        digest = data.get("content_hash")
        media_id = data.get("id")
        if digest and media_id and (MEDIA_DIR / f"{media_id}{Path(str(data.get('filename', ''))).suffix}").exists():
            index[str(digest)] = str(media_id)
    return index


def scan(root_id: str, should_cancel=None, on_progress=None) -> dict:
    """Important dans media/ chaque fichier du dossier connecté.

    ``should_cancel`` : callback optionnel, interrogé entre deux fichiers ;
    l'interrompre laisse en mémoire les médias déjà importés.
    ``on_progress`` : callback ``f(current, total)`` pour la barre de suivi.
    """
    roots = load_roots()
    root = _find(roots, root_id)
    source_dir = _as_directory(root["path"])

    wanted = root["kind"]
    files = [f for f in _walk(source_dir) if wanted == "any" or _kind_of(f) == wanted]
    index = known_digests()

    imported: list[dict] = []
    skipped: list[dict] = []
    new_count = 0
    interrupted = False
    for position, file_path in enumerate(files, start=1):
        if should_cancel is not None and should_cancel():
            interrupted = True
            break
        if on_progress is not None:
            on_progress(position, len(files))
        try:
            size = file_path.stat().st_size
        except OSError:
            skipped.append({"name": file_path.name, "reason": "fichier illisible"})
            continue
        rel = file_path.relative_to(source_dir).as_posix()
        if size == 0:
            skipped.append({"name": rel, "reason": "fichier vide"})
            continue
        if size > MAX_BYTES:
            skipped.append({"name": rel, "reason": f"fichier trop volumineux ({size} octets, max {MAX_BYTES})"})
            continue
        try:
            digest = _digest(file_path)
        except OSError:
            skipped.append({"name": rel, "reason": "lecture impossible"})
            continue

        media_id = index.get(digest)
        already = media_id is not None
        if not already:
            try:
                media_id = import_file_to_media(
                    file_path,
                    source=f"dossier « {root['name']} » · {rel}",
                    licence=root.get("licence", "inconnue"),
                    digest=digest,
                )
            except HTTPException as e:
                skipped.append({"name": rel, "reason": str(e.detail)})
                continue
            index[digest] = media_id
            new_count += 1
        imported.append(
            {
                "rel": rel,
                "name": file_path.name,
                "kind": _kind_of(file_path) or "file",
                "size": size,
                "media_id": media_id,
                "ref": f"media://{media_id}",
                "content_hash": digest,
                "already_present": already,
                "licence": root.get("licence", "inconnue"),
            }
        )

    root["files"] = imported
    root["path"] = str(source_dir)
    root["last_scan"] = {
        "at": _now(),
        "found": len(files),
        "imported": len(imported),
        "new": new_count,
        "existing": len(imported) - new_count,
        "skipped": len(skipped),
        "interrupted": interrupted,
    }
    save_roots(roots)
    return {"root": root, "imported": imported, "skipped": skipped, "summary": root["last_scan"]}


def assets_by_kind(kind: str) -> list[dict]:
    """Médias importés depuis les dossiers connectés, pour un type de ressource.

    Les fichiers d'un dossier enregistré comme « any » sont triés par nature,
    afin qu'un même dossier fournisse à la fois les fonds et les musiques.
    """
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"Type de ressource inconnu : {kind}")
    out: list[dict] = []
    for root in load_roots():
        for entry in root.get("files") or []:
            if entry.get("kind") != kind:
                continue
            if not list(MEDIA_DIR.glob(f"{entry['media_id']}.*")):
                continue
            item = dict(entry)
            item["folder"] = root["name"]
            item["folder_id"] = root["id"]
            out.append(item)
    return out
