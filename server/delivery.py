"""Paquet de livraison d'un lot : videos, sous-titres, miniatures, metadonnees et manifeste.

Le paquet est un ZIP pose dans ``batch/deliveries/``, a cote du manifeste deja ecrit
par la file. Trois regles commandent ce module :

1. rien d'invente — les .srt viennent des fenetres reellement rendues
   (``shortvideos.delivery``), le manifeste vient de ``queue.write_manifest`` et les
   metadonnees du bloc ``publish`` du projet, recopie tel quel ;
2. rien de lourd dans le thread de requete — l'assemblage tourne dans un job, avec
   progression et annulation comme un lot ;
3. un seul paquet a la fois par lot, ecriture en ``.part.zip`` puis remplacement
   atomique : un paquet a demi ecrit ne doit jamais remplacer le precedent.
"""
from __future__ import annotations

import json
import shutil
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from shortvideos import delivery as delivery_mod

from . import queue as queue_mod
from .jobs import Job, raise_if_cancelled
from .security import DELIVERIES_DIR, assert_local_dir, safe_name

_LOCK = threading.Lock()
_RUNNING: set[str] = set()

THUMBNAIL_RATIO = 0.45


def _stem(batch_id: str, name: str) -> str:
    return f"{batch_id}-{safe_name(name or 'lot')}"


def package_path(batch_id: str, name: str = "") -> Path:
    return assert_local_dir(DELIVERIES_DIR / f"{_stem(batch_id, name)}.zip")


def state_path(batch_id: str, name: str = "") -> Path:
    return assert_local_dir(DELIVERIES_DIR / f"{_stem(batch_id, name)}.package.json")


def _read_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _video_of(item: dict) -> Path | None:
    """Chemin disque de la video d'un item, seulement si elle est rendue et relisible."""
    if str(item.get("status") or "") != "done":
        return None
    raw = str(item.get("output_path") or "")
    if not raw:
        return None
    try:
        path = assert_local_dir(Path(raw))
    except (HTTPException, OSError, ValueError):
        return None
    return path if path.is_file() else None


