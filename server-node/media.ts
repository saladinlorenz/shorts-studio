import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import * as schema from "./schema.ts";
import { validateProject } from "./validation.ts";
import { ensureCached } from "./mediacache.ts";
import { HttpError, MEDIA_DIR, safeName } from "./security.ts";

export const PROVENANCE_DIR = path.join(MEDIA_DIR, "provenance");

const ALLOWED_EXTENSIONS = new Set([
  ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
  ".mp4", ".mov", ".webm", ".mkv",
  ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
]);

const PROJECT_MEDIA_KEYS = new Set(["media", "background_image", "logo", "music", "voice"]);

const MIME_BY_EXT: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".bmp": "image/bmp",
  ".mp4": "video/mp4",
  ".mov": "video/quicktime",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".m4a": "audio/mp4",
  ".aac": "audio/aac",
  ".ogg": "audio/ogg",
  ".flac": "audio/flac",
};

export function contentTypeOf(filename: string): string {
  const ext = path.extname(filename).toLowerCase();
  return MIME_BY_EXT[ext] || "application/octet-stream";
}

function guessExtension(filename: string, mime: string): string {
  const ext = path.extname(filename).toLowerCase();
  if (ALLOWED_EXTENSIONS.has(ext)) return ext;
  for (const [k, v] of Object.entries(MIME_BY_EXT)) {
    if (mime && v === mime.toLowerCase()) return k;
  }
  throw new HttpError(415, `Type de media non autorise : ${mime || filename}`);
}

export function writeProvenance(mediaId: string, data: Record<string, unknown>): string {
  fs.mkdirSync(PROVENANCE_DIR, { recursive: true });
  const p = path.join(PROVENANCE_DIR, `${mediaId}.json`);
  fs.writeFileSync(p, JSON.stringify(data, null, 2), "utf8");
  return p;
}

export function provenanceOf(mediaId: string): Record<string, unknown> {
  const p = path.join(PROVENANCE_DIR, `${mediaId}.json`);
  if (!fs.existsSync(p)) {
    return { id: mediaId, licence: "inconnue", declared: false };
  }
  try {
    const data = JSON.parse(fs.readFileSync(p, "utf8")) as Record<string, unknown>;
    if (!data.licence) data.licence = "inconnue";
    data.declared = true;
    return data;
  } catch {
    return { id: mediaId, licence: "inconnue", declared: false };
  }
}

export function resolveMedia(mediaId: string): string {
  if (!mediaId || /[\\/.:]/.test(mediaId)) {
    throw new HttpError(400, "Identifiant de media invalide.");
  }
  fs.mkdirSync(MEDIA_DIR, { recursive: true });
  const files = fs.readdirSync(MEDIA_DIR).filter((f) => f.startsWith(`${mediaId}.`) && !f.endsWith(".part"));
  if (files.length === 0) {
    throw new HttpError(404, "Media introuvable.");
  }
  return path.join(MEDIA_DIR, files.sort()[0]);
}

export function importFileToMedia(srcPath: string, source: string, licence = "", digest = ""): string {
  const original = safeName(path.basename(srcPath));
  const ext = guessExtension(original, contentTypeOf(original));
  const stat = fs.statSync(srcPath);
  if (stat.size === 0) throw new HttpError(400, `Fichier vide : ${original}`);
  if (stat.size > 500 * 1024 * 1024) {
    throw new HttpError(413, `Fichier trop volumineux (max 500 Mo) : ${original}`);
  }
  fs.mkdirSync(MEDIA_DIR, { recursive: true });
  const mediaId = crypto.randomBytes(16).toString("hex");
  const dest = path.join(MEDIA_DIR, `${mediaId}${ext}`);
  const bytes = fs.readFileSync(srcPath);
  fs.writeFileSync(dest, bytes);
  const hash = digest || crypto.createHash("sha256").update(bytes).digest("hex");

  writeProvenance(mediaId, {
    id: mediaId,
    filename: original,
    content_type: contentTypeOf(original),
    size: stat.size,
    source: source.trim() || "import local",
    licence: licence.trim() || "inconnue",
    content_hash: hash,
    imported_at: new Date().toISOString(),
  });
  ensureCached(mediaId);
  return mediaId;
}

