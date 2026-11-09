"""Routes de la production par lots : CSV, plan, file, manifeste.

Le client n'envoie jamais de projets : il envoie un modele, un CSV importe et
un mapping, et le serveur reconstruit le plan a l'identique (il est
deterministe). Ainsi ce que l'utilisateur voit dans le plan est exactement ce
qui sera rendu, et un lot relance plus tard repart des memes donnees.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from shortvideos import batch as batch_mod

from .. import csv_source
from .. import folders as folders_mod
from .. import library as library_mod
from .. import queue as queue_mod
from ..security import BATCH_DIR, EXPORTS_DIR, assert_local_dir

router = APIRouter(prefix="/api/batch", tags=["batch"])

MAX_CSV_BYTES = 20 * 1024 * 1024  # un CSV de 20 Mo depasse largement MAX_ROWS


class PlanPayload(BaseModel):
    model: str
    csv_id: str
    mapping: dict[str, str] = {}
    options: dict[str, str] = {}
    name: str = "lot"
    overwrite: bool = False


def _template(model_id: str) -> dict:
    template = library_mod.get_project(model_id)
    if template.get("version") != 2:
        raise HTTPException(status_code=400, detail=f"Le modèle {model_id} n'est pas un projet version 2.")
    return template


def _assets() -> dict[str, list[dict]]:
    return {
        "video": folders_mod.assets_by_kind("video"),
        "audio": folders_mod.assets_by_kind("audio"),
        "image": folders_mod.assets_by_kind("image"),
    }


def _plan(payload: PlanPayload) -> dict:
    template = _template(payload.model)
    source = csv_source.load(payload.csv_id)
    return batch_mod.build_plan(
        template,
        source["rows"],
        payload.mapping,
        _assets(),
        payload.options or {"background": "auto", "music": "auto"},
    )


def _light(item: dict) -> dict:
    """Item du plan sans le projet complet : la table reste lisible en UI."""
    project = item["project"]
    return {
        "index": item["index"],
        "name": item["name"],
        "filename": item["filename"],
        "row_preview": item["row_preview"],
        "assets_used": item["assets_used"],
        "background_source": item["background_source"],
        "background_pass": item.get("background_pass"),
        "music_source": item["music_source"],
        "music_pass": item.get("music_pass"),
        "errors": item["errors"],
        "warnings": item["warnings"],
        "scenes": len(project.get("content", {}).get("scenes", [])),
        "duration": round(sum(float(s.get("duration", 0.0)) for s in project.get("content", {}).get("scenes", [])), 2),
        "seed": project.get("variation", {}).get("seed"),
    }


@router.get("/setup")
def setup() -> dict:
    """Ce dont la page Production a besoin pour afficher ses trois colonnes."""
    return {
        "models": library_mod.list_library(),
        "folders": [
            {
                "id": f["id"],
                "name": f["name"],
                "kind": f["kind"],
                "path": f["path"],
                "present": f["present"],
                "imported": f["imported"],
                "licence": f["licence"],
                "last_scan": f.get("last_scan"),
            }
            for f in folders_mod.list_roots()
        ],
        "assets": _assets(),
        "csv_limits": {"max_rows": csv_source.MAX_ROWS, "max_bytes": MAX_CSV_BYTES},
        "batch_dir": str(BATCH_DIR),
        "policy": batch_mod.POLICY,
    }


@router.get("/fields")
def fields(model: str) -> dict:
    return {"model": model, "fields": batch_mod.fillable_fields(_template(model))}


@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    model: str = Form(""),
) -> dict:
    payload = await file.read(MAX_CSV_BYTES + 1)
    if len(payload) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail=f"CSV trop lourd (max {MAX_CSV_BYTES // (1024 * 1024)} Mo).")
    stored = csv_source.store(payload, file.filename or "lot.csv")
    response = {
        "csv_id": stored["id"],
        "file": stored["file"],
        "columns": stored["columns"],
        "rows": stored["rows"],
        "preview": stored["rows"][:20],
        "row_count": len(stored["rows"]),
        "encoding": stored["encoding"],
        "delimiter": stored["delimiter"],
        "warnings": stored["warnings"],
    }
    if model:
        template = _template(model)
        field_list = batch_mod.fillable_fields(template)
        response["fields"] = field_list
        response["suggested_mapping"] = batch_mod.suggest_mapping(stored["columns"], field_list)
    return response


@router.get("/csv/{csv_id}")
def csv_detail(csv_id: str, preview_rows: int = 20) -> dict:
    data = csv_source.preview(csv_id, limit=preview_rows)
    return {
        "csv_id": csv_id,
        "meta": data["meta"],
        "columns": data["columns"],
        "rows": data["rows"],
        "encoding": data["encoding"],
        "delimiter": data["delimiter"],
        "warnings": data["warnings"],
    }


@router.post("/plan")
def plan(payload: PlanPayload) -> dict:
    result = _plan(payload)
    return {
        "model": payload.model,
        "csv_id": payload.csv_id,
        "mapping": payload.mapping,
        "options": payload.options,
        "summary": result["summary"],
        "warnings": result["warnings"],
        "policy": result["policy"],
        "items": [_light(item) for item in result["items"]],
    }


@router.post("/line")
def line(payload: PlanPayload, position: int = 1) -> dict:
    """Projet complet d'une ligne, pour l'afficher dans l'aperçu avant lot."""
    if position < 1:
        raise HTTPException(status_code=400, detail="Numéro de ligne invalide.")
    result = _plan(payload)
    if position > len(result["items"]):
        raise HTTPException(status_code=404, detail=f"Le plan n'a que {len(result['items'])} ligne(s).")
    item = result["items"][position - 1]
    return {"item": _light(item), "project": item["project"]}


