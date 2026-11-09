"""Tests du catalogue d'effets : une seule liste, lue par tout le studio.

Le catalogue ``shortvideos/effects.py`` est la source de verite. Il est lu par
la validation, la resolution, la route ``/api/studio/effects``, l'inspecteur de
l'editeur et l'assistant. Ces tests verifient donc trois choses :

1. le catalogue est interne coherent (identifiants uniques, reglages bornes) ;
2. il correspond exactement a ce que le rendu Remotion implemente (registry.ts) ;
3. l'assistant ne peut proposer et appliquer que ce catalogue.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from server.agent import capabilities, proposals, tools  # noqa: E402
from server.app import app  # noqa: E402
from shortvideos import effects as fx  # noqa: E402
from shortvideos import schema  # noqa: E402

client = TestClient(app)

REGISTRY = ROOT / "web" / "src" / "remotion" / "effects" / "registry.ts"


# --------------------------------------------------------------------- catalogue
def test_catalog_identifiers_are_unique_and_declared_once():
    ids = fx.ids()
    assert len(ids) == len(set(ids)), "identifiant d'effet declare deux fois"
    categories = {key for key, _ in fx.CATEGORIES}
    for item in fx.all_effects():
        assert item["category"] in categories
        assert set(item["scopes"]) <= set(fx.SCOPES) and item["scopes"]
        assert set(item["targets"]) <= set(fx.TARGETS) and item["targets"]


def test_catalog_params_are_wellformed_and_defaults_in_range():
    for item in fx.all_effects():
        keys = [p["key"] for p in item["params"]]
        assert len(keys) == len(set(keys)), f"{item['id']} : cle de reglage dupliquee"
        for spec in item["params"]:
            assert spec["type"] in fx.PARAM_TYPES, spec
            default = spec["default"]
            if spec["type"] in ("number", "integer"):
                assert spec["min"] <= default <= spec["max"], f"{item['id']}.{spec['key']}"
                if spec["type"] == "integer":
                    assert float(default).is_integer()
            elif spec["type"] == "select":
                assert default in spec["options"], f"{item['id']}.{spec['key']}"
            elif spec["type"] == "color":
                assert fx._is_hex_color(str(default))
            elif spec["type"] == "bool":
                assert isinstance(default, bool)
            else:
                assert isinstance(default, str)


def test_audio_flagged_effects_measure_real_audio():
    audio_ids = [f["id"] for f in fx.all_effects() if f["needs_audio"]]
    assert {"audio_pulse", "audio_spectrum", "audio_waveform"} <= set(audio_ids)


# ------------------------------------------------------------- coherence du rendu
def test_registry_ts_implements_exactly_the_catalog():
    """Un effet au catalogue sans rendu (ou l'inverse) doit casser ici."""
    source = REGISTRY.read_text(encoding="utf-8")
    rendered: set[str] = set()
    for name in ("LAYER_EFFECT_IDS", "IMAGE_EFFECT_IDS", "SCENE_EFFECT_IDS", "OVERLAY_EFFECT_IDS"):
        block = re.search(rf"{name}[^\[]*\[(.*?)\]", source, re.DOTALL)
        assert block, f"tableau {name} introuvable dans registry.ts"
        rendered.update(re.findall(r'"([a-z0-9_]+)"', block.group(1)))
    assert rendered == set(fx.ids()), (
        f"catalogue sans rendu : {sorted(rendered ^ set(fx.ids()))}"
    )


# ------------------------------------------------------------------- normalisation
def test_normalize_accepts_short_and_tuned_forms():
    short, errors, warnings = fx.normalize(["shine"], "layer", "text", path="calque")
    assert errors == [] and warnings == []
    assert short[0]["id"] == "shine"
    assert short[0]["params"] == fx.default_params(fx.get("shine"))
    tuned, errors, _ = fx.normalize([{"id": "shine", "params": {"width": 0.5}}], "layer", "text", path="c")
    assert errors == []
    assert tuned[0]["params"]["width"] == 0.5


def test_normalize_rejects_unknown_duplicate_and_wrong_scope():
    _out, errors, _w = fx.normalize(["nimporte"], "layer", "text", path="c")
    assert errors and "effet inconnu" in errors[0]
    assert all(i in errors[0] for i in fx.ids()[:3]), "la liste des choix doit etre dans le message"

    _out, errors, _w = fx.normalize(["shine", "shine"], "layer", "text", path="c")
    assert any("deux fois" in e for e in errors)

    _out, errors, _w = fx.normalize(["plasma_field"], "layer", "text", path="c")
    assert any("ne s'applique pas a un calque" in e for e in errors)

    _out, errors, _w = fx.normalize(["spring_pop"], "scene", "scene", path="s")
    assert any("ne s'applique pas a une scene" in e for e in errors)


def test_normalize_rejects_effect_on_the_wrong_layer_type():
    image_only = next(f["id"] for f in fx.all_effects() if "image" in f["targets"] and "text" not in f["targets"])
    _out, errors, _w = fx.normalize([image_only], "layer", "text", path="c")
    assert any("est prevu pour un calque" in e for e in errors)


def test_normalize_clamps_out_of_range_and_warns():
    spec = next(p for p in fx.get("shine")["params"] if p["type"] == "number")
    out, errors, warnings = fx.normalize(
        [{"id": "shine", "params": {spec["key"]: spec["max"] + 100}}], "layer", "text", path="c"
    )
    assert errors == []
    assert out[0]["params"][spec["key"]] == spec["max"]
    assert any("hors bornes" in w for w in warnings)


def test_normalize_enforces_the_per_target_cap():
    five = fx.ids()[:5]
    _out, errors, _w = fx.normalize(five, "layer", "text", path="c")
    assert any("maximum 4 par cible" in e for e in errors)


def test_audio_dependent_effect_warns_without_audio():
    _out, errors, warnings = fx.normalize(["audio_pulse"], "layer", "text", path="c", audio_ready=False)
    assert errors == [] and any("audio reelle" in w for w in warnings)
    _out, _e, warnings = fx.normalize(["audio_pulse"], "layer", "text", path="c", audio_ready=True)
    assert warnings == []


# ------------------------------------------------------------------------- route
def test_effects_route_serves_the_catalog():
    res = client.get("/api/studio/effects")
    assert res.status_code == 200
    data = res.json()
    assert data["max_per_target"] == fx.MAX_EFFECTS_PER_TARGET
    assert [e["id"] for e in data["effects"]] == fx.ids()
    assert {c["id"] for c in data["categories"]} == {k for k, _ in fx.CATEGORIES}


def test_prepare_keeps_effect_errors_blocking():
    project = schema.new_project("quote_cinematic")
    project["content"]["scenes"][0]["layers"][0]["effects"] = ["effet_fantome"]
    res = client.post("/api/studio/prepare", json={"project": project})
    assert res.status_code == 400 or (res.status_code == 200 and res.json()["errors"])
    body = res.json() if res.status_code == 200 else {"detail": res.json()["detail"]}
    text = str(body)
    assert "effet_fantome" in text


# -------------------------------------------------------------------- assistant
def test_capabilities_manifest_and_prompt_carry_the_catalog():
    manifest = capabilities.build()
    assert [f["id"] for f in manifest["effects"]["effects"]] == fx.ids()
    assert manifest["project_format"]["effects_max_per_target"] == fx.MAX_EFFECTS_PER_TARGET

    prompt = capabilities.prompt_block(manifest)
    for item in fx.all_effects():
        assert item["id"] in prompt, f"{item['id']} absent du prompt capacites"

    compact = capabilities.compact_prompt_block(manifest)
    assert "set_effects" in compact
    assert all(i in compact for i in fx.ids())


def test_list_effects_tool_filters_and_bounds():
    layer_text = tools.execute("list_effects", {"scope": "layer", "target": "text"}, {})
    assert {e["id"] for e in layer_text["effects"]} == {
        f["id"] for f in fx.all_effects() if "layer" in f["scopes"] and "text" in f["targets"]
    }
    shine = tools.execute("list_effects", {"id": "shine"}, {})["effects"][0]
    assert shine["params"], "les reglages doivent etre renvoyes pour ecrire des params valides"
    width = next(p for p in shine["params"] if p["key"] == "width")
    assert {"min", "max", "default", "type"} <= set(width)

    for args, message in (
        ({"id": "nope"}, "Effet inconnu"),
        ({"scope": "tunnel"}, "Portée inconnue"),
        ({"category": "tunnel"}, "Catégorie inconnue"),
    ):
        try:
            tools.execute("list_effects", args, {})
        except tools.ToolError as e:
            assert message in str(e)
        else:
            raise AssertionError(f"{args} aurait du etre refuse")


def _one_scene_project() -> dict:
    project = schema.new_project("quote_cinematic")
    return project


def test_set_effects_applies_compact_forms():
    base = _one_scene_project()
    scene = base["content"]["scenes"][0]
    layer_id = scene["layers"][0]["id"]
    candidate, changes, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": scene["id"], "layer_id": layer_id,
         "effects": [{"id": "shine", "params": {"width": 0.4}}]},
        {"op": "set_effects", "scene_id": scene["id"], "effects": ["plasma_field"]},
    ])
    stored_layer = candidate["content"]["scenes"][0]["layers"][0]["effects"]
    assert stored_layer == [{"id": "shine", "params": {"width": 0.4}}]
    assert candidate["content"]["scenes"][0]["effects"] == ["plasma_field"]
    assert [c["target"] for c in changes] == [f"{scene['id']}/{layer_id}.effects", f"scene {scene['id']}.effects"]
    errors, _warnings = proposals.validate_candidate(candidate)
    assert errors == []


