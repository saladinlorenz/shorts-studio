"""Reglages du serveur (fichier local server/settings.json).

Les cles API (Groq des Clips et cles de l'assistant) restent ICI : elles ne
sont jamais renvoyees au frontend, qui ne recoit que leur etat
(``groq_configured``, ``key_configured``). Elles ne sont pas non plus ecrites
dans les journaux.

L'assistant choisit explicitement un fournisseur : un serveur local
(llama.cpp ou toute API compatible OpenAI), l'API Gemini ou l'API Groq. Les
deux derniers envoient le texte au cloud -- ce n'est jamais un repli
automatique, seulement un choix enregistre ici.
"""
from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).with_name("settings.json")

# Fournisseurs acceptes. L'URL des fournisseurs cloud est fixe cote serveur :
# ni le modele ni le navigateur ne peuvent la choisir.
PROVIDERS = ("local", "gemini", "groq")
CLOUD_BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
}
PROVIDER_LABELS = {
    "local": "Serveur local (llama.cpp / compatible OpenAI)",
    "gemini": "API Gemini (Google)",
    "groq": "API Groq",
}

# Mémoire adaptative : les fournisseurs cloud ont une grande fenêtre. Un budget
# serré (3000, calibré pour un petit modèle local) y fait sauter l'historique et
# les documents : le modèle oublie l'effet déjà choisi et redemande. On garantit
# donc un plancher généreux au cloud ; le local conserve le budget réglé. Une
# valeur cloud explicitement plus haute reste honorée ; le repli KIND_CONTEXT
# du service réduit encore si la fenêtre réelle du serveur est plus petite.
CLOUD_CONTEXT_FLOOR = 20000

# Valeurs par défaut : les seules clés conservées par load()/save() (liste
# blanche). Tout nouveau réglage doit être déclaré ici pour être lisible.
_DEFAULTS = {
    "groq_api_key": "",
    "host": "127.0.0.1",
    "port": 8000,
    # --- Assistant IA --------------------------------------------------------
    # Defaut local-first : le llama.cpp local est servi via le relais OpenAI de
    # Local Chat (127.0.0.1:8080/api/agent/v1). Le port moteur 8900 est interne ;
    # le relais applique la config de generation de l'app (thinking desactive),
    # seul moyen d'obtenir des reponses exploitables par le studio. Modele
    # « local » (un seul modele servi a la fois). Aucun cloud par defaut ;
    # l'utilisateur change de fournisseur ou de modele dans Reglages.
    "llm_enabled": True,
    "llm_provider": "local",
    "llm_local_base_url": "http://127.0.0.1:8080/api/agent/v1",
    "llm_local_api_key": "",
    "llm_local_pin": "",
    "llm_local_model": "local",
    "llm_gemini_api_key": "",
    "llm_gemini_model": "",
    "llm_groq_api_key": "",
    "llm_groq_model": "",
    "llm_temperature": 0.4,
    "llm_max_tokens": 900,
    "llm_context_budget": 3000,  # budget de contexte, en tokens ESTIMES (les petits
    #                             # modèles locaux tournent souvent sur 4096 tokens)
    "llm_timeout": 120,  # secondes
    "llm_max_repairs": 2,  # tentatives automatiques de reparation du JSON
    "llm_max_tool_calls": 3,  # appels d'outils de lecture par demande
    "llm_stream": True,  # streaming SSE (interrompable) si le serveur le peut
    "llm_json_mode": "auto",  # auto | on | off : sortie JSON demandee ou non
    "llm_vision_review": False,  # passe de vision optionnelle sur les frames rendues
    #                             # (off par defaut : envoie les images au fournisseur,
    #                             #  1 appel borne, advisory — ne corrige rien toute seule)
    # --- Transcription des moments forts --------------------------------------
    # Cle DEDIEE : la cle Groq des Clips (groq_api_key) ne sert a la transcription
    # que sur demande explicite de l'utilisateur (api_key_source = "clips").
    "asr_provider": "auto",  # auto | groq | local
    "asr_groq_api_key": "",
    "asr_groq_model": "whisper-large-v3-turbo",
    "asr_language": "",  # vide = la langue est laissee au modele
}

_LLM_NUMBER_DEFAULTS = {
    "llm_temperature": (0.0, 0.4, 2.0),
    "llm_max_tokens": (64, 900, 32000),
    "llm_context_budget": (1000, 3000, 200000),
    "llm_timeout": (5, 120, 1800),
    "llm_max_repairs": (0, 2, 5),
    "llm_max_tool_calls": (0, 3, 10),
}
_LLM_INT_KEYS = {
    "llm_max_tokens", "llm_context_budget", "llm_timeout",
    "llm_max_repairs", "llm_max_tool_calls",
}


def load_settings() -> dict:
    data = dict(_DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                data.update({k: v for k, v in stored.items() if k in _DEFAULTS})
        except (OSError, json.JSONDecodeError):
            pass  # fichier abîme : on repart des defauts
    return data


def provider_of(data: dict | None = None) -> str:
    data = data if data is not None else load_settings()
    provider = str(data.get("llm_provider") or "local").strip().lower()
    return provider if provider in PROVIDERS else "local"


def llm_config() -> dict:
    """Reglages de l'assistant ramenes a des types sures (bornes incluses).

    Fournit la configuration du fournisseur actif : URL, cle et modele. Une
    valeur saisie hors bornes est ramenee a la borne la plus proche plutot que
    de bloquer l'usage du serveur.
    """
    data = load_settings()
    provider = provider_of(data)
    base_url = (
        CLOUD_BASE_URLS[provider]
        if provider in CLOUD_BASE_URLS
        else str(data.get("llm_local_base_url") or "").strip().rstrip("/")
    )
    cfg = {
        "enabled": bool(data.get("llm_enabled")),
        "provider": provider,
        "base_url": base_url,
        "api_key": str(data.get(f"llm_{provider}_api_key") or "").strip(),
        "pin": str(data.get("llm_local_pin") or "").strip() if provider == "local" else "",
        "model": str(data.get(f"llm_{provider}_model") or "").strip(),
        "stream": bool(data.get("llm_stream", True)),
        "json_mode": str(data.get("llm_json_mode") or "auto").lower(),
        "vision_review": bool(data.get("llm_vision_review", False)),
    }
    for key, (lo, default, hi) in _LLM_NUMBER_DEFAULTS.items():
        raw = data.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
        value = min(hi, max(lo, value))
        short = key.removeprefix("llm_")
        cfg[short] = int(value) if key in _LLM_INT_KEYS else round(value, 3)
    return cfg


def effective_context_budget(cfg: dict, configured: int) -> int:
    """Budget effectif : plancher cloud généreux, budget local conservé tel quel.

    Le réglage ``context_budget`` reste la référence en local (petite fenêtre).
    Au cloud, on ne descend jamais sous ``CLOUD_CONTEXT_FLOOR`` pour que
    l'historique et les documents survivent ; une valeur réglée plus haute gagne.
    """
    configured = int(configured)
    if cfg.get("provider") in CLOUD_BASE_URLS:
        return max(configured, CLOUD_CONTEXT_FLOOR)
    return configured


def save_settings(data: dict) -> dict:
    current = load_settings()
    for key in _DEFAULTS:
        if key in data:
            current[key] = data[key]
    SETTINGS_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return current


def get_api_key() -> str:
    return str(load_settings().get("groq_api_key", ""))
