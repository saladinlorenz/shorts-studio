# -*- coding: utf-8 -*-
"""Decoupe le guide « Les meilleurs effets video avec Remotion » en fiches.

Les textes des sections sont recopies verbatim ; seuls les titres sont remontes
d'un niveau (## -> #) pour que chaque fiche soit autonome. Le script verifie
que chaque fiche est identique a sa section d'origine.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(r"C:\Users\saladin\Downloads\Les meilleurs effets vidéo avec Remotion (1).md")
OUT = Path(r"E:\youtube\youtube_clipper\skills\remotion\effects")

NAMES = {
    "1": "01_MODELE_RENDU_REGLES",
    "2": "02_FONCTIONS_ANIMATION",
    "3": "03_MEDIAS_METADONNEES_ENVIRONNEMENT",
    "4": "04_EFFETS_TEXTE_TRACES_CAMERA",
    "5": "05_EFFETS_FILTRES_TRANSITIONS_3D_AUDIO",
    "6": "06_PAQUETS_REMOTION",
    "7": "07_RENDU_AUTOMATISATION_DEPLOIEMENT",
    "8": "08_SOUS_TITRES_WHISPER",
    "9": "09_PERFORMANCE_PIEGES",
    "10": "10_COMPATIBILITE_VERSIONS",
}


def split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Coupe hors blocs de code : une ligne « ## » dans un ``` n'est pas un titre."""
    head: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            sections.append((line[3:].strip(), [line]))
        elif not sections:
            head.append(line)
        else:
            sections[-1][1].append(line)
    return head, sections


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    head, sections = split_sections(text.splitlines())

    guide_title = next((l[2:].strip() for l in head if l.startswith("# ")), "Guide des effets video")
    numbered = {}
    for title, body in sections:
        m = re.match(r"^(\d+)\.\s", title)
        if m:
            numbered[m.group(1)] = (title, body)

    missing = [k for k in NAMES if k not in numbered]
    if missing:
        print("SECTIONS MANQUANTES:", missing)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, str]] = []
    for key, stem in NAMES.items():
        title, body = numbered[key]
        original = "\n".join(body)[1:].rstrip()  # « ## » -> « # », texte inchange
        path = OUT / (stem + ".md")
        path.write_text(original + "\n", encoding="utf-8")
        check = path.read_text(encoding="utf-8").strip()
        if check != original.strip():
            print("CONTENU MODIFIE:", stem)
            return 1
        written.append((stem, title))

    extras = [(title, "\n".join(body).rstrip()) for title, body in sections if title not in {t for t, _ in numbered.values()}]
    intro_rest = "\n".join(l for l in head if not l.startswith("# ")).strip()
    toc = "\n".join(f"- {stem}.md — {title}" for stem, title in written)
    index = (
        "---\n"
        "name: remotion-effects-fr\n"
        f"description: Guide des effets video Remotion ({len(written)} fiches) : regles de "
        "rendu, animation, medias, effets codes, paquets @remotion/*, rendu CLI/Node/"
        "Lambda/Player, sous-titres Whisper, performance, compatibilite des versions.\n"
        "version: fourni par l'utilisateur (2026-11-03)\n"
        "---\n\n"
        "# EFFETS VIDEO REMOTION — INDEX (lisez ce fichier en premier)\n\n"
        + (intro_rest + "\n\n" if intro_rest else "")
        + f"Source : « {guide_title} », memoire de travail en francais fournie par "
        "l'utilisateur. Licence non precisee : contexte interne de l'agent, non "
        "redistribue au client.\n\n"
        "Le guide decrit Remotion 4.x et enumere beaucoup de paquets `@remotion/*` "
        "que ce projet n'a pas installes : se fier au bloc « ETAT DU PROJET » du "
        "contexte avant de proposer un paquet.\n\n"
        "## Fiches\n\n"
        + toc
        + "\n\n"
        + "\n\n".join(body for _, body in extras)
        + "\n"
    )
    (OUT / "00_INDEX_LISEZ_MOI.md").write_text(index, encoding="utf-8")

    print("fiches :", len(written) + 1)
    print("sommaire extras :", [t for t, _ in extras])
    print("caracteres source :", len(text), "| ecrits :", sum(len(p.read_text(encoding="utf-8")) for p in OUT.glob("*.md")))
    print("fichiers :", sorted(p.name for p in OUT.glob("*.md")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
