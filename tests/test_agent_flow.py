"""
Chat complet de l'assistant : demande → job → proposition → acceptation.

Ces tests verrouillent le contrat que consomme le tiroir d'assistant — les trois
sorties d'une acceptation (projet à appliquer, projet à enregistrer en
bibliothèque, plan de lot à reprendre dans le formulaire) — avec un serveur LLM
simulé. Aucun réseau : seule ``llm_client.chat`` est remplacée, tout le reste
(capacités, contrat JSON, validation métier, contrôle de révision) est le code
de production.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from server import library as library_mod
from server.agent import llm_client
from server.app import app
from shortvideos import batch as batch_mod
from shortvideos import schema

client = TestClient(app)

BLEU_PETROLE = "#2aa8c9"


class FakeResult:
    """Ce que ``llm_client.chat`` retourne : le texte brut du modèle."""

    def __init__(self, text: str):
        self.text = text
        self.latency_ms = 12
        self.model = "fake-model"


@pytest.fixture()
def fake_llm(monkeypatch):
    """Un modèle qui répond exactement ce qu'on lui demande, réponse par réponse."""

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


def _project() -> dict:
    return schema.new_project("quote_cinematic")


def _layer_of(project: dict, scene_id: str, layer_id: str) -> dict:
    for scene in project["content"]["scenes"]:
        if scene["id"] == scene_id:
            for layer in scene["layers"]:
                if layer["id"] == layer_id:
                    return layer
    raise AssertionError(f"{scene_id}/{layer_id} absent du projet")


def _ask_job(payload: dict) -> dict:
    """La demande passe par les vraies routes : POST /ask puis polling du job."""
    response = client.post("/api/agent/ask", json=payload)
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(200):
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] != "running":
            break
        time.sleep(0.05)
    assert snapshot is not None, job_id
    return snapshot


def _ask(payload: dict) -> dict:
    snapshot = _ask_job(payload)
    assert snapshot["status"] == "done", snapshot
    return snapshot["result"]


def _accept(proposal_id: str, project, rebase: bool = False) -> tuple[int, dict]:
    response = client.post(
        f"/api/agent/proposals/{proposal_id}/accept",
        json={"project": project, "rebase": rebase},
    )
    return response.status_code, response.json()


def test_color_patch_is_proposed_then_applied_on_accept(fake_llm):
    project = _project()
    fake_llm(
        {
            "type": "project_patch",
            "summary": "Accent bleu pétrole sur la citation.",
            "operations": [
                {
                    "op": "set_layer",
                    "scene_id": "s2",
                    "layer_id": "quote",
                    "path": "style.color",
                    "value": BLEU_PETROLE,
                }
            ],
        }
    )

    proposal = _ask({"message": "mets l'accent en bleu pétrole", "project": project, "project_name": "citation"})["proposal"]
    assert proposal["type"] == "project_patch"
    assert proposal["summary"], "le tiroir affiche ce résumé"
    assert proposal["validation"]["state"] == "valid", proposal["validation"]
    assert [c["target"] for c in proposal["changes"]] == ["s2/quote.style.color"]

    status, result = _accept(proposal["id"], project)
    assert status == 200, result
    # Contrat du frontend : kind "project" + un projet complet à passer à l'éditeur.
    assert result["kind"] == "project"
    assert result["project"]["version"] == schema.SCHEMA_VERSION_V2
    assert _layer_of(result["project"], "s2", "quote")["style"]["color"] == BLEU_PETROLE
    # Le texte du calque n'a pas bougé : une opération ne réécrit pas le projet.
    assert _layer_of(result["project"], "s2", "quote")["text"] == _layer_of(project, "s2", "quote")["text"]


