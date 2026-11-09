"""Test de bout en bout : upload média -> export Remotion -> vérification."""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Console Windows : afficher les messages d'erreur Remotion sans crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"


def call(method, path, data=None, raw=None, content_type="application/json"):
    url = BASE + path
    body = None
    if raw is not None:
        body = raw
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", content_type)
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
    boundary = "----bnd1234567890"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    # 1. Fond réel généré par Pillow
    from PIL import Image, ImageDraw

    d = Path(r"E:\youtube\youtube_clipper\.pytest_tmp\e2e")
    d.mkdir(parents=True, exist_ok=True)
    bg = d / "fond e2e.png"
    img = Image.new("RGB", (1080, 1920), (25, 32, 60))
    dr = ImageDraw.Draw(img)
    dr.ellipse([120, 480, 960, 1320], fill=(170, 84, 42))
    dr.rectangle([0, 1500, 1080, 1920], fill=(18, 20, 34))
    img.save(bg)
    logo = d / "logo e2e.png"
    Image.new("RGBA", (240, 240), (255, 210, 60, 230)).save(logo)

    print("[1] upload médias…")
    up_bg = multipart("/api/media/upload", "fond e2e.png", bg.read_bytes(), "image/png")
    up_logo = multipart("/api/media/upload", "logo e2e.png", logo.read_bytes(), "image/png")
    print("    fond:", up_bg["url"], "| logo:", up_logo["url"])

    # 2. Projet réel (5 s, 1080x1920, 30 fps)
    project = {
        "version": 1,
        "template": "quote_vertical",
        "content": {
            "text": "Le courage est le premier des vertus, car il est le garant de tous les autres.",
            "author": "Aristote",
            "background_image": f"media://{up_bg['id']}",
            "logo": f"media://{up_logo['id']}",
        },
        "theme": {
            "font_family": "arialbd.ttf", "font_size": 72,
            "text_color": "#FFFFFF", "author_color": "#F2C14E",
            "accent_color": "#F2C14E", "shadow": True,
        },
        "position": {"x": 0.5, "y": 0.45, "width": 0.85},
        "timing": {"duration": 5.0, "text_start": 0.4, "fade_in": 0.8, "fade_out": 0.8},
        "animation": {"text_in": "slide", "background": "zoom_slow"},
        "export": {"width": 1080, "height": 1920, "fps": 30, "output_dir": ""},
    }

    print("[2] validation serveur…")
    code, res = call("POST", "/api/projects/validate", {"project": project})
    print("   ", code, res)

    print("[3] lancement export Remotion…")
    t0 = time.time()
    code, res = call("POST", "/api/exports", {"name": "citation e2e", "project": project})
    print("   ", code, res)
    if code != 200:
        sys.exit(1)
    job_id = res["job_id"]

    last = None
    while True:
        time.sleep(0.5)
        code, snap = call("GET", f"/api/exports/{job_id}")
        if code != 200:
            print("   poll KO:", code, snap)
            sys.exit(1)
        state = (snap["status"], snap["message"], round(snap["progress"], 3))
        if state != last:
            print(f"   {snap['status']:10s} {snap['progress']*100:5.1f}%  {snap['message']}")
            last = state
        if snap["status"] != "running":
            break
        if time.time() - t0 > 900:
            call("POST", f"/api/exports/{job_id}/cancel")
            print("   TIMEOUT 15 min")
            sys.exit(1)

    elapsed = time.time() - t0
    print(f"[4] statut final: {snap['status']} après {elapsed:.1f} s")
    if snap["status"] != "done":
        print("ERREUR:", snap["error"])
        print(snap.get("result"))
        sys.exit(1)
    print("    résultat:", json.dumps(snap["result"], indent=2, ensure_ascii=False))

    # 3. Vérification indépendante du fichier produit (OpenCV)
    out = Path(r"E:\youtube\youtube_clipper\exports") / f"{snap['result']['path']}"
    print("[5] vérification fichier:", out, "existe:", out.exists())
    import cv2
    cap = cv2.VideoCapture(str(out))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, frame = cap.read()
    cap.release()
    print(f"    OpenCV: {w}x{h} @ {fps:.3f} fps, {n} frames, première frame lisible: {ok}")
    assert w == 1080 and h == 1920 and abs(fps - 30) < 0.1 and n == 150 and ok
    print(f"    TAILLE: {out.stat().st_size} octets")
    print(f"    TEMPS TOTAL EXPORT: {elapsed:.1f} s pour 5 s de vidéo "
          f"({5.0/elapsed:.2f}× temps réel, inclut 1er téléchargement navigateur si présent)")
    print("E2E OK")


if __name__ == "__main__":
    main()
