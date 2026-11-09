"""Catalogue des effets du studio : source unique de verite.

Un effet est une donnees AVANT d'etre du code : ce fichier declare ce qui
existe, l'interface et l'assistant lisent la meme liste, et le rendu Remotion
implemente exactement ces identifiants. Un effet absent d'ici ne peut pas etre
demande ; un effet declare ici sans implementation TS echoue au test de
cohérence (tests/test_effects.py).

Regles heritees du cahier des charges :
- aucun effet ne lit l'heure wall-clock ni Math.random() : la grain du projet
  (``variation.seed``) et la frame de la composition decident seuls, donc
  l'apercu et l'export produisent les memes images ;
- aucun effet ne depend d'une dependance non installee : que du CSS, des filtres
  SVG, du canvas 2D et des paquets @remotion/* deja presents ;
- les valeurs sont bornees : une entree hors bornes est signalee, jamais
  ignoree ni remplacee en silence.
"""
from __future__ import annotations

CATEGORIES: tuple[tuple[str, str], ...] = (
    ("motion", "Motion design et physique"),
    ("distort", "Distorsions et glitch"),
    ("space", "3D, camera et espace"),
    ("audio", "Reactif a l'audio"),
    ("screen", "Screencast et interface"),
    ("generative", "Generatif et shaders"),
    ("light", "Lumiere, couleur et keying"),
)

# Portee d'un effet :
#   layer   - emballe un calque (texte ou image)
#   scene   - emballe une scene entiere (fond + calques)
#   overlay - element plein cadre pose par-dessus la scene
SCOPES = ("layer", "scene", "overlay")

TARGETS = ("text", "image", "any")

PARAM_TYPES = ("number", "integer", "bool", "color", "select", "text")

MAX_EFFECTS_PER_TARGET = 4


def _num(key, label, lo, hi, default, step=0.01, unit=""):
    return {
        "key": key,
        "label": label,
        "type": "number",
        "min": lo,
        "max": hi,
        "default": default,
        "step": step,
        "unit": unit,
    }


def _int(key, label, lo, hi, default, step=1):
    return {
        "key": key,
        "label": label,
        "type": "integer",
        "min": lo,
        "max": hi,
        "default": default,
        "step": step,
    }


def _bool(key, label, default):
    return {"key": key, "label": label, "type": "bool", "default": default}


def _color(key, label, default):
    return {"key": key, "label": label, "type": "color", "default": default}


def _select(key, label, options, default):
    return {
        "key": key,
        "label": label,
        "type": "select",
        "options": list(options),
        "default": default,
    }


def _text(key, label, default, max_chars, placeholder=""):
    return {
        "key": key,
        "label": label,
        "type": "text",
        "default": default,
        "max_chars": max_chars,
        "placeholder": placeholder,
    }


def _fx(
    effect_id,
    label,
    category,
    scopes,
    description,
    params,
    targets=("text", "image"),
    needs_audio=False,
    note="",
):
    return {
        "id": effect_id,
        "label": label,
        "category": category,
        "scopes": list(scopes),
        "targets": list(targets),
        "needs_audio": needs_audio,
        "description": description,
        "note": note,
        "params": params,
    }


