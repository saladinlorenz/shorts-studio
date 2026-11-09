"""Routes des jobs (suivi des tâches longues)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..jobs import cancel_job, get_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    return job.snapshot()


@router.post("/{job_id}/cancel")
def job_cancel(job_id: str) -> dict:
    job = cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    return job.snapshot()
