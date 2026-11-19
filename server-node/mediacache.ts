import fs from "node:fs";
import path from "node:path";
import { EXPORTS_DIR, MEDIA_DIR, WEB_DIR, safeName } from "./security.ts";

export const CACHE_DIRS = [
  path.join(WEB_DIR, "public", "media-cache"),
  path.join(WEB_DIR, "dist", "media-cache"),
];

const MEDIA_REF_RE = /^media:\/\/([0-9a-zA-Z_-]{4,64})$/;
const MEDIA_KEYS = new Set(["media", "background_image", "logo", "music", "voice"]);

export function mediaFile(mediaId: string): string | null {
  if (!fs.existsSync(MEDIA_DIR)) return null;
  const files = fs
    .readdirSync(MEDIA_DIR)
    .filter((f) => f.startsWith(`${mediaId}.`) && !f.endsWith(".part"))
    .sort();
  return files.length > 0 ? path.join(MEDIA_DIR, files[0]) : null;
}

export function ensureCached(mediaId: string): string | null {
  const src = mediaFile(mediaId);
  if (!src || !fs.existsSync(src)) return null;
  const ext = path.extname(src).toLowerCase();
  const name = `${mediaId}${ext}`;
  const size = fs.statSync(src).size;
  for (const dir of CACHE_DIRS) {
    fs.mkdirSync(dir, { recursive: true });
    const dest = path.join(dir, name);
    if (fs.existsSync(dest) && fs.statSync(dest).size === size) continue;
    fs.copyFileSync(src, dest);
  }
  return `/media-cache/${name}`;
}

function refToUrl(value: string): string {
  const m = MEDIA_REF_RE.exec(value.trim());
  if (!m) return value;
  const url = ensureCached(m[1]);
  return url || value;
}

function walk(node: unknown): unknown {
  if (Array.isArray(node)) return node.map((item) => walk(item));
  if (node && typeof node === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      out[k] = MEDIA_KEYS.has(k) && typeof v === "string" ? refToUrl(v) : walk(v);
    }
    return out;
  }
  return node;
}

export function toRenderUrls<T>(project: T): T {
  const cloned = JSON.parse(JSON.stringify(project)) as T;
  return walk(cloned) as T;
}

export function writeProps(resolved: unknown, jobId: string): string {
  fs.mkdirSync(EXPORTS_DIR, { recursive: true });
  const propsPath = path.join(EXPORTS_DIR, `props-${safeName(jobId)}.json`);
  fs.writeFileSync(propsPath, JSON.stringify({ project: resolved }), "utf8");
  return propsPath;
}

export function outputPath(name: string): string {
  let outName = safeName(name);
  if (!outName.toLowerCase().endsWith(".mp4")) {
    outName += ".mp4";
  }
  return path.join(EXPORTS_DIR, outName);
}
