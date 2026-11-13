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

# Transitions entre scenes : un chevauchement rendu a la frontiere, sans toucher
# la chronologie resolue (le curseur, la duree totale et les fenetres de calques
# restent identiques). « none » = coupe franche, le comportement historique.
TRANSITION_TYPES = (
    "none", "fade", "dip_black", "slide_left", "slide_right",
    "slide_up", "slide_down", "wipe", "zoom", "push",
)
TRANSITION_FRAMES_MAX = 60

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


def default_transition() -> dict:
    """Transition d'entree d'une scene : coupe franche par defaut."""
    return {"type": "none", "frames": 0}


def scene(scene_id: str, label: str, duration: float, layers: list[dict], effects: list | None = None,
          transition: dict | None = None, **bg) -> dict:
    background = {"media": "", "fit": "cover", "animation": "static"}
    background.update(bg)
    return {
        "id": scene_id,
        "label": label,
        "duration": duration,
        "hidden": False,
        "effects": copy.deepcopy(list(effects)) if effects else [],
        "background": background,
        "transition": copy.deepcopy(transition) if transition else default_transition(),
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


def preset_project(preset_id: str) -> dict:
    """Construit un preset indépendant, sans média, pour quote_cinematic."""
    if preset_id not in ("recit-cinematique", "showcase-cinematique"):
        raise RuntimeError(f"Preset inconnu : {preset_id!r}.")

    project = cinematic_project()
    project["name"] = preset_id
    project["content"]["signature"].update(enabled=False, media="", handle="")
    project["audio"].update(
        music="", voice="", enabled=False, music_volume=0.12, voice_volume=1.0,
        music_fade_in=0.6, music_fade_out=1.0,
    )
    narrative = preset_id == "recit-cinematique"
    if narrative:
        project["theme"].update(
            palette_id="bleu_ambre", background_color="#080F1E", surface_color="#192D48",
            text_color="#F6F3EC", accent_color="#E8B46A", author_color="#E8B46A",
            muted_color="#AAB4C4", font_family="space-grotesk", font_weight=700,
            font_size=84, line_height=1.12, letter_spacing=-0.015,
        )
        beats = [
            ("Accroche", 3.0, "Tout part\nd’un choix.", "Une idée peut tout changer.", "hook", 0.38, 0.59, "mask_reveal"),
            ("Contexte", 4.0, "Chaque jour,\nle même chemin.", "Le confort avait pris toute la place.", "body", 0.46, 0.68, "slide_up"),
            ("Tension", 4.0, "Et si rien\nne changeait ?", "Attendre devenait le vrai risque.", "body", 0.40, 0.63, "mask_reveal"),
            ("Déclic", 4.0, "Un premier pas.", "Pas parfait. Mais bien réel.", "reveal", 0.48, 0.70, "scale"),
            ("Conclusion", 3.0, "À vous\nd’écrire la suite.", "Commencez petit. Commencez maintenant.", "reveal", 0.42, 0.64, "mask_reveal"),
        ]
        scene_effects = {
            1: [{"id": "light_leak", "params": {"color_a": "#E8B46A", "color_b": "#FFD99A", "intensity": 0.12, "size": 0.65, "cycle_frames": 180}}],
            4: [{"id": "color_grade", "params": {"look": "teal_orange", "strength": 0.15, "contrast": 1.05, "vignette": 0.1}}],
        }
        title_effects = {
            1: [{"id": "shine", "params": {"once": True, "period_frames": 55, "width": 0.2, "intensity": 1.5, "opacity": 0.45}}],
            4: [{"id": "spring_pop", "params": {"damping": 18, "stiffness": 160, "mass": 1, "overshoot": 1.06, "rotate_deg": 0}}],
        }
    else:
        project["theme"].update(
            palette_id="noir_or", background_color="#0B0B10", surface_color="#24232B",
            text_color="#FAF8F2", accent_color="#D9BC7A", author_color="#D9BC7A",
            muted_color="#B7B3AA", font_family="playfair-display", font_weight=700,
            font_size=92, line_height=1.16, letter_spacing=0.01,
        )
        beats = [
            ("Promesse", 3.0, "L’essentiel,\nsublimé.", "Une présence. Tout simplement.", "hook", 0.40, 0.62, "mask_reveal"),
            ("Détail", 4.0, "Le sens\ndu détail.", "Chaque ligne compte.", "body", 0.68, 0.83, "slide_up"),
            ("Bénéfice", 4.0, "Plus de place\npour l’essentiel.", "Votre quotidien, en plus simple.", "body", 0.68, 0.83, "mask_reveal"),
            ("Invitation", 3.0, "Faites place\nà l’exception.", "Découvrez votre prochain essentiel.", "reveal", 0.42, 0.65, "scale"),
        ]
        scene_effects = {
            1: [{"id": "light_leak", "params": {"color_a": "#D9BC7A", "color_b": "#FAF8F2", "intensity": 0.08, "size": 0.6, "cycle_frames": 240}}],
        }
        title_effects = {
            4: [{"id": "shine", "params": {"once": True, "period_frames": 60, "width": 0.18, "intensity": 1.4, "opacity": 0.4}}],
        }

    scenes = []
    for index, (label, duration, text, caption, role, title_y, caption_y, entrance) in enumerate(beats, 1):
        title_style = {}
        if narrative and index in (1, 5):
            title_style.update(font_family="anton", font_weight=400, font_size=112, line_height=1.04)
        elif not narrative and index in (2, 3):
            title_style["font_size"] = 76
        title = text_layer(
            "title", text, role=role, start_frames=4, in_frames=24,
            position={"y": title_y, "width": 0.82}, style=title_style,
            animation={
                "in": entrance, "unit": "line" if "\n" in text else "block",
                "stagger_frames": 4, "out_frames": 10,
                "easing": "ease_out_quint", "distance": 0.035,
            },
            effects=title_effects.get(index),
        )
        subtitle = text_layer(
            "subtitle", caption, role="caption", start_frames=24, in_frames=18,
            position={"y": caption_y, "width": 0.82},
            style={"font_family": "space-grotesk", "font_weight": 500, "font_size": 32,
                   "line_height": 1.3, "letter_spacing": 0.05},
            animation={"in": "slide_up", "unit": "block", "distance": 0.02, "out_frames": 10},
        )
        subtitle["emphasis"] = [caption]
        layers = [title, subtitle]
        if not narrative and index in (2, 3):
            visual = image_layer(
                "visual", media="", start_frames=0, in_frames=24,
                position={"x": 0.5, "y": 0.36, "width": 0.68},
                animation={"in": "scale", "out": "fade", "out_frames": 10, "easing": "ease_out_quint"},
            )
            visual["hidden"] = True  # Emplacement à activer après l'ajout d'un média.
            layers.insert(0, visual)
        scenes.append(scene(
            f"s{index}", label, duration, layers, effects=scene_effects.get(index),
            media="", animation="zoom_slow" if index % 2 else "zoom_out",
        ))
    project["content"]["scenes"] = scenes
    return project


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
