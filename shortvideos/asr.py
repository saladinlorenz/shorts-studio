"""Transcription audio reelle, sans aucune dependance ajoutee.

Deux fournisseurs, le meme resultat :

- ``groq`` — ``whisper-large-v3-turbo`` via le SDK ``groq`` **deja requis par le
  projet** (Clips l'utilise pour l'analyse de texte). C'est un appel reseau : il
  n'est lance que si l'utilisateur le demande, et la cle utilisee est choisie
  explicitement (jamais pickup en silence).
- ``local`` — whisper.cpp (``whisper-cli``) ou ``faster_whisper`` **si l'utilisateur
  les a deja installs**. Le module les detecte, il n'installe rien : sans binaire ni
  modele, le fournisseur repond « indisponible » avec la raison.

Le son est extrait avec le FFmpeg deja embarque (``imageio_ffmpeg``), puis decoupe
sur les silences pour rester sous la limite de taille d'un fichier Groq. Les temps
remontes par un morceau sont decales de sa position : les segments sont toujours
exprimes en secondes **absolues** de la video source.

Aucun texte n'est invente, aucun temps n'est estimation : ce module ne renvoie que
ce que le modele ASR a entendu.
"""
from __future__ import annotations

import array
import json
import math
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg


SAMPLE_RATE = 16_000          # 16 kHz mono 16 bits : ce que Whisper attend
CHANNELS = 1
MAX_CHUNK_SECONDS = 7 * 60    # ~13 Mo dans ce format, sous la limite Groq (25 Mo)
GROQ_WHISPER_MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")
SILENCE_RMS = 0.012           # seuil de RMS normalise pour couper sans casser un mot
ENERGY_WINDOW_S = 0.05


class AsrError(RuntimeError):
    """La transcription est impossible : raison humaine, jamais un stacktrace nu."""


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


# --- Extraction et lecture du son -------------------------------------------


def extract_audio(source, out_path=None, *, sample_rate=SAMPLE_RATE, timeout=600) -> dict:
    """Extrait la piste audio d'une video (ou d'un audio) en WAV PCM 16 bits mono.

    Retourne ``{path, sample_rate, channels, duration, seconds_of_stream}``. Une
    absence de piste audio est une erreur explicite : sans son, il n'y a rien a
    transcrire, et le reste de la chaine ne doit pas tourner dans le vide.
    """
    src = Path(source)
    if not src.is_file():
        raise AsrError(f"Fichier audio introuvable : {src.name}")
    out = Path(out_path) if out_path else src.with_suffix(".asr.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.wav")
    if tmp.exists():
        tmp.unlink()
    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vn", "-ac", str(CHANNELS), "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", str(tmp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        tmp.unlink(missing_ok=True)
        raise AsrError(f"Extraction audio interrompue apres {timeout} s : {src.name}") from exc
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        if "does not contain any stream" in stderr or "Stream map" in stderr:
            raise AsrError(f"Aucune piste audio dans {src.name} : rien a transcrire.")
        raise AsrError(f"Extraction audio impossible (code {proc.returncode}) : "
                       f"{stderr[:200] or 'aucun detail'}")
    if out.exists():
        out.unlink()
    tmp.replace(out)
    seconds = wav_duration(out)
    return {"path": str(out), "sample_rate": sample_rate, "channels": CHANNELS,
            "duration": round(seconds, 3)}


