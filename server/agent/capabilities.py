"""Manifeste des capacités réelles du studio.

Ce module répond à une question précise : qu'est-ce que l'agent peut
 honnêtement proposer d'appliquer aujourd'hui . Trois niveaux sont distingués,
comme l'exige le cahier des charges :

1. ce que la documentation décrit (corpus ``skills/``) ;
2. ce dont le projet dispose comme dépendance (``web/package.json``) ;
3. ce que notre renderer implémente et ce que l'éditeur expose.

Une technique documentée mais absente de la liste 3 n'est pas disponible :
l'agent doit le dire, pas le faire croire.
"""
from __future__ import annotations

import json
from typing import Any

from shortvideos import batch as batch_mod
from shortvideos import effects as effects_mod
from shortvideos import fonts as fonts_mod
from shortvideos import schema
from shortvideos.validation import V2_LAYER_TYPES

from .. import library as library_mod
from .. import media as media_mod
from ..security import MEDIA_DIR

# Inventaire borné : le modèle n'a jamais besoin de connaître 500 fichiers.
MAX_MEDIA_IN_LIST = 40


def _installed_packages() -> dict[str, str]:
    from ..security import ROOT

    path = ROOT / "web" / "package.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {**data.get("dependencies", {}), **data.get("devDependencies", {})}


