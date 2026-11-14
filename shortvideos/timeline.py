"""Rendu d'un EDL en MP4, avec FFmpeg seul (aucun Remotion, aucun ffprobe).

Trois passes, dans cet ordre :

1. **normalisation** : chaque plan est decode depuis sa source, coupe a
   ``in``/``out``, recadre sur le canevas, ramene au bon fps et a un audio
   stereo 48 kHz (silence genere si le rush n'a pas de piste audio) ;
2. **assemblage** : les plans sont concatenes par groupes ; un groupe est une
   suite de coupes franches (filtre ``concat``), deux groupes se rejoignent par
   une transition ``xfade`` (video) et ``acrossfade`` (audio) ;
3. **finition** : etalonnage, musique (bouclee, fondue, ducking sous la voix)
   puis encodage final.

Cette approche en trois passes est plus lente qu'un unique ``filter_complex``
mais beaucoup plus robuste : sources de codecs, resolutions et fps differents,
rushs muets, fichiers plus courts que prevu. Les durees reelles sont relues
apres normalisation et le resultat le signale si le plan ne tient pas.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

import imageio_ffmpeg

from . import edl as edl_mod
from .probe import duration_ffmpeg, has_audio_stream, probe_mp4

# 1920x1080 a 25 fps en veryfast : marge confortable pour un montage de 60 s
CUT_CRF = 18
FINAL_CRF = 20
AUDIO_BITRATE = "192k"
SAMPLE_RATE = 48000
# marge entre la duree planifiee et la duree rendue (secondes + ratio)
DURATION_TOLERANCE = 0.35

_GRADES = {
    "warm": "colorbalance=rs=.08:gs=.02:bs=-.06",
    "cool": "colorbalance=rs=-.06:gs=0:bs=.08",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "mono": "hue=s=0",
    "teal_orange": "colorbalance=rs=-.05:bs=.08",
}


class TimelineError(RuntimeError):
    """Le montage n'a pas pu etre rendu."""


class TimelineCancelled(Exception):
    """Le worker a ete interrompu ; la couche serveur le traduit en JobCancelled."""


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def _run(job, args: list[str], log_path: Path, timeout: float) -> None:
    """Lance ffmpeg en surveillant l'annulation ; la sortie va dans un fichier."""
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        job.result_process = proc  # type: ignore[attr-defined]
        deadline = time.time() + timeout
        while proc.poll() is None:
            if job.cancel_event.is_set():
                _terminate(proc)
                raise TimelineCancelled()
            if time.time() > deadline:
                _terminate(proc)
                raise TimelineError(f"ffmpeg a depasse {int(timeout)} s.")
            time.sleep(0.1)
    if proc.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-12:]
        raise TimelineError(
            f"ffmpeg a echoue (code {proc.returncode}) :\n" + ("\n".join(tail) or "aucune sortie")
        )


