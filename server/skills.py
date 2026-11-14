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

from .security import MONTAGE_DIR, ROOT, SKILLS_DIR, assert_local_dir

BUNDLE = SKILLS_DIR / "remotion-best-practices"
# bible francaise fournie par l'utilisateur (voir skills/remotion/PROVENANCE.md)
BIBLE = SKILLS_DIR / "bible"
BIBLE_ID = "remotion-bible"
# guide des effets video, fourni par l'utilisateur et decoupe en fiches
EFFECTS = SKILLS_DIR / "effects"
EFFECTS_ID = "remotion-effects-fr"
# grammaire de production importee d'OpenMontage (voir skills/montage/PROVENANCE.md)
MONTAGE = MONTAGE_DIR
MONTAGE_ID = "montage-production"
# prefixe virtuel des chemins du paquet montage : « montage/pipeline_defs/... »
MONTAGE_PREFIX = "montage"
MONTAGE_SUFFIXES = {".md", ".yaml", ".yml"}
MAX_PIPELINE_DESC = 600
MAX_PIPELINE_EXCERPT = 4_000
MAX_STAGE_TOOLS = 12

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


def _montage_rel(path: Path) -> str:
    """Chemin virtuel d'un fichier du paquet montage : « montage/<relatif> »."""
    return f"{MONTAGE_PREFIX}/{path.relative_to(MONTAGE).as_posix()}"


def _montage_path(rel_path: str) -> Path | None:
    """Resout un chemin virtuel « montage/... » ; None si ce n'en est pas un."""
    prefix = MONTAGE_PREFIX + "/"
    if not rel_path.startswith(prefix):
        return None
    return MONTAGE / rel_path[len(prefix):]


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


def _montage_entry() -> dict | None:
    """Grammaire de production (pipelines YAML + directeurs d'etape).

    Le README du dossier sert d'entree ; tout le reste est indexe comme
    documents. Les manifestes .yaml sont acceptes : ce sont eux qui portent
    les etapes, les outils autorises et les criteres de revue.
    """
    if not MONTAGE.is_dir():
        return None
    readme = MONTAGE / "README.md"
    if not readme.is_file():
        return None
    meta = _frontmatter(readme.read_text(encoding="utf-8", errors="replace"))
    docs = [
        path
        for path in _montage_docs()
        if path != _montage_rel(readme)
    ]
    if not docs:
        return None
    return {
        "id": MONTAGE_ID,
        "title": "Montage (pipelines de production)",
        "description": meta.get("description") or (
            "Choisir un pipeline, produire brief, plan de scenes, manifeste "
            "d'assets et decisions de montage avant tout rendu."
        ),
        "version": meta.get("version", ""),
        "entry": _montage_rel(readme),
        "docs": docs,
    }


def _montage_docs() -> list[str]:
    """Chemins relatifs des fiches et manifestes du paquet montage."""
    if not MONTAGE.is_dir():
        return []
    return sorted(
        _montage_rel(path)
        for path in MONTAGE.rglob("*")
        if path.is_file() and path.suffix.lower() in MONTAGE_SUFFIXES
    )


def _yaml_data(text: str) -> dict | None:
    """Charge un manifeste YAML ; None si PyYAML est absent ou le fichier invalide."""
    try:
        import yaml  # noqa: PLC0415 - dependance optionnelle, chargee a l'usage
    except ImportError:
        return None
    try:
        data = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 - un manifeste casse ne doit pas tuer l'outil
        return None
    return data if isinstance(data, dict) else None