EFFECTS: list[dict] = [
    # --- Motion design et physique -----------------------------------------
    _fx(
        "spring_pop",
        "Ressort d'apparition",
        "motion",
        ["layer"],
        "Le calque entre avec un ressort physique reglable : surtension d'echelle "
        "et rotation qui se stabilisent, sans courbe lineaire.",
        [
            _num("damping", "Amortissement", 1, 40, 8, 0.5),
            _num("stiffness", "Raideur", 20, 500, 200, 5),
            _num("mass", "Masse", 0.1, 6, 1, 0.1),
            _num("overshoot", "Surtension d'echelle", 1.0, 1.8, 1.18, 0.01),
            _num("rotate_deg", "Rotation de depart", -45, 45, -8, 1, "degres"),
        ],
        targets=("text", "image"),
    ),
    _fx(
        "kinetic_letters",
        "Typographie cinematique lettre a lettre",
        "motion",
        ["layer"],
        "Chaque lettre recoit son propre ressort : montee, rotation et flou de "
        "mouvement decalés, facon motion design.",
        [
            _int("stagger_frames", "Decalage par lettre", 0, 8, 2),
            _num("rise", "Hauteur de montee", 0, 0.5, 0.12, 0.01, "fraction de hauteur"),
            _num("rotate_deg", "Rotation", -45, 45, -12, 1, "degres"),
            _num("blur_px", "Flou de depart", 0, 24, 6, 0.5, "px"),
            _num("damping", "Amortissement", 4, 40, 12, 0.5),
        ],
        targets=("text",),
    ),
    _fx(
        "flip_card",
        "Revelation par carte retournee",
        "motion",
        ["layer"],
        "Le calque arrive comme une carte qui pivote : la face colorée est visible "
        "a mi-parcours, le contenu se revele quand la carte se retourne.",
        [
            _select("axis", "Axe", ("y", "x"), "y"),
            _int("duration_frames", "Duree", 10, 120, 40),
            _int("delay_frames", "Attente avant pivot", 0, 300, 0),
            _int("perspective_px", "Perspective", 400, 4000, 1200, 50),
            _color("plate_color", "Face de la carte", "#E2B458"),
        ],
        targets=("text", "image"),
    ),
    _fx(
        "path_trace",
        "Tracer un contour SVG",
        "motion",
        ["overlay"],
        "Une forme se dessine trait apres trait : longueur calculee avec "
        "@remotion/paths, puis deplacement du masque de tracage.",
        [
            _text(
                "path",
                "Chemin SVG (attribut d)",
                "M 40 200 C 120 40, 240 360, 340 200 S 520 60, 600 220",
                600,
                "M 0 100 L 200 100",
            ),
            _color("stroke_color", "Couleur du trait", "#E2B458"),
            _int("stroke_width_px", "Epaisseur", 1, 40, 5, 1),
            _int("draw_frames", "Frames de tracage", 5, 300, 45),
            _int("hold_frames", "Maintien apres tracage", 0, 600, 30),
            _bool("fade_out", "Disparaitre a la fin", True),
        ],
        note="Le chemin est une donnee : il est verifie (longueur, caracteres) avant le rendu.",
    ),
    _fx(
        "path_morph",
        "Morphing de forme",
        "motion",
        ["overlay"],
        "Interpolation reelle entre deux tracés SVG via @remotion/paths : "
        "remplace flubber sans dependance ajoutee.",
        [
            _text("from_path", "Forme de depart", "M 100 20 L 300 200 L 100 380 Z", 600),
            _text("to_path", "Forme d'arrivee", "M 200 20 A 180 180 0 1 1 199 20 Z", 600),
            _int("morph_frames", "Frames d'interpolation", 5, 300, 50),
            _int("delay_frames", "Attente avant morphing", 0, 300, 0),
            _color("fill_color", "Remplissage", "#E2B458"),
            _num("fill_opacity", "Opacite du remplissage", 0, 1, 0.85, 0.05),
        ],
        note="Les deux tracés doivent avoir le meme nombre de segments : sinon le rendu "
        "n'affiche rien au lieu d'inventer une interpolation ou de casser la video.",
    ),
    # --- Distorsions et glitch ---------------------------------------------
    _fx(
        "chromatic_aberration",
        "Aberration chromatique",
        "distort",
        ["layer", "scene"],
        "Separation des couches rouge, verte et bleue decalees puis recomposees en "
        "fusion ecran : rendu par filtres SVG, aucune dependance.",
        [
            _num("offset_px", "Decalage", 0, 60, 12, 0.5, "px"),
            _num("angle_deg", "Direction du decalage", 0, 360, 0, 1, "degres"),
            _bool("animate", "Animer le decalage", True),
            _int("cycle_frames", "Periode d'animation", 6, 240, 24),
        ],
        targets=("text", "image"),
    ),
    _fx(
        "glitch_slices",
        "Glitch par tranches",
        "distort",
        ["layer", "scene"],
        "Tranches horizontales deplacees et recolorées a partir de la graine du "
        "projet : deterministe, la meme frame donne la meme image.",
        [
            _int("delay_frames", "Debut dans la scene", 0, 600, 0),
            _int("duration_frames", "Duree du glitch", 4, 180, 24),
            _int("slice_count", "Nombre de tranches", 2, 24, 8),
            _num("max_offset", "Decalage maximal", 0, 1, 0.08, 0.01, "fraction de largeur"),
            _int("reroll_frames", "Frames par saut", 1, 12, 2),
            _num("intensity", "Opacite du dedoublement", 0, 1, 0.55, 0.05),
        ],
        targets=("text", "image"),
    ),
    _fx(
        "scanlines",
        "Scanlines CRT",
        "distort",
        ["overlay"],
        "Rayures horizontales animees façon écran cathodique, avec leger "
        "roulement vertical et moirage evite par pas entier.",
        [
            _int("line_height_px", "Pas des lignes", 2, 40, 6, 1),
            _int("thickness_px", "Epaisseur du trait", 1, 8, 1, 1),
            _num("opacity", "Opacite", 0, 1, 0.35, 0.05),
            _bool("roll", "Faire defiler", True),
            _num("roll_speed", "Vitesse de defilement", -4, 4, 0.6, 0.1, "px par frame"),
            _color("color", "Couleur", "#000000"),
        ],
    ),
    _fx(
        "white_noise",
        "Bruit blanc",
        "distort",
        ["overlay"],
        "Grain analogique genere par feTurbulence : le meme reglage donne la meme "
        "matiere a chaque frame, l'animation deplace la frequence, pas le hasard.",
        [
            _num("opacity", "Opacite", 0, 1, 0.22, 0.02),
            _num("scale", "Granulosite", 1, 60, 14, 0.5),
            _bool("animated", "Faire bouillonner", True),
            _int("cycle_frames", "Periode", 2, 120, 3),
            _select("kind", "Type de turbulence", ("fractalNoise", "turbulence"), "fractalNoise"),
            _int("octaves", "Octaves", 1, 5, 2),
        ],
    ),
    # --- 3D, camera et espace ----------------------------------------------
    _fx(
        "perspective_dolly",
        "Travelling de camera 3D",
        "space",
        ["scene"],
        "La scene entre dans un espace en perspective : depth deplacee, leger "
        "pendule en X et Y, easing choisi. CSS 3D pur, sans three.js. "
        "Reglages par defaut prudents : au-dela de 0.35 d'arrivee, les bords "
        "des calques sortent du cadre.",
        [
            _num("start_z", "Profondeur de depart", -0.9, 0.9, -0.25, 0.05, "fraction"),
            _num("end_z", "Profondeur d'arrivee", -0.9, 0.9, 0.08, 0.05, "fraction"),
            _num("rotate_x_deg", "Pendule vertical", -25, 25, 4, 0.5, "degres"),
            _num("rotate_y_deg", "Pendule horizontal", -25, 25, -6, 0.5, "degres"),
            _int("perspective_px", "Focale", 400, 4000, 1600, 50),
            _select("easing", "Courbe", ("ease_out_cubic", "ease_out_quint", "linear", "spring"), "ease_out_cubic"),
        ],
    ),
    _fx(
        "parallax_depth",
        "Parallaxe par profondeur",
        "space",
        ["layer"],
        "Le calque derive pendant la scene selon sa profondeur, alors que le fond "
        "reste a sa place : la separation des plans donne le volume.",
        [
            _num("depth", "Profondeur", 0, 1, 0.6, 0.05),
            _num("drift_x", "Derive horizontale", -1, 1, 0.12, 0.02, "fraction de largeur"),
            _num("drift_y", "Derive verticale", -1, 1, -0.05, 0.02, "fraction de hauteur"),
            _num("scale_from", "Echelle au debut", 0.6, 1.6, 1.04, 0.02),
            _num("scale_to", "Echelle a la fin", 0.6, 1.6, 1, 0.02),
        ],
        targets=("text", "image"),
    ),
    _fx(
        "cylinder_wrap",
        "Texte enveloppe sur un cylindre",
        "space",
        ["layer"],
        "Chaque lettre pivote autour d'un axe vertical et se place sur la surface "
        "d'un cylindre en CSS 3D ; les lettres de dos disparaissent, comme en reel.",
        [
            _int("radius_px", "Rayon du cylindre", 80, 1600, 420, 10),
            _num("arc_deg", "Arc occupe", 20, 340, 150, 5, "degres"),
            _num("rotation_deg", "Orientation de depart", -360, 360, -60, 5, "degres"),
            _bool("spin", "Rotation continue", True),
            _num("spin_deg_per_s", "Vitesse de rotation", -180, 180, 24, 1, "degres/s"),
            _num("opacity_back", "Opacite des lettres de dos", 0, 1, 0.15, 0.05),
        ],
        targets=("text",),
    ),
    _fx(
        "sphere_wrap",
        "Texte enveloppe sur une sphere",
        "space",
        ["layer"],
        "Approximation en tranches : les lettres sont reparties en latitude et "
        "longitude puis projetees sur la sphere par rotateX/rotateY + translateZ.",
        [
            _int("radius_px", "Rayon de la sphere", 80, 1200, 320, 10),
            _num("lat_deg", "Latitude", -80, 80, 12, 1, "degres"),
            _num("spread_deg", "Etalement en longitude", 20, 320, 140, 5, "degres"),
            _num("rotation_deg", "Rotation de depart", -360, 360, 0, 5, "degres"),
            _num("spin_deg_per_s", "Vitesse de rotation", -180, 180, 18, 1, "degres/s"),
            _num("opacity_back", "Opacite des lettres cachees", 0, 1, 0.1, 0.05),
        ],
        targets=("text",),
        note="Sphere en CSS : projection par tranches, pas un maillage 3D reel.",
    ),
    # --- Reactif a l'audio --------------------------------------------------
    _fx(
        "audio_pulse",
        "Pulse sur les graves",
        "audio",
        ["layer"],
        "L'echelle et l'eclaircissement du calque suivent la bande d'energie "
        "choisie, mesuree sur la vraie piste via @remotion/media-utils.",
        [
            _select("band", "Bande", ("bass", "mid", "treble"), "bass"),
            _num("min_scale", "Echelle au silence", 0.6, 1.2, 0.97, 0.01),
            _num("max_scale", "Echelle au pic", 1, 2.2, 1.14, 0.01),
            _num("smoothing", "Lissage", 0, 0.95, 0.6, 0.05),
            _num("glow", "Halo sur les pics", 0, 60, 18, 1, "px"),
        ],
        needs_audio=True,
        targets=("text", "image"),
    ),
    _fx(
        "audio_spectrum",
        "Spectre frequentiel",
        "audio",
        ["overlay"],
        "Barres de spectre dessinees a partir des donnees audio reelles de la "
        "musique du projet (FFT embarquee dans @remotion/media-utils). Le nombre "
        "de barres est arrondi a la puissance de deux la plus proche.",
        [
            _int("bars", "Nombre de barres", 8, 96, 32),
            _num("max_height", "Hauteur maximale", 0.02, 0.6, 0.18, 0.01, "fraction de hauteur"),
            _color("color", "Couleur", "#E2B458"),
            _select("edge", "Position", ("bottom", "top"), "bottom"),
            _num("smoothing", "Lissage", 0, 0.95, 0.75, 0.05),
            _num("tilt", "Compensation des aigus", 0, 4, 1.2, 0.1),
            _num("opacity", "Opacite", 0, 1, 0.9, 0.05),
        ],
        needs_audio=True,
    ),
    _fx(
        "audio_waveform",
        "Forme d'onde",
        "audio",
        ["overlay"],
        "Tracé de l'enveloppe sonore autour de la frame courante : la courbe vient "
        "de l'echantillonnage reel du fichier, pas d'une simulation.",
        [
            _int("samples", "Points traces", 32, 512, 96),
            _num("window_seconds", "Fenetre", 0.2, 10, 2.5, 0.1, "s"),
            _num("max_height", "Amplitude", 0.02, 0.5, 0.12, 0.01, "fraction de hauteur"),
            _color("color", "Couleur", "#F7F5EF"),
            _num("position_y", "Position verticale", 0, 1, 0.8, 0.02, "fraction"),
            _num("opacity", "Opacite", 0, 1, 0.8, 0.05),
            _bool("normalize", "Ramener au pic de la fenetre", True),
        ],
        needs_audio=True,
    ),
    # --- Screencast et interface -------------------------------------------
    _fx(
        "cursor_tour",
        "Curseur anime et clic",
        "screen",
        ["overlay"],
        "Un curseur suit une route definie par des points, avec acceleration "
        "humaine et une onde lumineuse a chaque arrivee.",
        [
            _text("points", "Points de passage (x,y)", "0.18,0.72 0.5,0.42 0.78,0.6", 240, "0.2,0.8 0.6,0.4"),
            _int("duration_frames", "Duree du trajet", 12, 480, 70),
            _num("cursor_scale", "Taille du curseur", 0.4, 3, 1.1, 0.1),
            _color("cursor_color", "Couleur du curseur", "#F7F5EF"),
            _color("ripple_color", "Couleur de l'onde", "#E2B458"),
            _select("easing", "Courbe", ("ease_out_cubic", "ease_out_quint", "linear", "spring"), "ease_out_cubic"),
        ],
        note="Les points sont des fractions de l'image (0 a 1) ; une valeur hors cadre est signalee.",
    ),
    _fx(
        "code_type",
        "Code qui se tape",
        "screen",
        ["overlay"],
        "Edition de code animee : frappe caractere par caractere, coloration "
        "mot-cle/chaine/commentaire par un tokenizer maison (ni prism ni shiki).",
        [
            _text("code", "Code affiche", "def etat(plateforme):\n    return 'studio'", 1200),
            _int("chars_per_frame", "Caracteres par frame", 1, 40, 3),
            _int("delay_frames", "Attente avant frappe", 0, 300, 6),
            _int("font_size_px", "Taille du texte", 12, 72, 28, 1),
            _select("theme", "Theme", ("sombre", "clair"), "sombre"),
            _bool("line_numbers", "Numeros de ligne", True),
            _bool("caret", "Curseur clignotant", True),
            _num("opacity", "Opacite du bloc", 0, 1, 1, 0.05),
        ],
    ),
    # --- Generatif et shaders ----------------------------------------------
    _fx(
        "liquid_contours",
        "Contours liquides",
        "generative",
        ["scene"],
        "Deformation du contenu de la scene par turbulence SVG (feTurbulence + "
        "feDisplacementMap) : le fond ondule comme une surface liquide.",
        [
            _num("frequency", "Frequence de la turbulence", 0.001, 0.09, 0.012, 0.001),
            _int("octaves", "Octaves", 1, 5, 2),
            _num("displacement", "Amplitude de deplacement", 0, 160, 42, 1, "px"),
            _bool("animate", "Animer la surface", True),
            _int("cycle_frames", "Periode", 6, 240, 40),
            _num("seed_shift", "Variante de grain", 0, 8, 0, 1),
        ],
        note="Deformation par filtre SVG : sur un fond video, le rendu reste cadre par cadre mais "
        "la deplacement s'applique a l'image decodee.",
    ),
    _fx(
        "plasma_field",
        "Champ de plasma",
        "generative",
        ["overlay"],
        "Interferences de sinus calculees dans un canvas 2D basse resolution puis "
        "etirees : aspect organique, cout maitrise, deterministe.",
        [
            _color("color_a", "Couleur chaude", "#E2B458"),
            _color("color_b", "Couleur froide", "#2B6CE6"),
            _num("scale", "Zoom des cellules", 0.4, 8, 2.2, 0.1),
            _num("complexity", "Complexite", 0.5, 6, 2, 0.1),
            _num("speed", "Vitesse", 0, 4, 0.7, 0.05),
            _num("opacity", "Opacite", 0, 1, 0.35, 0.02),
            _select("blend", "Fusion", ("screen", "lighten", "normal", "color-dodge"), "screen"),
        ],
    ),
    # --- Lumiere, couleur et keying ----------------------------------------
    _fx(
        "shine",
        "Reflet qui traverse",
        "light",
        ["layer"],
        "Balayage lumineux masque sur le calque : une copie eclairée du contenu "
        "n'apparait que dans la bande deplacee, donc le reflet suit les glyphes "
        "et ne lave jamais le fond.",
        [
            _num("width", "Largeur du reflet", 0.05, 0.8, 0.22, 0.01, "fraction"),
            _num("angle_deg", "Inclinaison", -90, 90, 20, 1, "degres"),
            _int("period_frames", "Periode", 18, 300, 50),
            _num("intensity", "Force de l'eclairage", 1, 3, 1.9, 0.05, "multiplicateur"),
            _num("opacity", "Intensite", 0, 1, 0.75, 0.05),
            _bool("once", "Un seul passage", False),
        ],
        targets=("text", "image"),
    ),
    _fx(
        "light_leak",
        "Fuite de lumiere",
        "light",
        ["overlay"],
        "Halos chauds en fusion ecran, deplaces par la graine du projet : "
        "migration pellicule, sans asset externe.",
        [
            _color("color_a", "Teinte 1", "#FF6B3D"),
            _color("color_b", "Teinte 2", "#FFD166"),
            _num("intensity", "Intensite", 0, 1, 0.4, 0.05),
            _num("size", "Taille des halos", 0.2, 1.6, 0.75, 0.05, "fraction"),
            _int("cycle_frames", "Periode de derive", 40, 900, 180),
            _select("blend", "Fusion", ("screen", "lighten", "color-dodge"), "screen"),
        ],
    ),
    _fx(
        "color_grade",
        "Etalonnage",
        "light",
        ["scene"],
        "Courbes de transfert SVG (feComponentTransfer) appliquees a toute la "
        "scene : rendus prets a l'emploi + exposition, contraste, saturation.",
        [
            _select("look", "Rendu", ("teal_orange", "bleute", "sepia", "bleu_nuit", "lavande", "noir_blanc"), "teal_orange"),
            _num("strength", "Melange avec l'original", 0, 1, 0.75, 0.05),
            _num("exposure", "Exposition", 0.4, 2, 1, 0.05),
            _num("contrast", "Contraste", 0.4, 2, 1, 0.05),
            _num("saturation", "Saturation", 0, 2, 1, 0.05),
            _num("vignette", "Vignettage", 0, 1, 0.25, 0.05),
        ],
        note="Etalonnage par courbes, pas un fichier LUT .cube : aucun LUT externe n'est charge.",
    ),
    _fx(
        "depth_blur",
        "Flou progressif et profondeur de champ",
        "light",
        ["scene"],
        "Trois copies floues du contenu masquees par des bandes : le flou "
        "augmente progressivement autour de la zone de mise au point.",
        [
            _num("focus_y", "Zone de nettete", 0, 1, 0.45, 0.02, "fraction"),
            _num("blur_px", "Flou maximal", 0, 60, 18, 1, "px"),
            _num("falloff", "Progressivite", 0.15, 2, 0.8, 0.05),
            _bool("top_to_bottom", "Axe vertical", True),
        ],
        note="Approximation en paliers : le rendu est progressif visuellement, pas une "
        "refocus reel image par image.",
    ),
    _fx(
        "chroma_key",
        "Keying sur fond vert",
        "light",
        ["layer"],
        "Retrait d'une couleur sur un calque IMAGE : echantillonnage canvas 2D, "
        "similarite et suppression des reflets regles.",
        [
            _color("key_color", "Couleur a retirer", "#00FF00"),
            _num("similarity", "Similarite", 0, 1, 0.32, 0.02),
            _num("blend", "Adoucissement du bord", 0, 0.4, 0.08, 0.01),
            _num("spill", "Suppression du renvoi", 0, 1, 0.4, 0.05),
        ],
        targets=("image",),
        note="Supporte les images importees (PNG/JPG). Le keying d'une video de fond n'est "
        "pas implemente : une scene video doit passer par un montage prealable.",
    ),
]

