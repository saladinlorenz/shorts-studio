"""Paquet de connaissances Remotion lu par l'agent de l'app.

Le paquet « Agent Skills » (remotion-dev) est vendorise sous skills/remotion/ :
lecture disque uniquement, aucun appel reseau, aucune dependance ajoutee.
L'agent (Groq, cote serveur) demande le catalogue, une competence, un document
ou un bloc de contexte a inserer dans son prompt systeme.

Les fichiers du paquet ne sont pas modifies : ils s'enchainent par liens
relatifs, donc tout chemin renvoye par le catalogue est resolvable ici.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from .security import ROOT, SKILLS_DIR, assert_local_dir

BUNDLE = SKILLS_DIR / "remotion-best-practices"
# bible francaise fournie par l'utilisateur (voir skills/remotion/PROVENANCE.md)
BIBLE = SKILLS_DIR / "bible"
BIBLE_ID = "remotion-bible"
# guide des effets video, fourni par l'utilisateur et decoupe en fiches
EFFECTS = SKILLS_DIR / "effects"
EFFECTS_ID = "remotion-effects-fr"

# Garde-fou : un document fait quelques kilo-octets ; on refuse les derives.
MAX_DOC_CHARS = 200_000


def _frontmatter(text: str) -> dict[str, str]:
    """Lit l'en-tete YAML simple (name/description/version) d'un fichier .md."""
    meta: dict[str, str] = {}
    if not text.startswith("---"):
        return meta
    for line in text.splitlines()[1:40]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    return meta


def _rel(path: Path) -> str:
    return path.relative_to(SKILLS_DIR).as_posix()


def _docs_of(base: Path) -> list[str]:
    return sorted(_rel(p) for p in base.rglob("*.md") if p.is_file())


def _entry(entry_path: Path, *, with_docs: bool = True) -> dict:
    text = entry_path.read_text(encoding="utf-8", errors="replace")
    meta = _frontmatter(text)
    skill_dir = entry_path.parent
    name = meta.get("name") or skill_dir.name
    return {
        "id": name,
        "title": name.replace("-", " ").capitalize(),
        "description": meta.get("description", ""),
        "version": meta.get("version", ""),
        "entry": _rel(entry_path),
        "docs": _docs_of(skill_dir) if with_docs else [],
    }


def is_installed() -> bool:
    return SKILLS_DIR.is_dir()


def _bible_entry() -> dict | None:
    """Entree du paquet de fiches francises depose dans skills/remotion/bible/."""
    if not BIBLE.is_dir():
        return None
    docs = sorted((p for p in BIBLE.glob("*.md") if p.is_file()), key=lambda p: p.name)
    if not docs:
        return None
    return {
        "id": BIBLE_ID,
        "title": "Bible Remotion (francais)",
        "description": (
            "Memoire de travail en francais : coeur de l'API du paquet remotion, "
            "effets et recettes, paquets @remotion/*, rendu CLI/Node/Lambda/Player, "
            "audio, video, sous-titres et IA."
        ),
        "version": "fourni par l'utilisateur (2026-11-02)",
        "entry": _rel(docs[0]),
        "docs": [_rel(p) for p in docs[1:]],
    }


def _effects_entry() -> dict | None:
    """Entree du guide des effets, decoupe en fiches ranges par numero."""
    if not EFFECTS.is_dir():
        return None
    docs = sorted((p for p in EFFECTS.glob("*.md") if p.is_file()), key=lambda p: p.name)
    if not docs:
        return None
    meta = _frontmatter(docs[0].read_text(encoding="utf-8", errors="replace"))
    return {
        "id": EFFECTS_ID,
        "title": "Effets video Remotion (francais)",
        "description": meta.get("description") or (
            "Regles de rendu et d'animation, medias, code des effets (texte, traces, "
            "camera, filtres, transitions, 3D, audio), paquets @remotion/*, rendu "
            "CLI/Node/Lambda/Player, sous-titres Whisper, performance et pieges."
        ),
        "version": meta.get("version") or "fourni par l'utilisateur (2026-11-03)",
        "entry": _rel(docs[0]),
        "docs": [_rel(p) for p in docs[1:]],
    }


def list_skills() -> list[dict]:
    """Routeur du paquet d'abord, puis une entree par competence, puis les fiches francises."""
    if not is_installed():
        return []
    entries: list[dict] = []
    router = BUNDLE / "SKILL.md"
    if router.is_file():
        entries.append(_entry(router, with_docs=False))
    for reference in sorted(BUNDLE.glob("*/REFERENCE.md")):
        entries.append(_entry(reference))
    bible = _bible_entry()
    if bible:
        entries.append(bible)
    effects = _effects_entry()
    if effects:
        entries.append(effects)
    return entries


def find_skill(skill_id: str) -> dict:
    for entry in list_skills():
        if entry["id"] == skill_id:
            return entry
    raise HTTPException(status_code=404, detail="Competence inconnue.")


