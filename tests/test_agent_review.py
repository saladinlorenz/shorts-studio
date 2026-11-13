"""Correction technique sans VLM : la boucle audit → mesures → correction JSON.

Lois verrouillées ici :

- le LLM ne reçoit QUE du texte : projet JSON, mesures DOM, logs ; jamais d'image ;
- un défaut mesuré déclenche une correction JSON bornée, puis un RECONTRÔLE réel ;
- une réponse invalide est enregistrée comme erreur de round, jamais appliquée ;
- une erreur de rendu est transmise au LLM comme donnée, pas comme instruction ;
- « verified » est technique : aucun succès visuel n'est attesté ;
- le projet source n'est jamais muté ; l'annulation est respectée.

Le rendu Remotion et le LLM sont simulés ; la validation métier, l'application
des opérations et la détection de défauts sont le code de production.
"""
from __future__ import annotations

import copy
import json

import pytest

from server import jobs, media, render
from server.agent import llm_client, review
from shortvideos import fonts, schema


class FakeResult:
    def __init__(self, text: str):
        self.text = text
        self.latency_ms = 5
        self.model = "fake"


def _project() -> dict:
    return schema.new_project("quote_cinematic")


@pytest.fixture()
def no_fonts(monkeypatch):
    families = ["anton", "archivo-black", "inter", "playfair-display", "space-grotesk"]
    monkeypatch.setattr(fonts, "families", lambda: [{"id": fam, "complete": True} for fam in families])


@pytest.fixture()
def fake_import(monkeypatch):
    monkeypatch.setattr(media, "import_file_to_media", lambda path, source, **kw: "img" + path.stem[-4:])


