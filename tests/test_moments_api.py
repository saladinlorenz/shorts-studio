"""Trajet complet des moments forts par HTTP : source -> analyse -> projet.

Seule la reconnaissance vocale est simulee : aucun reseau pendant les tests. Tout le
reste est le code de production — la source est un vrai MP4 (image + son) fabrique par
le ffmpeg embarque, sa piste est reellement extraite et mesuree, l'extrait vocal et la
miniature sont reellement importes dans ``media/``, le projet ecrit dans ``projects/``
passe par la validation du studio.

Lois verifiees ici :

- « l'assistant propose, l'utilisateur applique » : l'analyse n'ecrit aucun projet ;
- la cle de Clips ne sort pas d'elle-meme, et aucune cle ne remonte au client ;
- une source se designe par ``media://``, jamais par un chemin disque ;
- la miniature ratee ou impossible n'empeche jamais la generation ;
- la file SQLite du lot reste etrangere a ce parcours.
"""
from __future__ import annotations

import json
import math
import subprocess
import time
import wave
from pathlib import Path

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from server import brands as brands_mod
from server import media as media_mod
from server import mediacache
from server import moments as moments_mod
from server import queue as queue_mod
from server import settings as settings_mod
from server.app import app
from shortvideos import asr, delivery, moments, schema, validation

SOURCE_DURATION = 6.0
SEGMENTS = [
    (0.40, 1.90, "Ce que personne ne te dit : la discipline s'entraine."),
    (2.20, 3.60, "Le probleme n'est pas la paresse, c'est l'absence de signal."),
    (4.00, 5.60, "Deux minutes de clarte valent dix heures d'agitation."),
]
ASR_KEY = "gsk-cle-dediee-introuvable"
CLIPS_KEY = "gsk-cle-de-clips-introuvable"


def _clip(path: Path) -> Path:
    """Un vrai MP4 avec piste audio : la miniature et le decoupe s'exercent sur du reel."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=15:duration={SOURCE_DURATION}",
         "-f", "lavfi", "-i", f"sine=frequency=320:sample_rate=16000:duration={SOURCE_DURATION}",
         "-c:v", "mpeg4", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        capture_output=True, text=True, timeout=180, check=True,
    )
    return path


def _podcast(path: Path, seconds: float = SOURCE_DURATION) -> Path:
    """Un WAV 16 kHz mono, crete pendant les segments et silence entre les deux."""
    rate = 16000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(int(seconds * rate)):
            at = index / rate
            speaking = any(s - 0.05 <= at <= e for s, e, _ in SEGMENTS)
            value = int(9000 * math.sin(2 * math.pi * 320 * at)) if speaking else 0
            frames += value.to_bytes(2, "little", signed=True)
        handle.writeframes(bytes(frames))
    return path


def _silent_clip(path: Path, seconds: float = SOURCE_DURATION) -> Path:
    """Une video sans piste audio : la transcription n'a rien a ecouter."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=15:duration={seconds}",
         "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, text=True, timeout=180, check=True,
    )
    return path


