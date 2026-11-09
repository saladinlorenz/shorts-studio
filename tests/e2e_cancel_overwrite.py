"""Vérifications serveur : annulation d'export, refus d'écrasement, timing à chaud."""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
EXPORTS = Path(r"E:\youtube\youtube_clipper\exports")


def call(method, path, data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, {"detail": text}


def multipart(path, filename, payload, content_type):
    boundary = "----bndxyz"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + path, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def build_project(bg_id, duration=4.0):
    return {
        "version": 1, "template": "quote_vertical",
        "content": {
            "text": "La persévérance est la force des faibles.",
            "author": "Victor Hugo",
            "background_image": f"media://{bg_id}", "logo": "",
        },
        "theme": {"font_family": "arialbd.ttf", "font_size": 80,
                  "text_color": "#FFFFFF", "author_color": "#F2C14E",
                  "accent_color": "#F2C14E", "shadow": True},
        "position": {"x": 0.5, "y": 0.5, "width": 0.85},
        "timing": {"duration": duration, "text_start": 0.3, "fade_in": 0.6, "fade_out": 0.6},
        "animation": {"text_in": "fade", "background": "zoom_slow"},
        "export": {"width": 1080, "height": 1920, "fps": 30, "output_dir": ""},
    }


def wait_job(job_id, timeout=600, poll=0.4):
    t0 = time.time()
    while True:
        time.sleep(poll)
        code, snap = call("GET", f"/api/exports/{job_id}")
        if code != 200:
            return {"status": "http_error", "code": code, "body": snap}
        if snap["status"] != "running":
            snap["_elapsed"] = time.time() - t0
            return snap
        if time.time() - t0 > timeout:
            call("POST", f"/api/exports/{job_id}/cancel")
            return {"status": "timeout"}


def main():
    # Fond réel
    from PIL import Image, ImageDraw
    d = Path(r"E:\youtube\youtube_clipper\.pytest_tmp\e2e")
    d.mkdir(parents=True, exist_ok=True)
    bg = d / "fond annulation.png"
    img = Image.new("RGB", (1080, 1920), (30, 24, 48))
    ImageDraw.Draw(img).rectangle([0, 900, 1080, 1020], fill=(200, 120, 60))
    img.save(bg)
    up = multipart("/api/media/upload", "fond annulation.png", bg.read_bytes(), "image/png")
    project = build_project(up["id"])

    # ---- 1. Annulation en cours de rendu ----
    print("[1] annulation en cours de rendu…")
    code, res = call("POST", "/api/exports", {"name": "a_annuler", "project": project, "overwrite": True})
    assert code == 200, res
    job_id = res["job_id"]
    time.sleep(3.0)  # laisser le rendu démarrer
    code, snap = call("GET", f"/api/exports/{job_id}")
    print(f"    avant annulation: {snap['status']} {snap['progress']*100:.0f}%")
    assert snap["status"] == "running", snap
    code, snap = call("POST", f"/api/exports/{job_id}/cancel")
    print("    demande d'annulation envoyée")
    final = wait_job(job_id, timeout=60)
    print(f"    statut final: {final['status']} ({final.get('_elapsed', 0):.1f}s)")
    assert final["status"] == "cancelled", final
    leftovers = list(EXPORTS.glob("*.part.mp4")) + list(EXPORTS.glob("a_annuler*"))
    print("    fichiers restants:", leftovers or "aucun (nettoyage OK)")
    assert leftovers == [], leftovers

    # ---- 2. Refus d'écrasement (409) puis remplacement confirmé ----
    print("[2] refus d'écrasement…")
    # D'abord créer le fichier par un export réussi
    code, res = call("POST", "/api/exports", {"name": "a_annuler", "project": project, "overwrite": True})
    assert code == 200, res
    final = wait_job(res["job_id"])
    print(f"    1er export -> {final['status']} en {final.get('_elapsed', 0):.1f}s")
    assert final["status"] == "done", final
    target = EXPORTS / "a_annuler.mp4"
    assert target.exists() and target.stat().st_size > 0
    print(f"    taille: {target.stat().st_size} octets")

    # Ensuite : refus sans confirmation
    code, res = call("POST", "/api/exports", {"name": "a_annuler", "project": project, "overwrite": False})
    print(f"    sans overwrite -> {code} {res.get('detail', {}).get('code', '')}")
    assert code == 409, (code, res)

    # ---- 3. Timing à chaud (2e export du même projet) ----
    print("[3] timing à chaud…")
    t0 = time.time()
    code, res = call("POST", "/api/exports", {"name": "a_chaud", "project": project, "overwrite": True})
    assert code == 200, res
    final = wait_job(res["job_id"])
    elapsed = final.get("_elapsed", 0)
    print(f"    {final['status']} en {elapsed:.1f}s pour 4 s de vidéo "
          f"({4.0/elapsed:.2f}× temps réel), {final['result']['frames']} frames")
    assert final["status"] == "done", final

    # Nettoyage des fichiers de test
    for f in ("a_annuler.mp4", "a_chaud.mp4"):
        (EXPORTS / f).unlink(missing_ok=True)
    print("OK-ANNULL-OVERWRITE-WARM")


if __name__ == "__main__":
    main()
