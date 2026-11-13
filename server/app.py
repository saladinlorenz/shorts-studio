"""Application FastAPI locale de youtube_clipper.

- écoute sur 127.0.0.1:8000 par défaut (aucune publication externe) ;
- sert le frontend buildé (web/dist) à la racine : même origine, pas de CORS ;
- vérifie l'origine sur toutes les requêtes de modification (CSRF de base) ;
- aucune logique métier copiée ici : les routes appellent shortvideos/ et
  les modules existants.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import queue as batch_queue, security, settings
from .api import agent, batch, brands, clips, delivery, exports, folders, jobs, library, media_routes, moments as moments_api, podcast, projects, settings as settings_api, skills, studio, tts

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

app = FastAPI(title="youtube_clipper (local)", version="0.1.0")

security.ensure_dirs()
# la file SQLite est persistante : une ligne coupee par un arret repasse en
# file d'attente, le lot est mis en pause, rien ne redemarre sans l'utilisateur
RECOVERED_QUEUE = batch_queue.recover()


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    """Refuse les requêtes de modification dont l'origine ne correspond pas."""
    try:
        security.check_origin(request)
    except Exception as e:  # HTTPException 403
        detail = getattr(e, "detail", "Origine non autorisee.")
        return JSONResponse(status_code=403, content={"detail": detail})
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "groq_configured": bool(settings.get_api_key()),
        "web_dist": WEB_DIST.exists(),
        "queue_recovered": RECOVERED_QUEUE,
    }


app.include_router(projects.router)
app.include_router(exports.router)
app.include_router(jobs.router)
app.include_router(media_routes.router)
app.include_router(settings_api.router)
app.include_router(studio.router)
app.include_router(library.router)
app.include_router(skills.router)
app.include_router(folders.router)
app.include_router(batch.router)
app.include_router(delivery.router)
app.include_router(brands.router)
app.include_router(moments_api.router)
app.include_router(agent.router)
app.include_router(clips.router)
app.include_router(podcast.router)
app.include_router(tts.router)


def _index_response() -> FileResponse | JSONResponse:
    index_file = WEB_DIST / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Frontend non construit. Exécutez une fois : "
                    "cd web && npm install && npm run build"
                )
            },
        )
    return FileResponse(index_file)


@app.get("/", response_model=None)
def index():
    return _index_response()


STATIC_MEDIA_TYPES = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}


# SPA : toute route GET non-API renvoie index.html (le router gère côté client).
@app.get("/{full_path:path}", response_model=None)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Route API inconnue."})
    # Fichiers statiques racine (favicon, polices, cache de rendu, etc.).
    candidate = (WEB_DIST / full_path).resolve()
    try:
        candidate.relative_to(WEB_DIST.resolve())
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Chemin invalide."})
    if candidate.is_file():
        media_type = STATIC_MEDIA_TYPES.get(candidate.suffix.lower())
        return FileResponse(candidate, media_type=media_type)
    return _index_response()


def _browse_url(host: str, port: int) -> str:
    """URL locale réellement navigable (0.0.0.0 et :: ne le sont pas)."""
    browse_host = "127.0.0.1" if host in {"", "0.0.0.0", "::"} else host
    return f"http://{browse_host}:{port}/"


def _is_up(host: str, port: int) -> bool:
    """Vrai si un serveur de l'application répond déjà sur ce point d'entrée."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            _browse_url(host, port) + "api/health", timeout=1
        ) as response:
            return response.status == 200
    except Exception:
        return False


def _is_free(host: str, port: int) -> bool:
    """Vrai si personne n'écoute déjà sur l'hôte et le port demandés."""
    import socket

    bind_host = "127.0.0.1" if host in {"", "::"} else host
    family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((bind_host, port))
        except OSError:
            return False
    return True


def _open_browser_when_ready(host: str, port: int) -> None:
    """Attend que le serveur réponde avant d'ouvrir le navigateur.

    Les imports (ffmpeg, file SQLite, routeurs) prennent plusieurs secondes : ouvrir
    la page avant l'écoute montrerait un site inaccessible. L'hôte et le port sont
    ceux réellement configurés, pas une valeur supposée.
    """
    import threading
    import time
    import urllib.request
    import webbrowser

    url = _browse_url(host, port)

    def wait_and_open() -> None:
        for _ in range(120):
            try:
                with urllib.request.urlopen(url + "api/health", timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        return
            except Exception:
                pass
            time.sleep(0.5)

    threading.Thread(target=wait_and_open, daemon=True).start()


# Watchdog : le socket d'écoute peut mourir (WinError 64) sans que le processus
# s'arrête. On surveille /api/health et, si le serveur ne répond plus alors qu'il
# a répondu au moins une fois, on sort avec un code dédié : start_web.bat relance
# alors une instance neuve. Plusieurs échecs espacés évitent de tuer un serveur
# simplement occupé par un rendu lourd.
WATCHDOG_INTERVAL = 15
WATCHDOG_TIMEOUT = 10
WATCHDOG_FAILURES = 4
WATCHDOG_EXIT_CODE = 3


def _start_watchdog(host: str, port: int) -> None:
    import os
    import threading
    import time
    import urllib.request

    url = _browse_url(host, port) + "api/health"
    state = {"armed": False, "failures": 0}

    def loop() -> None:
        while True:
            time.sleep(WATCHDOG_INTERVAL)
            try:
                with urllib.request.urlopen(url, timeout=WATCHDOG_TIMEOUT) as response:
                    ok = response.status == 200
            except Exception:
                ok = False
            if ok:
                state["armed"] = True
                state["failures"] = 0
                continue
            if not state["armed"]:
                continue  # démarrage lent : jamais répondu, on ne tue pas
            state["failures"] += 1
            if state["failures"] >= WATCHDOG_FAILURES:
                print(
                    f"\n[watchdog] /api/health ne répond plus ({state['failures']} checks, "
                    f"~{state['failures'] * WATCHDOG_INTERVAL} s) : arrêt pour redémarrage "
                    f"automatique (code {WATCHDOG_EXIT_CODE}).",
                    flush=True,
                )
                os._exit(WATCHDOG_EXIT_CODE)

    threading.Thread(target=loop, daemon=True, name="studio-watchdog").start()


def main() -> None:
    import sys

    import uvicorn

    cfg = settings.load_settings()
    host = str(cfg["host"])
    port = int(cfg["port"])
    open_browser = "--open" in sys.argv[1:]

    if _is_up(host, port):
        # Une instance tourne déjà : la relancer échouerait sur le port déjà
        # pris. On réutilise celle-ci plutôt que d'afficher « address in use ».
        url = _browse_url(host, port)
        print(f"Deja en execution sur {url}")
        print("Relancez l'application apres avoir ferme sa fenetre (Ctrl+C).")
        if open_browser:
            import webbrowser

            webbrowser.open(url)
        return

    if not _is_free(host, port):
        print(f"ERREUR: le port {port} est occupe par un autre programme et")
        print("aucun serveur de l'application ne repond dessus.")
        print("Fermez ce programme, ou changez le port dans server/settings.json.")
        raise SystemExit(1)

    if open_browser:
        _open_browser_when_ready(host, port)
    _start_watchdog(host, port)
    # Un arrêt du serveur en plein plan laisse un état « running » sur disque :
    # on reprend ces plans interrompus avant d'accepter de nouvelles requêtes.
    from .agent import autopilot

    resumed = autopilot.resume_interrupted()
    if resumed:
        print(f"{len(resumed)} plan(s) autopilote interrompu(s) repris au demarrage.", flush=True)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
