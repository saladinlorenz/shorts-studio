"""Resolution deterministe d'un projet -> projet resolu inspectable.

Le projet edite (Design) ou la ligne importee (Production) sont normalises ici
en un projet resolu : chaque scene et chaque calque recoit des FRAMES
ABSOLUES, les ressources sont inventoriees, la reference et la version du
modele ainsi que la graine sont figees.

Regles :
- aucune valeur aleatoire : meme projet en entree -> meme projet resollu en
  sortie (la graine est conservee, jamais reimprovisee) ;
- le rendu Remotion lit le bloc ``resolved`` : l'aperçu et l'export partagent
  donc le meme calcul de chronologie, sans timer independant ;
- le bloc ``resolved`` est regenerable et ecarte a chaque re-resolution.
"""
from __future__ import annotations

from . import effects as effects_mod
from . import fonts as fonts_mod
from . import schema
from .schema import SCHEMA_VERSION_V2

RESOLVED_KEY = "resolved"


def _clamp01(value) -> float:
    """Volume normalise 0..1 : une valeur hors bornes ne casse pas le rendu."""
    try:
        return round(min(max(float(value), 0.0), 1.0), 3)
    except (TypeError, ValueError):
        return 0.0


def _strip_resolved(project: dict) -> dict:
    out = {k: v for k, v in project.items() if k != RESOLVED_KEY}
    content = dict(out.get("content", {}))
    scenes = []
    for sc in content.get("scenes", []):
        clean = {k: v for k, v in sc.items() if k != RESOLVED_KEY}
        scenes.append(clean)
    content["scenes"] = scenes
    out["content"] = content
    return out


def _layer_window(fps: int, scene_start: int, scene_frames: int, layer: dict) -> dict:
    anim = layer.get("animation", {})
    start = scene_start + int(anim.get("start_frames", 0) or 0)
    in_frames = int(anim.get("in_frames", 0) or 0)
    out_frames = int(anim.get("out_frames", 0) or 0) if anim.get("out", "none") != "none" else 0
    stagger = max(0, int(anim.get("stagger_frames", 0) or 0))
    unit = anim.get("unit", "block")
    if unit == "word":
        units = max(1, len([w for w in str(layer.get("text", "")).split() if w]))
    elif unit == "line":
        units = max(1, len([l for l in str(layer.get("text", "")).split("\n") if l.strip()]))
    else:
        units = 1
    spread = (units - 1) * stagger
    end = scene_start + scene_frames - out_frames
    return {
        "id": layer.get("id", ""),
        "type": layer.get("type", "text"),
        "start_frame": start,
        "in_end_frame": start + max(1, in_frames),
        "spread_frames": spread,
        "units": units,
        "out_start_frame": end - out_frames if out_frames else end,
        "end_frame": end,
        "hold_frames": max(0, (end - out_frames) - (start + max(1, in_frames) + spread)),
        "duration_frames": max(0, end - start),
    }


