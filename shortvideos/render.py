"""Moteur de composition d'image (Pillow).

`compose_frame(project, t)` est la SOURCE UNIQUE de rendu :
l'apercu et l'export MP4 passent tous les deux par cette fonction,
ce qui garantit que l'apercu correspond au rendu exporte (meme code).

Aucune dependance a Tkinter ici : les images sont des objets PIL.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import timing as _timing
from .validation import FONTS_DIR

# Taille du cache de fonds : evite de recharger/disquer a chaque frame.
_BG_CACHE_MAX = 8
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_bg_cache: dict[tuple[str, float], Image.Image] = {}
_bg_order: list[tuple[str, float]] = []


def _hex_to_rgba(color: str, alpha: float) -> tuple[int, int, int, int]:
    """Convertit '#RRGGBB' + opacite 0..1 en tuple RGBA."""
    color = color.lstrip("#")
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return (r, g, b, int(round(255 * max(0.0, min(1.0, alpha)))))


def resolve_font(family: str, size: int) -> ImageFont.FreeTypeFont:
    """Charge une police (fichier du dossier Windows Fonts ou chemin absolu)."""
    key = (family, size)
    if key in _font_cache:
        return _font_cache[key]
    path = Path(family)
    if not path.exists():
        path = FONTS_DIR / family
    if not path.exists():
        # Fallback : la plus ancienne police disponible.
        for fallback in ("arialbd.ttf", "arial.ttf", "segoeuib.ttf"):
            candidate = FONTS_DIR / fallback
            if candidate.exists():
                path = candidate
                break
        else:
            raise RuntimeError(f"Police introuvable : {family}")
    font = ImageFont.truetype(str(path), size)
    _font_cache[key] = font
    return font


def _load_background(project: dict) -> Image.Image | None:
    """Charge le fond image en cache (recharge si le fichier change)."""
    path_str = project["content"].get("background_image", "")
    if not path_str.strip():
        return None
    path = Path(path_str)
    if not path.exists():
        return None  # validation.py signale l'erreur ; ici on laisse passer l'apercu
    mtime = path.stat().st_mtime
    key = (str(path), mtime)
    if key in _bg_cache:
        return _bg_cache[key]
    img = Image.open(path).convert("RGB")
    _bg_cache[key] = img
    _bg_order.append(key)
    while len(_bg_order) > _BG_CACHE_MAX:
        old = _bg_order.pop(0)
        _bg_cache.pop(old, None)
    return img


# Cache des covers haute resolution : une seule passe LANCZOS par image,
# ensuite chaque frame ne fait qu'un crop + un petit resize (rapide).
_cover_cache: dict[tuple, Image.Image] = {}
_cover_order: list[tuple] = []
_COVER_CACHE_MAX = 4


def _cover_base(img: Image.Image, width: int, height: int, zoom_max: float) -> Image.Image:
    """Cover du fond a la resolution maximale de zoom (calcule une seule fois)."""
    base_w = int(round(width * zoom_max))
    base_h = int(round(height * zoom_max))
    key = (id(img), img.size, base_w, base_h)
    cached = _cover_cache.get(key)
    if cached is not None:
        return cached
    ratio = max(base_w / img.width, base_h / img.height)
    new_w = max(base_w, int(round(img.width * ratio)))
    new_h = max(base_h, int(round(img.height * ratio)))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - base_w) // 2
    top = (new_h - base_h) // 2
    base = resized.crop((left, top, left + base_w, top + base_h))
    _cover_cache[key] = base
    _cover_order.append(key)
    while len(_cover_order) > _COVER_CACHE_MAX:
        _cover_cache.pop(_cover_order.pop(0), None)
    return base


def _load_logo(project: dict, width: int) -> Image.Image | None:
    """Charge et redimensionne le logo en cache (taille relative au cadre)."""
    logo_path = project["content"].get("logo", "").strip()
    if not logo_path or not Path(logo_path).exists():
        return None
    path = Path(logo_path)
    mtime = path.stat().st_mtime
    target_w = max(8, int(width * 0.18))
    key = (str(path), mtime, target_w)
    cached = _bg_cache.get(key)
    if cached is not None:
        return cached
    logo = Image.open(path).convert("RGBA")
    ratio = target_w / logo.width
    logo = logo.resize((target_w, max(1, int(logo.height * ratio))), Image.LANCZOS)
    _bg_cache[key] = logo
    _bg_order.append(key)
    while len(_bg_order) > _BG_CACHE_MAX:
        old = _bg_order.pop(0)
        _bg_cache.pop(old, None)
    return logo


def _resize_fast(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Redimensionne avec OpenCV (beaucoup plus rapide que PIL) si dispo."""
    if img.size == size:
        return img
    try:
        import cv2
        import numpy as np

        arr = np.asarray(img)
        out = cv2.resize(arr, size, interpolation=cv2.INTER_LINEAR)
        return Image.fromarray(out)
    except ImportError:
        return img.resize(size, Image.BILINEAR)


