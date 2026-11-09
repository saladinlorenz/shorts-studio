"""Pack de marque client : ce qui se retrouve d'une video a l'autre.

Un pack ne porte que des champs qui existent deja dans le format de projet
(``theme``, ``content.signature``, ``audio``, ``model``) : il n'invente aucune cle,
et un projet qui passe par un pack reste validable par ``validation.validate_project``.

Meme discipline que le catalogue d'effets : ``normalize()`` refuse ce qui est faux
(erreur), signale ce qui est superflu (avertissement), ne remplace jamais une valeur
par une hypothese. ``apply_brand()`` ne fait qu'ecrire dans le projet — c'est
l'utilisateur qui decide de l'appliquer, jamais le serveur de lui-meme.
"""
from __future__ import annotations

import re

from . import fonts as fonts_mod
from . import schema

MEDIA_REF = re.compile(r"^media://[0-9A-Za-z_-]{4,64}$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

THEME_KEYS = tuple(schema.default_theme().keys())
SIGNATURE_KEYS = tuple(schema.default_signature().keys())
AUDIO_KEYS = ("enabled", "music", "music_volume")

# Deux formes particulieres dans ces sections : du texte libre (nom de palette,
# handle affiche a l'ecran) et une reference de media du studio (logo, musique).
STRING_KEYS = {"palette_id", "handle"}
MEDIA_KEYS = {"media", "music"}

MAX_LABEL_CHARS = 80
MAX_NOTES_CHARS = 600


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_ref(value, label: str, errors: list[str]) -> str:
    ref = str(value or "").strip()
    if not ref:
        return ""
    # une reference de media du studio est la seule forme acceptee ; le scheme
    # « media:// » contient des « / », on le valide donc avant tout test de chemin.
    if ref.startswith("media://"):
        if not MEDIA_REF.match(ref):
            errors.append(f"{label} : référence média invalide (media:// suivi de 4 à 64 caractères d'identifiant).")
            return ""
        return ref
    errors.append(f"{label} : un chemin ou une URL ne sont pas acceptés, choisissez un media du studio.")
    return ""


def _check_section(section: dict, keys: tuple, label: str, errors: list[str], warnings: list[str]) -> dict:
    """Une section de theme ou de signature, cle par cle, dans les types attendus."""
    out: dict = {}
    for key, value in (section or {}).items():
        if key not in keys:
            warnings.append(f"{label} : réglage {key!r} inconnu, ignoré.")
            continue
        if key == "position":
            if not isinstance(value, dict):
                errors.append(f"{label} : la position doit être un objet {{x, y}}.")
                continue
            out[key] = {k: float(v) for k, v in value.items() if k in ("x", "y") and _is_number(v)}
            continue
        if key in MEDIA_KEYS:
            ref = _check_ref(value, f"{label} : {key}", errors)
            if ref:
                out[key] = ref
            continue
        if key in STRING_KEYS:
            out[key] = str(value or "").strip()[:80]
            continue
        if key.endswith("_color") or key == "color":
            if not isinstance(value, str) or not HEX_COLOR.match(value.strip()):
                errors.append(f"{label} : couleur {value!r} illisible (forme attendue : #RRGGBB).")
                continue
            out[key] = value.strip()
            continue
        if key.endswith("_family"):
            family = str(value or "").strip()
            if not family:
                errors.append(f"{label} : aucune police choisie.")
                continue
            if not fonts_mod.known_family(family):
                errors.append(f"{label} : police {family!r} absente du catalogue sous licence du studio.")
                continue
            out[key] = family
            continue
        if isinstance(value, bool):
            out[key] = value
            continue
        if _is_number(value):
            out[key] = float(value) if isinstance(value, float) else value
            continue
        errors.append(f"{label} : valeur de {key!r} ni média, ni texte, nombre ou booléen.")
    return out


def normalize(raw: dict) -> tuple[dict, list[str], list[str]]:
    """Pack brut -> pack sur, avec erreurs et avertissements separes."""
    errors: list[str] = []
    warnings: list[str] = []
    data = raw if isinstance(raw, dict) else {}

    label = str(data.get("label") or "").strip()
    if not label:
        errors.append("Pack : un nom de client est obligatoire.")
    if len(label) > MAX_LABEL_CHARS:
        label = label[:MAX_LABEL_CHARS]
        warnings.append(f"Pack : nom raccourci à {MAX_LABEL_CHARS} caractères.")

    notes = str(data.get("notes") or "").strip()[:MAX_NOTES_CHARS]

    for key in data:
        if key not in {"label", "notes", "theme", "signature", "audio", "models"}:
            warnings.append(f"Pack : section {key!r} inconnue, ignorée.")

    theme = _check_section(data.get("theme") or {}, THEME_KEYS, "Thème", errors, warnings)
    signature = _check_section(data.get("signature") or {}, SIGNATURE_KEYS, "Signature", errors, warnings)

    raw_audio = data.get("audio") or {}
    audio: dict = {}
    for key, value in raw_audio.items():
        if key not in AUDIO_KEYS:
            warnings.append(f"Audio : réglage {key!r} inconnu, ignoré.")
            continue
        if key == "music":
            ref = _check_ref(value, "Musique du pack", errors)
            if ref:
                audio[key] = ref
        elif key == "enabled":
            audio[key] = bool(value)
        else:
            if not _is_number(value):
                errors.append("Audio : volume de musique illisible.")
                continue
            volume = float(value)
            if not 0.0 <= volume <= 1.0:
                volume = min(1.0, max(0.0, volume))
                warnings.append(f"Audio : volume ramené à {volume} (borne 0 à 1).")
            audio[key] = round(volume, 3)

    models = data.get("models") or []
    if not isinstance(models, list):
        errors.append("Modèles autorisés : la liste doit être une liste d'identifiants.")
        models = []
    else:
        clean = []
        for model_id in models:
            if str(model_id) not in schema.MODELS:
                errors.append(
                    f"Modèles autorisés : {model_id!r} inconnu (connus : {', '.join(schema.MODELS)})."
                )
                continue
            clean.append(str(model_id))
        models = clean

    pack = {
        "label": label,
        "notes": notes,
        "theme": theme,
        "signature": signature,
        "audio": audio,
        "models": models,
    }
    return pack, errors, warnings


def from_project(project: dict, label: str, notes: str = "") -> dict:
    """Pack construit avec ce que le projet affiche deja (aucune valeur inventee)."""
    content = project.get("content") or {}
    audio = project.get("audio") or {}
    return {
        "label": label,
        "notes": notes,
        "theme": {k: v for k, v in (project.get("theme") or {}).items() if k in THEME_KEYS},
        "signature": {k: v for k, v in (content.get("signature") or {}).items() if k in SIGNATURE_KEYS},
        "audio": {k: audio.get(k) for k in AUDIO_KEYS if k in audio},
        "models": [str(project.get("model", {}).get("id") or "")] if project.get("model") else [],
    }


def apply_brand(project: dict, pack: dict) -> tuple[dict, list[str]]:
    """Applique un pack a un projet et renvoie le projet patche + avertissements.

    N'ecrit que dans des cles existantes, ne touche ni aux scenes ni aux calques,
    et ne remplace pas le modele du projet : un pack qui n'autorise pas le modele
    affiche le projet reste un avertissement, pas une surprise.
    """
    warnings: list[str] = []
    patched = schema.clone(project)
    patched.pop("resolved", None)

    theme = patched.setdefault("theme", schema.default_theme())
    for key, value in (pack.get("theme") or {}).items():
        if key in THEME_KEYS:
            theme[key] = value

    signature = (patched.setdefault("content", {})).setdefault("signature", schema.default_signature())
    for key, value in (pack.get("signature") or {}).items():
        if key in SIGNATURE_KEYS:
            signature[key] = value
    if pack.get("signature", {}).get("media") and not signature.get("enabled", True):
        warnings.append("Signature désactivée dans le projet : le logo du pack ne s'affichera pas.")

    audio = patched.setdefault("audio", {})
    for key, value in (pack.get("audio") or {}).items():
        if key in AUDIO_KEYS:
            audio[key] = value
    if pack.get("audio", {}).get("music") and not audio.get("enabled", False):
        warnings.append("Piste audio du pack enregistrée mais l'audio reste désactivé dans le projet.")

    allowed = pack.get("models") or []
    model_id = str((patched.get("model") or {}).get("id") or "")
    if allowed and model_id and model_id not in allowed:
        warnings.append(
            f"Modèle {model_id!r} hors des modèles autorisés du pack ({', '.join(allowed)}) : "
            "il reste appliqué, changez de modèle si le client l'impose."
        )
    return patched, warnings
