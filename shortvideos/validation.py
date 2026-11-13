"""Validation des projets Short Videos.

Retourne deux listes :
- errors   : problemes bloquants (fichiers manquants, valeurs hors bornes)
- warnings : problemes non bloquants (texte long, chevauchement de fondus)

Le rendu des avertissements de texte long utilise les memes calculs que
la composition (render.measure_text) pour rester coherent.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import schema
from . import effects as effects_mod
from . import fonts as fonts_mod
from .project import BACKGROUND_EFFECTS, SCHEMA_VERSION, SUPPORTED_TEMPLATES, TEXT_EFFECTS
from .schema import SCHEMA_VERSION_V2

# Un texte de plus de ces caracteres est signale comme long.
LONG_TEXT_CHARS = 220

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# Polices proposees : fichiers Windows standard + fallback.
FONTS_DIR = Path(r"C:\Windows\Fonts")
FALLBACK_FONT = "arialbd.ttf"


def _check_num(errors, warnings, section, key, value, lo, hi, integer=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{section}.{key} doit etre un nombre (valeur : {value!r}).")
        return None
    if integer and (float(value) != int(value)):
        errors.append(f"{section}.{key} doit etre un entier (valeur : {value!r}).")
        return None
    if value < lo or value > hi:
        errors.append(f"{section}.{key} doit etre entre {lo} et {hi} (valeur : {value}).")
    return value


def _check_color(errors, section, key, value):
    if not isinstance(value, str) or not _HEX_COLOR.match(value):
        errors.append(f"{section}.{key} doit etre une couleur au format #RRGGBB (valeur : {value!r}).")


def _check_path(errors, section, key, value, label, required=False):
    """Verifie un chemin de fichier. Espaces acceptes. Absence = erreur claire."""
    if not isinstance(value, str):
        errors.append(f"{section}.{key} doit etre un chemin texte (valeur : {value!r}).")
        return
    if not value.strip():
        if required:
            errors.append(f"{label} : aucun fichier selectionne.")
        return
    p = Path(value)
    if not p.exists():
        errors.append(f"{label} introuvable : {value}")
    elif not p.is_file():
        errors.append(f"{label} n'est pas un fichier : {value}")


def validate_project(data: dict) -> tuple[list[str], list[str]]:
    """Valide un projet (v1 herite ou v2 studio). Retourne (errors, warnings)."""
    if isinstance(data, dict) and data.get("version") == SCHEMA_VERSION_V2:
        return validate_project_v2(data)
    return _validate_v1(data)


def _validate_v1(data: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return (["Le projet doit etre un objet JSON."], warnings)

    version = data.get("version")
    if version != SCHEMA_VERSION:
        errors.append(
            f"Version de projet non prise en charge : {version!r} "
            f"(attendu : {SCHEMA_VERSION})."
        )
        return (errors, warnings)

    # --- Template ---
    template = data.get("template")
    if template not in SUPPORTED_TEMPLATES:
        errors.append(
            f"Template inconnu : {template!r} (supporte : {', '.join(SUPPORTED_TEMPLATES)})."
        )

    # --- Sections obligatoires ---
    for section in ("content", "theme", "position", "timing", "animation", "export"):
        if not isinstance(data.get(section), dict):
            errors.append(f"Section manquante ou invalide : {section}")
    if errors:
        return (errors, warnings)

    content = data["content"]
    theme = data["theme"]
    position = data["position"]
    timing = data["timing"]
    animation = data["animation"]
    export = data["export"]

    # --- Contenu ---
    text = content.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append("content.text : la citation ne peut pas etre vide.")
    else:
        if len(text) > LONG_TEXT_CHARS:
            warnings.append(
                f"Texte long ({len(text)} caracteres, seuil {LONG_TEXT_CHARS}) : "
                "risque de debordement dans le cadre vertical."
            )
        try:
            from . import render as _render

            m = _render.measure_text(data)
            if not m["fits"]:
                warnings.append(
                    f"Le texte deborde : {m['lines']} lignes estimees "
                    f"(hauteur {m['block_height']} px pour {m['available_height']} px "
                    "disponibles). Reduisez la taille de police ou le texte."
                )
        except Exception as e:  # police indisponible : signale mais ne bloque pas ici
            warnings.append(f"Impossible de mesurer le texte : {e}")

    _check_path(errors, "content", "background_image", content.get("background_image", ""),
                "L'image de fond", required=True)
    _check_path(errors, "content", "logo", content.get("logo", ""), "Le logo")

    # --- Theme ---
    font_family = theme.get("font_family")
    if not isinstance(font_family, str) or not font_family.strip():
        errors.append("theme.font_family : police absente.")
    else:
        candidate = FONTS_DIR / font_family
        if not candidate.exists() and not Path(font_family).exists():
            errors.append(f"Police introuvable : {font_family} (ni dans {FONTS_DIR}).")

    _check_num(errors, warnings, "theme", "font_size", theme.get("font_size"), 8, 400)
    for key in ("text_color", "author_color", "accent_color"):
        _check_color(errors, "theme", key, theme.get(key))

    # --- Position (coordonnees normalisees 0..1) ---
    for key in ("x", "y", "width"):
        _check_num(errors, warnings, "position", key, position.get(key), 0.0, 1.0)

    # --- Timing ---
    duration = _check_num(errors, warnings, "timing", "duration", timing.get("duration"), 0.5, 300.0)
    text_start = _check_num(errors, warnings, "timing", "text_start", timing.get("text_start"), 0.0, 300.0)
    fade_in = _check_num(errors, warnings, "timing", "fade_in", timing.get("fade_in"), 0.0, 60.0)
    fade_out = _check_num(errors, warnings, "timing", "fade_out", timing.get("fade_out"), 0.0, 60.0)

    if all(isinstance(v, (int, float)) for v in (duration, text_start, fade_in, fade_out)):
        if text_start >= duration:
            errors.append(
                f"Le texte commence apres la fin de la scene "
                f"({text_start} s >= {duration} s)."
            )
        if text_start + fade_in >= duration:
            warnings.append(
                "Le fondu d'entree se termine apres la fin de la scene : "
                "le texte n'atteindra jamais 100 % d'opacite."
            )
        if fade_out > duration:
            warnings.append("Le fondu de sortie est plus long que la scene.")

    # --- Animation ---
    if animation.get("text_in") not in TEXT_EFFECTS:
        errors.append(
            f"animation.text_in inconnu : {animation.get('text_in')!r} "
            f"(supporte : {', '.join(TEXT_EFFECTS)})."
        )
    if animation.get("background") not in BACKGROUND_EFFECTS:
        errors.append(
            f"animation.background inconnu : {animation.get('background')!r} "
            f"(supporte : {', '.join(BACKGROUND_EFFECTS)})."
        )

    # --- Export ---
    _check_num(errors, warnings, "export", "width", export.get("width"), 16, 7680, integer=True)
    _check_num(errors, warnings, "export", "height", export.get("height"), 16, 7680, integer=True)
    _check_num(errors, warnings, "export", "fps", export.get("fps"), 1, 120, integer=True)

    w = export.get("width")
    h = export.get("height")
    if isinstance(w, int) and isinstance(h, int):
        if w % 2 or h % 2:
            errors.append(
                f"Les dimensions doivent etre paires pour H.264 (width={w}, height={h})."
            )

    return (errors, warnings)


# --- Version 2 (studio : scenes, calques, animations, signature) ------------

MEDIA_STORE = Path(__file__).resolve().parents[1] / "media"
V2_LAYER_TYPES = ("text", "image")
MAX_LAYER_CHARS = 260


def _media_exists(ref: str) -> bool:
    if ref.startswith("media://"):
        media_id = ref[len("media://"):].strip()
        return bool(list(MEDIA_STORE.glob(f"{media_id}.*")))
    return False


def _check_font(errors, warnings, label, family, weight=None):
    if not isinstance(family, str) or not family.strip():
        errors.append(f"{label} : aucune police selectionnee.")
        return
    if not fonts_mod.known_family(family):
        errors.append(
            f"{label} : police {family!r} absente du catalogue sous licence. "
            "Choisissez une police fournie par le studio."
        )
        return
    if weight is not None:
        available = fonts_mod.weights_of(family)
        if available and weight not in available:
            warnings.append(
                f"{label} : poids {weight} declare pour {family} "
                f"(poids disponibles : {', '.join(str(w) for w in available)})."
            )


def validate_project_v2(data: dict) -> tuple[list[str], list[str]]:
    """Validation d'un projet v2. Erreurs = bloquantes, avertissements = signales."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return (["Le projet doit etre un objet JSON."], warnings)

    model = data.get("model")
    model_id = model.get("id") if isinstance(model, dict) else model
    if model_id not in schema.MODELS:
        errors.append(
            f"model.id inconnu : {model_id!r} (connus : {', '.join(schema.MODELS)})."
        )

    content = data.get("content")
    theme = data.get("theme")
    export = data.get("export")
    if not isinstance(content, dict):
        errors.append("Section manquante ou invalide : content")
        return (errors, warnings)
    if not isinstance(theme, dict):
        errors.append("Section manquante ou invalide : theme")
    scenes = content.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append("content.scenes : au moins une scene est requise.")
        return (errors, warnings)

    fps = 30
    if isinstance(export, dict):
        _check_num(errors, warnings, "export", "width", export.get("width", 1080), 16, 7680, integer=True)
        _check_num(errors, warnings, "export", "height", export.get("height", 1920), 16, 7680, integer=True)
        fps_val = _check_num(errors, warnings, "export", "fps", export.get("fps", 30), 1, 120, integer=True)
        if isinstance(fps_val, (int, float)):
            fps = int(fps_val)
        w = export.get("width")
        h = export.get("height")
        if isinstance(w, int) and isinstance(h, int) and (w % 2 or h % 2):
            errors.append(f"Dimensions paires exigees pour H.264 (width={w}, height={h}).")
    else:
        errors.append("Section manquante ou invalide : export")

    if isinstance(theme, dict):
        _check_font(errors, warnings, "theme.font_family", theme.get("font_family"), theme.get("font_weight"))
        for key in ("text_color", "author_color", "accent_color", "muted_color", "background_color", "surface_color"):
            if key in theme:
                _check_color(errors, "theme", key, theme.get(key))
        _check_num(errors, warnings, "theme", "font_size", theme.get("font_size", 84), 8, 400)

    total = 0.0
    # Les effets reactifs mesurent la vraie piste : sans audio actif, ils sont
    # signales (avertissement) plutot que refuses, car le rendu reste legitime.
    audio_cfg = data.get("audio") if isinstance(data.get("audio"), dict) else {}
    audio_ready = bool(audio_cfg.get("enabled")) and bool(
        str(audio_cfg.get("music", "") or "") or str(audio_cfg.get("voice", "") or "")
    )
    seen_scene_ids: set[str] = set()
    for index, sc in enumerate(scenes):
        tag = f"scene[{index}]"
        if not isinstance(sc, dict):
            errors.append(f"{tag} : objet attendu.")
            continue
        scene_id = str(sc.get("id", "") or "")
        if not scene_id:
            errors.append(f"{tag} : identifiant de scene vide.")
        elif scene_id in seen_scene_ids:
            errors.append(f"{tag} : identifiant de scene duplique : {scene_id}")
        seen_scene_ids.add(scene_id)

        duration = _check_num(errors, warnings, tag, "duration", sc.get("duration"), schema.SCENE_DURATION_MIN, schema.SCENE_DURATION_MAX)
        if isinstance(duration, (int, float)):
            total += float(duration)
        scene_frames = int(round(float(duration or 0) * fps))

        bg = sc.get("background", {})
        if not isinstance(bg, dict):
            errors.append(f"{tag}.background : objet attendu.")
            bg = {}
        if bg.get("fit") not in schema.BACKGROUND_FIT:
            errors.append(f"{tag}.background.fit inconnu : {bg.get('fit')!r}.")
        if bg.get("animation") not in schema.BACKGROUND_ANIM:
            errors.append(f"{tag}.background.animation inconnue : {bg.get('animation')!r}.")
        bg_media = str(bg.get("media", "") or "")
        if bg_media and not bg_media.startswith("media://"):
            errors.append(
                f"{tag}.background.media : chemin Windows interdit dans un projet ({bg_media!r}). "
                "Reimportez le media depuis l'onglet."
            )
        elif bg_media and not _media_exists(bg_media):
            errors.append(f"{tag}.background : media manquant ({bg_media}).")

        trans = sc.get("transition")
        if trans is not None:
            if not isinstance(trans, dict):
                errors.append(f"{tag}.transition : objet attendu ({{type, frames}}).")
            else:
                ttype = trans.get("type", "none")
                if ttype not in schema.TRANSITION_TYPES:
                    errors.append(
                        f"{tag}.transition.type inconnu : {ttype!r} "
                        f"(connus : {', '.join(schema.TRANSITION_TYPES)})."
                    )
                tframes = _check_num(errors, warnings, tag, "transition.frames",
                                     trans.get("frames", 0), 0, schema.TRANSITION_FRAMES_MAX, integer=True)
                if isinstance(tframes, (int, float)):
                    if tframes > scene_frames:
                        errors.append(
                            f"{tag}.transition.frames ({int(tframes)}) depasse la duree de la scene "
                            f"({scene_frames} frames)."
                        )
                    if ttype == "none" and tframes:
                        warnings.append(f"{tag}.transition : type « none » avec frames={int(tframes)} ; ignoree.")
                    if index == 0 and ttype != "none":
                        warnings.append(f"{tag}.transition : premiere scene, pas de transition d'entree possible.")

        _scene_effects, fx_errors, fx_warnings = effects_mod.normalize(
            sc.get("effects"),
            "scene",
            "scene",
            path=f"{tag}.effects",
            audio_ready=audio_ready,
        )
        errors.extend(fx_errors)
        warnings.extend(fx_warnings)

        layers = sc.get("layers")
        if not isinstance(layers, list) or not layers:
            warnings.append(f"{tag} : scene sans calque.")
            continue
        seen_layer_ids: set[str] = set()
        for li, layer in enumerate(layers):
            ltag = f"{tag}.calque[{li}]"
            if not isinstance(layer, dict):
                errors.append(f"{ltag} : objet attendu.")
                continue
            lid = str(layer.get("id", "") or "")
            if lid in seen_layer_ids:
                errors.append(f"{ltag} : identifiant duplique dans la scene : {lid}")
            seen_layer_ids.add(lid)
            if layer.get("type") not in V2_LAYER_TYPES:
                errors.append(f"{ltag}.type inconnu : {layer.get('type')!r}.")
            if layer.get("hidden") or layer.get("locked"):
                continue

            position = layer.get("position", {})
            for key in ("x", "y", "width"):
                _check_num(errors, warnings, ltag, f"position.{key}", position.get(key, 0.5), 0.0, 1.0)
            if position.get("align") not in schema.ALIGNMENTS:
                errors.append(f"{ltag}.position.align inconnu : {position.get('align')!r}.")
            if position.get("direction") not in schema.DIRECTIONS:
                errors.append(f"{ltag}.position.direction inconnu : {position.get('direction')!r}.")

            style = layer.get("style", {})
            if style.get("font_family") is not None:
                _check_font(errors, warnings, ltag, style.get("font_family"), style.get("font_weight"))
            for key in ("color", "accent_color", "stroke_color"):
                if key in style:
                    _check_color(errors, ltag, key, style.get(key))
            if "font_size" in style:
                _check_num(errors, warnings, ltag, "font_size", style.get("font_size"), 8, 400)

            anim = layer.get("animation", {})
            if anim.get("in") not in schema.ANIM_IN:
                errors.append(f"{ltag}.animation.in inconnu : {anim.get('in')!r}.")
            if anim.get("out") not in schema.ANIM_OUT:
                errors.append(f"{ltag}.animation.out inconnu : {anim.get('out')!r}.")
            if anim.get("unit") not in schema.ANIM_UNITS:
                errors.append(f"{ltag}.animation.unit inconnu : {anim.get('unit')!r}.")
            if anim.get("easing") not in schema.EASINGS:
                errors.append(f"{ltag}.animation.easing inconnu : {anim.get('easing')!r}.")
            start = _check_num(errors, warnings, ltag, "animation.start_frames", anim.get("start_frames", 0), 0, 18000, integer=True)
            in_f = _check_num(errors, warnings, ltag, "animation.in_frames", anim.get("in_frames", 1), 0, 18000, integer=True)
            out_f = _check_num(errors, warnings, ltag, "animation.out_frames", anim.get("out_frames", 0), 0, 18000, integer=True)
            stagger = _check_num(errors, warnings, ltag, "animation.stagger_frames", anim.get("stagger_frames", 0), 0, 600, integer=True)
            if None not in (start, in_f, out_f, stagger):
                units = 1
                text_value = str(layer.get("text", ""))
                if anim.get("unit") == "word":
                    units = max(1, len(text_value.split()))
                elif anim.get("unit") == "line":
                    units = max(1, len([ln for ln in text_value.split("\n") if ln.strip()]))
                spread = (units - 1) * int(stagger)
                if int(start) >= scene_frames:
                    errors.append(
                        f"{ltag} : le calque debute apres la fin de sa scene "
                        f"({int(start)} frames >= {scene_frames} frames)."
                    )
                elif int(start) + int(in_f) > scene_frames:
                    warnings.append(
                        f"{ltag} : l'entree se termine apres la fin de la scene ; "
                        "le calque n'atteindra pas son etat final."
                    )
                if int(out_f) and int(start) + int(in_f) + spread >= scene_frames - int(out_f):
                    warnings.append(f"{ltag} : maintien nul : entree + decalage atteint la sortie.")

            _, fx_errors, fx_warnings = effects_mod.normalize(
                layer.get("effects"),
                "layer",
                layer.get("type") if layer.get("type") in ("text", "image") else "text",
                path=f"{ltag}.effects",
                audio_ready=audio_ready,
            )
            errors.extend(fx_errors)
            warnings.extend(fx_warnings)

            if layer.get("type") == "text":
                text = layer.get("text")
                if not isinstance(text, str) or not text.strip():
                    errors.append(f"{ltag}.text : texte vide.")
                elif len(text) > MAX_LAYER_CHARS:
                    warnings.append(
                        f"{ltag} : texte long ({len(text)} caracteres) ; verifiez le debordement dans l'aperçu."
                    )
            if layer.get("type") == "image":
                media = str(layer.get("media", "") or "")
                if not media:
                    errors.append(f"{ltag} : aucun media selectionne.")
                elif not media.startswith("media://"):
                    errors.append(f"{ltag} : chemin Windows interdit dans un projet ({media!r}).")
                elif not _media_exists(media):
                    errors.append(f"{ltag} : media manquant ({media}).")

    if total < schema.TOTAL_DURATION_MIN or total > schema.TOTAL_DURATION_MAX:
        errors.append(
            f"Duree totale hors bornes : {round(total, 2)} s "
            f"(attendu entre {schema.TOTAL_DURATION_MIN} et {schema.TOTAL_DURATION_MAX} s)."
        )
    if not 11.0 <= total <= 16.0:
        warnings.append(
            f"Duree totale {round(total, 1)} s : le modele est calibre pour 12 a 15 s de video courte."
        )

    signature = content.get("signature", {})
    if isinstance(signature, dict) and signature.get("enabled"):
        _check_font(errors, warnings, "signature.font_family", signature.get("font_family"), signature.get("font_weight"))
        if "color" in signature:
            _check_color(errors, "signature", "color", signature.get("color"))
        media = str(signature.get("media", "") or "")
        if media and not media.startswith("media://"):
            errors.append(f"signature.media : chemin Windows interdit dans un projet ({media!r}).")
        elif media and not _media_exists(media):
            errors.append(f"signature.media : logo manquant ({media}). Reimportez-le.")
        if not media and not str(signature.get("handle", "") or "").strip():
            warnings.append("Signature activee sans logo ni nom de marque : rien ne s'affichera.")

    audio = data.get("audio")
    if isinstance(audio, dict) and audio.get("enabled"):
        music = str(audio.get("music", "") or "")
        voice = str(audio.get("voice", "") or "")
        for key, ref in (("music", music), ("voice", voice)):
            if not ref:
                continue
            if not ref.startswith("media://"):
                errors.append(f"audio.{key} : chemin Windows interdit dans un projet ({ref!r}).")
            elif not _media_exists(ref):
                errors.append(f"audio.{key} : media manquant ({ref}). Reimportez-le.")
        if not music and not voice:
            warnings.append("Audio active sans aucun fichier : aucune piste ne sera mixee.")
        for key in ("music_volume", "voice_volume"):
            if key in audio:
                _check_num(errors, warnings, "audio", key, audio.get(key), 0.0, 1.0)
        for key in ("music_fade_in", "music_fade_out"):
            if key in audio:
                _check_num(errors, warnings, "audio", key, audio.get(key), 0.0, max(total, 0.0))

    return (errors, warnings)
