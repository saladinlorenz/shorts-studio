"""Mode autopilote : plan → démarrage → étapes → vidéo, échec, annulation, reprise.

LLM, synthèse vocale et rendu sont simulés ; tout le reste (contrat de
proposition, validation métier, jobs, routes, persistance) est le code de
production. Les fichiers produits restent dans tmp_path, jamais dans le vrai
studio.
"""
from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from server import jobs as jobs_mod
from server import media as media_mod
from server import render as render_mod
from server import security
from server.agent import autopilot, capabilities, context, llm_client, proposals, tools
from server import library
from shortvideos import effects, schema
from server.app import app
from shortvideos import tts as tts_mod
from shortvideos import validation as validation_mod

client = TestClient(app)

TEMPLATE = "citation-cinematique"
VOICE = "piper-fr-siwis"


class FakeResult:
    """Ce que ``llm_client.chat`` retourne : le texte brut du modèle."""

    def __init__(self, text: str):
        self.text = text
        self.latency_ms = 12
        self.model = "fake-model"


def _plan_reply(**overrides) -> dict:
    reply = {
        "type": "autopilot_plan",
        "summary": "Citation motivante en français.",
        "template_id": TEMPLATE,
        "script": [
            {"scene_id": "s1", "layer_id": "hook", "text": "Le saviez-vous ?"},
            {"scene_id": "s2", "layer_id": "quote", "text": "La persévérance bat le talent."},
            {"scene_id": "s2", "layer_id": "author", "text": "Anonyme"},
        ],
        "design": [{"op": "set_theme", "path": "accent_color", "value": "#2aa8c9"}],
        "voice": {"voice_id": VOICE, "speed": 1.0},
        "export": {"name": "video-test"},
    }
    reply.update(overrides)
    return reply


@pytest.fixture()
def studio_tmp(monkeypatch, tmp_path):
    """Isole exports, états autopilote et médias du vrai studio."""
    exports = tmp_path / "exports"
    state = tmp_path / "autopilot"
    media = tmp_path / "media"
    for directory in (exports, state, media):
        directory.mkdir()
    monkeypatch.setattr(autopilot, "EXPORTS_DIR", exports)
    monkeypatch.setattr(autopilot, "STATE_DIR", state)
    monkeypatch.setattr(proposals, "MEDIA_DIR", media)
    monkeypatch.setattr(validation_mod, "MEDIA_STORE", media)
    monkeypatch.setattr(security, "ALLOWED_DIRS", (*security.ALLOWED_DIRS, exports))
    return {"exports": exports, "state": state, "media": media}


@pytest.fixture()
def fake_llm(monkeypatch):
    """Un modèle qui répond exactement ce qu'on lui demande, réponse par réponse."""

    def install(*replies):
        sentences = [json.dumps(r, ensure_ascii=False) for r in replies]
        calls = {"index": 0, "messages": []}

        def fake_chat(messages, cfg=None, json_mode=True, cancel=None, **kwargs):
            calls["messages"].append([{**m} for m in messages])
            position = min(calls["index"], len(sentences) - 1)
            calls["index"] += 1
            return FakeResult(sentences[position])

        monkeypatch.setattr(llm_client, "chat", fake_chat)
        monkeypatch.setattr(llm_client, "is_ready", lambda cfg=None: (True, ""))
        return calls

    return install


@pytest.fixture()
def fake_tts(monkeypatch, studio_tmp):
    """Catalogue d'une voix prête + synthèse simulée (aucun moteur réel)."""
    calls = {"synthesize": 0, "texts": []}
    monkeypatch.setattr(tts_mod, "status", lambda models_dir: {
        "engines": [],
        "voices": [{"id": VOICE, "ready": True, "language": "fr", "language_name": "français"}],
    })

    def fake_synthesize(text, voice_id, models_dir, out_path, *, speed=1.0, progress=None, cancel=None):
        calls["synthesize"] += 1
        calls["texts"].append(text)
        if cancel is not None:
            cancel()
        return {"engine": "fake", "duration": 2.0, "sample_rate": 22050, "voice": voice_id}

    monkeypatch.setattr(tts_mod, "synthesize", fake_synthesize)

    def fake_import(path, source, licence="", digest=""):
        media_id = f"voix{calls['synthesize']}"
        (studio_tmp["media"] / f"{media_id}.wav").write_bytes(b"RIFFfake")
        return media_id

    monkeypatch.setattr(media_mod, "import_file_to_media", fake_import)
    return calls


