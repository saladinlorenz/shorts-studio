"""Adaptateur LLM (API compatible OpenAI).

Règles :
- le fournisseur est celui que l'utilisateur a choisi dans Réglages — serveur
  local (llama.cpp), Gemini ou Groq ; aucun repli automatique, et la clé Groq
  des Clips n'est jamais réutilisée à l'insu de l'utilisateur ;
- une clé cloud est saisie en clair par l'utilisateur, utilisée pour la seule
  demande en cours, et jamais renvoyée au navigateur ni écrite dans les journaux ;
- une génération peut être interrompue (le streaming est lu par morceaux) ;
- les particularités de serveur restent ici, le reste de l'agent ignore
  le transport.

On ne suppose pas que tous les modèles du serveur sont chargés : la liste
``/models`` est demandée, et le modèle employé est celui choisi par
l'utilisateur.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from .. import settings

# Erreurs classées : le service les traduit en messages compréhensibles.
KIND_UNREACHABLE = "unreachable"
KIND_TIMEOUT = "timeout"
KIND_HTTP = "http_error"
KIND_EMPTY = "empty_response"
KIND_CONTEXT = "context_too_long"
KIND_CANCELLED = "cancelled"
KIND_DISABLED = "disabled"
KIND_NOT_CONFIGURED = "not_configured"

# Motifs vus dans les messages des serveurs locaux quand le contexte déborde.
_CONTEXT_PATTERNS = re.compile(
    r"exceed|too long|context|n_ctx|n_kv|prompt is too long|maximum context",
    re.IGNORECASE,
)


class LLMError(RuntimeError):
    """ Echec de génération, avec une cause exploitable par l'agent. """

    def __init__(self, message: str, kind: str = KIND_HTTP, status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


@dataclass
class ChatResult:
    text: str
    model: str = ""
    finish_reason: str = ""
    prompt_chars: int = 0
    latency_ms: int = 0
    streamed: bool = False
    tool_calls: list[dict] = field(default_factory=list)


def endpoint_of(base_url: str) -> str:
    """Ramène l'URL de base à la racine de l'API compatible OpenAI.

    Une URL sans chemin (``http://127.0.0.1:8080``) reçoit ``/v1``, la
    convention de llama.cpp. Un chemin déjà précisé est respecté tel quel
    (``…/v1`` pour Groq, ``…/v1beta/openai`` pour Gemini).
    """
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url[: -len("/chat/completions")]
    segments = [part for part in urlsplit(url).path.split("/") if part]
    if segments:
        return url
    return f"{url}/v1"


def client_config() -> dict:
    return settings.llm_config()


def is_ready(cfg: dict | None = None) -> tuple[bool, str]:
    cfg = cfg or client_config()
    provider = str(cfg.get("provider") or "local")
    label = "un serveur local, Gemini ou Groq"
    if not cfg.get("enabled"):
        return (False, "L'assistant IA est désactivé (Réglages → Assistant IA).")
    if not cfg.get("base_url"):
        return (False, f"Aucune URL de serveur renseignée : précisez {label} dans Réglages → Assistant IA.")
    if not cfg.get("model"):
        return (False, f"Aucun modèle choisi pour {provider} : renseignez-le dans Réglages → Assistant IA.")
    if provider in settings.CLOUD_BASE_URLS and not cfg.get("api_key"):
        return (
            False,
            f"Aucune clé d'API enregistrée pour {provider} : saisissez-la dans "
            "Réglages → Assistant IA (vos textes seront envoyés à ce service).",
        )
    return (True, "")


def _headers(cfg: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    # Les serveurs locaux type « Local Chat » protègent leurs /api/* par un PIN.
    if cfg.get("pin"):
        headers["X-PIN"] = str(cfg["pin"])
    return headers


def _http_error(status: int, body: str) -> LLMError:
    detail = (body or "").strip()[:400]
    if _CONTEXT_PATTERNS.search(detail) and status in (400, 413, 500, 502):
        return LLMError(
            f"Contexte trop grand pour le serveur ({status}) : {detail}",
            KIND_CONTEXT,
            status,
        )
    return LLMError(f"Le serveur LLM a répondu {status} : {detail}", KIND_HTTP, status)


def list_models(cfg: dict | None = None) -> list[str]:
    """Modèles déclarés par le serveur (s'il expose /models)."""
    cfg = cfg or client_config()
    base = endpoint_of(cfg.get("base_url", ""))
    if not base:
        raise LLMError("URL de serveur LLM absente.", KIND_NOT_CONFIGURED)
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0), trust_env=False) as client:
            resp = client.get(f"{base}/models", headers=_headers(cfg))
    except httpx.TimeoutException as e:
        raise LLMError(f"Délai dépassé en interrogeant {base}/models.", KIND_TIMEOUT) from e
    except httpx.HTTPError as e:
        raise LLMError(f"Serveur LLM injoignable : {e}", KIND_UNREACHABLE) from e
    if resp.status_code != 200:
        raise _http_error(resp.status_code, resp.text)
    try:
        data = resp.json()
    except ValueError as e:
        raise LLMError("Le serveur /models ne renvoie pas de JSON valide.", KIND_HTTP) from e
    items: Any = None
    if isinstance(data, dict):
        items = data.get("data") or data.get("models") or []
    out: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
            # Gemini préfixe ses identifiants par « models/ » : la racine OpenAI
            # compatible attend le nom sans ce préfixe.
            if name.startswith("models/"):
                name = name[len("models/"):]
            if name and name not in out:
                out.append(name)
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _accumulate_stream(resp, cancel: Callable[[], bool] | None) -> ChatResult:
    """Lit un flux SSE en vérifiant l'annulation entre les morceaux."""
    pieces: list[str] = []
    tool_calls: list[dict] = []
    model = ""
    finish = ""
    buffer = ""
    for chunk in resp.iter_text():
        if cancel is not None and cancel():
            resp.close()
            raise LLMError("Génération interrompue.", KIND_CANCELLED)
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except ValueError:
                continue
            model = str(event.get("model") or model)
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str):
                    pieces.append(content)
                calls = delta.get("tool_calls")
                if isinstance(calls, list):
                    tool_calls.extend(c for c in calls if isinstance(c, dict))
                if choice.get("finish_reason"):
                    finish = str(choice["finish_reason"])
    return ChatResult(
        text="".join(pieces),
        model=model,
        finish_reason=finish,
        streamed=True,
        tool_calls=tool_calls,
    )


