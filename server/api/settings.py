"""Routes des réglages (clés API côté serveur uniquement).

Ni la clé Groq des Clips ni les clés de l'assistant ne sont renvoyées : seules
leurs états booléens sortent d'ici. L'URL du serveur local est visible (ce
n'est pas un secret, l'utilisateur doit la relire et la corriger) ; les URL des
fournisseurs cloud sont fixes côté serveur, personne d'autre ne peut les
choisir — ni le modèle, ni le navigateur.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shortvideos import asr

from .. import settings

# Fournisseurs de transcription proposes a l'ecran : le choix reste explicite.
ASR_PROVIDERS = ("auto", "local", "groq")

router = APIRouter(prefix="/api/settings", tags=["settings"])

_JSON_MODES = ("auto", "on", "off")


def _check_base_url(value: str) -> str:
    """Refuse un schéma non HTTP et toute authentification planquée dans l'URL."""
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"}:
        raise HTTPException(
            status_code=400,
            detail="URL de base invalide : utilisez http:// ou https:// "
            "(exemple : http://127.0.0.1:8080/v1).",
        )
    if not parts.netloc:
        raise HTTPException(status_code=400, detail="URL de base sans hôte.")
    if "@" in parts.netloc:
        raise HTTPException(
            status_code=400,
            detail="URL de base refusée : l'authentification passe par le champ "
            "« clé », jamais par l'URL.",
        )
    return value.rstrip("/")


class LlmSettings(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    local_base_url: str | None = None
    local_model: str | None = None
    local_api_key: str | None = None
    local_pin: str | None = None
    gemini_model: str | None = None
    gemini_api_key: str | None = None
    groq_model: str | None = None
    groq_api_key: str | None = None
    use_groq_clips_key: bool | None = None
    clear_key: bool | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    context_budget: int | None = None
    timeout: int | None = None
    max_repairs: int | None = None
    max_tool_calls: int | None = None
    stream: bool | None = None
    json_mode: str | None = None


class AsrSettings(BaseModel):
    provider: str | None = None
    groq_api_key: str | None = None
    clear_key: bool | None = None
    groq_model: str | None = None
    language: str | None = None


class SettingsPayload(BaseModel):
    groq_api_key: str | None = None
    llm: LlmSettings | None = None
    asr: AsrSettings | None = None


def _provider_state(data: dict, provider: str) -> dict:
    state = {
        "model": str(data.get(f"llm_{provider}_model") or "").strip(),
        "key_configured": bool(str(data.get(f"llm_{provider}_api_key") or "").strip()),
        "is_cloud": provider in settings.CLOUD_BASE_URLS,
    }
    if provider == "local":
        state["base_url"] = str(data.get("llm_local_base_url") or "").strip().rstrip("/")
        state["pin_configured"] = bool(str(data.get("llm_local_pin") or "").strip())
    else:
        state["base_url"] = settings.CLOUD_BASE_URLS[provider]
    return state


def public_llm() -> dict:
    """Bloc « Assistant IA » sans secret, pour le frontend."""
    data = settings.load_settings()
    cfg = settings.llm_config()
    provider = cfg["provider"]
    providers = [
        {
            "id": p,
            "label": settings.PROVIDER_LABELS[p],
            "is_cloud": p in settings.CLOUD_BASE_URLS,
            "base_url": settings.CLOUD_BASE_URLS.get(p, ""),
        }
        for p in settings.PROVIDERS
    ]
    states = {p: _provider_state(data, p) for p in settings.PROVIDERS}
    active = states[provider]
    return {
        "enabled": cfg["enabled"],
        "provider": provider,
        "providers": providers,
        "local": states["local"],
        "gemini": states["gemini"],
        "groq": states["groq"],
        "active": active,
        "base_url": active["base_url"],
        "model": active["model"],
        "key_configured": active["key_configured"],
        "pin_configured": active.get("pin_configured", False),
        "is_cloud": active["is_cloud"],
        "clips_groq_key_available": bool(str(data.get("groq_api_key") or "").strip()),
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "context_budget": cfg["context_budget"],
        "timeout": cfg["timeout"],
        "max_repairs": cfg["max_repairs"],
        "max_tool_calls": cfg["max_tool_calls"],
        "stream": cfg["stream"],
        "json_mode": cfg["json_mode"],
        "ready": bool(active["base_url"] and active["model"] and (not active["is_cloud"] or active["key_configured"])),
    }


def _llm_updates(llm: LlmSettings) -> dict:
    provider = (llm.provider or settings.provider_of()).strip().lower()
    if provider not in settings.PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Fournisseur inconnu : {llm.provider!r} "
            f"(choix : {', '.join(settings.PROVIDERS)}).",
        )
    updates: dict = {}
    if llm.enabled is not None:
        updates["llm_enabled"] = bool(llm.enabled)
    updates["llm_provider"] = provider
    if llm.local_base_url is not None:
        updates["llm_local_base_url"] = _check_base_url(llm.local_base_url.strip())
    if llm.local_model is not None:
        updates["llm_local_model"] = llm.local_model.strip()
    if llm.gemini_model is not None:
        updates["llm_gemini_model"] = llm.gemini_model.strip()
    if llm.groq_model is not None:
        updates["llm_groq_model"] = llm.groq_model.strip()

    # Les clés ne sont écrites que si un texte est fourni : un champ vide laisse
    # la clé enregistrée en place. « clear_key » est l'effacement explicite.
    key_field = f"llm_{provider}_api_key"
    typed = {"local": llm.local_api_key, "gemini": llm.gemini_api_key, "groq": llm.groq_api_key}[provider]
    if typed:
        updates[key_field] = typed.strip()
    if provider == "local":
        if llm.local_pin:
            updates["llm_local_pin"] = llm.local_pin.strip()
    if llm.use_groq_clips_key and provider == "groq":
        clips_key = str(settings.load_settings().get("groq_api_key") or "").strip()
        if not clips_key:
            raise HTTPException(
                status_code=400,
                detail="Aucune clé Groq des Clips à reprendre : enregistrez d'abord "
                "une clé dans la section Groq ou saisissez-la ci-dessus.",
            )
        # Reprise explicite, demandée par l'utilisateur — jamais un repli automatique.
        updates[key_field] = clips_key
    if llm.clear_key:
        updates[key_field] = ""
        if provider == "local":
            updates["llm_local_pin"] = ""

    if llm.stream is not None:
        updates["llm_stream"] = bool(llm.stream)
    if llm.json_mode is not None:
        mode = llm.json_mode.strip().lower()
        if mode not in _JSON_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Mode JSON inconnu : {llm.json_mode!r} (choix : {', '.join(_JSON_MODES)}).",
            )
        updates["llm_json_mode"] = mode
    for attr in ("temperature", "max_tokens", "context_budget", "timeout", "max_repairs", "max_tool_calls"):
        value = getattr(llm, attr)
        if value is not None:
            updates[f"llm_{attr}"] = value
    return updates


