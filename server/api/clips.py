"""Routes Clips : telechargement YouTube, analyse Groq, extraction FFmpeg.

La logique metier reste portee par les modules existants (``downloader``,
``analyzer``, ``processor``) : ce fichier les orchestre dans des jobs, avec
des chemins bornes au projet et la cle API Groq qui ne quitte jamais le
serveur.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from analyzer import TranscriptAnalyzer
from downloader import YouTubeDownloader
from processor import VideoProcessor
from shortvideos.probe import ProbeError, probe_mp4

from .. import settings as settings_mod
from ..jobs import Job, JobCancelled, create_job, raise_if_cancelled
from ..security import CLIPS_DIR, DOWNLOADS_DIR, assert_local_dir, safe_name

router = APIRouter(prefix="/api/clips", tags=["clips"])

SID_RE = re.compile(r"^[0-9a-f]{12}$")
TRANSCRIPT_LIMIT = 40000

# Callbacks metier -> progression du job : les modules existants ne renvoient
# que des messages texte ("Clip 3/12", "Downloading: 45.0%"), d'ou l'extraction.
_COUNT_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def bridge_progress(job: Job, log: list[str] | None = None) -> Callable[[str], None]:
    """Adapte une ``progress_callback`` metier en progression de job."""

    def callback(message: str) -> None:
        if job.cancel_event.is_set():
            raise JobCancelled()
        text = str(message)
        if log is not None:
            log.append(text[:200])
            del log[:-30]
        count = _COUNT_RE.search(text)
        if count:
            current, total = int(count.group(1)), int(count.group(2))
            job.set_progress(min(current, total), total, text[:200])
            return
        percent = _PERCENT_RE.search(text)
        if percent:
            value = float(percent.group(1).replace(",", "."))
            job.set_progress(min(int(value), 100), 100, text[:200])
            return
        job.set_progress(int(job.progress * 100), 100, text[:200])

    return callback


class UrlPayload(BaseModel):
    url: str


class AnalyzePayload(BaseModel):
    sid: str
    num_clips: int = 5


class ExtractPayload(BaseModel):
    sid: str
    clip_indexes: list[int] | None = None
    landscape: bool = True
    portrait: bool = True


def clean_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="URL YouTube manquante.")
    if len(cleaned) > 500 or any(c.isspace() for c in cleaned):
        raise HTTPException(status_code=400, detail="URL YouTube invalide (espaces ou longueur).")
    if not cleaned.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Seules les URL http/https sont acceptées.")
    return cleaned


def hhmmss(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def readable(exc: Exception) -> str:
    text = str(exc).strip().replace("\n", " ")
    return (text[-400:] or exc.__class__.__name__) if text else exc.__class__.__name__


def session_path(sid: str) -> Path:
    if not SID_RE.match(sid or ""):
        raise HTTPException(status_code=400, detail="Identifiant de session invalide.")
    return assert_local_dir(DOWNLOADS_DIR / f"session-{sid}.json")


def load_session(sid: str) -> dict:
    path = session_path(sid)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Session introuvable : téléchargez d'abord la vidéo.",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Session illisible : relancez le téléchargement.")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Session illisible : relancez le téléchargement.")
    return data


def save_session(data: dict) -> None:
    path = session_path(str(data["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def session_video(session: dict) -> Path:
    name = session.get("video_name")
    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=400, detail="Aucun fichier vidéo associé à cette session.")
    path = assert_local_dir(DOWNLOADS_DIR / safe_name(name))
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Fichier téléchargé introuvable : {path.name}. Relancez le téléchargement.",
        )
    return path


def file_info(path: Path, sid: str, clip: dict, fmt: str) -> dict:
    """Decrit un clip produit a partir du fichier reellement ecrit."""
    info = {
        "name": path.name,
        "url": f"/api/clips/files/{sid}/{path.name}",
        "format": fmt,
        "title": clip.get("title", ""),
        "hook": clip.get("hook", ""),
        "social_score": clip.get("social_score", 0),
        "start_time": clip.get("start_time", ""),
        "end_time": clip.get("end_time", ""),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "width": None,
        "height": None,
        "duration": clip.get("duration"),
        "unreadable": False,
    }
    try:
        probed = probe_mp4(str(path))
        info["width"] = probed["width"]
        info["height"] = probed["height"]
        info["duration"] = probed["duration"]
    except (ProbeError, OSError):
        info["unreadable"] = True
    return info


@router.post("/info")
def video_info(payload: UrlPayload) -> dict:
    url = clean_url(payload.url)

    def work(job: Job) -> dict:
        callback = bridge_progress(job)
        job.message = "Lecture des informations de la vidéo…"
        info = YouTubeDownloader(DOWNLOADS_DIR).get_video_info(url)
        raise_if_cancelled(job)
        duration = int(info.get("duration") or 0)
        return {
            "title": str(info.get("title") or "Inconnu")[:200],
            "duration": duration,
            "duration_display": hhmmss(duration),
            "formats": len(info.get("formats") or []),
            "subtitles": [str(x) for x in (info.get("subtitles") or [])][:12],
            "auto_captions": [str(x) for x in (info.get("auto_captions") or [])][:12],
        }

    return {"job_id": create_job("clips_info", work).id}


@router.post("/download")
def download(payload: UrlPayload) -> dict:
    url = clean_url(payload.url)
    started_at = time.time()

    def work(job: Job) -> dict:
        callback = bridge_progress(job)
        downloader = YouTubeDownloader(DOWNLOADS_DIR)
        try:
            job.message = "Téléchargement de la vidéo…"
            video_path, title = downloader.download_video(url, progress_callback=callback)
            job.message = "Téléchargement des sous-titres…"
            srt_path = downloader.download_subtitles(url, progress_callback=callback)
            raise_if_cancelled(job)
            transcript, segments = (downloader.srt_to_text(srt_path) if srt_path else ("", []))
        finally:
            if job.cancel_event.is_set():
                for part in DOWNLOADS_DIR.glob("*.part"):
                    try:
                        if part.stat().st_mtime >= started_at:
                            part.unlink()
                    except OSError:
                        pass

        video = Path(video_path)
        sid = uuid.uuid4().hex[:12]
        save_session(
            {
                "id": sid,
                "url": url,
                "title": str(title),
                "video_name": video.name,
                "subtitle_name": Path(srt_path).name if srt_path else None,
                "created_at": time.time(),
                "transcript": transcript,
                "segments": segments,
                "clips": [],
                "produced": [],
            }
        )
        return {
            "sid": sid,
            "title": str(title)[:200],
            "video_name": video.name,
            "video_size_bytes": video.stat().st_size if video.is_file() else 0,
            "subtitle_name": Path(srt_path).name if srt_path else None,
            "segment_count": len(segments),
            "transcript_chars": len(transcript),
            "warning": (
                None if srt_path else "Aucun sous-titre trouvé : l'analyse Groq est impossible."
            ),
        }

    return {"job_id": create_job("clips_download", work).id}


@router.get("/sessions")
def list_sessions() -> list[dict]:
    items = []
    for path in DOWNLOADS_DIR.glob("session-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not SID_RE.match(str(data.get("id", ""))):
            continue
        video = data.get("video_name")
        items.append(
            {
                "sid": data["id"],
                "title": str(data.get("title") or "")[:120],
                "video_name": video,
                "video_exists": bool(video) and (DOWNLOADS_DIR / safe_name(str(video))).is_file(),
                "created_at": data.get("created_at"),
                "analyzed_count": len(data.get("clips") or []),
                "produced_count": len(data.get("produced") or []),
            }
        )
    items.sort(key=lambda i: i.get("created_at") or 0, reverse=True)
    return items


@router.get("/sessions/{sid}")
def get_session(sid: str) -> dict:
    data = load_session(sid)
    transcript = str(data.get("transcript") or "")
    video_name = data.get("video_name")
    return {
        "sid": data["id"],
        "title": str(data.get("title") or "")[:200],
        "video_name": video_name,
        "video_exists": bool(video_name) and (DOWNLOADS_DIR / safe_name(str(video_name))).is_file(),
        "subtitle_name": data.get("subtitle_name"),
        "created_at": data.get("created_at"),
        "segment_count": len(data.get("segments") or []),
        "transcript_chars": len(transcript),
        "transcript": transcript[:TRANSCRIPT_LIMIT],
        "transcript_truncated": len(transcript) > TRANSCRIPT_LIMIT,
        "clips": data.get("clips") or [],
        "produced": data.get("produced") or [],
    }


@router.delete("/sessions/{sid}")
def delete_session(sid: str) -> dict:
    path = session_path(sid)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Session introuvable.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}

    removed = 0
    for key in ("video_name", "subtitle_name"):
        name = data.get(key) if isinstance(data, dict) else None
        if isinstance(name, str) and name:
            target = assert_local_dir(DOWNLOADS_DIR / safe_name(name))
            if target.is_file():
                try:
                    target.unlink()
                    removed += 1
                except OSError as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Suppression impossible du fichier {target.name} : {readable(e)}",
                    )

    clips_dir = assert_local_dir(CLIPS_DIR / sid)
    if clips_dir.is_dir():
        removed += sum(1 for p in clips_dir.rglob("*") if p.is_file())
        shutil.rmtree(clips_dir, ignore_errors=True)
    path.unlink(missing_ok=True)
    return {"deleted": sid, "removed_files": removed}


@router.post("/analyze")
def analyze(payload: AnalyzePayload) -> dict:
    session = load_session(payload.sid)
    transcript = str(session.get("transcript") or "")
    if not transcript.strip():
        raise HTTPException(
            status_code=400,
            detail="Aucune transcription disponible : les sous-titres sont absents ou vides.",
        )
    api_key = settings_mod.get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Clé API Groq non configurée : renseignez-la dans Réglages.",
        )
    num_clips = max(1, min(20, int(payload.num_clips)))
    sid = session["id"]
    title = str(session.get("title") or "Vidéo")

    def work(job: Job) -> dict:
        job.message = "Analyse de la transcription par Groq…"
        analyzer = TranscriptAnalyzer(api_key)
        raw = analyzer.analyze_transcript(transcript, video_title=title, num_clips=num_clips)
        raise_if_cancelled(job)
        if not isinstance(raw, list):
            raise RuntimeError("Réponse de l'IA inattendue : aucun découpage de clips renvoyé.")

        clips = []
        for i, clip in enumerate(raw):
            if not isinstance(clip, dict):
                continue
            start = as_seconds(clip.get("start_seconds"), clip.get("start_time"))
            end = as_seconds(clip.get("end_seconds"), clip.get("end_time"))
            if start is None or end is None or end <= start:
                continue
            clips.append(
                {
                    "index": len(clips),
                    "title": str(clip.get("title") or f"Clip {i + 1}")[:120],
                    "description": str(clip.get("description") or ""),
                    "hook": str(clip.get("hook") or ""),
                    "social_score": as_score(clip.get("social_score")),
                    "start_time": str(clip.get("start_time") or hhmmss(start)),
                    "end_time": str(clip.get("end_time") or hhmmss(end)),
                    "start_seconds": round(start, 2),
                    "end_seconds": round(end, 2),
                    "duration": round(end - start, 2),
                }
            )
        if not clips:
            raise RuntimeError(
                "Aucun clip exploitable détecté : l'IA n'a renvoyé aucun début/fin valide."
            )
        session["clips"] = clips
        save_session(session)
        return {
            "sid": sid,
            "clips": clips,
            "requested": num_clips,
            "discarded": max(0, len(raw) - len(clips)),
        }

    return {"job_id": create_job("clips_analyze", work).id}


def as_seconds(seconds, timestamp) -> float | None:
    try:
        if seconds is not None:
            return float(seconds)
    except (TypeError, ValueError):
        pass
    if isinstance(timestamp, str):
        parts = timestamp.replace(",", ".").split(":")
        try:
            numbers = [float(p) for p in parts]
        except ValueError:
            return None
        if len(numbers) == 3:
            return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]
    return None


def as_score(value) -> int:
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return 0


@router.post("/extract")
def extract(payload: ExtractPayload) -> dict:
    session = load_session(payload.sid)
    clips = session.get("clips") or []
    if not clips:
        raise HTTPException(
            status_code=400,
            detail="Aucun clip analysé : lancez l'analyse de la transcription avant l'extraction.",
        )
    if not payload.landscape and not payload.portrait:
        raise HTTPException(
            status_code=400,
            detail="Choisissez au moins un format d'export (paysage 16:9 ou portrait 9:16).",
        )
    if payload.clip_indexes is None:
        selected = clips
    else:
        try:
            selected = [clips[int(i)] for i in payload.clip_indexes]
        except (IndexError, TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Index de clip invalide : relancez l'analyse pour rafraîchir la liste.",
            )
    if not selected:
        raise HTTPException(status_code=400, detail="Aucun clip sélectionné pour l'extraction.")

    video = session_video(session)
    sid = session["id"]
    out_dir = assert_local_dir(CLIPS_DIR / sid)
    formats = [f for f, on in (("landscape", payload.landscape), ("portrait", payload.portrait)) if on]

    def work(job: Job) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        processor = VideoProcessor(out_dir)
        total = len(selected)
        produced: list[dict] = []
        errors: list[dict] = []
        written: list[Path] = []
        try:
            for i, clip in enumerate(selected, 1):
                raise_if_cancelled(job)
                base = safe_name(
                    f"{int(clip.get('index', i - 1)) + 1:02d}-{clip['title']}"
                )[:50].strip() or f"clip_{i}"
                job.set_progress(i - 1, total, f"Clip {i}/{total} : {clip['title']}")
                for fmt in formats:
                    if job.cancel_event.is_set():
                        raise JobCancelled()
                    try:
                        path = Path(
                            processor.clip_video(
                                str(video), clip["start_seconds"], clip["end_seconds"], base, fmt
                            )
                        )
                    except Exception as e:  # noqa: BLE001 - l'erreur est remontee a l'utilisateur
                        errors.append({"clip": clip["title"], "format": fmt, "error": readable(e)})
                        continue
                    if path.is_file() and path.stat().st_size > 0:
                        written.append(path)
                        produced.append(file_info(path, sid, clip, fmt))
                    else:
                        errors.append(
                            {
                                "clip": clip["title"],
                                "format": fmt,
                                "error": "FFmpeg n'a produit aucun fichier.",
                            }
                        )
                job.set_progress(i, total, f"Clip {i}/{total} terminé")
            raise_if_cancelled(job)
        except JobCancelled:
            for path in written:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        if not produced:
            raise RuntimeError(
                "Aucun clip produit : " + (errors[0]["error"] if errors else "entrée invalide.")
            )
        session["produced"] = produced
        save_session(session)
        return {
            "sid": sid,
            "files": produced,
            "errors": errors,
            "requested": total,
            "formats": formats,
            "output_folder": out_dir.name,
        }

    return {"job_id": create_job("clips_extract", work).id}


@router.get("/files/{sid}/{name}")
def get_clip_file(sid: str, name: str) -> FileResponse:
    if not SID_RE.match(sid):
        raise HTTPException(status_code=400, detail="Identifiant de session invalide.")
    path = assert_local_dir(CLIPS_DIR / sid / safe_name(name))
    if path.suffix.lower() != ".mp4":
        raise HTTPException(status_code=400, detail="Seuls les fichiers MP4 sont servis.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier de clip introuvable.")
    return FileResponse(path, media_type="video/mp4")