def _background_frame(base: Image.Image, width: int, height: int,
                      scale: float, zoom_max: float) -> Image.Image:
    """Extrait la frame de fond a l'echelle ``scale`` depuis le cover max.

    Le zoom se fait en recadrant une fenêtre plus petite dans le cover
    haute resolution puis en redimensionnant (rapide, cv2).
    """
    # Fenetre visible dans les coordonnees du cover max.
    win_w = width * zoom_max / scale
    win_h = height * zoom_max / scale
    win_w = min(win_w, base.width)
    win_h = min(win_h, base.height)
    left = (base.width - win_w) / 2
    top = (base.height - win_h) / 2
    box = (round(left), round(top), round(left + win_w), round(top + win_h))
    cropped = base.crop(box)
    if cropped.size != (width, height):
        cropped = _resize_fast(cropped, (width, height))
    return cropped


def _default_background(width: int, height: int) -> Image.Image:
    """Fond de repli (degrade sombre) si aucune image n'est fournie."""
    img = Image.new("RGB", (width, height), (18, 18, 24))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        shade = int(18 + 30 * (y / height))
        draw.line([(0, y), (width, y)], fill=(shade, shade, shade + 8))
    return img


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Habille le texte a la largeur max, en tenant compte de la largeur reelle des mots."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.getlength(candidate) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


_measure_cache: dict[tuple, dict] = {}
_MEASURE_CACHE_MAX = 8


def measure_text(project: dict) -> dict:
    """Mesure le bloc de texte (habillage + hauteurs) pour la validation.

    Resultat mis en cache : l'export appelle cette fonction a chaque frame.
    """
    width = int(project["export"]["width"])
    height = int(project["export"]["height"])
    font_family = project["theme"]["font_family"]
    raw_size = int(project["theme"]["font_size"])
    pos_width = float(project["position"]["width"])
    text = project["content"]["text"]
    author = project["content"].get("author", "").strip()
    key = (text, author, font_family, raw_size, pos_width, width, height)
    cached = _measure_cache.get(key)
    if cached is not None:
        return cached

    font_size = int(round(raw_size * height / 1920))
    font = resolve_font(font_family, max(8, font_size))
    max_width = int(pos_width * width)
    lines = _wrap_text(text, font, max_width)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + int(font_size * 0.25)
    block_height = line_height * len(lines)
    if author:
        block_height += int(line_height * 0.75)
    available_height = int(height * 0.62)
    result = {
        "lines": len(lines),
        "block_height": block_height,
        "available_height": available_height,
        "fits": block_height <= available_height,
        "max_width": max_width,
        "line_height": line_height,
        "font": font,
        "font_size": font_size,
        "wrapped": lines,
    }
    if len(_measure_cache) >= _MEASURE_CACHE_MAX:
        _measure_cache.pop(next(iter(_measure_cache)), None)
    _measure_cache[key] = result
    return result


def compose_frame(project: dict, t: float) -> Image.Image:
    """Compose la frame a l'instant t (secondes). Retourne une image PIL RGB.

    C'est la fonction commune a l'apercu et a l'export.
    """
    width = int(project["export"]["width"])
    height = int(project["export"]["height"])

    # 1. Fond (image ou repli), avec zoom lent eventuel.
    scale = _timing.background_scale(t, project)
    bg = _load_background(project)
    if bg is None:
        frame = _default_background(width, height)
    else:
        from .timing import ZOOM_MAX
        base = _cover_base(bg, width, height, ZOOM_MAX)
        frame = _background_frame(base, width, height, scale, ZOOM_MAX)

    # 2. Logo (coin bas-droite, taille relative au cadre) - redimensionne en cache.
    logo = _load_logo(project, width)
    if logo is not None:
        margin = int(width * 0.04)
        frame = frame.convert("RGBA")
        frame.alpha_composite(logo, (width - logo.width - margin, height - logo.height - margin))
        frame = frame.convert("RGB")

    # 3. Texte (opacite + glissement selon timing).
    alpha = _timing.text_alpha(t, project)
    if alpha > 0.003:
        m = measure_text(project)
        font = m["font"]
        offset_y = _timing.text_offset_y(t, project)
        block_x = int(project["position"]["x"] * width)
        block_y = int(project["position"]["y"] * height) - m["block_height"] // 2 + offset_y

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        text_rgba = _hex_to_rgba(project["theme"]["text_color"], alpha)
        if project["theme"].get("shadow", True):
            shadow_rgba = (0, 0, 0, int(200 * alpha))
            y = block_y
            for line in m["wrapped"]:
                x = int(block_x - font.getlength(line) / 2)
                draw.text((x + 3, y + 3), line, font=font, fill=shadow_rgba)
                y += m["line_height"]
        y = block_y
        for line in m["wrapped"]:
            x = int(block_x - font.getlength(line) / 2)
            draw.text((x, y), line, font=font, fill=text_rgba)
            y += m["line_height"]

        author = project["content"].get("author", "").strip()
        if author:
            author_size = max(8, int(m["font_size"] * 0.5))
            author_font = resolve_font(project["theme"]["font_family"], author_size)
            label = f"— {author}"
            x = int(block_x - author_font.getlength(label) / 2)
            draw.text(
                (x, y + int(m["line_height"] * 0.15)),
                label, font=author_font,
                fill=_hex_to_rgba(project["theme"]["author_color"], alpha),
            )

        frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")

    return frame
