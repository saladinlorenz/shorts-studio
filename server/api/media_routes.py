"""Routes des médias : import (upload) et service limité."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from .. import media as media_mod

router = APIRouter(prefix="/api/media", tags=["media"])


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    source: str = Form(""),
    licence: str = Form(""),
) -> dict:
    """Import d'un media. Provenance et licence sont des champs simples :
    une licence non renseignee est enregistree comme « inconnue »."""
    return await media_mod.save_upload(file, source=source, licence=licence)


@router.get("/{media_id}")
def get_media(media_id: str) -> FileResponse:
    path = media_mod.resolve_media(media_id)
    media_type = None
    suffix = path.suffix.lower()
    if suffix in {".png"}:
        media_type = "image/png"
    elif suffix in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif suffix in {".webp"}:
        media_type = "image/webp"
    elif suffix in {".gif"}:
        media_type = "image/gif"
    elif suffix in {".mp4"}:
        media_type = "video/mp4"
    elif suffix in {".webm"}:
        media_type = "video/webm"
    elif suffix in {".mov"}:
        media_type = "video/quicktime"
    return FileResponse(path, media_type=media_type, filename=None)