@pytest.fixture()
def fake_tts_wav(monkeypatch, studio_tmp):
    """Comme fake_tts, mais la synthèse écrit un VRAI WAV (bouffées de parole) :
    l'alignement des sous-titres a une matière réelle à lire."""
    calls = {"synthesize": 0, "texts": []}
    monkeypatch.setattr(tts_mod, "status", lambda models_dir: {
        "engines": [],
        "voices": [{"id": VOICE, "ready": True, "language": "fr", "language_name": "français"}],
    })

    def speech_wav(path, seconds=3.0, rate=22050):
        import array
        import math
        import wave
        samples = array.array("h")
        elapsed = 0.0
        while elapsed < seconds:
            for duration, amplitude in ((0.35, 0.8), (0.15, 0.0)):
                count = int(duration * rate)
                for i in range(count):
                    value = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * i / rate)) if amplitude else 0
                    samples.append(value)
                elapsed += duration
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(samples.tobytes())

    def fake_synthesize(text, voice_id, models_dir, out_path, *, speed=1.0, progress=None, cancel=None):
        calls["synthesize"] += 1
        calls["texts"].append(text)
        if cancel is not None:
            cancel()
        speech_wav(out_path)
        return {"engine": "fake", "duration": 3.0, "sample_rate": 22050, "voice": voice_id}

    monkeypatch.setattr(tts_mod, "synthesize", fake_synthesize)

    def fake_import(path, source, licence="", digest=""):
        media_id = f"voix{calls['synthesize']}"
        (studio_tmp["media"] / f"{media_id}.wav").write_bytes(b"RIFFfake")
        return media_id

    monkeypatch.setattr(media_mod, "import_file_to_media", fake_import)
    return calls


@pytest.fixture()
def fake_render(monkeypatch, studio_tmp):
    calls = {"render": 0, "projects": []}

    def render(job, project, out_path):
        calls["render"] += 1
        calls["projects"].append(project)
        out_path.write_bytes(b"fake mp4")
        return {"size_bytes": 8, "duration": 13.5}

    monkeypatch.setattr(render_mod, "render_project_to_mp4", render)
    return calls


def _poll(path: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = client.get(path).json()
        if snapshot.get("status") != "running":
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"Job toujours en cours : {path}")


def _make_plan(fake_llm, reply: dict | None = None) -> dict:
    """Plan complet via les vraies routes : POST /plan puis polling du job."""
    fake_llm(reply if reply is not None else _plan_reply())
    response = client.post("/api/agent/autopilot/plan", json={"message": "Crée une citation motivante."})
    assert response.status_code == 200, response.text
    snapshot = _poll(f"/api/jobs/{response.json()['job_id']}")
    assert snapshot["status"] == "done", snapshot
    return snapshot["result"]["proposal"]


def _start(proposal_id: str) -> str:
    response = client.post("/api/agent/autopilot/start", json={"proposal_id": proposal_id})
    assert response.status_code == 200, response.text
    return response.json()["job_id"]


# --------------------------------------------------------------------------- #
# Chaîne complète
# --------------------------------------------------------------------------- #

def test_full_pipeline_to_video_file(fake_llm, fake_tts, fake_render, studio_tmp):
    proposal = _make_plan(fake_llm)
    assert proposal["type"] == "autopilot_plan"
    assert proposal["validation"]["state"] == "valid"
    assert proposal["autopilot"]["voice"]["voice_id"] == VOICE

    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert [s["status"] for s in state["steps"]] == ["done"] * 4
    assert state["video"]["name"] == "video-test.mp4"
    assert (studio_tmp["exports"] / "video-test.mp4").is_file()
    assert fake_tts["synthesize"] == 1
    assert fake_render["render"] == 1
    # Le texte parlé par défaut est le script complet, dans l'ordre.
    assert fake_tts["texts"] == ["Le saviez-vous ? La persévérance bat le talent. Anonyme"]
    # La voix off est attachée au projet qui part au rendu.
    rendered = fake_render["projects"][0]
    assert rendered["audio"]["voice"] == state["voice_ref"]
    assert rendered["audio"]["enabled"] is True
    # L'état persisté porte de quoi reprendre et servir la vidéo.
    persisted = json.loads((studio_tmp["state"] / f"{job_id}.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "done"
    assert persisted["project"]["audio"]["voice"] == state["voice_ref"]
    # Lien vidéo final : servi par la route dédiée, même origine.
    response = client.get(f"/api/agent/autopilot/{job_id}/file")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")


def test_voice_null_skips_the_voice_step(fake_llm, fake_tts, fake_render, studio_tmp):
    proposal = _make_plan(fake_llm, _plan_reply(voice=None))
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert [s["status"] for s in state["steps"]] == ["done", "done", "skipped", "done"]
    assert fake_tts["synthesize"] == 0
    assert state["voice_ref"] is None


def test_voice_step_paces_scenes_to_narration(fake_llm, fake_tts, fake_render, studio_tmp):
    """G2 : la duree totale du montage rendu suit la voix off (2 s simulees)."""
    proposal = _make_plan(fake_llm)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    # Le rythme est cale DANS l'etape voix : toujours exactement 4 etapes.
    assert [s["status"] for s in state["steps"]] == ["done"] * 4
    rendered = fake_render["projects"][0]
    assert schema.total_duration(rendered) == pytest.approx(2.0, abs=0.1)
    assert proposals.validate_candidate(rendered)[0] == []


def test_no_voice_keeps_original_scene_durations(fake_llm, fake_tts, fake_render, studio_tmp):
    """G2 : sans voix off, l'etape est sautee et les durees restent celles du modele."""
    proposal = _make_plan(fake_llm, _plan_reply(voice=None))
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert state["steps"][2]["status"] == "skipped"
    rendered = fake_render["projects"][0]
    original = library.get_project(TEMPLATE)
    assert schema.total_duration(rendered) == pytest.approx(schema.total_duration(original), abs=0.01)


def test_export_delivers_three_social_formats(fake_llm, fake_tts, monkeypatch, studio_tmp):
    """G3 : le master 9:16 + les derives 1:1 et 16:9 sont livres et servables."""
    import subprocess

    import imageio_ffmpeg

    from shortvideos.probe import probe_mp4

    def real_render(job, project, out_path):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=270x480:d=1:r=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(out_path),
        ], check=True, capture_output=True)
        return {"size_bytes": out_path.stat().st_size, "duration": 1.0}

    monkeypatch.setattr(render_mod, "render_project_to_mp4", real_render)
    proposal = _make_plan(fake_llm)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert [s["status"] for s in state["steps"]] == ["done"] * 4

    video = state["video"]
    formats = video["formats"]
    assert {f["ratio"] for f in formats} == {"1:1", "16:9"}
    exports = studio_tmp["exports"]
    assert (exports / video["name"]).is_file()  # master 9:16 intact
    for fmt in formats:
        path = exports / fmt["name"]
        assert path.is_file()
        info = probe_mp4(str(path))
        assert (info["width"], info["height"]) == (fmt["width"], fmt["height"])
        assert client.get(fmt["url"]).status_code == 200
    # Un nom qui n'est pas un format declare n'est jamais servi.
    assert client.get(f"/api/agent/autopilot/{job_id}/format/inconnu.mp4").status_code == 404


