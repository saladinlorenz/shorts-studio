"""Génération d'images via Pollinations, API publique SANS clé.

Le descriptif (prompt texte) est envoyé à un service tiers ; l'image revient en
local et devient un média normal (``media://<id>``), assignable à un fond de
scène ou un calque image par les opérations déjà validées. Aucune écriture dans
un projet ici : l'affectation reste une proposition séparée.

Bornes : hôte whitelisté + HTTPS, pas de redirection ni de proxy d'environnement,
plafond d'octets, vérification JPEG (type MIME + octets magiques), annulation
entre chunks, écriture atomique. ``httpx`` est déjà utilisé par le client LLM :
aucune dépendance nouvelle.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx

from . import media

_HOST = "image.pollinations.ai"
_BASE = f"https://{_HOST}/prompt/"
_MAX_BYTES = 12 * 1024 * 1024
_TIMEOUT = 60.0
_JPEG_MAGIC = b"\xff\xd8\xff"


class ImageGenError(RuntimeError):
    pass


def _url(prompt: str, width: int, height: int, seed: int | None) -> str:
    url = f"{_BASE}{quote(prompt, safe='')}?width={width}&height={height}&nologo=true"
    if seed is not None:
        url += f"&seed={seed}"
    return url


def _download(url: str, dest: Path, *, cancel=None) -> None:
    part = dest.with_name(dest.name + ".part")
    try:
        with httpx.Client(timeout=httpx.Timeout(_TIMEOUT, connect=15.0),
                          trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", url, headers={"User-Agent": "youtube_clipper-local"}) as resp:
                if resp.status_code != 200:
                    raise ImageGenError(f"Le service d'images a répondu {resp.status_code}.")
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if ctype != "image/jpeg":
                    raise ImageGenError(f"Réponse inattendue du service d'images ({ctype or 'type inconnu'}).")
                done = 0
                first = True
                with part.open("wb") as out:
                    for chunk in resp.iter_bytes(256 * 1024):
                        if cancel is not None:
                            cancel()
                        if not chunk:
                            continue
                        if first:
                            if not chunk.startswith(_JPEG_MAGIC):
                                raise ImageGenError("Le fichier reçu n'est pas un JPEG.")
                            first = False
                        done += len(chunk)
                        if done > _MAX_BYTES:
                            raise ImageGenError("Image trop volumineuse : téléchargement interrompu.")
                        out.write(chunk)
        if not part.is_file() or part.stat().st_size == 0:
            raise ImageGenError("Téléchargement d'image vide.")
        part.replace(dest)
    except httpx.TimeoutException as e:
        raise ImageGenError("Délai dépassé en générant l'image.") from e
    except httpx.HTTPError as e:
        raise ImageGenError(f"Service d'images injoignable : {e}") from e
    finally:
        part.unlink(missing_ok=True)


def generate_image(prompt: str, *, width: int = 1024, height: int = 1024,
                   seed: int | None = None, cancel=None) -> dict:
    """Génère une image et l'importe comme média local. Retourne sa référence.

    L'annulation (``cancel()`` lève JobCancelled) interrompt le téléchargement ;
    le fichier provisoire et le dossier temporaire sont toujours nettoyés.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageGenError("Descriptif d'image vide.")
    url = _url(prompt, width, height, seed)
    with tempfile.TemporaryDirectory(prefix="imagegen-") as directory:
        tmp = Path(directory) / f"{uuid.uuid4().hex[:12]}.jpg"
        _download(url, tmp, cancel=cancel)
        media_id = media.import_file_to_media(
            tmp,
            source="Génération d'image Pollinations (sans clé)",
            licence="Image générée par IA via Pollinations (service tiers)",
        )
    return {
        "media_id": media_id,
        "ref": f"media://{media_id}",
        "url": f"/api/media/{media_id}",
        "width": width,
        "height": height,
        "summary": "Image générée et importée comme média local.",
    }