"""Projet v2 genere depuis un moment detecte : le clip EST le moment, pas une reecriture.

Trois lois commandent ce module :

1. frame 0 de la composition = instant de depart du moment. La piste vocale est
   l'extrait reel decoupe dans la source (``audio.voice``) et ``resolve()`` la fait
   demarrer a 0 : une scene d'introduction deplacerait la voix de quelques dixiemes
   et le clip parlerait faux.
2. un sous-titre = une scene. ``resolve()`` clot la fenetre d'un calque sur la fin de sa
   scene : la scene s'etend donc jusqu'au debut du cue suivant et le calque porte un
   fondu de sortie egal au silence mesure entre les deux. Le .sRT re-derive retrouve
   alors les bornes de l'ASR a la frame pres, sans un centieme invente.
3. rien d'invente. Le texte vient de la transcription, le titre est une citation du
   moment, les hashtags des mots du moment. Le branding n'entre que si un pack est
   passe explicitement : l'assistant propose, l'utilisateur applique.
"""
from __future__ import annotations

import re

from . import branding, moments, schema, validation


DEFAULT_FPS = 30
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
CAPTION_Y = 0.80
CAPTION_WIDTH = 0.90
CAPTION_FONT_SIZE = 62
CAPTION_LINE_HEIGHT = 1.14
MAX_TITLE_SLUG = 42


class MomentProjectError(RuntimeError):
    """Le moment ne peut pas devenir un projet : donnees insuffisantes ou incoherentes."""


def caption_timeline(cues, fps: int, *, end_seconds: float | None = None,
                     min_scene_seconds: float = schema.SCENE_DURATION_MIN) -> tuple[list[dict], int]:
    """Cues ASR -> scenes qui carrelent la timeline, plus la duree totale en frames.

    Le sous-titre doit coller a la voix, or ``resolve()`` ne connait que deux bornes :
    ``scene_start + start_frames`` et ``fin de scene - out_frames``. D'ou la construction :

    - la scene N commence a l'instant ou le cue N commence (scene 0 = frame 0 de la
      composition = instant de depart du moment, sinon la piste vocale serait decalee
      par rapport a l'image des la premiere scene) ;
    - le calque porte ``out_frames`` = silence mesure jusqu'au cue suivant : sa fenetre
      resolue se clot exactement a la fin du segment ASR, pas a la fin de la scene.

    Retourne ``(specs, total_frames)`` ou chaque spec a ``scene_start`` / ``scene_end`` /
    ``cue_start`` / ``cue_end`` / ``text`` en frames absolues de la composition.
    """
    min_frames = max(1, int(round(min_scene_seconds * fps)))
    windows: list[dict] = []
    for cue in cues or []:
        if not isinstance(cue, dict):
            continue
        text = re.sub(r"\s+", " ", str(cue.get("text") or "")).strip()
        if not text:
            continue
        start = max(0.0, float(cue.get("start") or 0.0))
        end = max(start, float(cue.get("end") or start))
        start_frame = int(round(start * fps))
        end_frame = int(round(end * fps))
        if windows and start_frame < windows[-1]["cue_end"]:
            # deux segments qui se chevauchent : le second commence a la fin du premier
            start_frame = windows[-1]["cue_end"]
        windows.append({
            "cue_start": start_frame,
            "cue_end": max(end_frame, start_frame + 1),
            "text": text,
            "raw_start": cue.get("raw_start", round(start, 3)),
            "raw_end": cue.get("raw_end", round(end, 3)),
        })
    if not windows:
        return [], 0

    # une scene de 0,3 s est refusee par le format : le cue trop proche du precedent
    # est fondu avec lui. Les bornes exterieures restent celles de l'ASR.
    merged = [windows[0]]
    for window in windows[1:]:
        if window["cue_start"] - merged[-1]["cue_start"] < min_frames:
            _join(merged[-1], window)
        else:
            merged.append(window)

    tail = int(round(float(end_seconds) * fps)) if end_seconds is not None else merged[-1]["cue_end"]
    total = max(tail, merged[-1]["cue_end"], merged[-1]["cue_start"] + min_frames)

    specs: list[dict] = []
    for index, item in enumerate(merged):
        scene_end = merged[index + 1]["cue_start"] if index + 1 < len(merged) else total
        specs.append({**item, "scene_start": 0 if index == 0 else item["cue_start"],
                      "scene_end": max(scene_end, item["cue_start"] + min_frames)})
    return specs, total


def _join(previous: dict, window: dict) -> None:
    previous["cue_end"] = max(previous["cue_end"], window["cue_end"])
    previous["raw_end"] = window["raw_end"]
    previous["text"] = moments.wrap_caption(f"{previous['text']} {window['text']}")


def _caption_animation(available: int, out_frames: int, words: int) -> dict:
    """Entree du calque : mot par mot quand la place le permet, en bloc sinon.

    La sortie est un fondu quand un silence est reellement mesure jusqu'au cue suivant :
    il materialise la fin du segment ASR. « none » quand scene et sous-titre tombent sur
    le meme frame, pour ne pas rogner la derniere seconde legendee.
    """
    room = max(1, available - out_frames)
    in_frames = max(1, min(6, room - 2))
    if room >= 24 and words >= 3 and in_frames + (words - 1) * 3 < room:
        stagger = max(1, min(3, int(room * 0.35 / max(1, words - 1))))
        return {"in": "fade", "out": "fade" if out_frames else "none", "unit": "word",
                "in_frames": in_frames, "stagger_frames": stagger, "out_frames": out_frames,
                "easing": "ease_out_cubic"}
    return {"in": "fade", "out": "fade" if out_frames else "none", "unit": "block",
            "in_frames": in_frames, "stagger_frames": 0, "out_frames": out_frames,
            "easing": "ease_out_cubic"}


