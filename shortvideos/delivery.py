"""Pieces livrables sans moteur supplementaire : sous-titres et miniatures.

Deux regles commandent ce module :

1. aucun paquet ajoute — l'SRT est ecrit a la main (pas de ``@remotion/captions`` ;
   la reconnaissance vocale vit dans ``asr.py``, pas ici) et l'image vient du ffmpeg
   deja embarque par ``imageio_ffmpeg`` ;
2. les temps viennent de ``resolve()``, c'est-a-dire des frames absolues recues par
   Remotion. Un .srt qui ne correspondrait pas a l'animation reellement rendue serait
   une promesse commerciale fausse.

Le texte des calques n'est pas dans le bloc ``resolved`` (il reste dans ``content``) :
``srt_cues`` croise donc les fenetres resolues avec les calques du projet, en ignorant
les scenes et calques masques, et en excluant la signature de marque — un filigrane
n'est pas une replique.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg

from . import probe, resolve


MIN_CUE_FRAMES = 1


def _timestamp(seconds: float) -> str:
    """``00:01:23,456`` comme l'exige le format SRT (millisecondes, virgule)."""
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _clean_text(raw) -> str:
    """Un cue SRT ne accepte que des sauts de ligne LF. L'indentation du calque est
    retiree — elle releve de la mise en page, pas du texte — et les lignes vides de
    tete et de queue aussi ; celles du corps sont gardees, elles portent le vers."""
    lines = [line.strip() for line in str(raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _windows_by_layer_id(resolved_scene: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for layer in resolved_scene.get("layers") or []:
        key = str(layer.get("id") or "")
        if key and key not in out:
            out[key] = layer
    return out


def _resolved_scene_by_id(resolved: dict, scene_id: str) -> dict | None:
    for scene in resolved.get("scenes") or []:
        if str(scene.get("id") or "") == str(scene_id or ""):
            return scene
    return None


def srt_cues(project: dict) -> list[dict]:
    """Segments horodatees, dans l'ordre d'apparition a l'ecran.

    Chaque segment porte ``start`` / ``end`` en secondes et le texte du calque. Une
    duree minimale d'une frame est garantie : deux bornes identiques produiraient un
    cue invalide que la plupart des lecteurs rejettent.
    """
    resolved = resolve.resolve(project).get(resolve.RESOLVED_KEY) or {}
    fps = int(resolved.get("fps") or 30) or 30
    total_frames = int(resolved.get("total_frames") or 0)
    content = (project.get("content") or {})

    cues: list[dict] = []
    for scene in content.get("scenes") or []:
        if not isinstance(scene, dict) or scene.get("hidden"):
            continue
        rs = _resolved_scene_by_id(resolved, scene.get("id"))
        if not rs or rs.get("hidden"):
            continue
        windows = _windows_by_layer_id(rs)
        for layer in scene.get("layers") or []:
            if not isinstance(layer, dict) or layer.get("hidden"):
                continue
            if layer.get("type") != "text":
                continue
            text = _clean_text(layer.get("text"))
            if not text:
                continue
            window = windows.get(str(layer.get("id") or ""))
            if not window:
                continue
            start = max(0, int(window.get("start_frame") or 0))
            end = int(window.get("end_frame") or 0)
            if total_frames:
                end = min(end, total_frames)
            if end <= start:
                end = start + MIN_CUE_FRAMES
            if start >= total_frames > 0:
                continue
            cues.append(
                {
                    "index": len(cues) + 1,
                    "scene_id": str(scene.get("id") or ""),
                    "layer_id": str(layer.get("id") or ""),
                    "start_frame": start,
                    "end_frame": end,
                    "start": round(start / fps, 3),
                    "end": round(end / fps, 3),
                    "text": text,
                }
            )

    cues.sort(key=lambda c: (c["start_frame"], c["end_frame"]))
    for position, cue in enumerate(cues, start=1):
        cue["index"] = position
    return cues


def srt_from_project(project: dict) -> str:
    """Fichier .srt complet (UTF-8, toutes les fins de ligne en CRLF) ou chaine vide.

    Un seul type de fin de ligne dans tout le fichier, y compris dans les cues
    multilignes : un SRT qui melerait LF et CRLF se lit mal selon le lecteur.
    """
    cues = srt_cues(project)
    if not cues:
        return ""
    blocks = [
        f"{cue['index']}\n{_timestamp(cue['start'])} --> {_timestamp(cue['end'])}\n{cue['text']}" for cue in cues
    ]
    return ("\n\n".join(blocks) + "\n").replace("\n", "\r\n")


def make_thumbnail(
    mp4_path,
    out_path,
    *,
    at_seconds: float | None = None,
    ratio: float = 0.45,
    overwrite: bool = False,
) -> dict:
    """Extrait une frame PNG avec le ffmpeg deja installe, sans jamais lever.

    Une miniature ratee ne doit pas faire echouer une livraison : l'echec remonte
    dans ``warning`` et le paquet est simplement ampute de cette image.
    """
    src = Path(mp4_path)
    out = Path(out_path)
    result = {"source": str(src), "path": "", "at_seconds": None, "warning": ""}

    if not src.is_file():
        result["warning"] = f"Video absente : {src.name}"
        return result
    if out.exists() and not overwrite:
        result["warning"] = f"Miniature deja presente : {out.name}"
        result["path"] = str(out)
        return result

    try:
        meta = probe.probe_mp4(str(src))
    except Exception as exc:  # noqa: BLE001 - la sonde ne doit jamais bloquer un paquet
        result["warning"] = f"Video illisible : {exc}"
        return result

    duration = float(meta.get("duration") or 0.0)
    if duration <= 0:
        result["warning"] = "Duree inconnue : aucune miniature possible."
        return result

    if at_seconds is None:
        at = max(0.0, min(duration * float(ratio), duration - 0.04))
    else:
        at = max(0.0, min(float(at_seconds), duration - 0.04))
    result["at_seconds"] = round(at, 3)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.png")
    if tmp.exists():
        tmp.unlink()

    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{at:.3f}",
        "-i",
        str(src),
        "-frames:v",
        "1",
        str(tmp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as exc:  # noqa: BLE001 - ffmpeg absent ou tue = avertissement
        result["warning"] = f"ffmpeg indisponible : {exc}"
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return result

    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        result["warning"] = (
            f"Miniature impossible (code {proc.returncode}) : "
            f"{(proc.stderr or '').strip()[:200] or 'aucun detail'}"
        )
        tmp.unlink(missing_ok=True)
        return result

    if out.exists():
        out.unlink()
    tmp.replace(out)
    result["path"] = str(out)
    return result
