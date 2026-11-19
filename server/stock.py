"""Recherche et import de contenus depuis les banques du catalogue.

Rôle : chercher (vidéos, photos, bruitages, musiques, spatial) auprès des
fournisseurs déclarés dans ``server/sources.py``, puis importer un résultat
dans la médiathèque avec sa provenance, sa licence et une déduplication par
empreinte SHA-256.

Lois appliquées ici :

- **aucune URL choisie hors catalogue** : URL de recherche, paramètres et
  hébergeurs de téléchargement viennent des blocs « search » ; le navigateur,
  le modèle et l'utilisateur ne fournissent qu'un mot-clé, un genre et un
  fournisseur (anti-SSRF) ;
- **les clés restent serveur** : injectées dans la requête sortante, jamais
  renvoyées, jamais journalisées ;
- **HTTPS seul**, hébergeur apparié à la liste blanche **à chaque saut** de
  redirection (5 maximum) ;
- **429 : une nouvelle tentative bornée, puis repli** sur un autre
  fournisseur du même genre ; un échec devient un avertissement, pas une
  exception ;
- **licence déclarée affichée telle quelle, absente ⇒ « inconnue »** : ce
  module n'invente aucune licence ;
- **dédup sha256** : un fichier déjà importé est réutilisé, jamais réécrit ;
- **aucune suppression de fichier**, aucun ``exec``/``eval``, aucune
  installation de dépendance.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx
from fastapi import HTTPException

from . import media as media_mod
from . import sources as sources_mod

# Recherche bornée : 8 s par appel, au plus 3 fournisseurs interrogés,
# 2 tentatives sur 429 avec un court repos entre les deux.
_TIMEOUT = 8.0
_PROVIDERS_MAX = 3
_ATTEMPTS_ON_429 = 2
_RETRY_SLEEP = (0.25, 0.9)
_MAX_REDIRECTS = 5
_MAX_BYTES = 500 * 1024 * 1024  # même borne que l'upload de média
_CACHE_MAX = 400
_MAX_QUERY_CHARS = 200

KINDS = ("video", "photo", "audio", "music", "space")

# Cache des résultats : la ref retournée au client est opaque ; l'URL de
# téléchargement ne quitte jamais ce dictionnaire.
_CACHE: dict[str, dict] = {}

# Repos entre deux tentatives 429 — remplaçable en test (aucun attente réelle).
_sleep = time.sleep


class StockError(ValueError):
    """Erreur réparable : message affiché tel quel à l'utilisateur."""


# --------------------------------------------------------------------------- #
# Petits utilitaires
# --------------------------------------------------------------------------- #

def _num(value) -> float | int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cc_license(url: str) -> str:
    """Traduit une URL Creative Commons (ou domaine public) en libellé lisible."""
    if not url:
        return ""
    lowered = url.lower()
    if "publicdomain" in lowered or "mark/1.0" in lowered:
        return "Domaine public"
    parts = [p for p in urlsplit(url).path.split("/") if p]
    try:
        index = parts.index("licenses")
    except ValueError:
        return ""
    kind = parts[index + 1] if len(parts) > index + 1 else ""
    version = parts[index + 2] if len(parts) > index + 2 else ""
    if not kind:
        return ""
    label = f"CC {kind.upper()}"
    return f"{label} {version}" if version else label


def _fill(raw, text: str, limit: int):
    """Remplace {query} / {limit} dans les paramètres déclarés au catalogue."""
    if not isinstance(raw, str):
        return raw
    return raw.replace("{query}", text).replace("{limit}", str(limit))


def _client() -> httpx.Client:
    try:
        return httpx.Client(timeout=_TIMEOUT, follow_redirects=False)
    except httpx.InvalidURL:
        # NO_PROXY mal formé sur certaines machines : on retente sans
        # l'environnement, comme le fait le test de connexion des banques.
        return httpx.Client(timeout=_TIMEOUT, follow_redirects=False, trust_env=False)


