"""Routes du studio : modeles, polices sous licence, preparation du rendu.

Le frontend ne decide pas de la chronologie ni des ressources : il demande au
serveur le projet resollu (frames absolues, URLs medias, polices verifiees) et
l'utilise tel quel dans le Remotion Player. C'est le meme objet que celui que
recevra le navigateur de rendu, done l'aperçu et l'export partagent leur
source de verite.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel

from shortvideos import effects as effects_mod
from shortvideos import fonts as fonts_mod
from shortvideos import schema
from shortvideos import resolve as resolve_mod

from .. import media as media_mod
from .. import render as render_mod
from ..security import MEDIA_DIR

router = APIRouter(prefix="/api/studio", tags=["studio"])

MODEL_INFO = {
    "quote_cinematic": {
        "id": "quote_cinematic",
        "label": "Citation cinématique",
        "description": (
            "Trois scenes : accroche revelée par masque, citation animée mot à mot "
            "avec mots mis en valeur, signature de marque."
        ),
        "version": schema.MODELS["quote_cinematic"],
        "recommended_duration": [12.0, 15.0],
        "aspect_ratios": ["1080x1920", "1080x1080", "1920x1080"],
        "editable": [
            "textes des calques", "mots mis en valeur", "police et poids par calque",
            "taille, interligne, chasse, alignement", "couleurs et palette",
            "ombre, contour", "position et largeur du bloc", " duree de scene",
            "effet d'entree et de sortie", "unite d'animation (bloc / ligne / mot)",
            "decalage entre unites", "courbe et ressort", "fond image ou video",
            "logo et nom de marque", "resolution, fps, graine",
            "effets visuels par calque et par scene (catalogue /api/studio/effects)",
        ],
        "limits": [
            "Audio mixé au rendu (musique + voix, volumes et fondus) ; pas de calage par markers.",
            "Fond video : lecture silencieuse, sans decalage temporel.",
            "Le debordement de texte est mesure dans le navigateur, pas anticipe serveur.",
            "Effets : au plus 4 par calque ou scene, sans 3D reelle ni LUT externe.",
        ],
    },
}


@router.get("/effects")
def list_effects() -> dict:
    """Catalogue des effets reels : la meme liste sert a l'editeur et a l'assistant."""
    return effects_mod.manifest()


@router.get("/models")
def list_models() -> dict:
    return {"models": list(MODEL_INFO.values()), "default": "quote_cinematic"}


@router.get("/fonts")
def list_fonts() -> dict:
    families = fonts_mod.families()
    return {
        "families": families,
        "missing_files": fonts_mod.missing_files(),
        "catalog": str(fonts_mod.CATALOG_PATH.relative_to(fonts_mod.ROOT)),
    }


@router.get("/default")
def default_project(model: str = "quote_cinematic") -> dict:
    try:
        project = schema.new_project(model)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"project": project}


class PreparePayload(BaseModel):
    project: dict


@router.post("/prepare")
def prepare(payload: PreparePayload) -> dict:
    """Resollu + valide +pret pour le Player : la preparation du rendu.

    Retourne le projet avec les URLs de rendu (celles que verra le navigateur
    de rendu) et le bloc ``resolved`` inspectable (frames absolues, graine,
    version du modele, ressources).
    """
    project = payload.project
    version = project.get("version")
    if version == 1:
        raise HTTPException(
            status_code=400,
            detail="Projet en version 1 : convertissez-le d'abord vers la version 2.",
        )
    if version != schema.SCHEMA_VERSION_V2:
        raise HTTPException(status_code=400, detail=f"Version de projet non prise en charge : {version!r}.")

    errors, warnings = media_mod.validate_project_refs(project)
    try:
        props = render_mod.prepare_for_render(project)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    licences = []
    for asset in props.get("resolved", {}).get("assets", []):
        ref = asset.get("ref", "")
        if ref.startswith("media://"):
            media_id = ref[len("media://"):]
            prov = media_mod.provenance_of(media_id)
            licences.append(
                {
                    "ref": ref,
                    "kind": asset.get("kind", ""),
                    "licence": prov.get("licence", "inconnue"),
                    "source": prov.get("source", ""),
                    "declared": prov.get("declared", False),
                }
            )
    unknown = [item for item in licences if item["licence"].strip().lower() in {"", "inconnue"}]
    if unknown:
        warnings.append(
            f"{len(unknown)} media(s) sans licence declaree : verifiez le droit d'utilisation "
            "avant livraison (champ licence dans l'import)."
        )

    return {
        "project": props,
        "resolved": props.get("resolved", {}),
        "errors": errors,
        "warnings": warnings,
        "licences": licences,
        "composition": render_mod.composition_id_of(project) if not errors else None,
    }


class UpgradePayload(BaseModel):
    project: dict


@router.post("/upgrade")
def upgrade(payload: UpgradePayload) -> dict:
    """Conversion explicite v1 -> v2, avec la liste de ce qui a change."""
    if payload.project.get("version") != 1:
        raise HTTPException(status_code=400, detail="Seuls les projets v1 sont convertibles.")
    try:
        project, notes = schema.upgrade_v1_to_v2(payload.project)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    errors, warnings = media_mod.validate_project_refs(project)
    return {"project": project, "notes": notes, "errors": errors, "warnings": warnings}


class ProvenancePayload(BaseModel):
    media_id: str
    source: str = ""
    licence: str = ""


@router.post("/provenance")
def set_provenance(payload: ProvenancePayload) -> dict:
    """Enregistre provenance et licence d'un media (champs simples)."""
    media_id = payload.media_id.strip()
    if not media_id or any(c in media_id for c in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de média invalide.")
    if not list(MEDIA_DIR.glob(f"{media_id}.*")):
        raise HTTPException(status_code=404, detail="Média introuvable.")
    existing = media_mod.provenance_of(media_id)
    data = {
        **existing,
        "id": media_id,
        "source": (payload.source or "").strip() or existing.get("source", "import local"),
        "licence": (payload.licence or "").strip() or "inconnue",
    }
    media_mod.write_provenance(media_id, data)
    return {"media_id": media_id, "source": data["source"], "licence": data["licence"]}


@router.get("/provenance/{media_id}")
def get_provenance(media_id: str) -> dict:
    if not media_id or any(c in media_id for c in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de média invalide.")
    return media_mod.provenance_of(media_id)


@router.post("/inspect")
def inspect(payload: PreparePayload) -> dict:
    """Projet resollu seul, pour verification manuelle des reglages applies."""
    try:
        resolved = resolve_mod.resolve(payload.project)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"resolved": resolved.get("resolved", {})}