def scenes_from_specs(specs: list[dict], fps: int, *, background_media: str = "") -> list[dict]:
    """Une scene par sous-titre, avec le calque de legende qui porte le texte."""
    scenes: list[dict] = []
    for index, spec in enumerate(specs, start=1):
        scene_frames = spec["scene_end"] - spec["scene_start"]
        start_frames = spec["cue_start"] - spec["scene_start"]
        out_frames = spec["scene_end"] - spec["cue_end"]
        words = len(spec["text"].split())
        layer = schema.text_layer(
            f"cue-{index}",
            spec["text"],
            role="caption",
            start_frames=start_frames,
            position={"x": 0.5, "y": CAPTION_Y, "width": CAPTION_WIDTH, "align": "center"},
            style={"font_size": CAPTION_FONT_SIZE,
                   "line_height": CAPTION_LINE_HEIGHT,
                   "letter_spacing": 0.005},
            animation=_caption_animation(scene_frames - start_frames, max(0, out_frames), words),
        )
        scenes.append(
            schema.scene(f"cue-{index:02d}", f"Sous-titre {index}", scene_frames / fps, [layer],
                         media=background_media)
        )
    return scenes


def project_name(moment: dict, title: str) -> str:
    position = int(moment.get("position") or 1)
    slug = moments.ascii_slug(title) or str(moment.get("id") or "moment")
    return f"moment-{position:02d}-{slug[:MAX_TITLE_SLUG]}"


def generate(moment: dict, *, pack: dict | None = None, voice_ref: str = "",
             thumbnail_ref: str = "", source: dict | None = None, fps: int = DEFAULT_FPS,
             width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
             model_id: str = "quote_cinematic", handle: str = "", brand_label: str = "",
             source_title: str = "", background_media: str = "") -> dict:
    """Moment detecte -> projet v2 complet, resoluble, valide et livre avec ses donnees.

    Retourne ``{"project", "name", "errors", "warnings", "start", "end", "duration",
    "cues", "timeline"}`` : les temps en secondes sont ceux reellement couverts par la
    composition, ce qui sert a decouper la piste vocale et a regler la miniature.
    """
    if not isinstance(moment, dict):
        raise MomentProjectError("Moment attendu : objet JSON issu de moments.detect().")
    fps = max(1, int(fps or DEFAULT_FPS))
    if model_id not in schema.MODELS:
        raise MomentProjectError(
            f"Modele inconnu : {model_id!r} (connus : {', '.join(schema.MODELS)})."
        )

    specs, total_frames = caption_timeline(moment.get("cues"), fps,
                                           end_seconds=float(moment.get("duration") or 0.0))
    if not specs:
        raise MomentProjectError(
            "Ce moment ne contient aucun sous-titre : rien a generer. "
            "Relancez la transcription ou choisissez un autre passage."
        )
    scenes = scenes_from_specs(specs, fps, background_media=background_media)

    duration = round(total_frames / fps, 3)
    start = round(float(moment.get("start") or 0.0), 3)
    end = round(start + duration, 3)

    title = moments.title_from(moment, brand_label=brand_label)
    signature = schema.default_signature()
    if handle:
        signature["handle"] = handle if handle.startswith("@") else f"@{handle}"

    audio = {
        "music": "",
        "voice": voice_ref,
        "music_volume": 0.3,
        "voice_volume": 1.0,
        "music_fade_in": 1.0,
        "music_fade_out": 1.5,
        "markers": [],
        "enabled": bool(voice_ref),
    }

    project = {
        "version": schema.SCHEMA_VERSION_V2,
        "model": {"id": model_id, "version": schema.MODELS[model_id]},
        "name": project_name(moment, title),
        "content": {"scenes": scenes, "signature": signature},
        "theme": schema.default_theme(),
        "audio": audio,
        "variation": {"seed": 1},
        "export": {"width": int(width), "height": int(height), "fps": fps,
                   "output_dir": "", "filename": ""},
        "publish": {
            **moments.metadata_from(moment, source_title=source_title, handle=handle,
                                    brand_label=brand_label),
            "moment_id": moment.get("id", ""),
            "start": start,
            "end": end,
            "duration": duration,
            "title": title,
            "voice": voice_ref,
            "thumbnail": thumbnail_ref,
            "background": background_media,
            "scene_count": len(scenes),
            "source": {
                "path": str((source or {}).get("path") or ""),
                "title": source_title or str((source or {}).get("title") or ""),
                "duration": float((source or {}).get("duration") or 0.0),
            },
        },
    }

    warnings: list[str] = []
    if pack:
        project, brand_warnings = branding.apply_brand(project, pack)
        warnings.extend(brand_warnings)

    errors, validation_warnings = validation.validate_project_v2(project)
    warnings.extend(validation_warnings)
    if not (project.get("audio") or {}).get("enabled"):
        warnings.append(
            "Piste vocale absente : le clip sera muet. Renseignez la source audio pour "
            "que l'extrait soit importe."
        )
    return {
        "project": project,
        "name": project["name"],
        "errors": errors,
        "warnings": warnings,
        "start": start,
        "end": end,
        "duration": duration,
        "cues": len(scenes),
        "timeline": specs,
    }
