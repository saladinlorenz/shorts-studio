"""Lecture d'un CSV de production.

Le fichier vient de l'utilisateur (Excel, Google Sheets, Notion…) : le
programme se plie au fichier, pas l'inverse. Trois choses sont donc détectées
et rapportées — l'encodage, le séparateur, la ligne d'en-têtes — et le reste
(des règles strictes) s'applique à l'identique quel que soit le CSV :

- ``;`` ou ``,`` ou ``\\t`` : le séparateur le plus fréquent sur la ligne 1 ;
- UTF-8 avec BOM, UTF-8, sinon Windows-1252 (le défaut des CSV français) ;
- une ligne trop courte ou trop longue n'est pas « corrigée » : elle est
  signalée avec son numéro, pour que le lot ne parte pas sur des données
  décalées ;
- le nombre de lignes est plafonné (:data:`MAX_ROWS`) : au-delà, le découpage
  en plusieurs lots reste plus sûr pour un rendu local.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from .security import BATCH_DIR, safe_name

MAX_ROWS = 2000
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252")
DELIMITERS = (",", ";", "\t", "|")


def _csv_dir() -> Path:
    path = BATCH_DIR / "csvs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def store(payload: bytes, original_name: str = "lot.csv") -> dict:
    """Enregistre le CSV tel quel et renvoie son analyse.

    Le fichier reste sur disque : un lot relance quelques jours plus tard
    s'appuie sur la meme source, et le manifeste peut la citer.
    """
    parsed = parse(payload)
    csv_id = uuid.uuid4().hex[:12]
    name = safe_name(original_name or "lot.csv")
    if not name.lower().endswith(".csv"):
        name += ".csv"
    folder = _csv_dir()
    (folder / f"{csv_id}.csv").write_bytes(payload)
    (folder / f"{csv_id}.json").write_text(
        json.dumps(
            {
                "id": csv_id,
                "original_name": name,
                "stored_as": f"{csv_id}.csv",
                "columns": parsed["columns"],
                "encoding": parsed["encoding"],
                "delimiter": parsed["delimiter"],
                "warnings": parsed["warnings"],
                "rows": len(parsed["rows"]),
                "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"id": csv_id, "file": name, **parsed}


def load(csv_id: str) -> dict:
    """Meta + lignes d'un CSV enregistré (le fichier n'est jamais trusté à l'aveugle)."""
    if not csv_id or any(ch in csv_id for ch in "/\\.:"):
        raise HTTPException(status_code=400, detail="Identifiant de CSV invalide.")
    folder = _csv_dir()
    meta_path = folder / f"{csv_id}.json"
    source = folder / f"{csv_id}.csv"
    if not meta_path.exists() or not source.exists():
        raise HTTPException(status_code=404, detail="CSV introuvable : importez-le à nouveau.")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"CSV illisible : {e}") from e
    parsed = parse(source.read_bytes())
    if parsed["columns"] != meta.get("columns"):
        raise HTTPException(
            status_code=400,
            detail="Le CSV enregistré n'est plus lisible : relancez l'import.",
        )
    return {"meta": meta, **parsed}


def preview(csv_id: str, limit: int = 20) -> dict:
    data = load(csv_id)
    data["rows"] = data["rows"][: max(1, min(limit, 100))]
    return data



def _decode(payload: bytes) -> tuple[str, str]:
    for encoding in ENCODINGS:
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    # dernier recours : remplace les octets invalides plutot que d'échouer
    return payload.decode("utf-8", errors="replace"), "utf-8 (octets invalides remplacés)"


def detect_delimiter(text: str) -> str:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    try:
        dialect = csv.Sniffer().sniff(first_line, delimiters="".join(DELIMITERS))
        if dialect.delimiter in DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass
    counts = {d: first_line.count(d) for d in DELIMITERS}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","


def parse(payload: bytes) -> dict:
    """Bytes du fichier -> colonnes, lignes et avertissements de structure."""
    if not payload or not payload.strip():
        raise HTTPException(status_code=400, detail="CSV vide.")
    text, encoding = _decode(payload)
    delimiter = detect_delimiter(text)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        rows = list(reader)
    except csv.Error as e:
        raise HTTPException(status_code=400, detail=f"CSV illisible : {e}") from e

    rows = [r for r in rows if any(str(cell).strip() for cell in r)]
    if not rows:
        raise HTTPException(status_code=400, detail="CSV sans ligne exploitable.")
    if len(rows) - 1 > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"CSV de {len(rows) - 1} lignes : maximum {MAX_ROWS} par lot — découpez en plusieurs lots.",
        )

    header = [str(cell).strip() for cell in rows[0]]
    columns: list[str] = []
    for position, name in enumerate(header, start=1):
        candidate = name or f"colonne_{position}"
        while candidate in columns:
            candidate += "_"
        columns.append(candidate)

    records: list[dict[str, str]] = []
    warnings: list[str] = []
    for number, raw in enumerate(rows[1:], start=2):
        if len(raw) != len(columns):
            warnings.append(
                f"ligne {number} : {len(raw)} valeur(s) pour {len(columns)} colonne(s) ; "
                "les cellules manquantes sont laissées vides."
            )
            padded = list(raw) + [""] * max(0, len(columns) - len(raw))
            raw = padded[: len(columns)]
        record = {columns[i]: str(raw[i]).strip() for i in range(len(columns))}
        if not any(v for v in record.values()):
            continue
        records.append(record)

    if not records:
        raise HTTPException(status_code=400, detail="Le CSV n'a que des lignes vides après l'en-tête.")

    blank_headers = [columns[i] for i, name in enumerate(header) if not name]
    if blank_headers:
        warnings.append(
            "en-tête(s) vide(s) renommé(s) : " + ", ".join(blank_headers[:6]) + " (mapping à vérifier)."
        )

    return {
        "columns": columns,
        "rows": records,
        "encoding": encoding,
        "delimiter": delimiter,
        "warnings": warnings,
        "max_rows": MAX_ROWS,
    }
