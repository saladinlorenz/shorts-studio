"""B-roll automatique : un visuel local choisi par thème, sans aucun LLM.

Le moteur rapproche les mots d'une scène (label + textes) des noms et dossiers
des médias déjà importés. Un visuel n'est posé que sur une correspondance franche
(au moins un mot-outil exclu, de longueur significative, partagé avec la scène),
et jamais par-dessus un fond ou un calque média déjà choisi.

Deux cibles, selon le modèle : l'emplacement « visual » masqué d'une scène
n'accepte qu'une image (il est rendu en <Img>) ; images et vidéos servent de fond
plein cadre (rendu <Img> ou <OffthreadVideo> selon l'extension). Tout est
best-effort : sans média pertinent, la scène garde le dégradé de la palette.
"""
from __future__ import annotations

import copy
import os
import re
import unicodedata

# Mots-outils français/anglais : sans valeur de thème, ils ne servent jamais de
# correspondance. La longueur minimale filtre déjà la plupart des formes courtes.
_STOPWORDS = frozenset("""
dans pour avec sans sous sont etre avoir fait fais tout toute tous toutes meme
aussi mais comme bien tres peu votre notre leur leurs elle elles nous vous plus
alors donc ainsi cela ceci voici voila quel quelle quels quelles quoi dont cest
dune jamais toujours encore deja apres avant pendant depuis vers chez
the and for with that this from your you are was were have has had not but all
any can will just into over such than then them they what when where which while
about above after again because before below between both during each few here
there these those through under until very own same too only more most other
some nor out off down up
""".split())

_MIN_TOKEN = 4
_IMAGE_VIDEO = ("image", "video")


def _tokens(text: str) -> set[str]:
    """Mots significatifs : accents retirés, casse ignorée, mots-outils exclus."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    words = re.split(r"[^a-z0-9]+", stripped.casefold())
    return {w for w in words if len(w) >= _MIN_TOKEN and w not in _STOPWORDS}


def _asset_tokens(asset: dict) -> set[str]:
    name = os.path.splitext(str(asset.get("name", "") or ""))[0]
    return _tokens(name) | _tokens(str(asset.get("folder", "") or ""))


def _scene_tokens(scene: dict) -> set[str]:
    tokens = _tokens(str(scene.get("label", "") or ""))
    for layer in scene.get("layers") or []:
        if isinstance(layer, dict) and layer.get("type") == "text":
            tokens |= _tokens(str(layer.get("text", "") or ""))
    return tokens


def _best_asset(keywords: set[str], pool: list, used: set[str], min_score: int) -> dict | None:
    """Meilleure correspondance : score décroissant, puis média non encore utilisé
    (variété entre scènes), puis référence (ordre déterministe)."""
    best, best_key = None, None
    for asset, tokens in pool:
        score = len(keywords & tokens)
        if score < min_score:
            continue
        ref = asset["ref"]
        key = (-score, ref in used, ref)
        if best_key is None or key < best_key:
            best, best_key = asset, key
    return best


def auto_broll(project: dict, assets: list[dict], *, min_score: int = 1) -> dict:
    """Pose un visuel local par scène sur correspondance de thème franche.

    Pur : ne touche ni au disque ni au projet d'origine (copie profonde).
    ``assets`` porte au moins {ref, name, kind} (« folder » optionnel) ; seules
    les images et vidéos en ``media://`` sont retenues. Jamais d'écrasement d'un
    fond ni d'un calque média déjà visible. Sans correspondance, scène inchangée.
    """
    project = copy.deepcopy(project)
    pool: list[tuple[dict, set[str]]] = []
    seen: set[str] = set()
    for asset in assets or []:
        ref = str(asset.get("ref", "") or "")
        if asset.get("kind") not in _IMAGE_VIDEO or not ref.startswith("media://") or ref in seen:
            continue
        seen.add(ref)
        tokens = _asset_tokens(asset)
        if tokens:
            pool.append((asset, tokens))
    if not pool:
        return project

    used: set[str] = set()
    for scene in project.get("content", {}).get("scenes", []):
        if not isinstance(scene, dict) or scene.get("hidden"):
            continue
        if str((scene.get("background") or {}).get("media", "") or ""):
            continue  # fond déjà choisi : jamais écrasé
        layers = scene.get("layers") or []
        if any(
            isinstance(layer, dict) and not layer.get("hidden")
            and layer.get("type") in _IMAGE_VIDEO and str(layer.get("media", "") or "")
            for layer in layers
        ):
            continue  # un calque média visible tient déjà lieu de visuel
        keywords = _scene_tokens(scene)
        if not keywords:
            continue
        asset = _best_asset(keywords, pool, used, min_score)
        if asset is None:
            continue
        slot = next(
            (layer for layer in layers
             if isinstance(layer, dict) and layer.get("type") == "image"
             and layer.get("hidden") and not str(layer.get("media", "") or "")),
            None,
        )
        if slot is not None and asset.get("kind") == "image":
            slot["media"] = asset["ref"]
            slot["hidden"] = False
        else:
            background = scene.setdefault("background", {})
            background["media"] = asset["ref"]
            background.setdefault("fit", "cover")
            background.setdefault("animation", "static")
        used.add(asset["ref"])
    return project