"""Test d'export court + verification reelle du MP4 produit.

Sans ffprobe (absent de l'environnement) : la verification utilise
OpenCV (ouverture reelle, dimensions, FPS, frames) et la comparaison
frame par frame entre l'apercu (compose_frame) et le MP4 decode.
Le test est declare reussi uniquement si ces controles passent.
"""
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from shortvideos import project as project_mod
from shortvideos import render, timing, validation
from shortvideos.exporter import ExportCancelled, ExportError, export_video
from shortvideos.probe import probe_mp4

# Petit format pour que le test reste rapide (~2 s de video).
TEST_WIDTH, TEST_HEIGHT, TEST_FPS = 270, 480, 15


def build_project(tmp_path: Path) -> dict:
    media_dir = tmp_path / "medias d'essai"
    media_dir.mkdir(parents=True, exist_ok=True)

    bg_path = media_dir / "fond de test.png"
    img = Image.new("RGB", (640, 1138), (30, 60, 120))
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 200, 540, 900], fill=(200, 80, 40))
    img.save(bg_path)

    logo_path = media_dir / "le logo.png"
    logo = Image.new("RGBA", (120, 120), (255, 255, 0, 200))
    logo.save(logo_path)

    proj = project_mod.default_project()
    proj["content"]["text"] = "Le courage est le premier des vertus."
    proj["content"]["author"] = "Auteur Test"
    proj["content"]["background_image"] = str(bg_path)
    proj["content"]["logo"] = str(logo_path)
    proj["timing"] = {"duration": 2.0, "text_start": 0.2, "fade_in": 0.5, "fade_out": 0.5}
    proj["export"] = {
        "width": TEST_WIDTH, "height": TEST_HEIGHT, "fps": TEST_FPS, "output_dir": ""
    }
    return proj


def test_export_short_and_verified(tmp_path, capsys):
    """Exporte 2 s et verifie reellement le fichier produit."""
    proj = build_project(tmp_path)
    errors, warnings = validation.validate_project(proj)
    assert errors == [], errors

    out = tmp_path / "sorties" / "video de test.mp4"  # espaces dans le chemin

    progress_calls = []

    def on_progress(current, total):
        progress_calls.append((current, total))

    started = time.perf_counter()
    result = export_video(proj, out, progress_cb=on_progress)
    elapsed = time.perf_counter() - started

    # --- Le fichier existe et n'est pas vide ---
    assert out.exists()
    assert result["size_bytes"] > 0

    # --- Verification reelle par decodage (OpenCV) ---
    info = probe_mp4(str(out))
    assert info["width"] == TEST_WIDTH, info
    assert info["height"] == TEST_HEIGHT, info
    assert info["frames"] == int(2.0 * TEST_FPS), info
    assert abs(info["duration"] - 2.0) <= 0.25, info

    # --- La progression a bien ete appelee, de facon croissante ---
    assert progress_calls, "le callback de progression n'a pas ete appele"
    currents = [c for c, _t in progress_calls]
    assert currents == sorted(currents)
    assert currents[-1] == int(2.0 * TEST_FPS)

    # --- Comparaison apercu (compose_frame) vs frames decodees du MP4 ---
    cap = cv2.VideoCapture(str(out))
    assert cap.isOpened()
    max_mean_diff = 0.0
    for t in (0.35, 1.0, 1.8):  # instants choisis : fondu, plein, sortie
        idx = int(round(t * TEST_FPS))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame_bgr = cap.read()
        assert ok, f"frame {idx} illisible"
        decoded = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        expected = np.asarray(render.compose_frame(proj, idx / TEST_FPS), dtype=np.int16)
        diff = np.abs(decoded.astype(np.int16) - expected)
        max_mean_diff = max(max_mean_diff, float(diff.mean()))
    cap.release()

    # La compression H.264 est lossy : on accepte une petite difference moyenne,
    # mais une divergence apercu/export depasserait largement ce seuil.
    assert max_mean_diff < 12.0, (
        f"Divergence apercu/export : difference moyenne {max_mean_diff:.2f}/255"
    )

    with capsys.disabled():
        print(f"\n[mesure] export 2.0 s de video ({TEST_WIDTH}x{TEST_HEIGHT}@{TEST_FPS}fps, "
              f"{result['frames']} frames) en {elapsed:.2f} s reelles "
              f"(rapport {2.0 / elapsed:.1f}x), fichier {result['size_bytes']} octets, "
              f"ecart apercu/export moyen max {max_mean_diff:.2f}/255.")


def test_export_refuses_existing_file(tmp_path):
    proj = build_project(tmp_path)
    out = tmp_path / "existant.mp4"
    export_video(proj, out)  # premier export : OK
    with pytest.raises(ExportError, match="existe deja"):
        export_video(proj, out, overwrite=False)


def test_export_overwrite_with_confirmation(tmp_path):
    proj = build_project(tmp_path)
    out = tmp_path / "a ecraser.mp4"
    export_video(proj, out)
    size_before = out.stat().st_size
    time.sleep(0.05)
    result = export_video(proj, out, overwrite=True)
    assert Path(result["path"]).exists()
    assert out.stat().st_size > 0
    assert size_before > 0


def test_export_cancel_cleans_up(tmp_path):
    proj = build_project(tmp_path)
    out = tmp_path / "annule.mp4"
    cancel = threading.Event()

    def on_progress(current, _total):
        if current >= 3:
            cancel.set()

    with pytest.raises(ExportCancelled):
        export_video(proj, out, progress_cb=on_progress, cancel_event=cancel)
    assert not out.exists(), "l'annulation ne doit pas laisser de fichier final"
    leftovers = list(tmp_path.glob("*.part.mp4"))
    assert leftovers == [], f"fichiers temporaires non nettoyes : {leftovers}"


def test_export_missing_file_blocks_before_start(tmp_path):
    proj = build_project(tmp_path)
    proj["content"]["background_image"] = str(tmp_path / "fond absent.png")
    out = tmp_path / "jamais.mp4"
    with pytest.raises(ExportError, match="invalide"):
        export_video(proj, out)
    assert not out.exists()
    assert list(tmp_path.glob("*.part.mp4")) == []


def test_no_part_file_left_after_success(tmp_path):
    proj = build_project(tmp_path)
    out = tmp_path / "propre.mp4"
    export_video(proj, out)
    assert list(tmp_path.glob("*.part.mp4")) == []


def test_compose_frame_deterministic(tmp_path):
    """La meme fonction de composition produit la meme image pour le meme instant."""
    proj = build_project(tmp_path)
    a = np.asarray(render.compose_frame(proj, 1.0))
    b = np.asarray(render.compose_frame(proj, 1.0))
    assert np.array_equal(a, b)


def test_preview_matches_export_dimensions(tmp_path):
    proj = build_project(tmp_path)
    frame = render.compose_frame(proj, 1.0)
    assert frame.size == (TEST_WIDTH, TEST_HEIGHT)
    assert timing.frame_count(proj) == int(2.0 * TEST_FPS)