def _check_url(url: str, hosts: list[str]) -> None:
    """Valide une URL contre la liste blanche d'hébergeurs du catalogue."""
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise StockError("URL refusée : HTTPS uniquement, sans identifiant ni mot de passe.")
    if parts.port not in (None, 443):
        raise StockError(f"URL refusée : le port {parts.port} n'est pas autorisé.")
    for allowed in hosts:
        allowed = str(allowed).lower()
        if host == allowed or (allowed.startswith(".") and host.endswith(allowed)):
            return
    raise StockError(f"Hébergeur refusé : {host} (hors liste blanche du catalogue).")


def _extension(url: str, content_type: str) -> str:
    """Extension autorisée du fichier : suffixe d'URL, sinon type MIME."""
    suffix = Path(urlsplit(str(url)).path).suffix.lower()
    if suffix in media_mod.ALLOWED_EXTENSIONS:
        return suffix
    ctype = str(content_type or "").split(";")[0].strip().lower()
    for candidate in (mimetypes.guess_extension(ctype),):
        if candidate and candidate.lower() in media_mod.ALLOWED_EXTENSIONS:
            return candidate.lower()
    raise HTTPException(
        status_code=415,
        detail=f"Type de média non autorisé : {ctype or suffix or 'inconnu'}",
    )


