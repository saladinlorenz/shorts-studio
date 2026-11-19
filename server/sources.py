"""Banques de contenu : clés API côté serveur, jamais renvoyées au navigateur.

Catalogue fixe de fournisseurs (Pexels, NASA, Pixabay, Unsplash, Freesound,
Jamendo, Internet Archive) : clés en écriture seule, test de connexion réel
depuis le serveur vers l'API officielle, et blocs « search » qui déclarent
URL de recherche, paramètres et hébergeurs de téléchargement — le module
voisin ``server/stock.py`` s'appuie dessus pour chercher et importer, sans
jamais accepter une URL venue du navigateur ou du modèle.

Les URL de test et de recherche sont décidées ici, jamais ailleurs (aucun
SSRF) : le navigateur choisit un fournisseur du catalogue et fournit sa clé,
rien d'autre. Les clés ne sortent jamais : seul un indice des 4 derniers
caractères est affiché, comme pour les réglages de l'assistant.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

SOURCES_PATH = Path(__file__).with_name("sources.json")

_KEY_RE = re.compile(r"[A-Za-z0-9_-]{4,200}")
_TEST_TIMEOUT = 10.0

# Catalogue fixe. « test » décrit l'appel de vérification : mode de transport
# de la clé (en-tête ou paramètre), chemin d'un échantillon lisible dans la réponse.
CATALOG: list[dict] = [
    {
        "id": "pexels",
        "label": "Pexels",
        "tagline": "Vidéos et photos libres de droits, recherche par mots-clés.",
        "kinds": ["video", "photo"],
        "key_required": True,
        "key_label": "Clé API",
        "signup_url": "https://www.pexels.com/api/",
        "docs_url": "https://www.pexels.com/api/documentation/",
        "search": {
            "video": {
                "url": "https://api.pexels.com/videos/search",
                "params": {"query": "{query}", "per_page": "{limit}"},
                "key_mode": "header", "key_name": "Authorization", "key_prefix": "",
                "license": "Pexels License",
                "hosts": ["videos.pexels.com"],
            },
            "photo": {
                "url": "https://api.pexels.com/v1/search",
                "params": {"query": "{query}", "per_page": "{limit}"},
                "key_mode": "header", "key_name": "Authorization", "key_prefix": "",
                "license": "Pexels License",
                "hosts": ["images.pexels.com"],
            },
        },
        "test": {
            "url": "https://api.pexels.com/v1/curated",
            "params": {"per_page": "1"},
            "key_mode": "header",
            "key_name": "Authorization",
            "key_prefix": "",
            "sample": ["photos", 0, "alt"],
        },
    },
    {
        "id": "pixabay",
        "label": "Pixabay",
        "tagline": "Plus de 4 millions d'images, vidéos et musiques libres.",
        "kinds": ["video", "photo", "music"],
        "key_required": True,
        "key_label": "Clé API",
        "signup_url": "https://pixabay.com/api/docs/",
        "docs_url": "https://pixabay.com/api/docs/",
        "search": {
            "photo": {
                "url": "https://pixabay.com/api/",
                "params": {"q": "{query}", "per_page": "{limit}", "image_type": "photo"},
                "key_mode": "query", "key_name": "key", "key_prefix": "",
                "license": "Pixabay Content License",
                "hosts": ["cdn.pixabay.com"],
            },
            "video": {
                "url": "https://pixabay.com/api/videos/",
                "params": {"q": "{query}", "per_page": "{limit}"},
                "key_mode": "query", "key_name": "key", "key_prefix": "",
                "license": "Pixabay Content License",
                "hosts": ["cdn.pixabay.com"],
            },
        },
        "test": {
            "url": "https://pixabay.com/api/",
            "params": {"image_type": "photo", "per_page": "3"},
            "key_mode": "query",
            "key_name": "key",
            "key_prefix": "",
            "sample": ["hits", 0, "tags"],
        },
    },
    {
        "id": "unsplash",
        "label": "Unsplash",
        "tagline": "Photographies haute résolution, licence Unsplash.",
        "kinds": ["photo"],
        "key_required": True,
        "key_label": "Access Key",
        "signup_url": "https://unsplash.com/developers",
        "docs_url": "https://unsplash.com/documentation",
        "search": {
            "photo": {
                "url": "https://api.unsplash.com/search/photos",
                "params": {"query": "{query}", "per_page": "{limit}"},
                "key_mode": "header", "key_name": "Authorization", "key_prefix": "Client-ID ",
                "license": "Unsplash License",
                "hosts": ["images.unsplash.com"],
            },
        },
        "test": {
            "url": "https://api.unsplash.com/photos",
            "params": {"per_page": "1"},
            "key_mode": "header",
            "key_name": "Authorization",
            "key_prefix": "Client-ID ",
            "sample": [0, "alt_description"],
        },
    },
    {
        "id": "nasa",
        "label": "NASA",
        "tagline": "Image du jour, Mars, Terre : le domaine public spatial.",
        "kinds": ["space", "photo"],
        "key_required": False,
        "key_label": "Clé API (optionnelle, sinon DEMO_KEY)",
        "signup_url": "https://api.nasa.gov/",
        "docs_url": "https://api.nasa.gov/",
        "search": {
            "photo": {
                "url": "https://images-api.nasa.gov/search",
                "params": {"q": "{query}", "media_type": "image", "page_size": "{limit}"},
                "key_mode": "none", "key_name": "", "key_prefix": "",
                # L'API ne déclare aucune licence par item : elle reste « inconnue ».
                "license": "",
                "hosts": ["images-assets.nasa.gov"],
            },
            "space": {
                "url": "https://images-api.nasa.gov/search",
                "params": {"q": "{query}", "media_type": "image", "page_size": "{limit}"},
                "key_mode": "none", "key_name": "", "key_prefix": "",
                "license": "",
                "hosts": ["images-assets.nasa.gov"],
            },
        },
        "test": {
            "url": "https://api.nasa.gov/planetary/apod",
            "params": {},
            "key_mode": "query",
            "key_name": "api_key",
            "key_prefix": "",
            "default_key": "DEMO_KEY",
            "sample": ["title"],
        },
    },
    {
        "id": "freesound",
        "label": "Freesound",
        "tagline": "Bruitage et effets sonores collaboratifs, licences Creative Commons.",
        "kinds": ["audio"],
        "key_required": True,
        "key_label": "Clé API (token)",
        "signup_url": "https://freesound.org/apiv2/apply",
        "docs_url": "https://freesound.org/docs/api/",
        "search": {
            "audio": {
                "url": "https://freesound.org/apiv2/search/text/",
                "params": {"query": "{query}", "page_size": "{limit}",
                           "fields": "id,name,username,license,duration,previews"},
                "key_mode": "query", "key_name": "token", "key_prefix": "",
                "max_limit": 15,
                "license": "",
                "hosts": ["cdn.freesound.org", "freesound.org"],
            },
        },
        "test": {
            "url": "https://freesound.org/apiv2/search/text/",
            "params": {"query": "wind", "page_size": "1"},
            "key_mode": "query",
            "key_name": "token",
            "key_prefix": "",
            "sample": ["results", 0, "name"],
        },
    },
    {
        "id": "jamendo",
        "label": "Jamendo",
        "tagline": "Musiques indépendantes sous licences Creative Commons.",
        "kinds": ["music"],
        "key_required": True,
        "key_label": "Client ID",
        "signup_url": "https://devportal.jamendo.com/",
        "docs_url": "https://developer.jamendo.com/v3.0",
        "search": {
            "music": {
                "url": "https://api.jamendo.com/v3.0/tracks/",
                "params": {"search": "{query}", "limit": "{limit}", "format": "json"},
                "key_mode": "query", "key_name": "client_id", "key_prefix": "",
                "license": "",
                "hosts": [".jamendo.com"],
            },
        },
        "test": {
            "url": "https://api.jamendo.com/v3.0/tracks/",
            "params": {"format": "json", "limit": "1"},
            "key_mode": "query",
            "key_name": "client_id",
            "key_prefix": "",
            "sample": ["results", 0, "name"],
        },
    },
    {
        "id": "archive",
        "label": "Internet Archive",
        "tagline": "Films, concerts et documents du domaine public, sans clé.",
        "kinds": ["video", "audio", "archive"],
        "key_required": False,
        "key_label": "Aucune clé requise",
        "signup_url": "",
        "docs_url": "https://archive.org/developers/",
        "search": {
            "video": {
                "url": "https://archive.org/advancedsearch.php",
                "params": {"q": "{query} AND mediatype:movies", "rows": "{limit}", "output": "json",
                           "fl[]": ["identifier", "title", "creator", "licenseurl", "mediatype"]},
                "key_mode": "none", "key_name": "", "key_prefix": "",
                # Le fichier n'est pas dans la recherche : le module stock va
                # lire https://archive.org/metadata/<id> au moment de l'import.
                "resolver": "archive",
                "license": "",
                "hosts": ["archive.org", ".archive.org"],
            },
            "audio": {
                "url": "https://archive.org/advancedsearch.php",
                "params": {"q": "{query} AND mediatype:audio", "rows": "{limit}", "output": "json",
                           "fl[]": ["identifier", "title", "creator", "licenseurl", "mediatype"]},
                "key_mode": "none", "key_name": "", "key_prefix": "",
                "resolver": "archive",
                "license": "",
                "hosts": ["archive.org", ".archive.org"],
            },
        },
        "test": {
            "url": "https://archive.org/advancedsearch.php",
            "params": {"q": "mediatype:movies", "rows": "1", "output": "json"},
            "key_mode": "none",
            "key_name": "",
            "key_prefix": "",
            "sample": ["response", "docs", 0, "title"],
        },
    },
]

_BY_ID = {spec["id"]: spec for spec in CATALOG}


class SourceError(ValueError):
    """Erreur réparable : message affiché tel quel à l'utilisateur."""


