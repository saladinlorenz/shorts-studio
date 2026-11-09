"""Protections du serveur local.

- verification de l'origine sur les requêtes de modification ;
- aucun accès arbitraire au systeme de fichiers depuis une requête :
  tous les chemins sont bornes aux dossiers autorises du projet.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import HTTPException, Request

# Dossier racine du projet applicatif (la ou se trouve server/).
ROOT = Path(__file__).resolve().parents[1]

# Dossiers autorisés pour les donnees du serveur (aucun autre chemin).
PROJECTS_DIR = ROOT / "projects"
MODELS_DIR = ROOT / "models"
MEDIA_DIR = ROOT / "media"
EXPORTS_DIR = ROOT / "exports"
DOWNLOADS_DIR = ROOT / "downloads"
CLIPS_DIR = ROOT / "clips"
PODCAST_DIR = ROOT / "podcast_db"
# paquet de connaissances (Agent Skills) lu par l'agent de l'app, en lecture seule
SKILLS_DIR = ROOT / "skills" / "remotion"
# dossiers de la production par lots : file SQLite, plan, manifestes,
# et registre des dossiers de médias connectés par l'utilisateur
BATCH_DIR = ROOT / "batch"
# paquets de livraison assembles apres un lot (videos + .srt + miniatures +
# manifeste) : sous-dossier de BATCH_DIR, donc deja couvert par ALLOWED_DIRS
DELIVERIES_DIR = BATCH_DIR / "deliveries"
# packs de marque client (logo, palette, police, signature, musique, modeles
# autorises) : un JSON par client, meme motif de persistance que models/
BRANDS_DIR = ROOT / "brands"
# analyses de moments forts (transcription + detection + extraits) : un JSON par
# source, plus un dossier de travail effacable ; les projets generes partent dans
# projects/ et les extraits audio dans media/, comme toute autre importation
MOMENTS_DIR = ROOT / "moments"
# index de recherche lexicale des connaissances (SQLite FTS5) construit par
# l'agent à partir des fichiers déjà autorisés ; régénérable, aucun document
# utilisateur n'y est ajouté
KNOWLEDGE_DIR = ROOT / "knowledge"
# poids des moteurs de synthese vocale (Piper / Kokoro) telecharges a la demande :
# un dossier borne, comme models/, mais pour les fichiers .onnx/.bin (pas les
# templates JSON de video). Rien n'est telecharge sans un clic utilisateur.
TTS_MODELS_DIR = ROOT / "tts_models"

ALLOWED_DIRS = (
    PROJECTS_DIR,
    MODELS_DIR,
    MEDIA_DIR,
    EXPORTS_DIR,
    DOWNLOADS_DIR,
    CLIPS_DIR,
    PODCAST_DIR,
    SKILLS_DIR,
    BATCH_DIR,
    BRANDS_DIR,
    MOMENTS_DIR,
    KNOWLEDGE_DIR,
    TTS_MODELS_DIR,
)

# Origines attendues : le frontend servi par ce meme serveur.
DEFAULT_ORIGINS = frozenset(
    {
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }
)

# Noms d'hote consideres comme locaux : un rebinding DNS presente le nom de
# l'attaquant, jamais l'une de ces adresses.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def ensure_dirs() -> None:
    """Cree les dossiers de donnees du serveur s'ils n'existent pas."""
    for d in ALLOWED_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def assert_local_dir(path: Path) -> Path:
    """Verifie qu'un chemin est bien dans un dossier autorise (aucun traversal)."""
    resolved = path.resolve()
    for allowed in ALLOWED_DIRS:
        try:
            resolved.relative_to(allowed.resolve())
            return resolved
        except ValueError:
            continue
    raise HTTPException(
        status_code=400,
        detail="Chemin hors des emplacements autorises.",
    )


def safe_name(name: str) -> str:
    """Ramene un nom de fichier a un nom simple sans chemin ni caracteres dangereux."""
    cleaned = Path(str(name)).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")
    for ch in '<>:"/\\|?*':
        cleaned = cleaned.replace(ch, "_")
    return cleaned[:120]


def _loopback_for(host: str) -> bool:
    """Vrai si l'hote est une adresse locale (127.x, ::1, localhost)."""
    if host in LOCAL_HOSTS:
        return True
    parts = host.split(".")
    return len(parts) == 4 and parts[0] == "127" and all(p.isdigit() for p in parts)


def check_origin(request: Request) -> None:
    """Refuse les requêtes de modification (POST/PUT/DELETE/PATCH) dont
    l'origine ne correspond pas a ce serveur local.

    Les requêtes sans Origine (curl, memes origines, navigateur local)
    sont acceptees ; une origine presente mais differente est refusee
    (protection CSRF de base).

    L'origine du serveur lui-meme est construite a partir de l'hote et du port
    rejoints (le port vient de settings.json, il change selon la machine) ; elle
    n'est admise que si cet hote est local, ce qui bloque une origine distante
    qui se ferait passer pour le serveur.
    """
    if request.method not in {"POST", "PUT", "DELETE", "PATCH"}:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    origins = {o.rstrip("/") for o in DEFAULT_ORIGINS}
    if _loopback_for(request.url.hostname or ""):
        origins.add(str(request.base_url).rstrip("/"))
    if origin.rstrip("/") in origins:
        return
    raise HTTPException(status_code=403, detail="Origine non autorisee.")


def csrf_token() -> str:
    """Jeton simple (memoire uniquement) si un jour besoin d'auth locale."""
    return secrets.token_urlsafe(24)
