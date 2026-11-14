"""G3 — livraison multi-formats : derives 1:1 et 16:9 du master 9:16.

Verification reelle : un master 9:16 (video + son) est produit par ffmpeg,
recadre au centre, puis re-ouvert. Le master n'est jamais modifie ; l'audio
normalise est conserve ; l'annulation ne laisse aucun provisoire.
"""
from __future__ import annotations

import subprocess

import imageio_ffmpeg
import pytest

from server.jobs import JobCancelled
from shortvideos import delivery
from shortvideos.probe import has_audio_stream, probe_mp4


def _make_master(path, *, audio=True):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=270x480:d=1:r=10",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def test_derive_social_formats_produces_both_ratios(tmp_path):
    master = tmp_path / "master.mp4"
    _make_master(master)
    before = master.read_bytes()

    made = delivery.derive_social_formats(master, tmp_path, "master", cancel=lambda: None)
    assert {f["ratio"] for f in made} == {"1:1", "16:9"}
    dims = {f["ratio"]: (f["width"], f["height"]) for f in made}
    assert dims["1:1"] == (1080, 1080)
    assert dims["16:9"] == (1920, 1080)
    for fmt in made:
        info = probe_mp4(fmt["path"])
        assert (info["width"], info["height"]) == (fmt["width"], fmt["height"])
        assert has_audio_stream(fmt["path"]) is True  # audio du master conserve
    assert master.read_bytes() == before, "le master n'est pas modifie"
    assert list(tmp_path.glob("*.part.mp4")) == []


def test_derive_social_formats_cancel_cleans_up(tmp_path):
    master = tmp_path / "master.mp4"
    _make_master(master)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        if calls["n"] >= 2:  # annulation apres le premier recadrage
            raise JobCancelled()

    with pytest.raises(JobCancelled):
        delivery.derive_social_formats(master, tmp_path, "master", cancel=cancel)
    assert list(tmp_path.glob("*.part.mp4")) == []
    assert list(tmp_path.glob("master-*.mp4")) == []


def test_derive_social_formats_non_video_returns_empty(tmp_path):
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not a video")
    assert delivery.derive_social_formats(fake, tmp_path, "fake") == []
    assert list(tmp_path.glob("*.part.mp4")) == []