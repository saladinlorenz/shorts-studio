"""G1 — loudness pro post-rendu + detection de piste audio.

Verification reelle : un petit MP4 (video + son) est produit par ffmpeg,
normalise, puis re-ouvert. Aucun serveur ni rendu Remotion ici : on teste la
passe audio de ``server.render`` et le helper ``probe.has_audio_stream``.
Les cas limites (annulation, chaine de filtres) sont couverts sans ffmpeg.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from server import render as render_mod
from server.jobs import Job, JobCancelled
from shortvideos import probe as probe_mod
from shortvideos.probe import has_audio_stream, probe_mp4


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _make_clip(path: Path, *, audio: bool) -> None:
    """1 s de video 64x64, avec ou sans piste son (sine 440 Hz)."""
    cmd = [
        _ffmpeg(), "-hide_banner", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1:r=10",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def test_has_audio_stream_detects_audio_and_silence(tmp_path):
    with_audio = tmp_path / "son.mp4"
    video_only = tmp_path / "muet.mp4"
    _make_clip(with_audio, audio=True)
    _make_clip(video_only, audio=False)
    assert has_audio_stream(str(with_audio)) is True
    assert has_audio_stream(str(video_only)) is False


def test_normalize_loudness_applies_and_preserves_video(tmp_path):
    out = tmp_path / "master.mp4"
    _make_clip(out, audio=True)
    before = probe_mp4(str(out))

    job = Job("test")
    assert render_mod._normalize_loudness(job, out) is True

    after = probe_mp4(str(out))
    # La video est copiee : memes dimensions, memes frames, duree conservee.
    assert after["width"] == before["width"] == 64
    assert after["height"] == before["height"] == 64
    assert after["frames"] == before["frames"]
    assert abs(after["duration"] - 1.0) <= 0.25
    assert has_audio_stream(str(out)) is True
    # Aucun temporaire residue, et le job ne pointe plus sur un processus.
    assert list(tmp_path.glob("*.loudnorm.mp4")) == []
    assert job.result_process is None


def test_normalize_loudness_skips_video_only(tmp_path):
    out = tmp_path / "muet.mp4"
    _make_clip(out, audio=False)
    original = out.read_bytes()

    job = Job("test")
    assert render_mod._normalize_loudness(job, out) is False
    # Fichier intact : pas de son, donc pas de passe loudness.
    assert out.read_bytes() == original
    assert list(tmp_path.glob("*.loudnorm.mp4")) == []


class _RecordingProc:
    """Faux subprocess.Popen : capture la commande et simule un succes."""

    captured: dict = {}

    def __init__(self, cmd, **kwargs):
        _RecordingProc.captured["cmd"] = cmd
        self.returncode = 0
        self._temp = Path(cmd[-1])

    def communicate(self, timeout=None):
        self._temp.write_bytes(b"normalized")
        return ("", "")

    def poll(self):
        return 0


def test_normalize_loudness_command_uses_loudnorm_and_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_mod, "has_audio_stream", lambda path: True)
    monkeypatch.setattr(render_mod.subprocess, "Popen", _RecordingProc)
    _RecordingProc.captured = {}

    out = tmp_path / "v.mp4"
    out.write_bytes(b"original")
    job = Job("test")
    assert render_mod._normalize_loudness(job, out) is True

    cmd = _RecordingProc.captured["cmd"]
    af = cmd[cmd.index("-af") + 1]
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in af
    assert "aresample=48000" in af
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    # Le rendu original a ete remplace atomiquement par la version normalisee.
    assert out.read_bytes() == b"normalized"
    assert list(tmp_path.glob("*.loudnorm.mp4")) == []


def test_normalize_loudness_cancel_raises_and_cleans(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_mod, "has_audio_stream", lambda path: True)
    monkeypatch.setattr(render_mod.subprocess, "Popen", _RecordingProc)

    out = tmp_path / "v.mp4"
    out.write_bytes(b"original")
    job = Job("test")
    job.cancel_event.set()
    with pytest.raises(JobCancelled):
        render_mod._normalize_loudness(job, out)
    # L'original est preserve et aucun temporaire ne subsiste.
    assert out.read_bytes() == b"original"
    assert list(tmp_path.glob("*.loudnorm.mp4")) == []
    assert job.result_process is None


def test_normalize_loudness_failure_keeps_original(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_mod, "has_audio_stream", lambda path: True)

    class _FailingProc(_RecordingProc):
        def __init__(self, cmd, **kwargs):
            super().__init__(cmd, **kwargs)
            self.returncode = 1

        def communicate(self, timeout=None):
            return ("", "")

    monkeypatch.setattr(render_mod.subprocess, "Popen", _FailingProc)
    out = tmp_path / "v.mp4"
    out.write_bytes(b"original")
    job = Job("test")
    assert render_mod._normalize_loudness(job, out) is False
    assert out.read_bytes() == b"original"
    assert list(tmp_path.glob("*.loudnorm.mp4")) == []