def wav_duration(path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def read_pcm16(path):
    """(samples signed 16 bits, sample_rate) — lecture stdlib, aucun paquet ajoute."""
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise AsrError("WAV attendu : mono 16 bits (produit par extract_audio).")
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    return samples, rate


def energy_curve(path, *, window_s: float = ENERGY_WINDOW_S) -> dict:
    """Enveloppe d'energie (RMS normalise) par fenetre, pour la detection de moments.

    Returnne ``{window_s, duration, rms: [...]}`` — une valeur par fenetre, calculee
    sur le vrai signal, jamais interpolatee ni lissage invente.

    ``numpy`` vient d'``opencv-python`` (déjà requis par le projet) : sur une heure de
    parole, la boucle Python couterait des dizaines de secondes a chaque analyse.
    """
    samples, rate = read_pcm16(path)
    step = max(1, int(round(window_s * rate)))
    total = len(samples)
    duration = total / float(rate) if rate else 0.0
    if total == 0:
        return {"window_s": round(window_s, 4), "duration": 0.0, "rms": []}

    import numpy as np

    values = np.frombuffer(samples.tobytes(), dtype=np.int16).astype(np.float64)
    peak = float(np.max(np.abs(values))) or 1.0
    usable = (total // step) * step
    windows = values[:usable].reshape(-1, step)
    rms = [round(float(value), 4) for value in np.sqrt((windows * windows).mean(axis=1)) / peak]
    if usable < total:
        tail = values[usable:]
        rms.append(round(float(np.sqrt((tail * tail).mean()) / peak), 4))
    return {"window_s": round(window_s, 4), "duration": round(duration, 3), "rms": rms}


def split_points(path, *, max_seconds: float = MAX_CHUNK_SECONDS) -> list[tuple[float, float]]:
    """Decoupe un WAV en morceaux <= ``max_seconds``, coupes dans un silence.

    Un morceau coupe au milieu d'un mot produit une transcription degradee : on
    cherche le point le plus bas d'energie autour de la limite, a l'interieur d'une
    fenetre de tolerance, et on ne coupe jamais deux fois au meme endroit.
    """
    curve = energy_curve(path)
    duration = curve["duration"]
    window = curve["window_s"]
    rms = curve["rms"]
    if duration <= 0:
        return []
    if duration <= max_seconds:
        return [(0.0, round(duration, 3))]
    cuts: list[float] = [0.0]
    limit = max_seconds
    tolerance = max_seconds * 0.2
    while limit < duration - tolerance:
        low_i, high_i = int((limit - tolerance) / window), int((limit + tolerance) / window)
        low_i, high_i = max(1, low_i), min(len(rms) - 1, high_i)
        candidate = min(range(low_i, high_i + 1), key=lambda i: rms[i]) if high_i > low_i else low_i
        point = round(candidate * window, 3)
        if point <= cuts[-1] + 1.0:
            point = round(limit, 3)
        cuts.append(point)
        limit = point + max_seconds
    cuts.append(round(duration, 3))
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]


def cut_wav(source, out_path, start: float, end: float) -> str:
    """Ecrit un sous-morceau WAV (pour les decoupages envoyes a l'ASR)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.05, float(end) - float(start))
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{float(start):.3f}", "-t", f"{duration:.3f}", "-i", str(source),
           "-c:a", "pcm_s16le", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        raise AsrError(f"Decoupe audio impossible ({out.name}) : "
                       f"{(proc.stderr or '').strip()[:180] or 'aucun detail'}")
    return str(out)


# --- Fournisseurs ------------------------------------------------------------


def local_backend() -> dict:
    """Detecte un Whisper deja installe sur ce poste. N'installe rien."""
    env_cli = os.environ.get("WHISPER_CLI") or os.environ.get("WHISPER_CPP_CLI")
    cli = env_cli if env_cli and Path(env_cli).is_file() else (
        shutil.which("whisper-cli") or shutil.which("whisper-cpp") or shutil.which("main")
    )
    model = os.environ.get("WHISPER_MODEL") or ""
    if not model:
        candidates = sorted(Path.cwd().glob("ggml-*.bin")) + sorted(
            (Path.home() / ".cache" / "whisper.cpp").glob("*.bin")
        )
        model = str(candidates[0]) if candidates else ""
    if cli and model:
        return {"kind": "whisper.cpp", "available": True, "cli": str(cli), "model": str(model),
                "reason": ""}
    try:  # plus rapide a detecter qu'a charger : l'import seul ne coute rien
        import faster_whisper  # noqa: F401
    except Exception:
        faster_whisper = None
    if faster_whisper is not None:
        return {"kind": "faster_whisper", "available": True, "cli": "",
                "model": os.environ.get("WHISPER_MODEL", "base.en"), "reason": ""}
    if cli and not model:
        reason = ("whisper.cpp détecté mais aucun modèle `ggml-*.bin` : "
                  "renseigne WHISPER_MODEL.")
    else:
        reason = ("Aucun Whisper local : installe toi-même whisper.cpp (variable WHISPER_CLI "
                  "+ un modèle ggml-*.bin) ou le paquet faster_whisper. Rien n'est installé "
                  "automatiquement.")
    return {"kind": "", "available": False, "cli": cli or "", "model": model, "reason": reason}


def providers(*, groq_key_present: bool) -> list[dict]:
    """Etat reel de chaque fournisseur, avec la raison precise s'il est hors service."""
    local = local_backend()
    return [
        {
            "id": "groq",
            "label": "Groq Whisper",
            "cloud": True,
            "available": bool(groq_key_present),
            "models": list(GROQ_WHISPER_MODELS),
            "reason": "" if groq_key_present else
            "Aucune cle Groq selectionnee : choisis « Copie serveur -> cle de Clips » "
            "ou renseigne la cle dediee a la transcription dans Reglages.",
        },
        {
            "id": "local",
            "label": "Whisper local",
            "cloud": False,
            "available": local["available"],
            "kind": local["kind"],
            "models": [local["model"]] if local["available"] else [],
            "reason": local["reason"],
        },
    ]


def transcribe_groq(chunks, *, api_key, model=GROQ_WHISPER_MODELS[0], language=None,
                    client_factory=None, progress=None, cancel=None) -> dict:
    """Transcrit des morceaux WAV sequentially ; les temps sont rendus absolus.

    ``client_factory`` est injectable pour les tests : sans lui, le SDK ``groq`` est
    instancie avec la cle fournie. Aucun appel n'est fait si la cle est absente.
    """
    if model not in GROQ_WHISPER_MODELS:
        raise AsrError(f"Modele Groq inconnu : {model!r} (attendu : "
                       f"{', '.join(GROQ_WHISPER_MODELS)}).")
    if not api_key:
        raise AsrError("Cle Groq absente : la transcription Groq est un appel reseau, "
                       "elle doit etre demandee explicitement.")
    try:
        from groq import Groq
    except Exception as exc:  # pragma: no cover - le paquet est requis par le projet
        raise AsrError(f"SDK groq indisponible : {exc}") from exc
    client = client_factory(api_key) if client_factory else Groq(api_key=api_key)

    segments: list[dict] = []
    warnings: list[str] = []
    detected = ""
    for index, chunk in enumerate(chunks, start=1):
        if cancel is not None:
            cancel()
        if progress is not None:
            progress(index - 1, len(chunks), f"Transcription Groq du morceau {index}/{len(chunks)}…")
        payload = _groq_chunk(client, chunk["path"], model=model, language=language)
        offset = float(chunk["start"])
        for seg in payload.get("segments") or []:
            start, end = seg.get("start"), seg.get("end")
            if start is None or end is None:
                continue
            segments.append({"start": round(float(start) + offset, 3),
                             "end": round(float(end) + offset, 3),
                             "text": str(seg.get("text") or "").strip()})
        detected = detected or str(payload.get("language") or "")
        if not (payload.get("segments") or []):
            warnings.append(f"Piece {index}/{len(chunks)} : aucun segment entendu.")
    return {"segments": segments, "language": detected, "warnings": warnings,
            "model": model, "provider": "groq"}


def _groq_chunk(client, wav_path, *, model, language) -> dict:
    """Un appel /audio/transcriptions, reponse normalisee en dictionnaire."""
    kwargs = {"model": model, "response_format": "verbose_json",
              "timestamp_granularities": ["segment"]}
    if language:
        kwargs["language"] = language
    try:
        with open(wav_path, "rb") as handle:
            result = client.audio.transcriptions.create(file=handle, **kwargs)
    except TypeError as exc:  # SDK trop ancien pour les granularites
        raise AsrError(f"SDK groq trop ancien pour la transcription horodatee : {exc}") from exc
    except Exception as exc:
        raise AsrError(f"Transcription Groq refusee : {type(exc).__name__} — {exc}") from exc
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return {"segments": [
        {"start": s.start, "end": s.end, "text": s.text} for s in (getattr(result, "segments", None) or [])
    ], "language": getattr(result, "language", "") or ""}


def transcribe_local(chunks, *, model=None, language=None, progress=None, cancel=None) -> dict:
    """Transcrit avec le Whisper detecte sur le poste. Erreur claire si absent."""
    backend = local_backend()
    if not backend["available"]:
        raise AsrError(backend["reason"])
    if backend["kind"] == "whisper.cpp":
        return _local_whisper_cpp(backend, chunks, language=language,
                                  progress=progress, cancel=cancel)
    return _local_faster_whisper(chunks, model=model or backend["model"], language=language,
                                 progress=progress, cancel=cancel)


def _local_whisper_cpp(backend, chunks, *, language=None, progress=None, cancel=None) -> dict:
    """whisper-cli avec sortie JSON (`-oj`) : les temps sont deja secondes."""
    segments: list[dict] = []
    warnings: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        if cancel is not None:
            cancel()
        if progress is not None:
            progress(index - 1, len(chunks), f"Transcription locale {index}/{len(chunks)}…")
        cmd = [backend["cli"], "-m", backend["model"], "-f", chunk["path"], "-oj", "-np"]
        if language:
            cmd += ["-l", language]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=3600)
        if proc.returncode != 0:
            raise AsrError(f"whisper.cpp a echoue (code {proc.returncode}) : "
                           f"{(proc.stderr or '').strip()[:200] or 'aucun detail'}")
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise AsrError(f"Sortie JSON de whisper.cpp illisible : {exc}") from exc
        result = data.get("result") or {}
        offset = float(chunk["start"])
        heard = 0
        for transcription in result.get("transcription") or []:
            start, end = transcription.get("timestamps", [None, None])
            segments.append({"start": round(float(start) + offset, 3),
                             "end": round(float(end) + offset, 3),
                             "text": str(transcription.get("text") or "").strip()})
            heard += 1
        if not heard:
            warnings.append(f"Piece {index}/{len(chunks)} : aucun segment entendu.")
    return {"segments": [s for s in segments if s["text"]], "language": language or "",
            "warnings": warnings, "model": Path(backend["model"]).name, "provider": "local"}


