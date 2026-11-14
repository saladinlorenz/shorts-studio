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
from server import imagegen
from server.agent import actions, llm_client, proposals, review, service, tools
from server.app import app
from shortvideos import edl as edl_mod, schema

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
            "batch_start", "delivery_package", "moments_analyze", "settings_update",
            "image_generate", "montage_render"} <= names
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
    ("image_generate", {}),
    ("image_generate", {"prompt": ""}),
    ("image_generate", {"prompt": "ok", "width": 100}),
    ("image_generate", {"prompt": "ok", "height": 4000}),
    ("image_generate", {"prompt": "ok", "width": "1024"}),
    ("image_generate", {"prompt": "ok", "seed": -1}),
    ("image_generate", {"prompt": "ok", "chemin": "C:/evil"}),
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


# --------------------------------------------------------------------------- #
# image_generate : descriptif, impacts tiers, exécution sur clic dédié
# --------------------------------------------------------------------------- #

def test_image_generate_describe_without_project(isolated_settings):
    settings_mod.save_settings({"llm_local_api_key": "cle-secrete-test"})
    descriptor = actions.describe("image_generate", {"prompt": "un coucher de soleil cinématique"}, None)
    assert descriptor["name"] == "image_generate"
    assert descriptor["params"] == {"prompt": "un coucher de soleil cinématique", "width": 1024, "height": 1024}
    # Aucune cible locale ne dérive : le contexte reste vide.
    assert descriptor["context"] == {}
    joined = " ".join(descriptor["impact"])
    assert "pollinations.ai" in joined and "sans clé" in joined
    assert "prompt texte" in joined and "tiers" in joined
    assert "Aucune écriture dans le projet" in joined
    assert "cle-secrete-test" not in json.dumps(descriptor, ensure_ascii=False)


def test_image_generate_full_flow(fake_llm, isolated_settings, monkeypatch):
    seen = {}

    def fake_generate(prompt, *, width=1024, height=1024, seed=None, cancel=None):
        seen.update(prompt=prompt, width=width, height=height, seed=seed)
        assert callable(cancel)
        return {"media_id": "img123", "ref": "media://img123", "url": "/api/media/img123",
                "width": width, "height": height, "summary": "Image générée et importée comme média local."}

    monkeypatch.setattr(imagegen, "generate_image", fake_generate)
    fake_llm(_action_reply("image_generate", {"prompt": "forêt brumeuse", "width": 1280, "height": 720, "seed": 7}))
    proposal = _ask({"message": "génère un fond", "project": None})["proposal"]
    assert proposal["type"] == "studio_action"
    assert proposal["action"]["name"] == "image_generate"
    confirmation = proposal["action"]["confirmation"]

    # /accept ne lance jamais l'action ; seule la confirmation dédiée le fait.
    accept = client.post(f"/api/agent/proposals/{proposal['id']}/accept", json={"project": None})
    assert accept.status_code == 424
    assert _execute(proposal["id"], "mauvaise-confirmation")[0] == 424
    assert seen == {}

    status, body = _execute(proposal["id"], confirmation)
    assert status == 200, body
    snapshot = _finished(body["job_id"])
    assert snapshot["status"] == "done", snapshot
    assert snapshot["result"]["ref"] == "media://img123"
    assert snapshot["result"]["media_id"] == "img123"
    assert seen == {"prompt": "forêt brumeuse", "width": 1280, "height": 720, "seed": 7}

    # Aucun double lancement, même avec la bonne confirmation.
    assert _execute(proposal["id"], confirmation)[0] == 424


# --------------------------------------------------------------------------- #
# montage_render : EDL validé, rendu FFmpeg réel après confirmation
# --------------------------------------------------------------------------- #

@pytest.fixture()
def montage_studio(tmp_path, monkeypatch):
    from server import media as media_mod, security
    from server.api import montage as montage_api

    media = tmp_path / "media"
    exports = tmp_path / "exports"
    (media / "provenance").mkdir(parents=True)
    exports.mkdir()
    for name in ("a.mp4", "b.mp4", "music.m4a"):
        (media / name).write_bytes(b"factice")
    monkeypatch.setattr(media_mod, "MEDIA_DIR", media)
    monkeypatch.setattr(media_mod, "PROVENANCE_DIR", media / "provenance")
    monkeypatch.setattr(security, "EXPORTS_DIR", exports)
    monkeypatch.setattr(montage_api, "EXPORTS_DIR", exports)
    return {"media": media, "exports": exports}


def _edl_draft() -> dict:
    return {
        "version": 1,
        "canvas": {"width": 160, "height": 90, "fps": 15},
        "cuts": [
            {"media": "media://a", "in": 0.1, "out": 1.4, "role": "hook", "reason": "ouverture"},
            {"media": "media://b", "in": 0.1, "out": 1.5, "role": "end", "reason": "chute",
             "transition": {"type": "fade", "duration": 0.3}},
        ],
        "audio": {"music": "media://music", "gain_db": -20, "duck": True,
                  "fade_in": 0.2, "fade_out": 0.3},
        "grade": {"look": "warm", "saturation": 1.1, "contrast": 1.05},
    }


