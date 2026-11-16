"""Incrément 1 — édition globale (ciblage « * » / rôle / type) + visibilité des effets.

Couvre le bug « appliquer un effet à toute la vidéo » : le moteur expands un
ciblage global en opérations concrètes (validation par cible inchangée), et
l'outline montre désormais les effets déjà posés pour que le modèle ne les
oublie plus en mode compact. Tests mock : aucun rendu, aucun réseau.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.agent import context, proposals  # noqa: E402
from shortvideos import effects as fx  # noqa: E402
from shortvideos import schema  # noqa: E402


def _multi_scene_project() -> dict:
    base = schema.new_project("quote_cinematic")
    base["content"]["scenes"] = [
        schema.scene("s1", "Accroche", 3.0, [
            schema.text_layer("hook", "Accroche", role="hook"),
            schema.text_layer("title", "Titre", role="caption"),
        ]),
        schema.scene("s2", "Citation", 4.0, [
            schema.text_layer("quote", "Citation", role="quote"),
            schema.text_layer("author", "Auteur", role="author"),
        ]),
        schema.scene("s3", "Fin", 2.0, [
            schema.text_layer("hook", "Rappel", role="hook"),
            schema.image_layer("logo", "media://x"),
        ]),
    ]
    return base


def _layer(project: dict, scene_id: str, layer_id: str) -> dict:
    return next(l for s in project["content"]["scenes"] if s["id"] == scene_id
                for l in s["layers"] if l["id"] == layer_id)


# --------------------------------------------------------------------------- #
# Ciblage global : scène entière
# --------------------------------------------------------------------------- #
def test_wildcard_scene_effects_apply_to_every_scene():
    base = _multi_scene_project()
    candidate, changes, errors = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "*", "effects": ["plasma_field"]},
    ])
    assert errors == []
    assert len(changes) == 3
    for scene in candidate["content"]["scenes"]:
        assert scene["effects"] == ["plasma_field"]
        for layer in scene["layers"]:
            assert layer["effects"] == []


def test_wildcard_scene_duration_applies_everywhere():
    base = _multi_scene_project()
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "set_scene", "scene_id": "*", "path": "duration", "value": 5.0},
    ])
    assert len(changes) == 3
    assert all(s["duration"] == 5.0 for s in candidate["content"]["scenes"])


def test_wildcard_layer_type_recolors_all_text_layers():
    base = _multi_scene_project()
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "set_layer", "scene_id": "*", "layer_type": "text",
         "path": "style.color", "value": "#FFFFFF"},
    ])
    text_layers = [l for s in candidate["content"]["scenes"] for l in s["layers"]
                   if l["type"] == "text"]
    assert len(changes) == len(text_layers) == 5
    assert all(l["style"]["color"] == "#FFFFFF" for l in text_layers)
    assert _layer(candidate, "s3", "logo").get("style", {}).get("color") is None


# --------------------------------------------------------------------------- #
# Ciblage global : calques par rôle / type / joker
# --------------------------------------------------------------------------- #
def test_wildcard_layer_role_targets_only_matching_layers():
    base = _multi_scene_project()
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "*", "layer_role": "hook", "effects": ["shine"]},
    ])
    assert len(changes) == 2
    assert _layer(candidate, "s1", "hook")["effects"] == ["shine"]
    assert _layer(candidate, "s3", "hook")["effects"] == ["shine"]
    assert _layer(candidate, "s1", "title")["effects"] == []
    assert _layer(candidate, "s2", "quote")["effects"] == []
    assert _layer(candidate, "s3", "logo")["effects"] == []


def test_wildcard_layer_id_star_targets_all_layers_of_scene():
    base = _multi_scene_project()
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "s1", "layer_id": "*", "effects": ["shine"]},
    ])
    assert len(changes) == 2
    assert _layer(candidate, "s1", "hook")["effects"] == ["shine"]
    assert _layer(candidate, "s1", "title")["effects"] == ["shine"]
    assert _layer(candidate, "s2", "quote")["effects"] == []


def test_wildcard_concrete_layer_id_skips_scenes_without_it():
    base = _multi_scene_project()
    candidate, changes, errors = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "*", "layer_id": "hook", "effects": ["shine"]},
    ])
    assert errors == []
    assert len(changes) == 2  # s2 n'a pas de calque « hook » : ignoré, pas une erreur
    assert _layer(candidate, "s2", "quote")["effects"] == []


def test_wildcard_role_without_match_is_ignored():
    base = _multi_scene_project()
    candidate, changes, errors = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "*", "layer_role": "reveal", "effects": ["shine"]},
    ])
    assert errors == []
    assert changes == []
    assert all(l["effects"] == [] for s in candidate["content"]["scenes"] for l in s["layers"])


# --------------------------------------------------------------------------- #
# Le ciblage global ne contourne aucune règle de portée / borne
# --------------------------------------------------------------------------- #
def test_wildcard_scene_effect_respects_scope():
    base = _multi_scene_project()
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.apply_operations(base, [
            {"op": "set_effects", "scene_id": "*", "effects": ["shine"]},  # shine = calque seul
        ])
    assert exc.value.kind == "invalid_operations"


def test_wildcard_layer_effect_respects_scope():
    base = _multi_scene_project()
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.apply_operations(base, [
            {"op": "set_effects", "scene_id": "*", "layer_role": "hook",
             "effects": ["plasma_field"]},  # plasma_field = overlay, pas calque
        ])
    assert exc.value.kind == "invalid_operations"


def test_wildcard_max_effects_per_target_still_enforced():
    layer_fx = [e["id"] for e in fx.all_effects()
                if "layer" in e["scopes"] and "text" in e["targets"]][:5]
    assert len(layer_fx) >= 5
    base = _multi_scene_project()
    with pytest.raises(proposals.ProposalError):
        proposals.apply_operations(base, [
            {"op": "set_effects", "scene_id": "s1", "layer_id": "*", "effects": layer_fx},
        ])


def test_wildcard_overflow_is_refused():
    base = _multi_scene_project()
    template = base["content"]["scenes"][0]
    for index in range(61):
        scene = copy.deepcopy(template)
        scene["id"] = f"x{index}"
        base["content"]["scenes"].append(scene)
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.apply_operations(base, [
            {"op": "set_scene", "scene_id": "*", "path": "duration", "value": 4.0},
        ])
    assert "trop large" in str(exc.value)


def test_set_layer_wildcard_requires_layer_selector():
    base = _multi_scene_project()
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.apply_operations(base, [
            {"op": "set_layer", "scene_id": "*", "path": "style.color", "value": "#FFFFFF"},
        ])
    assert "cible calque" in str(exc.value)


def test_non_wildcard_set_effects_unchanged():
    base = _multi_scene_project()
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "s2", "layer_id": "quote",
         "effects": [{"id": "shine", "params": {"width": 0.4}}]},
    ])
    assert len(changes) == 1
    assert _layer(candidate, "s2", "quote")["effects"] == [{"id": "shine", "params": {"width": 0.4}}]


# --------------------------------------------------------------------------- #
# Visibilité des effets dans l'outline (cause du bug « quel effet ? »)
# --------------------------------------------------------------------------- #
def test_outline_shows_scene_and_layer_effects():
    base = _multi_scene_project()
    candidate, _, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "s1", "effects": ["plasma_field"]},
        {"op": "set_effects", "scene_id": "s1", "layer_id": "hook", "effects": ["shine"]},
    ])
    outline = context.outline_project(candidate)
    assert "effets=[plasma_field]" in outline
    assert "effets=[shine]" in outline


def test_outline_without_effects_omits_marker():
    assert "effets=" not in context.outline_project(_multi_scene_project())


def test_outline_handles_tuned_effect_forms():
    base = _multi_scene_project()
    candidate, _, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": "s1", "layer_id": "hook",
         "effects": [{"id": "shine", "params": {"width": 0.4}}]},
    ])
    assert "effets=[shine]" in context.outline_project(candidate)


# --------------------------------------------------------------------------- #
# Guidance du protocole
# --------------------------------------------------------------------------- #
def test_protocol_documents_global_targeting():
    assert 'scene_id:"*"' in context.PROTOCOL
    assert 'scene_id:"*"' in context.PROTOCOL_CORE
    assert "layer_role" in context.PROTOCOL
    assert "TOUTE LA VIDÉO" in context.SYSTEM_RULES
    assert "ne redemande pas" in context.SYSTEM_RULES