def _digest_of(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _find_by_digest(digest: str) -> str:
    """Média déjà importé portant cette empreinte, ou chaîne vide."""
    try:
        paths = sorted(media_mod.PROVENANCE_DIR.glob("*.json"))
    except OSError:
        return ""
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("content_hash") == digest and data.get("id"):
            return str(data["id"])
    return ""


# --------------------------------------------------------------------------- #
# Parseurs : une réponse d'API devient une fiche normalisée
# --------------------------------------------------------------------------- #

def _pexels_video(payload, block) -> list[dict]:
    out = []
    for video in (payload.get("videos") or []):
        files = [f for f in (video.get("video_files") or []) if isinstance(f, dict) and f.get("link")]
        if not files:
            continue
        files.sort(key=lambda f: (abs(int(f.get("height") or 0) - 1080), -int(f.get("width") or 0)))
        best = files[0]
        pictures = video.get("video_pictures") or []
        out.append({
            "id": str(video.get("id") or ""),
            "title": f"Vidéo Pexels {video.get('id') or ''}".strip(),
            "duration": _num(video.get("duration")),
            "width": _num(best.get("width")),
            "height": _num(best.get("height")),
            "author": str((video.get("user") or {}).get("name") or ""),
            "license": "Pexels License",
            "page": str(video.get("url") or ""),
            "download": str(best.get("link") or ""),
            "preview": str((pictures[0].get("picture") if pictures else "") or ""),
        })
    return out


def _pexels_photo(payload, block) -> list[dict]:
    out = []
    for photo in (payload.get("photos") or []):
        src = photo.get("src") or {}
        out.append({
            "id": str(photo.get("id") or ""),
            "title": str(photo.get("alt") or "") or f"Photo Pexels {photo.get('id') or ''}",
            "duration": None,
            "width": _num(photo.get("width")),
            "height": _num(photo.get("height")),
            "author": str(photo.get("photographer") or (photo.get("user") or {}).get("name") or ""),
            "license": "Pexels License",
            "page": str(photo.get("url") or ""),
            "download": str(src.get("original") or src.get("large2x") or src.get("large") or ""),
            "preview": str(src.get("medium") or ""),
        })
    return out


def _pixabay_photo(payload, block) -> list[dict]:
    out = []
    for hit in (payload.get("hits") or []):
        out.append({
            "id": str(hit.get("id") or ""),
            "title": str(hit.get("tags") or "") or f"Image Pixabay {hit.get('id') or ''}",
            "duration": None,
            "width": _num(hit.get("imageWidth")),
            "height": _num(hit.get("imageHeight")),
            "author": str(hit.get("user") or ""),
            "license": "Pixabay Content License",
            "page": str(hit.get("pageURL") or ""),
            "download": str(hit.get("largeImageURL") or hit.get("webformatURL") or hit.get("imageURL") or ""),
            "preview": str(hit.get("webformatURL") or hit.get("previewURL") or ""),
        })
    return out


def _pixabay_video(payload, block) -> list[dict]:
    out = []
    for hit in (payload.get("hits") or []):
        videos = hit.get("videos") or {}
        best = videos.get("large") or videos.get("medium") or videos.get("small") or {}
        out.append({
            "id": str(hit.get("id") or ""),
            "title": str(hit.get("tags") or "") or f"Vidéo Pixabay {hit.get('id') or ''}",
            "duration": _num(hit.get("duration")),
            "width": _num(best.get("width")),
            "height": _num(best.get("height")),
            "author": str(hit.get("user") or ""),
            "license": "Pixabay Content License",
            "page": str(hit.get("pageURL") or ""),
            "download": str(best.get("url") or ""),
            "preview": str(hit.get("picture") or ""),
        })
    return out


def _unsplash(payload, block) -> list[dict]:
    out = []
    for photo in (payload.get("results") or []):
        urls = photo.get("urls") or {}
        out.append({
            "id": str(photo.get("id") or ""),
            "title": str(photo.get("alt_description") or "") or f"Photo Unsplash {photo.get('id') or ''}",
            "duration": None,
            "width": _num(photo.get("width")),
            "height": _num(photo.get("height")),
            "author": str((photo.get("user") or {}).get("name") or ""),
            "license": "Unsplash License",
            "page": str((photo.get("links") or {}).get("html") or ""),
            "download": str(urls.get("raw") or urls.get("full") or urls.get("regular") or ""),
            "preview": str(urls.get("small") or ""),
        })
    return out


def _nasa(payload, block) -> list[dict]:
    collection = payload.get("collection") or {}
    out = []
    for item in (collection.get("items") or []):
        data = (item.get("data") or [{}])[0]
        links = item.get("links") or []
        href = str((links[0].get("href") if links else "") or "")
        nasa_id = str(data.get("nasa_id") or "")
        out.append({
            "id": nasa_id,
            "title": str(data.get("title") or "") or f"Image NASA {nasa_id}",
            "duration": None,
            "width": None,
            "height": None,
            "author": str(data.get("center") or ""),
            # L'API ne déclare aucune licence par item : elle reste « inconnue ».
            "license": "",
            "page": f"https://images.nasa.gov/details/{nasa_id}" if nasa_id else "",
            "download": href.replace("~thumb", "~orig") if href else "",
            "preview": href,
        })
    return out


def _freesound(payload, block) -> list[dict]:
    out = []
    for result in (payload.get("results") or []):
        previews = result.get("previews") or {}
        out.append({
            "id": str(result.get("id") or ""),
            "title": str(result.get("name") or "") or f"Son {result.get('id') or ''}",
            "duration": _num(result.get("duration")),
            "width": None,
            "height": None,
            "author": str(result.get("username") or ""),
            "license": str(result.get("license") or ""),
            "page": f"https://freesound.org/s/{result.get('id')}/" if result.get("id") else "",
            "download": str(
                previews.get("preview-hq-mp3")
                or previews.get("preview-lq-mp3")
                or previews.get("preview-hq-ogg")
                or ""
            ),
            "preview": "",
        })
    return out


def _jamendo(payload, block) -> list[dict]:
    out = []
    for track in (payload.get("results") or []):
        out.append({
            "id": str(track.get("id") or ""),
            "title": str(track.get("name") or "") or f"Piste {track.get('id') or ''}",
            "duration": _num(track.get("duration")),
            "width": None,
            "height": None,
            "author": str(track.get("artist_name") or ""),
            "license": _cc_license(str(track.get("license_ccurl") or "")),
            "page": f"https://www.jamendo.com/track/{track.get('id')}" if track.get("id") else "",
            "download": str(track.get("audiodownload") or track.get("audio") or ""),
            "preview": str(track.get("album_image") or ""),
        })
    return out


def _archive(payload, block) -> list[dict]:
    docs = ((payload.get("response") or {}).get("docs")) or []
    out = []
    for doc in docs:
        identifier = str(doc.get("identifier") or "")
        creator = doc.get("creator")
        if isinstance(creator, list):
            creator = ", ".join(str(c) for c in creator[:3])
        out.append({
            "id": identifier,
            "title": str(doc.get("title") or "") or f"Archive {identifier}",
            "duration": None,
            "width": None,
            "height": None,
            "author": str(creator or ""),
            "license": _cc_license(str(doc.get("licenseurl") or "")),
            "page": f"https://archive.org/details/{identifier}" if identifier else "",
            # Le fichier n'apparaît qu'à l'import : voir _archive_file_url.
            "download": "",
            "preview": "",
        })
    return out


_PARSERS: dict[tuple[str, str], object] = {
    ("pexels", "video"): _pexels_video,
    ("pexels", "photo"): _pexels_photo,
    ("pixabay", "photo"): _pixabay_photo,
    ("pixabay", "video"): _pixabay_video,
    ("unsplash", "photo"): _unsplash,
    ("nasa", "photo"): _nasa,
    ("nasa", "space"): _nasa,
    ("freesound", "audio"): _freesound,
    ("jamendo", "music"): _jamendo,
    ("archive", "video"): _archive,
    ("archive", "audio"): _archive,
}

# Préférences de format à l'import d'une archive (classement par genre).
_ARCHIVE_PREFS = {
    "video": (".mp4", ".ogv", ".webm", ".mkv", ".avi"),
    "audio": (".mp3", ".ogg", ".wav", ".m4a", ".flac"),
    "photo": (".jpg", ".jpeg", ".png", ".webp"),
}


# --------------------------------------------------------------------------- #
# Cache des résultats (refs opaques)
# --------------------------------------------------------------------------- #

def _cache_put(ref: str, entry: dict) -> None:
    _CACHE.pop(ref, None)
    while len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[ref] = entry


def clear_cache() -> None:
    """Vide le cache des résultats de recherche (tests et redémarrage)."""
    _CACHE.clear()


def _public(entry: dict) -> dict:
    """Fiche publique : jamais l'URL de téléchargement, jamais la clé."""
    return {
        "ref": entry["ref"],
        "provider": entry["provider"],
        "provider_id": entry["source_id"],
        "kind": entry["kind"],
        "id": entry["id"],
        "title": entry["title"],
        "duration": entry["duration"],
        "width": entry["width"],
        "height": entry["height"],
        "author": entry["author"],
        "license": entry["license"] or "inconnue",
        "page": entry["page"],
        "preview": entry["preview"],
    }


def describe_ref(ref: str) -> dict:
    """Fiche d'un résultat en cache — lève StockError si la ref a expiré."""
    entry = _CACHE.get(str(ref or ""))
    if entry is None:
        raise StockError(
            "Résultat introuvable : relancez la recherche (search_stock) avant d'importer."
        )
    return _public(entry)


# --------------------------------------------------------------------------- #
# Requête vers un fournisseur du catalogue
# --------------------------------------------------------------------------- #

def _ready(spec: dict) -> bool:
    try:
        return bool(sources_mod.state_of(spec["id"]).get("ready"))
    except sources_mod.UnknownSource:
        return False


def _candidates(kind: str, source: str) -> list[dict]:
    specs = [s for s in sources_mod.CATALOG if kind in (s.get("search") or {})]
    if source:
        match = next((s for s in specs if s["id"] == source), None)
        if match is None:
            if any(s["id"] == source for s in sources_mod.CATALOG):
                raise StockError(f"La banque {source!r} ne propose pas la recherche « {kind} ».")
            raise StockError(f"Fournisseur inconnu : {source!r}. Choisissez un fournisseur du catalogue.")
        specs.sort(key=lambda s: s["id"] != source)
    return specs


def _credentials(spec: dict, block: dict) -> tuple[dict | None, dict]:
    """Paramètres et en-têtes d'authentification — la clé ne sort jamais."""
    mode = block.get("key_mode", "none")
    if mode == "none":
        return {}, {}
    key = sources_mod.key_of(spec["id"]) or str(block.get("default_key") or "")
    if not key:
        return None, {}
    prefix = str(block.get("key_prefix") or "")
    if mode == "query":
        return {str(block["key_name"]): prefix + key}, {}
    if mode == "header":
        return {}, {str(block["key_name"]): prefix + key}
    return {}, {}


def _query(spec: dict, block: dict, text: str, kind: str, limit: int) -> dict:
    """Un appel réel vers l'API officielle. Retourne {ok, items|error}."""
    effective = limit
    if block.get("max_limit"):
        effective = min(limit, int(block["max_limit"]))
    params: dict = {}
    for key, raw in (block.get("params") or {}).items():
        if isinstance(raw, list):
            params[key] = [_fill(v, text, effective) for v in raw]
        else:
            params[key] = _fill(raw, text, effective)
    extra, headers = _credentials(spec, block)
    if extra is None:
        return {"ok": False, "error": "clé absente : enregistrez-la sur la page Banques."}
    params.update(extra)

    response = None
    for attempt in range(_ATTEMPTS_ON_429):
        try:
            with _client() as client:
                response = client.get(block["url"], params=params, headers=headers)
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"injoignable ({type(exc).__name__})."}
        except httpx.InvalidURL:
            return {"ok": False, "error": "URL du catalogue illisible sur cette machine."}
        if response.status_code == 429:
            if attempt + 1 < _ATTEMPTS_ON_429:
                _sleep(_RETRY_SLEEP[min(attempt, len(_RETRY_SLEEP) - 1)])
                continue
            return {"ok": False, "error": "quota atteint (HTTP 429) : réessayez plus tard."}
        break
    if response is None:
        return {"ok": False, "error": "appel non effectué."}
    if response.status_code in (401, 403):
        return {"ok": False, "error": f"clé refusée (HTTP {response.status_code}) : vérifiez la clé sur la page Banques."}
    if response.status_code != 200:
        return {"ok": False, "error": f"réponse HTTP {response.status_code}."}
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "error": "réponse non JSON."}
    parser = _PARSERS.get((spec["id"], kind))
    if parser is None:
        return {"ok": False, "error": "recherche non prise en charge pour ce fournisseur."}
    try:
        items = parser(payload, block)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        return {"ok": False, "error": "réponse inattendue du fournisseur."}
    return {"ok": True, "items": items}