class UnknownSource(SourceError):
    pass


def _spec(source_id: str) -> dict:
    spec = _BY_ID.get(source_id)
    if spec is None:
        raise UnknownSource(f"Source inconnue : {source_id!r}. Choisissez une source du catalogue.")
    return spec


def _load() -> dict:
    try:
        data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    clean = {}
    for source_id, entry in data.items():
        if source_id not in _BY_ID or not isinstance(entry, dict):
            continue
        clean[source_id] = {
            "key": str(entry.get("key") or ""),
            "enabled": bool(entry.get("enabled", True)),
        }
    return clean


def _save(data: dict) -> None:
    tmp = SOURCES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SOURCES_PATH)


def key_of(source_id: str) -> str:
    """Clé enregistrée pour une source — usage serveur interne uniquement.

    La valeur ne quitte jamais ce processus : elle est injectée dans la
    requête sortante puis oubliée, jamais renvoyée au navigateur ni au modèle.
    """
    if source_id not in _BY_ID:
        return ""
    return str(_load().get(source_id, {}).get("key") or "")


def public_state(spec: dict, entry: dict) -> dict:
    """État visible : jamais la clé, seulement un indice des 4 derniers caractères."""
    key = str(entry.get("key") or "")
    configured = bool(key)
    enabled = bool(entry.get("enabled", True))
    return {
        **{k: spec[k] for k in ("id", "label", "tagline", "kinds", "key_required", "key_label", "signup_url", "docs_url")},
        "key_configured": configured,
        "key_hint": ("••••" + key[-4:]) if configured else "",
        "enabled": enabled,
        "ready": enabled and (configured or not spec["key_required"]),
    }


