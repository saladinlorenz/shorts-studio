"""Analyses de moments forts : transcription reelle, detection, puis projet a la demande.

Un instantane vit dans ``moments/<id>.json`` — transcription horodatee, moments
classes et reference media de la source. Rien d'autre : le projet nait seulement
quand l'utilisateur clique sur « generer », ce qui respecte « l'assistant propose,
l'utilisateur applique ». L'analyse ne touche donc aucun projet, n'importe aucun
media et n'ecrit jamais la cle API dans son dossier.

La piste 16 kHz extraite pour la transcription sert aussi a l'enveloppe d'energie
(la detection en a besoin) : elle est mesuree puis supprimee, car une heure de WAV
ne se garde pas a cote d'un fichier de quelques centaines de kilo-octets.

Le decoupage audio d'un moment reimporte l'extrait dans ``media/`` (reference
``media://``) : le projet genere ne porte jamais un chemin disque.
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from shortvideos import asr as asr_mod
from shortvideos import delivery as delivery_mod
from shortvideos import moment_project as moment_project_mod
from shortvideos import moments as moments_mod

from . import brands as brands_mod
from . import jobs as jobs_mod
from . import media as media_mod
from . import settings as settings_mod
from .security import MOMENTS_DIR, PROJECTS_DIR, assert_local_dir, safe_name

# Bandes de duree proposees a l'interface : la detection reste libre de ses bornes.
DURATION_PRESETS = {
    "short": {"label": "Punchy (10-24 s)", "min_seconds": 10.0, "max_seconds": 24.0},
    "standard": {"label": "Standard (10-45 s)", "min_seconds": 10.0, "max_seconds": 45.0},
    "long": {"label": "Développé (20-70 s)", "min_seconds": 20.0, "max_seconds": 70.0},
}

DEFAULT_TOP = moments_mod.TOP_DEFAULT
# seuls ces conteneurs portent une image : un fichier de son seul n'a rien a montrer
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
SOURCE_EXT_HINTS = VIDEO_EXT + AUDIO_EXT


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _analysis_path(analysis_id: str) -> Path:
    filename = safe_name(analysis_id)
    if not filename.lower().endswith(".json"):
        filename += ".json"
    return assert_local_dir(MOMENTS_DIR / filename)


def _work_dir(analysis_id: str) -> Path:
    return assert_local_dir(MOMENTS_DIR / "work" / safe_name(analysis_id))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Analyse illisible : {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Analyse illisible : ce n'est pas un objet JSON.")
    return data


# --- Fournisseurs et cle -----------------------------------------------------


def providers_state() -> dict:
    """Ce que la machine peut vraiment faire, avec la raison ecrite quand non.

    Une cle absente ou un Whisper non installe ne sont pas des erreurs : ce sont
    des etats que l'interface affiche avant de proposer un choix.
    """
    data = settings_mod.load_settings()
    asr_key = str(data.get("asr_groq_api_key") or "").strip()
    clips_key = str(data.get("groq_api_key") or "").strip()
    return {
        "providers": asr_mod.providers(groq_key_present=bool(asr_key or clips_key)),
        "local_backend": asr_mod.local_backend(),
        "asr_key_configured": bool(asr_key),
        "clips_key_configured": bool(clips_key),
        "default_provider": str(data.get("asr_provider") or "auto"),
        "default_model": str(data.get("asr_groq_model") or asr_mod.GROQ_WHISPER_MODELS[0]),
        "language": str(data.get("asr_language") or ""),
        "duration_presets": DURATION_PRESETS,
        "top_default": DEFAULT_TOP,
    }


def _asr_choice(provider: str = "", api_key_source: str = "", model: str = "") -> tuple[str, str, str]:
    """Cle en main : la cle de Clips n'est utilisee que si on le demande explicitement."""
    data = settings_mod.load_settings()
    choice = (api_key_source or "asr").strip().lower()
    if choice not in {"asr", "clips"}:
        raise HTTPException(
            status_code=400,
            detail="Source de cle inconnue : « asr » (cle dediee) ou « clips » (cle de Clips).",
        )
    key = str(data.get("asr_groq_api_key") or "").strip()
    if choice == "clips":
        key = key or str(data.get("groq_api_key") or "").strip()
    wanted = (provider or data.get("asr_provider") or "auto").strip().lower()
    if wanted not in {"auto", "local", "groq"}:
        raise HTTPException(
            status_code=400,
            detail=f"Fournisseur de transcription inconnu : {wanted!r} (choix : auto, local, groq).",
        )
    # un Whisper local n'a pas de cle : seule la voie Groq (explicitement demandee, ou
    # tentee en auto apres le local) exige que l'utilisateur en ait designe une.
    if wanted == "groq" and not key:
        raise HTTPException(
            status_code=400,
            detail=(
                "Aucune cle dediee a la transcription. Renseigne « asr_groq_api_key » dans "
                "Réglages, ou coche « reutiliser la cle de Clips » — cette cle ne sort pas "
                "du serveur et n'est jamais utilisee en silence."
            ),
        )
    groq_model = str(model or data.get("asr_groq_model") or asr_mod.GROQ_WHISPER_MODELS[0]).strip()
    if groq_model not in asr_mod.GROQ_WHISPER_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Modele Groq inconnu : {groq_model} (choix : {', '.join(asr_mod.GROQ_WHISPER_MODELS)}).",
        )
    return wanted, key, groq_model


