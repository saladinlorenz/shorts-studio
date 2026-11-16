"""Incrément 3 — réordonner (move_scene/move_layer) et dupliquer un calque.

Réordonnancement par identifiant de référence (before/after), jamais par index
(règle 5 du protocole). duplicate_layer copie un calque juste après l'original.
Tests mock : aucune écriture disque, aucun rendu.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.agent import context, proposals  # noqa: E402
from shortvideos import schema  # noqa: E402


def _project() -> dict:
    base = schema.new_project("quote_cinematic")
    base["content"]["scenes"] = [
        schema.scene("s1", "Accroche", 3.0, [
            schema.text_layer("hook", "Accroche", role="hook"),
            schema.text_layer("title", "Titre", role="caption"),
        ]),
        schema.scene("s2", "Citation", 4.0, [
            schema.text_layer("quote", "Citation", role="quote"),
        ]),
        schema.scene("s3", "Fin", 2.0, [
            schema.text_layer("end", "Fin", role="body"),
        ]),
    ]
    return base


def _scene_ids(project: dict) -> list[str]:
    return [s["id"] for s in project["content"]["scenes"]]


def _layer_ids(project: dict, scene_id: str) -> list[str]:
    scene = next(s for s in project["content"]["scenes"] if s["id"] == scene_id)
    return [l["id"] for l in scene["layers"]]


# --------------------------------------------------------------------------- #
# move_scene
# --------------------------------------------------------------------------- #
def test_move_scene_after_reorders():
    candidate, changes, _ = proposals.apply_operations(_project(), [
        {"op": "move_scene", "scene_id": "s3", "after": "s1"},
    ])
    assert _scene_ids(candidate) == ["s1", "s3", "s2"]
    assert changes[0]["target"] == "scene s3"


def test_move_scene_before_reorders():
    candidate, _, _ = proposals.apply_operations(_project(), [
        {"op": "move_scene", "scene_id": "s3", "before": "s1"},
    ])
    assert _scene_ids(candidate) == ["s3", "s1", "s2"]


@pytest.mark.parametrize("op", [
    {"op": "move_scene", "scene_id": "s3"},
    {"op": "move_scene", "scene_id": "s3", "before": "s1", "after": "s2"},
    {"op": "move_scene", "scene_id": "s3", "after": "s3"},
    {"op": "move_scene", "scene_id": "s3", "after": "inconnu"},
    {"op": "move_scene", "scene_id": "inconnu", "after": "s1"},
])
def test_move_scene_invalid_is_refused(op):
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.apply_operations(_project(), [op])
    assert exc.value.kind == "invalid_operations"


# --------------------------------------------------------------------------- #
# move_layer
# --------------------------------------------------------------------------- #
def test_move_layer_before_reorders_within_scene():
    candidate, changes, _ = proposals.apply_operations(_project(), [
        {"op": "move_layer", "scene_id": "s1", "layer_id": "title", "before": "hook"},
    ])
    assert _layer_ids(candidate, "s1") == ["title", "hook"]
    assert changes[0]["target"] == "s1/title"


def test_move_layer_after_reorders():
    base = _project()
    base["content"]["scenes"][0]["layers"].append(schema.text_layer("note", "Note", role="body"))
    candidate, _, _ = proposals.apply_operations(base, [
        {"op": "move_layer", "scene_id": "s1", "layer_id": "hook", "after": "note"},
    ])
    assert _layer_ids(candidate, "s1") == ["title", "note", "hook"]


def test_move_layer_unknown_is_refused():
    with pytest.raises(proposals.ProposalError):
        proposals.apply_operations(_project(), [
            {"op": "move_layer", "scene_id": "s1", "layer_id": "absent", "before": "hook"},
        ])


# --------------------------------------------------------------------------- #
# duplicate_layer
# --------------------------------------------------------------------------- #
def test_duplicate_layer_copies_after_source():
    base = _project()
    base["content"]["scenes"][0]["layers"][0]["effects"] = ["shine"]
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "duplicate_layer", "scene_id": "s1", "layer_id": "hook", "new_layer_id": "hook-bis"},
    ])
    assert _layer_ids(candidate, "s1") == ["hook", "hook-bis", "title"]
    clone = candidate["content"]["scenes"][0]["layers"][1]
    assert clone["text"] == "Accroche"
    assert clone["effects"] == ["shine"]
    assert changes[0]["after"] == "copie de hook"
    # l'original est intact
    assert candidate["content"]["scenes"][0]["layers"][0]["id"] == "hook"


@pytest.mark.parametrize("op", [
    {"op": "duplicate_layer", "scene_id": "s1", "layer_id": "hook"},
    {"op": "duplicate_layer", "scene_id": "s1", "layer_id": "hook", "new_layer_id": "title"},
    {"op": "duplicate_layer", "scene_id": "s1", "layer_id": "absent", "new_layer_id": "x"},
    {"op": "duplicate_layer", "scene_id": "inconnu", "layer_id": "hook", "new_layer_id": "x"},
])
def test_duplicate_layer_invalid_is_refused(op):
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.apply_operations(_project(), [op])
    assert exc.value.kind == "invalid_operations"


def test_duplicate_layer_independent_copy():
    base = _project()
    candidate, _, _ = proposals.apply_operations(base, [
        {"op": "duplicate_layer", "scene_id": "s1", "layer_id": "hook", "new_layer_id": "hook-bis"},
        {"op": "set_layer", "scene_id": "s1", "layer_id": "hook-bis", "path": "text", "value": "Autre"},
    ])
    layers = candidate["content"]["scenes"][0]["layers"]
    assert layers[0]["text"] == "Accroche"
    assert layers[1]["text"] == "Autre"


# --------------------------------------------------------------------------- #
# Guidance du protocole
# --------------------------------------------------------------------------- #
def test_protocol_documents_reorder_and_duplicate():
    for text in (context.PROTOCOL, context.PROTOCOL_CORE):
        assert "move_scene" in text
        assert "move_layer" in text
        assert "duplicate_layer" in text