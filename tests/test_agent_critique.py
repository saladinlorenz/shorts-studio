"""Incrément 4 — direction artistique consultative (project_critique).

Lois verrouillées ici :

- le LLM ne reçoit QUE du texte : projet JSON + protocole ; jamais d'image ni de rendu ;
- un seul appel au modèle ; les améliorations sont des opérations revalidées côté serveur ;
- une réponse invalide ou une panne dégrade en avis textuel / « non exécutée », sans casser le suivi ;
- l'avis est consultatif : rien n'est appliqué par l'action, seule une proposition followup
  validée est produite, applicable uniquement après un clic humain (/accept) ;
- le projet source n'est jamais muté ; l'annulation est respectée ; aucun secret dans le contexte.

Le LLM est simulé ; la validation métier, l'application des opérations, le contrat
de confirmation et les jobs sont le code de production.
"""
from __future__ import annotations

import copy
import json
import time

import pytest
from fastapi.testclient import TestClient

from server import jobs, settings as settings_mod
from server.agent import actions, critique, llm_client, proposals
from server.app import app
from shortvideos import fonts, schema

client = TestClient(app)


class FakeResult:
    def __init__(self, text: str):
        self.text = text
        self.latency_ms = 5
        self.model = "fake-model"


def _project() -> dict:
    return schema.new_project("quote_cinematic")


@pytest.fixture()
def no_fonts(monkeypatch):
    families = ["anton", "archivo-black", "inter", "playfair-display", "space-grotesk"]
    monkeypatch.setattr(fonts, "families", lambda: [{"id": fam, "complete": True} for fam in families])


def _fake_chat(monkeypatch, reply=None, error=None):
    seen = {"messages": [], "n": 0}

    def chat(messages, cfg=None, max_tokens=None, json_mode=True, cancel=None, stream=False):
        seen["messages"].append(messages)
        seen["n"] += 1
        if error is not None:
            raise error
        return FakeResult(json.dumps(reply, ensure_ascii=False))

    monkeypatch.setattr(llm_client, "chat", chat)
    return seen


IMPROVEMENT = {"summary": "Renforcer la hiérarchie visuelle.", "operations": [
    {"op": "set_layer", "scene_id": "s2", "layer_id": "quote", "path": "style.font_size", "value": 64}]}
INVALID = {"summary": "Cible inexistante.", "operations": [
    {"op": "set_layer", "scene_id": "fantome", "layer_id": "x", "path": "style.color", "value": "#fff"}]}


# --------------------------------------------------------------------------- #
# Gardes d'entrée (mêmes bornes que l'audit technique)
# --------------------------------------------------------------------------- #
def test_guards_refuse_unsupported_projects(no_fonts):
    job = jobs.Job("test")
    v1 = _project()
    v1["version"] = 1
    with pytest.raises(ValueError):
        critique.critique_project(job, v1, "améliore", {})
    other = _project()
    other["model"]["id"] = "quote_vertical"
    with pytest.raises(ValueError):
        critique.critique_project(job, other, "améliore", {})
    many = _project()
    base = many["content"]["scenes"][0]
    for index in range(13):
        scene = copy.deepcopy(base)
        scene["id"] = f"x{index}"
        many["content"]["scenes"].append(scene)
    with pytest.raises(ValueError):
        critique.critique_project(job, many, "améliore", {})
    layers = _project()
    scene = layers["content"]["scenes"][0]
    template = scene["layers"][0]
    for index in range(61):
        layer = copy.deepcopy(template)
        layer["id"] = f"l{index}"
        scene["layers"].append(layer)
    with pytest.raises(ValueError):
        critique.critique_project(job, layers, "améliore", {})
    big = _project()
    big["content"]["scenes"][0]["layers"][0]["text"] = "x" * 90000
    with pytest.raises(ValueError):
        critique.critique_project(job, big, "améliore", {})


# --------------------------------------------------------------------------- #
# Passe nominale : un seul appel texte, opérations revalidées
# --------------------------------------------------------------------------- #
def test_valid_reply_proposes_validated_operations(monkeypatch, no_fonts):
    seen = _fake_chat(monkeypatch, IMPROVEMENT)
    project = _project()
    before = copy.deepcopy(project)
    result = critique.critique_project(jobs.Job("test"), project, "améliore la composition", {"max_tokens": 8000})
    assert seen["n"] == 1, "un seul appel au modèle"
    assert result["ran"] is True
    assert result["verification_kind"] == "artistic"
    assert result["operations"] == IMPROVEMENT["operations"]
    assert result["summary"] == "Renforcer la hiérarchie visuelle."
    assert "consultatif" in result["limitations"]
    assert project == before, "le projet source n'est jamais muté"
    system = seen["messages"][0][0]["content"]
    user = seen["messages"][0][1]["content"]
    assert "ne vois PAS les images" in system
    assert "PROTOCOLE AUTORISÉ" in user and "PROJET (données)" in user
    assert "EFFETS RÉELS" in user and "POLICES DISPONIBLES" in user
    for message in seen["messages"][0]:
        assert isinstance(message["content"], str)
        assert "data:image" not in message["content"]
        assert "base64" not in message["content"]