# --- Sources -----------------------------------------------------------------


def _known_media_suffixes() -> set[str]:
    return set(SOURCE_EXT_HINTS)


def resolve_source(source: str) -> tuple[str, Path]:
    """``media://<id>`` ou un identifiant nu -> chemin, strictement dans ``media/``.

    Le client ne choisit jamais un chemin : il designe un media deja importe.
    """
    ref = str(source or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="Choisis une source : la bibliotheque de medias.")
    if "://" in ref:
        if not ref.startswith("media://"):
            raise HTTPException(status_code=400, detail="Source non reconnue : reference media:// attendue.")
        media_id = ref[len("media://"):]
    else:
        media_id = ref
    path = media_mod.resolve_media(media_id)
    if path.suffix.lower() not in _known_media_suffixes():
        raise HTTPException(
            status_code=400,
            detail=f"Format de source non transcriptible : {path.suffix or 'sans extension'}",
        )
    return media_id, path


def _source_title(media_id: str, path: Path) -> str:
    provenance = media_mod.provenance_of(media_id)
    return str(provenance.get("filename") or path.name)


# --- Analyses ----------------------------------------------------------------


def _summary(analysis_id: str, data: dict) -> dict:
    transcript = data.get("transcript") or {}
    items = data.get("moments") or []
    scores = [int(m.get("score") or 0) for m in items]
    return {
        "id": analysis_id,
        "source_ref": data.get("source_ref") or "",
        "source_media_id": data.get("source_media_id") or "",
        "source_title": data.get("source_title") or "",
        "duration": float(transcript.get("duration") or 0.0),
        "provider": transcript.get("provider") or "",
        "model": transcript.get("model") or "",
        "language": transcript.get("language") or "",
        "segments": len(transcript.get("segments") or []),
        "moment_count": len(items),
        "best_score": max(scores) if scores else 0,
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or "",
    }


def list_analyses() -> list[dict]:
    out: list[dict] = []
    for path in sorted(MOMENTS_DIR.glob("*.json")):
        try:
            data = _read_json(path)
        except HTTPException:
            out.append({"id": path.stem, "source_title": path.stem, "unreadable": True})
            continue
        out.append(_summary(path.stem, data))
    out.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return out