def _canonical_filter(width: int, height: int, fps: float) -> str:
    """Recadre sans deformer, force le fps et le pixel format d'encodage."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p"
    )


def _normalize_cut(
    job,
    source: Path,
    start: float,
    duration: float,
    destination: Path,
    canvas: dict,
    has_audio: bool,
    log_path: Path,
) -> None:
    width, height, fps = canvas["width"], canvas["height"], canvas["fps"]
    args = [
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
    ]
    if has_audio:
        graph = (
            f"[0:v]{_canonical_filter(width, height, fps)}[v];"
            f"[0:a]aresample={SAMPLE_RATE},"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo[a]"
        )
    else:
        args += [
            "-f", "lavfi", "-t", f"{duration:.3f}",
            "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}",
        ]
        graph = (
            f"[0:v]{_canonical_filter(width, height, fps)}[v];"
            f"[1:a]anull[a]"
        )
    args += [
        "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CUT_CRF),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(SAMPLE_RATE), "-ac", "2",
        str(destination),
    ]
    _run(job, args, log_path, timeout=max(120.0, duration * 20))


def _group_concat_inputs(count: int) -> str:
    """Entrees et filtre ``concat`` pour un groupe de coupes franches."""
    return "".join(f"[{index}:v][{index}:a]" for index in range(count)) + f"concat=n={count}:v=1:a=1"


def _assemble(
    job,
    parts: list[Path],
    durations: list[float],
    transitions: list[dict],
    canvas: dict,
    destination: Path,
    log_path: Path,
) -> None:
    """Concatene les plans normalises, transitions comprises."""
    groups: list[list[int]] = [[0]] if parts else []
    for index in range(1, len(parts)):
        if float(transitions[index].get("duration") or 0.0) > 0:
            groups.append([index])
        else:
            groups[-1].append(index)

    fps = canvas["fps"]
    args = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    for part in parts:
        args += ["-i", str(part)]

    graph: list[str] = []
    group_v: list[str] = []
    group_a: list[str] = []
    group_duration: list[float] = []

    if len(groups) == 1:
        graph.append(f"{_group_concat_inputs(len(parts))}[vout][aout]")
    else:
        for group_index, members in enumerate(groups):
            if len(members) == 1:
                source = members[0]
                graph.append(f"[{source}:v]null[gv{group_index}];[{source}:a]anull[ga{group_index}]")
            else:
                # les entrees du groupe ne sont pas contigues dans le graphe :
                # on les cite explicitement, dans l'ordre des plans
                inputs = "".join(f"[{member}:v][{member}:a]" for member in members)
                graph.append(
                    f"{inputs}concat=n={len(members)}:v=1:a=1"
                    f"[gv{group_index}][ga{group_index}]"
                )
            group_v.append(f"gv{group_index}")
            group_a.append(f"ga{group_index}")
            group_duration.append(sum(durations[member] for member in members))

        previous_v, previous_a = group_v[0], group_a[0]
        elapsed = group_duration[0]
        for group_index in range(1, len(groups)):
            first_member = groups[group_index][0]
            transition = transitions[first_member]
            name = edl_mod.TRANSITIONS.get(transition.get("type", "cut")) or "fade"
            length = float(transition.get("duration") or 0.0)
            offset = max(0.0, elapsed - length)
            out_v, out_a = f"vx{group_index}", f"ax{group_index}"
            graph.append(
                f"[{previous_v}][{group_v[group_index]}]"
                f"xfade=transition={name}:duration={length:.3f}:offset={offset:.3f}[{out_v}]"
            )
            graph.append(
                f"[{previous_a}][{group_a[group_index]}]acrossfade=d={length:.3f}[{out_a}]"
            )
            elapsed = elapsed + group_duration[group_index] - length
            previous_v, previous_a = out_v, out_a

        graph.append(f"[{previous_v}]null[vout];[{previous_a}]anull[aout]")

    args += [
        "-filter_complex", ";".join(graph),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CUT_CRF),
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(SAMPLE_RATE), "-ac", "2",
        str(destination),
    ]
    total = sum(durations)
    _run(job, args, log_path, timeout=max(180.0, total * 20))


def _grade_filter(grade: dict) -> str:
    look = grade.get("look") or "none"
    parts: list[str] = []
    saturation = float(grade.get("saturation", 1.0))
    contrast = float(grade.get("contrast", 1.0))
    if abs(saturation - 1.0) > 1e-3 or abs(contrast - 1.0) > 1e-3:
        parts.append(f"eq=contrast={contrast:.3f}:saturation={saturation:.3f}")
    if look in _GRADES:
        parts.append(_GRADES[look])
    return ",".join(parts)


def _finish(
    job,
    body: Path,
    edl: dict,
    destination: Path,
    log_path: Path,
    has_voice: bool,
    duration: float | None = None,
) -> None:
    """Etalonnage + musique + encodage final (ou copie si rien a faire)."""
    grade = _grade_filter(edl.get("grade") or {})
    audio = edl.get("audio") or {}
    if not grade and not audio:
        shutil.copyfile(body, destination)
        return

    duration = float(duration) if duration else edl_mod.timeline_duration(edl)
    args = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(body)]
    filters: list[str] = []
    video_label = "0:v"

    if grade:
        filters.append(f"[0:v]{grade}[v]")
        video_label = "v"

    audio_label = None
    if audio:
        music_path = Path(audio["_path"])  # injecte par l'appelant apres resolution
        args += ["-stream_loop", "-1", "-i", str(music_path)]
        gain = float(audio.get("gain_db", -18.0))
        fade_in = max(0.0, float(audio.get("fade_in", 0.0)))
        fade_out = max(0.0, min(float(audio.get("fade_out", 0.0)), duration))
        chain = [
            f"atrim=0:{duration:.3f}",
            "asetpts=N/SR/TB",
            f"volume={gain}dB",
        ]
        if fade_in > 0:
            chain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
        if fade_out > 0:
            chain.append(f"afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}")
        filters.append("[1:a]" + ",".join(chain) + "[music]")

        if audio.get("duck", True) and has_voice:
            filters.append("[0:a]asplit=2[voice][sc]")
            filters.append(
                "[music][sc]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=250[ducked]"
            )
            filters.append("[voice][ducked]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            filters.append("[music][0:a]amix=inputs=2:duration=first:normalize=0[a]")
        audio_label = "a"

    args += ["-filter_complex", ";".join(filters)]
    args += ["-map", f"[{video_label}]" if video_label != "0:v" else "0:v"]
    if audio_label:
        args += ["-map", f"[{audio_label}]"]
    else:
        args += ["-map", "0:a?", "-c:a", "copy"]

    args += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(FINAL_CRF),
        "-pix_fmt", "yuv420p",
    ]
    if audio_label:
        args += ["-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(SAMPLE_RATE), "-ac", "2"]
    args += ["-movflags", "+faststart", str(destination)]
    _run(job, args, log_path, timeout=max(180.0, duration * 20))


def render_timeline(
    job,
    edl: dict,
    out_path: Path,
    *,
    media_lookup: Callable[[str], Path],
    work_dir: Path | None = None,
) -> dict:
    """Rend un EDL valide en MP4.

    ``media_lookup`` resout un identifiant ``media://`` en chemin disque (le
    serveur passe ``media.resolve_media`` ; les tests passent une table). Le
    rendu ne lit jamais un chemin fourni par le client.
    """
    warnings: list[str] = []

    def exists(media_id: str) -> bool:
        try:
            media_lookup(media_id)
            return True
        except Exception:  # noqa: BLE001 - un média absent est une erreur d'EDL
            return False

    normalized = edl_mod.validate_or_raise(edl, media_exists=exists)
    canvas = normalized["canvas"]
    cuts = normalized["cuts"]

    # un même rush peut servir deux plans : duree et piste audio se lisent une fois.
    media_info: dict[str, tuple[float | None, bool]] = {}

    def info_of(path: Path) -> tuple[float | None, bool]:
        key = str(path)
        if key not in media_info:
            media_info[key] = (duration_ffmpeg(key), has_audio_stream(key))
        return media_info[key]

    sources: list[dict] = []
    for index, cut in enumerate(cuts):
        media_id = edl_mod.media_id_of(cut["media"])
        path = Path(media_lookup(media_id))
        if not path.is_file():
            raise TimelineError(f"cuts[{index}] : fichier introuvable pour le média {media_id}.")
        real, has_audio = info_of(path)
        start = float(cut["in"])
        planned = float(cut["out"]) - start
        if real is not None:
            if start >= real - 0.05:
                raise TimelineError(
                    f"cuts[{index}].in ({start:.2f} s) tombe apres la fin du rush ({real:.2f} s)."
                )
            if start + planned > real:
                clamped = max(0.0, real - start)
                warnings.append(
                    f"cuts[{index}] : rush de {real:.2f} s, plan ramene de {planned:.2f} s a {clamped:.2f} s."
                )
                planned = clamped
                if planned < edl_mod.MIN_CUT_SECONDS:
                    raise TimelineError(
                        f"cuts[{index}] : reste {planned:.2f} s apres « in », plan inutilisable."
                    )
                cut["out"] = start + planned
        sources.append(
            {
                "path": path,
                "start": start,
                "duration": planned,
                "has_audio": has_audio,
            }
        )

    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="montage-"))
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "ffmpeg.log"
    try:
        parts: list[Path] = []
        rendered: list[float] = []
        total_cuts = len(sources)
        for index, source in enumerate(sources):
            job.set_progress(int(index / total_cuts * 70), 100, f"Plan {index + 1}/{total_cuts}")
            if job.cancel_event.is_set():
                raise TimelineCancelled()
            part = work / f"cut-{index:03d}.mp4"
            _normalize_cut(
                job, source["path"], source["start"], source["duration"],
                part, canvas, source["has_audio"], log_path,
            )
            parts.append(part)
            # duree reelle du plan normalise : les offsets de transition se calculent
            # sur le fichier produit, pas sur la duree theorique du rush.
            actual = duration_ffmpeg(str(part))
            rendered.append(actual if actual and actual > 0 else source["duration"])

        overlap = sum(
            float(cut["transition"].get("duration") or 0.0) for cut in cuts[1:]
        )
        body_duration = max(0.0, sum(rendered) - overlap)

        body = work / "body.mp4"
        job.set_progress(72, 100, "Assemblage")
        _assemble(job, parts, rendered,
                  [cut["transition"] for cut in cuts], canvas, body, log_path)

        if normalized.get("audio"):
            music_id = edl_mod.media_id_of(normalized["audio"]["music"])
            normalized["audio"]["_path"] = str(Path(media_lookup(music_id)))

        final = work / "final.mp4"
        job.set_progress(88, 100, "Finition")
        _finish(job, body, normalized, final, log_path,
                any(s["has_audio"] for s in sources), duration=body_duration)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(final, out_path)

        job.set_progress(97, 100, "Verification")
        info = probe_mp4(str(out_path))
        planned = edl_mod.timeline_duration(normalized)
        actual = float(info.get("duration") or 0.0)
        if planned and abs(actual - planned) > DURATION_TOLERANCE + planned * 0.02:
            warnings.append(
                f"duree rendue {actual:.2f} s pour {planned:.2f} s planifiees "
                "(rushs plus courts ou transitions chevauchees)."
            )
        return {
            "path": str(out_path),
            "width": info["width"],
            "height": info["height"],
            "fps": info["fps"],
            "duration": actual,
            "planned_duration": round(planned, 3),
            "size_bytes": out_path.stat().st_size,
            "cuts": len(cuts),
            "music": bool(normalized.get("audio")),
            "grade": normalized["grade"]["look"],
            "has_audio": has_audio_stream(str(out_path)),
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
