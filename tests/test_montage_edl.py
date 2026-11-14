"""Contrat EDL : validation pure, sans disque ni FFmpeg."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shortvideos import edl as edl_mod  # noqa: E402


def _edl(**overrides) -> dict:
    base = {
        "version": 1,
        "canvas": {"width": 1920, "height": 1080, "fps": 30},
        "cuts": [
            {"media": "media://a", "in": 0.0, "out": 2.0, "role": "hook", "reason": "ouverture"},
            {"media": "media://b", "in": 0.5, "out": 3.0, "role": "body", "reason": "decor",
             "transition": {"type": "fade", "duration": 0.5}},
        ],
        "audio": {"music": "media://music", "gain_db": -18, "duck": True,
                  "fade_in": 1.0, "fade_out": 2.0},
        "grade": {"look": "none", "saturation": 1.0, "contrast": 1.0},
    }
    base.update(overrides)
    return base


def _media_exists(media_id: str) -> bool:
    return media_id in {"a", "b", "music"}


def test_minimal_edl_is_valid():
    errors, warnings = edl_mod.validate(_edl(), media_exists=_media_exists)
    assert errors == []
    assert warnings == []


def test_normalize_fills_defaults_and_drops_unknown_keys():
    normalized = edl_mod.normalize(
        {
            "version": 1,
            "canvas": {"width": 1280, "height": 720, "fps": 25, "inconnu": True},
            "cuts": [{"media": "media://a", "out": 1.0, "extra": 42}],
            "inconnu": "valeur",
        }
    )
    assert normalized["canvas"] == {"width": 1280, "height": 720, "fps": 25}
    assert "inconnu" not in normalized
    assert normalized["cuts"][0]["in"] == 0.0
    assert normalized["cuts"][0]["role"] == "body"
    assert "extra" not in normalized["cuts"][0]
    assert normalized["grade"]["look"] == "none"


def test_remote_url_is_refused_and_ingestion_explained():
    bad = _edl()
    bad["cuts"][0]["media"] = "https://example.com/clip.mp4"
    errors, _ = edl_mod.validate(bad, media_exists=_media_exists)
    assert any("media://<id>" in e and "ingerer" in e for e in errors)


def test_missing_media_is_reported_with_index():
    errors, _ = edl_mod.validate(_edl(), media_exists=lambda media_id: media_id != "b")
    assert any(e.startswith("cuts[1].media") and "introuvable" in e for e in errors)


def test_unknown_role_transition_and_grade_are_refused():
    bad = _edl()
    bad["cuts"][0]["role"] = "hero"
    bad["cuts"][1]["transition"] = {"type": "starwipe", "duration": 0.5}
    bad["grade"]["look"] = "vintage"
    errors, _ = edl_mod.validate(bad, media_exists=_media_exists)
    joined = " | ".join(errors)
    assert "cuts[0].role" in joined and "hero" in joined
    assert "cuts[1].transition.type" in joined and "starwipe" in joined
    assert "grade.look" in joined and "vintage" in joined


def test_first_cut_cannot_have_a_transition():
    bad = _edl()
    bad["cuts"][0]["transition"] = {"type": "fade", "duration": 0.4}
    errors, _ = edl_mod.validate(bad, media_exists=_media_exists)
    assert any(e.startswith("cuts[0].transition") for e in errors)


def test_transition_cannot_eat_the_shorter_plan():
    bad = _edl()
    bad["cuts"][0]["out"] = 0.8  # plan de 0.8 s
    bad["cuts"][1]["transition"] = {"type": "fade", "duration": 0.5}
    errors, _ = edl_mod.validate(bad, media_exists=_media_exists)
    assert any("maximum 40%" in e for e in errors)


def test_at_most_four_distinct_transitions():
    cuts = []
    for index, name in enumerate(("cut", "fade", "dissolve", "wipeleft", "slideup")):
        cut = {"media": f"media://{chr(97 + index)}", "in": 0.0, "out": 2.0, "role": "body"}
        if index:
            cut["transition"] = {"type": name, "duration": 0.4}
        cuts.append(cut)
    many = _edl(cuts=cuts)
    errors, _ = edl_mod.validate(
        many, media_exists=lambda media_id: True
    )
    assert any("valeurs distinctes" in e for e in errors)


def test_timeline_duration_subtracts_transition_overlap():
    edl = edl_mod.normalize(_edl())
    # 2,0 + 2,5 bruts, 0,5 s de recouvrement
    assert edl_mod.timeline_duration(edl) == pytest.approx(4.0)


def test_cut_shorter_than_minimum_is_refused():
    bad = _edl()
    bad["cuts"][1]["out"] = bad["cuts"][1]["in"] + 0.1
    errors, _ = edl_mod.validate(bad, media_exists=_media_exists)
    assert any("plan trop court" in e for e in errors)


def test_odd_canvas_is_refused():
    bad = _edl(canvas={"width": 1921, "height": 1080, "fps": 30})
    errors, _ = edl_mod.validate(bad, media_exists=_media_exists)
    assert any("pair" in e for e in errors)


def test_music_without_media_reference_is_refused():
    bad = _edl(audio={"music": "C:/musique.mp3", "gain_db": -18})
    errors, _ = edl_mod.validate(bad, media_exists=_media_exists)
    assert any(e.startswith("audio.music") for e in errors)


def test_validate_or_raise_lists_every_error():
    bad = _edl()
    bad["canvas"]["fps"] = 5
    bad["cuts"][0]["media"] = "media://"
    bad["grade"]["look"] = "x"
    with pytest.raises(edl_mod.EdlError) as excinfo:
        edl_mod.validate_or_raise(bad, media_exists=_media_exists)
    assert len(excinfo.value.errors) >= 3
    assert isinstance(excinfo.value.warnings, list)


def test_duplicate_media_is_a_warning_not_a_blocker():
    edl = _edl()
    edl["cuts"][0]["media"] = edl["cuts"][1]["media"] = "media://a"
    errors, warnings = edl_mod.validate(edl, media_exists=_media_exists)
    assert errors == []
    assert any("deja utilise" in w for w in warnings)


def test_empty_edl_is_refused():
    errors, _ = edl_mod.validate(
        {"version": 1, "canvas": {"width": 1920, "height": 1080, "fps": 30}, "cuts": []}
    )
    assert any("au moins un plan" in e for e in errors)