def _store(spec: dict, kind: str, block: dict, items: list[dict]) -> list[dict]:
    """Met les fiches en cache (refs opaques) et renvoie leur version publique."""
    hosts = [str(h) for h in (block.get("hosts") or [])]
    resolver = str(block.get("resolver") or "")
    out: list[dict] = []
    for item in items:
        download = str(item.get("download") or "")
        if download:
            try:
                _check_url(download, hosts)
            except StockError:
                continue  # jamais importable : on ne le propose pas
        elif not resolver:
            continue
        item_id = str(item.get("id") or "")
        page = str(item.get("page") or "")
        seed = hashlib.sha1(f"{item_id}|{page}".encode("utf-8")).hexdigest()[:16]
        ref = f"{spec['id']}:{kind}:{seed}"
        entry = {
            **item,
            "ref": ref,
            "source_id": spec["id"],
            "kind": kind,
            "provider": spec["label"],
            "hosts": hosts,
            "resolver": resolver,
        }
        if not entry.get("license"):
            entry["license"] = str(block.get("license") or "")
        _cache_put(ref, entry)
        out.append(_public(entry))
    return out


def search(query: str, kind: str = "video", source: str = "", limit: int = 8) -> dict:
    """Cherche un mot-clé auprès des banques prêtes, avec repli fournisseur."""
    text = str(query or "").strip()
    if not text:
        raise StockError("Donnez un mot-clé à rechercher (paramètre « query »).")
    if len(text) > _MAX_QUERY_CHARS:
        raise StockError(f"Mot-clé trop long : {_MAX_QUERY_CHARS} caractères maximum.")
    kind = str(kind or "").strip() or "video"
    if kind not in KINDS:
        raise StockError(f"Genre de recherche inconnu : {kind!r}. Choisissez parmi : {', '.join(KINDS)}.")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 8
    limit = max(1, min(20, limit))

    candidates = _candidates(kind, source)
    warnings: list[str] = []
    providers: list[str] = []
    for spec in candidates[:_PROVIDERS_MAX]:
        if not _ready(spec):
            if source:
                raise StockError(
                    f"{spec['label']} n'est pas prête : activez-la et enregistrez "
                    "sa clé sur la page Banques."
                )
            warnings.append(f"{spec['label']} ignorée : inactive ou sans clé (page Banques).")
            continue
        block = spec["search"][kind]
        outcome = _query(spec, block, text, kind, limit)
        if not outcome["ok"]:
            warnings.append(f"{spec['label']} : {outcome['error']}")
            continue
        results = _store(spec, kind, block, outcome["items"])[:limit]
        if not results:
            warnings.append(f"{spec['label']} : aucun résultat.")
            continue
        providers.append(spec["id"])
        return {
            "query": text,
            "kind": kind,
            "results": results,
            "providers": providers,
            "warnings": warnings,
            "note": "Chaque ref désigne un résultat conservé en cache : importez-le "
                    "avec l'action confirmée stock_import. La licence est celle "
                    "déclarée par le fournisseur ; absente, elle s'affiche « inconnue ».",
        }
    if not providers and not warnings:
        raise StockError(
            f"Aucune banque prête pour le genre « {kind} » : enregistrez une clé "
            "sur la page Banques."
        )
    return {
        "query": text,
        "kind": kind,
        "results": [],
        "providers": providers,
        "warnings": warnings,
        "note": "Aucun résultat : reformulez le mot-clé, changez de genre, ou "
                "vérifiez les banques prêtes sur la page Banques.",
    }


