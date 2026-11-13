from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from .. import jobs, media, settings

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
MediaRef = Annotated[str, StringConstraints(pattern=r"^media://[a-zA-Z0-9_-]{1,80}$")]
Prompt = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ProjectReview(Params):
    prompt: Prompt = "Vérifie la lisibilité, le contraste et le cadrage ; corrige les défauts visibles."


class ProjectExport(Params):
    name: Identifier


class ClipsDownload(Params):
    url: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class ClipsAnalyze(Params):
    sid: Identifier
    num_clips: int = Field(default=5, ge=1, le=20)


class ClipsExtract(Params):
    sid: Identifier
    clip_indexes: list[Annotated[int, Field(ge=0)]] = Field(min_length=1, max_length=20)
    landscape: bool = True
    portrait: bool = True


class TtsDownload(Params):
    voice_id: Identifier


class TtsGenerate(TtsDownload):
    text: Annotated[str, StringConstraints(min_length=1, max_length=5000)]
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class BatchTarget(Params):
    batch_id: Identifier


class MomentsAnalyze(Params):
    source: MediaRef
    provider: Literal["local", "groq"] = "local"
    language: Annotated[str, StringConstraints(max_length=8)] = ""


class MomentsGenerate(Params):
    analysis_id: Identifier
    moment_id: Identifier


class SettingsUpdate(Params):
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=256, le=8000)
    timeout: int | None = Field(default=None, ge=15, le=300)
    max_tool_calls: int | None = Field(default=None, ge=0, le=8)
    max_repairs: int | None = Field(default=None, ge=0, le=3)
    stream: bool | None = None


SCHEMAS = {
    "project_review": (ProjectReview, "Auditer et corriger le projet sans vision"),
    "project_export": (ProjectExport, "Exporter le projet en MP4"),
    "clips_download": (ClipsDownload, "Télécharger une vidéo YouTube"),
    "clips_analyze": (ClipsAnalyze, "Analyser la transcription des Clips"),
    "clips_extract": (ClipsExtract, "Extraire les Clips sélectionnés"),
    "tts_download": (TtsDownload, "Télécharger une voix du catalogue"),
    "tts_generate": (TtsGenerate, "Synthétiser une voix off locale"),
    "batch_start": (BatchTarget, "Démarrer un lot déjà préparé"),
    "batch_retry": (BatchTarget, "Relancer les échecs d’un lot"),
    "batch_cancel": (BatchTarget, "Annuler un lot"),
    "delivery_package": (BatchTarget, "Préparer le ZIP de livraison"),
    "moments_analyze": (MomentsAnalyze, "Transcrire et détecter les moments forts"),
    "moments_generate": (MomentsGenerate, "Créer un projet depuis un moment fort"),
    "settings_update": (SettingsUpdate, "Modifier les paramètres non secrets de l’assistant"),
}


class ActionError(ValueError):
    pass


def catalog(name: str = "") -> dict:
    if name and name not in SCHEMAS:
        raise ActionError("Action inconnue.")
    return {
        "actions": [
            {"name": key, "label": label, **({"parameters": model.model_json_schema()} if name else {})}
            for key, (model, label) in SCHEMAS.items() if not name or key == name
        ],
        "protocol": 'type=studio_action, action={"name":"…","params":{…}} ; confirmation humaine obligatoire.',
        "note": "Consulter get_action_catalog avec name pour les paramètres exacts. Aucun shell, code généré, secret, suppression ou publication externe.",
    }


def _youtube_url(value: str) -> str:
    parts = urlsplit(value)
    if (parts.scheme != "https" or parts.username or parts.password
            or parts.netloc not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
            or parts.fragment):
        raise ActionError("Utilisez une URL HTTPS de vidéo YouTube, sans authentification ni port.")
    if parts.netloc == "youtu.be":
        video_id = parts.path.removeprefix("/")
    elif parts.path == "/watch":
        video_id = (parse_qs(parts.query).get("v") or [""])[0]
    elif parts.path.startswith(("/shorts/", "/embed/")):
        video_id = parts.path.rsplit("/", 1)[-1]
    else:
        video_id = ""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
        raise ActionError("Une vidéo YouTube précise est requise, pas une chaîne ou une playlist.")
    return f"https://www.youtube.com/watch?v={video_id}"


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _media_state(ref: str) -> dict:
    path = media.resolve_media(ref.removeprefix("media://"))
    stat = path.stat()
    return {"ref": ref, "size": stat.st_size, "modified": stat.st_mtime_ns}