def test_design_step_auto_broll_matches_theme(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    """G4 : un visuel local pertinent est pose en fond DANS l'etape design (4 etapes)."""
    (studio_tmp["media"] / "broll-montagne.png").write_bytes(b"png")
    monkeypatch.setattr(autopilot, "_gather_broll_assets", lambda: [
        {"ref": "media://broll-montagne", "name": "montagne.png", "kind": "image", "folder": "Paysages"},
    ])
    reply = _plan_reply(script=[
        {"scene_id": "s1", "layer_id": "hook", "text": "Le saviez-vous ?"},
        {"scene_id": "s2", "layer_id": "quote", "text": "La montagne nous appelle."},
        {"scene_id": "s2", "layer_id": "author", "text": "Anonyme"},
    ])
    proposal = _make_plan(fake_llm, reply)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert [s["status"] for s in state["steps"]] == ["done"] * 4
    rendered = fake_render["projects"][0]
    scenes = {s["id"]: s for s in rendered["content"]["scenes"]}
    assert scenes["s2"]["background"]["media"] == "media://broll-montagne"
    assert scenes["s1"]["background"]["media"] == ""  # aucune correspondance de theme
    assert proposals.validate_candidate(rendered)[0] == []


def test_auto_broll_missing_media_never_breaks_design(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    """G4 best-effort : un media collecte mais absent du store ne casse pas le plan."""
    monkeypatch.setattr(autopilot, "_gather_broll_assets", lambda: [
        {"ref": "media://fantome", "name": "montagne.png", "kind": "image"},
    ])
    reply = _plan_reply(script=[
        {"scene_id": "s1", "layer_id": "hook", "text": "Le saviez-vous ?"},
        {"scene_id": "s2", "layer_id": "quote", "text": "La montagne nous appelle."},
        {"scene_id": "s2", "layer_id": "author", "text": "Anonyme"},
    ])
    proposal = _make_plan(fake_llm, reply)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert [s["status"] for s in state["steps"]] == ["done"] * 4
    rendered = fake_render["projects"][0]
    assert all(s["background"]["media"] == "" for s in rendered["content"]["scenes"])


# --------------------------------------------------------------------------- #
# Sous-titres synchronisés (drapeau captions)
# --------------------------------------------------------------------------- #

def _caption_layers(project: dict) -> list[dict]:
    return [layer for scene in project["content"]["scenes"]
            for layer in scene["layers"] if layer.get("role") == "caption"]


def test_captions_flag_adds_synced_subtitle_layers(fake_llm, fake_tts_wav, fake_render, studio_tmp):
    reply = _plan_reply(voice={"voice_id": VOICE, "speed": 1.0}, captions=True)
    proposal = _make_plan(fake_llm, reply)
    assert proposal["autopilot"]["captions"] is True
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    rendered = fake_render["projects"][0]
    layers = _caption_layers(rendered)
    assert layers, "des sous-titres synchronisés sont posés sur le montage"
    assert all(layer["text"].strip() for layer in layers)
    # La piste synchronisée remplace les sous-titres décoratifs du modèle.
    assert all(layer["id"].startswith("caption-") for layer in layers)
    # Le texte vient de la narration réelle, rien d'inventé.
    spoken = fake_tts_wav["texts"][0]
    assert all(word in spoken for layer in layers for word in layer["text"].split())
    # Design et voix off conservés ; le projet qui part au rendu reste valide.
    assert rendered["audio"]["voice"] == state["voice_ref"]
    assert rendered["audio"]["enabled"] is True
    assert proposals.validate_candidate(rendered)[0] == []


def test_captions_default_off_keeps_design_clean(fake_llm, fake_tts_wav, fake_render, studio_tmp):
    proposal = _make_plan(fake_llm, _plan_reply(voice={"voice_id": VOICE, "speed": 1.0}))
    assert proposal["autopilot"]["captions"] is False
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    rendered = fake_render["projects"][0]
    # Sans le drapeau, les sous-titres décoratifs du modèle restent tels quels :
    # aucun calque synchronisé « caption-N » n'est ajouté.
    template = library.get_project(TEMPLATE)
    expected = {layer["id"] for scene in template["content"]["scenes"]
                for layer in scene["layers"] if layer.get("role") == "caption"}
    assert {layer["id"] for layer in _caption_layers(rendered)} == expected


def test_captions_without_voice_is_ignored(fake_llm, fake_tts_wav, fake_render, studio_tmp):
    proposal = _make_plan(fake_llm, _plan_reply(voice=None, captions=True))
    assert proposal["autopilot"]["captions"] is False
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert state["steps"][2]["status"] == "skipped"
    assert fake_tts_wav["synthesize"] == 0


def test_captions_guidance_reaches_autopilot_rules_and_grounding():
    manifest = capabilities.build()
    for compact in (False, True):
        assert "captions" in capabilities.autopilot_grounding(manifest, compact=compact)
    assert "captions" in context.AUTOPILOT_RULES
    assert "ne promets pas de synchronisation" not in context.AUTOPILOT_RULES


def test_export_name_never_overwrites_an_existing_file(fake_llm, fake_tts, fake_render, studio_tmp):
    (studio_tmp["exports"] / "video-test.mp4").write_bytes(b"export precedent")
    proposal = _make_plan(fake_llm)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert state["video"]["name"] == "video-test-2.mp4"
    assert (studio_tmp["exports"] / "video-test.mp4").read_bytes() == b"export precedent"


# --------------------------------------------------------------------------- #
# Échec, annulation, reprise
# --------------------------------------------------------------------------- #

def test_export_failure_stops_the_plan_cleanly(fake_llm, fake_tts, monkeypatch, studio_tmp):
    def boom(job, project, out_path):
        out_path.write_bytes(b"partiel")
        raise RuntimeError("rendu impossible (test)")

    monkeypatch.setattr(render_mod, "render_project_to_mp4", boom)
    proposal = _make_plan(fake_llm)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "error", state
    assert [s["status"] for s in state["steps"]] == ["done", "done", "done", "failed"]
    assert "rendu impossible" in state["steps"][3]["error"]
    assert state["video"] is None
    assert state["resumable"] is True
    # Aucun fichier provisoire ne reste, aucun export final n'est publié.
    assert list(studio_tmp["exports"].iterdir()) == []
    assert client.get(f"/api/agent/autopilot/{job_id}/file").status_code == 404


def test_resume_reruns_only_the_failed_step(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    def boom(job, project, out_path):
        raise RuntimeError("coupure simulée")

    monkeypatch.setattr(render_mod, "render_project_to_mp4", boom)
    proposal = _make_plan(fake_llm)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "error", state
    assert fake_tts["synthesize"] == 1

    # Le serveur a redémarré (ou le rendu est réparé) : on reprend le MÊME plan.
    def repaired(job, project, out_path):
        fake_render["render"] += 1
        fake_render["projects"].append(project)
        out_path.write_bytes(b"fake mp4")
        return {"size_bytes": 8, "duration": 13.5}

    monkeypatch.setattr(render_mod, "render_project_to_mp4", repaired)
    response = client.post("/api/agent/autopilot/start", json={"job_id": job_id})
    assert response.status_code == 200, response.text
    assert response.json()["job_id"] == job_id, "l'identifiant du plan survit à la reprise"
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert [s["status"] for s in state["steps"]] == ["done"] * 4
    assert fake_tts["synthesize"] == 1, "la voix off déjà synthétisée n'est pas rejouée"
    assert fake_render["render"] == 1, "seul l'export est rejoué"


def test_interrupted_state_is_resumable_after_restart(fake_llm, fake_tts, fake_render, studio_tmp):
    """Crash serveur en plein export : l'état disque dit running, aucun job vivant."""
    reply = _plan_reply(voice=None)
    plan = proposals.from_reply(reply, None, "")
    state = {
        "job_id": "interrompu1",
        "proposal_id": plan["id"],
        "status": "running",
        "project_name": plan["project_name"],
        "plan": plan["autopilot"],
        "steps": [
            {"id": "script", "label": "Script", "status": "done", "message": "", "error": ""},
            {"id": "design", "label": "Design", "status": "done", "message": "", "error": ""},
            {"id": "voice", "label": "Voix off", "status": "skipped", "message": "", "error": ""},
            {"id": "export", "label": "Export MP4", "status": "running", "message": "", "error": ""},
        ],
        "project": plan["candidate"],
        "voice_ref": None,
        "video": None,
        "error": "",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    (studio_tmp["state"] / "interrompu1.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    seen = client.get("/api/agent/autopilot/interrompu1").json()
    assert seen["status"] == "interrupted"
    assert seen["resumable"] is True

    response = client.post("/api/agent/autopilot/start", json={"job_id": "interrompu1"})
    assert response.status_code == 200, response.text
    state = _poll("/api/agent/autopilot/interrompu1")
    assert state["status"] == "done", state
    assert fake_render["render"] == 1
    assert fake_tts["synthesize"] == 0


# --------------------------------------------------------------------------- #
# Auto-reprise : retry borné par étape + reprise des plans interrompus
# --------------------------------------------------------------------------- #

def test_transient_export_failure_is_retried_once(fake_llm, fake_tts, monkeypatch, studio_tmp):
    calls = {"render": 0}

    def flaky(job, project, out_path):
        calls["render"] += 1
        if calls["render"] == 1:
            raise RuntimeError("coupure transitoire (test)")
        out_path.write_bytes(b"fake mp4")
        return {"size_bytes": 8, "duration": 13.5}

    monkeypatch.setattr(render_mod, "render_project_to_mp4", flaky)
    proposal = _make_plan(fake_llm)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert [s["status"] for s in state["steps"]] == ["done"] * 4
    assert calls["render"] == 2, "l'export transitoire est rejoué une fois, sans clic"
    assert (studio_tmp["exports"] / "video-test.mp4").is_file()


def test_persistent_export_failure_surfaces_after_bounded_retry(fake_llm, fake_tts, monkeypatch, studio_tmp):
    calls = {"render": 0}

    def boom(job, project, out_path):
        calls["render"] += 1
        raise RuntimeError("rendu impossible (test)")

    monkeypatch.setattr(render_mod, "render_project_to_mp4", boom)
    proposal = _make_plan(fake_llm)
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "error", state
    assert calls["render"] == 2, "la reprise est bornée : pas de boucle infinie"
    assert state["steps"][3]["status"] == "failed"
    assert "rendu impossible" in state["steps"][3]["error"]
    assert state["resumable"] is True
    assert list(studio_tmp["exports"].iterdir()) == []


def test_cancel_is_not_retried(fake_llm, fake_tts, monkeypatch, studio_tmp):
    calls = {"render": 0}

    def cancelled(job, project, out_path):
        calls["render"] += 1
        raise jobs_mod.JobCancelled()

    monkeypatch.setattr(render_mod, "render_project_to_mp4", cancelled)
    proposal = _make_plan(fake_llm, _plan_reply(voice=None))
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "cancelled", state
    assert calls["render"] == 1, "une annulation n'est jamais rejouée"
    assert state["steps"][3]["status"] == "cancelled"


def test_resume_interrupted_relaunches_only_running_plans(fake_llm, fake_tts, fake_render, studio_tmp):
    plan = proposals.from_reply(_plan_reply(voice=None), None, "")

    def write_state(job_id, status, export_status):
        state = {
            "job_id": job_id,
            "proposal_id": plan["id"],
            "status": status,
            "project_name": plan["project_name"],
            "plan": plan["autopilot"],
            "steps": [
                {"id": "script", "label": "Script", "status": "done", "message": "", "error": ""},
                {"id": "design", "label": "Design", "status": "done", "message": "", "error": ""},
                {"id": "voice", "label": "Voix off", "status": "skipped", "message": "", "error": ""},
                {"id": "export", "label": "Export MP4", "status": export_status, "message": "", "error": ""},
            ],
            "project": plan["candidate"],
            "voice_ref": None,
            "video": None,
            "error": "",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        (studio_tmp["state"] / f"{job_id}.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    write_state("interrompuA", "running", "running")
    write_state("termineB", "done", "done")

    resumed = autopilot.resume_interrupted()
    assert resumed == ["interrompuA"], "seuls les plans « running » sur disque sont repris"
    state = _poll("/api/agent/autopilot/interrompuA")
    assert state["status"] == "done", state
    assert fake_render["render"] == 1
    assert fake_tts["synthesize"] == 0
    # Une fois terminé, le plan n'est plus repris : pas de double exécution.
    assert autopilot.resume_interrupted() == []


def test_cancel_stops_the_plan_and_cleans_up(fake_llm, fake_tts, monkeypatch, studio_tmp):
    started = threading.Event()

    def blocking_render(job, project, out_path):
        out_path.write_bytes(b"partiel")
        started.set()
        for _ in range(200):
            if job.cancel_event.is_set():
                raise jobs_mod.JobCancelled()
            time.sleep(0.05)
        raise RuntimeError("le test n'a pas annulé à temps")

    monkeypatch.setattr(render_mod, "render_project_to_mp4", blocking_render)
    proposal = _make_plan(fake_llm, _plan_reply(voice=None))
    job_id = _start(proposal["id"])
    assert started.wait(timeout=10), "le rendu n'a pas démarré"
    response = client.post(f"/api/agent/autopilot/{job_id}/cancel")
    assert response.status_code == 200, response.text
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "cancelled", state
    assert state["steps"][3]["status"] == "cancelled"
    assert state["resumable"] is True
    assert list(studio_tmp["exports"].iterdir()) == [], "le fichier provisoire est nettoyé"


# --------------------------------------------------------------------------- #
# Auto-correction après rendu (drapeau review)
# --------------------------------------------------------------------------- #

def test_review_default_off_skips_audit(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    from server.agent import review as review_mod

    called = {"review": 0}

    def spy(*args, **kwargs):
        called["review"] += 1
        return {"operations": []}

    monkeypatch.setattr(review_mod, "review_project", spy)
    proposal = _make_plan(fake_llm)
    assert proposal["autopilot"]["review"] is False
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert called["review"] == 0
    assert fake_render["render"] == 1


def test_review_flag_audits_corrects_and_rerenders(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    from server import settings as settings_mod
    from server.agent import review as review_mod

    monkeypatch.setattr(settings_mod, "llm_config", lambda: {"provider": "fake"})
    seen = {"review": 0}

    def fake_review(job, project, prompt, cfg):
        seen["review"] += 1
        return {"summary": "audit", "verified": False, "defects": [], "frames": [],
                "measurements": [], "rounds": [],
                "operations": [{"op": "set_theme", "path": "accent_color", "value": "#123456"}]}

    monkeypatch.setattr(review_mod, "review_project", fake_review)
    proposal = _make_plan(fake_llm, _plan_reply(review=True))
    assert proposal["autopilot"]["review"] is True
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert seen["review"] == 1
    assert fake_render["render"] == 2, "rendu initial + re-rendu après correction"
    # La correction est appliquée au projet persisté et à la vidéo finale.
    persisted = json.loads((studio_tmp["state"] / f"{job_id}.json").read_text(encoding="utf-8"))
    assert persisted["project"]["theme"]["accent_color"] == "#123456"
    assert fake_render["projects"][-1]["theme"]["accent_color"] == "#123456"
    assert (studio_tmp["exports"] / "video-test.mp4").is_file()


def test_review_without_defect_keeps_single_render(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    from server import settings as settings_mod
    from server.agent import review as review_mod

    monkeypatch.setattr(settings_mod, "llm_config", lambda: {})
    monkeypatch.setattr(review_mod, "review_project", lambda *a, **k: {"operations": [], "verified": True})
    proposal = _make_plan(fake_llm, _plan_reply(review=True))
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert fake_render["render"] == 1


def test_review_without_llm_keeps_the_export(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    from server import settings as settings_mod
    from server.agent import review as review_mod

    monkeypatch.setattr(settings_mod, "llm_config", lambda: {})
    called = {"review": 0}

    def spy(*args, **kwargs):
        called["review"] += 1
        return {"operations": []}

    monkeypatch.setattr(review_mod, "review_project", spy)
    proposal = _make_plan(fake_llm, _plan_reply(review=True))
    # Le LLM tombe en panne après la validation du plan : la revue est sautée.
    monkeypatch.setattr(llm_client, "is_ready", lambda cfg=None: (False, "clé absente"))
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert called["review"] == 0, "sans LLM prêt, aucune revue n'est tentée"
    assert fake_render["render"] == 1


def test_review_failure_does_not_break_the_export(fake_llm, fake_tts, fake_render, monkeypatch, studio_tmp):
    from server import settings as settings_mod
    from server.agent import review as review_mod

    monkeypatch.setattr(settings_mod, "llm_config", lambda: {})

    def boom(*args, **kwargs):
        raise ValueError("sonde indisponible (test)")

    monkeypatch.setattr(review_mod, "review_project", boom)
    proposal = _make_plan(fake_llm, _plan_reply(review=True))
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert fake_render["render"] == 1, "la première vidéo est conservée"
    assert (studio_tmp["exports"] / "video-test.mp4").is_file()


def test_review_guidance_reaches_autopilot_rules():
    assert "review" in context.AUTOPILOT_RULES
    assert '"review":true' in context.AUTOPILOT_RULES


# --------------------------------------------------------------------------- #
# Validation du plan (contrat serveur)
# --------------------------------------------------------------------------- #

def test_plan_refuses_an_invented_template():
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.from_reply(_plan_reply(template_id="quote_vertical"), None, "")
    assert "quote_vertical" in str(exc.value)
    assert TEMPLATE in str(exc.value), "le message de réparation liste les modèles réels"


def test_plan_refuses_an_unknown_or_not_downloaded_voice(fake_tts):
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.from_reply(_plan_reply(voice={"voice_id": "voix-fantome"}), None, "")
    assert "voix-fantome" in str(exc.value)
    assert VOICE in str(exc.value), "le message liste les voix prêtes"


def test_plan_refuses_an_effect_out_of_its_scope(fake_tts):
    reply = _plan_reply(design=[
        {"op": "set_effects", "scene_id": "s2", "layer_id": "quote", "effects": ["path_trace"]},
    ])
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.from_reply(reply, None, "")
    assert "path_trace" in str(exc.value)
    assert "portee" in str(exc.value) or "portée" in str(exc.value)


def test_plan_refuses_a_script_targeting_an_unknown_layer(fake_tts):
    reply = _plan_reply(script=[{"scene_id": "s1", "layer_id": "calque-fantome", "text": "…"}])
    with pytest.raises(proposals.ProposalError) as exc:
        proposals.from_reply(reply, None, "")
    assert "calque-fantome" in str(exc.value)


def test_accept_of_a_plan_is_refused_points_to_start(fake_llm, fake_tts, studio_tmp):
    proposal = _make_plan(fake_llm)
    response = client.post(f"/api/agent/proposals/{proposal['id']}/accept", json={"project": None})
    assert response.status_code == 424
    assert "autopilot/start" in response.json()["detail"]


def test_start_requires_exactly_one_identifier():
    assert client.post("/api/agent/autopilot/start", json={}).status_code == 400
    assert client.post(
        "/api/agent/autopilot/start", json={"proposal_id": "a", "job_id": "b"}
    ).status_code == 400
    assert client.post(
        "/api/agent/autopilot/start", json={"proposal_id": "inconnu"}
    ).status_code == 404
    assert client.post(
        "/api/agent/autopilot/start", json={"job_id": "inconnu"}
    ).status_code == 404


def test_status_of_unknown_plan_is_404():
    assert client.get("/api/agent/autopilot/inexistant").status_code == 404
    assert client.get("/api/agent/autopilot/inexistant/file").status_code == 404


# --------------------------------------------------------------------------- #
# Contexte obligatoire (création, voix prêtes)
# --------------------------------------------------------------------------- #

def test_creation_hint_is_in_context_when_no_project(fake_llm, fake_tts):
    calls = fake_llm({"type": "question", "summary": "Précision.", "questions": ["Quel sujet ?"]})
    response = client.post("/api/agent/ask", json={"message": "crée une vidéo", "project": None})
    assert response.status_code == 200
    snapshot = _poll(f"/api/jobs/{response.json()['job_id']}")
    assert snapshot["status"] == "done", snapshot
    user_content = calls["messages"][0][-1]["content"]
    assert "AUCUN PROJET ACTIF" in user_content
    assert TEMPLATE in user_content, "la liste RÉELLE des modèles est fournie"
    assert "jamais project_patch" in user_content


def test_no_creation_hint_when_a_project_is_active(fake_llm, fake_tts):
    from shortvideos import schema

    calls = fake_llm({"type": "question", "summary": "Précision.", "questions": ["Quel sujet ?"]})
    response = client.post("/api/agent/ask", json={
        "message": "modifie la vidéo", "project": schema.new_project("quote_cinematic"),
    })
    assert response.status_code == 200
    snapshot = _poll(f"/api/jobs/{response.json()['job_id']}")
    assert snapshot["status"] == "done", snapshot
    user_content = calls["messages"][0][-1]["content"]
    assert "AUCUN PROJET ACTIF" not in user_content


def test_autopilot_context_lists_ready_voices(fake_llm, fake_tts):
    calls = fake_llm(_plan_reply())
    response = client.post("/api/agent/autopilot/plan", json={"message": "Crée une citation motivante."})
    assert response.status_code == 200, response.text
    snapshot = _poll(f"/api/jobs/{response.json()['job_id']}")
    assert snapshot["status"] == "done", snapshot
    messages = calls["messages"][0]
    system = messages[0]["content"]
    user = messages[-1]["content"]
    assert "MODE AUTOPILOTE" in user, "règles du plan jamais tronquées (mode compact inclus)"
    assert "autopilot_plan" in system
    assert "VOIX PRÊTES" in user
    assert VOICE in user, "seules les voix prêtes sont proposées"
    assert "GUIDE AUTOPILOTE" in user
    assert "recit-cinematique" in user and "showcase-cinematique" in user
    assert "EXEMPLES VALIDÉS" in user
    assert all(effect_id in user for effect_id in effects.ids())
    assert "réponds type=project_new" not in user


@pytest.mark.parametrize("template_id,scene_count,seconds", [
    ("recit-cinematique", 5, 18), ("showcase-cinematique", 4, 14),
])
def test_cinematic_presets_are_valid_without_assets(template_id, scene_count, seconds):
    project = library.builtin_project(template_id)
    assert proposals.validate_candidate(project)[0] == []
    assert project["model"]["id"] == "quote_cinematic"
    assert len(project["content"]["scenes"]) == scene_count
    assert schema.total_duration(project) == seconds
    assert project["content"]["signature"]["enabled"] is False
    assert project["audio"]["music"] == project["audio"]["voice"] == ""
    assert project["audio"]["music_volume"] <= 0.15
    assert all(not scene["background"]["media"] for scene in project["content"]["scenes"])
    project["content"]["scenes"][0]["layers"][0]["text"] = "modifié"
    assert library.builtin_project(template_id) != project


@pytest.mark.parametrize("example", capabilities.AUTOPILOT_EXAMPLES)
def test_storyboard_examples_fill_every_visible_text(example):
    proposal = proposals.from_reply(example["plan"], None, "")
    assert proposal["validation"]["state"] == "valid"
    template = library.get_project(example["plan"]["template_id"])
    targets = {(entry["scene_id"], entry["layer_id"]) for entry in example["plan"]["script"]}
    expected = {(scene["id"], layer["id"]) for scene in template["content"]["scenes"]
                for layer in scene["layers"] if layer["type"] == "text" and not layer.get("hidden")}
    assert targets == expected
    assert len(proposal["autopilot"]["script"]) == len(expected)


def test_catalog_structure_matches_real_templates_and_slots():
    items = tools.execute("list_templates", {}, {})["templates"]
    for item in items:
        project = library.get_project(item["id"])
        assert item["structure"] == capabilities._template_structure(project)
    showcase = next(item for item in items if item["id"] == "showcase-cinematique")
    slots = [layer for scene in showcase["structure"] for layer in scene["layers"]
             if layer["type"] == "image"]
    assert len(slots) == 2
    assert all(layer["id"] == "visual" and layer["hidden"] for layer in slots)


def test_compact_autopilot_preserves_catalog_examples_and_budget():
    manifest = capabilities.build()
    messages, meta = context.build(
        request="Raconte une histoire motivante.", project=None, budget_tokens=2300,
        capabilities_text=capabilities.autopilot_grounding(manifest),
        capabilities_text_compact=capabilities.autopilot_grounding(manifest, compact=True),
        system_override=context.AUTOPILOT_RULES, required_text="VOIX PRÊTES : aucune, voice=null.",
        passages=[{"source": "test", "path": "test", "title": "test", "version": "1", "text": "x" * 9000}],
    )
    assert meta["compact_prompt"] is True
    assert meta["total_chars"] == sum(len(m["content"]) for m in messages)
    assert meta["total_chars"] <= 2300 * context.CHARS_PER_TOKEN
    user = messages[-1]["content"]
    for template in manifest["templates"]:
        assert template["id"] in user
        for scene in template["structure"]:
            assert scene["scene"] in user
            for layer in scene["layers"]:
                assert layer["id"] in user
    assert all(effect_id in user for effect_id in effects.ids())
    assert "EXEMPLES VALIDÉS" in user and "VOIX PRÊTES" in user
    assert "list_effects" in messages[0]["content"]


def test_grounding_reports_overflow_instead_of_silent_truncation():
    manifest = capabilities.build()
    with pytest.raises(context.ContextTooLarge):
        context.build(
            request="Vidéo", project=None, budget_tokens=1400,
            capabilities_text=capabilities.autopilot_grounding(manifest),
            capabilities_text_compact=capabilities.autopilot_grounding(manifest, compact=True),
            system_override=context.AUTOPILOT_RULES,
        )


def test_director_craft_guides_autopilot_and_design():
    """Le cerveau de réalisateur : techniques de montage motivées, pas un template rempli."""
    manifest = capabilities.build()
    for compact in (False, True):
        grounding = capabilities.autopilot_grounding(manifest, compact=compact)
        assert "RÉALISATION" in grounding
        for technique in ("kinetic_letters", "color_grade", "emphasis"):
            assert technique in grounding, f"{technique} absent du grounding (compact={compact})"
    assert "RÉALISATION" in capabilities.prompt_block(manifest)
    assert "réalisateur" in context.SYSTEM_RULES and "ingénieur de montage" in context.SYSTEM_RULES


def test_image_generate_guidance_reaches_design_grounding_only():
    """Quand proposer une image générée, et pourquoi l'affectation reste séparée.

    Le guidage vit dans le grounding design (budget souple). Il n'entre PAS dans
    le grounding autopilote compact : l'autopilote a 4 étapes fixes et ne génère
    pas d'image en plein plan, et son budget de contexte est déjà au plus juste.
    """
    manifest = capabilities.build()
    grounding = capabilities.prompt_block(manifest)
    assert "image_generate" in grounding
    assert "clic dédié" in grounding
    assert "SÉPARÉE" in grounding
    assert "set_scene background.media" in grounding and "hidden=false" in grounding
    assert "Pollinations" in grounding
    assert "image_generate" not in capabilities.autopilot_grounding(manifest, compact=True)


def test_list_assets_includes_imported_media_without_connected_folders(monkeypatch):
    monkeypatch.setattr(tools.folders_mod, "assets_by_kind", lambda kind: [])
    media = [{"ref": "media://local-image", "kind": "image", "name": "image.png", "licence": "personnelle"},
             {"ref": "media://local-audio", "kind": "audio", "name": "music.wav", "licence": "personnelle"}]
    assets = tools.execute("list_assets", {"kind": "image"}, {"manifest": {"media": media}})["assets"]
    assert [a["ref"] for a in assets] == ["media://local-image"]
    monkeypatch.setattr(tools.folders_mod, "assets_by_kind", lambda kind: [media[0]])
    assert len(tools.execute("list_assets", {"kind": "image"}, {"manifest": {"media": media}})["assets"]) == 1


def test_showcase_accepts_real_local_image_and_music(studio_tmp):
    from PIL import Image
    import wave

    Image.new("RGB", (64, 64), "gold").save(studio_tmp["media"] / "preview.png")
    with wave.open(str(studio_tmp["media"] / "bed.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 8000, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 8000)
    reply = schema.clone(capabilities.AUTOPILOT_EXAMPLES[1]["plan"])
    reply["design"] = [
        {"op": "set_layer", "scene_id": "s2", "layer_id": "visual", "path": "media", "value": "media://preview"},
        {"op": "set_layer", "scene_id": "s2", "layer_id": "visual", "path": "hidden", "value": False},
        {"op": "set_audio", "path": "music", "value": "media://bed"},
        {"op": "set_audio", "path": "enabled", "value": True},
    ]
    plan = proposals.from_reply(reply, None, "")
    assert plan["validation"]["state"] == "valid"
    assert plan["candidate"]["audio"]["music"] == "media://bed"
    reply["design"][0]["value"] = "media://does-not-exist"
    with pytest.raises(proposals.ProposalError):
        proposals.from_reply(reply, None, "")


@pytest.mark.parametrize("example", capabilities.AUTOPILOT_EXAMPLES)
def test_new_presets_pass_full_autopilot_pipeline(example, fake_llm, fake_tts, fake_render):
    proposal = _make_plan(fake_llm, example["plan"])
    job_id = _start(proposal["id"])
    state = _poll(f"/api/agent/autopilot/{job_id}")
    assert state["status"] == "done", state
    assert fake_render["render"] == 1
    assert fake_tts["synthesize"] == 0
    assert fake_render["projects"][0]["name"] == example["plan"]["template_id"]