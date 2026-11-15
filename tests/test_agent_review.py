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
from server.agent import llm_client, proposals, review
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


# --------------------------------------------------------------------------- #
# Passe de vision optionnelle (bornée, advisory, séparée de la boucle texte)
# --------------------------------------------------------------------------- #

def _fake_chat_routing(monkeypatch, correction=None, vision=None, vision_error=None):
    """Aiguille selon le type de contenu : liste = vision, chaîne = correction texte."""
    seen = {"correction": [], "vision": [], "n": 0}

    def chat(messages, cfg=None, max_tokens=None, json_mode=True, cancel=None, stream=False):
        seen["n"] += 1
        if any(isinstance(m.get("content"), list) for m in messages):
            seen["vision"].append(messages)
            if vision_error is not None:
                raise vision_error
            payload = vision if vision is not None else {"summary": "vu", "findings": []}
            return FakeResult(json.dumps(payload, ensure_ascii=False))
        seen["correction"].append(messages)
        payload = correction if correction is not None else {"summary": "ok", "operations": []}
        return FakeResult(json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(llm_client, "chat", chat)
    return seen


def test_vision_findings_validation_is_bounded_and_normalized():
    used = [10, 20]
    reply = {"summary": "s", "findings": [
        {"frame": 20, "issue": "contraste faible", "severity": "warning"},
        {"frame": 999, "issue": "frame inconnu", "severity": "critical"},
        {"frame": 10, "issue": "x", "severity": "n'importe quoi"},
        {"issue": ""},
        "pas un dict",
    ]}
    out = review._vision_findings(reply, used)
    assert len(out) == 3
    assert out[0] == {"frame": 20, "issue": "contraste faible", "severity": "warning"}
    assert out[1]["frame"] == 10  # frame hors images montrées -> ramené au premier
    assert out[2]["severity"] == "info"  # sévérité inconnue -> info
    many = {"findings": [{"frame": 10, "issue": f"i{i}", "severity": "info"} for i in range(30)]}
    assert len(review._vision_findings(many, used)) == review._VISION_MAX_FINDINGS
    with pytest.raises(proposals.ProposalError):
        review._vision_findings({"summary": "s"}, used)


def test_vision_pass_disabled_short_circuits(tmp_path, monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("Le LLM ne doit pas être appelé quand la vision est désactivée.")

    monkeypatch.setattr(llm_client, "chat", never)
    out = review._vision_pass(jobs.Job("test"), tmp_path, [0], {"max_tokens": 8000}, "p")
    assert out == {"ran": False, "reason": "disabled"}


def test_vision_pass_bounded_to_four_frames(tmp_path, monkeypatch):
    for frame in range(6):
        (tmp_path / f"frame-{frame}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    seen = {}

    def chat(messages, **kwargs):
        seen["messages"] = messages
        return FakeResult(json.dumps({"summary": "s", "findings": []}))

    monkeypatch.setattr(llm_client, "chat", chat)
    out = review._vision_pass(
        jobs.Job("test"), tmp_path, [0, 1, 2, 3, 4, 5],
        {"vision_review": True, "max_tokens": 8000}, "vérifie",
    )
    assert out["ran"] is True
    assert out["frames_used"] == [0, 1, 2, 3]
    parts = seen["messages"][1]["content"]
    images = [p for p in parts if p.get("type") == "image_url"]
    assert len(images) == 4
    assert all(p["image_url"]["url"].startswith("data:image/png;base64,") for p in images)


def test_vision_pass_no_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_client, "chat", lambda *a, **k: FakeResult("{}"))
    out = review._vision_pass(jobs.Job("test"), tmp_path, [], {"vision_review": True}, "p")
    assert out == {"ran": False, "reason": "no_frames"}


def test_vision_pass_cancel_respected(tmp_path, monkeypatch):
    (tmp_path / "frame-0.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.setattr(llm_client, "chat", lambda *a, **k: FakeResult("{}"))
    job = jobs.Job("test")
    job.cancel_event.set()
    with pytest.raises(jobs.JobCancelled):
        review._vision_pass(job, tmp_path, [0], {"vision_review": True}, "p")


def test_vision_disabled_by_default(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["clean"])
    seen = _fake_chat_routing(monkeypatch)
    result = review.review_project(jobs.Job("test"), _project(), "vérifie", {"max_tokens": 8000})
    assert seen["n"] == 0
    assert result["vision"] == {"ran": False, "reason": "disabled"}
    assert "sans vision" in result["limitations"]


def test_vision_enabled_is_advisory_and_sends_images(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["clean"])
    seen = _fake_chat_routing(monkeypatch, vision={
        "summary": "contraste faible",
        "findings": [{"frame": 0, "issue": "texte peu lisible sur le fond", "severity": "warning"}],
    })
    result = review.review_project(
        jobs.Job("test"), _project(), "vérifie", {"max_tokens": 8000, "vision_review": True},
    )
    assert seen["n"] == 1, "projet propre : aucune correction texte, seulement la vision"
    assert len(seen["vision"]) == 1 and not seen["correction"]
    parts = seen["vision"][0][1]["content"]
    assert isinstance(parts, list)
    assert any(
        p.get("type") == "image_url" and "data:image/png;base64," in p["image_url"]["url"]
        for p in parts
    )
    assert result["vision"]["ran"] is True
    assert result["vision"]["findings"]
    assert result["operations"] == [], "la vision est advisory : aucune opération ajoutée"
    assert result["verified"] is True
    assert "sans vision" not in result["limitations"]
    assert "consultative" in result["limitations"]


def test_vision_keeps_correction_loop_text_only(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["defect", "clean"])
    seen = _fake_chat_routing(monkeypatch, correction=CORRECTION, vision={"summary": "vu", "findings": []})
    result = review.review_project(
        jobs.Job("test"), _project(), "vérifie", {"max_tokens": 8000, "vision_review": True},
    )
    assert seen["n"] == 2, "une correction texte + une passe vision, pas plus"
    assert len(seen["correction"]) == 1 and len(seen["vision"]) == 1
    for message in seen["correction"][0]:
        assert isinstance(message["content"], str)
        assert "data:image" not in message["content"]
        assert "base64" not in message["content"]
    assert result["operations"] == CORRECTION["operations"], "la vision n'ajoute aucune opération"
    assert result["vision"]["ran"] is True


def test_vision_model_error_degrades_gracefully(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["clean"])
    error = llm_client.LLMError("le modèle ne voit pas les images", llm_client.KIND_HTTP)
    _fake_chat_routing(monkeypatch, vision_error=error)
    result = review.review_project(
        jobs.Job("test"), _project(), "vérifie", {"max_tokens": 8000, "vision_review": True},
    )
    assert result["vision"]["ran"] is False
    assert result["verified"] is True, "l'audit technique reste concluant"
    assert result["operations"] == []
    assert "sans vision" in result["limitations"]


def test_vision_invalid_reply_degrades(monkeypatch, no_fonts, fake_import):
    _fake_render(monkeypatch, ["clean"])
    _fake_chat_routing(monkeypatch, vision={"summary": "s"})  # pas de findings
    result = review.review_project(
        jobs.Job("test"), _project(), "vérifie", {"max_tokens": 8000, "vision_review": True},
    )
    assert result["vision"]["ran"] is False
    assert result["operations"] == []