# --------------------------------------------------------------------------- #
# Téléchargement borné (HTTPS, liste blanche, redirections vérifiées)
# --------------------------------------------------------------------------- #

def _download(url: str, hosts: list[str], folder: Path, cancel=None) -> tuple[Path, int]:
    current = str(url)
    for _hop in range(_MAX_REDIRECTS + 1):
        _check_url(current, hosts)
        if cancel is not None:
            cancel()
        with _client() as client:
            with client.stream("GET", current) as response:
                status = response.status_code
                if status in (301, 302, 303, 307, 308):
                    location = str(response.headers.get("location") or "")
                    if not location:
                        raise StockError("Redirection sans destination.")
                    current = urljoin(current, location)
                    continue
                if status != 200:
                    raise StockError(
                        f"Téléchargement impossible : HTTP {status} depuis {urlsplit(current).hostname}."
                    )
                ext = _extension(current, str(response.headers.get("content-type") or ""))
                part = folder / f"stock-{uuid.uuid4().hex}{ext}"
                written = 0
                try:
                    with part.open("wb") as out:
                        for chunk in response.iter_bytes(64 * 1024):
                            if cancel is not None:
                                cancel()
                            written += len(chunk)
                            if written > _MAX_BYTES:
                                raise HTTPException(
                                    status_code=413,
                                    detail=f"Fichier trop volumineux (max {int(_MAX_BYTES // (1024 * 1024))} Mo).",
                                )
                            out.write(chunk)
                except BaseException:
                    part.unlink(missing_ok=True)
                    raise
                if written == 0:
                    part.unlink(missing_ok=True)
                    raise StockError("Fichier vide reçu du fournisseur.")
                return part, written
    raise StockError(f"Trop de redirections pour ce fichier ({_MAX_REDIRECTS} maximum).")


