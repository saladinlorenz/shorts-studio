"""Export MP4 via ffmpeg (imageio-ffmpeg), sans bloquer l'interface.

Principes :
- le projet est fige (copie profonde) au debut de l'export ;
- aucun acces aux widgets Tkinter depuis ce module : la progression est
  remontee par un callback appele depuis le thread d'export, c'est a
  l'appelant (tab.py) de la basculer sur le thread principal ;
- annulation possible via un objet threading.Event ;
- en cas d'erreur ou d'annulation, le processus ffmpeg est tue et les
  fichiers temporaires/sortie partiels sont supprimes ;
- un fichier existant n'est jamais ecrase sans confirmation (overwrite=True).

Le flux video est envoye a ffmpeg en rawvideo RGB24 par pipe, ce qui evite
d'ecrire des milliers de fichiers temporaires sur le disque.
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import imageio_ffmpeg

from . import render, timing
from .project import snapshot
from .validation import validate_project


class ExportError(RuntimeError):
    """Erreur d'export avec message clair pour l'utilisateur."""


class ExportCancelled(Exception):
    """ levee quand l'utilisateur annule l'export."""


def export_video(
    project: dict,
    output_path: str | Path,
    progress_cb=None,
    cancel_event: threading.Event | None = None,
    overwrite: bool = False,
) -> dict:
    """Exporte le projet en MP4. Bloquant : a appeler dans un thread.

    progress_cb : callable(current:int, total:int), appele depuis ce thread.
    cancel_event : si set pendant le rendu, l'export est annule proprement.

    Retourne un dict avec le chemin, la duree, les dimensions et le
    temps d'export mesure.
    """
    # 1. Figer une copie des reglages (l'UI peut changer pendant le rendu).
    proj = snapshot(project)

    # 2. Validation bloquante avant tout lancement.
    errors, _warnings = validate_project(proj)
    if errors:
        raise ExportError("Projet invalide :\n- " + "\n- ".join(errors))

    out = Path(output_path)
    if out.exists() and not overwrite:
        raise ExportError(
            f"Le fichier existe deja : {out}\n"
            "Cochez 'Ecraser le fichier existant' pour le remplacer."
        )
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)

    width = int(proj["export"]["width"])
    height = int(proj["export"]["height"])
    fps = int(proj["export"]["fps"])
    total = timing.frame_count(proj)
    duration = timing.duration(proj)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Fichier temporaire : on n'ecrase la destination qu'en fin de rendu reussi.
    tmp = out.with_name(out.stem + ".part.mp4")
    if tmp.exists():
        tmp.unlink()

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
        "-framerate", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(tmp),
    ]

    started = time.perf_counter()
    proc: subprocess.Popen | None = None
    success = False
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None
        frame_bytes = width * height * 3
        for i in range(total):
            if cancel_event is not None and cancel_event.is_set():
                raise ExportCancelled("Export annule par l'utilisateur.")
            frame = render.compose_frame(proj, timing.frame_time(i, proj))
            proc.stdin.write(frame.tobytes())
            if progress_cb is not None:
                progress_cb(i + 1, total)
        proc.stdin.close()
        proc.stdin = None
        stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        returncode = proc.wait(timeout=120)
        if returncode != 0:
            raise ExportError(f"ffmpeg a echoue (code {returncode}) :\n{stderr.strip() or 'pas de detail'}")
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise ExportError("ffmpeg n'a produit aucun fichier (sortie vide).")
        # Rendu reussi : deplacement atomique vers la destination.
        if out.exists():
            out.unlink()
        tmp.replace(out)
        success = True
        elapsed = time.perf_counter() - started
        return {
            "path": str(out),
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
            "frames": total,
            "export_seconds": round(elapsed, 2),
            "size_bytes": out.stat().st_size,
        }
    except ExportCancelled:
        raise
    except ExportError:
        raise
    except BrokenPipeError as e:
        stderr = ""
        if proc is not None and proc.stderr is not None:
            try:
                proc.stdin and proc.stdin.close()
            except OSError:
                pass
            stderr = proc.stderr.read().decode("utf-8", "replace")
        raise ExportError(
            f"ffmpeg s'est arrete prematurument.\n{stderr.strip() or e}"
        ) from e
    except Exception as e:  # noqa: BLE001 - toute erreur est remontee a l'utilisateur
        raise ExportError(f"Echec de l'export : {e}") from e
    finally:
        # Nettoyage garanti : processus tue, tampon ferme, fichier temporaire supprime
        # si le rendu n'a pas reussi.
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except OSError:
                pass
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            try:
                if proc.stderr:
                    proc.stderr.close()
            except OSError:
                pass
        if not success and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
