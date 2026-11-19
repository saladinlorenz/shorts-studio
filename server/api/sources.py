"""Routes des banques de contenu (clés API côté serveur uniquement).

Comme les réglages de l'assistant : les clés ne sont jamais renvoyées, seul
un indice des 4 derniers caractères sort d'ici. Le test de connexion est
exécuté par le serveur vers l'URL fixe du catalogue — le navigateur ne
choisit ni la destination ni les paramètres.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from .. import sources

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str | None = None
    enabled: bool | None = None
    clear_key: bool | None = None


@router.get("")
def get_sources() -> dict:
    return sources.list_sources()


@router.post("/{source_id}")
def update_source(source_id: str, payload: SourceUpdate) -> dict:
    try:
        state = sources.save(
            source_id,
            key=payload.key,
            enabled=payload.enabled,
            clear_key=bool(payload.clear_key),
        )
    except sources.UnknownSource as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"provider": state}


@router.post("/{source_id}/test")
def test_source(source_id: str) -> dict:
    try:
        return sources.test_connection(source_id)
    except sources.UnknownSource as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None