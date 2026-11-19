import fs from "node:fs";
import path from "node:path";
import { PODCAST_DIR } from "./security.ts";

export function stats() {
  const catalogPath = path.join(PODCAST_DIR, "catalog.csv");
  if (!fs.existsSync(catalogPath)) {
    return {
      total_clips: 0,
      speakers: [],
      speaker_count: 0,
      folder: path.basename(PODCAST_DIR),
      legacy: { exists: false, total_clips: 0, speakers: 0 },
    };
  }
  const lines = fs.readFileSync(catalogPath, "utf8").trim().split("\n").slice(1);
  return {
    total_clips: lines.length,
    speakers: [],
    speaker_count: 0,
    folder: path.basename(PODCAST_DIR),
    legacy: { exists: false, total_clips: 0, speakers: 0 },
  };
}

export function searchClips() {
  return { total: 0, shown: 0, clips: [] };
}
