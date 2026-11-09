"""Extraction de la bible Remotion fournie par l'utilisateur vers skills/remotion/bible/.

Usage : python tools/extract_bible.py "chemin/du.zip"
Écrase uniquement skills/remotion/bible/, ne touche à rien d'autre.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "skills" / "remotion" / "bible"


def main() -> int:
    if not sys.argv[1:]:
        print("zip source manquant")
        return 1
    src = Path(sys.argv[1])
    if not src.is_file():
        print(f"archive introuvable : {src}")
        return 1
    DEST.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(src) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.endswith(".md"):
                continue
            target = DEST / Path(info.filename).name
            target.write_bytes(archive.read(info.filename))
            print(f"{target.stat().st_size:>7}  {target.name}")
            written += 1
    print(f"total : {written} fichiers -> {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