def list_sources() -> dict:
    data = _load()
    providers = [public_state(spec, data.get(spec["id"], {})) for spec in CATALOG]
    return {
        "providers": providers,
        "configured": sum(1 for p in providers if p["key_configured"]),
        "ready": sum(1 for p in providers if p["ready"]),
        "note": "Terrain préparé : la recherche (outil search_stock) et l'import "
                "(action confirmée stock_import) passent par l'assistant, sur les "
                "URL du catalogue. Aucun contenu n'est téléchargé depuis cette page.",
    }


def state_of(source_id: str) -> dict:
    """État public d'une source (jamais la clé) ; lève UnknownSource si hors catalogue."""
    spec = _spec(source_id)
    return public_state(spec, _load().get(source_id, {}))


def save(source_id: str, *, key: str | None = None, enabled: bool | None = None, clear_key: bool = False) -> dict:
    spec = _spec(source_id)
    data = _load()
    entry = data.get(source_id, {"key": "", "enabled": True})
    # Une clé n'est écrite que si un texte est fourni : un champ vide laisse la
    # clé enregistrée en place. « clear_key » est l'effacement explicite.
    if key is not None and key.strip():
        typed = key.strip()
        if not _KEY_RE.fullmatch(typed):
            raise SourceError(
                "Clé invalide : 4 à 200 caractères attendus (lettres, chiffres, tirets, "
                "underscores), sans espace ni caractère spécial."
            )
        entry["key"] = typed
    if clear_key:
        entry["key"] = ""
    if enabled is not None:
        entry["enabled"] = bool(enabled)
    data[source_id] = entry
    _save(data)
    return public_state(spec, entry)


