import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { BATCH_DIR, HttpError, safeName } from "./security.ts";

export const MAX_ROWS = 500;
const CSV_DIR = path.join(BATCH_DIR, "csv");

function parseCsvLine(line: string, delimiter: string): string[] {
  const fields: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === delimiter && !inQuotes) {
      fields.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  fields.push(cur);
  return fields;
}

function splitRecords(text: string): string[] {
  const records: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
      cur += ch;
    } else if ((ch === "\n" || ch === "\r") && !inQuotes) {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      if (cur.trim()) records.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  if (cur.trim()) records.push(cur);
  return records;
}

function detectDelimiter(sample: string): string {
  const candidates = [",", ";", "\t", "|"];
  let best = ",";
  let bestCount = 0;
  for (const d of candidates) {
    const count = parseCsvLine(sample, d).length;
    if (count > bestCount) {
      bestCount = count;
      best = d;
    }
  }
  return best;
}

export function store(buffer: Buffer, filename: string): {
  id: string;
  file: string;
  columns: string[];
  rows: Array<Record<string, string>>;
  encoding: string;
  delimiter: string;
  warnings: string[];
} {
  let text = buffer.toString("utf8").replace(/^\uFEFF/, "");
  const encoding = "utf-8";
  const records = splitRecords(text);
  if (records.length === 0) {
    throw new HttpError(400, "Fichier CSV vide.");
  }
  const delimiter = detectDelimiter(records[0]);
  const headers = parseCsvLine(records[0], delimiter).map((h, i) => h.trim() || `col_${i + 1}`);
  const warnings: string[] = [];
  if (records.length - 1 > MAX_ROWS) {
    warnings.push(`CSV limite aux ${MAX_ROWS} premieres lignes.`);
  }
  const rows: Array<Record<string, string>> = [];
  for (const rec of records.slice(1, MAX_ROWS + 1)) {
    const vals = parseCsvLine(rec, delimiter);
    const obj: Record<string, string> = {};
    headers.forEach((h, idx) => {
      obj[h] = (vals[idx] ?? "").trim();
    });
    if (Object.values(obj).some((v) => v !== "")) {
      rows.push(obj);
    }
  }
  if (rows.length === 0) {
    throw new HttpError(400, "Le CSV ne contient aucune ligne exploitable.");
  }

  const id = crypto.randomBytes(6).toString("hex");
  const safe = safeName(filename || "lot.csv");
  fs.mkdirSync(CSV_DIR, { recursive: true });
  const stored = { id, file: safe, columns: headers, rows, encoding, delimiter, warnings };
  fs.writeFileSync(path.join(CSV_DIR, `${id}.json`), JSON.stringify(stored), "utf8");
  return stored;
}

export function load(csvId: string): {
  id: string;
  file: string;
  columns: string[];
  rows: Array<Record<string, string>>;
  encoding: string;
  delimiter: string;
  warnings: string[];
} {
  const clean = safeName(csvId);
  const full = path.join(CSV_DIR, `${clean}.json`);
  if (!fs.existsSync(full)) {
    throw new HttpError(404, "CSV introuvable ou expire : rechargez le fichier.");
  }
  return JSON.parse(fs.readFileSync(full, "utf8"));
}

export function preview(csvId: string, limit = 20) {
  const data = load(csvId);
  return {
    meta: { file: data.file, row_count: data.rows.length },
    columns: data.columns,
    rows: data.rows.slice(0, Math.max(1, limit)),
    encoding: data.encoding,
    delimiter: data.delimiter,
    warnings: data.warnings,
  };
}
