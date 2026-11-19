import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import * as mediaMod from "./media.ts";
import { BATCH_DIR, HttpError, ROOT } from "./security.ts";

export const KINDS = ["video", "audio", "image"] as const;
export const MAX_FILES_PER_FOLDER = 250;
export const MAX_DEPTH = 4;
export const MAX_BYTES = 500 * 1024 * 1024;

const EXTS_BY_KIND: Record<string, Set<string>> = {
  video: new Set([".mp4", ".mov", ".webm", ".mkv"]),
  audio: new Set([".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"]),
  image: new Set([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]),
};

const REGISTRY_PATH = path.join(BATCH_DIR, "folders.json");

export interface FolderRoot {
  id: string;
  path: string;
  name: string;
  kind: string;
  licence: string;
  added_at: string;
  last_scan: string | null;
  files: Array<{
    media_id: string;
    name: string;
    kind: string;
    size: number;
    hash: string;
    licence: string;
  }>;
}

function loadRegistry(): { folders: FolderRoot[] } {
  if (!fs.existsSync(REGISTRY_PATH)) return { folders: [] };
  try {
    const parsed = JSON.parse(fs.readFileSync(REGISTRY_PATH, "utf8")) as { folders?: FolderRoot[] };
    return { folders: Array.isArray(parsed.folders) ? parsed.folders : [] };
  } catch {
    return { folders: [] };
  }
}

function saveRegistry(data: { folders: FolderRoot[] }): void {
  fs.mkdirSync(BATCH_DIR, { recursive: true });
  fs.writeFileSync(REGISTRY_PATH, JSON.stringify(data, null, 2), "utf8");
}

function detectKind(ext: string): string | null {
  for (const [k, exts] of Object.entries(EXTS_BY_KIND)) {
    if (exts.has(ext.toLowerCase())) return k;
  }
  return null;
}

export function listRoots(): FolderRoot[] {
  return loadRegistry().folders;
}

export function getRoot(folderId: string): FolderRoot {
  const found = listRoots().find((f) => f.id === folderId);
  if (!found) throw new HttpError(404, `Dossier introuvable : ${folderId}`);
  return found;
}

export function register(rawPath: string, kind = "any", name = "", licence = ""): FolderRoot {
  const cleanedPath = String(rawPath || "").trim();
  if (!cleanedPath) throw new HttpError(400, "Chemin de dossier manquant.");
  const resolved = path.isAbsolute(cleanedPath) ? path.resolve(cleanedPath) : path.resolve(ROOT, cleanedPath);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
    throw new HttpError(400, `Dossier introuvable : ${cleanedPath}`);
  }
  const cleanKind = [...KINDS, "any"].includes(kind) ? kind : "any";
  const reg = loadRegistry();
  const existing = reg.folders.find((f) => path.resolve(f.path) === resolved);
  if (existing) return existing;

  const entry: FolderRoot = {
    id: crypto.randomBytes(6).toString("hex"),
    path: resolved,
    name: name.trim() || path.basename(resolved) || "dossier",
    kind: cleanKind,
    licence: licence.trim() || "inconnue",
    added_at: new Date().toISOString(),
    last_scan: null,
    files: [],
  };
  reg.folders.push(entry);
  saveRegistry(reg);
  return entry;
}

export function unregister(folderId: string): FolderRoot {
  const reg = loadRegistry();
  const idx = reg.folders.findIndex((f) => f.id === folderId);
  if (idx < 0) throw new HttpError(404, `Dossier introuvable : ${folderId}`);
  const [removed] = reg.folders.splice(idx, 1);
  saveRegistry(reg);
  return removed;
}

function walkFiles(dir: string, depth = 0, out: string[] = []): string[] {
  if (depth > MAX_DEPTH || out.length >= MAX_FILES_PER_FOLDER) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (out.length >= MAX_FILES_PER_FOLDER) break;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkFiles(full, depth + 1, out);
    } else if (entry.isFile()) {
      out.push(full);
    }
  }
  return out;
}

export function scan(
  folderId: string,
  opts: { shouldCancel?: () => boolean; onProgress?: (cur: number, tot: number) => void } = {},
): { summary: { imported: number; reused: number; total: number }; skipped: string[] } {
  const reg = loadRegistry();
  const root = reg.folders.find((f) => f.id === folderId);
  if (!root) throw new HttpError(404, `Dossier introuvable : ${folderId}`);
  if (!fs.existsSync(root.path) || !fs.statSync(root.path).isDirectory()) {
    throw new HttpError(400, "Le dossier configure n'existe plus sur le disque.");
  }

  const all = walkFiles(root.path);
  const byHash = new Map((root.files || []).map((f) => [f.hash, f]));
  const nextFiles = [...(root.files || [])];
  const skipped: string[] = [];
  let imported = 0;
  let reused = 0;

  all.forEach((filePath, idx) => {
    if (opts.shouldCancel && opts.shouldCancel()) return;
    opts.onProgress?.(idx + 1, all.length);
    const ext = path.extname(filePath).toLowerCase();
    const detected = detectKind(ext);
    if (!detected || (root.kind !== "any" && detected !== root.kind)) {
      skipped.push(`${path.basename(filePath)} : type non retenu`);
      return;
    }
    const stat = fs.statSync(filePath);
    if (stat.size === 0 || stat.size > MAX_BYTES) {
      skipped.push(`${path.basename(filePath)} : taille hors limites`);
      return;
    }
    const bytes = fs.readFileSync(filePath);
    const digest = crypto.createHash("sha256").update(bytes).digest("hex");
    if (byHash.has(digest)) {
      reused += 1;
      return;
    }
    try {
      const mediaId = mediaMod.importFileToMedia(filePath, `dossier: ${root.name}`, root.licence, digest);
      const item = {
        media_id: mediaId,
        name: path.basename(filePath),
        kind: detected,
        size: stat.size,
        hash: digest,
        licence: root.licence,
      };
      nextFiles.push(item);
      byHash.set(digest, item);
      imported += 1;
    } catch (err) {
      skipped.push(`${path.basename(filePath)} : ${err instanceof Error ? err.message : String(err)}`);
    }
  });

  root.files = nextFiles;
  root.last_scan = new Date().toISOString();
  saveRegistry(reg);
  return { summary: { imported, reused, total: nextFiles.length }, skipped };
}

export function assetsByKind(kind: string): Array<Record<string, unknown>> {
  const roots = listRoots();
  const seen = new Set<string>();
  const assets: Array<Record<string, unknown>> = [];
  for (const root of roots) {
    for (const f of root.files || []) {
      if (kind !== "any" && f.kind !== kind) continue;
      if (seen.has(f.media_id)) continue;
      seen.add(f.media_id);
      assets.push({
        id: f.media_id,
        ref: `media://${f.media_id}`,
        name: f.name,
        kind: f.kind,
        size: f.size,
        licence: f.licence,
        folder: root.name,
      });
    }
  }
  return assets;
}