def _media_inventory(limit: int = MAX_MEDIA_IN_LIST) -> list[dict]:
    files = sorted(
        (p for p in MEDIA_DIR.iterdir() if p.is_file() and not p.name.endswith(".part")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit] if MEDIA_DIR.is_dir() else []
    out = []
    for path in files:
        prov = media_mod.provenance_of(path.stem)
        kind = (prov.get("content_type") or "").split("/")[0] or "file"
        out.append(
            {
                "ref": f"media://{path.stem}",
                "name": prov.get("filename") or path.name,
                "kind": kind,
                "licence": prov.get("licence") or "inconnue",
                "source": prov.get("source") or "",
            }
        )
    return out


def _models() -> list[dict]:
    from ..api.studio import MODEL_INFO  # import tardif : évite toute dépendance circulaire

    out = []
    for model_id, version in schema.MODELS.items():
        info = MODEL_INFO.get(model_id, {})
        out.append(
            {
                "id": model_id,
                "version": version,
                "label": info.get("label", model_id),
                "description": info.get("description", ""),
                "composition": model_id.replace("_", "-"),
                "editable": info.get("editable", []),
                "limits": info.get("limits", []),
                "recommended_duration": info.get("recommended_duration", []),
                "aspect_ratios": info.get("aspect_ratios", []),
            }
        )
    return out


def _templates() -> list[dict]:
    out = []
    for item in library_mod.list_library():
        out.append(
            {
                "id": item["id"],
                "label": item.get("label", item["id"]),
                "description": item.get("description", ""),
                "builtin": bool(item.get("builtin")),
                "model_id": item.get("model_id"),
                "scenes": item.get("scenes"),
                "duration": item.get("duration"),
                "size": f"{item.get('width')}x{item.get('height')}",
                "fps": item.get("fps"),
            }
        )
    return out


def _fonts() -> list[dict]:
    out = []
    for family in fonts_mod.families():
        out.append(
            {
                "id": family["id"],
                "label": family["label"],
                "weights": [w["weight"] for w in family["weights"] if w["available"]],
                "license": family.get("license") or "inconnue",
                "usable": bool(family["complete"]),
            }
        )
    return out


def _effects_brief() -> dict:
    """Catalogue d'effets reduit : ce qui sert a ecrire une proposition.

    Les descriptions redigees restent accessibles par l'outil de lecture
    ``list_effects`` ; le manifeste ne porte que l'identifiant, la portee, les
    cibles, le besoin d'audio et les reglages avec leurs bornes.
    """
    brief = []
    for fx in effects_mod.all_effects():
        brief.append(
            {
                "id": fx["id"],
                "label": fx["label"],
                "category": fx["category"],
                "scopes": fx["scopes"],
                "targets": fx["targets"],
                "needs_audio": bool(fx["needs_audio"]),
                "params": {
                    p["key"]: {
                        k: p[k]
                        for k in ("type", "default", "min", "max", "step", "options")
                        if p.get(k) is not None
                    }
                    for p in fx["params"]
                },
            }
        )
    return {
        "max_per_target": effects_mod.MAX_EFFECTS_PER_TARGET,
        "categories": [{"id": k, "label": v} for k, v in effects_mod.CATEGORIES],
        "effects": brief,
    }


def build() -> dict:
    """Manifeste complet, tel qu'il est renvoyé par ``GET /api/agent/capabilities``."""
    deps = _installed_packages()
    remotion_packages = sorted(k for k in deps if k.startswith("@remotion/"))
    models = _models()
    editable = sorted({item for model in models for item in model["editable"]})
    manifest = {
        "project_format": {
            "version": schema.SCHEMA_VERSION_V2,
            "models": [m["id"] for m in models],
            "layer_types": list(V2_LAYER_TYPES),
            "animation_in": list(schema.ANIM_IN),
            "animation_out": list(schema.ANIM_OUT),
            "animation_units": list(schema.ANIM_UNITS),
            "easings": list(schema.EASINGS),
            "background_fit": list(schema.BACKGROUND_FIT),
            "background_animation": list(schema.BACKGROUND_ANIM),
            "alignments": list(schema.ALIGNMENTS),
            "directions": list(schema.DIRECTIONS),
            "scene_duration_range": [schema.SCENE_DURATION_MIN, schema.SCENE_DURATION_MAX],
            "total_duration_range": [schema.TOTAL_DURATION_MIN, schema.TOTAL_DURATION_MAX],
            "media_references": "media://<id> uniquement ; aucun chemin Windows dans un projet",
            "resolved_block": "calculé par le serveur, jamais accepté depuis un projet fourni",
            "effects_max_per_target": effects_mod.MAX_EFFECTS_PER_TARGET,
        },
        "models": models,
        "templates": _templates(),
        "fonts": _fonts(),
        "effects": _effects_brief(),
        "media": _media_inventory(),
        "editor_controls": editable,
        "batch": {
            "fillable_fields_example": [f["key"] for f in _batch_fields()],
            "policy": dict(batch_mod.POLICY),
            "options": {"background": ["auto", "column", "none"], "music": ["auto", "column", "none"]},
        },
        "dependencies": {
            "remotion": deps.get("remotion", "absent"),
            "remotion_packages": remotion_packages,
            "react": deps.get("react", "absent"),
        },
        "knowledge_sources": _knowledge_sources(),
        "not_available": _not_available(deps),
    }
    return manifest


def _batch_fields() -> list[dict]:
    """Champs remplissables du modèle intégré : sert d'exemple au manifeste."""
    try:
        template = library_mod.builtin_project("citation-cinematique")
        return batch_mod.fillable_fields(template)
    except Exception:  # noqa: BLE001 - le manifeste ne doit jamais échouer
        return []


def _knowledge_sources() -> list[dict]:
    from .. import skills as skills_mod

    if not skills_mod.is_installed():
        return []
    return [
        {
            "id": entry["id"],
            "title": entry["title"],
            "version": entry.get("version") or "inconnue",
            "documents": len(entry.get("docs", [])) + 1,
            "nature": "documentation",
        }
        for entry in skills_mod.list_skills()
    ]


def _not_available(deps: dict | None = None) -> list[str]:
    """Ce que l'agent doit refuser de promettre, avec l'alternative."""
    deps = deps or {}
    installed = {k for k in deps if k.startswith("@remotion/")}
    blocked = [
        "Les effets du catalogue (liste « effets » ci-dessus) sont les seuls effets "
        "applicables : un nom de preset vu dans la documentation (chromaticAberration(), "
        "pageTurn(), shatter(), lensBlur(), sphere(), cylinder(), fractalNoise(), lut()) "
        "n'existe pas ici, sauf l'identifiant equivalent du catalogue.",
        "Les effets des paquets @remotion/* non installés (filtres GPU, transitions, "
        "3D réelle avec @remotion/three, sous-titres automatiques, Lottie, GIF, Player avancé) : "
        "la documentation les décrit mais le renderer ne les implémente pas.",
        "L'écriture d'une nouvelle composition Remotion en code : mode avancé non livré.",
        "La compréhension du contenu visuel ou sonore d'un média : aucune capacité "
        "de vision ni d'annotation automatique.",
        "Le choix d'un chemin disque, l'installation d'une dépendance, la suppression "
        "d'un fichier ou le lancement d'un lot sans validation humaine.",
    ]
    extra = sorted(
        name for name in (
            "@remotion/transitions", "@remotion/google-fonts", "@remotion/preload",
            "@remotion/paths", "@remotion/shapes", "@remotion/install-whisper-corrector",
        )
        if name not in installed
    )
    if extra:
        blocked.append(
            "Paquets explicitement documentés mais absents de web/package.json : "
            + ", ".join(extra) + " — les proposer exige d'abord d'ajouter la dépendance."
        )
    return blocked


def _effects_lines(effects: dict) -> list[str]:
    """Vocabulaire des effets pour le prompt : identifiants et portees.

    Le detail des reglages (bornes, types) reste dans l'outil de lecture
    ``list_effects`` : la liste complete tiendrait pas dans la fenetre d'un
    petit modele local, et un identifiant invente est refuse de toute facon.
    """
    items = effects["effects"]
    layer_fx = [f for f in items if "layer" in f["scopes"]]
    scene_fx = [f for f in items if "scene" in f["scopes"] or "overlay" in f["scopes"]]

    def render(entry: dict) -> str:
        marks = []
        if entry["needs_audio"]:
            marks.append("audio")
        if entry["scopes"] == ["layer"]:
            marks.append("calque:" + "/".join(entry["targets"]))
        elif "layer" in entry["scopes"]:
            marks.append("calque+scene")
        else:
            marks.append("scene" if "scene" in entry["scopes"] else "overlay")
        return f"{entry['id']} ({','.join(marks)})"

    audio = [f["id"] for f in items if f["needs_audio"]]
    return [
        f"- Effets reels (catalogue serveur, au plus {effects['max_per_target']} par cible) : "
        "l'operation set_effects les applique, un identifiant hors de cette liste est refuse.",
        "  calques : " + ", ".join(render(f) for f in layer_fx),
        "  scenes : " + ", ".join(render(f) for f in scene_fx),
        "- Reglages d'un effet : {"
        "\"id\":\"…\",\"params\":{…}}"
        " ; les cles, types et bornes sont donnes par l'outil list_effects "
        "(la forme courte \"id\" seul prend les reglages par defaut).",
        "- Effets qui mesurent la vraie piste audio : "
        + (", ".join(audio) if audio else "aucun")
        + " ; sans musique ni voix active dans Reglages > Audio, previens qu'ils seront reguliers.",
    ]


def _prompt_lines(manifest: dict, max_chars: int = 6000) -> list[str]:
    lines: list[str] = []
    fmt = manifest["project_format"]
    models = manifest["models"]
    lines.append("CAPACITÉS RÉELLES DU STUDIO (seul ce liste est applicable)")
    lines.append(
        f"- Format projet v{fmt['version']} ; modèles de composition : "
        f"{', '.join(fmt['models'])}. Un model.id hors de cette liste est refusé."
    )
    lines.append(
        "- Calques : " + ", ".join(fmt["layer_types"])
        + f". Entrée : {', '.join(fmt['animation_in'])}. Sortie : {', '.join(fmt['animation_out'])}."
    )
    lines.append(
        f"- Unités d'animation : {', '.join(fmt['animation_units'])}. Courbes : "
        f"{', '.join(fmt['easings'])}."
    )
    lines.append(
        f"- Fond d'une scène : fit {', '.join(fmt['background_fit'])}, animation "
        f"{', '.join(fmt['background_animation'])}."
    )
    lo, hi = fmt["scene_duration_range"]
    tlo, thi = fmt["total_duration_range"]
    lines.append(f"- Durée : scène entre {lo} et {hi} s, total entre {tlo} et {thi} s (12-15 s conseillé).")
    lines.append(
        f"- Références média : {fmt['media_references']}. {fmt['resolved_block']}."
    )
    lines.append("- Temps exprimés en FRAMES (animation.start_frames / in_frames / out_frames / stagger_frames).")
    fonts = ", ".join(
        f"{f['id']} ({'/'.join(str(w) for w in f['weights']) or 'poids inconnu'})"
        for f in manifest["fonts"]
    )
    lines.append(f"- Polices du catalogue sous licence : {fonts}.")
    lines.extend(_effects_lines(manifest["effects"]))
    templates = "; ".join(
        f"{t['id']}=« {t['label']} », {t['scenes']} scènes/{t['duration']} s"
        for t in manifest["templates"]
    )
    lines.append(f"- Modèles de la bibliothèque : {templates or 'aucun'}.")
    comps = "; ".join(
        f"{m['id']} -> composition « {m['composition']} » (éditable : {', '.join(m['editable'][:8])}…)"
        for m in models
    )
    lines.append(f"- Compositions enregistrées : {comps}.")
    lines.append(
        "- Au-delà de cette liste, un effet documenté n'est PAS disponible : "
        "le dire, proposer une alternative applicable."
    )
    blocked = " / ".join(manifest["not_available"][:2])
    lines.append(f"- Explicitement indisponible : {blocked}")
    media = manifest["media"][:10]
    if media:
        lines.append(
            "- Médias récents (refs utilisables) : "
            + "; ".join(f"{m['ref']} ({m['name']}, {m['kind']}, licence {m['licence']})" for m in media)
        )
    else:
        lines.append("- Aucun média importé : ne proposer aucun fond, logo ou musique.")
    return _budget(lines, max_chars)


def _prompt_lines_production(manifest: dict, max_chars: int = 2500) -> list[str]:
    batch = manifest["batch"]
    lines = [
        "PRODUCTION PAR LOTS — ce que le moteur sait faire",
        f"- Champs remplissables d'un modèle : {', '.join(batch['fillable_fields_example'][:20])}.",
        f"- Options médias : background {batch['options']['background']}, music {batch['options']['music']}.",
        "- Règles : " + "; ".join(f"{k} = {v}" for k, v in batch["policy"].items()),
        "- Le plan est calculé par build_plan() ; aucune attribution inventée n'est applicable.",
        "- Aucun export n'est lancé depuis l'assistant : l'utilisateur appuie lui-même.",
    ]
    return _budget(lines, max_chars)


def _budget(lines: list[str], max_chars: int) -> list[str]:
    out: list[str] = []
    used = 0
    for line in lines:
        used += len(line)
        if used > max_chars:
            out.append("… manifeste tronqué (budget de contexte) : la liste complète est dans /api/agent/capabilities")
            break
        out.append(line)
    return out


def compact_prompt_block(manifest: dict | None = None, max_chars: int = 1500) -> str:
    """Identifiants et valeurs stricts, sans prose : pour les petites fenêtres.

    Utilisé quand le projet + les règles ne tiennent pas dans la fenêtre du
    modèle local. Les médias et les champs détaillés restent accessibles aux
    outils de lecture (list_assets, get_batch_fields).
    """
    manifest = manifest or build()
    fmt = manifest["project_format"]
    scene_lo, scene_hi = fmt["scene_duration_range"]
    total_lo, total_hi = fmt["total_duration_range"]
    lines = [
        "CAPACITÉS STRICTES DU STUDIO (rien d'autre n'est applicable)",
        f"modeles : {', '.join(fmt['models'])}",
        f"calques : {', '.join(fmt['layer_types'])} · entree : {', '.join(fmt['animation_in'])}"
        f" · sortie : {', '.join(fmt['animation_out'])}"
        f" · unite : {', '.join(fmt['animation_units'])} · courbe : {', '.join(fmt['easings'])}",
        f"fond : fit {', '.join(fmt['background_fit'])} · animation {', '.join(fmt['background_animation'])}"
        f" · alignement {', '.join(fmt['alignments'])} · direction {', '.join(fmt['directions'])}",
        f"duree : scene {scene_lo}-{scene_hi} s, total {total_lo}-{total_hi} s · temps en FRAMES",
        f"media : {fmt['media_references']} · bloc « resolved » : refusé",
        "polices : " + ", ".join(
            f"{f['id']} ({'/'.join(str(w) for w in f['weights']) or 'poids inconnu'})"
            for f in manifest["fonts"]
        ),
        "modeles bibliotheque : " + (
            ", ".join(f"{t['id']} [{t['model_id']}, {t['scenes']} scènes, {t['duration']} s]"
                      for t in manifest["templates"]) or "aucun"
        ),
        "effets (set_effects, "
        f"{manifest['effects']['max_per_target']} par cible au maximum, reglages par defaut si « params » absent) : "
        + " ".join(f["id"] for f in manifest["effects"]["effects"]),
        "INDISPONIBLE : " + " / ".join(_short_blocked(manifest["not_available"])),
    ]
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…"


def _short_blocked(not_available: list[str], max_chars: int = 300) -> list[str]:
    """Résumé des interdits : assez pour qu'un petit modèle ne promette pas."""
    keys = ["catalogue", "@remotion", "nouvelle composition", "vision", "chemin disque", "installation"]
    out: list[str] = []
    used = 0
    for item in not_available:
        first = item.split(" : ")[0].split("（")[0].strip()[:90]
        if not any(k in item for k in keys) and out:
            continue
        if used + len(first) > max_chars:
            break
        used += len(first)
        out.append(first)
    return out or ["effets GPU et paquets @remotion/* non installés"]


def prompt_block(manifest: dict | None = None, max_chars: int = 6000) -> str:
    manifest = manifest or build()
    return "\n".join(_prompt_lines(manifest, max_chars))


def production_prompt_block(manifest: dict | None = None) -> str:
    manifest = manifest or build()
    return "\n".join(_prompt_lines_production(manifest))


def summary_for_ui(manifest: dict) -> dict[str, Any]:
    """Vue compacte pour le panneau technique de l'interface."""
    return {
        "models": manifest["project_format"]["models"],
        "templates": [t["id"] for t in manifest["templates"]],
        "fonts": [f["id"] for f in manifest["fonts"]],
        "effects": [f["id"] for f in manifest["effects"]["effects"]],
        "effects_max_per_target": manifest["effects"]["max_per_target"],
        "media_count": len(manifest["media"]),
        "animation_in": manifest["project_format"]["animation_in"],
        "remotion": manifest["dependencies"]["remotion"],
        "remotion_packages": manifest["dependencies"]["remotion_packages"],
        "not_available": manifest["not_available"],
        "knowledge_sources": manifest["knowledge_sources"],
    }