def get_analysis(analysis_id: str) -> dict:
    path = _analysis_path(analysis_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Analyse introuvable : {analysis_id}")
    data = _read_json(path)
    record = {"id": path.stem, **data}
    record["summary"] = _summary(path.stem, data)
    return record


def _progress_cb(job: jobs_mod.Job, base: float, span: float, label: str):
    def report(done: int, total: int, message: str = "") -> None:
        inside = (done / total) if total else 0.0
        job.set_progress(base + span * inside, 1.0, message or label)

    return report


def analyze_create_job(source: str, *, provider: str = "", api_key_source: str = "",
                       model: str = "", language: str = "", min_seconds: float | None = None,
                       max_seconds: float | None = None, top: int | None = None) -> jobs_mod.Job:
    """Analyse complete (transcription + energie + detection) dans un job, sans ecrire avant la fin."""
    wanted, key, groq_model = _asr_choice(provider, api_key_source, model)
    media_id, path = resolve_source(source)
    duration = DURATION_PRESETS["standard"]
    low = float(min_seconds) if min_seconds else duration["min_seconds"]
    high = float(max_seconds) if max_seconds else duration["max_seconds"]
    limit = int(top) if top else DEFAULT_TOP
    language = str(language or settings_mod.load_settings().get("asr_language") or "").strip() or None
    work = _work_dir(f"pending-{uuid.uuid4().hex[:8]}")

    def worker(job: jobs_mod.Job) -> dict:
        work.mkdir(parents=True, exist_ok=True)
        wav = work / "audio.wav"
        moved = False
        try:
            transcript = asr_mod.transcribe(
                path, provider=wanted, api_key=key, groq_model=groq_model, language=language,
                work_dir=work, audio_out=wav,
                progress=_progress_cb(job, 0.0, 0.7, "Transcription…"),
                cancel=lambda: jobs_mod.raise_if_cancelled(job),
            )
            jobs_mod.raise_if_cancelled(job)
            job.set_progress(0.72, 1.0, "Mesure de l'energie…")
            energy = asr_mod.energy_curve(wav)
            _write_json(work / "energy.json", energy)
            # l'energie est mesuree : la piste brute (une heure de WAV ~= 130 Mo) ne
            # reste pas dans moments/, sinon le dossier grossit sans jamais servir
            wav.unlink(missing_ok=True)
            job.set_progress(0.78, 1.0, "Detection des moments…")
            found = moments_mod.detect(
                transcript, energy=energy,
                min_seconds=max(1.0, low), max_seconds=max(low + 1.0, high), top=max(1, limit),
            )
            job.set_progress(0.85, 1.0, "Enregistrement de l'analyse…")
            analysis_id = uuid.uuid4().hex[:12]
            final_work = _work_dir(analysis_id)
            if final_work.exists():
                shutil.rmtree(final_work, ignore_errors=True)
            work.replace(final_work)
            moved = True  # le dossier appartient desormais a l'analyse
            data = {
                "id": analysis_id,
                "source_ref": f"media://{media_id}",
                "source_media_id": media_id,
                "source_title": _source_title(media_id, path),
                "created_at": _now(),
                "updated_at": _now(),
                "transcript": {**transcript, "source": path.name, "audio_path": ""},
                "energy_file": str((final_work / "energy.json").relative_to(MOMENTS_DIR)),
                "detect": {
                    "min_seconds": max(1.0, low),
                    "max_seconds": max(low + 1.0, high),
                    "top": max(1, limit),
                    "algorithm": "score+energie",
                },
                "moments": found,
            }
            _write_json(_analysis_path(analysis_id), data)
            return {"analysis": _summary(analysis_id, data), "moment_count": len(found)}
        finally:
            # deplace, le dossier est devenu celui de l'analyse et porte son energie ;
            # sinon il n'etait que temporaire et ne doit rien laisser derriere lui
            wav.unlink(missing_ok=True)
            if not moved:
                shutil.rmtree(work, ignore_errors=True)

    return jobs_mod.create_job("moments-analyze", worker)


def recompute(analysis_id: str, *, min_seconds: float | None = None,
              max_seconds: float | None = None, top: int | None = None) -> dict:
    """Relance la seule detection sur une transcription deja stockee.

    Pas de nouvelle transcription : le cout (et l'appel reseau) est deja paye.
    Les reglages utilises restent dans l'enregistrement, pour que l'on sache
    toujours pourquoi tel moment est monte tel jour.
    """
    path = _analysis_path(analysis_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Analyse introuvable : {analysis_id}")
    data = _read_json(path)
    transcript = data.get("transcript") or {}
    if not transcript.get("segments"):
        raise HTTPException(status_code=400, detail="Cette analyse n'a aucun segment : relance la transcription.")
    stored = data.get("detect") or {}
    low = float(min_seconds if min_seconds else stored.get("min_seconds") or DURATION_PRESETS["standard"]["min_seconds"])
    high = float(max_seconds if max_seconds else stored.get("max_seconds") or DURATION_PRESETS["standard"]["max_seconds"])
    limit = int(top if top else stored.get("top") or DEFAULT_TOP)

    energy = None
    energy_file = data.get("energy_file")
    if energy_file:
        candidate = assert_local_dir(MOMENTS_DIR / str(energy_file))
        if candidate.is_file():
            try:
                energy = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                energy = None  # energie perdue : la detection tourne sans ce critere

    found = moments_mod.detect(
        transcript, energy=energy,
        min_seconds=max(1.0, low), max_seconds=max(low + 1.0, high), top=max(1, limit),
    )
    data["moments"] = found
    data["detect"] = {
        "min_seconds": max(1.0, low), "max_seconds": max(low + 1.0, high),
        "top": max(1, limit), "algorithm": "score+energie",
    }
    data["updated_at"] = _now()
    _write_json(path, data)
    return {"analysis": _summary(path.stem, data), "moments": found,
            "energy_used": bool(energy and energy.get("rms"))}


def delete_analysis(analysis_id: str) -> dict:
    path = _analysis_path(analysis_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Analyse introuvable : {analysis_id}")
    work = _work_dir(analysis_id)
    if work.is_dir():
        shutil.rmtree(work, ignore_errors=True)
    path.unlink()
    return {"deleted": path.stem}


# --- Generation d'un projet --------------------------------------------------


def _find_moment(data: dict, moment_id: str) -> dict:
    wanted = str(moment_id or "").strip()
    for moment in data.get("moments") or []:
        if str(moment.get("id") or "") == wanted:
            return moment
    raise HTTPException(status_code=404, detail=f"Moment introuvable dans cette analyse : {wanted!r}")


def _import_as_media(path: Path, source_label: str) -> str:
    media_id = media_mod.import_file_to_media(path, source=source_label)
    return f"media://{media_id}"


def generate_project(analysis_id: str, moment_id: str, *, brand_id: str = "", handle: str = "",
                     source_title: str = "", use_source_thumbnail: bool = True,
                     overwrite: bool = False) -> dict:
    """Le click utilisateur qui transforme un moment en projet de travail.

    Aucun autre chemin n'ecrit dans ``projects/`` depuis cette fonction :
    l'analyse propose, la generation applique.
    """
    analysis = get_analysis(analysis_id)
    moment = _find_moment(analysis, moment_id)
    pack = brands_mod.get_pack(brand_id) if brand_id else None
    brand_label = str((pack or {}).get("label") or "").strip()
    _, source_path = resolve_source(analysis.get("source_ref") or "")
    work = _work_dir(f"{analysis_id}-{moment_id}")
    work.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    voice_ref = ""
    thumbnail_ref = ""

    try:
        extract = work / "voice.wav"
        try:
            asr_mod.cut_wav(source_path, extract, float(moment["start"]), float(moment["end"]))
            voice_ref = _import_as_media(extract, f"extrait {moment_id} de {analysis.get('source_title') or source_path.name}")
        except HTTPException as exc:
            warnings.append(f"Extrait vocal non importe : {exc}")
        except Exception as exc:  # noqa: BLE001 : un decoupage rate ne doit pas perdre le moment
            warnings.append(f"Extrait vocal non importe : {exc}")

        if use_source_thumbnail:
            if source_path.suffix.lower() not in VIDEO_EXT:
                # une source audio n'a aucune frame a capter, et OpenCV se bloque sur un
                # fichier purements audio : on ne lance meme pas l'extraction.
                warnings.append(
                    f"Miniature indisponible : la source {source_path.suffix} est du son seul, "
                    "il n'y a pas d'image a extraire. Ajoute un fond dans Design."
                )
            else:
                shot = work / "thumbnail.png"
                stamp = float(moment.get("start") or 0.0) + max(0.0, float(moment.get("duration") or 0.0)) / 2.0
                made = delivery_mod.make_thumbnail(source_path, shot, at_seconds=round(stamp, 3))
                if made.get("warning"):
                    warnings.append(f"Miniature indisponible : {made['warning']}")
                else:
                    try:
                        thumbnail_ref = _import_as_media(shot, f"miniature {moment_id}")
                    except HTTPException as exc:
                        warnings.append(f"Miniature non importee : {exc}")

        generated = moment_project_mod.generate(
            moment, pack=pack, voice_ref=voice_ref, thumbnail_ref=thumbnail_ref,
            source={"path": source_path.name, "title": source_title or analysis.get("source_title") or "",
                    "duration": float((analysis.get("transcript") or {}).get("duration") or 0.0)},
            handle=handle, brand_label=brand_label,
            source_title=source_title or analysis.get("source_title") or "",
        )
        if source_path.suffix.lower() in VIDEO_EXT:
            warnings.append(
                "Fond vidéo : la composition rejoue le média à chaque scène, il n'est pas "
                "appliqué automatiquement. Ajoute une image de fond dans Design si tu veux "
                "garder l'image d'origine sur tout le clip."
            )
        if generated["errors"]:
            raise HTTPException(
                status_code=400,
                detail={"message": "Projet généré invalide : corrige la source avant l'écriture.",
                        "errors": generated["errors"]},
            )

        project = generated["project"]
        name = str(project.get("name") or f"{analysis_id}-{moment_id}")
        target = assert_local_dir(PROJECTS_DIR / f"{safe_name(name)}.json")
        if target.exists() and not overwrite:
            raise HTTPException(
                status_code=409,
                detail=f"Le projet {target.name} existe déjà : relance en écrasant ou change de moment.",
            )

        srt = delivery_mod.srt_from_project(project)
        if not srt:
            warnings.append("Aucun sous-titre dans le projet genere : .srt non ecrit.")

        tmp = target.with_name(target.name + ".part")
        tmp.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        if srt:
            # le .srt part a cote du projet, pas dans le dossier de travail detruit ici :
            # c'est le fichier que l'utilisateur depose sur la plateforme
            target.with_suffix(".srt").write_text(srt, encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "project": project,
        "project_path": str(target),
        "name": name,
        "voice_ref": voice_ref,
        "thumbnail_ref": thumbnail_ref,
        "srt_available": bool(srt),
        "srt_path": str(target.with_suffix(".srt")) if srt else "",
        "start": generated["start"],
        "end": generated["end"],
        "duration": generated["duration"],
        "cues": generated["cues"],
        "timeline": generated["timeline"],
        "publish": project.get("publish") or {},
        "warnings": warnings + list(generated["warnings"]),
    }