def chat(
    messages: list[dict],
    *,
    cfg: dict | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
    cancel: Callable[[], bool] | None = None,
    stream: bool | None = None,
) -> ChatResult:
    """Un appel de ``/chat/completions`` vers le serveur configuré.

    ``json_mode`` ne force la sortie structurée que si le serveur l'accepte :
    en cas de refus explicite, l'appel est retenté sans ``response_format``
    (le protocole de l'agent reste de toute façon validé côté Python).
    """
    cfg = cfg or client_config()
    base = endpoint_of(cfg.get("base_url", ""))
    if not base:
        raise LLMError("URL de serveur LLM absente.", KIND_NOT_CONFIGURED)
    if not cfg.get("model"):
        raise LLMError("Aucun modèle LLM sélectionné.", KIND_NOT_CONFIGURED)

    timeout = float(cfg.get("timeout", 120) or 120)
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.4) if temperature is None else temperature),
        "max_tokens": int(cfg.get("max_tokens", 1500) if max_tokens is None else max_tokens),
        "stream": cfg.get("stream", True) if stream is None else bool(stream),
    }
    if json_mode and str(cfg.get("json_mode", "auto")) != "off":
        payload["response_format"] = {"type": "json_object"}

    started = time.perf_counter()
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(15.0, timeout)),
            follow_redirects=False,  # pas de redirection réseau incontrôlée
            trust_env=False,
        ) as client:
            with client.stream(
                "POST", f"{base}/chat/completions", headers=_headers(cfg), json=payload
            ) as resp:
                if resp.status_code != 200:
                    resp.read()
                    if (
                        json_mode
                        and resp.status_code in (400, 422)
                        and "response_format" in (resp.text or "").lower()
                    ):
                        payload.pop("response_format", None)
                        return chat(
                            messages, cfg=cfg, temperature=temperature,
                            max_tokens=max_tokens, json_mode=False,
                            cancel=cancel, stream=False,
                        )
                    raise _http_error(resp.status_code, resp.text)
                if payload["stream"] and "text/event-stream" in resp.headers.get("content-type", ""):
                    result = _accumulate_stream(resp, cancel)
                else:
                    if cancel is not None and cancel():
                        raise LLMError("Génération interrompue.", KIND_CANCELLED)
                    body = json.loads(resp.read().decode("utf-8", errors="replace"))
                    result = _from_json(body)
    except LLMError as e:
        if e.kind == KIND_CONTEXT and payload["stream"]:
            # certains serveurs locaux gèrent mal streaming + grande entrée
            return chat(
                messages, cfg=cfg, temperature=temperature, max_tokens=max_tokens,
                json_mode=json_mode, cancel=cancel, stream=False,
            )
        raise
    except httpx.TimeoutException as e:
        raise LLMError(
            f"Délai de {int(timeout)} s dépassé : le modèle n'a pas répondu à temps.",
            KIND_TIMEOUT,
        ) from e
    except httpx.HTTPError as e:
        raise LLMError(
            f"Fournisseur « {cfg.get('provider', 'local')} » injoignable ({base}) : {e}. "
            "Pour un serveur local, vérifiez qu'il tourne et que l'URL est correcte ; "
            "pour une clé cloud, vérifiez la clé et le réseau.",
            KIND_UNREACHABLE,
        ) from e
    except ValueError as e:
        raise LLMError(f"Réponse du serveur LLM illisible : {e}", KIND_HTTP) from e

    result.latency_ms = int((time.perf_counter() - started) * 1000)
    result.prompt_chars = prompt_chars
    if not result.text.strip() and not result.tool_calls:
        raise LLMError(
            "Le modèle a renvoyé une réponse vide (arrêt prématuré, contexte plein "
            "ou limite de sortie trop basse).",
            KIND_EMPTY,
        )
    return result