def montage_pipelines() -> list[dict]:
    """Manifestes de pipeline lus sur disque, resumes et bornes.

    Chaque entree decrit les etapes, l'artefact produit par chacune et les
    outils autorises : c'est le contrat que l'assistant doit suivre avant de
    proposer un montage. Aucun chemin ne vient d'une requete.
    """
    if not MONTAGE.is_dir():
        return []
    base = MONTAGE / "pipeline_defs"
    if not base.is_dir():
        return []
    result: list[dict] = []
    for path in sorted(base.glob("*.yaml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        data = _yaml_data(text)
        item: dict = {"id": path.stem, "source": _montage_rel(path)}
        if data is None:
            item["parsed"] = False
            item["excerpt"] = text[:MAX_PIPELINE_EXCERPT]
            result.append(item)
            continue
        orchestration = data.get("orchestration") or {}
        stages = []
        for stage in data.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            stages.append(
                {
                    "name": stage.get("name", ""),
                    "skill": stage.get("skill", ""),
                    "produces": list(stage.get("produces") or []),
                    "approval": bool(stage.get("human_approval_default")),
                    "tools": list(stage.get("tools_available") or [])[:MAX_STAGE_TOOLS],
                }
            )
        item.update(
            {
                "parsed": True,
                "name": data.get("name") or path.stem,
                "category": data.get("category", ""),
                "stability": data.get("stability", ""),
                "description": " ".join(
                    str(data.get("description") or "").split()
                )[:MAX_PIPELINE_DESC],
                "budget_default_usd": orchestration.get("budget_default_usd"),
                "stages": stages,
            }
        )
        result.append(item)
    return result


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
    montage = _montage_entry()
    if montage:
        entries.append(montage)
    return entries


def find_skill(skill_id: str) -> dict:
    for entry in list_skills():
        if entry["id"] == skill_id:
            return entry
    raise HTTPException(status_code=404, detail="Competence inconnue.")


def document_path(rel_path: str) -> Path:
    """Chemin disque d'un document du catalogue, borne au paquet qui le declare.

    Les chemins « montage/... » sont resolus dans ``skills/montage`` ; tous les
    autres restent dans ``skills/remotion``. Aucun chemin arbitraire.
    """
    if not rel_path:
        raise HTTPException(status_code=400, detail="Chemin de document requis.")
    montage_target = _montage_path(rel_path)
    if montage_target is not None:
        base = MONTAGE
        candidate = montage_target
        allowed = MONTAGE_SUFFIXES
    else:
        base = SKILLS_DIR
        candidate = SKILLS_DIR / rel_path
        allowed = {".md"}
    candidate = assert_local_dir(candidate)
    if candidate.suffix.lower() not in allowed or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Document de competence introuvable.")
    try:
        candidate.relative_to(base.resolve())
    except ValueError:  # pragma: no cover - assert_local_dir protege deja
        raise HTTPException(status_code=400, detail="Chemin hors du paquet de competences.")
    return candidate


def read_document(rel_path: str) -> dict:
    """Contenu d'un document du paquet (.md, .yaml), chemin borne au paquet."""
    candidate = document_path(rel_path)
    text = candidate.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > MAX_DOC_CHARS
    label = rel_path if _montage_path(rel_path) is not None else _rel(candidate)
    return {
        "path": label,
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
        if e["version"] and e["id"] not in {BIBLE_ID, EFFECTS_ID, MONTAGE_ID}
    }
    sources = [
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
        {
            "id": MONTAGE_ID,
            "source": "https://github.com/OpenMontageInc/OpenMontage @ fecb9a1 (2026-11-08)",
            "licence": "AGPL-3.0",
            "note": (
                "Copie sans modification des manifestes de pipeline, des "
                "directeurs d'etape, des fiches core/creative/meta et des "
                "playbooks de style. Aucun code executable n'est copie : le "
                "depot reste hors du studio. Voir skills/montage/PROVENANCE.md."
            ),
        },
    ]
    return {
        "folder": _rel(SKILLS_DIR),
        "folder_path": str(SKILLS_DIR),
        "version": ", ".join(sorted(versions)),
        "sources": sources,
        "licence": "inconnue",
        "licence_note": (
            "Au moins une source n'a pas de licence etablie : le dossier est un "
            "contexte interne de l'agent, il n'est pas redistribue au client."
        ),
        "usage": "contexte interne de l'agent ; documents non redistribues au client",
    }