def read_document(rel_path: str) -> dict:
    """Contenu d'un document markdown du paquet, chemin borne au paquet."""
    if not rel_path:
        raise HTTPException(status_code=400, detail="Chemin de document requis.")
    candidate = assert_local_dir(SKILLS_DIR / rel_path)
    if candidate.suffix.lower() != ".md" or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Document de competence introuvable.")
    try:
        candidate.relative_to(SKILLS_DIR.resolve())
    except ValueError:  # pragma: no cover - assert_local_dir protege deja
        raise HTTPException(status_code=400, detail="Chemin hors du paquet de competences.")
    text = candidate.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > MAX_DOC_CHARS
    return {
        "path": _rel(candidate),
        "content": text[:MAX_DOC_CHARS],
        "chars": len(text),
        "truncated": truncated,
    }


def project_state() -> str:
    """Etat reel de l'outillage, lu a l'execution : ce que l'agent peut employer."""
    pkg = ROOT / "web" / "package.json"
    if not pkg.is_file():
        return ""
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ""
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    packs = sorted(k for k in deps if k.startswith("@remotion/"))
    return "\n".join(
        [
            "<!-- ETAT DU PROJET (lu a l'execution) -->",
            f"- Remotion installe : {deps.get('remotion', 'inconnu')} (web/package.json).",
            f"- Paquets @remotion/* presents : {', '.join(packs) if packs else 'aucun'}.",
            "- Un paquet @remotion/* qui n'est pas dans cette liste n'est pas "
            "installable en silence : proposer ce paquet exige d'abord d'ajouter "
            "la dependance.",
        ]
    )


def build_context(skill_ids: list[str] | None = None, max_chars: int = 60_000) -> str:
    """Bloc Markdown (etat du projet + routeur + competences) pour le prompt de l'agent.

    Le resultat ne depasse jamais `max_chars` : l'appelant budgete des tokens.
    """
    parts: list[str] = []
    used = 0

    def add(block: str) -> bool:
        nonlocal used
        if used + len(block) > max_chars:
            # On garde ce qui tient plutot que de ne rien renvoyer.
            parts.append(block[: max_chars - used])
            used = max_chars
            return False
        parts.append(block)
        used += len(block)
        return True

    state = project_state()
    if state and not add(state + "\n\n"):
        return "".join(parts).strip()

    for entry in list_skills():
        wanted = skill_ids is None or entry["id"] in skill_ids
        if entry["id"] == "remotion-best-practices":
            wanted = True  # le routeur oriente l'agent vers les bonnes fiches
        if not wanted:
            continue
        for rel_path in [entry["entry"], *entry["docs"]]:
            doc = read_document(rel_path)
            if not add(f"\n\n<!-- {doc['path']} -->\n{doc['content']}"):
                return "".join(parts).strip()
    return "".join(parts).strip()


def provenance() -> dict:
    """Origine et licence de chaque source du dossier, telles que verifyees localement."""
    versions = {
        e["version"]
        for e in list_skills()
        if e["version"] and e["id"] not in {BIBLE_ID, EFFECTS_ID}
    }
    return {
        "folder": _rel(SKILLS_DIR),
        "folder_path": str(SKILLS_DIR),
        "version": ", ".join(sorted(versions)),
        "sources": [
            {
                "id": "remotion-best-practices",
                "source": "https://github.com/remotion-dev/skills",
                "licence": "inconnue",
                "note": (
                    "Aucun fichier LICENSE dans le depot (main/LICENSE -> 404, "
                    "API GitHub -> « license: null ») : licence non etablie, "
                    "donc non validee ici."
                ),
            },
            {
                "id": BIBLE_ID,
                "source": "fourni par l'utilisateur (archive « files (4).zip », 2026-11-02)",
                "licence": "non precisee",
                "note": (
                    "Memoire de travail redigee pour le projet ; les noms d'API "
                    "cites ont ete confrontes aux fichiers installes. La liste des "
                    "paquets @remotion/* depasse l'outillage reel du projet, d'ou "
                    "le bloc ETAT DU PROJET injecte dans le contexte."
                ),
            },
            {
                "id": EFFECTS_ID,
                "source": "fourni par l'utilisateur (« Les meilleurs effets vidéo avec "
                "Remotion.md », 2026-11-03)",
                "licence": "non precisee",
                "note": (
                    "Guide d'effets decoupe en 10 fiches sans modification du texte "
                    "(titres remontes d'un niveau) ; l'original reste dans le "
                    "telechargement de l'utilisateur. Les paquets @remotion/* cites "
                    "depassent l'outillage installe (seuls remotion, @remotion/cli et "
                    "@remotion/player le sont), et le guide documente Remotion 4.x : "
                    "le bloc ETAT DU PROJET et la fiche 10 « Compatibilite entre "
                    "versions » font foi avant toute proposition de code."
                ),
            },
        ],
        "licence": "inconnue",
        "licence_note": (
            "Au moins une source n'a pas de licence etablie : le dossier est un "
            "contexte interne de l'agent, il n'est pas redistribue au client."
        ),
        "usage": "contexte interne de l'agent ; documents non redistribues au client",
    }