def test_montage_render_describe_freezes_valid_edl(montage_studio):
    descriptor = actions.describe("montage_render", {"edl": _edl_draft(), "name": "doc"}, None)
    assert descriptor["name"] == "montage_render"
    # L'EDL stocké est la version normalisée : le plan ne peut plus dériver.
    assert descriptor["params"]["edl"]["cuts"][0]["transition"] == {"type": "cut", "duration": 0.0}
    assert descriptor["context"]["duration_seconds"] == pytest.approx(2.4)
    assert descriptor["context"]["edl"] == actions._fingerprint(descriptor["params"]["edl"])
    assert {m["ref"] for m in descriptor["context"]["media"]} == {"media://a", "media://b", "media://music"}
    joined = " ".join(descriptor["impact"])
    assert "FFmpeg" in joined and "2 plans" in joined
    assert "aucun téléchargement" in joined


def test_montage_render_refuses_invalid_edl(montage_studio):
    bad = _edl_draft()
    bad["cuts"][0]["role"] = "intro"
    with pytest.raises(actions.ActionError, match="EDL invalide"):
        actions.describe("montage_render", {"edl": bad, "name": "doc"}, None)
    with pytest.raises(actions.ActionError, match="EDL invalide"):
        actions.describe("montage_render", {"edl": {"version": 1, "cuts": []}, "name": "doc"}, None)


def test_montage_render_refuses_name_collision(montage_studio):
    (montage_studio["exports"] / "doc.mp4").write_bytes(b"deja")
    with pytest.raises(actions.ActionError, match="écrasement"):
        actions.describe("montage_render", {"edl": _edl_draft(), "name": "doc"}, None)


def test_montage_render_media_drift_is_refused(fake_llm, isolated_settings, montage_studio):
    fake_llm(_action_reply("montage_render", {"edl": _edl_draft(), "name": "doc"}))
    proposal = _ask({"message": "monte ces rushes", "project": None})["proposal"]
    assert proposal["type"] == "studio_action"
    # Le rush change entre la proposition et le clic : aucune exécution sur une cible périmée.
    (montage_studio["media"] / "a.mp4").write_bytes(b"contenu modifie apres coup")
    status, body = _execute(proposal["id"], proposal["action"]["confirmation"])
    assert status == 424
    assert "changé depuis la confirmation" in json.dumps(body, ensure_ascii=False)


def test_montage_render_full_flow(fake_llm, isolated_settings, montage_studio):
    import subprocess

    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    media = montage_studio["media"]

    def rush(name: str, source: str, seconds: float, audio: bool) -> None:
        args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"{source}=size=160x90:rate=30:duration={seconds}"]
        if audio:
            args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
                     "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k"]
        args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                 "-t", str(seconds), str(media / name)]
        subprocess.run(args, check=True)

    rush("a.mp4", "testsrc2", 2.2, audio=True)
    rush("b.mp4", "smptebars", 2.0, audio=False)
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=1.2",
                    "-c:a", "aac", "-b:a", "128k", str(media / "music.m4a")], check=True)

    fake_llm(_action_reply("montage_render", {"edl": _edl_draft(), "name": "doc-montage"}))
    proposal = _ask({"message": "monte ces rushes en documentaire", "project": None})["proposal"]
    assert proposal["type"] == "studio_action"
    assert proposal["action"]["name"] == "montage_render"
    confirmation = proposal["action"]["confirmation"]

    accept = client.post(f"/api/agent/proposals/{proposal['id']}/accept", json={"project": None})
    assert accept.status_code == 424
    assert _execute(proposal["id"], "mauvaise-confirmation")[0] == 424

    status, body = _execute(proposal["id"], confirmation)
    assert status == 200, body
    snapshot = _finished(body["job_id"], timeout=120.0)
    assert snapshot["status"] == "done", snapshot
    result = snapshot["result"]
    assert result["path"] == "doc-montage.mp4"
    assert result["cuts"] == 2
    assert result["duration"] == pytest.approx(2.4, abs=0.15)
    assert result["has_audio"] is True
    out_file = montage_studio["exports"] / "doc-montage.mp4"
    assert out_file.is_file() and out_file.stat().st_size == result["size_bytes"]

    assert _execute(proposal["id"], confirmation)[0] == 424


def test_validate_montage_tool_contract_and_indexed_errors(montage_studio):
    out = tools.execute("validate_montage", {"edl": _edl_draft()}, {})
    assert out["valid"] is True, out["errors"]
    assert out["cuts"] == 2
    assert out["duration_seconds"] == pytest.approx(2.4)
    assert out["contract"]["cut"]["role"] == list(edl_mod.ROLES)
    assert out["contract"]["cut"]["transition"]["type"] == list(edl_mod.TRANSITIONS)
    assert "edl" not in out  # pas d'écho du plan : le modèle a déjà son brouillon

    bad = _edl_draft()
    bad["cuts"][1]["out"] = 0.05
    out = tools.execute("validate_montage", {"edl": bad}, {})
    assert out["valid"] is False
    assert any("cuts[1]" in error for error in out["errors"])

    with pytest.raises(tools.ToolError, match="edl"):
        tools.execute("validate_montage", {}, {})