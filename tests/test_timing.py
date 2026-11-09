"""Tests des calculs de duree et d'animation (shortvideos.timing)."""
import pytest

from shortvideos import project as project_mod
from shortvideos import timing


@pytest.fixture
def proj():
    p = project_mod.default_project()
    p["timing"] = {"duration": 8.0, "text_start": 1.0, "fade_in": 1.0, "fade_out": 2.0}
    p["export"]["fps"] = 30
    return p


def test_duration(proj):
    assert timing.duration(proj) == 8.0


def test_frame_count(proj):
    assert timing.frame_count(proj) == 240  # 8 s x 30 fps


def test_frame_count_rounding(proj):
    proj["timing"]["duration"] = 2.0
    proj["export"]["fps"] = 24
    assert timing.frame_count(proj) == 48


def test_frame_count_minimum_one(proj):
    proj["timing"]["duration"] = 0.5
    proj["export"]["fps"] = 1
    assert timing.frame_count(proj) == 1  # arrondi de 0.5 -> 0, mais minimum 1


def test_frame_time(proj):
    assert timing.frame_time(0, proj) == 0.0
    assert timing.frame_time(30, proj) == 1.0
    assert timing.frame_time(239, proj) == pytest.approx(239 / 30)


def test_alpha_before_start(proj):
    assert timing.text_alpha(0.5, proj) == 0.0


def test_alpha_mid_fade_in(proj):
    assert timing.text_alpha(1.5, proj) == pytest.approx(0.5)


def test_alpha_full_visibility(proj):
    assert timing.text_alpha(4.0, proj) == 1.0


def test_alpha_mid_fade_out(proj):
    # fade_out = 2.0, fin a 8.0 -> a t=7.0, alpha = (8-7)/2 = 0.5
    assert timing.text_alpha(7.0, proj) == pytest.approx(0.5)


def test_alpha_at_and_after_end(proj):
    assert timing.text_alpha(8.0, proj) == 0.0
    assert timing.text_alpha(9.0, proj) == 0.0


def test_alpha_monotone_during_fade_in(proj):
    alphas = [timing.text_alpha(t / 10, proj) for t in range(10, 21)]
    assert alphas == sorted(alphas)


def test_slide_offset_progressive(proj):
    proj["animation"]["text_in"] = "slide"
    # Au debut du fondu, decalage maximal ; a la fin, nul.
    h = proj["export"]["height"]
    assert timing.text_offset_y(1.0, proj) == int(round(0.05 * h))
    assert timing.text_offset_y(2.0, proj) == 0
    assert timing.text_offset_y(5.0, proj) == 0


def test_no_slide_when_fade(proj):
    assert timing.text_offset_y(1.0, proj) == 0


def test_background_zoom_monotone(proj):
    scales = [timing.background_scale(t / 10, proj) for t in range(0, 81, 5)]
    assert scales == sorted(scales)
    assert scales[0] == pytest.approx(1.0)
    assert scales[-1] == pytest.approx(1.08)


def test_background_static_when_disabled(proj):
    proj["animation"]["background"] = "static"
    assert timing.background_scale(8.0, proj) == 1.0
