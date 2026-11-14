"""Contrat EDL (edit decision list) du montage footage.

Un EDL decrit un montage **reel** : quels rushes, de quelle seconde a quelle
seconde, dans quel ordre, avec quelles transitions, quelle musique. Il ne
contient que des references ``media://<id>`` : la provenance d'un plan (fichier
local, Pexels, Archive.org, NASA) vit dans le manifeste d'assets, pas ici. Une
source distante doit donc etre ingeree dans ``media/`` avant le rendu, ce qui
garde le rendu deterministe et hors ligne.

Vocabulaire ferme, comme le reste du studio : un role, une transition ou un
etalonnage hors listes est refuse. Les erreurs sont indexees (``cuts[2].out``)
pour que le modele puisse les corriger sans deviner.
"""
from __future__ import annotations

from math import isfinite
from typing import Callable

EDL_VERSION = 1

ROLES = ("hook", "body", "broll", "quote", "detail", "transition", "end")

# nom public -> nom de transition ffmpeg (xfade)
TRANSITIONS = {
    "cut": None,
    "fade": "fade",
    "dissolve": "dissolve",
    "wipeleft": "wipeleft",
    "slideup": "slideup",
}

GRADES = ("none", "warm", "cool", "sepia", "mono", "teal_orange")

MIN_CUT_SECONDS = 0.4
MAX_CUT_SECONDS = 120.0
MIN_TOTAL_SECONDS = 2.0
MAX_TOTAL_SECONDS = 3600.0
MAX_CUTS = 80
MIN_TRANSITION_SECONDS = 0.1
MAX_TRANSITION_SECONDS = 2.0
# une transition ne peut pas manger plus de 40 % du plan le plus court qu'elle relie
MAX_TRANSITION_RATIO = 0.4
MAX_DISTINCT_TRANSITIONS = 4

DEFAULT_CANVAS = {"width": 1920, "height": 1080, "fps": 30}
MAX_CANVAS_SIDE = 7680
MIN_CANVAS_SIDE = 16
MIN_FPS = 12
MAX_FPS = 60