def test_invalid_operations_degrade_to_text_only(monkeypatch, no_fonts):
    _fake_chat(monkeypatch, INVALID)
    result = critique.critique_project(jobs.Job("test"), _project(), "améliore", {"max_tokens": 8000})
    assert result["ran"] is True
    assert result["operations"] == [], "des opérations invalides ne sont jamais proposées"
    assert any("non validées" in w for w in result["warnings"])
    assert result["summary"] == "Cible inexistante."


def test_empty_operations_is_advisory_only(monkeypatch, no_fonts):
    _fake_chat(monkeypatch, {"summary": "Le projet est cohérent, rien à changer.", "operations": []})
    result = critique.critique_project(jobs.Job("test"), _project(), "améliore", {"max_tokens": 8000})
    assert result["ran"] is True
    assert result["operations"] == []
    assert result["summary"] == "Le projet est cohérent, rien à changer."


def test_operations_bounded_to_twenty(monkeypatch, no_fonts):
    many = {"summary": "s", "operations": [
        {"op": "set_layer", "scene_id": "s2", "layer_id": "quote", "path": "style.font_size", "value": 64}
        for _ in range(25)]}
    _fake_chat(monkeypatch, many)
    result = critique.critique_project(jobs.Job("test"), _project(), "améliore", {"max_tokens": 8000})
    assert result["ran"] is True
    assert len(result["operations"]) == critique._CRITIQUE_MAX_OPS == 20


def test_llm_error_degrades_gracefully(monkeypatch, no_fonts):
    error = llm_client.LLMError("modèle indisponible", llm_client.KIND_HTTP)
    _fake_chat(monkeypatch, error=error)
    result = critique.critique_project(jobs.Job("test"), _project(), "améliore", {"max_tokens": 8000})
    assert result["ran"] is False
    assert "modèle indisponible" in result["reason"]
    assert result["verification_kind"] == "artistic"
    assert "operations" not in result


def test_invalid_reply_shape_degrades(monkeypatch, no_fonts):
    _fake_chat(monkeypatch, {"pas_summary": "x"})
    result = critique.critique_project(jobs.Job("test"), _project(), "améliore", {"max_tokens": 8000})
    assert result["ran"] is False


def test_cancel_is_respected(no_fonts):
    job = jobs.Job("test")
    job.cancel_event.set()
    with pytest.raises(jobs.JobCancelled):
        critique.critique_project(job, _project(), "améliore", {})


# --------------------------------------------------------------------------- #
# Contrat de l'action confirmée
# --------------------------------------------------------------------------- #
@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    settings_mod.save_settings({"llm_context_budget": 20000, "llm_max_tokens": 8000})
    return tmp_path / "settings.json"


def test_catalog_includes_project_critique():
    names = {a["name"] for a in actions.catalog()["actions"]}
    assert "project_critique" in names


def test_project_critique_requires_valid_project():
    with pytest.raises(actions.ActionError):
        actions.describe("project_critique", {}, None)
    broken = _project()
    broken["content"]["scenes"][0]["layers"][0]["style"]["font_size"] = 99999
    with pytest.raises(actions.ActionError):
        actions.describe("project_critique", {}, broken)


def test_project_critique_context_has_revision_and_text_only_destination(isolated_settings):
    settings_mod.save_settings({"llm_local_api_key": "cle-secrete-test"})
    project = _project()
    descriptor = actions.describe("project_critique", {}, project)
    assert descriptor["context"]["project_revision"] == proposals.revision_of(project)
    assert set(descriptor["context"]["destination"]) == {"provider", "model", "base_url"}
    serialized = json.dumps(descriptor, ensure_ascii=False)
    assert "cle-secrete-test" not in serialized
    assert any("Aucun rendu" in line for line in descriptor["impact"])
    assert any("jamais appliquées automatiquement" in line for line in descriptor["impact"])


