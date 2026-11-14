"""Entree de rendu unique, partagee par l'export unitaire et la production.

Un projet -> un MP4. L'export d'une video isolee comme le rendu d'un lot de
100 lignes passent par ``render_project_to_mp4()`` : il n'existe qu'une seule
chaine d'execution, donc un correctif de rendu profite aux deux usages.

Etapes :
1. resolution du projet (frames absolues, modele, graine) ;
2. references media -> URLs locales du cache de rendu ;
3. sous-processus ``remotion render`` dans ``web/`` (jamais dans le thread de
   requete) avec l'identifiant de composition vient du projet, pas du code ;
4. progression reellement lue dans la sortie du rendu ;
5. annulation = terminaison du sous-processus.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import math
import time
import uuid
from pathlib import Path

import imageio_ffmpeg

from shortvideos import resolve as resolve_mod
from shortvideos import schema

from . import mediacache
from .jobs import Job, JobCancelled
from .security import ROOT

WEB_DIR = ROOT / "web"
ENTRY = "src/remotion/index.tsx"

_PROGRESS_RE = re.compile(r"(?:Rendered|Rendering|Encoded)\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)


def node_command() -> Path:
    """Node.js portable du projet, sinon celui du PATH."""
    portable = ROOT.parent / "_tools" / "node" / "node.exe"
    if portable.exists():
        return portable
    raise RuntimeError(
        "Node.js introuvable dans _tools/node. Relancez start_web.bat "
        "ou installez Node.js 18+."
    )


def _env() -> dict:
    env = dict(os.environ)
    node_dir = ROOT.parent / "_tools" / "node"
    if (node_dir / "node.exe").exists():
        env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")
    return env


def prepare_for_render(project: dict) -> dict:
    """Projet edite -> objet de props du rendu (resollu + URLs medias)."""
    if project.get("version") == schema.SCHEMA_VERSION_V2:
        prepared = resolve_mod.resolve(project)
    else:
        prepared = copy.deepcopy(project)
    return mediacache.to_render_urls(prepared)


def composition_id_of(project: dict) -> str:
    """Identifiant de la composition passe a Remotion.

    Les ids de modele du projet sont en snake_case (format JSON, tests,
    presets) alors que Remotion n'accepte que ``[a-zA-Z0-9-]`` : le registre
    frontend applique la meme correspondance (``quote_cinematic`` ->
    ``quote-cinematic``), donc l'aperçu et le rendu visent la meme entree.
    """
    if project.get("version") == schema.SCHEMA_VERSION_V2:
        return _remotion_id(resolve_mod.composition_id(project))
    template = str(project.get("template", ""))
    if template not in schema.MODELS:
        raise RuntimeError(f"Modele inconnu pour le rendu : {template!r}.")
    return _remotion_id(template)


def _remotion_id(model_id: str) -> str:
    return model_id.replace("_", "-")


def remotion_cli() -> Path:
    cli = WEB_DIR / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not cli.exists():
        raise RuntimeError("Remotion CLI introuvable : lancez 'npm install' dans web/.")
    if not (WEB_DIR / "package.json").exists():
        raise RuntimeError("Frontend absent : dossier web/ introuvable.")
    return cli


def render_project_to_mp4(job: Job, project: dict, out_path: Path) -> dict:
    """Rendu reel d'UN projet. Utilise par l'export unitaire et par la file."""
    prepared = prepare_for_render(project)
    composition = composition_id_of(project)

    props_path = mediacache.write_props(prepared, job.id)
    try:
        cmd = [
            str(node_command()),
            str(remotion_cli()),
            "render",
            ENTRY,
            composition,
            str(out_path),
            f"--props={props_path}",
            "--codec=h264",
            "--log=info",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(WEB_DIR),
            env=_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        job.result_process = proc  # type: ignore[attr-defined]

        tail: list[str] = []
        total_seen = 0
        for line in proc.stdout:  # type: ignore[union-attr]
            tail.append(line.rstrip())
            if len(tail) > 200:
                tail.pop(0)
            match = _PROGRESS_RE.search(line)
            if match:
                current, total = int(match.group(1)), int(match.group(2))
                total_seen = max(total_seen, total)
                job.set_progress(current, total or 1, f"Rendu {current}/{total}")
            if job.cancel_event.is_set():
                _terminate(proc)
                raise JobCancelled()
            if proc.poll() is not None:
                break

        returncode = proc.wait(timeout=30)
        if job.cancel_event.is_set():
            raise JobCancelled()
        if returncode != 0:
            raise RuntimeError(
                f"Le rendu Remotion a echoue (code {returncode}) :\n"
                + ("\n".join(tail[-25:]) or "aucune sortie")
            )
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError("Le rendu n'a produit aucun fichier.")

        normalized = _normalize_loudness(job, out_path)

        from shortvideos.probe import probe_mp4

        info = probe_mp4(str(out_path))
        info["path"] = str(out_path)
        info["size_bytes"] = out_path.stat().st_size
        info["composition"] = composition
        info["frames_expected"] = total_seen
        info["loudness_normalized"] = normalized
        return info
    finally:
        props_path.unlink(missing_ok=True)


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


LOUDNORM_FILTER = "loudnorm=I=-14:TP=-1.5:LRA=11"
LOUDNORM_TIMEOUT_SECONDS = 180.0


def _normalize_loudness(job: Job, out_path: Path) -> bool:
    """Loudness pro du mix final, sans re-rendu video.

    Cible -14 LUFS / -1.5 dBTP (reseaux sociaux) puis ``aresample=48000`` :
    loudnorm surechantillonne en interne a 192 kHz, on revient a 48 kHz pour
    l'AAC. La video est copiee (``-c:v copy``), seule la piste audio est
    refiltree. Best-effort : un echec garde le render original et ne casse pas
    l'export. Retourne True si la normalisation a ete appliquee.
    """
    from shortvideos.probe import has_audio_stream

    try:
        if not has_audio_stream(str(out_path)):
            return False
    except (OSError, RuntimeError):
        return False

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    temp = out_path.with_name(out_path.stem + ".loudnorm.mp4")
    cmd = [
        ffmpeg, "-hide_banner", "-y", "-i", str(out_path),
        "-c:v", "copy",
        "-af", f"{LOUDNORM_FILTER},aresample=48000",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(temp),
    ]
    proc = None
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(WEB_DIR), env=_env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        job.result_process = proc
        deadline = time.monotonic() + LOUDNORM_TIMEOUT_SECONDS
        while True:
            if job.cancel_event.is_set():
                raise JobCancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                proc.communicate(timeout=min(0.25, remaining))
                break
            except subprocess.TimeoutExpired:
                pass
        if job.cancel_event.is_set():
            raise JobCancelled()
        if proc.returncode != 0:
            return False
        if not temp.exists() or temp.stat().st_size == 0:
            return False
        os.replace(temp, out_path)
        return True
    except JobCancelled:
        raise
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        job.result_process = None
        if proc is not None and proc.poll() is None:
            _terminate(proc)
        temp.unlink(missing_ok=True)


FRAME_TIMEOUT_SECONDS = 120.0
_FRAME_LOG_LIMIT = 6000


def _frame_log(output: str | bytes | None) -> str:
    """Keep both the beginning and end of a command's log, never credentials."""
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    text = output or "aucune sortie"
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    text = re.sub(r"(?i)\b(?:https?|file)://[^\s\"<>]+", "[URL redacted]", text)
    text = re.sub(r"(?i)data:[^\s\"<>]+", "[data redacted]", text)
    text = re.sub(
        r"(?i)(authorization|bearer|api[_-]?key|token|password|secret|pin)"
        r"[\s\"':=]+[^\s,;]+", r"\1=[redacted]", text,
    )
    # Render subprocesses inherit the environment, but must not echo its secrets.
    for key, value in os.environ.items():
        if value and re.search(r"(?i)(key|token|secret|password|pin)$", key):
            text = text.replace(value, "[redacted]")
    if len(text) > _FRAME_LOG_LIMIT:
        half = (_FRAME_LOG_LIMIT - 40) // 2
        text = text[:half] + "\n[log truncated]\n" + text[-half:]
    return text


