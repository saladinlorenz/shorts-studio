"""Rendu réel d'un montage footage : EDL -> FFmpeg -> MP4, via l'API.

Les rushes sont synthétiques (lavfi), les dossiers media/ et exports/ sont
temporaires : le test ne touche ni à la médiathèque ni aux exports du projet.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.app import app  # noqa: E402
from server.api import montage as montage_api  # noqa: E402
from shortvideos.probe import probe_mp4  # noqa: E402
from shortvideos.timeline import TimelineCancelled, TimelineError  # noqa: E402

client = TestClient(app)
FF = imageio_ffmpeg.get_ffmpeg_exe()


def _make_video(path: Path, source: str, seconds: float, audio: bool) -> None:
    args = [FF, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"{source}=size=160x90:rate=30:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i",
                 f"sine=frequency=440:sample_rate=48000:duration={seconds}",
                 "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-t", str(seconds), str(path)]
    subprocess.run(args, check=True)


def _make_music(path: Path, seconds: float) -> None:
    subprocess.run(
        [FF, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={seconds}",
         "-c:a", "aac", "-b:a", "128k", str(path)],
        check=True,
    )


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    media = tmp_path / "media"
    exports = tmp_path / "exports"
    for path in (media, media / "provenance", exports):
        path.mkdir(parents=True, exist_ok=True)
    _make_video(media / "a.mp4", "testsrc2", 2.2, audio=True)
    _make_video(media / "b.mp4", "smptebars", 2.0, audio=False)
    _make_music(media / "music.m4a", 1.2)

    monkeypatch.setattr("server.media.MEDIA_DIR", media)
    monkeypatch.setattr("server.media.PROVENANCE_DIR", media / "provenance")
    monkeypatch.setattr(montage_api, "EXPORTS_DIR", exports)
    monkeypatch.setattr(montage_api, "assert_local_dir", lambda path: Path(path))
    return {"tmp": tmp_path, "media": media, "exports": exports}


def _edl() -> dict:
    return {
        "version": 1,
        "canvas": {"width": 160, "height": 90, "fps": 15},
        "cuts": [
            {"media": "media://a", "in": 0.1, "out": 1.4, "role": "hook",
             "reason": "ouverture"},
            {"media": "media://b", "in": 0.1, "out": 1.5, "role": "end",
             "reason": "chute", "transition": {"type": "fade", "duration": 0.3}},
        ],
        "audio": {"music": "media://music", "gain_db": -20, "duck": True,
                  "fade_in": 0.2, "fade_out": 0.3},
        "grade": {"look": "warm", "saturation": 1.1, "contrast": 1.05},
    }


def _wait(job_id: str, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = client.get(f"/api/montage/{job_id}").json()
        if snapshot["status"] != "running":
            return snapshot
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} toujours en cours apres {timeout} s")


def test_validate_route_accepts_a_real_plan(studio):
    response = client.post("/api/montage/validate", json={"edl": _edl()})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True, body["errors"]
    assert body["cuts"] == 2
    assert body["duration_seconds"] == pytest.approx(2.4, abs=1e-6)


def test_validate_route_indexes_missing_and_remote_sources(studio):
    edl = _edl()
    edl["cuts"][0]["media"] = "media://absent"
    edl["cuts"][1]["media"] = "https://exemple.test/clip.mp4"
    body = client.post("/api/montage/validate", json={"edl": edl}).json()
    assert body["valid"] is False
    joined = " | ".join(body["errors"])
    assert "cuts[0].media" in joined and "introuvable" in joined
    assert "cuts[1].media" in joined and "media://<id>" in joined


def test_render_produces_a_verified_mp4(studio):
    response = client.post(
        "/api/montage", json={"name": "essai montage", "edl": _edl()}
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    snapshot = _wait(job_id)
    assert snapshot["status"] == "done", snapshot
    result = snapshot["result"]
    assert result["cuts"] == 2
    assert result["music"] is True
    assert result["grade"] == "warm"
    assert result["planned_duration"] == pytest.approx(2.4, abs=0.05)
    assert abs(result["duration"] - 2.4) <= 0.45, result
    assert result["has_audio"] is True

    out = studio["exports"] / "essai montage.mp4"
    assert out.is_file() and out.stat().st_size > 0
    info = probe_mp4(str(out))
    assert (info["width"], info["height"]) == (160, 90)
    assert info["fps"] == pytest.approx(15.0, abs=0.2)
    assert list(studio["exports"].glob("*.part.mp4")) == []

    served = client.get(f"/api/montage/{job_id}/file")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("video/mp4")


def test_existing_output_needs_overwrite(studio):
    response = client.post("/api/montage", json={"name": "deja-la", "edl": _edl()})
    job_id = response.json()["job_id"]
    assert _wait(job_id)["status"] == "done"
    again = client.post("/api/montage", json={"name": "deja-la", "edl": _edl()})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "exists"


def test_render_error_keeps_no_part_file(studio, monkeypatch):
    def failing(job, edl, out_path, **_kwargs):
        Path(out_path).write_bytes(b"partiel")
        raise TimelineError("ffmpeg simule en echec")

    monkeypatch.setattr(montage_api, "render_timeline", failing)
    job_id = client.post("/api/montage", json={"name": "echec", "edl": _edl()}).json()["job_id"]
    snapshot = _wait(job_id)
    assert snapshot["status"] == "error"
    assert "ffmpeg simule en echec" in snapshot["error"]
    assert not (studio["exports"] / "echec.mp4").exists()
    assert list(studio["exports"].glob("*.part.mp4")) == []


def test_cancel_is_translated_to_cancelled_status(studio, monkeypatch):
    def blocking(job, edl, out_path, **_kwargs):
        while not job.cancel_event.is_set():
            time.sleep(0.05)
        Path(out_path).write_bytes(b"partiel")
        raise TimelineCancelled()

    monkeypatch.setattr(montage_api, "render_timeline", blocking)
    job_id = client.post("/api/montage", json={"name": "annule", "edl": _edl()}).json()["job_id"]
    assert client.post(f"/api/montage/{job_id}/cancel").status_code == 200
    snapshot = _wait(job_id)
    assert snapshot["status"] == "cancelled"
    assert not (studio["exports"] / "annule.mp4").exists()
    assert list(studio["exports"].glob("*.part.mp4")) == []
