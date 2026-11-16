"""Incrément 2 — mémoire adaptative au fournisseur.

Le bug « l'assistant oublie l'effet déjà choisi » venait d'un budget de contexte
figé à 3000 tokens : sur un fournisseur cloud à grande fenêtre, l'historique et
les documents sautaient. Le cloud garantit désormais un plancher généreux ; le
local conserve le budget serré. Tests mock : aucun réseau, aucun rendu.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import settings  # noqa: E402
from server.agent import context, llm_client  # noqa: E402
from server.app import app  # noqa: E402
from shortvideos import schema  # noqa: E402


# --------------------------------------------------------------------------- #
# Budget effectif : plancher cloud, local conservé
# --------------------------------------------------------------------------- #
def test_local_budget_unchanged():
    assert settings.effective_context_budget({"provider": "local"}, 3000) == 3000
    assert settings.effective_context_budget({"provider": "local"}, 1500) == 1500


@pytest.mark.parametrize("provider", ["gemini", "groq"])
def test_cloud_budget_floor_applied(provider):
    assert settings.effective_context_budget({"provider": provider}, 3000) == settings.CLOUD_CONTEXT_FLOOR


def test_cloud_higher_setting_honored():
    high = settings.CLOUD_CONTEXT_FLOOR + 5000
    assert settings.effective_context_budget({"provider": "gemini"}, high) == high


# --------------------------------------------------------------------------- #
# Conséquence : l'historique survit au cloud, pas au budget local serré
# --------------------------------------------------------------------------- #
def test_history_survives_cloud_budget_but_local_overflows():
    history = [
        {"role": "user", "content": "ajoute un effet glitch_slices"},
        {"role": "assistant", "content": "Effet glitch_slices ajouté au calque hook."},
    ]
    passages = [{"source": "t", "path": "p", "title": "t", "version": "1", "text": "doc " * 300}]
    # Section obligatoire volumineuse : essential > 9000 caractères, déterministe.
    common = dict(
        request="applique l'effet à toute la vidéo", capabilities_text="CAPACITÉS",
        project=None, history=history, passages=passages, required_text="RÈGLE " * 2000,
    )
    cloud_budget = settings.effective_context_budget({"provider": "gemini"}, 3000)
    messages, meta = context.build(budget_tokens=cloud_budget, **common)
    assert "historique" not in meta["dropped"]
    assert "ÉCHANGES PRÉCÉDENTS" in messages[-1]["content"]
    assert "glitch_slices" in messages[-1]["content"]

    with pytest.raises(context.ContextTooLarge):
        context.build(budget_tokens=3000, **common)


# --------------------------------------------------------------------------- #
# Câblage service : une demande cloud conserve l'historique jusqu'au modèle
# --------------------------------------------------------------------------- #
def test_service_keeps_history_on_cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    settings.save_settings({
        "llm_provider": "gemini", "llm_context_budget": 3000,
        "llm_gemini_api_key": "cle-de-test", "llm_gemini_model": "modele-test",
    })
    captured = {}

    class Reply:
        text = '{"type":"question","summary":"Précision.","questions":["Quel sujet ?"]}'
        latency_ms = 1
        model = "modele-test"

    def fake_chat(messages, cfg=None, **kwargs):
        captured["messages"] = list(messages)
        return Reply()

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    monkeypatch.setattr(llm_client, "is_ready", lambda cfg=None: (True, ""))
    client = TestClient(app)
    history = [
        {"role": "user", "content": "ajoute un effet glitch_slices"},
        {"role": "assistant", "content": "Effet glitch_slices ajouté au calque hook."},
    ]
    response = client.post("/api/agent/ask", json={
        "message": "applique l'effet à toute la vidéo",
        "project": schema.new_project("quote_cinematic"),
        "history": history,
    })
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(200):
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] != "running":
            break
        time.sleep(0.05)
    assert snapshot["status"] == "done", snapshot
    user_content = captured["messages"][-1]["content"]
    assert "ÉCHANGES PRÉCÉDENTS" in user_content
    assert "glitch_slices" in user_content