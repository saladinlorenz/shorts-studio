"""Recherche locale ciblée sur les connaissances déjà présentes.

Le corpus n'est pas recopié dans le prompt : il est découpé en sections,
indexé une fois, puis interrogé pour quelques passages bornés.

Sources indexées :
A. documentation Remotion (``skills/remotion/remotion-best-practices``) ;
B. guides fournis (``bible/``, ``effects/``) ;
C. contrat du studio (format v2, valeurs autorisées, capacités réelles) ;
D. exemples validés (modèles de la bibliothèque, projets v2 réels).

Moteur : SQLite FTS5 (vérifié disponible) avec repli lexical borné si FTS5
manque ou si la requête est refusée. Aucune base vectorielle, aucun modèle
d'embeddings : l'interface ``search()`` est le point d'extension.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from shortvideos import schema

from .. import library as library_mod
from .. import skills as skills_mod
from ..security import KNOWLEDGE_DIR, ROOT, SKILLS_DIR

DB_PATH = KNOWLEDGE_DIR / "agent_index.sqlite3"
CONTRACT_DOC = "contrat/STUDIO.md"
EXAMPLE_PREFIX = "exemples/"

MAX_DOC_CHARS = 200_000  # même plafond que skills.read_document
MAX_CHUNK_CHARS = 2600
MIN_CHUNK_CHARS = 200
MAX_TITLE_CHARS = 160
DEFAULT_LIMIT = 5
DEFAULT_MAX_CHARS = 6000

_LOCK = threading.Lock()

# Docs du contrat studio, lus en dur : aucun chemin ne vient d'une requête.
CONTRACT_FILES = [
    ROOT / "shortvideos" / "PROJECT_FORMAT.md",
]


class RetrievalUnavailable(RuntimeError):
    """Index impossible à construire : l'agent fonctionne sans passages documentaires."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


def _has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE temp._probe USING fts5(x, tokenize='unicode61 remove_diacritics 2')"
        )
        conn.execute("DROP TABLE temp._probe")
        return True
    except sqlite3.OperationalError:
        return False