def _from_json(body: dict) -> ChatResult:
    if not isinstance(body, dict):
        return ChatResult(text="")
    choices = body.get("choices") or []
    if not choices:
        return ChatResult(text="", model=str(body.get("model") or ""))
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    text = message.get("content")
    if not isinstance(text, str):
        text = ""
    calls = message.get("tool_calls")
    return ChatResult(
        text=text,
        model=str(body.get("model") or ""),
        finish_reason=str(choice.get("finish_reason") or ""),
        tool_calls=[c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else [],
    )


def check_connection(cfg: dict | None = None) -> dict:
    """état réel du serveur : modèles listés, chat disponible, options supportées.

    Les capacités sont déduites de réponses effectives, jamais supposées.
    """
    cfg = cfg or client_config()
    provider = str(cfg.get("provider") or "local")
    report = {
        "enabled": bool(cfg.get("enabled")),
        "provider": provider,
        "is_cloud": provider in settings.CLOUD_BASE_URLS,
        "base_url": cfg.get("base_url", ""),
        "api_root": endpoint_of(cfg.get("base_url", "")),
        "model": cfg.get("model", ""),
        "key_configured": bool(cfg.get("api_key")),
        "pin_configured": bool(cfg.get("pin")),
        "ok": False,
        "models": [],
        "capabilities": {
            "models_list": "inconnu",
            "chat": "inconnu",
            "streaming": "inconnu",
            "structured_output": "inconnu",
            "tool_calling": "inconnu",
        },
        "error": "",
        "hint": "",
    }
    if not cfg.get("base_url"):
        report["error"] = "Aucune URL de serveur LLM enregistrée."
        return report
    if report["is_cloud"] and not cfg.get("api_key"):
        report["error"] = (
            f"Aucune clé d'API pour {provider} : sans clé la vérification échouerait "
            "et vos textes ne partiraient de toute façon pas."
        )
        return report
    if not cfg.get("model"):
        report["error"] = f"Aucun modèle choisi pour {provider}."
        return report
    try:
        report["models"] = list_models(cfg)
        report["capabilities"]["models_list"] = "oui"
    except LLMError as e:
        report["capabilities"]["models_list"] = "non"
        if e.kind == KIND_UNREACHABLE:
            report["error"] = str(e)
            return report

    # Test de chat minimal, sans sortie structurée.
    try:
        result = chat(
            [{"role": "user", "content": 'Réponds uniquement par: {"ok":true}'}],
            cfg=cfg, max_tokens=32, cancel=None, stream=False,
        )
        report["capabilities"]["chat"] = "oui"
        report["ok"] = True
        if '"ok"' in result.text and "true" in result.text:
            report["capabilities"]["structured_output"] = "partiel (JSON obtenu sans response_format)"
        if result.tool_calls:
            report["capabilities"]["tool_calling"] = "oui"
    except LLMError as e:
        report["capabilities"]["chat"] = "non"
        report["error"] = str(e)
        return report

    # Test du streaming, puis de response_format, séparément : un serveur peut
    # n'en supporter qu'un des deux.
    try:
        streamed = chat(
            [{"role": "user", "content": 'Réponds uniquement par: {"ok":true}'}],
            cfg=cfg, max_tokens=32, stream=True,
        )
        report["capabilities"]["streaming"] = "oui" if streamed.text.strip() else "inconnu"
    except LLMError:
        report["capabilities"]["streaming"] = "non"
    try:
        chat(
            [{"role": "user", "content": "donne un objet JSON vide"}],
            cfg={**cfg, "json_mode": "on"}, max_tokens=16, json_mode=True, stream=False,
        )
        report["capabilities"]["structured_output"] = "oui (response_format json_object)"
    except LLMError as e:
        report["capabilities"]["structured_output"] = (
            "non" if "response_format" in str(e).lower() else "inconnu"
        )
    if not report["ok"] and report["error"]:
        report["hint"] = _load_hint(report["error"], cfg)
    elif not report["models"]:
        report["hint"] = (
            "Le serveur ne déclare aucun modèle : chargez-en un (dans Local Chat, "
            "ou POST /api/load) puis relancez la vérification."
        )
    return report


def _load_hint(error: str, cfg: dict) -> str:
    """Message d'aide quand l'erreur ressemble à un moteur sans modèle chargé."""
    text = error.lower()
    if cfg.get("provider") != "local":
        return ""
    if any(marker in text for marker in ("loading", "no model", "not loaded", "aucun modèle", "chargement")):
        return (
            "Le moteur local ne sert aucun modèle pour l'instant : chargez-en un "
            "dans votre application (POST /api/load ou l'interface), puis relancez "
            "la vérification."
        )
    if "unreachable" in text or "injoignable" in text or "10061" in text:
        return (
            "Vérifiez que le moteur LLM est démarré et que l'URL saisie dans Réglages "
            "est la bonne (avec son chemin /v1 si le serveur l'exige)."
        )
    if "401" in text or "403" in text or "pin" in text:
        return "Le serveur refuse la requête : renseignez le PIN dans Réglages → Assistant IA."
    return ""


# 3 caractères par token : estimation prudente pour le français et les tokenizers
# des petits modèles. Mesure réelle : le serveur seul la connaît.
CHARS_PER_TOKEN = 3


def estimate_tokens(text: str) -> int:
    """Estimation, pas une mesure : jamais présentée comme un comptage exact."""
    return max(1, int(len(text) / CHARS_PER_TOKEN)) if text else 0