def _archive_file_url(entry: dict) -> str:
    """Résout le fichier réel d'une archive.org via son endpoint metadata."""
    identifier = str(entry.get("id") or "")
    if not identifier or not all(c.isalnum() or c in "-_." for c in identifier):
        raise StockError("Identifiant d'archive invalide.")
    meta_url = f"https://archive.org/metadata/{identifier}"
    _check_url(meta_url, entry["hosts"])
    try:
        with _client() as client:
            response = client.get(meta_url)
    except httpx.HTTPError as exc:
        raise StockError(f"Archive injoignable ({type(exc).__name__}).") from None
    if response.status_code != 200:
        raise StockError(f"Archive illisible (HTTP {response.status_code}).")
    try:
        payload = response.json()
    except ValueError:
        raise StockError("Archive : réponse non JSON.") from None
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        raise StockError("Archive sans fichier lisible.")
    names = [str((f or {}).get("name") or "") for f in files if isinstance(f, dict)]
    prefs = _ARCHIVE_PREFS.get(str(entry.get("kind") or ""), ())
    chosen = ""
    for pref in prefs:
        chosen = next((n for n in names if n.lower().endswith(pref)), "")
        if chosen:
            break
    if not chosen:
        chosen = next(
            (n for n in names if Path(n).suffix.lower() in media_mod.ALLOWED_EXTENSIONS),
            "",
        )
    if not chosen:
        raise StockError("Aucun fichier exploitable (vidéo, audio ou image) dans cette archive.")
    return f"https://archive.org/download/{identifier}/{quote(chosen)}"