def public_asr() -> dict:
    """Bloc « transcription des moments » sans secret : etats et raisons, jamais la clef."""
    data = settings.load_settings()
    typed = bool(str(data.get("asr_groq_api_key") or "").strip())
    clips = bool(str(data.get("groq_api_key") or "").strip())
    return {
        "provider": str(data.get("asr_provider") or "auto"),
        "groq_models": list(asr.GROQ_WHISPER_MODELS),
        "model": str(data.get("asr_groq_model") or asr.GROQ_WHISPER_MODELS[0]),
        "language": str(data.get("asr_language") or ""),
        "key_configured": typed,
        "clips_key_available": clips,
        "providers": asr.providers(groq_key_present=typed or clips),
        "local_backend": asr.local_backend(),
    }


def _asr_updates(payload: AsrSettings) -> dict:
    provider = (payload.provider or "").strip().lower()
    if provider:
        if provider not in ASR_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Fournisseur de transcription inconnu : {payload.provider!r} "
                f"(choix : {', '.join(ASR_PROVIDERS)}).",
            )
    updates: dict = {}
    if provider:
        updates["asr_provider"] = provider
    if payload.groq_model is not None:
        model = payload.groq_model.strip()
        if model and model not in asr.GROQ_WHISPER_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Modèle Groq inconnu : {model} (choix : {', '.join(asr.GROQ_WHISPER_MODELS)}).",
            )
        updates["asr_groq_model"] = model or asr.GROQ_WHISPER_MODELS[0]
    if payload.language is not None:
        updates["asr_language"] = payload.language.strip()[:8]
    # une cle n'est ecrite que si un texte est fourni ; « clear_key » est l'effacement explicite
    if payload.groq_api_key:
        updates["asr_groq_api_key"] = payload.groq_api_key.strip()
    if payload.clear_key:
        updates["asr_groq_api_key"] = ""
    return updates


@router.get("")
def get_settings() -> dict:
    cfg = settings.load_settings()
    return {
        "groq_configured": bool(cfg.get("groq_api_key")),
        "host": cfg["host"],
        "port": cfg["port"],
        "llm": public_llm(),
        "asr": public_asr(),
    }


@router.post("")
def update_settings(payload: SettingsPayload) -> dict:
    updates = {}
    if payload.groq_api_key is not None:
        updates["groq_api_key"] = payload.groq_api_key.strip()
    if payload.llm is not None:
        updates.update(_llm_updates(payload.llm))
    if payload.asr is not None:
        updates.update(_asr_updates(payload.asr))
    settings.save_settings(updates)
    return {
        "groq_configured": bool(settings.load_settings().get("groq_api_key")),
        "llm": public_llm(),
        "asr": public_asr(),
    }