def _fake_transcribe(calls: list[dict]):
    def transcribe(source, **kwargs):
        calls.append({"provider": kwargs.get("provider"), "api_key": kwargs.get("api_key"),
                      "model": kwargs.get("groq_model"), "language": kwargs.get("language")})
        audio_out = kwargs.get("audio_out")
        if audio_out:
            asr.extract_audio(source, audio_out)  # vraie piste : l'energie mesuree sera celle du fichier
        progress = kwargs.get("progress")
        if progress:
            progress(len(SEGMENTS), len(SEGMENTS), "transcription simulee")
        return {
            "provider": "fake", "model": "whisper-large-v3-turbo",
            "language": kwargs.get("language") or "fr", "duration": SOURCE_DURATION,
            "warnings": [],
            "segments": [{"start": s, "end": e, "text": t} for s, e, t in SEGMENTS],
        }
    return transcribe


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    moments_dir = tmp_path / "moments"
    projects_dir = tmp_path / "projects"
    brands_dir = tmp_path / "brands"
    for folder in (media_dir, moments_dir, projects_dir, brands_dir):
        folder.mkdir(parents=True)
    _clip(media_dir / "episode.mp4")
    _silent_clip(media_dir / "muet.mp4")
    _podcast(media_dir / "podcast.wav")

    monkeypatch.setattr(media_mod, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(media_mod, "PROVENANCE_DIR", media_dir / "provenance")
    monkeypatch.setattr(moments_mod, "MOMENTS_DIR", moments_dir)
    monkeypatch.setattr(moments_mod, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(moments_mod, "assert_local_dir", lambda path: path)
    monkeypatch.setattr(brands_mod, "BRANDS_DIR", brands_dir)
    monkeypatch.setattr(brands_mod, "assert_local_dir", lambda path: path)
    monkeypatch.setattr(validation, "MEDIA_STORE", media_dir)
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(mediacache, "ensure_cached", lambda media_id: None)
    monkeypatch.setattr(queue_mod, "DB_PATH", tmp_path / "batch" / "queue.sqlite3")

    calls: list[dict] = []
    monkeypatch.setattr(asr, "transcribe", _fake_transcribe(calls))
    client = TestClient(app)
    return {
        "client": client, "tmp": tmp_path, "media": media_dir, "moments": moments_dir,
        "projects": projects_dir, "brands": brands_dir, "calls": calls,
        "settings": tmp_path / "settings.json",
    }


def _finished(client: TestClient, job_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = client.get(f"/api/jobs/{job_id}").json()
        if snapshot["status"] != "running":
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} jamais termine")


def _analyse(studio: dict, source: str = "media://episode", **overrides) -> str:
    body = {"source": source, "min_seconds": 1.0, "max_seconds": 4.0, "top": 3}
    body.update(overrides)
    res = studio["client"].post("/api/moments/analyze", json=body)
    assert res.status_code == 200, res.text
    job = _finished(studio["client"], res.json()["job_id"])
    assert job["status"] == "done", job
    assert job["kind"] == "moments-analyze"
    return job["result"]["analysis"]["id"]


def _settings(studio: dict, **values) -> None:
    studio["settings"].write_text(json.dumps(values), encoding="utf-8")


# --- etat de la machine --------------------------------------------------------


def test_providers_decrivent_la_machine_sans_jamais_montrer_une_cle(studio):
    res = studio["client"].get("/api/moments/providers")
    assert res.status_code == 200
    body = res.json()
    assert {p["id"] for p in body["providers"]} == {"groq", "local"}
    assert body["asr_key_configured"] is False and body["clips_key_configured"] is False
    groq = next(p for p in body["providers"] if p["id"] == "groq")
    assert groq["available"] is False and groq["reason"], "sans cle, la voie est fermee et la raison est ecrite"
    assert body["local_backend"]["available"] in (True, False)
    assert set(body["duration_presets"]) == {"short", "standard", "long"}
    assert body["top_default"] == moments.TOP_DEFAULT
    _settings(studio, asr_groq_api_key=ASR_KEY, groq_api_key=CLIPS_KEY)
    after = studio["client"].get("/api/moments/providers").json()
    assert after["asr_key_configured"] is True and after["clips_key_configured"] is True
    assert ASR_KEY not in res.text and CLIPS_KEY not in res.text


# --- l'analyse propose, elle n'applique pas ------------------------------------


def test_l_analyse_ecrit_dans_moments_et_rien_dans_projects(studio):
    analysis_id = _analyse(studio)
    record = studio["moments"] / f"{analysis_id}.json"
    assert record.is_file()
    assert studio["projects"].exists() and list(studio["projects"].iterdir()) == [], \
        "l'analyse ne cree aucun projet de travail : c'est le clic qui applique"

    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["source_ref"] == "media://episode" and data["source_media_id"] == "episode"
    assert data["transcript"]["audio_path"] == "", "le chemin du WAV ne reste pas dans l'analyse"
    assert [s["text"] for s in data["transcript"]["segments"]] == [t for _s, _e, t in SEGMENTS]
    assert data["detect"] == {"min_seconds": 1.0, "max_seconds": 4.0, "top": 3,
                              "algorithm": "score+energie"}
    assert data["moments"], "three anchored thoughts on 6 s must give at least one moment"

    energy = json.loads((studio["moments"] / "work" / analysis_id / "energy.json").read_text(encoding="utf-8"))
    assert len(energy["rms"]) == pytest.approx(SOURCE_DURATION / energy["window_s"], abs=3)
    assert max(energy["rms"]) > 0, "l'enveloppe est mesuree sur la vraie piste, pas inventee"
    work = studio["moments"] / "work" / analysis_id
    assert [p.name for p in work.iterdir()] == ["energy.json"], \
        "la piste brute n'est pas gardee : seule l'enveloppe mesuree reste"
    assert not list(studio["moments"].glob("*.wav"))
    assert not list(studio["media"].glob("voice*"))


def test_liste_et_detail_restituent_l_analyse(studio):
    analysis_id = _analyse(studio)
    listing = studio["client"].get("/api/moments").json()["analyses"]
    assert [item["id"] for item in listing] == [analysis_id]
    summary = listing[0]
    assert summary["source_title"] == "episode.mp4"
    assert summary["segments"] == len(SEGMENTS) and summary["moment_count"] > 0
    assert summary["duration"] == SOURCE_DURATION and summary["best_score"] > 0
    detail = studio["client"].get(f"/api/moments/{analysis_id}")
    assert detail.status_code == 200
    record = detail.json()
    for moment in record["moments"]:
        assert moment["start"] >= 0.0 and moment["end"] <= SOURCE_DURATION + 0.01
        assert moment["score"] > 0 and moment["reasons"]
        for cue in moment["cues"]:
            assert moment["start"] - 0.01 <= cue["raw_start"] <= cue["raw_end"] <= moment["end"] + 0.01
    assert studio["client"].get("/api/moments/0123456789ab").status_code == 404


def test_suppression_emporte_le_dossier_de_travail(studio):
    analysis_id = _analyse(studio)
    res = studio["client"].delete(f"/api/moments/{analysis_id}")
    assert res.status_code == 200 and res.json()["deleted"] == analysis_id
    assert not (studio["moments"] / f"{analysis_id}.json").exists()
    assert not (studio["moments"] / "work" / analysis_id).exists()
    assert studio["client"].get(f"/api/moments/{analysis_id}").status_code == 404


# --- recompute -----------------------------------------------------------------


def test_recompute_relance_la_detection_sans_nouvel_appel_asr(studio):
    analysis_id = _analyse(studio)
    assert len(studio["calls"]) == 1, "l'analyse a deja paye la transcription"
    res = studio["client"].post(f"/api/moments/{analysis_id}/recompute",
                                json={"min_seconds": 1.0, "max_seconds": 2.0, "top": 1})
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["moments"]) == 1 and body["energy_used"] is True
    assert len(studio["calls"]) == 1, "recompute ne relance pas la reconnaissance vocale"
    stored = json.loads((studio["moments"] / f"{analysis_id}.json").read_text(encoding="utf-8"))
    assert stored["detect"]["max_seconds"] == 2.0 and len(stored["moments"]) == 1
    assert stored["transcript"]["segments"], "la transcription stockee reste intacte"


# --- generation ----------------------------------------------------------------


def test_le_clic_genere_projet_srt_voix_miniature_et_metadonnees(studio):
    analysis_id = _analyse(studio)
    record = studio["client"].get(f"/api/moments/{analysis_id}").json()
    moment = record["moments"][0]

    res = studio["client"].post(f"/api/moments/{analysis_id}/generate",
                               json={"moment_id": moment["id"], "handle": "@atelier",
                                     "source_title": "Episode 12"})
    assert res.status_code == 200, res.text
    body = res.json()

    target = Path(body["project_path"])
    assert target.parent == studio["projects"] and target.suffix == ".json"
    srt_path = Path(body["srt_path"])
    assert body["srt_available"] is True and srt_path.is_file() and srt_path.stem == target.stem

    project = json.loads(target.read_text(encoding="utf-8"))
    errors, _warnings = validation.validate_project_v2(project)
    assert errors == [], errors
    assert project["version"] == schema.SCHEMA_VERSION_V2
    assert len(project["content"]["scenes"]) == body["cues"] == len(body["timeline"])

    # la piste vocale est l'extrait reel de la source, importe comme media du studio
    assert body["voice_ref"].startswith("media://")
    voice_file = next(studio["media"].glob(f"{body['voice_ref'][8:]}.*"))
    assert voice_file.suffix == ".wav" and voice_file.stat().st_size > 44

    # miniature extraite de la vraie video, elle aussi importee comme media
    assert body["thumbnail_ref"].startswith("media://")
    assert next(studio["media"].glob(f"{body['thumbnail_ref'][8:]}.*")).suffix == ".png"

    publish = body["publish"]
    assert publish["title"] and publish["hashtags"][0] == "#atelier"
    assert "Episode 12" in publish["description"] and "@atelier" in publish["description"]
    assert publish["moment_id"] == moment["id"]
    assert abs(publish["start"] - moment["start"]) < 0.01

    # un fond video ne serait pas applique : le projet est ecrit sans fond, et la
    # raison est dite a l'utilisateur
    assert any("Fond v" in w for w in body["warnings"]), body["warnings"]
    for scene in project["content"]["scenes"]:
        assert scene["background"]["media"] == ""

    # la file SQLite du lot n'a rien a faire dans ce parcours
    assert not queue_mod.DB_PATH.exists()


def test_le_srt_du_projet_retrouve_les_bornes_de_l_asr(studio):
    analysis_id = _analyse(studio)
    record = studio["client"].get(f"/api/moments/{analysis_id}").json()
    moment = record["moments"][0]
    body = studio["client"].post(f"/api/moments/{analysis_id}/generate",
                               json={"moment_id": moment["id"]}).json()
    project = json.loads(Path(body["project_path"]).read_text(encoding="utf-8"))
    fps = project["export"]["fps"]

    cues = delivery.srt_cues(project)
    assert 0 < len(cues) <= len(moment["cues"]), (len(cues), len(moment["cues"]))
    for cue in cues:
        assert any(abs(cue["start_frame"] - round(c["start"] * fps)) <= 1 for c in moment["cues"]), cue
        assert any(abs(cue["end_frame"] - round(c["end"] * fps)) <= 1 for c in moment["cues"]), cue
    assert cues[0]["start_frame"] == 0, "frame 0 de la composition = instant de depart du moment"
    assert cues[-1]["end_frame"] <= round(moment["duration"] * fps) + 1
    text = Path(body["srt_path"]).read_text(encoding="utf-8")
    assert text.count("-->") == len(cues) and text.splitlines()[0] == "1"


def test_generate_refuse_ecraser_sans_demande_explicite(studio):
    analysis_id = _analyse(studio)
    moment_id = studio["client"].get(f"/api/moments/{analysis_id}").json()["moments"][0]["id"]
    payload = {"moment_id": moment_id}
    first = studio["client"].post(f"/api/moments/{analysis_id}/generate", json=payload)
    assert first.status_code == 200
    name = Path(first.json()["project_path"]).name
    second = studio["client"].post(f"/api/moments/{analysis_id}/generate", json=payload)
    assert second.status_code == 409 and name in second.text
    third = studio["client"].post(f"/api/moments/{analysis_id}/generate",
                                 json={**payload, "overwrite": True})
    assert third.status_code == 200 and Path(third.json()["project_path"]).name == name


def test_le_pack_de_marque_ne_s_applique_que_si_il_est_designe(studio):
    saved = studio["client"].post("/api/brands", json={"pack": {
        "label": "Atelier Runa",
        "theme": {"accent_color": "#C4F1BE", "palette_id": "vert"},
        "signature": {"handle": "@atelier.runa"},
    }})
    assert saved.status_code == 200, saved.text
    brand_id = saved.json()["brand"]["id"]

    analysis_id = _analyse(studio)
    moment_id = studio["client"].get(f"/api/moments/{analysis_id}").json()["moments"][0]["id"]
    sans = studio["client"].post(f"/api/moments/{analysis_id}/generate",
                               json={"moment_id": moment_id}).json()
    assert json.loads(Path(sans["project_path"]).read_text(encoding="utf-8"))["theme"] == schema.default_theme()
    assert sans["publish"]["title"] == moments.title_from(
        studio["client"].get(f"/api/moments/{analysis_id}").json()["moments"][0])

    avec = studio["client"].post(f"/api/moments/{analysis_id}/generate",
                               json={"moment_id": moment_id, "brand_id": brand_id,
                                     "overwrite": True}).json()
    project = json.loads(Path(avec["project_path"]).read_text(encoding="utf-8"))
    assert project["theme"]["accent_color"] == "#C4F1BE"
    assert project["content"]["signature"]["handle"] == "@atelier.runa"
    assert "Atelier Runa" in avec["publish"]["title"]
    assert "Atelier Runa" in avec["publish"]["description"]


def test_une_source_sans_image_ne_bloque_pas_la_generation(studio):
    """Un podcast n'a aucune frame a capter : la miniature est annoncee, pas demandee
       a OpenCV — et le projet sort quand meme."""
    analysis_id = _analyse(studio, source="media://podcast")
    moment_id = studio["client"].get(f"/api/moments/{analysis_id}").json()["moments"][0]["id"]
    res = studio["client"].post(f"/api/moments/{analysis_id}/generate", json={"moment_id": moment_id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["thumbnail_ref"] == ""
    assert any("Miniature indisponible" in w for w in body["warnings"]), body["warnings"]
    assert body["voice_ref"].startswith("media://")
    assert Path(body["project_path"]).is_file()
    assert not any("Fond v" in w for w in body["warnings"])


def test_une_source_son_audio_ne_produit_aucune_analyse(studio):
    """Pas de piste ecoutable = rien a transcrire : le job le dit et n'crit rien."""
    res = studio["client"].post("/api/moments/analyze",
                               json={"source": "media://muet", "min_seconds": 1.0,
                                     "max_seconds": 4.0, "top": 3})
    assert res.status_code == 200
    job = _finished(studio["client"], res.json()["job_id"])
    assert job["status"] == "error"
    assert "piste audio" in job["error"], job["error"]
    assert list(studio["moments"].glob("*.json")) == [], "aucune analyse a demi ecrite"
    assert list(studio["projects"].iterdir()) == []


def test_un_decoupage_vocal_rate_ne_perd_pas_le_moment(studio, monkeypatch):
    """Le decoupe audio est le maillon qui depend du codec de la source : s'il echoue,
       le projet sort quand meme, muet et avec l'avertissement ecrit."""
    def refuse(*args, **kwargs):
        raise asr.AsrError("Decoupe audio impossible (episode.mp4) : codec non supporte")

    monkeypatch.setattr(asr, "cut_wav", refuse)
    analysis_id = _analyse(studio)
    moment_id = studio["client"].get(f"/api/moments/{analysis_id}").json()["moments"][0]["id"]
    body = studio["client"].post(f"/api/moments/{analysis_id}/generate",
                                json={"moment_id": moment_id}).json()
    assert body["voice_ref"] == "", "aucun son a decouper : la piste reste vide"
    assert any("Extrait vocal non importe" in w for w in body["warnings"]), body["warnings"]
    assert any("muet" in w for w in body["warnings"])
    project = json.loads(Path(body["project_path"]).read_text(encoding="utf-8"))
    assert project["audio"]["enabled"] is False and project["audio"]["voice"] == ""
    assert body["thumbnail_ref"].startswith("media://"), "la miniature reste disponible"


# --- clefs ---------------------------------------------------------------------


def test_la_cle_de_clips_n_est_reusee_que_sur_demande_explicite(studio):
    _settings(studio, groq_api_key=CLIPS_KEY)
    res = studio["client"].post("/api/moments/analyze",
                               json={"source": "media://episode", "provider": "groq"})
    assert res.status_code == 400, res.text
    assert "cle" in res.text.lower() and CLIPS_KEY not in res.text
    assert studio["calls"] == [], "aucune transcription lancee sans cle designee"

    analysis_id = _analyse(studio, provider="groq", api_key_source="clips")
    assert studio["calls"][0]["api_key"] == CLIPS_KEY
    assert studio["calls"][0]["provider"] == "groq"

    _settings(studio, groq_api_key=CLIPS_KEY, asr_groq_api_key=ASR_KEY)
    _analyse(studio, source="media://episode", provider="groq")
    assert studio["calls"][-1]["api_key"] == ASR_KEY, \
        "la cle dediee a la transcription passe avant celle de Clips"

    dumped = json.dumps([json.loads(p.read_text(encoding="utf-8"))
                         for p in studio["moments"].glob("*.json")])
    assert ASR_KEY not in dumped and CLIPS_KEY not in dumped, "aucune cle n'est ecrite dans une analyse"


def test_reglages_asr_ecrivent_la_cle_et_ne_la_redonnent_jamais(studio):
    client = studio["client"]
    res = client.post("/api/settings",
                     json={"asr": {"provider": "groq", "groq_api_key": ASR_KEY, "language": "fr"}})
    assert res.status_code == 200, res.text
    block = res.json()["asr"]
    assert block["provider"] == "groq" and block["language"] == "fr"
    assert block["key_configured"] is True and ASR_KEY not in res.text
    assert json.loads(studio["settings"].read_text(encoding="utf-8"))["asr_groq_api_key"] == ASR_KEY

    # la cle dedies est la voie par defaut : rien ne passe par la cle de Clips
    _analyse(studio, provider="groq")
    assert studio["calls"][-1]["api_key"] == ASR_KEY

    assert client.post("/api/settings", json={"asr": {"provider": "openai"}}).status_code == 400
    assert client.post("/api/settings", json={"asr": {"groq_model": "whisper-plus-ultra"}}).status_code == 400

    cleared = client.post("/api/settings", json={"asr": {"clear_key": True}}).json()["asr"]
    assert cleared["key_configured"] is False
    assert json.loads(studio["settings"].read_text(encoding="utf-8"))["asr_groq_api_key"] == ""


def test_un_whisper_local_ne_demande_aucune_cle(studio):
    analysis_id = _analyse(studio, provider="local")
    assert studio["calls"][0]["provider"] == "local" and studio["calls"][0]["api_key"] == ""
    assert studio["client"].get(f"/api/moments/{analysis_id}").status_code == 200


def test_un_modele_inconnu_est_refuse_avant_appel(studio):
    _settings(studio, groq_api_key=CLIPS_KEY)
    res = studio["client"].post("/api/moments/analyze",
                               json={"source": "media://episode", "provider": "groq",
                                     "api_key_source": "clips", "model": "whisper-plus-ultra"})
    assert res.status_code == 400 and "Modele Groq inconnu" in res.text, res.text
    assert studio["calls"] == []


# --- frontieres ----------------------------------------------------------------


def test_la_source_est_toujours_un_media_du_studio(studio):
    client = studio["client"]
    for source in ("", "C:\\temp\\episode.mp4", "media://../settings", "media://inconnu01",
                   "file:///C:/Windows"):
        res = client.post("/api/moments/analyze", json={"source": source})
        if source == "media://inconnu01":
            assert res.status_code == 404, source
        else:
            assert res.status_code == 400, (source, res.text)
    assert studio["calls"] == []


def test_un_identifiant_invalide_ne_touche_pas_le_disque(studio):
    client = studio["client"]
    # un separateur encode ne correspond a aucun identifiant : la requete meurt avant
    # la route des moments, donc avant la moindre ouverture de fichier
    for traversal in ("..%2F..%2Fserver%2Fsettings", "a%2Fb"):
        res = client.get(f"/api/moments/{traversal}")
        assert res.status_code == 404 and "inconnue" in res.text, (traversal, res.text)
    # un identifiant alphanumerique seulement est admis a lire, et il est then borne
    for bad in ("x.json", "bad-id", "m1 2"):
        res = client.get(f"/api/moments/{bad}")
        assert res.status_code == 400, (bad, res.status_code, res.text)
        assert "Chemin hors" not in res.text, "la route rejette avant toute ouverture de fichier"
    analysis_id = _analyse(studio)
    assert client.post(f"/api/moments/{analysis_id}/generate",
                       json={"moment_id": "../m1"}).status_code == 400
    assert client.post(f"/api/moments/{analysis_id}/generate",
                       json={"moment_id": ""}).status_code == 400


def test_un_post_d_une_autre_origine_est_refuse(studio):
    res = studio["client"].post("/api/moments/analyze", json={"source": "media://episode"},
                               headers={"Origin": "http://evil.example.com"})
    assert res.status_code == 403 and "rigine" in res.text
    assert studio["calls"] == []


def test_une_analyse_introuvable_le_die_clairement(studio):
    assert studio["client"].post("/api/moments/0123456789ab/recompute", json={}).status_code == 404
    assert studio["client"].post("/api/moments/0123456789ab/generate",
                                json={"moment_id": "m1"}).status_code == 404
    analysis_id = _analyse(studio)
    assert studio["client"].post(f"/api/moments/{analysis_id}/generate",
                                json={"moment_id": "m42"}).status_code == 404
