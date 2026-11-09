"""Format de projet version 2 : scenes, calques, animations, signature.

Un projet v2 separe explicitement (cahier des charges, section 5) :
``model`` (reference et version du modele), ``content`` (scenes et calques de
contenu), ``theme`` (valeurs par defaut de mise en page), ``signature``
(elements de marque), ``audio`` (reserve, non rendu dans cette tranche),
``variation`` (graine enregistree) et ``export`` (parametres de sortie).

Les regles de timing sont exprimees en FRAMES, pas en secondes ni en timers
independants : la composition est la seule horloge, donc l'aperçu et le rendu
parcourent exactement les memes valeurs (section 8).

Les projets v1 restent lisibles : ``upgrade_v1_to_v2()`` produit une
conversion EXPLICITE, accompagnee des notes de ce qui a change.
"""
from __future__ import annotations

import copy

SCHEMA_VERSION_V2 = 2

# Modeles disponibles cote serveur. Le registre reel des composants est
# web/src/remotion/registry.tsx ; ce dictionnaire est la liste d'acceptation.
MODELS: dict[str, int] = {"quote_cinematic": 1, "quote_vertical": 1}

ANIM_IN = ("fade", "slide_up", "slide_left", "scale", "mask_reveal", "none")
ANIM_OUT = ("none", "fade")
ANIM_UNITS = ("block", "line", "word")
EASINGS = ("linear", "ease_out_cubic", "ease_out_quint", "spring")
BACKGROUND_FIT = ("cover", "contain")
BACKGROUND_ANIM = ("static", "zoom_slow", "zoom_out")
ALIGNMENTS = ("left", "center", "right")
DIRECTIONS = ("ltr", "rtl")

# Taille de composition de reference : les tailles de police sont en pixels
# pour ce cadre, puis mise a l'echelle par hauteur d'image (comme v1).
REF_HEIGHT = 1920

TOTAL_DURATION_MIN = 0.5
TOTAL_DURATION_MAX = 300.0
SCENE_DURATION_MIN = 0.5
SCENE_DURATION_MAX = 120.0


def _anim(**overrides) -> dict:
    base = {
        "in": "fade",
        "out": "fade",
        "unit": "block",
        "stagger_frames": 0,
        "start_frames": 0,
        "in_frames": 18,
        "out_frames": 12,
        "easing": "ease_out_cubic",
        "spring": {"damping": 16, "stiffness": 140, "mass": 1},
        "distance": 0.06,
    }
    base.update(overrides)
    return base


def text_layer(
    layer_id: str,
    text: str,
    *,
    role: str = "body",
    start_frames: int = 0,
    in_frames: int = 18,
    animation: dict | None = None,
    style: dict | None = None,
    position: dict | None = None,
    effects: list | None = None,
) -> dict:
    layer = {
        "id": layer_id,
        "type": "text",
        "role": role,
        "text": text,
        "emphasis": [],
        "hidden": False,
        "locked": False,
        "effects": [],
        "position": {
            "x": 0.5,
            "y": 0.5,
            "width": 0.84,
            "align": "center",
            "direction": "ltr",
        },
        "style": {},
        "animation": _anim(start_frames=start_frames, in_frames=in_frames),
    }
    if position:
        layer["position"].update(position)
    if style:
        layer["style"].update(style)
    if animation:
        layer["animation"].update(animation)
    if effects:
        layer["effects"] = copy.deepcopy(list(effects))
    return layer


def image_layer(
    layer_id: str,
    media: str = "",
    *,
    start_frames: int = 0,
    in_frames: int = 16,
    position: dict | None = None,
    animation: dict | None = None,
    effects: list | None = None,
) -> dict:
    layer = {
        "id": layer_id,
        "type": "image",
        "role": "mark",
        "media": media,
        "hidden": False,
        "locked": False,
        "opacity": 1.0,
        "effects": [],
        "position": {
            "x": 0.82,
            "y": 0.9,
            "width": 0.16,
            "align": "center",
            "direction": "ltr",
        },
        "animation": _anim(start_frames=start_frames, in_frames=in_frames, out="none"),
    }
    if position:
        layer["position"].update(position)
    if animation:
        layer["animation"].update(animation)
    if effects:
        layer["effects"] = copy.deepcopy(list(effects))
    return layer