def test_proposal_never_modifies_the_project_before_accept(fake_llm):
    project = _project()
    fake_llm(
        {
            "type": "project_patch",
            "summary": "Deux effets sur la citation.",
            "operations": [
                {
                    "op": "set_effects",
                    "scene_id": "s2",
                    "layer_id": "quote",
                    "effects": ["kinetic_letters", "spring_pop"],
                }
            ],
        }
    )
    proposal = _ask({"message": "ajoute kinetic_letters et spring_pop", "project": project, "project_name": "citation"})["proposal"]
    assert proposal["validation"]["state"] == "valid", proposal["validation"]
    assert _layer_of(project, "s2", "quote").get("effects", []) == [], "le projet affiché reste intact"

    # La route de lecture seule ne postule rien : l'aperçu est demandé, rien n'est écrit.
    view = client.get(f"/api/agent/proposals/{proposal['id']}?preview=true").json()["proposal"]
    assert _layer_of(view["candidate"], "s2", "quote")["effects"] == ["kinetic_letters", "spring_pop"]
    assert _layer_of(project, "s2", "quote").get("effects", []) == [], "l'aperçu seul ne postule rien"


def test_invented_effect_is_refused_with_a_repairable_message(fake_llm):
    project = _project()
    fake_llm(
        {
            "type": "project_patch",
            "summary": "Un effet qui n'existe pas.",
            "operations": [
                {
                    "op": "set_effects",
                    "scene_id": "s2",
                    "layer_id": "quote",
                    "effects": ["shatter"],
                }
            ],
        }
    )
    snapshot = _ask_job({"message": "ajoute shatter", "project": project, "project_name": "citation"})
    assert snapshot["status"] == "error", snapshot
    # Le nom vient de la documentation Remotion vue par l'utilisateur : le studio
    # le refuse et renvoie la liste réelle au lieu de le deviner.
    assert "shatter" in snapshot["error"]
    assert "set_effects" in snapshot["error"] or "operations" in snapshot["error"]


def test_a_change_during_generation_conflicts_and_rebase_replays_it(fake_llm):
    project = _project()
    fake_llm(
        {
            "type": "project_patch",
            "summary": "Accent bleu pétrole.",
            "operations": [
                {
                    "op": "set_layer",
                    "scene_id": "s2",
                    "layer_id": "quote",
                    "path": "style.color",
                    "value": BLEU_PETROLE,
                }
            ],
        }
    )
    proposal_id = _ask({"message": "accent", "project": project, "project_name": "citation"})["proposal"]["id"]

    changed = json.loads(json.dumps(project))
    _layer_of(changed, "s2", "quote")["text"] = "texte ajouté pendant la génération"

    status, result = _accept(proposal_id, changed)
    assert status == 409, result
    assert result["detail"]["rebase_available"] is True

    status, result = _accept(proposal_id, changed, rebase=True)
    assert status == 200, result
    assert result["rebuilt"] is True
    assert _layer_of(result["project"], "s2", "quote")["style"]["color"] == BLEU_PETROLE
    assert _layer_of(result["project"], "s2", "quote")["text"] == "texte ajouté pendant la génération"


def test_library_save_returns_the_project_and_label_for_the_save_call(fake_llm):
    project = _project()
    fake_llm(
        {
            "type": "library_save",
            "summary": "Enregistrer ce projet comme modèle.",
            "label": "citation bleue",
            "description": "Accent bleu pétrole.",
        }
    )
    proposal = _ask({"message": "enregistre en modèle", "project": project, "project_name": "citation"})["proposal"]
    assert proposal["library"]["label"] == "citation bleue"

    status, result = _accept(proposal["id"], project)
    assert status == 200, result
    # La page Design appelle ensuite saveLibraryModel(project, label, description).
    assert result["kind"] == "library_save"
    assert result["project"]["version"] == schema.SCHEMA_VERSION_V2
    assert result["library"]["label"] == "citation bleue"


