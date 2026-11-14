"""Orchestrateur du mode autopilote : un plan validé → une vidéo MP4.

Un seul job enchaîne les étapes du plan (script → design → voix off → export),
sans nouvel appel LLM : tout a été validé dans la proposition. Chaque transition
est persistée sur disque (projects/autopilot/<job>.json) : après un arrêt du
serveur, le plan est reprenable à la première étape non terminée via
``start(job_id=…)``. L'annulation passe par le cancel_event du job : la synthèse
vocale et le rendu la respectent, aucun fichier provisoire ne reste.
"""
from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from pathlib import Path

from shortvideos import broll as broll_mod
from shortvideos import captions as captions_mod
from shortvideos import tts as tts_mod

from .. import jobs, media as media_mod, render as render_mod
from ..security import EXPORTS_DIR, PROJECTS_DIR, TTS_MODELS_DIR, safe_name
from . import proposals, service

STATE_DIR = PROJECTS_DIR / "autopilot"

_LOCK = threading.Lock()
_RUNNING: dict[str, dict] = {}

_DONE_MESSAGES = {
    "script": "Textes appliqués.",
    "design": "Design appliqué.",
    "voice": "Voix off synthétisée.",
    "export": "Vidéo exportée.",
}

# Échec transitoire (moteur vocal, rendu, disque) : l'étape est rejouée une fois.
# Script et design sont déterministes (validation du plan) : les rejouer est inutile.
_RETRYABLE_STEPS = frozenset({"voice", "export"})
_MAX_STEP_ATTEMPTS = 2


def start(*, proposal_id: str = "", job_id: str = "") -> str:
    """Démarre un plan proposé, ou reprend un plan interrompu/échoué.

    Retourne l'identifiant du PLAN (stable entre les reprises) : chaque exécution
    crée un job interne neuf, mais l'état — et donc l'URL de suivi — garde le
    même identifiant, y compris après un redémarrage du serveur.
    """
    if bool(proposal_id) == bool(job_id):
        raise ValueError("Fournir proposal_id (nouveau plan) ou job_id (reprise), pas les deux.")
    state = _state_from_proposal(proposal_id) if proposal_id else _resumable_state(job_id)
    plan_id = state["job_id"]
    ready = threading.Event()

    def work(job: jobs.Job) -> dict:
        with _LOCK:
            _RUNNING[plan_id] = {"job": job, "state": state}
        ready.set()
        return _run(job, state)

    jobs.create_job("autopilot", work)
    ready.wait(timeout=5)
    return plan_id


def cancel(job_id: str) -> dict | None:
    """Annulation : le cancel_event du job interne est partagé par toutes les
    étapes (synthèse, rendu). Sans job vivant, il n'y a rien à annuler."""
    with _LOCK:
        entry = _RUNNING.get(job_id)
        if entry is not None and entry["job"].status == "running":
            entry["job"].cancel_event.set()
            entry["job"].message = "Annulation demandée…"
    return status(job_id)


def status(job_id: str) -> dict | None:
    """État public : mémoire vive si le job tourne, sinon état persisté.

    Un état « running » sur disque sans job en mémoire signifie que le serveur
    s'est arrêté en cours de route : le plan est présenté comme interrompu,
    reprenable, jamais comme perdu.
    """
    with _LOCK:
        entry = _RUNNING.get(job_id)
        if entry is not None:
            data = copy.deepcopy(entry["state"])
            snap = entry["job"].snapshot()
        else:
            data, snap = None, None
    if data is None:
        data = _load_state(job_id)
        if data is None:
            return None
        if data["status"] == "running":
            data["status"] = "interrupted"
            for step in data["steps"]:
                if step["status"] == "running":
                    step["status"] = "pending"
                    step["message"] = "Interrompu par l'arrêt du serveur."
    out = _public(data)
    if snap is not None:
        out["progress"] = snap["progress"]
        out["message"] = snap["message"]
    return out


def video_path(job_id: str) -> Path | None:
    """Fichier final d'un plan terminé (sert la route /file, même après reprise)."""
    with _LOCK:
        entry = _RUNNING.get(job_id)
        data = copy.deepcopy(entry["state"]) if entry is not None else None
    if data is None:
        data = _load_state(job_id)
    video = (data or {}).get("video")
    if not video:
        return None
    path = EXPORTS_DIR / safe_name(str(video["name"]))
    return path if path.is_file() else None


