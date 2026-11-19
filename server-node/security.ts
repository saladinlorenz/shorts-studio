import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import type { Request } from "express";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, "..");

export const WEB_DIR = path.join(ROOT, "web");
export const WEB_DIST = path.join(WEB_DIR, "dist");
export const WEB_PUBLIC = path.join(WEB_DIR, "public");

export const PROJECTS_DIR = path.join(ROOT, "projects");
export const MODELS_DIR = path.join(ROOT, "models");
export const MEDIA_DIR = path.join(ROOT, "media");
export const EXPORTS_DIR = path.join(ROOT, "exports");
export const DOWNLOADS_DIR = path.join(ROOT, "downloads");
export const CLIPS_DIR = path.join(ROOT, "clips");
export const PODCAST_DIR = path.join(ROOT, "podcast_db");
export const SKILLS_DIR = path.join(ROOT, "skills", "remotion");
export const MONTAGE_DIR = path.join(ROOT, "skills", "montage");
export const BATCH_DIR = path.join(ROOT, "batch");
export const DELIVERIES_DIR = path.join(BATCH_DIR, "deliveries");
export const BRANDS_DIR = path.join(ROOT, "brands");
export const MOMENTS_DIR = path.join(ROOT, "moments");
export const KNOWLEDGE_DIR = path.join(ROOT, "knowledge");
export const TTS_MODELS_DIR = path.join(ROOT, "tts_models");
export const LOGS_DIR = path.join(ROOT, "logs");

export const ALLOWED_DIRS: readonly string[] = [
  PROJECTS_DIR,
  MODELS_DIR,
  MEDIA_DIR,
  EXPORTS_DIR,
  DOWNLOADS_DIR,
  CLIPS_DIR,
  PODCAST_DIR,
  SKILLS_DIR,
  MONTAGE_DIR,
  BATCH_DIR,
  BRANDS_DIR,
  MOMENTS_DIR,
  KNOWLEDGE_DIR,
  TTS_MODELS_DIR,
  LOGS_DIR,
];

export class HttpError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

export function ensureDirs(): void {
  for (const dir of ALLOWED_DIRS) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.mkdirSync(DELIVERIES_DIR, { recursive: true });
}

export function assertLocalDir(targetPath: string): string {
  const resolved = path.resolve(targetPath);
  for (const allowed of ALLOWED_DIRS) {
    const base = path.resolve(allowed);
    if (resolved === base || resolved.startsWith(base + path.sep)) {
      return resolved;
    }
  }
  throw new HttpError(400, "Chemin hors des emplacements autorises.");
}

export function safeName(name: string): string {
  const cleaned = path.basename(String(name ?? "")).trim();
  if (!cleaned || cleaned === "." || cleaned === "..") {
    throw new HttpError(400, "Nom de fichier invalide.");
  }
  let sanitized = cleaned;
  for (const ch of '<>:"/\\|?*') {
    sanitized = sanitized.split(ch).join("_");
  }
  return sanitized.slice(0, 120);
}

export function isLoopbackHost(host: string): boolean {
  const clean = host.toLowerCase();
  if (clean === "127.0.0.1" || clean === "localhost" || clean === "::1" || clean === "[::1]") {
    return true;
  }
  const parts = clean.split(".");
  return parts.length === 4 && parts[0] === "127" && parts.every((p) => /^\d+$/.test(p));
}

export function checkOrigin(req: Request): void {
  if (!["POST", "PUT", "DELETE", "PATCH"].includes(req.method.toUpperCase())) {
    return;
  }
  const origin = req.headers.origin;
  if (!origin) return;

  try {
    const parsed = new URL(origin);
    const reqHost = String(req.headers.host || "").split(":")[0];
    if (
      isLoopbackHost(parsed.hostname) ||
      parsed.hostname === reqHost ||
      parsed.hostname.endsWith(".run.app") ||
      parsed.hostname.endsWith(".web.app") ||
      parsed.hostname.endsWith(".googleusercontent.com")
    ) {
      return;
    }
  } catch {
    throw new HttpError(403, "Origine invalide.");
  }
  throw new HttpError(403, "Origine non autorisee.");
}

export function csrfToken(): string {
  return crypto.randomBytes(24).toString("base64url");
}
