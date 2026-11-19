"""L'assistant grand maître : banques de contenu et packs marque branchés.

Lois verrouillées ici :

- les clés des banques ne sortent jamais du serveur, même via l'assistant :
  l'outil get_sources_state ne montre que des booléens et des indices ;
- aucune clé ne se saisit dans le chat : un test sans clé enregistrée renvoie
  l'utilisateur vers la page Banques ;
- test et activation passent par le contrat studio_action (confirmation,
  contexte figé, aucun double lancement) ;
- brand_apply ne propose que des opérations validées limitées à
  theme/signature/audio : scènes et calques intacts, application après clic ;
- brand_capture enregistre un pack réutilisable sans toucher au projet.

Aucun réseau : llm_client.chat et httpx.Client sont simulés ; tout le reste
(contrat, validation, jobs, stockage) est le code de production.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from server import brands as brands_mod
from server import security
from server import settings as settings_mod
from server import sources as sources_mod
from server.agent import actions, capabilities, llm_client, proposals, tools
from server.app import app
from shortvideos import schema

client = TestClient(app)

KEY = "ABCD1234wxyz"
ACCENT = "#1F6FEB"


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
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    settings_mod.save_settings({"llm_context_budget": 20000, "llm_max_tokens": 8000})
    monkeypatch.setattr(sources_mod, "SOURCES_PATH", tmp_path / "sources.json")
    monkeypatch.setattr(brands_mod, "BRANDS_DIR", tmp_path / "brands")
    monkeypatch.setattr(security, "ALLOWED_DIRS", (*security.ALLOWED_DIRS, tmp_path))
    (tmp_path / "brands").mkdir()
    return tmp_path


@pytest.fixture()
def fake_httpx(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"photos": [{"alt": "Forêt dans la brume"}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None, headers=None):
            return Response()

    monkeypatch.setattr(sources_mod.httpx, "Client", Client)


def _project() -> dict:
    return schema.new_project("quote_cinematic")


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


def _brand(label: str = "Client Test") -> dict:
    return brands_mod.save_brand({
        "label": label,
        "theme": {"accent_color": ACCENT},
        "signature": {"handle": "@client.test"},
    })["brand"]


# --------------------------------------------------------------------------- #
# Catalogue et outils de lecture
# --------------------------------------------------------------------------- #

def test_catalog_covers_sources_and_brands(isolated):
    names = {a["name"] for a in actions.catalog()["actions"]}
    assert {"sources_test", "sources_toggle", "brand_apply", "brand_capture"} <= names
    for name in ("sources_test", "sources_toggle", "brand_apply", "brand_capture"):
        spec = actions.catalog(name)["actions"][0]
        assert spec["parameters"]["additionalProperties"] is False


def test_strict_params_rejected(isolated):
    with pytest.raises(actions.ActionError):
        actions.describe("sources_test", {"source_id": "pexels", "url": "http://autre.example"}, None)
    with pytest.raises(actions.ActionError):
        actions.describe("sources_toggle", {"source_id": "pexels"}, None)


def test_get_sources_state_never_leaks_keys(isolated):
    sources_mod.save("pexels", key=KEY)
    out = tools.execute("get_sources_state", {}, {})
    dumped = json.dumps(out, ensure_ascii=False)
    assert KEY not in dumped
    pexels = next(p for p in out["providers"] if p["id"] == "pexels")
    assert pexels["key_configured"] is True
    assert pexels["key_hint"] == "••••wxyz"
    assert "page Banques" in out["note"]
    assert out["configured"] == 1


def test_brand_read_tools(isolated):
    brand = _brand()
    listing = tools.execute("list_brands", {}, {})
    assert [b["id"] for b in listing["brands"]] == [brand["id"]]
    pack = tools.execute("get_brand", {"id": brand["id"]}, {})["pack"]
    assert pack["theme"]["accent_color"] == ACCENT
    with pytest.raises(tools.ToolError):
        tools.execute("get_brand", {"id": "fantome"}, {})
    with pytest.raises(tools.ToolError):
        tools.execute("get_brand", {}, {})


def test_capabilities_manifest_mentions_both_domains(isolated):
    sources_mod.save("nasa", key=KEY)
    _brand()
    manifest = capabilities.build()
    assert manifest["content_sources"]["configured"] == 1
    assert manifest["brands"][0]["label"] == "Client Test"
    text = capabilities.prompt_block(manifest, max_chars=20000)
    assert "Banques de contenu" in text
    assert "Packs marque" in text
    assert "jamais dans le chat" in text


# --------------------------------------------------------------------------- #
# Banques : description, test et activation confirmés
# --------------------------------------------------------------------------- #

def test_sources_test_without_key_sends_user_to_page(isolated):
    with pytest.raises(actions.ActionError) as exc:
        actions.describe("sources_test", {"source_id": "pexels"}, None)
    assert "page Banques" in str(exc.value)


def test_sources_test_describe_freezes_public_state(isolated):
    sources_mod.save("pexels", key=KEY)
    described = actions.describe("sources_test", {"source_id": "pexels"}, None)
    assert described["context"]["source"] == {"key_configured": True, "enabled": True}
    assert any("ni affichée ni envoyée au modèle" in line for line in described["impact"])
    assert KEY not in json.dumps(described, ensure_ascii=False)


def test_sources_test_full_flow(isolated, fake_llm, fake_httpx):
    sources_mod.save("pexels", key=KEY)
    fake_llm(_action_reply("sources_test", {"source_id": "pexels"}))
    proposal = _ask({"message": "teste pexels", "project": None})["proposal"]
    assert proposal["validation"]["state"] == "valid"
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"])
    assert status == 200, body
    snapshot = _finished(body["job_id"])
    assert snapshot["status"] == "done", snapshot
    result = snapshot["result"]
    assert result["ok"] is True
    assert result["sample"] == "Forêt dans la brume"
    assert result["summary"] == result["message"]
    assert KEY not in json.dumps(result, ensure_ascii=False)


def test_sources_toggle_full_flow(isolated, fake_llm):
    sources_mod.save("nasa", key=KEY)
    fake_llm(_action_reply("sources_toggle", {"source_id": "nasa", "enabled": False}))
    proposal = _ask({"message": "mets nasa en pause", "project": None})["proposal"]
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"])
    assert status == 200, body
    result = _finished(body["job_id"])["result"]
    assert result["provider"]["enabled"] is False
    assert result["provider"]["ready"] is False
    assert sources_mod.state_of("nasa")["enabled"] is False
    assert sources_mod.state_of("nasa")["key_configured"] is True


def test_sources_toggle_conflict_if_page_changed(isolated, fake_llm):
    sources_mod.save("nasa", key=KEY)
    fake_llm(_action_reply("sources_toggle", {"source_id": "nasa", "enabled": False}))
    proposal = _ask({"message": "mets nasa en pause", "project": None})["proposal"]
    sources_mod.save("nasa", enabled=False)
    status, _ = _execute(proposal["id"], proposal["action"]["confirmation"])
    assert status == 424


# --------------------------------------------------------------------------- #
# Marques : application proposée, capture enregistrée
# --------------------------------------------------------------------------- #

def test_brand_apply_requires_project(isolated):
    _brand()
    with pytest.raises(actions.ActionError):
        actions.describe("brand_apply", {"brand_id": "client-test"}, None)


def test_brand_apply_noop_pack_refused(isolated):
    project = _project()
    brands_mod.save_brand({
        "label": "Miroir",
        "theme": {"accent_color": project["theme"]["accent_color"]},
    })
    with pytest.raises(actions.ActionError) as exc:
        actions.describe("brand_apply", {"brand_id": "miroir"}, project)
    assert "ne change rien" in str(exc.value)


def test_brand_apply_full_flow_proposes_validated_ops(isolated, fake_llm):
    project = _project()
    brand = _brand()
    fake_llm(_action_reply("brand_apply", {"brand_id": brand["id"]}))
    proposal = _ask({"message": "applique la marque client", "project": project, "project_name": "citation"})["proposal"]
    assert proposal["validation"]["state"] == "valid"
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], project)
    assert status == 200, body
    result = _finished(body["job_id"])["result"]
    followup = result["proposal"]
    assert followup["type"] == "project_patch"
    assert followup["validation"]["state"] == "valid"
    operations = followup["changes"]
    assert {op["op"] for op in operations} <= {"set_theme", "set_signature", "set_audio"}
    assert followup["has_candidate"] is True
    applied = brands_mod.apply_to_project(brand["id"], project)
    ops = actions._brand_operations(project, applied["project"], brands_mod.get_pack(brand["id"]))
    candidate, _, errors = proposals.apply_operations(project, ops)
    assert not errors
    assert candidate["theme"]["accent_color"] == ACCENT
    assert candidate["content"]["signature"]["handle"] == "@client.test"
    assert candidate["content"]["scenes"] == project["content"]["scenes"]
    assert KEY not in json.dumps(result, ensure_ascii=False)


def test_brand_apply_revision_conflict_is_409(isolated, fake_llm):
    project = _project()
    brand = _brand()
    fake_llm(_action_reply("brand_apply", {"brand_id": brand["id"]}))
    proposal = _ask({"message": "applique la marque", "project": project, "project_name": "citation"})["proposal"]
    changed = _project()
    changed["content"]["scenes"][0]["layers"][0]["text"] = "autre accroche"
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], changed)
    assert status == 409
    assert body["detail"]["current_revision"] == proposals.revision_of(changed)


def test_brand_capture_full_flow(isolated, fake_llm):
    project = _project()
    fake_llm(_action_reply("brand_capture", {"label": "Style actuel", "notes": "capté pour le client"}))
    proposal = _ask({"message": "capture le style", "project": project, "project_name": "citation"})["proposal"]
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"], project)
    assert status == 200, body
    result = _finished(body["job_id"])["result"]
    assert result["brand"]["label"] == "Style actuel"
    stored = brands_mod.get_pack(result["brand"]["id"])
    assert stored["theme"]["accent_color"] == project["theme"]["accent_color"]
    assert len(brands_mod.list_brands()) == 1