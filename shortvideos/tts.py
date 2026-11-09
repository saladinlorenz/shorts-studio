"""Synthese vocale locale (TTS), sans service cloud ni cle API.

Deux moteurs libres, detectes comme dans ``asr.py`` (le module n'installe rien) :

- ``piper`` (paquet ``piper-tts``, code GPL-3.0) — voix legères (~20-60 Mo),
  multilingues ; espeak-ng est embarque, le francais marche sans reglage. Une voix
  = un fichier ``.onnx`` + son ``.onnx.json``, telecharges a la demande.
- ``kokoro`` (paquet ``kokoro-onnx``, code MIT / modele Apache-2.0) — un modele
  partage (~310 Mo) + un fichier de voix, plusieurs langues et timbres.

Le principe du produit est respecte : rien n'est telecharge ni synthetise sans un
clic. Ce module ne fait que detecter, lister, telecharger (a la demande) et
produire un WAV ; c'est la couche serveur qui importe le WAV en ``media://<id>``
et l'assigne au projet. Aucun chemin Windows ne sort d'ici vers le frontend.

Les voix et les URL sont verifiees (HuggingFace ``rhasspy/piper-voices`` pour Piper,
release ``model-files-v1.1`` de kokoro-onnx pour Kokoro). Les licences des voix
individuelles ne sont pas affirmées ici : la provenance du media les note
« inconnue » tant qu'elles ne sont pas declarees, comme tout autre import.
"""
from __future__ import annotations

import math
import wave
from pathlib import Path
from urllib.request import Request, urlopen

# Cadence de sortie des moteurs (Hz). Piper depend de la voix (22050 en general),
# Kokoro sort toujours en 24000 ; on relit la vraie valeur produite au rendu.
PIPER_SAMPLE_RATE = 22050
KOKORO_SAMPLE_RATE = 24000

_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
_KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
_KOKORO_FILES = [
    {"url": f"{_KOKORO_RELEASE}/kokoro-v1.0.onnx", "filename": "kokoro-v1.0.onnx"},
    {"url": f"{_KOKORO_RELEASE}/voices-v1.0.bin", "filename": "voices-v1.0.bin"},
]


def _piper_voice(engine_voice: str, lang_family: str, lang_code: str,
                 name: str, quality: str) -> list[dict]:
    base = f"{_HF}/{lang_family}/{lang_code}/{name}/{quality}/{engine_voice}"
    return [
        {"url": f"{base}.onnx?download=true", "filename": f"{engine_voice}.onnx"},
        {"url": f"{base}.onnx.json?download=true", "filename": f"{engine_voice}.onnx.json"},
    ]


# Catalogue restreint et verifie : le francais d'abord (utilisateur francophone),
# puis l'anglais pour l'ouverture multilingue. Chaque entree porte les fichiers a
# telecharger ; les voix Kokoro partagent le meme modele (un seul download).
VOICES: list[dict] = [
    {
        "id": "piper-fr-siwis", "engine": "piper", "label": "Siwis · français (femme)",
        "language": "fr", "gender": "female", "engine_voice": "fr_FR-siwis-medium",
        "lang_code": "", "files": _piper_voice("fr_FR-siwis-medium", "fr", "fr_FR", "siwis", "medium"),
    },
    {
        "id": "piper-fr-tom", "engine": "piper", "label": "Tom · français (homme)",
        "language": "fr", "gender": "male", "engine_voice": "fr_FR-tom-medium",
        "lang_code": "", "files": _piper_voice("fr_FR-tom-medium", "fr", "fr_FR", "tom", "medium"),
    },
    {
        "id": "piper-en-lessac", "engine": "piper", "label": "Lessac · anglais (femme)",
        "language": "en", "gender": "female", "engine_voice": "en_US-lessac-medium",
        "lang_code": "", "files": _piper_voice("en_US-lessac-medium", "en", "en_US", "lessac", "medium"),
    },
    {
        "id": "piper-en-ryan", "engine": "piper", "label": "Ryan · anglais (homme)",
        "language": "en", "gender": "male", "engine_voice": "en_US-ryan-medium",
        "lang_code": "", "files": _piper_voice("en_US-ryan-medium", "en", "en_US", "ryan", "medium"),
    },
    {
        "id": "kokoro-fr-siwis", "engine": "kokoro", "label": "Siwis · français (femme)",
        "language": "fr", "gender": "female", "engine_voice": "ff_siwis",
        "lang_code": "fr-fr", "files": _KOKORO_FILES,
    },
    {
        "id": "kokoro-en-heart", "engine": "kokoro", "label": "Heart · anglais US (femme)",
        "language": "en", "gender": "female", "engine_voice": "af_heart",
        "lang_code": "en-us", "files": _KOKORO_FILES,
    },
    {
        "id": "kokoro-en-michael", "engine": "kokoro", "label": "Michael · anglais US (homme)",
        "language": "en", "gender": "male", "engine_voice": "am_michael",
        "lang_code": "en-us", "files": _KOKORO_FILES,
    },
    {
        "id": "kokoro-en-emma", "engine": "kokoro", "label": "Emma · anglais UK (femme)",
        "language": "en", "gender": "female", "engine_voice": "bf_emma",
        "lang_code": "en-gb", "files": _KOKORO_FILES,
    },
]