def _communicate_frame(job: Job, proc: subprocess.Popen, frame: int) -> str:
    """Poll even silent children; communicate drains both pipes without readline."""
    deadline = time.monotonic() + FRAME_TIMEOUT_SECONDS
    output: str | bytes | None = None
    completed = False
    try:
        while True:
            if job.cancel_event.is_set():
                raise JobCancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Remotion frame {frame}: timeout after {FRAME_TIMEOUT_SECONDS:g}s.\n"
                    + _frame_log(output)
                )
            try:
                output, _ = proc.communicate(timeout=min(0.25, remaining))
                completed = True
                if job.cancel_event.is_set():
                    raise JobCancelled()
                return output or ""
            except subprocess.TimeoutExpired as exc:
                # TimeoutExpired.output contains all output collected so far.
                if exc.output is not None:
                    output = exc.output
    finally:
        if not completed:
            _terminate(proc)
            try:
                proc.communicate(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()


def render_project_frames(job: Job, project: dict, frames: list[int], out_dir: Path, audit_layout: bool = False) -> list[Path]:
    """Render at most six small stills, without changing the export pipeline."""
    if (not isinstance(frames, list) or not 1 <= len(frames) <= 6
            or any(type(frame) is not int for frame in frames)
            or len(set(frames)) != len(frames)):
        raise ValueError("frames must contain 1 to 6 distinct integer frame numbers.")
    if job.cancel_event.is_set():
        raise JobCancelled()
    clean = copy.deepcopy(project)
    clean.pop("resolved", None)
    prepared = prepare_for_render(clean)
    resolved = prepared.get("resolved") or {}
    export = prepared.get("export") or {}
    width = resolved.get("width", export.get("width", 1080))
    height = resolved.get("height", export.get("height", 1920))
    fps = resolved.get("fps", export.get("fps", 30))
    if (any(type(n) is not int for n in (width, height, fps))
            or not 16 <= width <= 3840 or not 16 <= height <= 3840
            or width * height > 8_294_400 or not 1 <= fps <= 60):
        raise ValueError("Frame review requires dimensions 16..3840 (max 8.3MP), fps 1..60.")
    total = resolved.get("total_frames")
    if total is None and clean.get("version") != schema.SCHEMA_VERSION_V2:
        duration = prepared.get("timing", {}).get("duration")
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 120:
            raise ValueError("Frame review requires a finite duration of at most 120 seconds.")
        total = max(1, round(duration * fps))
    if type(total) is not int or not 1 <= total <= 120 * fps:
        raise ValueError("Resolved duration must be 1 frame to 120 seconds for frame review.")
    if any(frame < 0 or frame >= total for frame in frames):
        raise ValueError(f"Frame numbers must be within the resolved duration: 0..{total - 1}.")
    composition = composition_id_of(prepared)
    node, cli = node_command(), remotion_cli()
    # No upscaling; tall compositions are bounded too. Floor avoids >540 rounding.
    scale = math.floor(min(1.0, 540 / width, 1024 / height) * 1_000_000) / 1_000_000
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"frame-{frame}.png" for frame in frames]
    if any(path.exists() for path in paths):
        raise ValueError("Frame output files already exist; use an empty temporary directory.")
    if audit_layout and composition != "quote-cinematic":
        raise ValueError("La sonde DOM est disponible pour quote_cinematic uniquement.")
    props_path = mediacache.write_props(prepared, f"{job.id}-frames-{uuid.uuid4().hex[:8]}")
    succeeded = False
    try:
        commands = [(frames, props_path, out_dir)] if audit_layout else [
            ([frame], props_path, out_dir) for frame in frames
        ]
        for index, (batch, props, destination) in enumerate(commands):
            if job.cancel_event.is_set():
                raise JobCancelled()
            cmd = ([str(node), str(WEB_DIR / "audit-layout.mjs"), str(props), composition,
                    str(destination), json.dumps(batch), f"{scale:.6f}"] if audit_layout else [
                str(node), str(cli), "still", ENTRY, composition, str(paths[index]),
                f"--frame={batch[0]}", f"--props={props}", f"--scale={scale:.6f}",
                "--image-format=png", "--log=error",
            ])
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(WEB_DIR), env=_env(), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                    shell=False,
                )
            except OSError as exc:
                raise RuntimeError(f"Unable to start Remotion: {_frame_log(str(exc))}") from None
            job.result_process = proc
            try:
                output = _communicate_frame(job, proc, batch[0])
            finally:
                job.result_process = None
            if proc.returncode != 0:
                raise RuntimeError(f"Remotion frames {batch} failed (code {proc.returncode}):\n{_frame_log(output)}")
            for frame, path in zip(batch, paths):
                if not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError(f"Remotion frame {frame} produced no image.\n{_frame_log(output)}")
            job.set_progress(index + 1, len(commands), f"Frames {batch}")
        succeeded = True
        return paths
    finally:
        props_path.unlink(missing_ok=True)
        if not succeeded:
            for path in paths:
                path.unlink(missing_ok=True)


def render_props_preview(project: dict) -> dict:
    """Props telles que les verrait le Player (pour inspection dans l'UI)."""
    return json.loads(json.dumps(prepare_for_render(project)))
