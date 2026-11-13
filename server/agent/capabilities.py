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


def _template_structure(project: dict) -> list[dict]:
    """Identifiants ciblables sans copier les textes de démonstration."""
    out = []
    for scene in project.get("content", {}).get("scenes", []):
        out.append(
            {
                "scene": scene.get("id"),
                "label": scene.get("label", ""),
                "duration": scene.get("duration"),
                "layers": [
                    {"id": layer.get("id"), "role": layer.get("role", ""), "type": layer.get("type"),
                     "hidden": bool(layer.get("hidden"))}
                    for layer in scene.get("layers", [])
                    if isinstance(layer, dict)
                ],
            }
        )
    return out


def _templates() -> list[dict]:
    out = []
    for item in library_mod.list_library():
        try:
            structure = _template_structure(library_mod.get_project(item["id"]))
        except Exception:  # noqa: BLE001 - modèle illisible : pas de structure, jamais fatal
            structure = []
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
                "structure": structure,
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
            "transition_types": list(schema.TRANSITION_TYPES),
            "transition_frames_max": schema.TRANSITION_FRAMES_MAX,
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
        "L'écriture et l'exécution de nouveau code React/Remotion : pas de bac à sable livré. "
        "Les compositions nouvelles se créent en JSON v2 validé, avec les calques et effets existants.",
        "La vision : aucun modèle visuel requis ni image envoyée. project_review mesure le DOM et les "
        "logs sur quelques frames, propose des corrections et recontrôle techniquement ; un humain vérifie les aperçus.",
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
    lines.append(
        f"- Transition d'entrée d'une scène (set_scene) : transition.type "
        f"{', '.join(fmt['transition_types'])} ; transition.frames 0-{fmt['transition_frames_max']} "
        "(12-20 conseillé, 1re scène : none). Chevauchement au rendu, chronologie inchangée."
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
    lines.extend(_director_craft_lines(compact=True))
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
        f"transition set_scene : transition.type {', '.join(fmt['transition_types'])} · frames 0-{fmt['transition_frames_max']}",
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


AUTOPILOT_EXAMPLES = [
    {
        "prompt": "Vidéo motivante pour oser commencer, sans voix.",
        "plan": {
            "type": "autopilot_plan", "summary": "Récit du doute à l'action, lettres cinétiques, étalonnage chaud.",
            "template_id": "recit-cinematique",
            "script": [
                {"scene_id": "s1", "layer_id": "title", "text": "Et si tu osais ?"},
                {"scene_id": "s1", "layer_id": "subtitle", "text": "Tout commence ici."},
                {"scene_id": "s2", "layer_id": "title", "text": "Tu attends le bon moment."},
                {"scene_id": "s2", "layer_id": "subtitle", "text": "Demain ressemble à hier."},
                {"scene_id": "s3", "layer_id": "title", "text": "Le doute grandit."},
                {"scene_id": "s3", "layer_id": "subtitle", "text": "L'envie reste là."},
                {"scene_id": "s4", "layer_id": "title", "text": "Fais un premier pas."},
                {"scene_id": "s4", "layer_id": "subtitle", "text": "Petit, mais réel."},
                {"scene_id": "s5", "layer_id": "title", "text": "Commence aujourd'hui."},
                {"scene_id": "s5", "layer_id": "subtitle", "text": "La suite t'appartient."},
            ],
            "design": [
                {"op": "set_theme", "path": "accent_color", "value": "#E8B46A"},
                {"op": "set_effects", "scene_id": "s1", "layer_id": "title", "effects": ["kinetic_letters"]},
                {"op": "set_effects", "scene_id": "s5",
                 "effects": [{"id": "color_grade", "params": {"look": "teal_orange"}}]},
            ],
            "voice": None, "export": {"name": "oser"},
        },
    },
    {
        "prompt": "Présente mon carnet sobrement, sans médias ni voix.",
        "plan": {
            "type": "autopilot_plan", "summary": "Présentation épurée, entrée lettrée douce, sépia léger.",
            "template_id": "showcase-cinematique",
            "script": [
                {"scene_id": "s1", "layer_id": "title", "text": "Une place pour vos idées."},
                {"scene_id": "s1", "layer_id": "subtitle", "text": "Votre carnet."},
                {"scene_id": "s2", "layer_id": "title", "text": "Une page. Une envie."},
                {"scene_id": "s2", "layer_id": "subtitle", "text": "Notez ce qui vous inspire."},
                {"scene_id": "s3", "layer_id": "title", "text": "Faites le premier trait."},
                {"scene_id": "s3", "layer_id": "subtitle", "text": "Les idées prennent forme."},
                {"scene_id": "s4", "layer_id": "title", "text": "À vous d'écrire."},
                {"scene_id": "s4", "layer_id": "subtitle", "text": "Découvrez le carnet."},
            ],
            "design": [
                {"op": "set_theme", "path": "accent_color", "value": "#C9A227"},
                {"op": "set_effects", "scene_id": "s1", "layer_id": "title", "effects": ["kinetic_letters"]},
                {"op": "set_effects", "scene_id": "s4",
                 "effects": [{"id": "color_grade", "params": {"look": "sepia"}}]},
            ],
            "voice": None, "export": {"name": "carnet"},
        },
    },
    {
        "prompt": "Citation percutante sur le courage, style énergique, sans voix.",
        "plan": {
            "type": "autopilot_plan", "summary": "Citation choc : lettres cinétiques, emphase, étalonnage froid.",
            "template_id": "citation-cinematique",
            "script": [
                {"scene_id": "s1", "layer_id": "hook", "text": "Le courage n'est pas l'absence de peur"},
                {"scene_id": "s1", "layer_id": "hook-caption", "text": "mindset"},
                {"scene_id": "s2", "layer_id": "quote", "text": "C'est décider de continuer malgré elle."},
                {"scene_id": "s2", "layer_id": "author", "text": "— Anonyme"},
                {"scene_id": "s3", "layer_id": "reveal", "text": "Agir"},
                {"scene_id": "s3", "layer_id": "reveal-note", "text": "Passe à l'action aujourd'hui"},
            ],
            "design": [
                {"op": "set_theme", "path": "accent_color", "value": "#2B6CE6"},
                {"op": "set_effects", "scene_id": "s1", "layer_id": "hook", "effects": ["kinetic_letters"]},
                {"op": "set_layer", "scene_id": "s2", "layer_id": "quote", "path": "emphasis", "value": ["continuer"]},
                {"op": "set_effects", "scene_id": "s3",
                 "effects": [{"id": "color_grade", "params": {"look": "bleute"}}]},
            ],
            "voice": None, "export": {"name": "courage"},
        },
    },
]


def structure_lines(templates: list[dict], *, detailed: bool = True) -> list[str]:
    lines = []
    for template in templates:
        scenes = []
        for scene in template.get("structure", []):
            layers = ",".join(
                f"{layer['id']}:{layer['type']}" + ("(masqué)" if layer.get("hidden") else "")
                for layer in scene.get("layers", [])
            )
            scenes.append(f"{scene['scene']} {scene['label']} {scene['duration']}s [{layers}]")
        description = f" {template.get('description', '')}" if detailed else ""
        lines.append(f"{template['id']}:{description} " + ("; ".join(scenes) or "get_template requis"))
    return lines


def autopilot_grounding(manifest: dict | None = None, *, compact: bool = False) -> str:
    manifest = manifest or build()
    lines = ["GUIDE AUTOPILOTE — catalogue réel, choisir selon l'intention, pas toujours une citation."]
    lines.extend(structure_lines(manifest["templates"], detailed=False))
    lines.append("EFFETS (id:portée/cible ; réglages exacts via list_effects, défauts si params absent) :")
    for effect in manifest["effects"]["effects"]:
        lines.append(f"{effect['id']}:{'/'.join(effect['scopes'])}/{'/'.join(effect['targets'])}"
                     + (" audio requis" if effect["needs_audio"] else ""))
    lines += ["POLICES : " + ", ".join(f["id"] for f in manifest["fonts"] if f["usable"])]
    lines += _director_craft_lines(compact=compact)
    lines += [
        "ASSETS LOCAUX : list_assets kind=video|image|audio ou search_assets pour choisir un vrai media://. "
        "Le nom renseigne le thème, pas une analyse visuelle ; licence inconnue à signaler. "
        "B-roll en background.media, image via set_layer media ET hidden=false sur visual. "
        "Musique via set_audio music ET enabled=true, music_volume=0.12 sous la voix, "
        "music_fade_in=0.6/music_fade_out=1. Aucun média disponible : dégradé, silence, refs vides.",
    ]
    # Exemples few-shot : riches en mode détaillé, un seul en mode compact pour
    # tenir dans la fenêtre d'un petit modèle. Le marqueur reste dans les deux.
    ids = {t["id"] for t in manifest["templates"]}
    examples = [e for e in AUTOPILOT_EXAMPLES if e["plan"]["template_id"] in ids]
    if compact:
        examples = examples[:1]
    if examples:
        lines.append("EXEMPLES VALIDÉS (adapte contenu, voix, médias et style au prompt réel ; "
                     "design riche et cohérent, pas un simple set_theme) :")
        for example in examples:
            lines.append(json.dumps(example["plan"], ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def _director_craft_lines(compact: bool = False) -> list[str]:
    """Le métier de réalisateur : comment composer un montage impressionnant et
    cohérent avec les briques réelles du studio. Version condensée pour les
    petites fenêtres de contexte."""
    if compact:
        return [
            "RÉALISATION : une idée/scène, titres <=8 mots, sous-titres <=12 ; accroche 2-3s puis "
            "progression/déclic/conclusion. Anime les titres (kinetic_letters/spring_pop/mask_reveal), "
            "emphasis sur les mots forts, parallax_depth/perspective_dolly pour le volume, étalonnage "
            "color_grade, shine pour un reflet. 1-3 effets COHÉRENTS/cible, palette et accent uniques, "
            "B-roll en zoom_slow/zoom_out, musique 0.12 sous la voix. Remplis tous les textes visibles. "
            "Transition entre scènes : set_scene transition.type (fade/wipe/zoom/push/slide_*/dip_black), "
            "transition.frames 12-20 ; 1re scène none. "
            "Sous-titres calés sur la voix : \"captions\":true.",
        ]
    return [
        "RÉALISATION — compose un montage, ne remplis pas un template :",
        "  COMPOSITION/RYTHME : une idée/scène, titres <=8 mots, sous-titres <=12 ; accroche 2-3s, "
        "progression/déclic/conclusion. Remplis tous les textes.",
        "  MOUVEMENT : titres kinetic_letters/spring_pop/mask_reveal ; parallax_depth/"
        "perspective_dolly ; B-roll zoom_slow/zoom_out.",
        "  TRANSITIONS : set_scene transition.type (fade/dip_black/slide_*/wipe/zoom/push) + "
        "transition.frames 12-20 ; 1re scène none.",
        "  SOUS-TITRES : \"captions\":true dans le plan → sous-titres cinétiques calés sur la voix "
        "(alignement énergie automatique, aucun texte inventé).",
        "  LUMIÈRE/COULEUR : palette + accent uniques ; color_grade (teal_orange/bleute/sepia/"
        "noir_blanc) ; shine, light_leak, vignette.",
        "  TYPO/EMPHASE : emphasis mots forts, stagger mot/lettre, letter_spacing négatif "
        "sur gros titres.",
        "  EFFETS/SON : 1-3 effets COHÉRENTS/cible ; audio_pulse si musique ; "
        "musique 0.12 sous voix, fondus courts. Langage visuel unique.",
    ]


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
