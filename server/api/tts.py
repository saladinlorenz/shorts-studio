"""Routes de synthese vocale (TTS) : etat, telechargement a la demande, generation.

Meme principe que les moments forts et l'export :

- ``/status`` ne fait que detecter (moteurs installes, voix telechargees) ;
- ``/download`` lance un job et ne renvoie qu'un identifiant : aucun fichier n'est
  rapatrie sans ce clic explicite ;
- ``/generate`` synthetise un WAV, l'importe en ``media://<id>`` et renvoie la
  reference. C'est au frontend d'assigner cette reference a ``project.audio.voice``
  (aucune ecriture dans un projet ici).

Aucun chemin Windows ne circule vers le client : seule la reference ``media://``
et l'URL ``/api/media/<id>`` sortent. Les voix et leurs URL sont celles du catalogue
verifie de ``shortvideos/tts.py``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shortvideos import tts as tts_mod

from .. import media as media_mod
from ..jobs import Job, create_job, raise_if_cancelled
from ..security import TTS_MODELS_DIR

router = APIRouter(prefix="/api/tts", tags=["tts"])

MAX_TEXT = 5000
MIN_SPEED, MAX_SPEED = 0.5, 2.0


class DownloadPayload(BaseModel):
    voice_id: str = ""


class GeneratePayload(BaseModel):
    text: str = ""
    voice_id: str = ""
    speed: float = 1.0


def _check_voice(voice_id: str) -> dict:
    try:
        return tts_mod.voice_by_id(voice_id)
    except tts_mod.TtsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
def status() -> dict:
    """Moteurs disponibles + catalogue de voix (telechargee / prete), sans rien installer."""
    return tts_mod.status(TTS_MODELS_DIR)


@router.post("/download")
def download(payload: DownloadPayload) -> dict:
    """Le clic qui rapatrie les fichiers d'une voix. Job annulable, rien d'automatique."""
    voice = _check_voice(payload.voice_id)

    def work(job: Job) -> dict:
        return tts_mod.download_voice(
            voice["id"], TTS_MODELS_DIR,
            progress=lambda c, t, m: job.set_progress(c, t, m),
            cancel=lambda: raise_if_cancelled(job),
        )

    job = create_job("tts-download", work)
    return {"job_id": job.id, "status": job.status}


@router.post("/generate")
def generate(payload: GeneratePayload) -> dict:
    """Synthetise la voix off puis l'importe en media. Ne touche a aucun projet."""
    voice = _check_voice(payload.voice_id)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texte vide : rien a synthetiser.")
    if len(text) > MAX_TEXT:
        raise HTTPException(status_code=400, detail=f"Texte trop long (max {MAX_TEXT} caracteres).")
    speed = float(payload.speed)
    if not (MIN_SPEED <= speed <= MAX_SPEED):
        raise HTTPException(status_code=400,
                            detail=f"Vitesse hors plage ({MIN_SPEED} a {MAX_SPEED}).")

    def work(job: Job) -> dict:
        wav = TTS_MODELS_DIR / f"_synth_{uuid.uuid4().hex[:12]}.wav"
        try:
            info = tts_mod.synthesize(
                text, voice["id"], TTS_MODELS_DIR, wav, speed=speed,
                progress=lambda c, t, m: job.set_progress(c * 0.8, 1.0, m),
                cancel=lambda: raise_if_cancelled(job),
            )
            raise_if_cancelled(job)
            job.set_progress(0.85, 1.0, "Import de la voix off…")
            media_id = media_mod.import_file_to_media(
                wav, source=f"Synthese vocale ({info['engine']} : {voice['label']})",
            )
            # le WAV temporaire a ete copie dans media/ : on ne garde pas le doublon,
            # et aucun chemin disque ne sort vers le client
            return {
                "media_id": media_id,
                "ref": f"media://{media_id}",
                "url": f"/api/media/{media_id}",
                "duration": info["duration"],
                "sample_rate": info["sample_rate"],
                "voice": info["voice"],
                "engine": info["engine"],
            }
        finally:
            wav.unlink(missing_ok=True)
            wav.with_name(wav.name + ".part").unlink(missing_ok=True)

    job = create_job("tts-generate", work)
    return {"job_id": job.id, "status": job.status}