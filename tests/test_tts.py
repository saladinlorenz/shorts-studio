"""Synthese vocale : detection, catalogue, synthese et routes, sans reseau ni modele.

Les moteurs sont simules (aucun poids telecharge, aucun paquet requis pour faire
tourner ces tests) mais le WAV produit est reel : l'orchestration (ecriture
atomique, menage, duree, import media) est exercee sur du vrai son.

Lois verifiees ici :

- rien n'est telecharge ni synthetise sans un clic (jobs explicites) ;
- aucune cle ni chemin Windows ne sort vers le client : seule une ref ``media://`` ;
- la generation n'ecrit dans aucun projet : elle importe un media, c'est le
  frontend qui assigne la reference (geste annulable) ;
- une voie fermee (moteur absent, voix non telechargee) dit pourquoi.
"""
from __future__ import annotations

import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import media as media_mod
from server import mediacache
from server.api import tts as tts_api
from server.app import app
from shortvideos import tts


def _force_engines(monkeypatch, available=True):
    reason = "" if available else "Paquet absent : installez requirements.txt."
    monkeypatch.setattr(tts, "engine_state", lambda: {
        "piper": {"available": available, "reason": reason},
        "kokoro": {"available": available, "reason": reason},
    })


def _fake_voice_files(models_dir: Path, voice_id="piper-fr-siwis"):
    voice = tts.voice_by_id(voice_id)
    models_dir.mkdir(parents=True, exist_ok=True)
    for item in voice["files"]:
        (models_dir / item["filename"]).write_bytes(b"fake-model")


def _fake_engine(voice, text, models_dir, tmp, speed, cancel):
    """Ecrit un vrai WAV court : l'orchestration est exercee sur du son reel."""
    if cancel is not None:
        cancel()
    rate = 22050
    count = int(0.4 * rate)
    tts._write_wav_frames(tmp, channels=1, sample_width=2, sample_rate=rate,
                          frames=b"\x00\x10" * count)
    return rate, count


@pytest.fixture()
def synth(tmp_path, monkeypatch):
    _force_engines(monkeypatch)
    models_dir = tmp_path / "tts_models"
    _fake_voice_files(models_dir)
    monkeypatch.setattr(tts, "_synthesize_piper", _fake_engine)
    monkeypatch.setattr(tts, "_synthesize_kokoro", _fake_engine)
    return {"models": models_dir, "tmp": tmp_path}


# --- detection et catalogue ----------------------------------------------------


def test_engine_state_decrit_la_machine_sans_rien_installer():
    state = tts.engine_state()
    assert set(state) == {"piper", "kokoro"}
    for engine in state.values():
        assert set(engine) == {"available", "reason"}
        if not engine["available"]:
            assert engine["reason"], "une voie fermee doit dire pourquoi"


def test_catalogue_couvre_le_francais_des_deux_moteurs():
    french = [v for v in tts.VOICES if v["language"] == "fr"]
    assert {v["engine"] for v in french} == {"piper", "kokoro"}
    assert tts.voice_by_id("piper-fr-siwis")["engine"] == "piper"
    with pytest.raises(tts.TtsError):
        tts.voice_by_id("inconnue")


def test_status_marque_telechargee_et_prete(tmp_path, monkeypatch):
    _force_engines(monkeypatch)
    models_dir = tmp_path / "m"
    _fake_voice_files(models_dir)
    body = tts.status(models_dir)
    siwis = next(v for v in body["voices"] if v["id"] == "piper-fr-siwis")
    tom = next(v for v in body["voices"] if v["id"] == "piper-fr-tom")
    assert siwis["downloaded"] is True and siwis["ready"] is True
    assert tom["downloaded"] is False and tom["ready"] is False
    # moteur absent : meme voix presente, elle n'est pas prete
    _force_engines(monkeypatch, available=False)
    body = tts.status(models_dir)
    siwis = next(v for v in body["voices"] if v["id"] == "piper-fr-siwis")
    assert siwis["downloaded"] is True and siwis["ready"] is False


# --- orchestration de la synthese ----------------------------------------------


def test_synthesize_refuse_un_texte_vide(synth):
    with pytest.raises(tts.TtsError, match="Texte vide"):
        tts.synthesize("   ", "piper-fr-siwis", synth["models"], synth["tmp"] / "x.wav")