_BY_ID: dict[str, dict] = {fx["id"]: fx for fx in EFFECTS}


def all_effects() -> list[dict]:
    return EFFECTS


def ids() -> list[str]:
    return [fx["id"] for fx in EFFECTS]


def get(effect_id: str) -> dict | None:
    return _BY_ID.get(str(effect_id))


def manifest() -> dict:
    """Ce que lit l'interface et ce que lit l'assistant : le meme dictionnaire."""
    return {
        "categories": [{"id": k, "label": v} for k, v in CATEGORIES],
        "scopes": list(SCOPES),
        "scope_labels": {
            "layer": "sur un calque",
            "scene": "sur une scene entiere",
            "overlay": "plein cadre, par-dessus la scene",
        },
        "max_per_target": MAX_EFFECTS_PER_TARGET,
        "effects": EFFECTS,
    }


def default_params(effect: dict) -> dict:
    return {p["key"]: p["default"] for p in effect["params"]}


def _coerce(effect: dict, spec: dict, raw, path: str, errors: list[str], warnings: list[str]):
    kind = spec["type"]
    if kind in ("number", "integer"):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{path} : valeur numerique attendue, recu {raw!r}.")
            return spec["default"]
        if kind == "integer":
            value = round(value)
        lo, hi = spec["min"], spec["max"]
        if value < lo or value > hi:
            # Une valeur hors bornes est signalee puis ramenée dans le domaine
            # rendu : le projet reste affichable, l'utilisateur est prevenu.
            warnings.append(
                f"{path} = {raw} hors bornes ({lo} a {hi}) : ramene a "
                f"{min(max(value, lo), hi)} pour le rendu."
            )
            value = min(max(value, lo), hi)
        return int(value) if kind == "integer" else round(float(value), 4)
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        errors.append(f"{path} : attendu vrai/faux, recu {raw!r}.")
        return spec["default"]
    if kind == "color":
        text = str(raw or "").strip()
        if _is_hex_color(text):
            return text
        errors.append(f"{path} : couleur hexadecimale attendue (#RRGGBB), recu {raw!r}.")
        return spec["default"]
    if kind == "select":
        text = str(raw or "").strip()
        if text in spec["options"]:
            return text
        errors.append(f"{path} : valeur inconnue {raw!r} (choix : {', '.join(spec['options'])}).")
        return spec["default"]
    # text
    text = "" if raw is None else str(raw)
    limit = spec.get("max_chars", 1200)
    if len(text) > limit:
        errors.append(f"{path} : texte trop long ({len(text)} caracteres, maximum {limit}).")
        text = text[:limit]
    return text