def scene(scene_id: str, label: str, duration: float, layers: list[dict], effects: list | None = None, **bg) -> dict:
    background = {"media": "", "fit": "cover", "animation": "static"}
    background.update(bg)
    return {
        "id": scene_id,
        "label": label,
        "duration": duration,
        "hidden": False,
        "effects": copy.deepcopy(list(effects)) if effects else [],
        "background": background,
        "layers": layers,
    }


def default_theme() -> dict:
    return {
        "palette_id": "noir_or",
        "background_color": "#0B0B10",
        "surface_color": "#15151F",
        "text_color": "#F7F5EF",
        "accent_color": "#E2B458",
        "author_color": "#E2B458",
        "muted_color": "#9A9AA8",
        "font_family": "playfair-display",
        "font_weight": 700,
        "font_size": 84,
        "line_height": 1.18,
        "letter_spacing": -0.015,
        "shadow": True,
    }


def default_signature() -> dict:
    return {
        "enabled": True,
        "media": "",
        "handle": "@votre.marque",
        "font_family": "space-grotesk",
        "font_weight": 500,
        "font_size": 34,
        "color": "#9A9AA8",
        "logo_width": 0.14,
        "position": {"x": 0.5, "y": 0.945},
        "start_frames": 0,
        "in_frames": 24,
    }


def cinematic_project() -> dict:
    """Demonstration validee : 3 scenes, 13,5 s a 30 fps (405 frames).

    Scene 1 accroche (revelation par masque, mot par mot), scene 2 citation
    (entree par mot, mots mis en valeur), scene 3 signature (scale + fondu).
    Les valeurs sont celles du modele : elles sont toutes reglables sans code.
    """
    hook = text_layer(
        "hook",
        "Ce que personne ne te dit",
        role="hook",
        start_frames=4,
        in_frames=26,
        position={"x": 0.5, "y": 0.42, "width": 0.86, "align": "center"},
        style={
            "font_family": "anton",
            "font_weight": 400,
            "font_size": 132,
            "line_height": 1.02,
            "letter_spacing": 0.01,
            "color": "#F7F5EF",
        },
        animation={
            "in": "mask_reveal",
            "out": "fade",
            "unit": "line",
            "stagger_frames": 5,
            "easing": "spring",
            "out_frames": 10,
        },
    )
    hook_caption = text_layer(
        "hook-caption",
        "épisode 01",
        role="caption",
        start_frames=20,
        in_frames=20,
        position={"x": 0.5, "y": 0.62, "width": 0.6, "align": "center"},
        style={
            "font_family": "space-grotesk",
            "font_weight": 500,
            "font_size": 34,
            "letter_spacing": 0.24,
            "color": "#E2B458",
        },
        animation={"in": "fade", "out": "fade", "unit": "block", "in_frames": 20},
    )

    quote = text_layer(
        "quote",
        "Le courage n'est pas l'absence de peur, mais la decision de continuer malgre elle.",
        role="quote",
        start_frames=6,
        in_frames=22,
        position={"x": 0.5, "y": 0.46, "width": 0.82, "align": "center"},
        style={
            "font_family": "playfair-display",
            "font_weight": 700,
            "font_size": 88,
            "line_height": 1.16,
            "letter_spacing": -0.015,
            "color": "#F7F5EF",
        },
        animation={
            "in": "slide_up",
            "out": "fade",
            "unit": "word",
            "stagger_frames": 3,
            "in_frames": 16,
            "easing": "spring",
            "distance": 0.045,
        },
    )
    quote["emphasis"] = ["courage", "continuer"]

    author = text_layer(
        "author",
        "— Amelia Runa",
        role="author",
        start_frames=48,
        in_frames=20,
        position={"x": 0.5, "y": 0.68, "width": 0.7, "align": "center"},
        style={
            "font_family": "space-grotesk",
            "font_weight": 500,
            "font_size": 42,
            "letter_spacing": 0.04,
            "color": "#E2B458",
        },
        animation={"in": "fade", "out": "fade", "unit": "block", "in_frames": 20},
    )

    reveal = text_layer(
        "reveal",
        "Agir",
        role="reveal",
        start_frames=4,
        in_frames=30,
        position={"x": 0.5, "y": 0.4, "width": 0.9, "align": "center"},
        style={
            "font_family": "archivo-black",
            "font_weight": 400,
            "font_size": 210,
            "line_height": 1.0,
            "letter_spacing": -0.03,
            "color": "#E2B458",
        },
        animation={
            "in": "scale",
            "out": "none",
            "unit": "block",
            "in_frames": 30,
            "easing": "spring",
        },
    )
    reveal_note = text_layer(
        "reveal-note",
        "La marque · votre signature",
        role="caption",
        start_frames=34,
        in_frames=22,
        position={"x": 0.5, "y": 0.58, "width": 0.8, "align": "center"},
        style={
            "font_family": "inter",
            "font_weight": 400,
            "font_size": 36,
            "letter_spacing": 0.02,
            "color": "#F7F5EF",
        },
        animation={"in": "slide_up", "out": "none", "unit": "block", "distance": 0.03},
    )

    return {
        "version": SCHEMA_VERSION_V2,
        "model": {"id": "quote_cinematic", "version": MODELS["quote_cinematic"]},
        "name": "citation-cinematique",
        "content": {
            "scenes": [
                scene("s1", "Accroche", 4.0, [hook, hook_caption]),
                scene("s2", "Citation", 6.0, [quote, author]),
                scene("s3", "Signature", 3.5, [reveal, reveal_note]),
            ],
            "signature": default_signature(),
        },
        "theme": default_theme(),
        "audio": {
            "music": "",
            "voice": "",
            "music_volume": 0.3,
            "voice_volume": 1.0,
            "music_fade_in": 1.0,
            "music_fade_out": 1.5,
            "markers": [],
            "enabled": False,
        },
        "variation": {"seed": 1},
        "export": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "output_dir": "",
            "filename": "",
        },
    }