@router.post("/start")
def start(payload: PlanPayload) -> dict:
    """Crée le lot depuis le plan (reconstruit à l'identique) et lance le rendu."""
    result = _plan(payload)
    renderable = [item for item in result["items"] if not item["errors"]]
    if not renderable:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Aucune ligne du plan n'est renderisable.",
                "invalid_rows": result["summary"]["invalid_rows"],
                "errors": [e for item in result["items"] for e in item["errors"]][:20],
            },
        )
    batch = queue_mod.create_batch(
        result,
        name=payload.name,
        model_id=payload.model,
        csv_id=payload.csv_id,
        mapping=payload.mapping,
        options=payload.options,
        overwrite=payload.overwrite,
    )
    started = queue_mod.start_batch(batch["id"])
    return {
        "batch": started["batch"],
        "job_id": started["job_id"],
        "plan_summary": result["summary"],
        "plan_warnings": result["warnings"],
    }


@router.get("")
def batches(limit: int = 30) -> dict:
    return {"batches": queue_mod.list_batches(limit=min(max(1, limit), 200))}


@router.get("/{batch_id}")
def batch_detail(batch_id: str, items: bool = False, status: str = "") -> dict:
    _check_id(batch_id)
    return queue_mod.get_batch(batch_id, items=items, status=status)


@router.post("/{batch_id}/start")
def batch_start(batch_id: str) -> dict:
    _check_id(batch_id)
    return queue_mod.start_batch(batch_id)


@router.post("/{batch_id}/cancel")
def batch_cancel(batch_id: str) -> dict:
    _check_id(batch_id)
    return queue_mod.cancel(batch_id)


@router.post("/{batch_id}/retry")
def batch_retry(batch_id: str) -> dict:
    _check_id(batch_id)
    retried = queue_mod.retry_failed(batch_id)
    return {**retried, "started": queue_mod.start_batch(batch_id)["job_id"]}


@router.get("/{batch_id}/manifest")
def batch_manifest(batch_id: str, format: str = "json") -> dict:
    _check_id(batch_id)
    return queue_mod.write_manifest(batch_id, format)


@router.get("/{batch_id}/manifest/file")
def batch_manifest_file(batch_id: str, format: str = "json") -> FileResponse:
    """Téléchargement du manifeste : le chemin est produit par le serveur."""
    _check_id(batch_id)
    written = queue_mod.write_manifest(batch_id, format)
    path = Path(str(written["manifest"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Manifeste introuvable : régénérez-le.")
    media = "text/csv" if format == "csv" else "application/json"
    return FileResponse(path, filename=path.name, media_type=media)


@router.get("/{batch_id}/file")
def batch_file(batch_id: str, position: int = 1) -> FileResponse:
    """Relit la vidéo d'une ligne : le nom vient de la file, jamais du client."""
    _check_id(batch_id)
    items = queue_mod.get_batch(batch_id, items=True)["items"]
    item = next((i for i in items if int(i["position"]) == position), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Ligne introuvable dans ce lot.")
    if item["status"] != "done" or not item.get("output_path"):
        raise HTTPException(status_code=404, detail="Cette ligne n'a pas encore de fichier rendu.")
    # le nom est retrouvé à partir du chemin enregistré par le worker
    path = Path(str(item["output_path"]))
    file_path = assert_local_dir(EXPORTS_DIR / path.name)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Fichier de sortie supprimé.")
    return FileResponse(file_path, media_type="video/mp4")


@router.delete("/{batch_id}")
def batch_forget(batch_id: str) -> dict:
    _check_id(batch_id)
    return queue_mod.forget_batch(batch_id)


def _check_id(batch_id: str) -> None:
    if not batch_id or not batch_id.isalnum():
        raise HTTPException(status_code=400, detail="Identifiant de lot invalide.")
