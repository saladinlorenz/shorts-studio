"""Génération d'images Pollinations : téléchargement borné + import média.

Aucun réseau réel : httpx est simulé. L'import média est le code de production,
isolé dans tmp_path (MEDIA_DIR, provenance, cache neutralisés).
"""
from __future__ import annotations

import io
import json
import types

import pytest
from PIL import Image

from server import imagegen, media as media_mod, mediacache
from server.jobs import JobCancelled


def _jpeg_bytes(color="red", size=(8, 8)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


JPEG = _jpeg_bytes()
URL = "https://image.pollinations.ai/prompt/test"


class _FakeTimeout(Exception):
    pass


class _FakeHTTPError(Exception):
    pass


@pytest.fixture()
def media_tmp(monkeypatch, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    monkeypatch.setattr(media_mod, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(media_mod, "PROVENANCE_DIR", media_dir / "provenance")
    monkeypatch.setattr(mediacache, "ensure_cached", lambda media_id: None)
    return media_dir


def _install_httpx(monkeypatch, *, status=200, ctype="image/jpeg", chunks=None, exc=None):
    chunks = [JPEG] if chunks is None else chunks

    class Resp:
        status_code = status
        headers = {"content-type": ctype}

        def iter_bytes(self, n):
            yield from chunks

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, *a, **k):
            if exc is not None:
                raise exc
            return Resp()

    monkeypatch.setattr(imagegen, "httpx", types.SimpleNamespace(
        Client=Client, Timeout=lambda *a, **k: None,
        TimeoutException=_FakeTimeout, HTTPError=_FakeHTTPError,
    ))


# --------------------------------------------------------------------------- #
# URL construite côté serveur (hôte whitelisté, prompt encodé)
# --------------------------------------------------------------------------- #

def test_url_is_built_server_side_with_whitelisted_host():
    url = imagegen._url("a/b?c", 512, 768, 7)
    assert url.startswith("https://image.pollinations.ai/prompt/")
    assert "a%2Fb%3Fc" in url, "le prompt est encodé, aucune injection de chemin"
    assert "width=512" in url and "height=768" in url
    assert "seed=7" in url and "nologo=true" in url
    assert "seed=" not in imagegen._url("x", 64, 64, None)


# --------------------------------------------------------------------------- #
# Téléchargement borné
# --------------------------------------------------------------------------- #

def test_download_writes_jpeg_atomically(media_tmp, monkeypatch):
    _install_httpx(monkeypatch)
    dest = media_tmp / "out.jpg"
    imagegen._download(URL, dest)
    assert dest.read_bytes() == JPEG
    assert not (media_tmp / "out.jpg.part").exists()


def test_download_rejects_non_jpeg_content_type(media_tmp, monkeypatch):
    _install_httpx(monkeypatch, ctype="text/html")
    dest = media_tmp / "out.jpg"
    with pytest.raises(imagegen.ImageGenError, match="inattendue"):
        imagegen._download(URL, dest)
    assert not dest.exists() and not (media_tmp / "out.jpg.part").exists()


def test_download_rejects_bad_magic_bytes(media_tmp, monkeypatch):
    _install_httpx(monkeypatch, chunks=[b"ceci n'est pas un jpeg"])
    dest = media_tmp / "out.jpg"
    with pytest.raises(imagegen.ImageGenError, match="JPEG"):
        imagegen._download(URL, dest)
    assert not dest.exists() and not (media_tmp / "out.jpg.part").exists()


def test_download_enforces_size_cap(media_tmp, monkeypatch):
    _install_httpx(monkeypatch, chunks=[JPEG + b"\x00" * (imagegen._MAX_BYTES + 16)])
    dest = media_tmp / "out.jpg"
    with pytest.raises(imagegen.ImageGenError, match="volumineuse"):
        imagegen._download(URL, dest)
    assert not dest.exists() and not (media_tmp / "out.jpg.part").exists()


def test_download_rejects_http_error_status(media_tmp, monkeypatch):
    _install_httpx(monkeypatch, status=503)
    with pytest.raises(imagegen.ImageGenError, match="503"):
        imagegen._download(URL, media_tmp / "out.jpg")


def test_download_timeout_is_wrapped(media_tmp, monkeypatch):
    _install_httpx(monkeypatch, exc=_FakeTimeout("boom"))
    with pytest.raises(imagegen.ImageGenError, match="Délai"):
        imagegen._download(URL, media_tmp / "out.jpg")


def test_download_unreachable_is_wrapped(media_tmp, monkeypatch):
    _install_httpx(monkeypatch, exc=_FakeHTTPError("boom"))
    with pytest.raises(imagegen.ImageGenError, match="injoignable"):
        imagegen._download(URL, media_tmp / "out.jpg")


def test_download_cancel_interrupts_and_cleans(media_tmp, monkeypatch):
    _install_httpx(monkeypatch, chunks=[JPEG, JPEG])
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        if calls["n"] >= 2:
            raise JobCancelled()

    dest = media_tmp / "out.jpg"
    with pytest.raises(JobCancelled):
        imagegen._download(URL, dest, cancel=cancel)
    assert not dest.exists() and not (media_tmp / "out.jpg.part").exists()


# --------------------------------------------------------------------------- #
# Génération → import média (contrat de retour)
# --------------------------------------------------------------------------- #

def test_generate_image_imports_media_and_returns_ref(media_tmp, monkeypatch):
    def fake_download(url, dest, *, cancel=None):
        assert url.startswith("https://image.pollinations.ai/prompt/")
        dest.write_bytes(JPEG)

    monkeypatch.setattr(imagegen, "_download", fake_download)
    result = imagegen.generate_image("un coucher de soleil sur la mer", width=512, height=768)
    assert result["ref"] == f"media://{result['media_id']}"
    assert result["url"] == f"/api/media/{result['media_id']}"
    assert result["width"] == 512 and result["height"] == 768
    files = list(media_tmp.glob(f"{result['media_id']}.*"))
    assert len(files) == 1 and files[0].suffix == ".jpg"
    assert files[0].read_bytes() == JPEG
    prov = json.loads((media_tmp / "provenance" / f"{result['media_id']}.json").read_text(encoding="utf-8"))
    assert "Pollinations" in prov["source"]
    assert prov["content_type"] == "image/jpeg"


def test_generate_image_empty_prompt_raises(media_tmp):
    with pytest.raises(imagegen.ImageGenError):
        imagegen.generate_image("   ")


def test_generate_image_failure_imports_nothing(media_tmp, monkeypatch):
    def boom(url, dest, *, cancel=None):
        raise imagegen.ImageGenError("service indisponible")

    monkeypatch.setattr(imagegen, "_download", boom)
    with pytest.raises(imagegen.ImageGenError):
        imagegen.generate_image("une image")
    assert list(media_tmp.glob("*.jpg")) == []