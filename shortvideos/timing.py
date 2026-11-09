"""Calculs de duree, fondu, glissement et zoom.

Toutes les fonctions sont pures (projet en entree) : utilisees par la
composition (apercu et export) et par les tests.
"""
from __future__ import annotations


def duration(project: dict) -> float:
    """Duree totale de la scene, en secondes."""
    return float(project["timing"]["duration"])


def fps(project: dict) -> int:
    return int(project["export"]["fps"])


def frame_count(project: dict) -> int:
    """Nombre de frames de la scene (arrondi entier, minimum 1)."""
    return max(1, int(round(duration(project) * fps(project))))


def frame_time(index: int, project: dict) -> float:
    """Instant (s) correspondant a l'index de frame."""
    return index / fps(project)


def text_alpha(t: float, project: dict) -> float:
    """Opacite du texte a l'instant t (0.0 invisible -> 1.0 opaque).

    Gere le debut du texte, le fondu d'entree et le fondu de sortie.
    """
    tim = project["timing"]
    start = float(tim["text_start"])
    fade_in = max(0.0, float(tim["fade_in"]))
    fade_out = max(0.0, float(tim["fade_out"]))
    dur = duration(project)

    if t < start:
        return 0.0
    if t >= dur:
        return 0.0
    if fade_in > 0.0 and t < start + fade_in:
        return min(1.0, (t - start) / fade_in)
    fade_out_start = dur - fade_out
    if fade_out > 0.0 and t > fade_out_start:
        return max(0.0, (dur - t) / fade_out)
    return 1.0


def entrance_progress(t: float, project: dict) -> float:
    """Progression de l'entree du texte (0.0 -> 1.0), meme rythme que le fondu."""
    tim = project["timing"]
    start = float(tim["text_start"])
    fade_in = max(0.0, float(tim["fade_in"]))
    if t < start:
        return 0.0
    if fade_in <= 0.0:
        return 1.0
    return min(1.0, (t - start) / fade_in)


def text_offset_y(t: float, project: dict) -> int:
    """Decalage vertical (px, hauteur du canvas) pour l'effet glissement."""
    if project["animation"]["text_in"] != "slide":
        return 0
    progress = entrance_progress(t, project)
    height = int(project["export"]["height"])
    return int(round((1.0 - progress) * 0.05 * height))


# Zoom lent du fond : 1.0 -> 1.08 sur toute la duree de la scene.
ZOOM_MAX = 1.08


def background_scale(t: float, project: dict) -> float:
    """Facteur de zoom du fond a l'instant t."""
    if project["animation"]["background"] != "zoom_slow":
        return 1.0
    dur = max(duration(project), 1e-6)
    ratio = min(1.0, max(0.0, t / dur))
    return 1.0 + (ZOOM_MAX - 1.0) * ratio