def _enrich_provenance(media_id: str, entry: dict) -> None:
    """Ajoute la source banque à la provenance écrite par l'import."""
    data = media_mod.provenance_of(media_id)
    data.pop("declared", None)
    data.update({
        "provider": entry["provider"],
        "provider_id": entry["source_id"],
        "item_id": str(entry.get("id") or ""),
        "item_title": str(entry.get("title") or ""),
        "author": str(entry.get("author") or ""),
        "page": str(entry.get("page") or ""),
    })
    media_mod.write_provenance(media_id, data)


def import_item(ref: str, cancel=None) -> dict:
    """Télécharge le résultat désigné par ``ref`` vers la médiathèque.

    Déduplication par sha256 (le fichier déjà importé est réutilisé),
    provenance complète écrite, licence déclarée — ou « inconnue ».
    """
    entry = _CACHE.get(str(ref or ""))
    if entry is None:
        raise StockError(
            "Résultat introuvable : relancez la recherche (search_stock) avant d'importer."
        )
    if cancel is not None:
        cancel()
    url = str(entry.get("download") or "")
    if not url:
        if entry.get("resolver") == "archive":
            url = _archive_file_url(entry)
        else:
            raise StockError("Ce résultat ne porte aucun fichier téléchargeable.")
    _check_url(url, entry["hosts"])

    folder = media_mod.MEDIA_DIR
    folder.mkdir(parents=True, exist_ok=True)
    part, size = _download(url, entry["hosts"], folder, cancel=cancel)
    try:
        digest = _digest_of(part)
        existing = _find_by_digest(digest)
        licence = str(entry.get("license") or "")
        if existing:
            return {
                "ref": f"media://{existing}",
                "provider": entry["provider"],
                "title": entry["title"],
                "licence": licence or "inconnue",
                "author": entry.get("author") or "",
                "page": entry.get("page") or "",
                "bytes": size,
                "dedup": True,
                "summary": (
                    f"Déjà présent dans la médiathèque : « {entry['title']} » "
                    f"(licence {licence or 'inconnue'}) — fichier réutilisé, rien n'est réécrit."
                ),
            }
        source_line = str(entry["provider"]) + (f" — {entry['page']}" if entry.get("page") else "")
        media_id = media_mod.import_file_to_media(
            part, source=source_line, licence=licence, digest=digest
        )
        _enrich_provenance(media_id, entry)
        return {
            "ref": f"media://{media_id}",
            "provider": entry["provider"],
            "title": entry["title"],
            "licence": licence or "inconnue",
            "author": entry.get("author") or "",
            "page": entry.get("page") or "",
            "bytes": size,
            "dedup": False,
            "summary": (
                f"« {entry['title']} » importé depuis {entry['provider']} "
                f"(licence {licence or 'inconnue'}) — provenance écrite, projet inchangé."
            ),
        }
    finally:
        part.unlink(missing_ok=True)