class TtsError(RuntimeError):
    """Synthese impossible : raison humaine, jamais un stacktrace nu."""


def voice_by_id(voice_id: str) -> dict:
    voice = next((v for v in VOICES if v["id"] == voice_id), None)
    if voice is None:
        raise TtsError(f"Voix inconnue : {voice_id!r}.")
    return voice


def engine_state() -> dict:
    """Detecte les paquets deja installes. N'installe rien : sans paquet, le
    moteur repond « indisponible » avec la raison (meme principe que asr.py)."""
    state: dict = {}
    try:
        import piper  # noqa: F401
        state["piper"] = {"available": True, "reason": ""}
    except Exception as exc:
        state["piper"] = {"available": False,
                          "reason": f"Paquet piper-tts absent ({exc}). Installez requirements.txt."}
    try:
        import kokoro_onnx  # noqa: F401
        state["kokoro"] = {"available": True, "reason": ""}
    except Exception as exc:
        state["kokoro"] = {"available": False,
                           "reason": f"Paquet kokoro-onnx absent ({exc}). Installez requirements.txt."}
    return state


def _files_present(voice: dict, models_dir: Path) -> bool:
    return all((models_dir / f["filename"]).is_file() for f in voice["files"])


def status(models_dir: Path) -> dict:
    """Etat reel : moteurs disponibles + catalogue, chaque voix marquee
    « telechargee » si ses fichiers sont la, « prete » si le moteur suit."""
    engines = engine_state()
    models_dir = Path(models_dir)
    voices = []
    for voice in VOICES:
        downloaded = _files_present(voice, models_dir)
        engine = engines[voice["engine"]]
        voices.append({
            "id": voice["id"], "engine": voice["engine"], "label": voice["label"],
            "language": voice["language"], "gender": voice["gender"],
            "downloaded": downloaded,
            "ready": bool(engine["available"] and downloaded),
            "approx_mb": _approx_mb(voice),
        })
    return {"engines": engines, "voices": voices}


def _approx_mb(voice: dict) -> int:
    if voice["engine"] == "kokoro":
        return 330  # modele + voix partages
    return 60  # voix Piper medium (.onnx + config)


# --- Telechargement a la demande ------------------------------------------------