def format_path(job_id: str, name: str) -> Path | None:
    """Fichier d'un format social derive (1:1, 16:9) d'un plan termine.

    Le nom doit etre un format reellement declare par l'etat persiste : jamais
    un chemin fourni par le client. Meme garde que ``video_path``.
    """
    with _LOCK:
        entry = _RUNNING.get(job_id)
        data = copy.deepcopy(entry["state"]) if entry is not None else None
    if data is None:
        data = _load_state(job_id)
    video = (data or {}).get("video") or {}
    formats = video.get("formats") or []
    if not any(str(f.get("name")) == str(name) for f in formats):
        return None
    path = EXPORTS_DIR / safe_name(str(name))
    return path if path.is_file() else None


def resume_interrupted() -> list[str]:
    """Relance les plans laissés « running » sur disque par un arrêt du serveur.

    Appelé au lancement réel du serveur (``app.main``), jamais par TestClient.
    Un état « running » sans job vivant = interruption : le même plan repart de
    la première étape non terminée. Les plans déjà vivants en mémoire et ceux
    terminés sont ignorés. Best-effort : un plan illisible ne bloque pas les
    autres. Retourne les identifiants repris.
    """
    resumed: list[str] = []
    if not STATE_DIR.is_dir():
        return resumed
    for path in sorted(STATE_DIR.glob("*.json")):
        job_id = path.stem
        state = _load_state(job_id)
        if state is None or state.get("status") != "running":
            continue
        with _LOCK:
            entry = _RUNNING.get(job_id)
            if entry is not None and entry["job"].status == "running":
                continue
        try:
            start(job_id=job_id)
        except Exception:  # noqa: BLE001 - un plan cassé ne bloque pas le démarrage
            continue
        resumed.append(job_id)
    return resumed


# --------------------------------------------------------------------------- #
# État initial et reprise
# --------------------------------------------------------------------------- #