def _fake_render(monkeypatch, passes):
    """passes : comportement par appel ('clean' | 'defect' | 'error'), répété si besoin."""
    calls = {"n": 0}

    def render_frames(job, candidate, frames, directory, audit_layout=False):
        assert audit_layout is True
        behavior = passes[min(calls["n"], len(passes) - 1)]
        calls["n"] += 1
        if behavior == "error":
            raise RuntimeError("Remotion frames [1] failed (code 1): log simulé")
        for frame in frames:
            elements = []
            for scene in candidate["content"]["scenes"]:
                if scene.get("hidden"):
                    continue
                for layer in scene.get("layers", []):
                    if layer.get("hidden"):
                        continue
                    defect = behavior == "defect" and scene["id"] == "s2" and layer["id"] == "quote"
                    elements.append({
                        "id": f"{scene['id']}/{layer['id']}", "kind": layer["type"], "frame": frame,
                        "x": 100, "y": 100, "w": 200, "h": 80, "visible": True, "opacity": 1,
                        "steady": True, "outOfFrame": defect, "textOverflow": False,
                        "safeAreaWarning": False, "fontSize": 88, "smallText": False,
                        "scrollW": 200, "clientW": 200, "scrollH": 80, "clientH": 80,
                        "color": "#fff", "contrast": None,
                    })
            report = {"frame": frame, "width": 1080, "height": 1920,
                      "elements": elements, "overlaps": [], "limits": "simulé"}
            (directory / f"frame-{frame}.json").write_text(json.dumps(report), encoding="utf-8")
            (directory / f"frame-{frame}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return [directory / f"frame-{f}.png" for f in frames]

    monkeypatch.setattr(render, "render_project_frames", render_frames)
    return calls


def _fake_llm(monkeypatch, replies):
    sentences = [json.dumps(r, ensure_ascii=False) for r in replies]
    seen = {"messages": [], "n": 0}

    def chat(messages, cfg=None, max_tokens=None, json_mode=True, cancel=None, stream=False):
        seen["messages"].append(messages)
        position = min(seen["n"], len(sentences) - 1)
        seen["n"] += 1
        return FakeResult(sentences[position])

    monkeypatch.setattr(llm_client, "chat", chat)
    return seen


CORRECTION = {"summary": "Réduire la citation.", "operations": [
    {"op": "set_layer", "scene_id": "s2", "layer_id": "quote", "path": "style.font_size", "value": 64}]}
INVALID = {"summary": "Cible inexistante.", "operations": [
    {"op": "set_layer", "scene_id": "fantome", "layer_id": "x", "path": "style.color", "value": "#fff"}]}


# --------------------------------------------------------------------------- #
# Gardes d'entrée
# --------------------------------------------------------------------------- #

def test_guards_refuse_unsupported_projects(no_fonts):
    job = jobs.Job("test")
    v1 = _project()
    v1["version"] = 1
    with pytest.raises(ValueError):
        review.review_project(job, v1, "vérifie", {})
    other = _project()
    other["model"]["id"] = "quote_vertical"
    with pytest.raises(ValueError):
        review.review_project(job, other, "vérifie", {})
    many = _project()
    base = many["content"]["scenes"][0]
    for index in range(13):
        scene = copy.deepcopy(base)
        scene["id"] = f"x{index}"
        many["content"]["scenes"].append(scene)
    with pytest.raises(ValueError):
        review.review_project(job, many, "vérifie", {})
    layers = _project()
    scene = layers["content"]["scenes"][0]
    template = scene["layers"][0]
    for index in range(61):
        layer = copy.deepcopy(template)
        layer["id"] = f"l{index}"
        scene["layers"].append(layer)
    with pytest.raises(ValueError):
        review.review_project(job, layers, "vérifie", {})
    big = _project()
    big["content"]["scenes"][0]["layers"][0]["text"] = "x" * 90000
    with pytest.raises(ValueError):
        review.review_project(job, big, "vérifie", {})


def test_frames_selection_is_bounded_and_includes_last():
    prepared = render.prepare_for_render(_project())
    frames = review._frames(prepared)
    total = prepared["resolved"]["total_frames"]
    assert 1 <= len(frames) <= 6
    assert len(set(frames)) == len(frames)
    assert frames[-1] == total - 1
    assert all(0 <= frame < total for frame in frames)


# --------------------------------------------------------------------------- #
# Boucle nominale
# --------------------------------------------------------------------------- #

def test_clean_project_verifies_without_llm(monkeypatch, no_fonts, fake_import):
    calls = _fake_render(monkeypatch, ["clean"])

    def never_chat(*args, **kwargs):
        raise AssertionError("Le LLM ne doit pas être appelé sur un projet propre.")

    monkeypatch.setattr(llm_client, "chat", never_chat)
    project = _project()
    before = copy.deepcopy(project)
    result = review.review_project(jobs.Job("test"), project, "vérifie", {"max_tokens": 8000})
    assert calls["n"] == 1
    assert result["verified"] is True
    assert result["verification_kind"] == "technical"
    assert result["operations"] == [] and result["rounds"] == []
    assert result["frames"] and all(f["ref"].startswith("media://") for f in result["frames"])
    assert "sans vision" in result["limitations"]
    assert project == before


def test_defect_triggers_text_correction_then_recheck(monkeypatch, no_fonts, fake_import):
    calls = _fake_render(monkeypatch, ["defect", "clean"])
    seen = _fake_llm(monkeypatch, [CORRECTION])
    result = review.review_project(jobs.Job("test"), _project(), "vérifie la lisibilité", {"max_tokens": 8000})
    assert calls["n"] == 2, "un recontrôle réel doit suivre la correction"
    assert seen["n"] == 1
    assert result["verified"] is True
    assert result["operations"] == CORRECTION["operations"]
    assert len(result["rounds"]) == 1 and result["rounds"][0]["summary"] == "Réduire la citation."

    system = seen["messages"][0][0]["content"]
    user = seen["messages"][0][1]["content"]
    assert "ne vois PAS les images" in system
    assert "AUDIT (données)" in user and "hors du cadre" in user
    assert "PROTOCOLE AUTORISÉ" in user
    for message in seen["messages"][0]:
        assert isinstance(message["content"], str)
        assert "data:image" not in message["content"]
        assert "base64" not in message["content"]


def test_invalid_llm_operations_are_recorded_not_applied(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["defect"])
    seen = _fake_llm(monkeypatch, [INVALID])
    result = review.review_project(jobs.Job("test"), _project(), "vérifie", {"max_tokens": 8000})
    assert seen["n"] == 2, "deux tentatives de correction avant l'arrêt"
    assert result["verified"] is False
    assert result["operations"] == []
    assert len(result["rounds"]) == 2
    assert all("error" in round_ for round_ in result["rounds"])
    assert "aucun succès visuel" in result["summary"]


def test_render_error_is_data_for_the_llm(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["error", "clean"])
    seen = _fake_llm(monkeypatch, [CORRECTION])
    result = review.review_project(jobs.Job("test"), _project(), "vérifie", {"max_tokens": 8000})
    assert result["verified"] is True
    assert "Remotion" in result["rounds"][0]["diagnostics"]["render_error"]
    assert result["error"] == ""
    assert result["frames"]


def test_cancel_is_respected(no_fonts):
    job = jobs.Job("test")
    job.cancel_event.set()
    with pytest.raises(jobs.JobCancelled):
        review.review_project(job, _project(), "vérifie", {})


def test_source_project_never_mutated(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["defect", "clean"])
    _fake_llm(monkeypatch, [CORRECTION])
    project = _project()
    before = copy.deepcopy(project)
    review.review_project(jobs.Job("test"), project, "vérifie", {"max_tokens": 8000})
    assert project == before