def _fold(text: str) -> str:
    """Minuscules sans accents : le tokenizer unicode61 fait la même chose."""
    normalized = unicodedata.normalize("NFKD", str(text or "")).lower()
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chunks(
             rowid INTEGER PRIMARY KEY,
             path TEXT, source TEXT, version TEXT,
             title TEXT, section TEXT, body TEXT, sha TEXT
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS docs(
             path TEXT PRIMARY KEY, source TEXT, version TEXT,
             sha TEXT, mtime REAL, chunks INTEGER, updated_at TEXT
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS meta(
             key TEXT PRIMARY KEY, value TEXT
           )"""
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Découpage : par sections markdown, blocs de code préservés intégralement.
# --------------------------------------------------------------------------- #

def split_sections(path_label: str, text: str) -> list[tuple[str, str]]:
    """(titre de section, corps) — les fenced code blocks ne sont jamais coupés."""
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = path_label
    buffer: list[str] = []
    in_fence = False

    def flush(title: str, body: list[str]) -> None:
        content = "\n".join(body).strip("\n")
        if content.strip():
            sections.append((title, content))

    for line in lines:
        stripped = line.strip()
        fence = stripped.startswith("```") or stripped.startswith("~~~")
        heading = (not in_fence) and re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            flush(current_title, buffer)
            buffer = [line]
            current_title = heading.group(2).strip()[:MAX_TITLE_CHARS]
        else:
            buffer.append(line)
        if fence:
            in_fence = not in_fence
    flush(current_title, buffer)

    chunks: list[tuple[str, str]] = []
    for title, body in sections:
        if len(body) <= MAX_CHUNK_CHARS or in_fence_block(body):
            chunks.append((title, body[:MAX_CHUNK_CHARS * 2]))
            continue
        chunks.extend(_split_long(title, body))
    # sections trop courtes : fusionnée avec la précédente (bruit évité)
    merged: list[tuple[str, str]] = []
    for title, body in chunks:
        if merged and len(body) < MIN_CHUNK_CHARS and len(merged[-1][1]) + len(body) < MAX_CHUNK_CHARS:
            merged[-1] = (merged[-1][0], merged[-1][1] + "\n\n" + body)
        else:
            merged.append((title, body))
    return merged


def in_fence_block(body: str) -> bool:
    return body.count("```") % 2 == 1


def _split_long(title: str, body: str) -> list[tuple[str, str]]:
    """Découpe hors des blocs de code, à blanc digne, sans jamais casser un fence."""
    parts: list[tuple[str, str]] = []
    block: list[str] = []
    size = 0
    in_fence = False
    index = 0
    for paragraph in re.split(r"\n\s*\n", body):
        cost = len(paragraph) + 2
        fence_count = paragraph.count("```")
        if size and size + cost > MAX_CHUNK_CHARS and not in_fence:
            parts.append((f"{title} ({len(parts) + 1})", "\n\n".join(block)))
            block = [paragraph]
            size = cost
        else:
            block.append(paragraph)
            size += cost
        if fence_count % 2:
            in_fence = not in_fence
        index += 1
    if block:
        parts.append((title if not parts else f"{title} ({len(parts) + 1})", "\n\n".join(block)))
    return parts


# --------------------------------------------------------------------------- #
# Documents du corpus
# --------------------------------------------------------------------------- #

def _skill_documents() -> list[tuple[str, str, str, str]]:
    """(path, source, version, texte) pour chaque fiche des trois sources."""
    docs: list[tuple[str, str, str, str]] = []
    if not skills_mod.is_installed():
        return docs
    for entry in skills_mod.list_skills():
        for rel in [entry["entry"], *entry.get("docs", [])]:
            try:
                doc = skills_mod.read_document(rel)
            except Exception:  # noqa: BLE001 - une fiche illisible ne bloque pas l'index
                continue
            docs.append((rel, entry["id"], entry.get("version") or "inconnue", doc["content"]))
    return docs


def _contract_documents() -> list[tuple[str, str, str, str]]:
    from . import capabilities

    manifest = capabilities.build()
    fmt = manifest["project_format"]
    lines = [
        "# Contrat du studio (format v2)",
        "",
        "Ce document décrit ce que le studio accepte réellement. Il prime sur toute",
        "fiche documentaire : une technique décrite ailleurs mais absente ici n'est",
        "pas applicable.",
        "",
        "## Modèle de projet",
        "```json",
        json.dumps(
            {
                "version": fmt["version"],
                "model": {"id": fmt["models"][0], "version": 1},
                "content": {"scenes": [], "signature": {}},
                "theme": {},
                "audio": {},
                "variation": {"seed": 1},
                "export": {"width": 1080, "height": 1920, "fps": 30},
            },
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        f"- modèles de composition acceptés : {', '.join(fmt['models'])}",
        f"- types de calques : {', '.join(fmt['layer_types'])}",
        f"- animation entrée : {', '.join(fmt['animation_in'])}",
        f"- animation sortie : {', '.join(fmt['animation_out'])} (aucune autre)",
        f"- unités : {', '.join(fmt['animation_units'])} · courbes : {', '.join(fmt['easings'])}",
        f"- fond : fit {', '.join(fmt['background_fit'])} · animation {', '.join(fmt['background_animation'])}",
        f"- durées : scène {fmt['scene_duration_range'][0]}–{fmt['scene_duration_range'][1]} s, "
        f"total {fmt['total_duration_range'][0]}–{fmt['total_duration_range'][1]} s",
        f"- références média : {fmt['media_references']}",
        f"- bloc resolved : {fmt['resolved_block']}",
        "- temps en frames : animation.start_frames / in_frames / out_frames / stagger_frames",
        "",
        "## Polices autorisées",
        "```json",
        json.dumps(
            {f["id"]: f["weights"] for f in manifest["fonts"]},
            ensure_ascii=False,
        ),
        "```",
        "",
        "## Couleurs",
        "Hexadécimal #RRGGBB. `palette_id` est une étiquette libre : les couleurs",
        "appliquées au rendu sont background_color, surface_color, text_color,",
        "accent_color, author_color, muted_color (et style.color d'un calque).",
        "",
        "## Ce que l'éditeur expose",
        "```",
        "\n".join(f"- {item}" for item in manifest["editor_controls"]),
        "```",
        "",
        "## Indisponible",
        "```",
        "\n".join(f"- {item}" for item in manifest["not_available"]),
        "```",
        "",
        "## Production par lots",
        "```",
        "\n".join(f"- {k} : {v}" for k, v in manifest["batch"]["policy"].items()),
        f"- champs remplissables : {', '.join(manifest['batch']['fillable_fields_example'])}",
        "```",
    ]
    docs = [(CONTRACT_DOC, "studio-contract", f"format v{schema.SCHEMA_VERSION_V2}", "\n".join(lines))]
    for path in CONTRACT_FILES:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:MAX_DOC_CHARS]
        except OSError:
            continue
        docs.append((f"contrat/{path.name}", "studio-contract", "repo", text))
    return docs


def _example_documents() -> list[tuple[str, str, str, str]]:
    """Deux ou trois projets v2 validés, en exemple de structure."""
    docs = []
    for item in library_mod.list_library()[:4]:
        try:
            project = library_mod.get_project(item["id"])
        except Exception:  # noqa: BLE001 - un modèle illisible n'arrête pas l'index
            continue
        project.pop("resolved", None)
        text = json.dumps(project, ensure_ascii=False, indent=1)[:MAX_DOC_CHARS]
        docs.append(
            (
                f"{EXAMPLE_PREFIX}{item['id']}.json",
                "studio-example",
                f"exemple validé · {item.get('label') or item['id']}",
                f"# Exemple de projet v2 validé : {item.get('label') or item['id']}\n\n"
                "Structure de référence (schéma, scènes, calques, animations, signature, "
                "thème, export). Les références média sont des identifiants locaux.\n\n"
                "```json\n" + text + "\n```\n",
            )
        )
    return docs


def _all_documents() -> list[tuple[str, str, str, str]]:
    return [*_skill_documents(), *_contract_documents(), *_example_documents()]


def _index_doc(conn: sqlite3.Connection, path: str, source: str, version: str, text: str) -> int:
    conn.execute("DELETE FROM chunks WHERE path=?", (path,))
    count = 0
    for title, body in split_sections(path, text):
        conn.execute(
            "INSERT INTO chunks(source, version, title, section, body, sha, path) "
            "VALUES(?,?,?,?,?,?,?)",
            (source, version, title, path, body[:MAX_CHUNK_CHARS * 2],
             hashlib.sha256(body.encode("utf-8")).hexdigest()[:16], path),
        )
        count += 1
    conn.execute(
        "INSERT INTO docs(path, source, version, sha, mtime, chunks, updated_at) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
        "source=excluded.source, version=excluded.version, sha=excluded.sha, "
        "mtime=excluded.mtime, chunks=excluded.chunks, updated_at=excluded.updated_at",
        (path, source, version, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
         0.0, count, _now()),
    )
    return count


def _rebuild_fts(conn: sqlite3.Connection) -> bool:
    use_fts = _has_fts5(conn)
    conn.execute("DROP TABLE IF EXISTS chunks_fts")
    if not use_fts:
        conn.commit()
        return False
    conn.execute(
        "CREATE VIRTUAL TABLE chunks_fts USING fts5("
        "title, section, body, tokenize='unicode61 remove_diacritics 2')"
    )
    conn.execute(
        "INSERT INTO chunks_fts(rowid, title, section, body) "
        "SELECT rowid, title, section, body FROM chunks"
    )
    conn.commit()
    return True


def build(force: bool = False) -> dict:
    """Index (ré)utilisable : seuls les fichiers changés sont redécoupés."""
    with _LOCK:
        conn = _connect()
        _schema(conn)
        stored = {row[0]: row[1] for row in conn.execute("SELECT path, sha FROM docs")}
        docs = _all_documents()
        current = {}
        updated: list[str] = []
        chunk_total = 0
        for path, source, version, text in docs:
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            current[path] = sha
            if not force and stored.get(path) == sha:
                row = conn.execute("SELECT chunks FROM docs WHERE path=?", (path,)).fetchone()
                chunk_total += int(row[0] or 0) if row else 0
                continue
            chunk_total += _index_doc(conn, path, source, version, text)
            updated.append(path)
            conn.commit()
        # fichiers disparus du corpus : retirés de l'index
        removed = [p for p in stored if p not in current]
        for path in removed:
            conn.execute("DELETE FROM chunks WHERE path=?", (path,))
            conn.execute("DELETE FROM docs WHERE path=?", (path,))
            conn.commit()
        fts = _rebuild_fts(conn)
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('built_at', ?)", (_now(),))
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('fts5', ?)", ("1" if fts else "0",))
        conn.commit()
        total_chunks = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        conn.close()
    return {
        "built_at": _now(),
        "docs": len(docs),
        "docs_updated": len(updated),
        "docs_removed": len(removed),
        "chunks": total_chunks,
        "fts5": fts,
        "engine": "sqlite-fts5" if fts else "sqlite-like",
        "updated": updated[:20],
    }


def status() -> dict:
    try:
        conn = _connect()
    except sqlite3.Error:
        return {"built": False, "docs": 0, "chunks": 0, "engine": "aucun", "built_at": ""}
    _schema(conn)
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    docs = int(conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0])
    chunks = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    conn.close()
    return {
        "built": chunks > 0,
        "docs": docs,
        "chunks": chunks,
        "engine": "sqlite-fts5" if meta.get("fts5") == "1" else "sqlite-like",
        "built_at": meta.get("built_at", ""),
    }


def _tokens(query: str) -> list[str]:
    folded = _fold(query)
    words = re.findall(r"[a-z0-9][a-z0-9_./@+-]{2,}", folded)
    seen: list[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
    return seen[:12]


def _fts_query(tokens: list[str]) -> str:
    return " OR ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in tokens)


def _rows_for(conn: sqlite3.Connection, where: str, params: tuple, limit: int) -> list[dict]:
    cursor = conn.execute(
        f"SELECT rowid, path, source, version, title, body FROM chunks WHERE {where} "
        "ORDER BY rowid LIMIT ?",
        (*params, limit),
    )
    return [
        {"id": r[0], "path": r[1], "source": r[2], "version": r[3], "title": r[4], "text": r[5]}
        for r in cursor.fetchall()
    ]


def _lexical_search(conn: sqlite3.Connection, tokens: list[str], limit: int) -> list[dict]:
    """Repli sans FTS : occurrences bornées, titres et identifiants mieux notés."""
    if not tokens:
        return []
    scored: dict[int, dict] = {}
    for token in tokens[:8]:
        pattern = f"%{token}%"
        rows = _rows_for(conn, "(lower(title) LIKE ? OR lower(section) LIKE ? OR lower(body) LIKE ?)",
                         (pattern, pattern, pattern), 240)
        for row in rows:
            entry = scored.setdefault(row["id"], {**row, "score": 0.0})
            body = row["text"].lower()
            hits = body.count(token)
            entry["score"] += min(hits, 12) * 0.5
            if token in row["title"].lower():
                entry["score"] += 6
            if token in row["path"].lower():
                entry["score"] += 4
    out = sorted(scored.values(), key=lambda r: -r["score"])
    return out[:limit]


def search(query: str, limit: int = DEFAULT_LIMIT, max_chars: int = DEFAULT_MAX_CHARS) -> list[dict]:
    """Passages documentaires classés, avec source et section, budget respecté."""
    tokens = _tokens(query)
    if not tokens or not DB_PATH.is_file():
        return []
    limit = max(1, min(int(limit), 12))
    conn = _connect()
    try:
        rows: list[dict] = []
        use_fts = _has_fts5(conn)
        if use_fts:
            try:
                cursor = conn.execute(
                    "SELECT c.rowid, c.path, c.source, c.version, c.title, c.body, "
                    "bm25(chunks_fts, 6.0, 3.0, 1.0) AS rank "
                    "FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid "
                    "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                    (_fts_query(tokens), limit * 3),
                )
                rows = [
                    {"id": r[0], "path": r[1], "source": r[2], "version": r[3], "title": r[4],
                     "text": r[5], "score": round(-float(r[6]), 4)}
                    for r in cursor.fetchall()
                ]
            except sqlite3.OperationalError:
                rows = []
            if not rows:
                # requête refusée ou aucun mot exact : retentative AND, puis lexical
                try:
                    cursor = conn.execute(
                        "SELECT c.rowid, c.path, c.source, c.version, c.title, c.body, "
                        "bm25(chunks_fts, 6.0, 3.0, 1.0) AS rank "
                        "FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid "
                        "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                        (" AND ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in tokens[:4]), limit * 2),
                    )
                    rows = [
                        {"id": r[0], "path": r[1], "source": r[2], "version": r[3], "title": r[4],
                         "text": r[5], "score": round(-float(r[6]), 4)}
                        for r in cursor.fetchall()
                    ]
                except sqlite3.OperationalError:
                    rows = []
        if not rows:
            rows = _lexical_search(conn, tokens, limit * 2)
        conn.close()
    except sqlite3.Error as e:
        conn.close()
        raise RetrievalUnavailable(f"Index de connaissances indisponible : {e}") from e

    # identifiant exact cité dans la demande : renforcement (interpolate, spring…)
    needle = _fold(query)
    for row in rows:
        if needle and needle in _fold(row["title"]):
            row["score"] = float(row.get("score", 0)) + 10
    rows.sort(key=lambda r: -float(r.get("score", 0)))

    out: list[dict] = []
    used = 0
    for row in rows:
        text = row["text"]
        truncated = len(text) > 1400
        body = text[:1400]
        if used + len(body) > max_chars:
            break
        used += len(body)
        out.append(
            {
                "id": row["id"],
                "path": row["path"],
                "source": row["source"],
                "version": row["version"],
                "title": row["title"],
                "text": body,
                "truncated": truncated,
                "score": round(float(row.get("score", 0.0)), 3),
            }
        )
        if len(out) >= limit:
            break
    return out


def read_chunk(chunk_id: int) -> dict:
    """Texte complet d'un passage, pour l'outil read_knowledge."""
    conn = _connect()
    row = conn.execute(
        "SELECT rowid, path, source, version, title, body FROM chunks WHERE rowid=?",
        (int(chunk_id),),
    ).fetchone()
    conn.close()
    if not row:
        return {"error": f"Passage {chunk_id} introuvable dans l'index."}
    return {
        "id": row[0], "path": row[1], "source": row[2], "version": row[3],
        "title": row[4], "text": row[5][:MAX_CHUNK_CHARS * 2],
    }


def skills_path_of(rel: str) -> Path:
    """Chemin disque d'un document du catalogue (paquet Remotion ou montage)."""
    return skills_mod.document_path(rel)