export function saveUploadedBuffer(
  buffer: Buffer,
  originalName: string,
  mimeType: string,
  source = "",
  licence = "",
): Record<string, unknown> {
  if (mimeType && !mimeType.startsWith("image/") && !mimeType.startsWith("video/") && !mimeType.startsWith("audio/")) {
    throw new HttpError(415, `Type de media non autorise : ${mimeType}`);
  }
  if (!buffer || buffer.length === 0) {
    throw new HttpError(400, "Fichier vide.");
  }
  if (buffer.length > 500 * 1024 * 1024) {
    throw new HttpError(413, "Fichier trop volumineux (max 500 Mo).");
  }
  const original = safeName(originalName || "media");
  const ext = guessExtension(original, mimeType);
  fs.mkdirSync(MEDIA_DIR, { recursive: true });
  const mediaId = crypto.randomBytes(16).toString("hex");
  const dest = path.join(MEDIA_DIR, `${mediaId}${ext}`);
  fs.writeFileSync(dest, buffer);
  const hash = crypto.createHash("sha256").update(buffer).digest("hex");
  const ctype = mimeType || contentTypeOf(original);

  writeProvenance(mediaId, {
    id: mediaId,
    filename: original,
    content_type: ctype,
    size: buffer.length,
    source: source.trim() || "import local",
    licence: licence.trim() || "inconnue",
    content_hash: hash,
    imported_at: new Date().toISOString(),
  });
  ensureCached(mediaId);
  return {
    id: mediaId,
    url: `/api/media/${mediaId}`,
    render_url: `/media-cache/${mediaId}${ext}`,
    filename: original,
    size: buffer.length,
    content_type: ctype,
  };
}

export function mediaPathForProject(value: string): string {
  if (value.startsWith("media://")) {
    return resolveMedia(value.slice("media://".length));
  }
  return value;
}

export function validateProjectRefs(project: schema.AnyRecord): [string[], string[]] {
  const [errors, warnings] = validateProject(project);
  // Check referenced media:// ids actually exist in MEDIA_DIR
  const walk = (node: unknown, trail = ""): void => {
    if (Array.isArray(node)) {
      node.forEach((item, i) => walk(item, `${trail}[${i}]`));
      return;
    }
    if (node && typeof node === "object") {
      for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
        if (PROJECT_MEDIA_KEYS.has(k) && typeof v === "string" && v.trim()) {
          if (v.startsWith("media://")) {
            try {
              resolveMedia(v.slice("media://".length));
            } catch {
              errors.push(`${trail ? `${trail}.` : ""}${k} : media introuvable (${v}).`);
            }
          }
        } else if (v && typeof v === "object") {
          walk(v, trail ? `${trail}.${k}` : k);
        }
      }
    }
  };
  walk(project);
  return [errors, warnings];
}

export function migrateMediaRefs(project: schema.AnyRecord): [schema.AnyRecord, string[]] {
  const migrated: string[] = [];
  const cloned = schema.clone(project);
  const walk = (node: unknown, trail = ""): void => {
    if (Array.isArray(node)) {
      node.forEach((item) => walk(item, trail));
      return;
    }
    if (node && typeof node === "object") {
      const obj = node as Record<string, unknown>;
      for (const [k, v] of Object.entries(obj)) {
        if (
          PROJECT_MEDIA_KEYS.has(k) &&
          typeof v === "string" &&
          v.trim() &&
          !v.startsWith("media://") &&
          !v.startsWith("/media-cache/") &&
          !v.startsWith("http")
        ) {
          if (fs.existsSync(v) && fs.statSync(v).isFile()) {
            try {
              const id = importFileToMedia(v, `repris du projet (${trail || "content"})`);
              obj[k] = `media://${id}`;
              migrated.push(`${trail}${k} : ${path.basename(v)}`);
            } catch {
              // ignore unimportable legacy path
            }
          }
        } else if (v && typeof v === "object") {
          walk(v, Array.isArray(v) ? `${trail}${k}[].` : `${trail}${k}.`);
        }
      }
    }
  };
  walk(cloned);
  return [cloned, migrated];
}
