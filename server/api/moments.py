"""Routes des moments forts : etat des fournisseurs, analyse, puis generation a la demande.

Deux families d'endpoints, separees par le principe du produit :

- ``/analyze`` lance un job et ne renvoie qu'un identifiant : la transcription peut
  durer plusieurs minutes, et elle n'ecrit rien tant qu'elle n'est pas finie ;
- ``/{id}/generate`` est le seul chemin qui cree un projet de travail. L'utilisateur
  clique, on decaisse : rien ici ne remplace un projet sans ``overwrite``.

Aucun chemin disque ne circule : la source est une reference ``media://`` et les
clefs API ne sortent jamais du serveur (seuls les booleens d'etat remontent).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import moments as moments_mod

router = APIRouter(prefix="/api/moments", tags=["moments"])


class AnalyzePayload(BaseModel):
    source: str = ""
    provider: str = ""
    api_key_source: str = "asr"
    model: str = ""
    language: str = ""
    min_seconds: float | None = None
    max_seconds: float | None = None
    top: int | None = None


class RecomputePayload(BaseModel):
    min_seconds: float | None = None
    max_seconds: float | None = None
    top: int | None = None


class GeneratePayload(BaseModel):
    moment_id: str = ""
    brand_id: str = ""
    handle: str = ""
    source_title: str = ""
    use_source_thumbnail: bool = True
    overwrite: bool = False


def _check_id(analysis_id: str) -> None:
    if not analysis_id or not analysis_id.isalnum():
        raise HTTPException(status_code=400, detail="Identifiant d'analyse invalide.")


def _check_moment_id(moment_id: str) -> str:
    cleaned = str(moment_id or "").strip()
    if not cleaned or not cleaned.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Identifiant de moment invalide.")
    return cleaned


@router.get("")
def list_analyses() -> dict:
    return {"analyses": moments_mod.list_analyses()}


@router.get("/providers")
def providers() -> dict:
    """Choix reels de transcription, avec la raison ecrite quand une voie est fermee."""
    return moments_mod.providers_state()


@router.post("/analyze")
def analyze(payload: AnalyzePayload) -> dict:
    job = moments_mod.analyze_create_job(
        payload.source,
        provider=payload.provider,
        api_key_source=payload.api_key_source,
        model=payload.model,
        language=payload.language,
        min_seconds=payload.min_seconds,
        max_seconds=payload.max_seconds,
        top=payload.top,
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/{analysis_id}")
def read_analysis(analysis_id: str) -> dict:
    _check_id(analysis_id)
    return moments_mod.get_analysis(analysis_id)


@router.post("/{analysis_id}/recompute")
def recompute(analysis_id: str, payload: RecomputePayload) -> dict:
    """Relance la detection sur la transcription deja stockee : aucun nouvel appel ASR."""
    _check_id(analysis_id)
    return moments_mod.recompute(
        analysis_id,
        min_seconds=payload.min_seconds,
        max_seconds=payload.max_seconds,
        top=payload.top,
    )


@router.post("/{analysis_id}/generate")
def generate(analysis_id: str, payload: GeneratePayload) -> dict:
    """Le clic qui transforme un moment en projet + extrait audio + miniature + .srt."""
    _check_id(analysis_id)
    moment_id = _check_moment_id(payload.moment_id)
    return moments_mod.generate_project(
        analysis_id,
        moment_id,
        brand_id=payload.brand_id,
        handle=payload.handle,
        source_title=payload.source_title,
        use_source_thumbnail=payload.use_source_thumbnail,
        overwrite=payload.overwrite,
    )


@router.delete("/{analysis_id}")
def delete_analysis(analysis_id: str) -> dict:
    _check_id(analysis_id)
    return moments_mod.delete_analysis(analysis_id)