def _local_faster_whisper(chunks, *, model, language=None, progress=None, cancel=None) -> dict:
    from faster_whisper import WhisperModel  # import retard : seulement si present

    segments: list[dict] = []
    model_id = ""
    for index, chunk in enumerate(chunks, start=1):
        if cancel is not None:
            cancel()
        if progress is not None:
            progress(index - 1, len(chunks), f"Transcription locale {index}/{len(chunks)}…")
        engine = WhisperModel(model, device="auto", compute_type="auto")
        model_id = model
        offset = float(chunk["start"])
        try:
            iterator, _info = engine.transcribe(chunk["path"], language=language or None)
        except Exception as exc:
            raise AsrError(f"faster_whisper refuse le morceau {index} : {exc}") from exc
        for seg in iterator:
            segments.append({"start": round(float(seg.start) + offset, 3),
                             "end": round(float(seg.end) + offset, 3),
                             "text": str(seg.text or "").strip()})
    return {"segments": segments, "language": language or "", "warnings": [],
            "model": model_id, "provider": "local"}


def transcribe(source, *, provider="auto", api_key="", groq_model=GROQ_WHISPER_MODELS[0],
               language=None, work_dir=None, client_factory=None,
               progress=None, cancel=None, max_chunk_seconds=MAX_CHUNK_SECONDS,
               audio_out=None) -> dict:
    """Point d'entree : une video (ou un WAV) -> transcript horodate et normalise.

    ``provider`` : ``auto`` (local d'abord, puis Groq), ``groq`` ou ``local``. Les
    temps sont absolus ; ``duration`` vient du vrai flux audio ; ``warnings`` reste
    vide tant que rien d'anormal n'est observe.

    ``audio_out`` : garder la piste 16 kHz mono extraite a ce chemin (l'enveloppe
    d'energie de la detection de moments en a besoin) au lieu de la jeter.
    """
    src = Path(source)
    if not src.is_file():
        raise AsrError(f"Source introuvable : {src}")
    folder = Path(work_dir) if work_dir else src.parent
    folder.mkdir(parents=True, exist_ok=True)
    keep = Path(audio_out) if audio_out else None
    wav = keep if keep is not None else folder / f"{src.stem}.asr.wav"
    audio = extract_audio(src, wav)
    duration = float(audio["duration"])
    ranges = split_points(wav, max_seconds=max_chunk_seconds)
    chunks: list[dict] = []
    try:
        for index, (start, end) in enumerate(ranges, start=1):
            if cancel is not None:
                cancel()
            if end - start < 0.5:
                continue  # un bouttaille < 0,5 s ne porte aucun enonce
            path = cut_wav(wav, folder / f"{src.stem}.chunk{index:02d}.wav", start, end)
            chunks.append({"path": path, "start": round(start, 3), "end": round(end, 3)})
    finally:
        if keep is None:
            wav.unlink(missing_ok=True)

    if not chunks:
        raise AsrError(f"Audio trop court ({duration:.1f} s) : rien a transcrire.")

    order = ["local", "groq"] if provider == "auto" else [provider]
    result: dict | None = None
    failures: list[str] = []
    for choice in order:
        if choice == "local":
            if not local_backend()["available"]:
                failures.append(local_backend()["reason"])
                continue
            try:
                result = transcribe_local(chunks, language=language, progress=progress, cancel=cancel)
                break
            except AsrError as exc:
                failures.append(str(exc))
                continue
        if choice == "groq":
            try:
                result = transcribe_groq(chunks, api_key=api_key, model=groq_model,
                                         language=language, client_factory=client_factory,
                                         progress=progress, cancel=cancel)
                break
            except AsrError as exc:
                failures.append(str(exc))
                continue
        else:
            failures.append(f"Fournisseur de transcription inconnu : {choice!r}")
    if result is None:
        raise AsrError("Transcription impossible : " + " | ".join(f for f in failures if f))

    segments = normalize_segments(result["segments"])
    for path in (chunk["path"] for chunk in chunks):
        Path(path).unlink(missing_ok=True)

    warnings = list(result.get("warnings") or [])
    video_duration = _probe_duration(src)
    if video_duration and abs(duration - video_duration) > 1.0:
        warnings.append(
            f"Duree audio ({duration:.1f} s) et rangee video ({video_duration:.1f} s) "
            "differents : les temps sont ceux de l'audio."
        )
    return {
        "provider": result["provider"],
        "model": result["model"],
        "language": result.get("language") or (language or ""),
        "duration": round(duration, 3),
        "source": str(src),
        "audio_path": str(keep) if keep is not None else "",
        "segments": segments,
        "warnings": warnings,
    }


