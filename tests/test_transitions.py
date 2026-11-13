"""Transitions entre scenes : chevauchement rendu, chronologie resolue intacte.

Une transition ne deplace ni le curseur, ni la duree totale, ni les fenetres de
calques : elle est lue par le rendu a la frontiere entre deux scenes. Ces tests
verrouillent la normalisation (schema/validation/resolve) et la retrocompatibilite.
"""
import pytest

from server.agent import capabilities, proposals
from shortvideos import resolve, schema, validation


def _project() -> dict:
    return schema.new_project("quote_cinematic")


def test_scene_helper_defaults_to_no_transition():
    sc = schema.scene("s1", "Test", 3.0, [])
    assert sc["transition"] == {"type": "none", "frames": 0}


def test_default_project_resolves_without_transitions():
    resolved = resolve.resolve(_project())["resolved"]
    assert all(s["transition"] == {"type": "none", "frames": 0} for s in resolved["scenes"])


def test_transitions_leave_the_timeline_unchanged():
    project = _project()
    baseline = resolve.resolve(project)["resolved"]
    project["content"]["scenes"][1]["transition"] = {"type": "fade", "frames": 12}
    project["content"]["scenes"][2]["transition"] = {"type": "push", "frames": 20}
    resolved = resolve.resolve(project)["resolved"]
    assert resolved["total_frames"] == baseline["total_frames"]
    assert [s["start_frame"] for s in resolved["scenes"]] == [s["start_frame"] for s in baseline["scenes"]]
    assert [s["end_frame"] for s in resolved["scenes"]] == [s["end_frame"] for s in baseline["scenes"]]
    for after, before in zip(resolved["scenes"], baseline["scenes"]):
        assert [l["start_frame"] for l in after["layers"]] == [l["start_frame"] for l in before["layers"]]
    assert resolved["scenes"][1]["transition"] == {"type": "fade", "frames": 12}
    assert resolved["scenes"][2]["transition"] == {"type": "push", "frames": 20}


def test_first_scene_transition_is_ignored():
    project = _project()
    project["content"]["scenes"][0]["transition"] = {"type": "wipe", "frames": 10}
    resolved = resolve.resolve(project)["resolved"]
    assert resolved["scenes"][0]["transition"] == {"type": "none", "frames": 0}


def test_transition_frames_clamped_to_cap_and_both_scenes():
    project = _project()
    # scene 3 ne dure que 105 frames ; une transition de 200 est bornee par le plafond (60)
    project["content"]["scenes"][2]["transition"] = {"type": "zoom", "frames": 200}
    resolved = resolve.resolve(project)["resolved"]
    assert resolved["scenes"][2]["transition"] == {"type": "zoom", "frames": schema.TRANSITION_FRAMES_MAX}
    # une scene tres courte borne le chevauchement par sa propre duree
    project["content"]["scenes"][1]["duration"] = schema.SCENE_DURATION_MIN  # 0.5 s -> 15 frames
    project["content"]["scenes"][1]["transition"] = {"type": "fade", "frames": 40}
    resolved = resolve.resolve(project)["resolved"]
    assert resolved["scenes"][1]["transition"]["frames"] <= 15


def test_unknown_transition_type_is_normalized_to_none():
    project = _project()
    project["content"]["scenes"][1]["transition"] = {"type": "inexistant", "frames": 10}
    resolved = resolve.resolve(project)["resolved"]
    assert resolved["scenes"][1]["transition"] == {"type": "none", "frames": 0}


def test_validation_rejects_unknown_type_and_out_of_bounds_frames():
    project = _project()
    project["content"]["scenes"][1]["transition"] = {"type": "bogus", "frames": 5}
    errors, _ = validation.validate_project_v2(project)
    assert any("transition.type inconnu" in e for e in errors)
    project["content"]["scenes"][1]["transition"] = {"type": "fade", "frames": 999}
    errors, _ = validation.validate_project_v2(project)
    assert any("transition.frames" in e for e in errors)


def test_validation_warns_on_first_scene_transition():
    project = _project()
    project["content"]["scenes"][0]["transition"] = {"type": "fade", "frames": 8}
    errors, warnings = validation.validate_project_v2(project)
    assert errors == []
    assert any("premiere scene" in w for w in warnings)


def test_valid_transition_passes_validation():
    project = _project()
    project["content"]["scenes"][1]["transition"] = {"type": "dip_black", "frames": 15}
    project["content"]["scenes"][2]["transition"] = {"type": "slide_left", "frames": 12}
    errors, _ = validation.validate_project_v2(project)
    assert errors == []


# --- Ops assistant + capacites (B3) -----------------------------------------

def test_set_scene_transition_ops_apply_and_validate():
    base = _project()
    sid = base["content"]["scenes"][1]["id"]
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "set_scene", "scene_id": sid, "path": "transition.type", "value": "fade"},
        {"op": "set_scene", "scene_id": sid, "path": "transition.frames", "value": 14},
    ])
    assert candidate["content"]["scenes"][1]["transition"] == {"type": "fade", "frames": 14}
    assert [c["target"] for c in changes] == [f"scene {sid}.transition.type", f"scene {sid}.transition.frames"]
    errors, _ = proposals.validate_candidate(candidate)
    assert errors == []
    resolved = resolve.resolve(candidate)["resolved"]
    assert resolved["scenes"][1]["transition"] == {"type": "fade", "frames": 14}


def test_set_scene_transition_type_rejects_unknown_with_repair():
    base = _project()
    sid = base["content"]["scenes"][1]["id"]
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.apply_operations(base, [
            {"op": "set_scene", "scene_id": sid, "path": "transition.type", "value": "bogus"},
        ])
    assert exc.value.kind == "invalid_operations"
    assert "transition.type" in str(exc.value)
    assert "fade" in str(exc.value) and "wipe" in str(exc.value), "le message liste les types reels"


def test_set_scene_transition_frames_out_of_bounds_rejected():
    base = _project()
    sid = base["content"]["scenes"][1]["id"]
    candidate, _, _ = proposals.apply_operations(base, [
        {"op": "set_scene", "scene_id": sid, "path": "transition.type", "value": "fade"},
        {"op": "set_scene", "scene_id": sid, "path": "transition.frames", "value": 999},
    ])
    errors, _ = proposals.validate_candidate(candidate)
    assert any("transition.frames" in e for e in errors)


def test_capabilities_manifest_exposes_transitions():
    fmt = capabilities.build()["project_format"]
    assert fmt["transition_types"] == list(schema.TRANSITION_TYPES)
    assert fmt["transition_frames_max"] == schema.TRANSITION_FRAMES_MAX


def test_transition_guidance_reaches_design_and_autopilot():
    manifest = capabilities.build()
    assert "transition.type" in capabilities.prompt_block(manifest)
    assert "transition.type" in capabilities.compact_prompt_block(manifest)
    for compact in (False, True):
        grounding = capabilities.autopilot_grounding(manifest, compact=compact)
        assert "transition.type" in grounding, f"transition absente du grounding (compact={compact})"