# --------------------------------------------------------------------------- #
# Parcours HTTP complet : proposition → confirmation → avis consultatif
# --------------------------------------------------------------------------- #
def _action_reply(name: str, params: dict) -> dict:
    return {"type": "studio_action", "summary": "Action proposée.", "action": {"name": name, "params": params}}


def _ask(payload: dict) -> dict:
    response = client.post("/api/agent/ask", json=payload)
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(200):
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] != "running":
            break
        time.sleep(0.05)
    assert snapshot is not None and snapshot["status"] == "done", snapshot
    return snapshot["result"]


def _execute(proposal_id: str, confirmation: str, project=None) -> tuple[int, dict]:
    response = client.post(
        f"/api/agent/proposals/{proposal_id}/execute",
        json={"confirmation": confirmation, "project": project},
    )
    return response.status_code, response.json()


def _finished(job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] != "running":
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} jamais terminé")


def test_project_critique_revision_conflict_is_409(fake_llm_actions, isolated_settings):
    project = _project()
    fake_llm_actions(_action_reply("project_critique", {"prompt": "améliore"}))
    proposal = _ask({"message": "avis artistique", "project": project, "project_name": "citation"})["proposal"]
    changed = _project()
    changed["content"]["scenes"][0]["layers"][0]["text"] = "autre accroche"
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], changed)
    assert status == 409
    assert body["detail"]["current_revision"] == proposals.revision_of(changed)


def test_project_critique_execute_produces_advisory_proposal(fake_llm_actions, isolated_settings, monkeypatch):
    project = _project()
    fake_llm_actions(_action_reply("project_critique", {"prompt": "améliore la typographie"}))
    seen = {}

    def fake_critique(job, candidate, prompt, cfg):
        seen["prompt"] = prompt
        seen["project"] = candidate
        return {
            "ran": True, "summary": "Renforcer la hiérarchie visuelle.",
            "operations": [{"op": "set_layer", "scene_id": "s2", "layer_id": "quote",
                            "path": "style.color", "value": "#2aa8c9"}],
            "warnings": [], "model": "fake-model", "verification_kind": "artistic",
            "limitations": "Avis artistique consultatif.",
        }

    monkeypatch.setattr(critique, "critique_project", fake_critique)
    proposal = _ask({"message": "avis artistique", "project": project, "project_name": "citation"})["proposal"]
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], project)
    assert status == 200, body
    snapshot = _finished(body["job_id"])
    assert snapshot["status"] == "done", snapshot
    assert seen["prompt"] == "améliore la typographie"
    correction = snapshot["result"]["proposal"]
    assert correction["type"] == "project_patch"
    assert correction["validation"]["state"] == "valid"
    # L'action n'applique rien : seule une proposition followup est produite.
    assert snapshot["result"]["ran"] is True
    assert snapshot["result"]["verification_kind"] == "artistic"

    # Application uniquement après un clic humain explicite (/accept).
    accept = client.post(f"/api/agent/proposals/{correction['id']}/accept", json={"project": project})
    assert accept.status_code == 200, accept.text
    applied = accept.json()
    assert applied["kind"] == "project"
    quote = applied["project"]["content"]["scenes"][1]["layers"][0]
    assert quote["style"]["color"] == "#2aa8c9"


def test_project_critique_without_operations_has_no_proposal(fake_llm_actions, isolated_settings, monkeypatch):
    project = _project()
    fake_llm_actions(_action_reply("project_critique", {"prompt": "améliore"}))
    monkeypatch.setattr(critique, "critique_project", lambda job, candidate, prompt, cfg: {
        "ran": True, "summary": "Rien à changer.", "operations": [], "warnings": [],
        "model": "fake-model", "verification_kind": "artistic", "limitations": "consultatif",
    })
    proposal = _ask({"message": "avis artistique", "project": project, "project_name": "citation"})["proposal"]
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], project)
    assert status == 200, body
    snapshot = _finished(body["job_id"])
    assert snapshot["status"] == "done", snapshot
    assert "proposal" not in snapshot["result"]
    assert snapshot["result"]["operations"] == []


@pytest.fixture()
def fake_llm_actions(monkeypatch):
    def install(*replies):
        sentences = [json.dumps(r, ensure_ascii=False) for r in replies]
        calls = {"index": 0}

        def fake_chat(messages, cfg=None, json_mode=True, cancel=None, **kwargs):
            position = min(calls["index"], len(sentences) - 1)
            calls["index"] += 1
            return FakeResult(sentences[position])

        monkeypatch.setattr(llm_client, "chat", fake_chat)
        monkeypatch.setattr(llm_client, "is_ready", lambda cfg=None: (True, ""))
        return calls

    return install