def test_set_effects_rejects_invented_ids_and_out_of_scope():
    base = _one_scene_project()
    scene = base["content"]["scenes"][0]
    for effects in (["effet_invente"], ["plasma_field"]):
        try:
            proposals.apply_operations(base, [
                {"op": "set_effects", "scene_id": scene["id"],
                 "layer_id": scene["layers"][0]["id"], "effects": effects},
            ])
        except proposals.ProposalError as e:
            assert e.kind == "invalid_operations"
        else:
            raise AssertionError(f"{effects} aurait du etre refuse")


def test_set_effects_empty_list_removes_them():
    base = _one_scene_project()
    scene = base["content"]["scenes"][0]
    layer_id = scene["layers"][0]["id"]
    with_effect, _, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": scene["id"], "layer_id": layer_id, "effects": ["shine"]},
    ])
    emptied, changes, _ = proposals.apply_operations(with_effect, [
        {"op": "set_effects", "scene_id": scene["id"], "layer_id": layer_id, "effects": []},
    ])
    assert emptied["content"]["scenes"][0]["layers"][0]["effects"] == []
    assert changes[0]["before"] == ["shine"]


def test_set_effects_warns_when_audio_is_not_ready():
    base = _one_scene_project()
    scene = base["content"]["scenes"][0]
    candidate, _, _ = proposals.apply_operations(base, [
        {"op": "set_effects", "scene_id": scene["id"], "effects": ["audio_spectrum"]},
    ])
    _errors, warnings = proposals.validate_candidate(candidate)
    assert any("audio reelle" in w for w in warnings)

    base["audio"]["enabled"] = True
    base["audio"]["music"] = "media://absent"
    assert proposals._audio_ready(base) is True
