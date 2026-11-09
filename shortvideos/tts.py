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

import json
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


# --- Catalogue complet --------------------------------------------------------
# Piper publie la liste integrale de ses voix (53 langues, 180 voix) dans
# ``voices.json`` : un snapshot est versionne dans le depot, donc le catalogue
# est complet SANS aucune requete reseau au demarrage. Kokoro partage un seul
# modele pour ses 54 voix, listees ici.
_PIPER_SNAPSHOT = Path(__file__).with_name("piper_voices.json")

# Noms de langues en francais (affichage). Repli : le nom anglais du snapshot.
_LANG_FR = {
    "ar": "arabe", "bg": "bulgare", "bn": "bengali", "ca": "catalan",
    "cs": "tchèque", "cy": "gallois", "da": "danois", "de": "allemand",
    "el": "grec", "en": "anglais", "es": "espagnol", "et": "estonien",
    "eu": "basque", "fa": "persan", "fi": "finnois", "fr": "français",
    "he": "hébreu", "hi": "hindi", "hu": "hongrois", "hy": "arménien",
    "id": "indonésien", "is": "islandais", "it": "italien", "ja": "japonais",
    "ka": "géorgien", "kk": "kazakh", "ko": "coréen", "ku": "kurde",
    "lb": "luxembourgeois", "lt": "lituanien", "lv": "letton",
    "ml": "malayalam", "mr": "marathi", "ne": "népalais", "nl": "néerlandais",
    "no": "norvégien", "pl": "polonais", "pt": "portugais", "ro": "roumain",
    "ru": "russe", "sk": "slovaque", "sl": "slovène", "sq": "albanais",
    "sr": "serbe", "sv": "suédois", "sw": "swahili", "te": "télougou",
    "th": "thaï", "tr": "turc", "uk": "ukrainien", "ur": "ourdou",
    "vi": "vietnamien", "zh": "chinois",
}

# Ids deja publies par l'API et utilises par le frontend / les tests : on les
# conserve pour que rien ne casse en passant du catalogue restreint au complet.
_LEGACY_IDS = {
    "fr_FR-siwis-medium": "piper-fr-siwis",
    "fr_FR-tom-medium": "piper-fr-tom",
    "en_US-lessac-medium": "piper-en-lessac",
    "en_US-ryan-medium": "piper-en-ryan",
    "ff_siwis": "kokoro-fr-siwis",
    "af_heart": "kokoro-en-heart",
    "am_michael": "kokoro-en-michael",
    "bf_emma": "kokoro-en-emma",
}
_LEGACY_GENDER = {
    "piper-fr-siwis": "female", "piper-fr-tom": "male",
    "piper-en-lessac": "female", "piper-en-ryan": "male",
    "kokoro-fr-siwis": "female", "kokoro-en-heart": "female",
    "kokoro-en-michael": "male", "kokoro-en-emma": "female",
}

# Voix Kokoro (release model-files-v1.1) : prefixe -> langue, genre, code,
# nom francais. Source : VOICES.md de hexgrad/Kokoro-82M.
_KOKORO_PREFIX = {
    "af": ("en", "female", "en-us", "anglais US"),
    "am": ("en", "male", "en-us", "anglais US"),
    "bf": ("en", "female", "en-gb", "anglais UK"),
    "bm": ("en", "male", "en-gb", "anglais UK"),
    "ef": ("es", "female", "es", "espagnol"),
    "em": ("es", "male", "es", "espagnol"),
    "ff": ("fr", "female", "fr-fr", "français"),
    "hf": ("hi", "female", "hi", "hindi"),
    "hm": ("hi", "male", "hi", "hindi"),
    "if": ("it", "female", "it", "italien"),
    "im": ("it", "male", "it", "italien"),
    "jf": ("ja", "female", "ja", "japonais"),
    "jm": ("ja", "male", "ja", "japonais"),
    "pf": ("pt", "female", "pt-br", "portugais BR"),
    "pm": ("pt", "male", "pt-br", "portugais BR"),
    "zf": ("zh", "female", "zh", "mandarin"),
    "zm": ("zh", "male", "zh", "mandarin"),
}
_KOKORO_NAMES = (
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore",
    "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    "ef_dora", "em_alex", "em_santa", "ff_siwis",
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    "if_sara", "im_nicola",
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    "pf_dora", "pm_alex", "pm_santa",
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
)


def _piper_files(entry: dict) -> list[dict]:
    """Fichiers telechargeables d'une entree du snapshot (sans MODEL_CARD)."""
    files = []
    for path, meta in (entry.get("files") or {}).items():
        if not path.endswith((".onnx", ".onnx.json")):
            continue
        files.append({
            "url": f"{_HF}/{path}?download=true",
            "filename": Path(path).name,
            "size_bytes": int((meta or {}).get("size_bytes") or 0),
        })
    return files