def _state_from_proposal(proposal_id: str) -> dict:
    record = service.get_record(proposal_id)
    if record is None:
        raise KeyError("Proposition expirée ou inconnue : relancez une demande de plan.")
    proposal = record["proposal"]
    if proposal["type"] != "autopilot_plan":
        raise ValueError("Cette proposition n'est pas un plan autopilote.")
    plan = copy.deepcopy(proposal["autopilot"])
    steps = [
        {"id": sid, "label": label, "status": "pending", "message": "", "error": ""}
        for sid, label in proposals.AUTOPILOT_STEPS
    ]
    if not plan.get("voice"):
        steps[2]["status"] = "skipped"
        steps[2]["message"] = "Pas de voix off dans ce plan."
    proposal["status"] = "accepted"
    return {
        "job_id": uuid.uuid4().hex[:12],
        "proposal_id": proposal_id,
        "status": "running",
        "project_name": proposal.get("project_name", ""),
        "plan": plan,
        "steps": steps,
        "project": None,
        "voice_ref": None,
        "video": None,
        "error": "",
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def _resumable_state(job_id: str) -> dict:
    with _LOCK:
        entry = _RUNNING.get(job_id)
    if entry is not None and entry["job"].status == "running":
        raise ValueError("Ce plan est déjà en cours.")
    state = _load_state(job_id)
    if state is None:
        raise KeyError("Plan autopilote introuvable.")
    # « running » sur disque sans job vivant = arrêt du serveur en cours de route.
    if state["status"] not in ("error", "interrupted", "cancelled", "running"):
        raise ValueError("Ce plan est déjà terminé.")
    for step in state["steps"]:
        if step["status"] in ("running", "failed", "cancelled", "pending"):
            step["status"] = "pending"
            step["error"] = ""
    state["status"] = "running"
    state["error"] = ""
    return state


# --------------------------------------------------------------------------- #
# Exécution des étapes
# --------------------------------------------------------------------------- #

def _run(job: jobs.Job, state: dict) -> dict:
    plan = state["plan"]
    total = len(state["steps"])
    current = -1
    try:
        project = state.get("project")
        for index, step in enumerate(state["steps"]):
            if step["status"] in ("done", "skipped"):
                continue
            current = index
            jobs.raise_if_cancelled(job)
            attempts = _MAX_STEP_ATTEMPTS if step["id"] in _RETRYABLE_STEPS else 1
            for attempt in range(attempts):
                _set_step(state, index, status="running", message="", error="")
                job.set_progress(index, total, step["label"] + "…")
                try:
                    if step["id"] == "script":
                        project = _step_script(plan)
                    elif step["id"] == "design":
                        project = _step_design(plan, project)
                    elif step["id"] == "voice":
                        project, ref = _step_voice(job, plan, project, index, total)
                        with _LOCK:
                            state["voice_ref"] = ref
                    elif step["id"] == "export":
                        video, project = _step_export(job, plan, project, state, index, total)
                        with _LOCK:
                            state["video"] = video
                    break
                except jobs.JobCancelled:
                    raise
                except Exception as e:  # noqa: BLE001 - rejoué une fois si transitoire
                    if attempt + 1 >= attempts:
                        raise
                    jobs.raise_if_cancelled(job)
                    _set_step(state, index, status="running",
                              message=f"Nouvelle tentative après échec : {str(e)[:200]}")
            if step["id"] in ("script", "design", "voice", "export"):
                with _LOCK:
                    state["project"] = project
            _set_step(state, index, status="done", message=_DONE_MESSAGES[step["id"]])
        with _LOCK:
            state["status"] = "done"
        _persist(state)
        job.set_progress(total, total, "Vidéo prête.")
        return _public(state)
    except jobs.JobCancelled:
        if current >= 0:
            _set_step(state, current, status="cancelled", message="Annulé.")
        with _LOCK:
            state["status"] = "cancelled"
        _persist(state)
        raise
    except Exception as e:  # noqa: BLE001 - l'échec d'une étape arrête tout le plan
        if current >= 0:
            _set_step(state, current, status="failed", error=str(e)[:400])
        with _LOCK:
            state["status"] = "error"
            state["error"] = str(e)[:400]
        _persist(state)
        raise
    finally:
        with _LOCK:
            _RUNNING.pop(state["job_id"], None)


def _step_script(plan: dict) -> dict:
    from .. import library as library_mod

    template = library_mod.get_project(plan["template_id"])
    project, _, _ = proposals.apply_operations(template, plan["script"])
    errors, _ = proposals.validate_candidate(project)
    if errors:
        raise RuntimeError("Script refusé : " + " ; ".join(errors[:3]))
    return project


def _step_design(plan: dict, project: dict | None) -> dict:
    if project is None:
        raise RuntimeError("Projet absent : l'étape script n'est pas terminée.")
    candidate = project
    if plan["design"]:
        candidate, _, _ = proposals.apply_operations(project, plan["design"])
    candidate = _with_broll(candidate)
    errors, _ = proposals.validate_candidate(candidate)
    if errors:
        raise RuntimeError("Design refusé : " + " ; ".join(errors[:3]))
    return candidate


def _gather_broll_assets() -> list[dict]:
    """Visuels locaux disponibles : dossiers connectés + médias importés récents.

    Même pool que list_assets/search_assets (images et vidéos), dédupliqué par
    référence. Aucune analyse visuelle : le nom et le dossier renseignent le thème.
    """
    from .. import folders as folders_mod
    from . import capabilities

    assets: list[dict] = []
    seen: set[str] = set()
    for kind in ("image", "video"):
        for asset in folders_mod.assets_by_kind(kind):
            ref = asset.get("ref")
            if ref and ref not in seen:
                seen.add(ref)
                assets.append(asset)
    for asset in capabilities._media_inventory():
        ref = asset.get("ref")
        if asset.get("kind") in ("image", "video") and ref and ref not in seen:
            seen.add(ref)
            assets.append(asset)
    return assets


def _with_broll(candidate: dict) -> dict:
    """B-roll par thème, best-effort : posé seulement s'il garde le projet valide.

    Un média disparu entre la collecte et la validation ne doit jamais casser le
    design : on conserve alors le projet sans B-roll (dégradé de la palette).
    """
    assets = _gather_broll_assets()
    if not assets:
        return candidate
    brolled = broll_mod.auto_broll(candidate, assets)
    if proposals.validate_candidate(brolled)[0]:
        return candidate
    return brolled


def _step_voice(job: jobs.Job, plan: dict, project: dict | None, index: int, total: int) -> tuple[dict, str]:
    if project is None:
        raise RuntimeError("Projet absent : l'étape design n'est pas terminée.")
    voice = plan["voice"]
    fps = int((project.get("export") or {}).get("fps", 30) or 30)
    wav = TTS_MODELS_DIR / f"_synth_{uuid.uuid4().hex[:12]}.wav"
    cues: list[dict] = []
    try:
        info = tts_mod.synthesize(
            voice["text"], voice["voice_id"], TTS_MODELS_DIR, wav,
            speed=float(voice.get("speed", 1.0)),
            progress=_step_progress(job, index, total),
            cancel=lambda: jobs.raise_if_cancelled(job),
        )
        jobs.raise_if_cancelled(job)
        # Alignement lu sur le WAV réel, avant qu'il ne soit nettoyé. Best-effort :
        # un souci de lecture ne doit pas faire échouer une voix off déjà synthétisée.
        if plan.get("captions"):
            try:
                cues = captions_mod.caption_cues(wav, voice["text"], fps=fps)
            except captions_mod.CaptionError:
                cues = []
        media_id = media_mod.import_file_to_media(
            wav, source=f"Synthèse vocale ({info['engine']} : {voice['voice_id']})",
        )
    finally:
        wav.unlink(missing_ok=True)
        wav.with_name(wav.name + ".part").unlink(missing_ok=True)
    ref = f"media://{media_id}"
    candidate, _, _ = proposals.apply_operations(project, [
        {"op": "set_audio", "path": "voice", "value": ref},
        {"op": "set_audio", "path": "enabled", "value": True},
    ])
    errors, _ = proposals.validate_candidate(candidate)
    if errors:
        raise RuntimeError("Voix off non applicable : " + " ; ".join(errors[:3]))
    # Rythme cale sur la voix : la duree totale des scenes suit la narration.
    # Fait avant les sous-titres, dont les fenetres dependent des durees de scene.
    candidate = captions_mod.pace_to_voice(candidate, float(info.get("duration", 0.0)), fps=fps)
    errors, _ = proposals.validate_candidate(candidate)
    if errors:
        raise RuntimeError("Rythme non applicable : " + " ; ".join(errors[:3]))
    if cues:
        candidate = captions_mod.overlay_captions(candidate, cues, fps=fps)
        errors, _ = proposals.validate_candidate(candidate)
        if errors:
            raise RuntimeError("Sous-titres non applicables : " + " ; ".join(errors[:3]))
    return candidate, ref


def _step_export(job: jobs.Job, plan: dict, project: dict | None, state: dict, index: int, total: int) -> tuple[dict, dict]:
    if project is None:
        raise RuntimeError("Projet absent : les étapes précédentes ne sont pas terminées.")
    name = safe_name(plan["export"]["name"])
    if not name.lower().endswith(".mp4"):
        name += ".mp4"
    out_path = EXPORTS_DIR / name
    if out_path.exists():
        stem = name[:-4]
        for suffix in range(2, 100):
            candidate_path = EXPORTS_DIR / f"{stem}-{suffix}.mp4"
            if not candidate_path.exists():
                out_path, name = candidate_path, candidate_path.name
                break
        else:
            raise RuntimeError("Trop de fichiers portent ce nom : choisissez un autre nom d'export.")
    info = _render_mp4(job, project, out_path, index, total)
    if plan.get("review"):
        project, corrected = _auto_correct(job, project, out_path, index, total)
        if corrected is not None:
            info = corrected
    made = _derive_formats(job, out_path)
    formats = [
        {
            "ratio": f["ratio"], "name": f["name"],
            "url": f"/api/agent/autopilot/{state['job_id']}/format/{f['name']}",
            "size_bytes": f["size_bytes"], "width": f["width"], "height": f["height"],
        }
        for f in made
    ]
    return {
        "name": name,
        "url": f"/api/agent/autopilot/{state['job_id']}/file",
        "size_bytes": info.get("size_bytes"),
        "duration": info.get("duration"),
        "formats": formats,
    }, project


def _derive_formats(job: jobs.Job, out_path: Path) -> list[dict]:
    """Livraison multi-formats : 1:1 et 16:9 recadres depuis le master 9:16.

    Best-effort : un master illisible ou un format rate ne casse pas l'export
    (le master reste livre). L'annulation remonte et nettoie les formats deja
    produits ; le master, lui, a deja ete publie par l'etape de rendu.
    """
    from shortvideos import delivery as delivery_mod
    from shortvideos.probe import ProbeError, probe_mp4

    try:
        probe_mp4(str(out_path))
    except (ProbeError, OSError, ValueError):
        return []
    stem = out_path.stem
    expected = [out_path.parent / f"{stem}-{suffix}.mp4" for suffix in ("1x1", "16x9")]
    try:
        return delivery_mod.derive_social_formats(
            out_path, out_path.parent, stem,
            cancel=lambda: jobs.raise_if_cancelled(job),
        )
    except jobs.JobCancelled:
        for path in expected:
            path.unlink(missing_ok=True)
        raise


def _render_mp4(job: jobs.Job, project: dict, out_path: Path, index: int, total: int) -> dict:
    """Rendu atomique vers out_path : un fichier provisoire, puis remplacement.
    Aucun export partiel n'est publié ; le provisoire est nettoyé quoi qu'il arrive."""
    tmp = out_path.with_name(out_path.name + ".part.mp4")
    try:
        if tmp.exists():
            tmp.unlink()
        info = render_mod.render_project_to_mp4(_RenderJob(job, index, total), project, tmp)
        jobs.raise_if_cancelled(job)
        tmp.replace(out_path)
        return info
    finally:
        tmp.unlink(missing_ok=True)


_REVIEW_PROMPT = (
    "Corrige uniquement les défauts techniques mesurés (texte hors cadre, débordement, "
    "superposition, texte attendu invisible). Préserve le design, la narration, la voix off "
    "et les sous-titres. N'invente aucun contenu."
)


def _auto_correct(job: jobs.Job, project: dict, out_path: Path, index: int, total: int) -> tuple[dict, dict | None]:
    """Audit technique du montage rendu, puis correction bornée et re-rendu.

    Best-effort : sans LLM prêt, sans défaut mesuré, ou si la correction ne valide
    pas, la première vidéo est conservée — l'export n'échoue jamais pour une revue.
    Retourne (projet retenu, infos du re-rendu ou None). L'annulation, elle, remonte.
    """
    from .. import settings as settings_mod
    from . import llm_client, review

    cfg = settings_mod.llm_config()
    ready, _ = llm_client.is_ready(cfg)
    if not ready:
        return project, None
    try:
        jobs.raise_if_cancelled(job)
        result = review.review_project(_RenderJob(job, index, total), project, _REVIEW_PROMPT, cfg)
        operations = result.get("operations") or []
        if not operations:
            return project, None
        candidate, _, op_errors = proposals.apply_operations(project, operations)
        if op_errors:
            return project, None
        errors, _ = proposals.validate_candidate(candidate)
        if errors:
            return project, None
        jobs.raise_if_cancelled(job)
        info = _render_mp4(job, candidate, out_path, index, total)
        jobs.raise_if_cancelled(job)
        return candidate, info
    except jobs.JobCancelled:
        raise
    except Exception:  # noqa: BLE001 - une revue ratée ne casse pas l'export déjà rendu
        return project, None


def _step_progress(job: jobs.Job, index: int, total: int):
    """Progression d'une étape ramenée à la progression globale du plan."""
    def report(current, step_total, message=""):
        frac = (current / step_total) if step_total else 0.0
        job.set_progress(int((index + frac) * 1000), total * 1000, message)
    return report


class _RenderJob:
    """Le rendu partage l'annulation du job ; sa progression (en frames) est
    bornée à l'étape export pour ne pas écraser la progression du plan."""

    def __init__(self, job: jobs.Job, index: int, total: int):
        self._job = job
        self._index = index
        self._total = total
        self.id = job.id
        self.cancel_event = job.cancel_event

    def set_progress(self, current, total, message=""):
        frac = (current / total) if total else 0.0
        self._job.set_progress(int((self._index + frac) * 1000), self._total * 1000, message)


# --------------------------------------------------------------------------- #
# Persistance et vue publique
# --------------------------------------------------------------------------- #

def _state_path(job_id: str) -> Path:
    if not job_id or any(c in job_id for c in "/\\.:"):
        raise KeyError("Identifiant de plan invalide.")
    return STATE_DIR / f"{job_id}.json"


def _persist(state: dict) -> None:
    with _LOCK:
        state["updated_at"] = time.time()
        payload = json.dumps(state, ensure_ascii=False)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / f".{state['job_id']}.tmp"
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(_state_path(state["job_id"]))


def _load_state(job_id: str) -> dict | None:
    try:
        path = _state_path(job_id)
    except KeyError:
        return None
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _set_step(state: dict, index: int, **fields) -> None:
    with _LOCK:
        state["steps"][index].update(fields)
    _persist(state)


def _public(state: dict) -> dict:
    return {
        "job_id": state["job_id"],
        "proposal_id": state.get("proposal_id", ""),
        "status": state["status"],
        "project_name": state.get("project_name", ""),
        "steps": state["steps"],
        "voice_ref": state.get("voice_ref"),
        "video": state.get("video"),
        "error": state.get("error", ""),
        "resumable": state["status"] in ("error", "interrupted", "cancelled"),
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
    }