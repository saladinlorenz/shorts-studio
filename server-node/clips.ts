import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { DOWNLOADS_DIR, HttpError, safeName } from "./security.ts";

const SID_RE = /^[0-9a-f]{12}$/;

export function hasYtDlp(): boolean {
  try {
    execFileSync("which", ["yt-dlp"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

export function listSessions() {
  if (!fs.existsSync(DOWNLOADS_DIR)) return [];
  return fs
    .readdirSync(DOWNLOADS_DIR)
    .filter((f) => f.startsWith("session-") && f.endsWith(".json"))
    .map((f) => {
      try {
        const d = JSON.parse(fs.readFileSync(path.join(DOWNLOADS_DIR, f), "utf8")) as Record<string, any>;
        if (!SID_RE.test(String(d.id || ""))) return null;
        return {
          sid: d.id,
          title: String(d.title || "").slice(0, 120),
          video_name: d.video_name || null,
          video_exists: Boolean(d.video_name) && fs.existsSync(path.join(DOWNLOADS_DIR, safeName(String(d.video_name)))),
          created_at: d.created_at || null,
          analyzed_count: Array.isArray(d.clips) ? d.clips.length : 0,
          produced_count: Array.isArray(d.produced) ? d.produced.length : 0,
        };
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

export function getSession(sid: string) {
  if (!SID_RE.test(sid)) throw new HttpError(400, "Identifiant de session invalide.");
  const p = path.join(DOWNLOADS_DIR, `session-${sid}.json`);
  if (!fs.existsSync(p)) throw new HttpError(404, "Session introuvable.");
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

export function deleteSession(sid: string) {
  if (!SID_RE.test(sid)) throw new HttpError(400, "Identifiant de session invalide.");
  const p = path.join(DOWNLOADS_DIR, `session-${sid}.json`);
  if (!fs.existsSync(p)) throw new HttpError(404, "Session introuvable.");
  fs.unlinkSync(p);
  return { deleted: sid, removed_files: 1 };
}
