"""Routes de l'assistant IA local.

Le transport (LLM) et la logique restent dans ``server/agent/`` ; ici, uniquement
des bornes d'entrée, des jobs annulables et des réponses explicables.

Aucune route n'applique une modification : ``/accept`` renvoie le projet
candidat que l'éditeur applique lui-même, dans son historique Annuler/Rétablir,
après un clic utilisateur.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from shortvideos import schema

from .. import jobs, settings
from ..agent import autopilot, llm_client, proposals, retrieval, service
from ..security import assert_local_dir
from ..settings import llm_config

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AskPayload(BaseModel):
    message: str
    project: dict | None = None
    project_name: str = ""
    revision: str = ""
    selection: dict | None = None
    history: list[dict] = []
    csv_columns: list[str] = []
    mode: str = "design"


class AcceptPayload(BaseModel):
    project: dict | None = None
    rebase: bool = False


class ExecutePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    confirmation: str
    project: dict | None = None


class CheckPayload(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    pin: str | None = None


class SearchPayload(BaseModel):
    query: str
    limit: int = 5
    max_chars: int = 6000


def _draft_cfg(payload: CheckPayload) -> dict:
    """Configuration demandée par le formulaire, avant enregistrement.

    Un fournisseur cloud garde son URL fixe ; une clé saisie n'est utilisée que
    pour cette vérification, jamais stockée ni renvoyée ici.
    """
    cfg = llm_config()
    stored = settings.load_settings()
    provider = (payload.provider or cfg["provider"]).strip().lower()
    if provider not in settings.PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Fournisseur inconnu : {payload.provider!r} "
            f"(choix : {', '.join(settings.PROVIDERS)}).",
        )
    if provider in settings.CLOUD_BASE_URLS:
        base_url = settings.CLOUD_BASE_URLS[provider]
    elif payload.base_url is not None:
        from .settings import _check_base_url

        base_url = _check_base_url(payload.base_url.strip())
    else:
        base_url = str(stored.get("llm_local_base_url") or "").strip().rstrip("/")
    model = (payload.model or "").strip() or str(stored.get(f"llm_{provider}_model") or "").strip()
    api_key = (
        (payload.api_key or "").strip() or str(stored.get(f"llm_{provider}_api_key") or "").strip()
    )
    pin = ""
    if provider == "local":
        pin = (payload.pin or "").strip() or str(stored.get("llm_local_pin") or "").strip()
    return {**cfg, "provider": provider, "base_url": base_url, "model": model,
            "api_key": api_key, "pin": pin}


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, service.RevisionConflict):
        return HTTPException(status_code=409, detail={
            "message": str(error),
            "current_revision": error.current_revision,
            "rebase_available": True,
        })
    if isinstance(error, service.AgentUnavailable):
        return HTTPException(status_code=424, detail=str(error))
    if isinstance(error, proposals.ProposalError):
        return HTTPException(status_code=400, detail={"message": str(error), "errors": error.errors})
    if isinstance(error, llm_client.LLMError):
        return HTTPException(status_code=502, detail=str(error))
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail="Proposition expirée ou inconnue.")
    return HTTPException(status_code=500, detail=f"Assistant indisponible : {error}")


@router.get("/status")
def status() -> dict:
    return service.status()


@router.get("/capabilities")
def capabilities_route() -> dict:
    return service.manifest()


@router.post("/index")
def rebuild_index(force: bool = False) -> dict:
    try:
        return service.ensure_index() if not force else retrieval.build(force=True)
    except Exception as e:  # noqa: BLE001 - l'index ne doit jamais casser le studio
        return {"built": False, "error": str(e)[:200]}


@router.post("/check")
def check(payload: CheckPayload) -> dict:
    """Vérification de connexion : ce que le serveur répond réellement."""
    cfg = _draft_cfg(payload)
    try:
        return llm_client.check_connection(cfg)
    except llm_client.LLMError as e:
        return {"ok": False, "error": str(e), "error_kind": e.kind, "capabilities": {}, "models": []}


@router.post("/models")
def models(payload: CheckPayload) -> dict:
    cfg = _draft_cfg(payload)
    try:
        return {"models": llm_client.list_models(cfg), "provider": cfg["provider"]}
    except llm_client.LLMError as e:
        raise _http_error(e)


@router.post("/search")
def search(payload: SearchPayload) -> dict:
    """Recherche documentaire bornée (panneau technique, débogage des sources)."""
    service.ensure_index()
    try:
        passages = retrieval.search(payload.query, limit=payload.limit, max_chars=payload.max_chars)
    except retrieval.RetrievalUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {
        "query": payload.query,
        "engine": retrieval.status()["engine"],
        "passages": [
            {k: p[k] for k in ("id", "path", "source", "version", "title", "score", "truncated")}
            | {"excerpt": p["text"][:400]}
            for p in passages
        ],
    }


@router.post("/ask")
def ask(payload: AskPayload) -> dict:
    """Lance une demande dans un job annulable (polling /api/jobs/<id>)."""
    cfg = llm_config()
    ready, reason = llm_client.is_ready(cfg)
    if not ready:
        raise HTTPException(status_code=424, detail=reason)
    if payload.project is not None and payload.project.get("version") not in (schema.SCHEMA_VERSION_V2, 1):
        raise HTTPException(status_code=400, detail="Le projet transmis n'est pas un projet v2.")

    data = payload.model_dump()

    def work(job: jobs.Job) -> dict:
        return service.run_request(job, data)

    job = jobs.create_job("agent", work)
    return {"job_id": job.id, "status": job.status}


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, preview: bool = False) -> dict:
    record = service.get_record(proposal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Proposition expirée ou inconnue : relancez la demande.")
    view = proposals.public_view(record["proposal"])
    if preview:
        # Aperçu demandé par l'utilisateur, en lecture seule : le candidat n'est
        # jamais appliqué ni enregistré par cette route.
        candidate = record["proposal"].get("candidate")
        view["candidate"] = candidate if isinstance(candidate, dict) else None
    return {"proposal": view}


@router.post("/proposals/{proposal_id}/accept")
def accept(proposal_id: str, payload: AcceptPayload) -> dict:
    try:
        result = service.accept(proposal_id, payload.project, rebase=payload.rebase)
    except Exception as e:  # noqa: BLE001 - toutes les causes sont traduites en HTTP clair
        raise _http_error(e)
    record = service.get_record(proposal_id)
    if record is not None:
        record["proposal"]["status"] = "accepted"
    return result


@router.post("/proposals/{proposal_id}/execute")
def execute(proposal_id: str, payload: ExecutePayload) -> dict:
    try:
        return service.execute_action(proposal_id, payload.confirmation, payload.project)
    except Exception as exc:
        raise _http_error(exc)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str) -> dict:
    try:
        return service.reject(proposal_id)
    except Exception as exc:  # noqa: BLE001 - mêmes causes HTTP que accept/execute
        raise _http_error(exc)


# --------------------------------------------------------------------------- #
# Autopilote : plan validé par l'assistant, exécuté par le serveur après un clic
# --------------------------------------------------------------------------- #

class AutopilotPlanPayload(BaseModel):
    message: str
    history: list[dict] = []


class AutopilotStartPayload(BaseModel):
    proposal_id: str = ""
    job_id: str = ""


@router.post("/autopilot/plan")
def autopilot_plan(payload: AutopilotPlanPayload) -> dict:
    """Demande de plan complet (script → design → voix → export), job annulable."""
    cfg = llm_config()
    ready, reason = llm_client.is_ready(cfg)
    if not ready:
        raise HTTPException(status_code=424, detail=reason)
    data = {
        "message": payload.message,
        "history": payload.history,
        "mode": "autopilot",
        "project": None,
        "project_name": "",
    }

    def work(job: jobs.Job) -> dict:
        return service.run_request(job, data)

    job = jobs.create_job("agent", work)
    return {"job_id": job.id, "status": job.status}


@router.post("/autopilot/start")
def autopilot_start(payload: AutopilotStartPayload) -> dict:
    """Le clic unique : démarre le plan proposé, ou reprend un plan interrompu."""
    try:
        plan_id = autopilot.start(
            proposal_id=payload.proposal_id.strip(), job_id=payload.job_id.strip()
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job_id": plan_id, "status": "running"}


@router.post("/autopilot/{job_id}/cancel")
def autopilot_cancel(job_id: str) -> dict:
    state = autopilot.cancel(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Plan autopilote introuvable.")
    return state


@router.get("/autopilot/{job_id}")
def autopilot_status(job_id: str) -> dict:
    state = autopilot.status(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Plan autopilote introuvable.")
    return state


@router.get("/autopilot/{job_id}/file")
def autopilot_file(job_id: str) -> FileResponse:
    """Vidéo finale : le nom vient de l'état persisté, jamais du client."""
    path = autopilot.video_path(job_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="Vidéo finale introuvable (plan non terminé ou fichier supprimé).",
        )
    return FileResponse(assert_local_dir(path), media_type="video/mp4")


@router.get("/autopilot/{job_id}/format/{name}")
def autopilot_format_file(job_id: str, name: str) -> FileResponse:
    """Format social dérivé (1:1, 16:9) : nom validé contre l'état persisté."""
    path = autopilot.format_path(job_id, name)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="Format introuvable (plan non terminé ou fichier supprimé).",
        )
    return FileResponse(assert_local_dir(path), media_type="video/mp4")