def _download_file(url: str, dest: Path, *, progress=None, cancel=None) -> None:
    """Telecharge en streamant, progression + annulation, ecriture atomique.

    ``.part`` puis remplacement : un download coupe ne laisse jamais un fichier
    incomplet pris pour une voix prete.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    if tmp.exists():
        tmp.unlink()
    request = Request(url, headers={"User-Agent": "youtube_clipper-local"})
    try:
        with urlopen(request, timeout=120) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with tmp.open("wb") as out:
                while True:
                    if cancel is not None:
                        cancel()
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
        if not tmp.is_file() or tmp.stat().st_size == 0:
            raise TtsError(f"Telechargement vide : {dest.name}")
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def download_voice(voice_id: str, models_dir: Path, *, progress=None, cancel=None) -> dict:
    """Telecharge les fichiers d'une voix (a la demande). Saute ceux deja la.

    ``progress(current, total, message)`` agrege les fichiers ; ``cancel()`` leve
    une exception pour interrompre. Retourne la liste des fichiers presents.
    """
    voice = voice_by_id(voice_id)
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    files = voice["files"]
    for index, item in enumerate(files):
        if cancel is not None:
            cancel()
        dest = models_dir / item["filename"]
        label = f"{voice['label']} — fichier {index + 1}/{len(files)}"
        if dest.is_file() and dest.stat().st_size > 0:
            if progress is not None:
                progress(index + 1, len(files), f"{label} (déjà présent)")
            continue
        if progress is not None:
            progress(index, len(files), f"{label}…")

        def file_progress(done: int, total: int, _label=label) -> None:
            if progress is not None:
                # une fraction du fichier courant ajoute a l'index de fichier
                frac = (done / total) if total else 0.0
                progress(index + frac, len(files), f"{_label}… {done // (1024 * 1024)} Mo")

        try:
            _download_file(item["url"], dest, progress=file_progress, cancel=cancel)
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError(f"Telechargement impossible ({item['filename']}) : {exc}") from exc
    if progress is not None:
        progress(len(files), len(files), f"{voice['label']} prêt.")
    return {"id": voice_id, "files": [f["filename"] for f in files],
            "downloaded": _files_present(voice, models_dir)}


# --- Synthese ------------------------------------------------------------------


def _write_wav_frames(out_path: Path, *, channels: int, sample_width: int,
                      sample_rate: int, frames: bytes) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)


def _synthesize_piper(voice: dict, text: str, models_dir: Path, tmp: Path,
                      speed: float, cancel) -> tuple[int, int]:
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    model = models_dir / f"{voice['engine_voice']}.onnx"
    config = models_dir / f"{voice['engine_voice']}.onnx.json"
    engine = PiperVoice.load(str(model), config_path=str(config))
    # Piper pilote la duree des phonemes (length_scale) : > 1 = plus lent.
    # On expose une vitesse unique (> 1 = plus rapide) => length_scale = 1 / speed.
    syn_config = SynthesisConfig(length_scale=1.0 / max(0.1, speed))
    rate = PIPER_SAMPLE_RATE
    channels, width = 1, 2
    frames = bytearray()
    for chunk in engine.synthesize(text, syn_config=syn_config):
        if cancel is not None:
            cancel()
        rate = chunk.sample_rate
        channels, width = chunk.sample_channels, chunk.sample_width
        frames.extend(chunk.audio_int16_bytes)
    _write_wav_frames(tmp, channels=channels, sample_width=width,
                      sample_rate=rate, frames=bytes(frames))
    return rate, len(frames) // (channels * width)


def _synthesize_kokoro(voice: dict, text: str, models_dir: Path, tmp: Path,
                       speed: float, cancel) -> tuple[int, int]:
    import numpy as np
    from kokoro_onnx import Kokoro

    model = models_dir / "kokoro-v1.0.onnx"
    voices = models_dir / "voices-v1.0.bin"
    engine = Kokoro(str(model), str(voices))
    if cancel is not None:
        cancel()
    samples, rate = engine.create(text, voice=voice["engine_voice"],
                                  speed=max(0.1, speed), lang=voice["lang_code"] or "en-us")
    if cancel is not None:
        cancel()
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    _write_wav_frames(tmp, channels=1, sample_width=2, sample_rate=int(rate),
                      frames=pcm.tobytes())
    return int(rate), len(pcm)


def synthesize(text: str, voice_id: str, models_dir: Path, out_path: Path, *,
               speed: float = 1.0, progress=None, cancel=None) -> dict:
    """Produit un WAV PCM 16 bits mono a ``out_path``. Erreur claire si le moteur
    ou la voix manque. ``speed`` : 1.0 = normal, > 1 = plus rapide, < 1 = plus lent.

    Le WAV est ecrit dans un ``.part`` puis renomme : une synthese annulee ne
    laisse pas un fichier incomplet pris pour une voix off utilisable.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise TtsError("Texte vide : rien a synthetiser.")
    voice = voice_by_id(voice_id)
    models_dir = Path(models_dir)
    engines = engine_state()
    engine = engines[voice["engine"]]
    if not engine["available"]:
        raise TtsError(engine["reason"])
    if not _files_present(voice, models_dir):
        raise TtsError(f"Voix non telechargee : {voice['label']}. "
                       "Cliquez « Télécharger la voix » d'abord.")
    if not math.isfinite(speed) or speed <= 0:
        raise TtsError(f"Vitesse invalide : {speed!r}.")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".part")
    if tmp.exists():
        tmp.unlink()
    if progress is not None:
        progress(0, 1, f"Synthese ({voice['label']})…")
    try:
        if voice["engine"] == "piper":
            rate, n_samples = _synthesize_piper(voice, cleaned, models_dir, tmp, speed, cancel)
        else:
            rate, n_samples = _synthesize_kokoro(voice, cleaned, models_dir, tmp, speed, cancel)
        if cancel is not None:
            cancel()
        if not tmp.is_file() or tmp.stat().st_size == 0:
            raise TtsError("Synthese vide : aucun echantillon produit.")
        if out_path.exists():
            out_path.unlink()
        tmp.replace(out_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    duration = n_samples / float(rate) if rate else 0.0
    if progress is not None:
        progress(1, 1, "Voix off generee.")
    return {"path": str(out_path), "sample_rate": rate, "duration": round(duration, 3),
            "voice": voice_id, "engine": voice["engine"]}