class EdlError(ValueError):
    """EDL invalide : le message liste les erreurs, jamais une seule."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        super().__init__("; ".join(errors))


def _num(value) -> float | None:
    """Convertit en float fini, sinon None (bool refuse : True n'est pas 1.0)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def media_id_of(ref) -> str | None:
    """Identifiant d'une reference ``media://<id>``, sinon None."""
    if not isinstance(ref, str):
        return None
    prefix = "media://"
    if not ref.startswith(prefix):
        return None
    media_id = ref[len(prefix):].strip()
    if not media_id or any(c in media_id for c in "/\\.:"):
        return None
    return media_id


def normalize(edl: dict) -> dict:
    """Copie complete et bornee : defauts remplis, champs inconnus retires.

    Ne leve jamais : la validation est le role de :func:`validate`. Le
    resultat ne contient que les cles du contrat.
    """
    if not isinstance(edl, dict):
        return {"version": EDL_VERSION, "canvas": dict(DEFAULT_CANVAS), "cuts": [], "audio": {}}

    canvas_in = edl.get("canvas") if isinstance(edl.get("canvas"), dict) else {}
    canvas = {
        "width": canvas_in.get("width", DEFAULT_CANVAS["width"]),
        "height": canvas_in.get("height", DEFAULT_CANVAS["height"]),
        "fps": canvas_in.get("fps", DEFAULT_CANVAS["fps"]),
    }

    cuts: list[dict] = []
    for raw in edl.get("cuts") or []:
        if not isinstance(raw, dict):
            continue
        transition = raw.get("transition", "cut")
        if isinstance(transition, dict):
            name = transition.get("type", "cut")
            duration = transition.get("duration", 0.5)
        else:
            name, duration = transition, 0.5
        if name == "cut":
            duration = 0.0
        cuts.append(
            {
                "media": raw.get("media"),
                "in": raw.get("in", 0.0),
                "out": raw.get("out"),
                "role": raw.get("role", "body"),
                "reason": raw.get("reason", ""),
                "transition": {"type": name, "duration": duration},
            }
        )

    audio_in = edl.get("audio") if isinstance(edl.get("audio"), dict) else {}
    audio = {
        "music": audio_in.get("music"),
        "gain_db": audio_in.get("gain_db", -18.0),
        "duck": bool(audio_in.get("duck", True)),
        "fade_in": audio_in.get("fade_in", 1.0),
        "fade_out": audio_in.get("fade_out", 2.0),
    }
    if not audio["music"]:
        audio = {}

    grade_in = edl.get("grade") if isinstance(edl.get("grade"), dict) else {}
    grade = {
        "look": grade_in.get("look", "none"),
        "saturation": grade_in.get("saturation", 1.0),
        "contrast": grade_in.get("contrast", 1.0),
    }

    return {
        "version": edl.get("version", EDL_VERSION),
        "canvas": canvas,
        "cuts": cuts,
        "audio": audio,
        "grade": grade,
    }


def cut_durations(edl: dict) -> list[float]:
    """Durees brutes des plans (avant recouvrement des transitions)."""
    durations = []
    for cut in edl.get("cuts") or []:
        start, end = _num(cut.get("in")), _num(cut.get("out"))
        durations.append(max(0.0, (end - start)) if start is not None and end is not None else 0.0)
    return durations


def timeline_duration(edl: dict) -> float:
    """Duree finale : somme des plans moins les recouvrements de transition."""
    raw = sum(cut_durations(edl))
    overlap = 0.0
    for cut in (edl.get("cuts") or [])[1:]:
        transition = cut.get("transition") or {}
        overlap += _num(transition.get("duration")) or 0.0
    return max(0.0, raw - overlap)


def validate(
    edl: dict,
    *,
    media_exists: Callable[[str], bool] | None = None,
) -> tuple[list[str], list[str]]:
    """(erreurs, avertissements) d'un EDL. Ne touche pas au disque sans callback."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(edl, dict):
        return ["edl : un objet JSON est attendu."], []
    if edl.get("version") != EDL_VERSION:
        errors.append(f"version : {EDL_VERSION} attendu, recu {edl.get('version')!r}.")

    canvas = edl.get("canvas") or {}
    for side in ("width", "height"):
        value = _num(canvas.get(side))
        if value is None or value < MIN_CANVAS_SIDE or value > MAX_CANVAS_SIDE:
            errors.append(f"canvas.{side} : entier entre {MIN_CANVAS_SIDE} et {MAX_CANVAS_SIDE} attendu.")
        elif int(value) % 2:
            errors.append(f"canvas.{side} : doit etre pair (encodage yuv420p).")
    fps = _num(canvas.get("fps"))
    if fps is None or not (MIN_FPS <= fps <= MAX_FPS):
        errors.append(f"canvas.fps : entre {MIN_FPS} et {MAX_FPS} attendu.")

    cuts = edl.get("cuts") or []
    if not isinstance(cuts, list) or not cuts:
        errors.append("cuts : au moins un plan est requis.")
        cuts = []
    if len(cuts) > MAX_CUTS:
        errors.append(f"cuts : {MAX_CUTS} plans maximum ({len(cuts)} recus).")

    durations = cut_durations(edl)
    seen_media: dict[str, int] = {}
    distinct_transitions: set[str] = set()

    for index, cut in enumerate(cuts):
        prefix = f"cuts[{index}]"
        media_id = media_id_of(cut.get("media"))
        if media_id is None:
            errors.append(
                f"{prefix}.media : reference « media://<id> » attendue "
                "(ingerer une source distante avant le rendu)."
            )
        else:
            if media_id in seen_media:
                warnings.append(
                    f"{prefix}.media : média deja utilise par cuts[{seen_media[media_id]}] "
                    "(un média par plan est la regle du manifeste d'assets)."
                )
            seen_media.setdefault(media_id, index)
            if media_exists is not None and not media_exists(media_id):
                errors.append(f"{prefix}.media : média introuvable : {media_id}.")

        start, end = _num(cut.get("in")), _num(cut.get("out"))
        if start is None or start < 0:
            errors.append(f"{prefix}.in : nombre positif attendu (secondes).")
        if end is None:
            errors.append(f"{prefix}.out : nombre attendu (secondes).")
        elif start is not None:
            duration = end - start
            if duration < MIN_CUT_SECONDS:
                errors.append(
                    f"{prefix} : plan trop court ({duration:.2f} s), "
                    f"{MIN_CUT_SECONDS} s minimum."
                )
            elif duration > MAX_CUT_SECONDS:
                errors.append(
                    f"{prefix} : plan trop long ({duration:.1f} s), "
                    f"{MAX_CUT_SECONDS:.0f} s maximum."
                )

        if cut.get("role") not in ROLES:
            errors.append(f"{prefix}.role : {cut.get('role')!r} inconnu. Choix : {', '.join(ROLES)}.")
        reason = cut.get("reason")
        if reason is not None and not isinstance(reason, str):
            errors.append(f"{prefix}.reason : texte attendu.")
        elif isinstance(reason, str) and len(reason) > 400:
            errors.append(f"{prefix}.reason : 400 caracteres maximum.")

        transition = cut.get("transition") or {}
        name = transition.get("type", "cut")
        if name not in TRANSITIONS:
            errors.append(
                f"{prefix}.transition.type : {name!r} inconnu. "
                f"Choix : {', '.join(TRANSITIONS)}."
            )
        else:
            distinct_transitions.add(name)
        length = _num(transition.get("duration", 0.0))
        if length is None:
            errors.append(f"{prefix}.transition.duration : nombre attendu (secondes).")
            length = 0.0
        if name == "cut" and length > 0:
            errors.append(f"{prefix}.transition.duration : doit etre 0 pour une coupe franche.")
        if name != "cut":
            if not (MIN_TRANSITION_SECONDS <= length <= MAX_TRANSITION_SECONDS):
                errors.append(
                    f"{prefix}.transition.duration : entre {MIN_TRANSITION_SECONDS} et "
                    f"{MAX_TRANSITION_SECONDS} s attendu."
                )
            if index == 0:
                errors.append(f"{prefix}.transition : le premier plan ne peut pas avoir de transition.")
            else:
                previous = durations[index - 1] if index - 1 < len(durations) else 0.0
                current = durations[index] if index < len(durations) else 0.0
                shortest = min(previous, current)
                if shortest and length > shortest * MAX_TRANSITION_RATIO:
                    errors.append(
                        f"{prefix}.transition.duration : {length} s pour un plan de {shortest:.2f} s "
                        f"(maximum {MAX_TRANSITION_RATIO:.0%} du plan le plus court)."
                    )

    if len(distinct_transitions) > MAX_DISTINCT_TRANSITIONS:
        errors.append(
            f"transitions : {len(distinct_transitions)} valeurs distinctes, "
            f"{MAX_DISTINCT_TRANSITIONS} maximum dans une meme piece."
        )

    total = timeline_duration(edl)
    if cuts and total < MIN_TOTAL_SECONDS:
        errors.append(f"durée : {total:.2f} s, {MIN_TOTAL_SECONDS} s minimum.")
    if total > MAX_TOTAL_SECONDS:
        errors.append(f"durée : {total:.0f} s, {MAX_TOTAL_SECONDS:.0f} s maximum.")

    grade = edl.get("grade") or {}
    if grade.get("look") not in GRADES:
        errors.append(f"grade.look : {grade.get('look')!r} inconnu. Choix : {', '.join(GRADES)}.")
    for key in ("saturation", "contrast"):
        value = _num(grade.get(key, 1.0))
        if value is None or not (0.0 <= value <= 2.0):
            errors.append(f"grade.{key} : entre 0 et 2 attendu.")

    audio = edl.get("audio") or {}
    if audio:
        music_id = media_id_of(audio.get("music"))
        if music_id is None:
            errors.append("audio.music : reference « media://<id> » attendue.")
        elif media_exists is not None and not media_exists(music_id):
            errors.append(f"audio.music : média introuvable : {music_id}.")
        gain = _num(audio.get("gain_db", -18.0))
        if gain is None or not (-60.0 <= gain <= 0.0):
            errors.append("audio.gain_db : entre -60 et 0 attendu.")
        for key in ("fade_in", "fade_out"):
            value = _num(audio.get(key, 0.0))
            if value is None or value < 0 or value > 10:
                errors.append(f"audio.{key} : entre 0 et 10 secondes attendu.")
        if not isinstance(audio.get("duck"), bool):
            errors.append("audio.duck : booleen attendu.")

    return errors, warnings


def validate_or_raise(edl: dict, *, media_exists: Callable[[str], bool] | None = None) -> dict:
    """Normalise + valide ; leve :class:`EdlError` avec toutes les erreurs."""
    normalized = normalize(edl)
    errors, warnings = validate(normalized, media_exists=media_exists)
    if errors:
        raise EdlError(errors, warnings)
    return normalized
