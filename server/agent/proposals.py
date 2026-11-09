"""Contrat des propositions de l'assistant.

Le modèle ne renvoie jamais un projet appliqué : il renvoie une proposition
typée, que ce module transforme en projet candidat.

Garanties imposées ici :
- les scènes et calques sont désignés par identifiants stables, jamais par
  leur position ;
- les opérations sont limitées à des chemins autorisés (aucune propriété
  secrète, aucun chemin disque, aucun identifiant de composition inventé) ;
- le projet candidat est construit sur une COPIE puis validé par la validation
  métier existante ;
- un bloc ``resolved`` fourni par le modèle est toujours retiré : il est
  calculé côté serveur ;
- une proposition partiellement invalide n'est jamais appliquée en silence.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from shortvideos import effects as effects_mod
from shortvideos import schema
from shortvideos.validation import validate_project

from ..security import MEDIA_DIR

PROPOSAL_TYPES = ("question", "project_new", "project_patch", "library_save", "batch_plan", "unavailable")

THEME_KEYS = set(schema.default_theme().keys())
EXPORT_KEYS = {"width", "height", "fps"}
VARIATION_KEYS = {"seed"}
SCENE_KEYS = {"duration", "label", "hidden", "background.fit", "background.animation", "background.media"}
LAYER_KEYS = {
    "text", "hidden", "locked", "opacity", "emphasis", "media",
    "style.font_family", "style.font_weight", "style.font_size", "style.line_height",
    "style.letter_spacing", "style.color", "style.accent_color", "style.stroke_color",
    "style.stroke_width", "style.shadow",
    "position.x", "position.y", "position.width", "position.align", "position.direction",
    "animation.in", "animation.out", "animation.unit", "animation.stagger_frames",
    "animation.start_frames", "animation.in_frames", "animation.out_frames",
    "animation.easing", "animation.distance",
    "animation.spring.damping", "animation.spring.stiffness", "animation.spring.mass",
}
SIGNATURE_KEYS = {
    "enabled", "media", "handle", "font_family", "font_weight", "font_size", "color",
    "logo_width", "position.x", "position.y", "start_frames", "in_frames",
}
AUDIO_KEYS = {
    "enabled", "music", "voice", "music_volume", "voice_volume",
    "music_fade_in", "music_fade_out",
}
ROLE_CHOICES = {"hook", "caption", "quote", "author", "reveal", "body", "mark"}

# Valeurs fermées : rejetées à l'opération plutôt qu'à la validation, pour que le
# message de réparation liste directement les choix possibles.
ENUM_PATHS = {
    "animation.in": schema.ANIM_IN,
    "animation.out": schema.ANIM_OUT,
    "animation.unit": schema.ANIM_UNITS,
    "animation.easing": schema.EASINGS,
    "position.align": schema.ALIGNMENTS,
    "position.direction": schema.DIRECTIONS,
    "background.fit": schema.BACKGROUND_FIT,
    "background.animation": schema.BACKGROUND_ANIM,
}

# Ops « constructeur » : passent par les aides de schema, jamais par du JSON libre.
CONSTRUCT_OPS = {"add_scene", "add_text_layer", "add_image_layer", "duplicate_scene", "remove_scene", "remove_layer"}

PROPOSAL_TTL = 3600.0


class ProposalError(Exception):
    """Rejet structuré : le détail est renvoyé au modèle pour réparation."""

    def __init__(self, errors: list[str], kind: str = "invalid_proposal"):
        super().__init__(" ; ".join(errors[:8]) or "Proposition invalide.")
        self.errors = errors
        self.kind = kind


def revision_of(project: dict) -> str:
    """Empreinte stable d'un projet : détection du conflit de révision."""
    try:
        payload = json.dumps(_canonical(project), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload = repr(sorted((project or {}).keys()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _canonical(node):
    if isinstance(node, dict):
        return {k: _canonical(v) for k, v in sorted(node.items()) if k != "resolved"}
    if isinstance(node, list):
        return [_canonical(item) for item in node]
    if isinstance(node, float):
        return round(node, 6)
    return node


# --------------------------------------------------------------------------- #
# Lecture de la réponse du modèle
# --------------------------------------------------------------------------- #

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Extrait l'objet JSON d'une réponse, fences et bavardage tolérés."""
    raw = (text or "").strip()
    if not raw:
        raise ProposalError(["Le modèle n'a renvoyé aucun texte."], kind="empty")
    candidates = [raw]
    candidates += [block.strip() for block in _FENCE.findall(raw) if block.strip()]
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
        raise ProposalError([f"La réponse JSON n'est pas un objet (type {type(data).__name__})."], kind="invalid_json")
    raise ProposalError(["Aucun objet JSON exploitable dans la réponse du modèle."], kind="invalid_json")


def _media_exists(ref: str) -> bool:
    if not isinstance(ref, str) or not ref.startswith("media://"):
        return False
    media_id = ref[len("media://"):].strip()
    if not media_id or any(ch in media_id for ch in "/\\.: "):
        return False
    return bool(list(MEDIA_DIR.glob(f"{media_id}.*")))


def _check_media_ref(label: str, value) -> list[str]:
    """Une référence média doit exister dans le stockage du studio."""
    if value in (None, ""):
        return []
    if not isinstance(value, str):
        return [f"{label} : une référence média doit être un texte."]
    if not value.startswith("media://"):
        return [
            f"{label} : {value!r} n'est pas une référence media://… . Les chemins disque "
            "ne sont jamais acceptés dans un projet ; utilisez une référence de la liste "
            "des médias disponibles, ou videz le champ."
        ]
    if not _media_exists(value):
        return [f"{label} : média inexistant {value!r}. Choisissez une référence qui existe."]
    return []


def _check_enum(path: str, value) -> str | None:
    allowed = ENUM_PATHS.get(path)
    if allowed is None or value in allowed:
        return None
    return f"valeur {value!r} inconnue pour {path} (autorisées : {', '.join(allowed)})."


def _set_dotted(node: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cursor = node
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def _get_dotted(node: dict, dotted: str):
    cursor = node
    for part in dotted.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def _find_scene(project: dict, scene_id: str) -> dict | None:
    for scene in project.get("content", {}).get("scenes", []):
        if str(scene.get("id")) == scene_id:
            return scene
    return None


def _find_layer(project: dict, scene_id: str, layer_id: str) -> dict | None:
    scene = _find_scene(project, scene_id)
    if not scene:
        return None
    for layer in scene.get("layers", []):
        if str(layer.get("id")) == layer_id:
            return layer
    return None


def _ids_hint(project: dict) -> str:
    parts = []
    for scene in project.get("content", {}).get("scenes", []):
        layers = ", ".join(str(l.get("id")) for l in scene.get("layers", []))
        parts.append(f"{scene.get('id')}[{layers}]")
    return " | ".join(parts)


def _audio_ready(project: dict) -> bool:
    """Une piste reelle est-elle mixee ? Les effets audio le disent vrai."""
    audio = project.get("audio") or {}
    return bool(audio.get("enabled")) and bool(audio.get("music") or audio.get("voice"))


def _compact_effects(normalized: list[dict]) -> list:
    """Forme stockee dans le projet : chaine courte si rien ne differe du catalogue.

    Le projet ne garde que les ecarts aux reglages par defaut, comme l'editeur :
    un projet rempli de valeurs par defaut reste lisible et le catalogue peut
    evoluer sans figer des nombres dans chaque fichier.
    """
    out: list = []
    for fx in normalized:
        spec = effects_mod.get(fx["id"])
        defaults = effects_mod.default_params(spec) if spec else {}
        tuned = {k: v for k, v in fx["params"].items() if defaults.get(k) != v}
        out.append(fx["id"] if not tuned else {"id": fx["id"], "params": tuned})
    return out


# --------------------------------------------------------------------------- #
# Application des opérations
# --------------------------------------------------------------------------- #

def apply_operations(base: dict, operations: list) -> tuple[dict, list[dict], list[str]]:
    """Applique les ops à une copie. Retourne (candidat, changements, erreurs)."""
    if not isinstance(operations, list) or not operations:
        raise ProposalError(["operations doit être une liste non vide d'opérations typées."])
    project = schema.clone(base)
    project.pop("resolved", None)
    changes: list[dict] = []
    errors: list[str] = []

    for index, op in enumerate(operations[:60]):
        tag = f"operations[{index}]"
        if not isinstance(op, dict):
            errors.append(f"{tag} : objet attendu.")
            continue
        name = str(op.get("op", "")).strip()

        if name in {"set_theme", "set_export", "set_variation", "set_signature", "set_audio"}:
            key = {"set_theme": "theme", "set_export": "export", "set_variation": "variation",
                   "set_signature": "content.signature", "set_audio": "audio"}[name]
            allowed = {"set_theme": THEME_KEYS, "set_export": EXPORT_KEYS,
                       "set_variation": VARIATION_KEYS, "set_signature": SIGNATURE_KEYS,
                       "set_audio": AUDIO_KEYS}[name]
            path = str(op.get("path", "")).strip()
            if path not in allowed:
                errors.append(
                    f"{tag} : propriété {path!r} non exposée pour {name} "
                    f"(autorisées : {', '.join(sorted(allowed))})."
                )
                continue
            value = op.get("value")
            if path in {"media", "music", "voice"}:
                bad = _check_media_ref(f"{name} {path}", value)
                if bad:
                    errors.extend(f"{tag}: {b}" for b in bad)
                    continue
            container = _get_dotted(project, key)
            if not isinstance(container, dict):
                errors.append(f"{tag} : section {key!r} absente du projet.")
                continue
            before = container.get(path)
            container[path] = value
            changes.append({"op": name, "target": f"{key}.{path}", "before": before, "after": value})
            continue

        if name == "set_scene":
            scene_id = str(op.get("scene_id", "")).strip()
            scene = _find_scene(project, scene_id)
            if scene is None:
                errors.append(f"{tag} : scène {scene_id!r} inconnue. {_ids_hint(base)}")
                continue
            path = str(op.get("path", "")).strip()
            if path not in SCENE_KEYS:
                errors.append(f"{tag} : chemin {path!r} non autorisé pour une scène "
                              f"(autorisés : {', '.join(sorted(SCENE_KEYS))}).")
                continue
            value = op.get("value")
            if path == "background.media":
                bad = _check_media_ref(f"scene {scene_id}.background.media", value)
                if bad:
                    errors.extend(f"{tag}: {b}" for b in bad)
                    continue
            enum_error = _check_enum(path, value)
            if enum_error:
                errors.append(f"{tag} : {enum_error}")
                continue
            before = _get_dotted(scene, path)
            _set_dotted(scene, path, value)
            changes.append({"op": name, "target": f"scene {scene_id}.{path}", "before": before, "after": value})
            continue

        if name == "set_layer":
            scene_id = str(op.get("scene_id", "")).strip()
            layer_id = str(op.get("layer_id", "")).strip()
            layer = _find_layer(project, scene_id, layer_id)
            if layer is None:
                errors.append(f"{tag} : calque {layer_id!r} introuvable dans la scène {scene_id!r}. {_ids_hint(base)}")
                continue
            path = str(op.get("path", "")).strip()
            if path not in LAYER_KEYS:
                errors.append(f"{tag} : chemin {path!r} non autorisé pour un calque "
                              f"(autorisés : {', '.join(sorted(LAYER_KEYS))}).")
                continue
            value = op.get("value")
            if path == "emphasis" and not isinstance(value, list):
                errors.append(f"{tag} : emphasis attend une liste de mots.")
                continue
            if path == "text" and not isinstance(value, str):
                errors.append(f"{tag} : text attend du texte.")
                continue
            if path == "media":
                if str(layer.get("type")) != "image":
                    errors.append(f"{tag} : seul un calque image porte un média "
                                  "(ajoutez un calque image avec add_image_layer).")
                    continue
                bad = _check_media_ref(f"{scene_id}/{layer_id}.media", value)
                if bad:
                    errors.extend(f"{tag}: {b}" for b in bad)
                    continue
            enum_error = _check_enum(path, value)
            if enum_error:
                errors.append(f"{tag} : {enum_error}")
                continue
            before = _get_dotted(layer, path)
            _set_dotted(layer, path, value)
            changes.append({"op": name, "target": f"{scene_id}/{layer_id}.{path}", "before": before, "after": value})
            continue

        if name == "add_text_layer":
            scene_id = str(op.get("scene_id", "")).strip()
            scene = _find_scene(project, scene_id)
            if scene is None:
                errors.append(f"{tag} : scène {scene_id!r} inconnue. {_ids_hint(base)}")
                continue
            layer_id = str(op.get("layer_id", "")).strip() or f"{scene_id}-calque-{len(scene.get('layers', [])) + 1}"
            if any(str(l.get("id")) == layer_id for l in scene.get("layers", [])):
                errors.append(f"{tag} : identifiant de calque déjà pris : {layer_id}")
                continue
            role = str(op.get("role", "body")).strip() or "body"
            if role not in ROLE_CHOICES:
                errors.append(f"{tag} : rôle {role!r} hors {', '.join(sorted(ROLE_CHOICES))}.")
                continue
            style = op.get("style") if isinstance(op.get("style"), dict) else {}
            unknown_style = [k for k in style if f"style.{k}" not in LAYER_KEYS]
            if unknown_style:
                errors.append(f"{tag} : style non autorisé : {', '.join(unknown_style)}.")
                continue
            position = op.get("position") if isinstance(op.get("position"), dict) else {}
            unknown_position = [k for k in position if f"position.{k}" not in LAYER_KEYS]
            if unknown_position:
                errors.append(f"{tag} : position non autorisée : {', '.join(unknown_position)}.")
                continue
            position_enums = [_check_enum(f"position.{k}", v) for k, v in position.items()]
            if any(position_enums):
                errors.append(f"{tag} : {next(e for e in position_enums if e)}")
                continue
            layer = schema.text_layer(
                layer_id,
                str(op.get("text", "") or ""),
                role=role,
                start_frames=int(op.get("start_frames", 0) or 0),
                in_frames=int(op.get("in_frames", 18) or 18),
                style=style,
                position=position,
            )
            scene.setdefault("layers", []).append(layer)
            changes.append({"op": name, "target": f"{scene_id}/{layer_id}", "before": None, "after": role})
            continue

        if name == "add_image_layer":
            scene_id = str(op.get("scene_id", "")).strip()
            scene = _find_scene(project, scene_id)
            if scene is None:
                errors.append(f"{tag} : scène {scene_id!r} inconnue. {_ids_hint(base)}")
                continue
            ref = op.get("media", "")
            layer_id = str(op.get("layer_id", "")).strip() or f"{scene_id}-image-{len(scene.get('layers', [])) + 1}"
            bad = _check_media_ref(f"{scene_id}/{layer_id}.media", ref)
            if bad:
                errors.extend(f"{tag}: {b}" for b in bad)
                continue
            if any(str(l.get("id")) == layer_id for l in scene.get("layers", [])):
                errors.append(f"{tag} : identifiant de calque déjà pris : {layer_id}")
                continue
            layer = schema.image_layer(layer_id, str(ref), start_frames=int(op.get("start_frames", 0) or 0))
            scene.setdefault("layers", []).append(layer)
            changes.append({"op": name, "target": f"{scene_id}/{layer_id}", "before": None, "after": ref})
            continue

        if name == "add_scene":
            scene_id = str(op.get("scene_id", "")).strip()
            if not scene_id:
                errors.append(f"{tag} : add_scene exige un scene_id nouveau.")
                continue
            if _find_scene(project, scene_id) is not None:
                errors.append(f"{tag} : scène {scene_id!r} déjà présente.")
                continue
            try:
                duration = float(op.get("duration", 3.0))
            except (TypeError, ValueError):
                errors.append(f"{tag} : duration attend un nombre de secondes.")
                continue
            layer = schema.text_layer(f"{scene_id}-texte", str(op.get("text", "") or "—"))
            project["content"].setdefault("scenes", []).append(
                schema.scene(scene_id, str(op.get("label", "") or scene_id), duration, [layer])
            )
            changes.append({"op": name, "target": f"scene {scene_id}", "before": None, "after": duration})
            continue

        if name == "duplicate_scene":
            scene_id = str(op.get("scene_id", "")).strip()
            new_id = str(op.get("new_scene_id", "")).strip()
            source = _find_scene(project, scene_id)
            if source is None:
                errors.append(f"{tag} : scène {scene_id!r} inconnue. {_ids_hint(base)}")
                continue
            if not new_id or _find_scene(project, new_id) is not None:
                errors.append(f"{tag} : new_scene_id requis et inédit ({new_id!r}).")
                continue
            clone = schema.clone(source)
            clone["id"] = new_id
            clone["label"] = str(clone.get("label", "")) or new_id
            for layer in clone.get("layers", []):
                layer["id"] = f"{new_id}-{str(layer.get('id'))}"
            project["content"].setdefault("scenes", []).append(clone)
            changes.append({"op": name, "target": f"scene {new_id}", "before": None, "after": f"copie de {scene_id}"})
            continue

        if name == "remove_scene":
            scene_id = str(op.get("scene_id", "")).strip()
            scenes = project.get("content", {}).get("scenes", [])
            if len(scenes) <= 1:
                errors.append(f"{tag} : impossible de retirer la dernière scène.")
                continue
            remaining = [s for s in scenes if str(s.get("id")) != scene_id]
            if len(remaining) == len(scenes):
                errors.append(f"{tag} : scène {scene_id!r} inconnue. {_ids_hint(base)}")
                continue
            project["content"]["scenes"] = remaining
            changes.append({"op": name, "target": f"scene {scene_id}", "before": scene_id, "after": None})
            continue

        if name == "remove_layer":
            scene_id = str(op.get("scene_id", "")).strip()
            layer_id = str(op.get("layer_id", "")).strip()
            scene = _find_scene(project, scene_id)
            if scene is None:
                errors.append(f"{tag} : scène {scene_id!r} inconnue. {_ids_hint(base)}")
                continue
            layers = scene.get("layers", [])
            kept = [l for l in layers if str(l.get("id")) != layer_id]
            if len(kept) == len(layers):
                errors.append(f"{tag} : calque {layer_id!r} introuvable dans {scene_id!r}. {_ids_hint(base)}")
                continue
            scene["layers"] = kept
            changes.append({"op": name, "target": f"{scene_id}/{layer_id}", "before": layer_id, "after": None})
            continue

        if name == "set_effects":
            scene_id = str(op.get("scene_id", "")).strip()
            scene = _find_scene(project, scene_id)
            if scene is None:
                errors.append(f"{tag} : scène {scene_id!r} inconnue. {_ids_hint(base)}")
                continue
            layer_id = str(op.get("layer_id", "")).strip()
            if layer_id:
                layer = _find_layer(project, scene_id, layer_id)
                if layer is None:
                    errors.append(f"{tag} : calque {layer_id!r} introuvable dans la scène {scene_id!r}. {_ids_hint(base)}")
                    continue
                host = "layer"
                target = str(layer.get("type") or "text")
                container = layer
                where = f"{scene_id}/{layer_id}"
            else:
                host = "scene"
                target = "scene"
                container = scene
                where = f"scene {scene_id}"
            raw = op.get("effects")
            if raw is None:
                raw = op.get("value")
            # Une liste vide retire tous les effets : c'est le seul moyen propre
            # de les enlever par proposition, sans operations de suppression libre.
            if raw is None:
                errors.append(f"{tag} : set_effects exige « effects » (liste, [] pour tout retirer).")
                continue
            normalized, fx_errors, _fx_warnings = effects_mod.normalize(
                raw, host, target, path=f"{where}.effects", audio_ready=_audio_ready(project)
            )
            if fx_errors:
                errors.extend(f"{tag}: {e}" for e in fx_errors[:6])
                continue
            before = container.get("effects")
            container["effects"] = _compact_effects(normalized)
            changes.append({
                "op": name, "target": f"{where}.effects",
                "before": before, "after": [fx["id"] for fx in normalized],
            })
            continue

        errors.append(
            f"{tag} : opération {name!r} inconnue. Ops valides : set_theme, set_export, "
            "set_variation, set_signature, set_audio, set_scene, set_layer, set_effects, "
            "add_scene, add_text_layer, add_image_layer, duplicate_scene, remove_scene, "
            "remove_layer."
        )

    if errors:
        raise ProposalError(errors, kind="invalid_operations")
    return project, changes, errors


# --------------------------------------------------------------------------- #
# Propositions
# --------------------------------------------------------------------------- #

def validate_candidate(project: dict) -> tuple[list[str], list[str]]:
    """Validation métier existante, après retrait de tout bloc résiduel."""
    candidate = schema.clone(project)
    candidate.pop("resolved", None)
    if candidate.get("version") != schema.SCHEMA_VERSION_V2:
        return ([f"Version de projet non prise en charge : {candidate.get('version')!r}."], [])
    model = candidate.get("model")
    model_id = model.get("id") if isinstance(model, dict) else model
    if model_id not in schema.MODELS:
        return ([f"model.id inconnu : {model_id!r} (connus : {', '.join(schema.MODELS)})."], [])
    return validate_project(candidate)


def new_proposal(proposal_type: str, summary: str) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "type": proposal_type,
        "summary": (summary or "").strip()[:600],
        "project_name": "",
        "base_revision": "",
        "candidate": None,
        "changes": [],
        "questions": [],
        "warnings": [],
        "sources": [],
        "validation": {"state": "not_started", "errors": [], "warnings": []},
        "status": "proposed",
        "created_at": time.time(),
        "batch": None,
        "library": None,
        "capability": "",
        "alternative": "",
    }


def from_reply(
    reply: dict,
    base_project: dict | None,
    project_name: str,
    csv_columns: list[str] | None = None,
) -> dict:
    """Contrôle complet d'une réponse du modèle → proposition exploitable."""
    if not isinstance(reply, dict):
        raise ProposalError(["La réponse n'est pas un objet JSON."], kind="invalid_json")
    ptype = str(reply.get("type", "")).strip()
    if ptype not in PROPOSAL_TYPES:
        raise ProposalError(
            [f"type {ptype!r} inconnu. Choix : {', '.join(PROPOSAL_TYPES)}."], kind="unknown_type"
        )
    proposal = new_proposal(ptype, str(reply.get("summary", "")))
    raw_warnings = reply.get("warnings")
    proposal["warnings"] = [str(w) for w in raw_warnings][:8] if isinstance(raw_warnings, list) else []
    if not isinstance(reply.get("warnings"), list) and raw_warnings:
        proposal["warnings"].append("Le modèle a fourni « warnings » dans un format inattendu.")

    if ptype == "question":
        questions = reply.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ProposalError(["type=question exige « questions » : une liste de demandes de précision."])
        proposal["questions"] = [str(q) for q in questions][:6]
        proposal["validation"] = {"state": "not_needed", "errors": [], "warnings": []}
        return proposal

    if ptype == "unavailable":
        capability = str(reply.get("capability", "")).strip()
        if not capability:
            raise ProposalError(["type=unavailable exige « capability » : la capacité demandée qui manque."])
        proposal["capability"] = capability[:200]
        proposal["alternative"] = str(reply.get("alternative", ""))[:600]
        proposal["validation"] = {"state": "not_needed", "errors": [], "warnings": []}
        return proposal

    if ptype == "library_save":
        label = str(reply.get("label", "")).strip()
        if not label:
            raise ProposalError(["type=library_save exige « label » : le nom du modèle à enregistrer."])
        if base_project is None:
            raise ProposalError(["Aucun projet actif à enregistrer : ouvrez ou créez d'abord un projet."])
        errors, warnings = validate_candidate(base_project)
        if errors:
            raise ProposalError(
                ["Le projet actif n'est pas enregistrable en l'état : " + "; ".join(errors[:4])],
                kind="invalid_project",
            )
        proposal["library"] = {
            "label": label[:80],
            "description": str(reply.get("description", ""))[:400],
            "model_id": str(reply.get("model_id", "") or "")[:60],
        }
        proposal["base_revision"] = revision_of(base_project)
        proposal["project_name"] = project_name
        proposal["validation"] = {"state": "valid", "errors": [], "warnings": warnings}
        return proposal

    if ptype == "batch_plan":
        return _batch_proposal(reply, proposal, known_columns=csv_columns)

    # --- types portant un projet candidat ----------------------------------
    if ptype == "project_patch":
        if base_project is None:
            raise ProposalError(["Aucun projet actif à modifier : le studio n'a pas de projet chargé."])
        if _forced_resolved(reply):
            proposal["warnings"].append("Un bloc « resolved » a été retiré de la réponse du modèle.")
        candidate, changes, _ = apply_operations(base_project, reply.get("operations"))
        proposal["base_revision"] = revision_of(base_project)
        proposal["project_name"] = project_name
    else:  # project_new
        if _forced_resolved(reply):
            proposal["warnings"].append("Un bloc « resolved » a été retiré du projet proposé.")
        template_id = str(reply.get("template_id", "") or "").strip()
        operations = reply.get("operations")
        if template_id:
            from .. import library as library_mod

            try:
                candidate = library_mod.get_project(template_id)
            except Exception as e:  # noqa: BLE001 - identifiant inconnu : message réparable
                raise ProposalError(
                    [f"Modèle de bibliothèque inconnu : {template_id!r}. "
                     f"Modèles disponibles : {', '.join(_template_ids())}."]
                ) from e
            proposal["warnings"].append(f"Base : modèle « {template_id} » de la bibliothèque.")
            if operations:
                candidate, changes, _ = apply_operations(candidate, operations)
            else:
                changes = [{"op": "use_template", "target": "projet complet", "before": None, "after": template_id}]
        elif isinstance(reply.get("project"), dict):
            candidate = schema.clone(reply["project"])
            candidate.pop("resolved", None)
            if candidate.get("version") != schema.SCHEMA_VERSION_V2:
                candidate["version"] = schema.SCHEMA_VERSION_V2
            if operations:
                candidate, changes, _ = apply_operations(candidate, operations)
            else:
                changes = [{"op": "project_provided", "target": "projet complet", "before": None, "after": "v2"}]
        else:
            raise ProposalError(
                ["type=project_new exige « template_id » (modèle connu de la bibliothèque) "
                 "et/ou « project » complet, avec des « operations » typées."],
                kind="invalid_project",
            )
        proposal["project_name"] = str(candidate.get("name") or project_name or "")[:80]
        proposal["base_revision"] = revision_of(base_project) if base_project is not None else ""

    candidate.pop("resolved", None)
    errors, warnings = validate_candidate(candidate)
    proposal["candidate"] = candidate
    proposal["changes"] = changes
    proposal["warnings"].extend(warnings)
    if errors:
        proposal["validation"] = {"state": "invalid", "errors": errors, "warnings": warnings}
        raise ProposalError(errors, kind="invalid_project") from None
    proposal["validation"] = {"state": "valid", "errors": [], "warnings": warnings}
    return proposal


def _template_ids() -> list[str]:
    from .. import library as library_mod

    try:
        return [item["id"] for item in library_mod.list_library()]
    except Exception:  # noqa: BLE001 - le message d'erreur reste utile sans la liste
        return list(schema.MODELS)


def _forced_resolved(reply: dict) -> bool:
    project = reply.get("project")
    return isinstance(project, dict) and "resolved" in project


def _batch_proposal(reply: dict, proposal: dict, known_columns: list[str] | None = None) -> dict:
    """Mapping et options proposés ; le plan réel reste calculé par build_plan()."""
    model = str(reply.get("model", "") or "").strip()
    mapping = reply.get("mapping")
    options = reply.get("options")
    if not model:
        raise ProposalError(["type=batch_plan exige « model » : un identifiant de la bibliothèque."])
    if not isinstance(mapping, dict):
        raise ProposalError(["type=batch_plan exige « mapping » : objet champ → colonne CSV."])
    from .. import library as library_mod

    try:
        template = library_mod.get_project(model)
    except Exception as e:  # noqa: BLE001 - identifiant inconnu : erreur claire
        raise ProposalError(
            [f"Modèle de bibliothèque inconnu : {model!r}. "
             f"Modèles disponibles : {', '.join(_template_ids())}."]
        ) from e

    from shortvideos import batch as batch_mod

    fields = {f["key"] for f in batch_mod.fillable_fields(template)}
    columns = {str(c) for c in (known_columns or reply.get("csv_columns") or [])}
    unknown_fields = [k for k in mapping if k not in fields]
    if unknown_fields:
        raise ProposalError(
            [f"Champs inconnus pour ce modèle : {', '.join(unknown_fields)}. "
             f"Champs remplissables : {', '.join(sorted(fields))}."]
        )
    unknown_columns = [v for v in mapping.values() if columns and str(v) not in columns]
    if unknown_columns:
        raise ProposalError([f"Colonnes absentes du CSV : {', '.join(sorted(set(map(str, unknown_columns))))}."])
    opts = options if isinstance(options, dict) else {}
    allowed_opts = {"auto", "column", "none"}
    bad_opts = [f"{k}={v}" for k, v in opts.items() if k in {"background", "music"} and str(v) not in allowed_opts]
    if bad_opts:
        raise ProposalError([f"Option invalide : {', '.join(bad_opts)} (choix : auto, column, none)."])
    proposal["batch"] = {
        "model": model,
        "mapping": {str(k): str(v) for k, v in mapping.items()},
        "options": {k: str(v) for k, v in opts.items() if k in {"background", "music"}},
        "notes": str(reply.get("notes", ""))[:800],
        "fields": sorted(fields),
    }
    proposal["validation"] = {"state": "valid", "errors": [], "warnings": []}
    return proposal


def public_view(proposal: dict) -> dict:
    """Ce que le navigateur voit : jamais le candidat complet avant acceptation."""
    view = {
        "id": proposal["id"],
        "type": proposal["type"],
        "summary": proposal["summary"],
        "project_name": proposal["project_name"],
        "base_revision": proposal["base_revision"],
        "changes": [
            {
                "op": c.get("op", ""),
                "target": c.get("target", ""),
                "before": _brief(c.get("before")),
                "after": _brief(c.get("after")),
            }
            for c in proposal.get("changes", [])
        ],
        "questions": proposal.get("questions", []),
        "warnings": proposal.get("warnings", []),
        "sources": proposal.get("sources", []),
        "validation": proposal.get("validation", {"state": "not_started", "errors": [], "warnings": []}),
        "status": proposal.get("status", "proposed"),
        "batch": proposal.get("batch"),
        "library": proposal.get("library"),
        "capability": proposal.get("capability", ""),
        "alternative": proposal.get("alternative", ""),
        "has_candidate": proposal.get("candidate") is not None,
    }
    return view


def _brief(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)[:120]
    text = json.dumps(value, ensure_ascii=False)
    return text[:120] + ("…" if len(text) > 120 else "")


def diff_changes(base: dict, candidate: dict) -> list[dict]:
    """Résumé lisible des écarts, pour la carte de proposition."""
    changes: list[dict] = []
    for section, keys in (("theme", THEME_KEYS), ("export", EXPORT_KEYS), ("audio", AUDIO_KEYS)):
        for key in sorted(keys):
            before = (base.get(section) or {}).get(key)
            after = (candidate.get(section) or {}).get(key)
            if before != after:
                changes.append({"op": f"{section}.{key}", "before": _brief(before), "after": _brief(after)})
    base_scenes = {str(s.get("id")): s for s in base.get("content", {}).get("scenes", [])}
    cand_scenes = {str(s.get("id")): s for s in candidate.get("content", {}).get("scenes", [])}
    for scene_id, scene in cand_scenes.items():
        origin = base_scenes.get(scene_id)
        if origin is None:
            changes.append({"op": f"scène {scene_id} ajoutée", "before": "", "after": f"{scene.get('duration')} s"})
            continue
        for key in ("duration", "label"):
            if origin.get(key) != scene.get(key):
                changes.append({"op": f"scène {scene_id}.{key}", "before": _brief(origin.get(key)),
                                "after": _brief(scene.get(key))})
        base_layers = {str(l.get("id")): l for l in origin.get("layers", [])}
        for layer in scene.get("layers", []):
            layer_id = str(layer.get("id"))
            origin_layer = base_layers.get(layer_id)
            if origin_layer is None:
                changes.append({"op": f"calque {scene_id}/{layer_id} ajouté", "before": "",
                                "after": _brief(layer.get("text") or layer.get("media"))})
                continue
            for path in sorted(LAYER_KEYS):
                before = _get_dotted(origin_layer, path)
                after = _get_dotted(layer, path)
                if before != after:
                    changes.append({"op": f"{scene_id}/{layer_id}.{path}", "before": _brief(before),
                                    "after": _brief(after)})
        for layer_id in base_layers:
            if layer_id not in {str(l.get("id")) for l in scene.get("layers", [])}:
                changes.append({"op": f"calque {scene_id}/{layer_id} retiré", "before": layer_id, "after": ""})
    for scene_id in base_scenes:
        if scene_id not in cand_scenes:
            changes.append({"op": f"scène {scene_id} retirée", "before": scene_id, "after": ""})
    return changes[:40]


def expired(proposal: dict) -> bool:
    return time.time() - float(proposal.get("created_at", 0)) > PROPOSAL_TTL