def _sample(data, path: list) -> str:
    node = data
    for step in path:
        if isinstance(step, int):
            if not isinstance(node, list) or step >= len(node):
                return ""
            node = node[step]
        else:
            if not isinstance(node, dict):
                return ""
            node = node.get(step)
    return str(node)[:120] if isinstance(node, (str, int, float)) else ""


def test_connection(source_id: str) -> dict:
    """Un appel réel vers l'API officielle, avec la clé enregistrée (jamais renvoyée)."""
    spec = _spec(source_id)
    test = spec["test"]
    entry = _load().get(source_id, {})
    key = str(entry.get("key") or "").strip()
    if test["key_mode"] != "none" and not key:
        key = str(test.get("default_key") or "")
    if test["key_mode"] != "none" and not key:
        raise SourceError(
            f"Aucune clé enregistrée pour {spec['label']} : saisissez-la, enregistrez-la, puis testez."
        )
    params = dict(test["params"])
    headers: dict[str, str] = {}
    if test["key_mode"] == "query":
        params[test["key_name"]] = key
    elif test["key_mode"] == "header":
        headers[test["key_name"]] = test.get("key_prefix", "") + key
    started = time.perf_counter()
    try:
        try:
            client = httpx.Client(timeout=_TEST_TIMEOUT, follow_redirects=False)
        except httpx.InvalidURL:
            # Certaines machines ont un NO_PROXY mal formé (ex. « [::1] ») qui
            # fait échouer la lecture de l'environnement : on retente sans.
            client = httpx.Client(timeout=_TEST_TIMEOUT, follow_redirects=False, trust_env=False)
        with client:
            response = client.get(test["url"], params=params, headers=headers)
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "message": f"{spec['label']} injoignable ({type(exc).__name__}). Vérifiez la connexion réseau de cette machine.",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code in (401, 403):
        return {"ok": False, "message": f"Clé refusée par {spec['label']} (HTTP {response.status_code}). Vérifiez la clé et ses droits.", "latency_ms": latency}
    if response.status_code == 429:
        return {"ok": False, "message": f"Quota {spec['label']} atteint (HTTP 429). Réessayez plus tard.", "latency_ms": latency}
    if response.status_code != 200:
        return {"ok": False, "message": f"Réponse inattendue de {spec['label']} (HTTP {response.status_code}).", "latency_ms": latency}
    try:
        data = response.json()
    except ValueError:
        return {"ok": False, "message": f"{spec['label']} a répondu un contenu non JSON.", "latency_ms": latency}
    # Certaines API (Jamendo) signalent l'échec dans le corps avec un HTTP 200.
    if isinstance(data, dict):
        status = (data.get("headers") or {}).get("status") if isinstance(data.get("headers"), dict) else None
        if status not in (None, "success"):
            detail = str((data.get("headers") or {}).get("error_message") or "")[:160]
            return {"ok": False, "message": f"{spec['label']} refuse la demande. {detail}".strip(), "latency_ms": latency}
    sample = _sample(data, test["sample"])
    return {
        "ok": True,
        "message": f"{spec['label']} répond : accès valide.",
        "latency_ms": latency,
        "sample": sample,
    }