def test_synthesize_refuse_une_vitesse_invalide(synth):
    with pytest.raises(tts.TtsError, match="Vitesse"):
        tts.synthesize("Bonjour", "piper-fr-siwis", synth["models"], synth["tmp"] / "x.wav", speed=0)


def test_synthesize_refuse_une_voix_non_telechargee(tmp_path, monkeypatch):
    _force_engines(monkeypatch)
    with pytest.raises(tts.TtsError, match="non telechargee"):
        tts.synthesize("Bonjour", "piper-fr-siwis", tmp_path / "vide", tmp_path / "x.wav")


def test_synthesize_refuse_si_moteur_absent(tmp_path, monkeypatch):
    _force_engines(monkeypatch, available=False)
    _fake_voice_files(tmp_path / "m")
    with pytest.raises(tts.TtsError, match="requirements.txt"):
        tts.synthesize("Bonjour", "piper-fr-siwis", tmp_path / "m", tmp_path / "x.wav")


def test_synthesize_produit_un_wav_reel_et_nettoie_le_part(synth):
    out = synth["tmp"] / "voice.wav"
    info = tts.synthesize("Bonjour, voix off locale.", "piper-fr-siwis", synth["models"], out)
    assert out.is_file()
    assert not out.with_name(out.name + ".part").exists()
    assert info["sample_rate"] == 22050 and info["duration"] == pytest.approx(0.4, abs=0.01)
    assert info["voice"] == "piper-fr-siwis" and info["engine"] == "piper"
    with wave.open(str(out), "rb") as handle:
        assert handle.getnchannels() == 1 and handle.getsampwidth() == 2
        assert handle.getnframes() > 0


def test_synthesize_annulee_ne_laisse_aucun_fichier(synth, monkeypatch):
    class Cancelled(Exception):
        pass

    def cancelling_engine(voice, text, models_dir, tmp, speed, cancel):
        tmp.write_bytes(b"partial")
        raise Cancelled()

    monkeypatch.setattr(tts, "_synthesize_piper", cancelling_engine)
    out = synth["tmp"] / "voice.wav"
    with pytest.raises(Cancelled):
        tts.synthesize("Bonjour", "piper-fr-siwis", synth["models"], out)
    assert not out.exists()
    assert not out.with_name(out.name + ".part").exists()


# --- telechargement a la demande ------------------------------------------------


def test_download_ecrit_puis_saute_les_fichiers_presents(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, dest, *, progress=None, cancel=None):
        calls.append(dest.name)
        dest.write_bytes(b"model")
        if progress:
            progress(5, 5, "ok")

    monkeypatch.setattr(tts, "_download_file", fake_download)
    models_dir = tmp_path / "m"
    first = tts.download_voice("piper-fr-siwis", models_dir)
    assert first["downloaded"] is True
    assert sorted(calls) == ["fr_FR-siwis-medium.onnx", "fr_FR-siwis-medium.onnx.json"]
    calls.clear()
    tts.download_voice("piper-fr-siwis", models_dir)
    assert calls == [], "rien n'est re-telecharge quand les fichiers sont la"


def test_download_rate_ne_laisse_pas_de_part(tmp_path, monkeypatch):
    class _CutResponse:
        headers = {"Content-Length": "100"}

        def __init__(self):
            self.reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            self.reads += 1
            if self.reads == 1:
                return b"x" * 50
            raise OSError("coupure reseau")

    monkeypatch.setattr(tts, "urlopen", lambda request, timeout: _CutResponse())
    models_dir = tmp_path / "m"
    with pytest.raises(tts.TtsError, match="Telechargement impossible"):
        tts.download_voice("piper-fr-siwis", models_dir)
    assert not list(models_dir.glob("*.part"))
    assert not (models_dir / "fr_FR-siwis-medium.onnx").exists()