def _probe_duration(path: Path) -> float:
    """Duree declaree du conteneur, ou 0.0 quand elle n'est pas lisible.

    Seul ffmpeg est interroge ici : OpenCV ouvre un MP4 sans peine mais se bloque sur
    un fichier purement audio, et un podcast WAV gelerait le job pour toujours. Cette
    duree ne sert qu'a signaler un ecart conteneur/audio ; 0.0 saute simplement l'alerte.
    """
    from . import probe

    try:
        return float(probe.duration_ffmpeg(str(path)) or 0.0)
    except Exception:
        return 0.0


def normalize_segments(segments) -> list[dict]:
    """Segments triés, sans doublon ni durée invalide ; temps croissants garantis."""
    cleaned: list[dict] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        try:
            start, end = float(seg.get("start")), float(seg.get("end"))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(start) and math.isfinite(end)):
            continue  # un NaN traverserait les filtres et detruirait les decoupages
        text = re.sub(r"\s+", " ", str(seg.get("text") or "")).strip()
        if not text or end <= start:
            continue
        cleaned.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    cleaned.sort(key=lambda s: (s["start"], s["end"]))
    out: list[dict] = []
    for seg in cleaned:
        if out and seg["start"] < out[-1]["start"]:
            continue
        out.append(seg)
    return out


def parse_srt(text: str) -> list[dict]:
    """Un `.srt` (fourni par une session Clips) -> segments normalises.

    Utile quand la source a deja des sous-titres officiels : on ne repasse pas par un
    ASR pour retrouver ce qui est deja ecrit.
    """
    stamps = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
    )
    segments: list[dict] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text or "")
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        match = None
        text_lines: list[str] = []
        for line in lines:
            found = stamps.search(line)
            if found and match is None:
                match = found
            elif match is not None:
                text_lines.append(line.strip())
        if not match:
            continue
        g = [int(x) for x in match.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        joined = re.sub(r"\s+", " ", " ".join(text_lines)).strip()
        if joined:
            segments.append({"start": round(start, 3), "end": round(end, 3), "text": joined})
    return normalize_segments(segments)


def transcript_text(segments) -> str:
    return "\n".join(f"[{s['start']:.1f}s] {s['text']}" for s in segments or [])
