"""B-roll automatique (G4) : appariement de thème pur, sans disque ni LLM.

Le helper ne touche pas au projet d'origine et ne pose un visuel que sur une
correspondance franche, jamais par-dessus un fond ou un calque média déjà choisi.
"""
from __future__ import annotations

import copy

from shortvideos import broll, schema

IMG = {"ref": "media://montagne-img", "name": "montagne.png", "kind": "image", "folder": "Paysages"}
VID = {"ref": "media://montagne-vid", "name": "montagne.mp4", "kind": "video", "folder": "Paysages"}


def _scene(sid: str, label: str, text: str, *, visual: bool = False, bg: str = "", hidden: bool = False) -> dict:
    layers = [schema.text_layer("title", text)]
    if visual:
        slot = schema.image_layer("visual", media="", position={"x": 0.5, "y": 0.36, "width": 0.68})
        slot["hidden"] = True
        layers.insert(0, slot)
    scene = schema.scene(sid, label, 4.0, layers, media=bg)
    scene["hidden"] = hidden
    return scene


def _project(*scenes: dict) -> dict:
    project = schema.new_project("quote_cinematic")
    project["content"]["scenes"] = list(scenes)
    return project


def _bg(project: dict, index: int = 0) -> str:
    return project["content"]["scenes"][index]["background"]["media"]


def test_confident_match_sets_background():
    project = _project(_scene("s1", "Paysage", "La montagne nous appelle."))
    out = broll.auto_broll(project, [IMG])
    assert _bg(out) == IMG["ref"]


def test_image_fills_hidden_visual_slot():
    project = _project(_scene("s1", "Détail", "La montagne.", visual=True))
    out = broll.auto_broll(project, [IMG])
    scene = out["content"]["scenes"][0]
    slot = next(layer for layer in scene["layers"] if layer["id"] == "visual")
    assert slot["media"] == IMG["ref"] and slot["hidden"] is False
    assert scene["background"]["media"] == ""  # le fond n'est pas touché


def test_video_uses_background_not_image_slot():
    project = _project(_scene("s1", "Détail", "La montagne.", visual=True))
    out = broll.auto_broll(project, [VID])
    scene = out["content"]["scenes"][0]
    slot = next(layer for layer in scene["layers"] if layer["id"] == "visual")
    assert scene["background"]["media"] == VID["ref"]
    assert slot["hidden"] is True and slot["media"] == ""  # <Img> ne rend pas une vidéo


def test_never_overwrites_existing_background():
    project = _project(_scene("s1", "Paysage", "La montagne.", bg="media://deja-choisi"))
    out = broll.auto_broll(project, [IMG])
    assert _bg(out) == "media://deja-choisi"


def test_never_overwrites_visible_media_layer():
    scene = _scene("s1", "Paysage", "La montagne.")
    scene["layers"].append(schema.image_layer("logo", media="media://logo-existant"))
    out = broll.auto_broll(_project(scene), [IMG])
    assert _bg(out) == ""


def test_no_match_leaves_scene_unchanged():
    project = _project(_scene("s1", "Citation", "Le courage de continuer."))
    out = broll.auto_broll(project, [IMG])
    assert _bg(out) == ""


def test_no_assets_returns_equal_clone():
    project = _project(_scene("s1", "Paysage", "La montagne."))
    out = broll.auto_broll(project, [])
    assert out == project and out is not project


def test_stopword_asset_never_matches():
    asset = {"ref": "media://bruit", "name": "avec.png", "kind": "image"}
    project = _project(_scene("s1", "Paysage", "La montagne."))
    assert _bg(broll.auto_broll(project, [asset])) == ""


def test_accent_and_case_insensitive_match():
    asset = {"ref": "media://pic", "name": "MONTAGNE.PNG", "kind": "image"}
    project = _project(_scene("s1", "Paysage", "La montagné enneigée."))
    assert _bg(broll.auto_broll(project, [asset])) == "media://pic"


def test_variety_prefers_unused_asset_on_tie():
    project = _project(
        _scene("s1", "Paysage", "La montagne."),
        _scene("s2", "Paysage", "Encore la montagne."),
    )
    out = broll.auto_broll(project, [IMG, VID])
    assert _bg(out, 0) != _bg(out, 1)
    assert {_bg(out, 0), _bg(out, 1)} == {IMG["ref"], VID["ref"]}


def test_hidden_scene_is_skipped():
    project = _project(_scene("s1", "Paysage", "La montagne.", hidden=True))
    assert _bg(broll.auto_broll(project, [IMG])) == ""


def test_min_score_threshold():
    project = _project(_scene("s1", "Paysage", "La montagne."))
    assert _bg(broll.auto_broll(project, [IMG], min_score=2)) == ""
    assert _bg(broll.auto_broll(project, [IMG], min_score=1)) == IMG["ref"]


def test_original_project_is_not_mutated():
    project = _project(_scene("s1", "Paysage", "La montagne.", visual=True))
    before = copy.deepcopy(project)
    broll.auto_broll(project, [IMG])
    assert project == before