def publish_of(project: dict) -> dict:
    """Les champs de publication remplis dans le projet, et rien d'autre.

    Un projet venu d'un moment fort porte deja titre, description et hashtags ; un
    projet griffonne a la main peut en porter aussi. Le bloc est recopie tel quel : le
    paquet ne redige jamais une legende a la place du client.
    """
    publish = (project or {}).get("publish") or {}
    out: dict = {}
    for key in ("title", "description"):
        text = str(publish.get(key) or "").strip()
        if text:
            out[key] = text
    tags = publish.get("hashtags")
    if isinstance(tags, list) and any(str(tag).strip() for tag in tags):
        out["hashtags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
    return out


def status(batch_id: str) -> dict:
    """Etat du lot vu de la page Livraison : ce qui est pret, ce qui est empaquete."""
    batch = queue_mod.get_batch(batch_id, items=True)
    items = batch.get("items") or []
    pack = package_path(batch_id, batch["name"])
    pack_exists = pack.is_file()
    return {
        "batch": {
            "id": batch["id"],
            "name": batch["name"],
            "model_id": batch.get("model_id", ""),
            "status": batch["status"],
            "counters": batch.get("counters") or {},
        },
        "total": len(items),
        "rendered": sum(1 for item in items if _video_of(item)),
        "is_packaging": batch_id in _RUNNING,
        "package": (
            {
                "file": pack.name,
                "bytes": pack.stat().st_size,
                "modified_at": datetime.fromtimestamp(pack.stat().st_mtime).isoformat(timespec="seconds"),
                **_read_state(state_path(batch_id, batch["name"])),
            }
            if pack_exists
            else None
        ),
        "items": [
            {
                "position": item["position"],
                "nom": item.get("name") or "",
                "fichier": safe_name(str(item.get("filename") or "video.mp4")),
                "statut": item.get("status"),
                "duree_s": item.get("duration") or 0,
                "octets": item.get("size_bytes") or 0,
                "rendered": bool(_video_of(item)),
            }
            for item in items
        ],
    }


def _notice(batch: dict, counts: dict, warnings: list[str]) -> str:
    lines = [
        f"Lot : {batch['name']}  (identifiant {batch['id']})",
        f"Préparé le : {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"vidéos      : {counts['videos']} fichier(s) dans videos/",
        f"sous-titres : {counts['subtitles']} fichier(s) .srt dans subtitles/",
        f"miniatures  : {counts['thumbnails']} fichier(s) .png dans thumbnails/",
        f"métadonnées : {counts['metadata']} fichier(s) .json dans metadata/ (titre, description, hashtags saisis dans le projet)",
        "manifeste   : manifeste.json et manifeste.csv (mêmes colonnes que la page Production)",
        "",
        "Les sous-titres reprennent les fenêtres d'animation réellement rendues :",
        "un cue commence à la frame d'entrée du calque et finit à sa frame de sortie.",
        "La signature de marque n'est pas sous-titrée — ce n'est pas une réplique.",
        f"Les miniatures sont la frame à {int(THUMBNAIL_RATIO * 100)} % de la durée de la vidéo.",
        "",
        "Assemblé localement par youtube_clipper, sans service externe.",
    ]
    if warnings:
        lines += ["", "Avertissements :"] + [f"- {warning}" for warning in warnings]
    return "\r\n".join(lines) + "\r\n"


def build_package(batch_id: str, job: Job | None = None) -> dict:
    """Assemble le ZIP du lot et renvoie son inventaire. A appeler dans un job."""
    with _LOCK:
        if batch_id in _RUNNING:
            raise HTTPException(status_code=409, detail="Un paquet de livraison est déjà en cours pour ce lot.")
        _RUNNING.add(batch_id)

    pack: Path | None = None
    tmp_zip: Path | None = None
    staging = DELIVERIES_DIR / "_tmp" / batch_id
    try:
        batch = queue_mod.get_batch(batch_id, items=True)
        items = [item for item in (batch.get("items") or []) if _video_of(item)]
        if not items:
            raise HTTPException(status_code=400, detail="Aucune vidéo rendue dans ce lot : rien à livrer.")

        DELIVERIES_DIR.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)

        pack = package_path(batch_id, batch["name"])
        tmp_zip = DELIVERIES_DIR / f"{_stem(batch_id, batch['name'])}.part.zip"
        if tmp_zip.exists():
            tmp_zip.unlink()

        warnings: list[str] = []
        counts = {"videos": 0, "subtitles": 0, "thumbnails": 0, "metadata": 0}
        manifests: list[Path] = []
        for fmt in ("json", "csv"):
            try:
                manifests.append(Path(queue_mod.write_manifest(batch_id, fmt)["manifest"]))
            except Exception as exc:  # noqa: BLE001 - un manifeste absent se signale, ne casse pas le paquet
                warnings.append(f"Manifeste {fmt} indisponible : {exc}")

        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for position, item in enumerate(items, start=1):
                if job is not None:
                    raise_if_cancelled(job)
                    job.set_progress(position - 1, len(items), f"Livraison de {_video_of(item).name}…")

                video = _video_of(item)
                stem = video.name[:-4] if video.name.lower().endswith(".mp4") else safe_name(video.name)
                archive.write(video, f"videos/{video.name}")
                counts["videos"] += 1

                # Le sous-titre vient du projet tel qu'il a ete planifie : memes
                # frames que le rendu, aucun calcul parallele.
                try:
                    srt = delivery_mod.srt_from_project(item.get("project") or {})
                except Exception as exc:  # noqa: BLE001 - un SRT rate ne bloque pas le paquet
                    srt = ""
                    warnings.append(f"{stem} : sous-titres impossibles ({exc})")
                if srt:
                    archive.writestr(f"subtitles/{stem}.srt", srt.encode("utf-8"))
                    counts["subtitles"] += 1
                else:
                    warnings.append(f"{stem} : aucun texte sous-titrable")

                thumb = delivery_mod.make_thumbnail(video, staging / f"{stem}.png", ratio=THUMBNAIL_RATIO)
                if thumb["path"]:
                    archive.write(thumb["path"], f"thumbnails/{stem}.png")
                    counts["thumbnails"] += 1
                if thumb["warning"]:
                    warnings.append(f"{stem} : miniature — {thumb['warning']}")

                marketing = publish_of(item.get("project") or {})
                if marketing:
                    marketing["fichier"] = f"videos/{video.name}"
                    archive.writestr(
                        f"metadata/{stem}.json",
                        json.dumps(marketing, ensure_ascii=False, indent=2).encode("utf-8"),
                    )
                    counts["metadata"] += 1

            for path in manifests:
                if path.is_file():
                    archive.write(path, f"manifeste.{path.name.rsplit('.', 1)[-1]}")
            archive.writestr("LISEZ-MOI.txt", _notice(batch, counts, warnings).encode("utf-8"))

        tmp_zip.replace(pack)
        state = {
            "prepared_at": datetime.now().isoformat(timespec="seconds"),
            "batch_name": batch["name"],
            "model_id": batch.get("model_id", ""),
            **counts,
            "warnings": warnings,
        }
        state_path(batch_id, batch["name"]).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        if job is not None:
            job.set_progress(len(items), len(items), "Paquet prêt.")
        return {"package": str(pack), "file": pack.name, "bytes": pack.stat().st_size, **counts, "warnings": warnings}
    finally:
        if tmp_zip is not None:
            tmp_zip.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        with _LOCK:
            _RUNNING.discard(batch_id)
