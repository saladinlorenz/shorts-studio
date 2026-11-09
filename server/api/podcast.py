"""Routes Podcast : base de phrases et generation de video assemblee.

La logique metier reste portee par ``podcaster.py`` et ``database.py``
(telechargement yt-dlp, segmentation SRT, recherche de phrases, assemblage
FFmpeg). Le serveur ne fait que l'orchestrer dans des jobs et borner les
chemins ecrits au projet.
"""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import PhraseDatabase
from podcaster import Podcaster
from shortvideos.probe import ProbeError, probe_mp4

from ..jobs import Job, JobCancelled, create_job, raise_if_cancelled
from ..security import PODCAST_DIR, assert_local_dir, safe_name
from .clips import bridge_progress, clean_url, readable

router = APIRouter(prefix="/api/podcast", tags=["podcast"])

# Base Tkinter historique : dossier personnel, jamais ecrit par le serveur.
LEGACY_DIR = Path.home() / "podcast_db"
LEGACY_SKIP = ("temp", "output")


class AddVideoPayload(BaseModel):
    url: str
    speaker: str | None = None


class GeneratePayload(BaseModel):
    script: str
    altern: bool = True
    name: str = "generated_video"
    overwrite: bool = False


def as_float(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def database() -> PhraseDatabase:
    return PhraseDatabase(str(PODCAST_DIR))


def catalog_rows(db: PhraseDatabase) -> list[dict]:
    if not db.catalog_path.is_file():
        return []
    try:
        with open(db.catalog_path, "r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error) as e:
        raise HTTPException(status_code=400, detail=f"Catalogue illisible : {readable(e)}")


def clip_row(row: dict) -> dict:
    name = Path(str(row.get("clip", ""))).name
    return {
        "clip": name,
        "url": f"/api/podcast/files/{name}" if name else None,
        "speaker": str(row.get("speaker", ""))[:80],
        "phrase": str(row.get("phrase", ""))[:300],
        "start": as_float(row.get("start")),
        "end": as_float(row.get("end")),
        "duration": as_float(row.get("duration")),
        "source": str(row.get("source_video", ""))[:120],
    }


def legacy_stats() -> dict:
    """Statistiques de l'ancienne base (lecture seule, aucun ecrit hors projet)."""
    exists = LEGACY_DIR.is_dir()
    catalog = LEGACY_DIR / "catalog.csv"
    if not catalog.is_file():
        return {"exists": exists, "total_clips": 0, "speakers": 0}
    try:
        with open(catalog, "r", encoding="utf-8", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error):
        rows = []
    return {
        "exists": exists,
        "total_clips": len(rows),
        "speakers": len({str(r.get("speaker", "")) for r in rows}),
    }


@router.get("/stats")
def stats() -> dict:
    data = database().get_stats()
    speakers = [str(s)[:80] for s in (data.get("speakers") or [])]
    return {
        "total_clips": int(data.get("total_clips") or 0),
        "speakers": speakers[:100],
        "speaker_count": len(speakers),
        "folder": PODCAST_DIR.name,
        "legacy": legacy_stats(),
    }


@router.get("/clips")
def search_clips(speaker: str = "", q: str = "", limit: int = 50) -> dict:
    db = database()
    cap = max(1, min(200, int(limit)))
    if speaker:
        rows = db.get_clips_for_speaker(speaker)
    elif q:
        rows = db.search_word(q) or db.fuzzy_search(q, threshold=0.5)
    else:
        rows = catalog_rows(db)
    total = len(rows)
    return {"total": total, "shown": min(total, cap), "clips": [clip_row(r) for r in rows[:cap]]}


@router.post("/videos")
def add_video(payload: AddVideoPayload) -> dict:
    url = clean_url(payload.url)
    speaker = safe_name((payload.speaker or "").strip())[:60].strip() or None

    def work(job: Job) -> dict:
        log: list[str] = []
        podcaster = Podcaster(str(PODCAST_DIR))
        try:
            job.message = "Téléchargement et segmentation de la vidéo…"
            clips = podcaster.add_video(
                url, speaker_name=speaker, progress_callback=bridge_progress(job, log)
            )
            raise_if_cancelled(job)
        finally:
            temp = PODCAST_DIR / "temp"
            if temp.is_dir():
                shutil.rmtree(temp, ignore_errors=True)
        stats_data = podcaster.get_stats()
        return {
            "clips_created": len(clips),
            "total_clips": int(stats_data.get("total_clips") or 0),
            "speaker_count": len(stats_data.get("speakers") or []),
            "note": (
                None
                if clips
                else "Aucune phrase extraite : la vidéo n'a pas de sous-titres exploitables."
            ),
        }

    return {"job_id": create_job("podcast_add", work).id}


@router.post("/generate")
def generate(payload: GeneratePayload) -> dict:
    script = (payload.script or "").strip()
    if not script:
        raise HTTPException(
            status_code=400,
            detail="Texte à énoncer manquant : saisissez les phrases à assembler.",
        )
    db = database()
    if int(db.get_stats().get("total_clips") or 0) == 0:
        raise HTTPException(
            status_code=400,
            detail="Base de phrases vide : ajoutez d'abord une vidéo source dans la base.",
        )

    out_name = safe_name(payload.name)
    if not out_name.lower().endswith(".mp4"):
        out_name += ".mp4"
    out_path = assert_local_dir(PODCAST_DIR / "output" / out_name)
    if out_path.exists() and not payload.overwrite:
        raise HTTPException(
            status_code=409,
            detail={"message": f"Le fichier existe déjà : {out_name}", "code": "exists"},
        )
    altern = bool(payload.altern)

    def work(job: Job) -> dict:
        log: list[str] = []
        podcaster = Podcaster(str(PODCAST_DIR))
        tmp_path = out_path.with_name(f"{out_path.stem}.part.mp4")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.unlink(missing_ok=True)
        result = podcaster.build_video(
            script,
            output_path=str(tmp_path),
            altern=altern,
            progress_callback=bridge_progress(job, log),
        )
        if job.cancel_event.is_set():
            tmp_path.unlink(missing_ok=True)
            raise JobCancelled()
        if result is None or not tmp_path.is_file() or tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            last = log[-1] if log else "aucune étape rapportée"
            raise RuntimeError(
                "Aucune vidéo générée : aucune phrase de la base ne correspond au texte "
                f"(ou l'assemblage a échoué). Dernière étape : {last}"
            )
        if out_path.exists():
            out_path.unlink()
        tmp_path.replace(out_path)
        info = {
            "name": out_path.name,
            "url": f"/api/podcast/files/output/{out_path.name}",
            "size_bytes": out_path.stat().st_size,
            "width": None,
            "height": None,
            "duration": None,
            "unreadable": False,
        }
        try:
            probed = probe_mp4(str(out_path))
            info.update(
                {
                    "width": probed["width"],
                    "height": probed["height"],
                    "duration": probed["duration"],
                    "fps": probed["fps"],
                    "frames": probed["frames"],
                }
            )
        except (ProbeError, OSError):
            info["unreadable"] = True
        return info

    return {"job_id": create_job("podcast_generate", work).id}


@router.post("/legacy/import")
def import_legacy() -> dict:
    if not LEGACY_DIR.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Aucune ancienne base trouvée dans votre dossier personnel.",
        )
    if int(database().get_stats().get("total_clips") or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail="La base du projet contient déjà des phrases : l'import est réservé à une base vide.",
        )
    target = PODCAST_DIR

    def work(job: Job) -> dict:
        files = [
            p
            for p in LEGACY_DIR.rglob("*")
            if p.is_file() and not any(part in LEGACY_SKIP for part in p.relative_to(LEGACY_DIR).parts[:-1])
        ]
        total = len(files)
        if total == 0:
            raise RuntimeError("L'ancienne base ne contient aucun fichier à importer.")
        copied = 0
        failed: list[str] = []
        for i, src in enumerate(files, 1):
            raise_if_cancelled(job)
            dest = target / src.relative_to(LEGACY_DIR)
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied += 1
            except OSError as e:
                failed.append(f"{src.name} : {readable(e)}")
            job.set_progress(i, total, f"Import {i}/{total} : {src.name[:40]}")
        raise_if_cancelled(job)
        stats_data = database().get_stats()
        return {
            "copied": copied,
            "failed": failed[:10],
            "total_clips": int(stats_data.get("total_clips") or 0),
            "speaker_count": len(stats_data.get("speakers") or []),
        }

    return {"job_id": create_job("podcast_legacy_import", work).id}


@router.get("/files/{rel_path:path}")
def get_podcast_file(rel_path: str) -> FileResponse:
    parts = [safe_name(p) for p in rel_path.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise HTTPException(status_code=400, detail="Chemin de fichier invalide.")
    path = assert_local_dir(PODCAST_DIR.joinpath(*parts))
    if path.suffix.lower() != ".mp4":
        raise HTTPException(status_code=400, detail="Seuls les fichiers MP4 sont servis.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier podcast introuvable.")
    return FileResponse(path, media_type="video/mp4")