def _piper_voices() -> list[dict]:
    """Catalogue Piper complet lu dans le snapshot local (aucun reseau)."""
    try:
        raw = json.loads(_PIPER_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    voices = []
    for key, entry in sorted(raw.items()):
        if not isinstance(entry, dict):
            continue
        files = _piper_files(entry)
        if not files:
            continue
        lang = entry.get("language") or {}
        family = str(lang.get("family") or key.split("_")[0]).lower()
        locale = str(lang.get("code") or "")
        name = str(entry.get("name") or key)
        quality = str(entry.get("quality") or "")
        voice_id = _LEGACY_IDS.get(key, f"piper-{key}")
        language_name = _LANG_FR.get(
            family, str(lang.get("name_english") or family)
        )
        voices.append({
            "id": voice_id,
            "engine": "piper",
            "label": f"{name} · {language_name} ({locale}) · {quality}",
            "language": family,
            "gender": _LEGACY_GENDER.get(voice_id, ""),
            "engine_voice": key,
            "lang_code": "",
            "locale": locale,
            "quality": quality,
            "language_name": language_name,
            "files": files,
            "size_bytes": sum(f["size_bytes"] for f in files),
        })
    return voices


def _kokoro_voices() -> list[dict]:
    voices = []
    for full in _KOKORO_NAMES:
        prefix, _, name = full.partition("_")
        meta = _KOKORO_PREFIX.get(prefix)
        if meta is None:
            continue
        family, gender, lang_code, language_name = meta
        voice_id = _LEGACY_IDS.get(full, f"kokoro-{full}")
        voices.append({
            "id": voice_id,
            "engine": "kokoro",
            "label": f"{name} · {language_name} ({lang_code})",
            "language": family,
            "gender": _LEGACY_GENDER.get(voice_id, gender),
            "engine_voice": full,
            "lang_code": lang_code,
            "locale": "",
            "quality": "",
            "language_name": language_name,
            "files": _KOKORO_FILES,
            "size_bytes": 0,  # modele partage : voir _approx_mb
        })
    return voices


# Repli si le snapshot piper_voices.json est absent : les quatre voix
# historiquement verifiees, pour ne jamais laisser l'app sans catalogue.
_FALLBACK_PIPER = [
    {
        "id": "piper-fr-siwis", "engine": "piper",
        "label": "Siwis · français (fr_FR) · medium",
        "language": "fr", "gender": "female", "engine_voice": "fr_FR-siwis-medium",
        "lang_code": "", "locale": "fr_FR", "quality": "medium",
        "language_name": "français",
        "files": _piper_voice("fr_FR-siwis-medium", "fr", "fr_FR", "siwis", "medium"),
        "size_bytes": 63_000_000,
    },
    {
        "id": "piper-fr-tom", "engine": "piper",
        "label": "Tom · français (fr_FR) · medium",
        "language": "fr", "gender": "male", "engine_voice": "fr_FR-tom-medium",
        "lang_code": "", "locale": "fr_FR", "quality": "medium",
        "language_name": "français",
        "files": _piper_voice("fr_FR-tom-medium", "fr", "fr_FR", "tom", "medium"),
        "size_bytes": 63_000_000,
    },
    {
        "id": "piper-en-lessac", "engine": "piper",
        "label": "Lessac · anglais (en_US) · medium",
        "language": "en", "gender": "female", "engine_voice": "en_US-lessac-medium",
        "lang_code": "", "locale": "en_US", "quality": "medium",
        "language_name": "anglais",
        "files": _piper_voice("en_US-lessac-medium", "en", "en_US", "lessac", "medium"),
        "size_bytes": 63_000_000,
    },
    {
        "id": "piper-en-ryan", "engine": "piper",
        "label": "Ryan · anglais (en_US) · medium",
        "language": "en", "gender": "male", "engine_voice": "en_US-ryan-medium",
        "lang_code": "", "locale": "en_US", "quality": "medium",
        "language_name": "anglais",
        "files": _piper_voice("en_US-ryan-medium", "en", "en_US", "ryan", "medium"),
        "size_bytes": 63_000_000,
    },
]

VOICES: list[dict] = (_piper_voices() or _FALLBACK_PIPER) + _kokoro_voices()


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
            "language_name": voice.get("language_name") or voice["language"],
            "locale": voice.get("locale") or "",
            "quality": voice.get("quality") or "",
            "downloaded": downloaded,
            "ready": bool(engine["available"] and downloaded),
            "approx_mb": _approx_mb(voice),
        })
    voices.sort(key=lambda v: (v["language_name"].lower(), v["label"].lower()))
    return {"engines": engines, "voices": voices}


def _approx_mb(voice: dict) -> int:
    """Taille annoncee : somme reelle des fichiers, sauf modele Kokoro partage."""
    if voice["engine"] == "kokoro":
        return 330  # modele + voix partages
    total = sum(int(f.get("size_bytes") or 0) for f in voice.get("files") or [])
    if total:
        return max(1, round(total / (1024 * 1024)))
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