def test_batch_plan_is_returned_for_the_production_form(fake_llm):
    model_id = library_mod.list_library()[0]["id"]
    fields = sorted(f["key"] for f in batch_mod.fillable_fields(library_mod.get_project(model_id)))
    text_field = next(key for key in fields if key.endswith(".text"))

    fake_llm(
        {
            "type": "batch_plan",
            "summary": "Câbler la citation sur le texte de la scène 2.",
            "model": model_id,
            "mapping": {text_field: "Citation"},
            "options": {"background": "auto"},
            "notes": "Recalculez le plan avant de lancer.",
        }
    )
    proposal = _ask(
        {
            "message": "câble mon csv",
            "project": None,
            "project_name": "lot",
            "mode": "production",
            "csv_columns": ["Titre", "Citation"],
        }
    )["proposal"]
    assert proposal["type"] == "batch_plan"
    assert proposal["batch"]["fields"] == fields

    status, result = _accept(proposal["id"], None)
    assert status == 200, result
    assert result["kind"] == "batch_plan"
    assert result["batch"]["mapping"] == {text_field: "Citation"}
    assert result["batch"]["options"] == {"background": "auto"}


def test_batch_plan_refuses_a_column_absent_from_the_csv(fake_llm):
    model_id = library_mod.list_library()[0]["id"]
    fields = sorted(f["key"] for f in batch_mod.fillable_fields(library_mod.get_project(model_id)))
    text_field = next(key for key in fields if key.endswith(".text"))

    fake_llm(
        {
            "type": "batch_plan",
            "summary": "Mapping vers une colonne inventée.",
            "model": model_id,
            "mapping": {text_field: "Colonne Fantôme"},
        }
    )
    snapshot = _ask_job(
        {
            "message": "câble mon csv",
            "project": None,
            "mode": "production",
            "csv_columns": ["Titre", "Citation"],
        }
    )
    assert snapshot["status"] == "error", snapshot
    assert "Colonne Fantôme" in snapshot["error"]


def test_question_proposal_has_nothing_to_apply(fake_llm):
    project = _project()
    fake_llm(
        {
            "type": "question",
            "summary": "Deux précisions manquent.",
            "questions": ["Quelle scène ?", "Quelle teinte ?"],
        }
    )
    proposal = _ask({"message": "change la couleur", "project": project, "project_name": "citation"})["proposal"]
    assert proposal["questions"] == ["Quelle scène ?", "Quelle teinte ?"]

    status, result = _accept(proposal["id"], project)
    assert status == 424, result


def test_a_malformed_reply_is_repaired_before_being_shown(fake_llm):
    project = _project()
    calls = fake_llm(
        {"type": "question"},
        {"type": "question", "summary": "Précision nécessaire.", "questions": ["Sur quel calque ?"]},
    )
    result = _ask({"message": "change la couleur", "project": project, "project_name": "citation"})
    assert calls["index"] == 2, "une réparation, puis la réponse conforme"
    assert result["meta"]["attempts"] == 1
    assert result["proposal"]["questions"] == ["Sur quel calque ?"]


def test_ask_is_refused_when_the_llm_server_is_not_configured(monkeypatch):
    monkeypatch.setattr(llm_client, "is_ready", lambda cfg=None: (False, "Assistant IA non configuré."))
    response = client.post("/api/agent/ask", json={"message": "test", "project": None})
    assert response.status_code == 424
    assert "non configur" in response.json()["detail"].lower()


def test_reject_leaves_the_project_untouched(fake_llm):
    project = _project()
    fake_llm(
        {
            "type": "project_patch",
            "summary": "Rien d'utile.",
            "operations": [
                {
                    "op": "set_layer",
                    "scene_id": "s2",
                    "layer_id": "quote",
                    "path": "style.color",
                    "value": BLEU_PETROLE,
                }
            ],
        }
    )
    proposal = _ask({"message": "accent", "project": project, "project_name": "citation"})["proposal"]
    assert client.post(f"/api/agent/proposals/{proposal['id']}/reject").status_code == 200
    refused = client.get(f"/api/agent/proposals/{proposal['id']}").json()["proposal"]
    assert refused["status"] == "rejected"
    # Refuser ne postule rien : le projet publié par l'éditeur n'a pas bougé.
    assert _layer_of(project, "s2", "quote")["style"].get("color") != BLEU_PETROLE