def resolve(project: dict) -> dict:
    """Projet edite -> projet resollu (frames absolues, ressources, graine)."""
    base = schema.clone(_strip_resolved(project))
    if base.get("version") != SCHEMA_VERSION_V2:
        raise RuntimeError(
            f"Resolution attendue la version {SCHEMA_VERSION_V2}, recue {base.get('version')!r}."
        )

    export = base.setdefault("export", {})
    fps = int(export.get("fps", 30) or 30)
    width = int(export.get("width", 1080) or 1080)
    height = int(export.get("height", 1920) or 1920)
    scale = height / schema.REF_HEIGHT

    content = base.setdefault("content", {})
    scenes = content.get("scenes", [])
    signature = content.setdefault("signature", schema.default_signature())

    resolved_scenes: list[dict] = []
    assets: list[dict] = []
    font_ids: set[str] = set()
    cursor = 0

    theme_family = str(base.get("theme", {}).get("font_family", ""))
    if theme_family:
        font_ids.add(theme_family)

    # Les effets sont normalises ici : le rendu ne recoit que des reglages
    # completes et dans les bornes, jamais un objet livre par l'editeur ou par
    # l'assistant. Les erreurs reviennent a la validation, qui bloque avant.
    audio_cfg = base.get("audio", {}) or {}
    audio_ready = bool(audio_cfg.get("enabled")) and bool(
        str(audio_cfg.get("music", "") or "") or str(audio_cfg.get("voice", "") or "")
    )

    for sc in scenes:
        scene_frames = max(1, int(round(float(sc.get("duration", 0.0)) * fps)))
        bg = sc.get("background", {})
        bg_media = str(bg.get("media", "") or "")
        scene_effects, _fx_errors, _fx_warnings = effects_mod.normalize(
            sc.get("effects"), "scene", "scene", path="scene.effects", audio_ready=audio_ready
        )
        layers_resolved = []
        for layer in sc.get("layers", []):
            style = {**base.get("theme", {}), **layer.get("style", {})}
            family = str(style.get("font_family", theme_family))
            if family:
                font_ids.add(family)
            window = _layer_window(fps, cursor, scene_frames, layer)
            layer_effects, _e, _w = effects_mod.normalize(
                layer.get("effects"),
                "layer",
                layer.get("type") if layer.get("type") in ("text", "image") else "text",
                path="calque.effects",
                audio_ready=audio_ready,
            )
            if layer.get("type") == "image":
                media = str(layer.get("media", "") or "")
                if media:
                    assets.append({"kind": "image", "ref": media, "scene": sc.get("id", "")})
            layers_resolved.append(
                {
                    **window,
                    "effects": layer_effects[: effects_mod.MAX_EFFECTS_PER_TARGET],
                    "align": layer.get("position", {}).get("align", "center"),
                    "direction": layer.get("position", {}).get("direction", "ltr"),
                    "font_family": family,
                    "font_weight": int(style.get("font_weight", 400) or 400),
                    "font_size_px": round(float(style.get("font_size", 72)) * scale, 1),
                    "line_height": float(style.get("line_height", 1.2)),
                    "letter_spacing_em": float(style.get("letter_spacing", 0.0) or 0.0),
                    "color": str(style.get("color", style.get("text_color", "#FFFFFF"))),
                    "accent_color": str(style.get("accent_color", "#E2B458")),
                    "shadow": bool(style.get("shadow", False)),
                    "stroke_width_px": round(float(layer.get("style", {}).get("stroke_width", 0) or 0) * scale, 1),
                    "stroke_color": str(layer.get("style", {}).get("stroke_color", "#000000")),
                }
            )
        if bg_media:
            assets.append({"kind": "background", "ref": bg_media, "scene": sc.get("id", "")})
        resolved_scenes.append(
            {
                "id": sc.get("id", ""),
                "label": sc.get("label", ""),
                "start_frame": cursor,
                "duration_frames": scene_frames,
                "end_frame": cursor + scene_frames,
                "hidden": bool(sc.get("hidden", False)),
                "effects": scene_effects[: effects_mod.MAX_EFFECTS_PER_TARGET],
                "background": {
                    "media": bg_media,
                    "fit": bg.get("fit", "cover"),
                    "animation": bg.get("animation", "static"),
                },
                "layers": layers_resolved,
            }
        )
        cursor += scene_frames

    sig_media = str(signature.get("media", "") or "")
    if sig_media:
        assets.append({"kind": "signature", "ref": sig_media, "scene": "*"})
    signature_resolved = {
        **schema.clone(signature),
        "start_frame": int(signature.get("start_frames", 0) or 0),
        "in_frames": int(signature.get("in_frames", 0) or 0),
        "font_size_px": round(float(signature.get("font_size", 34)) * scale, 1),
        "logo_width_px": round(float(signature.get("logo_width", 0.14)) * width, 1),
        "end_frame": cursor,
    }
    font_ids.add(str(signature.get("font_family", "")))

    known = fonts_mod.family_ids()
    fonts_resolved = []
    for family in sorted(f for f in font_ids if f):
        weights = fonts_mod.weights_of(family)
        fonts_resolved.append(
            {
                "id": family,
                "known": family in known,
                "weights": weights,
            }
        )

    # Audio : la piste est resolue comme le reste (frames, bornes, refs). Une
    # piste plus courte que la video est bouclee par la composition, jamais
    # ralent ni accelerate.
    audio = base.get("audio", {}) or {}
    music = str(audio.get("music", "") or "")
    voice = str(audio.get("voice", "") or "")
    if music:
        assets.append({"kind": "music", "ref": music, "scene": "*"})
    if voice:
        assets.append({"kind": "voice", "ref": voice, "scene": "*"})
    total_seconds = round(cursor / fps, 3) if fps else 0.0
    audio_resolved = {
        "enabled": bool(audio.get("enabled", False)) and bool(music or voice),
        "music": music,
        "voice": voice,
        "music_volume": _clamp01(audio.get("music_volume", 0.3)),
        "voice_volume": _clamp01(audio.get("voice_volume", 1.0)),
        "music_fade_in": round(min(max(float(audio.get("music_fade_in", 1.0) or 0.0), 0.0), total_seconds), 3),
        "music_fade_out": round(min(max(float(audio.get("music_fade_out", 1.5) or 0.0), 0.0), total_seconds), 3),
        "start_frame": 0,
        "end_frame": cursor,
        "total_frames": cursor,
        "fps": fps,
        "duration": total_seconds,
    }

    base[RESOLVED_KEY] = {
        "model": {
            "id": base.get("model", {}).get("id", "quote_cinematic"),
            "version": int(base.get("model", {}).get("version", schema.MODELS.get("quote_cinematic", 1))),
        },
        "fps": fps,
        "width": width,
        "height": height,
        "scale": round(scale, 4),
        "total_frames": cursor,
        "duration": round(cursor / fps, 3) if fps else 0.0,
        "scenes": resolved_scenes,
        "signature": signature_resolved,
        "assets": assets,
        "fonts": fonts_resolved,
        "audio": audio_resolved,
        "seed": int(base.get("variation", {}).get("seed", 1) or 1),
    }
    return base


def composition_id(project: dict) -> str:
    """Identifiant Remotion de la composition : vient du projet resolllu."""
    resolved = project.get(RESOLVED_KEY) or {}
    model_id = resolved.get("model", {}).get("id") or project.get("model", {}).get("id", "")
    if model_id not in schema.MODELS:
        raise RuntimeError(
            f"Modele inconnu pour le rendu : {model_id!r} (connus : {', '.join(schema.MODELS)})."
        )
    return str(model_id)