def new_project(model_id: str = "quote_cinematic") -> dict:
    if model_id not in MODELS:
        raise RuntimeError(f"Modele inconnu : {model_id!r} (connus : {', '.join(MODELS)}).")
    if model_id == "quote_cinematic":
        return cinematic_project()
    return cinematic_project()


# --- Calculs de chronologie en frames (partages avec la validation) ---------


def fps_of(project: dict) -> int:
    return int(project.get("export", {}).get("fps", 30))


def scene_start_frame(project: dict, index: int) -> int:
    fps = fps_of(project)
    start = 0
    scenes = project.get("content", {}).get("scenes", [])
    for i, sc in enumerate(scenes):
        if i == index:
            break
        start += int(round(float(sc.get("duration", 0.0)) * fps))
    return start


def total_duration(project: dict) -> float:
    return sum(float(sc.get("duration", 0.0)) for sc in project.get("content", {}).get("scenes", []))


def total_frames(project: dict) -> int:
    fps = fps_of(project)
    return sum(int(round(float(sc.get("duration", 0.0)) * fps)) for sc in project.get("content", {}).get("scenes", []))


# --- Migration explicite v1 -> v2 ------------------------------------------

# Correspondance des anciens fichiers Windows vers le catalogue sous licence.
# Le nom de fichier est conserve dans les notes, jamais utilise pour le rendu.
_V1_FONT_MAP = {
    "arialbd.ttf": ("inter", 700),
    "arial.ttf": ("inter", 400),
    "segoeuib.ttf": ("inter", 700),
    "segoeui.ttf": ("inter", 400),
    "verdana.ttf": ("inter", 400),
    "calibrib.ttf": ("inter", 700),
    "calibri.ttf": ("inter", 400),
    "georgia.ttf": ("playfair-display", 400),
    "times.ttf": ("playfair-display", 400),
    "impact.ttf": ("anton", 400),
}