def _is_hex_color(text: str) -> bool:
    if len(text) != 7 or not text.startswith("#"):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in text[1:])


def normalize(raw, host: str, target: str, *, path: str, audio_ready: bool = False):
    """Liste brute -> effets normalises (reglages completes et bornes).

    ``host`` est la cible declaree dans le projet (``layer`` ou ``scene``) et
    ``target`` le type de calque (``text``/``image``) ou ``scene``. L'entree est
    tolérante (forme courte ``"glitch_slices"``, reglages partiels, valeurs hors
    bornes) mais rien n'est jamais invente : un identifiant inconnu est une
    erreur, un reglage inconnu est signale.

    Retourne ``(effets, erreurs, avertissements)``. Utilise par la validation
    (erreurs bloquantes) ET par la resolution (le rendu ne recoit que des
    valeurs completes) : une seule implementation de la norme.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if raw in (None, "", []):
        return [], errors, warnings
    if not isinstance(raw, list):
        errors.append(f"{path} : liste d'effets attendue, recu {type(raw).__name__}.")
        return [], errors, warnings
    if len(raw) > MAX_EFFECTS_PER_TARGET:
        errors.append(
            f"{path} : {len(raw)} effets, maximum {MAX_EFFECTS_PER_TARGET} par cible. "
            "Retirez-en ou regroupez-les sur une autre scene."
        )
    out: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(raw[: MAX_EFFECTS_PER_TARGET + 8]):
        tag = f"{path}[{index}]"
        if isinstance(item, str):
            # Forme courte : "glitch_slices" -> reglages par defaut.
            item = {"id": item}
        if not isinstance(item, dict):
            errors.append(f"{tag} : objet attendu ({{'id': ..., 'params': {{}}}}).")
            continue
        effect_id = str(item.get("id", "") or "").strip()
        effect = _BY_ID.get(effect_id)
        if effect is None:
            errors.append(
                f"{tag}.id : effet inconnu {effect_id!r}. Disponibles : {', '.join(ids())}."
            )
            continue
        if effect_id in seen:
            errors.append(f"{tag} : effet {effect_id!r} declare deux fois sur la meme cible.")
            continue
        seen.add(effect_id)
        if host == "layer":
            if "layer" not in effect["scopes"]:
                errors.append(
                    f"{tag} : {effect_id} ne s'applique pas a un calque "
                    f"(portees : {', '.join(effect['scopes'])})."
                )
                continue
            if target not in effect["targets"]:
                errors.append(
                    f"{tag} : {effect_id} est prevu pour un calque "
                    f"{' ou '.join(effect['targets'])}, pas {target!r}."
                )
                continue
            scope = "layer"
        else:
            allowed = [s for s in effect["scopes"] if s in ("scene", "overlay")]
            if not allowed:
                errors.append(
                    f"{tag} : {effect_id} ne s'applique pas a une scene "
                    f"(portees : {', '.join(effect['scopes'])})."
                )
                continue
            # Un effet plein cadre declare sur une scene garde sa portee overlay ;
            # un effet qui emballe la scene reste de portee scene.
            scope = "overlay" if "overlay" in allowed else "scene"
        if effect["needs_audio"] and not audio_ready:
            warnings.append(
                f"{tag} : {effect_id} mesure l'audio reelle ; sans musique ni voix active "
                "dans Reglages > Audio, il se comportera comme un mouvement regulier."
            )
        params_in = item.get("params") or {}
        if not isinstance(params_in, dict):
            errors.append(f"{tag}.params : objet attendu, recu {type(params_in).__name__}.")
            params_in = {}
        known = {p["key"] for p in effect["params"]}
        for extra in [k for k in params_in if k not in known]:
            warnings.append(f"{tag}.params.{extra} : reglage inconnu pour {effect_id}, ignore.")
        params = {}
        for spec in effect["params"]:
            raw_value = params_in.get(spec["key"], spec["default"])
            params[spec["key"]] = _coerce(
                effect, spec, raw_value, f"{tag}.params.{spec['key']}", errors, warnings
            )
        out.append(
            {
                "id": effect_id,
                "label": effect["label"],
                "scope": scope,
                "needs_audio": bool(effect["needs_audio"]),
                "params": params,
            }
        )
    return out, errors, warnings
