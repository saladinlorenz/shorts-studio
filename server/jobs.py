"""Registre de jobs : tâches longues hors des threads de requête.

Principe :
- ``create_job(kind, target, ...)`` lance le travail dans un thread ;
- le travail remonte sa progression par un callback (fonction existante) ;
- le frontend interroge ``GET /api/jobs/<id>`` (polling) ;
- ``cancel`` pose un ``threading.Event`` que le travail est censé respecter.

Aucun widget Tkinter ni aucune requête HTTP n'est manipulé depuis le
thread de travail : seul l'état du job est mis à jour (verrou).
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Any, Callable

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}

# Un job reste consultable au maximum cette durée après sa fin (secondes).
JOB_TTL = 3600


class Job:
    """Etat d'une tache longue, partage entre le worker et le polling."""

    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status = "running"  # running | done | error | cancelled
        self.progress = 0.0  # 0.0 .. 1.0
        self.message = ""
        self.result: Any = None
        self.error = ""
        self.cancel_event = threading.Event()
        self.started_at = time.time()
        self.finished_at: float | None = None

    def set_progress(self, current: int, total: int, message: str = "") -> None:
        with _LOCK:
            self.progress = (current / total) if total else 0.0
            self.message = message or f"{current}/{total}"

    def snapshot(self) -> dict:
        with _LOCK:
            return {
                "id": self.id,
                "kind": self.kind,
                "status": self.status,
                "progress": round(self.progress, 4),
                "message": self.message,
                "result": self.result,
                "error": self.error,
                "cancelable": self.status == "running",
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


def create_job(kind: str, work: Callable[[Job], Any]) -> Job:
    """Lance ``work(job)`` dans un thread secondaire et l'enregistre.

    ``work`` recoit le Job : il doit appeler ``job.set_progress(...)``
    pour la progression et verifier ``job.cancel_event`` pour annuler.
    Le retour de ``work`` devient ``job.result`` ; toute exception
    devient ``job.error`` avec le statut ``error``.
    """
    job = Job(kind)
    _JOBS[job.id] = job

    def runner() -> None:
        try:
            result = work(job)
            with _LOCK:
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                    job.message = "Annulé."
                else:
                    job.status = "done"
                    job.progress = 1.0
                    job.result = result
                    job.message = "Terminé."
        except JobCancelled:
            with _LOCK:
                job.status = "cancelled"
                job.message = "Annulé."
        except Exception as e:  # noqa: BLE001 - toute erreur est exposée au client
            with _LOCK:
                job.status = "error"
                job.error = f"{e}"
                job.message = "Erreur."
                job.result = {"traceback": traceback.format_exc()}
        finally:
            job.finished_at = time.time()
            _gc_jobs()

    threading.Thread(target=runner, daemon=True, name=f"job-{kind}").start()
    return job


class JobCancelled(Exception):
    """Levee par un worker quand l'utilisateur a demande l'annulation."""


def get_job(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def list_jobs(limit: int = 20) -> list[dict]:
    """Instantanés des tâches les plus récentes (toutes pages confondues)."""
    with _LOCK:
        ordered = sorted(_JOBS.values(), key=lambda j: j.started_at, reverse=True)[: max(1, min(50, limit))]
    # snapshot() prend le même verrou : l'appeler hors du bloc évite tout interblocage
    return [job.snapshot() for job in ordered]


def cancel_job(job_id: str) -> Job | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None and job.status == "running":
            job.cancel_event.set()
            job.message = "Annulation demandée…"
        return job


def _gc_jobs() -> None:
    """Supprime les jobs terminés depuis plus de JOB_TTL secondes."""
    now = time.time()
    stale = [
        jid
        for jid, j in _JOBS.items()
        if j.finished_at is not None and now - j.finished_at > JOB_TTL
    ]
    for jid in stale:
        _JOBS.pop(jid, None)


def raise_if_cancelled(job: Job) -> None:
    """A appeler regulierement dans un worker pour respecter l'annulation."""
    if job.cancel_event.is_set():
        raise JobCancelled()
