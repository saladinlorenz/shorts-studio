"""Routes du paquet de connaissances Remotion (lecture seule).

L'agent de l'app (cote serveur, cle Groq jamais exposee au frontend) lit ces
routes pour obtenir les fiches de bonnes pratiques avant d'ecrire du code
de composition.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import skills as skills_mod

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
def catalog() -> dict:
    return {
        "skills": skills_mod.list_skills(),
        "provenance": skills_mod.provenance(),
    }


@router.get("/context")
def context(
    names: str | None = Query(default=None, description="identifiants separes par des virgules"),
    max_chars: int = Query(default=60_000, ge=1_000, le=400_000),
) -> dict:
    wanted = [n.strip() for n in names.split(",")] if names else None
    block = skills_mod.build_context(wanted, max_chars)
    return {"context": block, "chars": len(block), "requested": wanted}


@router.get("/doc/{rel_path:path}")
def document(rel_path: str) -> dict:
    return skills_mod.read_document(rel_path)


@router.get("/{skill_id}")
def skill(skill_id: str) -> dict:
    if not skill_id or any(ch in skill_id for ch in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de competence invalide.")
    entry = skills_mod.find_skill(skill_id)
    doc = skills_mod.read_document(entry["entry"])
    return {"skill": entry, "content": doc["content"], "truncated": doc["truncated"]}
