"""Verification des MP4 produits, SANS ffprobe.

Constat de l'environnement : imageio-ffmpeg fournit uniquement l'executable
``ffmpeg`` (pas de ``ffprobe``), et ffprobe n'est pas present dans le PATH.
On verifie donc les fichiers ainsi :

1. OpenCV (cv2.VideoCapture) : ouvre le MP4, lit la premiere frame,
   relit les dimensions, le FPS et le nombre de reels.
2. ``ffmpeg -i`` (parse de la sortie stderr) : duree et codecs, en secours.

Pour installer ffprobe si vous le souhaitez (verification supplementaire,
pas obligatoire) : ``winget install Gyan.FFmpeg`` puis redemarrer le
terminal (ffprobe sera alors dans le PATH).
"""
from __future__ import annotations

import re
import shutil
import subprocess

import cv2
import imageio_ffmpeg


class ProbeError(RuntimeError):
    """Le fichier MP4 n'a pas pu etre ouvert ou est invalide."""


def probe_mp4(path: str) -> dict:
    """Ouvre un MP4 avec OpenCV et en retourne les caracteristiques reelles."""
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise ProbeError(
                f"Impossible d'ouvrir le MP4 : {path}\n"
                "Le fichier est absent, vide ou corrompu."
            )
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ProbeError(f"Le MP4 ne contient aucune frame lisible : {path}")
        return {
            "path": path,
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "frames": frames,
            "duration": round(frames / fps, 3) if fps else 0.0,
            "first_frame_shape": frame.shape,
        }
    finally:
        cap.release()


def duration_ffmpeg(path: str) -> float | None:
    """Duree via 'ffmpeg -i' (secours si ffprobe absent). None si inconnu."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr or "")
    if not match:
        return None
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def has_ffprobe() -> bool:
    """True si ffprobe est disponible (verifie avant de s'en servir)."""
    return shutil.which("ffprobe") is not None