# --- routes HTTP ----------------------------------------------------------------


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    models_dir = tmp_path / "tts_models"
    _fake_voice_files(models_dir)
    _force_engines(monkeypatch)
    monkeypatch.setattr(tts, "_synthesize_piper", _fake_engine)
    monkeypatch.setattr(tts, "_synthesize_kokoro", _fake_engine)
    monkeypatch.setattr(media_mod, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(media_mod, "PROVENANCE_DIR", media_dir / "provenance")
    monkeypatch.setattr(mediacache, "ensure_cached", lambda media_id: None)
    monkeypatch.setattr(tts_api, "TTS_MODELS_DIR", models_dir)
    return {"client": TestClient(app), "media": media_dir, "models": models_dir, "tmp": tmp_path}


def _finished(client, job_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/api/jobs/{job_id}").json()
        if snap["status"] != "running":
            return snap
        time.sleep(0.03)
    raise AssertionError(f"job {job_id} jamais termine")


def test_status_endpoint_decrit_moteurs_et_voix(studio):
    res = studio["client"].get("/api/tts/status")
    assert res.status_code == 200
    body = res.json()
    assert set(body["engines"]) == {"piper", "kokoro"}
    siwis = next(v for v in body["voices"] if v["id"] == "piper-fr-siwis")
    assert siwis["ready"] is True


def test_download_job_rapatrie_la_voix(studio, monkeypatch):
    def fake_download(url, dest, *, progress=None, cancel=None):
        dest.write_bytes(b"model")

    monkeypatch.setattr(tts, "_download_file", fake_download)
    res = studio["client"].post("/api/tts/download", json={"voice_id": "piper-fr-tom"})
    assert res.status_code == 200
    job = _finished(studio["client"], res.json()["job_id"])
    assert job["status"] == "done" and job["kind"] == "tts-download"
    assert job["result"]["downloaded"] is True
    assert (studio["models"] / "fr_FR-tom-medium.onnx").is_file()


def test_generate_importe_un_media_et_rend_une_reference(studio):
    res = studio["client"].post("/api/tts/generate",
                                json={"text": "Bonjour, voix off.", "voice_id": "piper-fr-siwis"})
    assert res.status_code == 200
    job = _finished(studio["client"], res.json()["job_id"])
    assert job["status"] == "done", job
    result = job["result"]
    assert result["ref"].startswith("media://")
    assert result["url"] == f"/api/media/{result['media_id']}"
    assert result["duration"] > 0 and result["engine"] == "piper"
    assert "path" not in result, "aucun chemin Windows ne sort vers le client"
    # le media est reellement servi
    served = studio["client"].get(result["url"])
    assert served.status_code == 200 and len(served.content) > 44
    # le WAV temporaire a ete range : seul le media importe reste
    assert not list(studio["models"].glob("_synth_*"))
    voice_file = next(studio["media"].glob(f"{result['media_id']}.*"))
    assert voice_file.suffix == ".wav"
    assert (studio["media"] / "provenance" / f"{result['media_id']}.json").is_file()


def test_generate_refuse_une_voix_non_telechargee(studio):
    # les voix Kokoro partagent un modele absent du fixture : la voie est fermee
    res = studio["client"].post("/api/tts/generate",
                                json={"text": "Bonjour", "voice_id": "kokoro-fr-siwis"})
    assert res.status_code == 200
    job = _finished(studio["client"], res.json()["job_id"])
    assert job["status"] == "error"
    assert "non telechargee" in job["error"]


def test_generate_valide_le_payload_avant_le_job(studio):
    client = studio["client"]
    assert client.post("/api/tts/generate", json={"text": "", "voice_id": "piper-fr-siwis"}).status_code == 400
    assert client.post("/api/tts/generate", json={"text": "x", "voice_id": "inconnue"}).status_code == 400
    assert client.post("/api/tts/generate", json={"text": "x", "voice_id": "piper-fr-siwis", "speed": 9}).status_code == 400
    assert client.post("/api/tts/generate", json={"text": "x" * 6000, "voice_id": "piper-fr-siwis"}).status_code == 400
    assert client.post("/api/tts/download", json={"voice_id": "inconnue"}).status_code == 400


def test_un_post_d_une_autre_origine_est_refuse(studio):
    res = studio["client"].post("/api/tts/generate",
                                json={"text": "Bonjour", "voice_id": "piper-fr-siwis"},
                                headers={"Origin": "http://evil.example.com"})
    assert res.status_code == 403