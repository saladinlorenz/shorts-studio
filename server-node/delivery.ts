import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import AdmZip from "adm-zip";
import { toSrt, type SubtitleCue } from "./captions.ts";
import { Job, raiseIfCancelled } from "./jobs.ts";
import * as queueMod from "./queue.ts";
import { resolveProject } from "./resolve.ts";
import * as schema from "./schema.ts";
import { DELIVERIES_DIR, HttpError, assertLocalDir, safeName } from "./security.ts";

const execFileAsync = promisify(execFile);
const RUNNING = new Set<string>();

function stemOf(batchId: string, name: string): string {
  return `${batchId}-${safeName(name || "lot")}`;
}

export function packagePath(batchId: string, name = ""): string {
  return assertLocalDir(path.join(DELIVERIES_DIR, `${stemOf(batchId, name)}.zip`));
}

export function srtFromProject(project: schema.AnyRecord): string {
  const resolved = project.resolved || resolveProject(project).resolved;
  const fps = Number(resolved.fps || 30);
  const cues: SubtitleCue[] = [];
  for (const sc of (resolved.scenes || []) as schema.AnyRecord[]) {
    const startSec = Number(sc.start_frame || 0) / fps;
    const endSec = Number(sc.end_frame || 0) / fps;
    const texts = (sc.layers || [])
      .filter((l: schema.AnyRecord) => l.type === "text" && String(l.text || "").trim())
      .map((l: schema.AnyRecord) => String(l.text).trim());
    if (texts.length > 0 && endSec > startSec) {
      cues.push({ start: startSec, end: endSec, text: texts.join("\n") });
    }
  }
  return cues.length > 0 ? toSrt(cues) : "";
}

export async function makeThumbnail(mp4Path: string, outPng: string, ratio = 0.45): Promise<boolean> {
  try {
    await execFileAsync(
      "ffmpeg",
      ["-hide_banner", "-y", "-ss", String(Math.max(0.2, ratio * 5)), "-i", mp4Path, "-vframes", "1", outPng],
      { timeout: 15_000 },
    );
    return fs.existsSync(outPng) && fs.statSync(outPng).size > 0;
  } catch {
    return false;
  }
}

export function status(batchId: string) {
  const batch = queueMod.getBatch(batchId, { items: true }) as Record<string, any>;
  const items = (batch.items || []) as Array<Record<string, any>>;
  const pack = packagePath(batchId, batch.name);
  const packExists = fs.existsSync(pack);
  return {
    batch: {
      id: batch.id,
      name: batch.name,
      model_id: batch.model_id || "",
      status: batch.status,
      counters: batch.counters || {},
    },
    total: items.length,
    rendered: items.filter((i) => i.status === "done" && i.output_path && fs.existsSync(i.output_path)).length,
    is_packaging: RUNNING.has(batchId),
    package: packExists
      ? {
          file: path.basename(pack),
          bytes: fs.statSync(pack).size,
          modified_at: fs.statSync(pack).mtime.toISOString(),
        }
      : null,
    items: items.map((i) => ({
      position: i.position,
      nom: i.name || "",
      fichier: safeName(String(i.filename || "video.mp4")),
      statut: i.status,
      duree_s: i.duration || 0,
      octets: i.size_bytes || 0,
      rendered: i.status === "done" && Boolean(i.output_path) && fs.existsSync(i.output_path),
    })),
  };
}

export async function buildPackage(batchId: string, job?: Job): Promise<Record<string, unknown>> {
  if (RUNNING.has(batchId)) {
    throw new HttpError(409, "Un paquet de livraison est deja en cours pour ce lot.");
  }
  RUNNING.add(batchId);
  const staging = path.join(DELIVERIES_DIR, "_tmp", batchId);
  try {
    const batch = queueMod.getBatch(batchId, { items: true }) as Record<string, any>;
    const items = ((batch.items || []) as Array<Record<string, any>>).filter(
      (i) => i.status === "done" && i.output_path && fs.existsSync(i.output_path),
    );
    if (items.length === 0) {
      throw new HttpError(400, "Aucune video rendue dans ce lot : rien a livrer.");
    }
    fs.mkdirSync(DELIVERIES_DIR, { recursive: true });
    fs.mkdirSync(staging, { recursive: true });

    const zip = new AdmZip();
    let videos = 0;
    let subtitles = 0;
    let thumbnails = 0;
    let metadata = 0;

    for (let idx = 0; idx < items.length; idx++) {
      if (job) {
        raiseIfCancelled(job);
        job.setProgress(idx, items.length, `Livraison ${idx + 1}/${items.length}…`);
      }
      const item = items[idx];
      const mp4 = String(item.output_path);
      const base = path.basename(mp4, ".mp4");
      zip.addLocalFile(mp4, "videos");
      videos += 1;

      const srt = srtFromProject(item.project || {});
      if (srt) {
        zip.addFile(`subtitles/${base}.srt`, Buffer.from(srt, "utf8"));
        subtitles += 1;
      }

      const png = path.join(staging, `${base}.png`);
      if (await makeThumbnail(mp4, png)) {
        zip.addLocalFile(png, "thumbnails");
        thumbnails += 1;
      }

      if (item.project?.publish) {
        zip.addFile(
          `metadata/${base}.json`,
          Buffer.from(JSON.stringify(item.project.publish, null, 2), "utf8"),
        );
        metadata += 1;
      }
    }

    const pack = packagePath(batchId, batch.name);
    zip.writeZip(pack);
    if (job) job.setProgress(items.length, items.length, "Paquet pret.");
    return {
      package: pack,
      file: path.basename(pack),
      bytes: fs.statSync(pack).size,
      videos,
      subtitles,
      thumbnails,
      metadata,
    };
  } finally {
    RUNNING.delete(batchId);
    try { fs.rmSync(staging, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}
