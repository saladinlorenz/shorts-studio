"""Actions confirmées du studio : le contrat studio_action de bout en bout.

Lois verrouillées ici :

- le catalogue est borné, sans secret, et chaque action a un schéma strict ;
- une URL de téléchargement est une vidéo YouTube HTTPS précise, rien d'autre ;
- la proposition porte une confirmation serveur, des impacts et un contexte ;
- /accept ne lance jamais une action : seul /execute, avec la bonne confirmation ;
- aucun double lancement, aucun refus après lancement, aucune dérive de cible ;
- l'exécution ne consomme que les paramètres enregistrés par le serveur ;
- settings_update ne touche que des réglages non secrets, jamais une clé.

Aucun réseau : ``llm_client.chat`` est simulé, les exécutions sensibles le sont
aussi ; tout le reste (contrat, validation, confirmation, jobs) est le code de
production.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from server import settings as settings_mod
from server.agent import actions, llm_client, proposals, review, service
from server.app import app
from shortvideos import schema

client = TestClient(app)


class FakeResult:
    def __init__(self, text: str):
        self.text = text
        self.latency_ms = 12
        self.model = "fake-model"


@pytest.fixture()
def fake_llm(monkeypatch):
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


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    # Budget de contexte suffisant pour le mode design (projet + outils), comme
    # la configuration réelle du studio ; les défauts nus (3000) sont trop courts.
    settings_mod.save_settings({"llm_context_budget": 20000, "llm_max_tokens": 8000})
    return tmp_path / "settings.json"


def _project() -> dict:
    return schema.new_project("quote_cinematic")


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


def _action_reply(name: str, params: dict) -> dict:
    return {"type": "studio_action", "summary": "Action proposée.", "action": {"name": name, "params": params}}


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


# --------------------------------------------------------------------------- #
# Catalogue et schémas stricts
# --------------------------------------------------------------------------- #

def test_catalog_lists_actions_without_secret():
    data = actions.catalog()
    names = {item["name"] for item in data["actions"]}
    assert {"project_review", "project_export", "clips_download", "tts_generate",
            "batch_start", "delivery_package", "moments_analyze", "settings_update"} <= names
    assert "shell" not in names and "media_analyze" not in names
    assert "api_key" not in json.dumps(data)
    detail = actions.catalog("project_export")
    assert detail["actions"][0]["parameters"]["properties"]["name"]
    with pytest.raises(actions.ActionError):
        actions.catalog("action_fantome")


@pytest.mark.parametrize("name,params", [
    ("action_fantome", {}),
    ("project_export", {"name": "ok", "chemin": "C:/evil"}),
    ("project_export", {"name": "../evil"}),
    ("clips_analyze", {"sid": "s1", "num_clips": 0}),
    ("clips_analyze", {"sid": "s1", "num_clips": 21}),
    ("clips_extract", {"sid": "s1", "clip_indexes": []}),
    ("tts_generate", {"voice_id": "fr_siwis", "text": "bonjour", "speed": 3.0}),
    ("settings_update", {"max_tokens": 9000}),
    ("settings_update", {"api_key": "vole-moi"}),
    ("settings_update", {"provider": "gemini"}),
    ("settings_update", {}),
    ("moments_analyze", {"source": "../../secret.wav"}),
])
def test_invalid_params_are_refused(name, params):
    with pytest.raises(actions.ActionError):
        actions.describe(name, params, _project())


def test_strict_types_refuse_string_numbers():
    with pytest.raises(actions.ActionError):
        actions.describe("clips_analyze", {"sid": "s1", "num_clips": "5"}, None)


# --------------------------------------------------------------------------- #
# URLs YouTube : liste blanche, vidéo précise, canonicalisation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=30", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
])
def test_youtube_urls_canonicalized(url, expected):
    assert actions._youtube_url(url) == expected


@pytest.mark.parametrize("url", [
    "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://evil.example/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/playlist?list=PL123",
    "https://www.youtube.com/@chaine",
    "https://www.youtube.com/watch?v=court",
    "https://user:pass@www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com:444/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ#t=10",
    "file:///C:/secret.mp4",
])
def test_unsafe_urls_are_refused(url):
    with pytest.raises(actions.ActionError):
        actions._youtube_url(url)


def test_clips_download_normalizes_url_in_params():
    descriptor = actions.describe("clips_download", {"url": "https://youtu.be/dQw4w9WgXcQ"}, None)
    assert descriptor["params"]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert any("YouTube" in line for line in descriptor["impact"])


# --------------------------------------------------------------------------- #
# Contexte serveur : révision, destination sans clé, collision d'export
# --------------------------------------------------------------------------- #

def test_project_review_requires_valid_project():
    with pytest.raises(actions.ActionError):
        actions.describe("project_review", {}, None)
    broken = _project()
    broken["content"]["scenes"][0]["layers"][0]["style"]["font_size"] = 99999
    with pytest.raises(actions.ActionError):
        actions.describe("project_review", {}, broken)


def test_project_review_context_has_revision_and_text_only_destination(isolated_settings):
    settings_mod.save_settings({"llm_local_api_key": "cle-secrete-test"})
    project = _project()
    descriptor = actions.describe("project_review", {}, project)
    assert descriptor["context"]["project_revision"] == proposals.revision_of(project)
    assert set(descriptor["context"]["destination"]) == {"provider", "model", "base_url"}
    serialized = json.dumps(descriptor, ensure_ascii=False)
    assert "cle-secrete-test" not in serialized
    assert any("Aucun envoi d’image" in line for line in descriptor["impact"])


def test_project_export_refuses_name_collision(tmp_path, monkeypatch):
    from server import security
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "deja.mp4").write_bytes(b"existant")
    monkeypatch.setattr(security, "EXPORTS_DIR", exports)
    with pytest.raises(actions.ActionError, match="écrasement"):
        actions.describe("project_export", {"name": "deja"}, _project())
    descriptor = actions.describe("project_export", {"name": "nouveau"}, _project())
    assert descriptor["params"]["name"] == "nouveau"


def test_settings_update_snapshots_before_values(isolated_settings):
    descriptor = actions.describe("settings_update", {"temperature": 0.7}, None)
    assert descriptor["context"]["before"] == {"temperature": 0.4}
    assert any("Ni clé" in line for line in descriptor["impact"])


# --------------------------------------------------------------------------- #
# Contrat de proposition : action={name,params} exclusivement
# --------------------------------------------------------------------------- #

def test_from_reply_refuses_extra_action_fields():
    reply = _action_reply("settings_update", {"temperature": 0.5})
    reply["action"]["confirmation"] = "injectee"
    with pytest.raises(proposals.ProposalError):
        proposals.from_reply(reply, None, "")


def test_from_reply_refuses_unknown_action():
    with pytest.raises(proposals.ProposalError):
        proposals.from_reply(_action_reply("shell", {"cmd": "dir"}), None, "")


def test_from_reply_builds_server_confirmation(isolated_settings):
    proposal = proposals.from_reply(_action_reply("settings_update", {"temperature": 0.5}), None, "")
    action = proposal["action"]
    assert proposal["type"] == "studio_action"
    assert proposal["validation"]["state"] == "valid"
    assert len(action["confirmation"]) == 32
    assert action["params"] == {"temperature": 0.5}
    assert action["context"]["before"] == {"temperature": 0.4}
    view = proposals.public_view(proposal)
    assert view["action"]["confirmation"] == action["confirmation"]


# --------------------------------------------------------------------------- #
# Parcours HTTP complet : proposition → confirmation → exécution unique
# --------------------------------------------------------------------------- #

def test_settings_update_full_flow(fake_llm, isolated_settings):
    fake_llm(_action_reply("settings_update", {"temperature": 0.7}))
    proposal = _ask({"message": "baisse la température", "project": None})["proposal"]
    assert proposal["type"] == "studio_action"
    confirmation = proposal["action"]["confirmation"]

    accept = client.post(f"/api/agent/proposals/{proposal['id']}/accept", json={"project": None})
    assert accept.status_code == 424

    wrong = _execute(proposal["id"], "mauvaise-confirmation")
    assert wrong[0] == 424

    extra = client.post(f"/api/agent/proposals/{proposal['id']}/execute",
                        json={"confirmation": confirmation, "params": {"temperature": 2.0}})
    assert extra.status_code == 422

    status, body = _execute(proposal["id"], confirmation)
    assert status == 200, body
    snapshot = _finished(body["job_id"])
    assert snapshot["status"] == "done", snapshot
    assert snapshot["result"]["values"] == {"temperature": 0.7}
    assert settings_mod.llm_config()["temperature"] == 0.7

    again = _execute(proposal["id"], confirmation)
    assert again[0] == 424
    refuse = client.post(f"/api/agent/proposals/{proposal['id']}/reject")
    assert refuse.status_code == 424


def test_execute_unknown_proposal_is_404(fake_llm, isolated_settings):
    status, _ = _execute("inexistante", "x")
    assert status == 404


def test_settings_drift_between_proposal_and_execute_is_refused(fake_llm, isolated_settings):
    fake_llm(_action_reply("settings_update", {"temperature": 0.7}))
    proposal = _ask({"message": "règle", "project": None})["proposal"]
    settings_mod.save_settings({"llm_temperature": 0.1})
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"])
    assert status == 424
    assert "changé" in json.dumps(body, ensure_ascii=False)
    assert settings_mod.llm_config()["temperature"] == 0.1


def test_project_review_revision_conflict_is_409(fake_llm, isolated_settings):
    project = _project()
    fake_llm(_action_reply("project_review", {"prompt": "vérifie la lisibilité"}))
    proposal = _ask({"message": "audite", "project": project, "project_name": "citation"})["proposal"]
    changed = _project()
    changed["content"]["scenes"][0]["layers"][0]["text"] = "autre accroche"
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], changed)
    assert status == 409
    assert body["detail"]["current_revision"] == proposals.revision_of(changed)


def test_project_review_execute_produces_acceptable_correction(fake_llm, isolated_settings, monkeypatch):
    project = _project()
    fake_llm(_action_reply("project_review", {"prompt": "vérifie"}))
    seen = {}

    def fake_review(job, candidate, prompt, cfg):
        seen["project"] = candidate
        seen["prompt"] = prompt
        return {
            "summary": "Contrôle technique terminé ; aperçus à vérifier par une personne.",
            "verified": True, "verification_kind": "technical", "rounds": [],
            "frames": [], "measurements": [], "defects": [], "error": "",
            "operations": [{"op": "set_layer", "scene_id": "s2", "layer_id": "quote",
                            "path": "style.color", "value": "#2aa8c9"}],
            "limitations": "LLM texte sans vision.",
        }

    monkeypatch.setattr(review, "review_project", fake_review)
    proposal = _ask({"message": "audite", "project": project, "project_name": "citation"})["proposal"]
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], project)
    assert status == 200, body
    snapshot = _finished(body["job_id"])
    assert snapshot["status"] == "done", snapshot
    assert seen["prompt"] == "vérifie"
    assert seen["project"]["content"]["scenes"][0]["layers"][0]["text"] == project["content"]["scenes"][0]["layers"][0]["text"]
    correction = snapshot["result"]["proposal"]
    assert correction["type"] == "project_patch"
    assert correction["validation"]["state"] == "valid"

    accept = client.post(f"/api/agent/proposals/{correction['id']}/accept", json={"project": project})
    assert accept.status_code == 200, accept.text
    applied = accept.json()
    assert applied["kind"] == "project"
    quote = applied["project"]["content"]["scenes"][1]["layers"][0]
    assert quote["style"]["color"] == "#2aa8c9"


def test_reject_before_execute_then_execute_is_refused(fake_llm, isolated_settings):
    fake_llm(_action_reply("settings_update", {"temperature": 0.7}))
    proposal = _ask({"message": "règle", "project": None})["proposal"]
    refuse = client.post(f"/api/agent/proposals/{proposal['id']}/reject")
    assert refuse.status_code == 200
    status, _ = _execute(proposal["id"], proposal["action"]["confirmation"])
    assert status == 424