def upgrade_v1_to_v2(v1: dict) -> tuple[dict, list[str]]:
    """Convertit un projet v1 en v2. Retourne (projet_v2, notes).

    Aucune valeur n'est inventee : ce que le format v2 ne peut pas exprimer
    fidelement est signale dans les notes pour correction manuelle.
    """
    if v1.get("version") != 1:
        raise RuntimeError(f"Conversion attendue un projet v1, recu version {v1.get('version')!r}.")

    notes: list[str] = []
    theme_v1 = v1.get("theme", {})
    timing = v1.get("timing", {})
    position = v1.get("position", {})
    animation = v1.get("animation", {})
    content = v1.get("content", {})
    export = v1.get("export", {})
    fps = int(export.get("fps", 30)) or 30

    family_v1 = str(theme_v1.get("font_family", ""))
    mapped = _V1_FONT_MAP.get(family_v1.lower())
    if mapped:
        family, weight = mapped
        notes.append(
            f"Police : {family_v1} (police systeme Windows, non redistribuable) "
            f"remplacee par {family} poids {weight} sous licence OFL."
        )
    else:
        family, weight = "inter", int(theme_v1.get("font_weight", 700))
        notes.append(
            f"Police : {family_v1 or 'non definie'} est inconnue dans le catalogue ; "
            "remplacee par inter. Choisissez une autre police dans l'editeur."
        )

    def frames(seconds: float) -> int:
        try:
            return max(0, int(round(float(seconds) * fps)))
        except (TypeError, ValueError):
            return 0

    quote = text_layer(
        "quote",
        str(content.get("text", "")),
        role="quote",
        start_frames=frames(timing.get("text_start", 0.0)),
        in_frames=frames(timing.get("fade_in", 0.8)) or 1,
        position={
            "x": float(position.get("x", 0.5)),
            "y": float(position.get("y", 0.45)),
            "width": float(position.get("width", 0.85)),
            "align": "center",
        },
        style={
            "font_family": family,
            "font_weight": weight,
            "font_size": float(theme_v1.get("font_size", 72)),
            "color": theme_v1.get("text_color", "#FFFFFF"),
            "shadow": bool(theme_v1.get("shadow", True)),
        },
        animation={
            "in": "slide_up" if animation.get("text_in") == "slide" else "fade",
            "out": "fade",
            "unit": "block",
            "out_frames": frames(timing.get("fade_out", 0.8)) or 1,
        },
    )

    layers = [quote]
    author_text = str(content.get("author", "") or "").strip()
    if author_text:
        layers.append(
            text_layer(
                "author",
                author_text if author_text.startswith("—") else f"— {author_text}",
                role="author",
                start_frames=frames(timing.get("text_start", 0.0)) + max(8, frames(timing.get("fade_in", 0.8))),
                in_frames=frames(timing.get("fade_in", 0.8)) or 1,
                position={"x": float(position.get("x", 0.5)), "y": min(0.95, float(position.get("y", 0.45)) + 0.22), "width": 0.7},
                style={"font_family": family, "font_weight": weight, "font_size": max(20, float(theme_v1.get("font_size", 72)) * 0.5), "color": theme_v1.get("author_color", "#F2C14E")},
                animation={"in": "fade", "out": "fade"},
            )
        )

    logo = str(content.get("logo", "") or "")
    signature = default_signature()
    signature["media"] = logo
    signature["enabled"] = bool(logo)
    if logo:
        notes.append("Logo v1 place dans la signature de marque (coin bas-droite).")

    duration = float(timing.get("duration", 8.0))
    project = {
        "version": SCHEMA_VERSION_V2,
        "model": {"id": "quote_cinematic", "version": MODELS["quote_cinematic"]},
        "name": str(v1.get("name") or "projet-converti"),
        "content": {
            "scenes": [
                scene(
                    "s1",
                    "Citation",
                    duration,
                    layers,
                    media=logo_and_background(content),
                    fit="cover",
                    animation="static" if animation.get("background") == "static" else animation.get("background", "static"),
                )
            ],
            "signature": signature,
        },
        "theme": {
            **default_theme(),
            "text_color": theme_v1.get("text_color", default_theme()["text_color"]),
            "author_color": theme_v1.get("author_color", default_theme()["author_color"]),
            "accent_color": theme_v1.get("accent_color", default_theme()["accent_color"]),
            "font_family": family,
            "font_weight": weight,
            "font_size": float(theme_v1.get("font_size", 84)),
            "shadow": bool(theme_v1.get("shadow", True)),
        },
        "audio": {"music": "", "voice": "", "music_volume": 0.3, "voice_volume": 1.0, "music_fade_in": 1.0, "music_fade_out": 1.5, "markers": [], "enabled": False},
        "variation": {"seed": 1},
        "export": {
            "width": int(export.get("width", 1080)),
            "height": int(export.get("height", 1920)),
            "fps": fps,
            "output_dir": str(export.get("output_dir", "") or ""),
            "filename": "",
        },
    }
    if duration > 15:
        notes.append(f"Scene unique de {duration} s : le modele v2 est concu pour 12 a 15 s.")
    return project, notes


def logo_and_background(content: dict) -> str:
    """Le fond v1 est repris tel quel (ref media:// ou chemin herite)."""
    return str(content.get("background_image", "") or "")


def clone(project: dict) -> dict:
    return copy.deepcopy(project)