def describe(name: str, raw: dict, project: dict | None) -> dict:
    from . import proposals

    if name not in SCHEMAS or not isinstance(raw, dict):
        raise ActionError("Action inconnue ou paramètres invalides.")
    model, label = SCHEMAS[name]
    try:
        params = model.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise ActionError(" ; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )) from None
    state: dict = {}
    impact = ["Seule cette action sera exécutée après confirmation ; aucune action suivante automatique."]
    try:
        if name in {"project_review", "project_export"}:
            if project is None:
                raise ActionError("Ouvrez un projet dans Design avant cette action.")
            errors, _ = proposals.validate_candidate(project)
            if errors:
                raise ActionError("Projet invalide : " + "; ".join(errors[:4]))
            errors, _ = media.validate_project_refs(project)
            if errors:
                raise ActionError("Références média invalides : " + "; ".join(errors[:4]))
            state["project_revision"] = proposals.revision_of(project)
            if name == "project_export":
                from ..security import EXPORTS_DIR, safe_name
                if (EXPORTS_DIR / (safe_name(params["name"]) + ".mp4")).exists():
                    raise ActionError("Un export porte déjà ce nom : choisissez un autre nom, aucun écrasement autorisé.")
        if name == "project_review":
            cfg = settings.llm_config()
            state["destination"] = {key: cfg.get(key) for key in ("provider", "model", "base_url")}
            destination = f"{cfg.get('provider')} / {cfg.get('model')} ({cfg.get('base_url')})"
            impact.append(f"Projet JSON, mesures DOM et logs texte envoyés au LLM configuré : {destination}. Aucun envoi d’image ni besoin de vision. Quota/coût possible si cloud.")
            impact.append("Rendu local de 6 frames maximum par passe ; au plus 2 appels au modèle et 2 corrections JSON, puis recontrôle. Les images restent locales pour votre contrôle. Résultat proposé, jamais appliqué automatiquement.")
        elif name == "project_export":
            impact.append("Rendu local potentiellement long. Création d’un MP4 ; aucun fichier existant ne sera remplacé.")
        elif name == "clips_download":
            params["url"] = _youtube_url(params["url"])
            impact.append("Téléchargement depuis YouTube vers le disque local. Confirmez disposer des droits nécessaires ; aucune autre source ni playlist autorisée.")
        elif name in {"clips_analyze", "clips_extract"}:
            from ..api import clips
            session = clips.load_session(params["sid"])
            state["session"] = _fingerprint(session)
            if name == "clips_analyze":
                if not session.get("transcript"):
                    raise ActionError("Cette session ne contient aucune transcription.")
                impact.append("Transcription envoyée à Groq avec la clé Clips configurée ; quota/coût possible. La sélection de clips de cette session sera remplacée.")
            else:
                if not params["landscape"] and not params["portrait"]:
                    raise ActionError("Choisissez au moins un format.")
                if any(i >= len(session.get("clips", [])) for i in params["clip_indexes"]):
                    raise ActionError("Index de clip absent de la session.")
                impact.append("Découpe locale par FFmpeg. Les exports des mêmes clips/formats peuvent être remplacés ; la vidéo source est conservée.")
        elif name.startswith("tts_"):
            from ..api import tts
            voice = next((v for v in tts.status()["voices"] if v["id"] == params["voice_id"]), None)
            if voice is None:
                raise ActionError("Voix inconnue : consultez get_tts_status.")
            if name == "tts_generate" and not voice["ready"]:
                raise ActionError("Voix non prête : téléchargez-la et vérifiez le moteur TTS.")
            if name == "tts_download":
                impact.append(f"Téléchargement des fichiers de la voix officielle {voice['label']} (~{voice.get('approx_mb', '?')} Mo). Aucune installation de paquet ou commande libre.")
            else:
                impact.append("Synthèse locale, création d’un média WAV ; l’affectation au projet reste une proposition séparée.")
        elif name.startswith("batch_") or name == "delivery_package":
            from .. import queue
            batch = queue.get_batch(params["batch_id"], items=False)
            state["batch"] = {k: batch.get(k) for k in ("id", "name", "status", "counters")}
            impact.append("Le lot ciblé est déjà préparé dans Production : " + str(batch.get("name", "")))
            impact.append("ZIP local uniquement, éventuellement remplacé ; aucune publication en ligne." if name == "delivery_package" else
                          "Traitement de la file locale ; démarrage/reprise peut rendre plusieurs vidéos selon la politique du lot. Annuler ne supprime pas les rendus terminés.")
        elif name == "moments_analyze":
            state["media"] = _media_state(params["source"])
            impact.append("Audio envoyé à Groq pour transcription ; quota/coût possible." if params["provider"] == "groq" else
                          "Transcription locale uniquement ; aucun repli automatique vers un fournisseur cloud.")
        elif name == "moments_generate":
            from .. import moments
            analysis = moments.get_analysis(params["analysis_id"])
            state["analysis"] = _fingerprint(analysis)
            impact.append("Création locale d’un projet, extrait audio et sous-titres ; aucun écrasement autorisé.")
        elif name == "settings_update":
            if not params:
                raise ActionError("Indiquez au moins un réglage non secret.")
            cfg = settings.llm_config()
            state["before"] = {key: cfg.get(key) for key in params}
            impact.append("Modification persistante des valeurs affichées pour les prochaines demandes. Ni clé, fournisseur, modèle, URL, permission ou chemin ne peut être modifié ici.")
    except HTTPException as exc:
        raise ActionError(str(exc.detail)) from None
    except (OSError, KeyError, ValueError) as exc:
        if isinstance(exc, ActionError):
            raise
        raise ActionError(str(exc)) from None
    return {"name": name, "params": params, "label": label, "impact": impact, "context": state}


def start(action: dict, record: dict, cfg: dict) -> dict:
    from ..api import batch, clips, delivery, exports, moments, tts

    name, params = action["name"], action["params"]
    if name == "clips_download":
        return clips.download(clips.UrlPayload(**params))
    if name == "clips_analyze":
        return clips.analyze(clips.AnalyzePayload(**params))
    if name == "clips_extract":
        return clips.extract(clips.ExtractPayload(**params))
    if name == "tts_download":
        return tts.download(tts.DownloadPayload(**params))
    if name == "tts_generate":
        return tts.generate(tts.GeneratePayload(**params))
    if name == "batch_start":
        return batch.batch_start(params["batch_id"])
    if name == "batch_retry":
        result = batch.batch_retry(params["batch_id"])
        return {"job_id": result["started"]}
    if name == "delivery_package":
        return delivery.package_batch(params["batch_id"])
    if name == "project_export":
        return exports.start_export(exports.ExportPayload(project=record["base_project"], **params))
    if name == "moments_analyze":
        return moments.analyze(moments.AnalyzePayload(**params))

    def work(job: jobs.Job) -> dict:
        jobs.raise_if_cancelled(job)
        if name == "batch_cancel":
            return batch.batch_cancel(params["batch_id"])
        if name == "moments_generate":
            return moments.generate(params["analysis_id"], moments.GeneratePayload(moment_id=params["moment_id"]))
        if name == "settings_update":
            settings.save_settings({f"llm_{key}": value for key, value in params.items()})
            return {"summary": "Réglages non secrets enregistrés.", "values": params}
        if name == "project_review":
            from . import proposals, review, service
            result = review.review_project(job, record["base_project"], params["prompt"], cfg)
            jobs.raise_if_cancelled(job)
            operations = result.get("operations", [])
            if operations:
                reply = {"type": "project_patch", "summary": result["summary"], "operations": operations,
                         "warnings": ["Vérification sur frames échantillonnées, pas sur l’ensemble du mouvement."]}
                proposal = proposals.from_reply(reply, record["base_project"], record["proposal"]["project_name"])
                service.store_followup(proposal, reply, record["base_project"])
                result["proposal"] = proposals.public_view(proposal)
            return result
        raise ActionError("Action non implémentée.")

    job = jobs.create_job("agent-action", work)
    return {"job_id": job.id, "status": job.status}
