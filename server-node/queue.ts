import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { onGlobalStop } from "./budgets.ts";
import { createJob, getJob, Job, JobCancelled, raiseIfCancelled } from "./jobs.ts";
import * as mediacache from "./mediacache.ts";
import * as mediaMod from "./media.ts";
import * as renderMod from "./render.ts";
import * as schema from "./schema.ts";
import { BATCH_DIR, HttpError, safeName } from "./security.ts";

const QUEUE_FILE = path.join(BATCH_DIR, "batches.json");
const MANIFEST_DIR = path.join(BATCH_DIR, "manifests");

interface QueueItem {
  position: number;
  name: string;
  filename: string;
  project: schema.AnyRecord;
  row_preview: Record<string, unknown>;
  assets: Array<Record<string, unknown>>;
  warnings: string[];
  sources: Record<string, unknown>;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "blocked";
  error: string;
  output_path: string;
  size_bytes: number;
  frames: number;
  duration: number;
  fps: number;
}

interface BatchRecord {
  id: string;
  name: string;
  model_id: string;
  csv_id: string;
  mapping: Record<string, string>;
  options: Record<string, unknown>;
  status: "ready" | "running" | "paused" | "done" | "cancelled";
  overwrite: boolean;
  total: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  message: string;
  items: QueueItem[];
}

const ACTIVE = new Map<string, { jobId: string; cancel: { aborted: boolean } }>();

function loadDb(): Record<string, BatchRecord> {
  if (!fs.existsSync(QUEUE_FILE)) return {};
  try {
    return JSON.parse(fs.readFileSync(QUEUE_FILE, "utf8")) as Record<string, BatchRecord>;
  } catch {
    return {};
  }
}

function saveDb(db: Record<string, BatchRecord>): void {
  fs.mkdirSync(BATCH_DIR, { recursive: true });
  fs.writeFileSync(QUEUE_FILE, JSON.stringify(db, null, 2), "utf8");
}

function computeCounters(batch: BatchRecord) {
  const counts = { total: batch.items.length, rendered: 0, queued: 0, running: 0, done: 0, failed: 0, cancelled: 0, blocked: 0, progress: 0 };
  for (const item of batch.items) {
    counts[item.status] = (counts[item.status] || 0) + 1;
  }
  counts.rendered = counts.done;
  counts.progress = counts.total > 0 ? Math.round((counts.done / counts.total) * 10000) / 10000 : 0;
  return counts;
}

export function recover(): { items_requeued: number; batches_paused: string[] } {
  const db = loadDb();
  let itemsRequeued = 0;
  const batchesPaused: string[] = [];
  for (const b of Object.values(db)) {
    if (b.status === "running") {
      b.status = "paused";
      b.message = "Reprise apres arret du serveur : relancez le lot.";
      batchesPaused.push(b.id);
    }
    for (const item of b.items) {
      if (item.status === "running") {
        item.status = "queued";
        itemsRequeued += 1;
      }
    }
  }
  if (batchesPaused.length > 0 || itemsRequeued > 0) saveDb(db);
  return { items_requeued: itemsRequeued, batches_paused: batchesPaused };
}

onGlobalStop(() => {
  for (const [batchId, entry] of ACTIVE.entries()) {
    entry.cancel.aborted = true;
    const job = getJob(entry.jobId);
    if (job) job.cancel();
    const db = loadDb();
    if (db[batchId]) {
      db[batchId].status = "cancelled";
      db[batchId].message = "Arret global active.";
      saveDb(db);
    }
  }
});

export function createBatch(
  plan: { items: Array<Record<string, any>> },
  opts: {
    name: string;
    model_id: string;
    csv_id?: string;
    mapping?: Record<string, string>;
    options?: Record<string, unknown>;
    overwrite?: boolean;
  },
) {
  const items = plan.items || [];
  if (items.length === 0) throw new HttpError(400, "Le plan ne contient aucune ligne.");
  const batchId = crypto.randomBytes(6).toString("hex");
  const db = loadDb();
  const record: BatchRecord = {
    id: batchId,
    name: String(opts.name || "lot").trim().slice(0, 80) || "lot",
    model_id: opts.model_id,
    csv_id: String(opts.csv_id || ""),
    mapping: opts.mapping || {},
    options: opts.options || {},
    status: "ready",
    overwrite: Boolean(opts.overwrite),
    total: items.length,
    created_at: new Date().toISOString(),
    started_at: null,
    finished_at: null,
    message: "",
    items: items.map((item) => {
      const errs = (item.errors as string[]) || [];
      return {
        position: Number(item.index),
        name: String(item.name || ""),
        filename: String(item.filename),
        project: item.project,
        row_preview: item.row_preview || {},
        assets: item.assets_used || [],
        warnings: item.warnings || [],
        sources: {
          background: item.background_source,
          pass: item.background_pass,
          music: item.music_source,
          music_pass: item.music_pass,
        },
        status: errs.length > 0 ? "blocked" : "queued",
        error: errs.join(" | "),
        output_path: "",
        size_bytes: 0,
        frames: 0,
        duration: 0,
        fps: 0,
      };
    }),
  };
  db[batchId] = record;
  saveDb(db);
  return getBatch(batchId);
}

export function getBatch(batchId: string, opts: { items?: boolean; status?: string } = {}) {
  const db = loadDb();
  const b = db[batchId];
  if (!b) throw new HttpError(404, "Lot introuvable.");
  const active = ACTIVE.get(batchId);
  const out: Record<string, unknown> = {
    ...b,
    counters: computeCounters(b),
    job_id: active?.jobId || "",
    is_running: Boolean(active),
  };
  if (!opts.items) {
    delete out.items;
  } else if (opts.status) {
    out.items = b.items.filter((i) => i.status === opts.status);
  }
  return out;
}

export function listBatches(limit = 30) {
  const db = loadDb();
  return Object.values(db)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, limit)
    .map((b) => {
      const copy: Record<string, unknown> = {
        ...b,
        counters: computeCounters(b),
        is_running: ACTIVE.has(b.id),
      };
      delete copy.items;
      return copy;
    });
}

export function startBatch(batchId: string) {
  const db = loadDb();
  const b = db[batchId];
  if (!b) throw new HttpError(404, "Lot introuvable.");
  const pending = b.items.filter((i) => ["queued", "failed", "cancelled"].includes(i.status));
  if (pending.length === 0) throw new HttpError(400, "Aucune ligne en attente dans ce lot.");
  if (ACTIVE.size > 0) {
    throw new HttpError(409, "Un autre lot est deja en cours de rendu.");
  }

  const cancelState = { aborted: false };
  ACTIVE.set(batchId, { jobId: "", cancel: cancelState });

  const job = createJob("batch", async (j: Job) => {
    try {
      const state = loadDb();
      const batch = state[batchId];
      batch.status = "running";
      batch.started_at = batch.started_at || new Date().toISOString();
      batch.finished_at = null;
      const todo = batch.items.filter((i) => ["queued", "failed", "cancelled"].includes(i.status));
      batch.message = `Rendu en cours (${todo.length} ligne(s))…`;
      saveDb(state);

      let done = 0;
      let failures = 0;
      for (const item of todo) {
        if (cancelState.aborted || j.cancelled) {
          item.status = "cancelled";
          item.error = "Annule.";
          continue;
        }
        done += 1;
        j.setProgress(done - 1, todo.length, `${item.filename} (${done}/${todo.length})`);
        item.status = "running";
        saveDb(state);
        try {
          const [errs] = mediaMod.validateProjectRefs(item.project);
          if (errs.length > 0) throw new Error(errs.join(" ; "));
          const outPath = mediacache.outputPath(item.filename);
          if (fs.existsSync(outPath) && !batch.overwrite) {
            throw new Error(`Le fichier existe deja : ${path.basename(outPath)}`);
          }
          const tmp = `${outPath}.part.mp4`;
          const info = await renderMod.renderProjectToMp4(j, item.project, tmp);
          if (fs.existsSync(outPath) && batch.overwrite) fs.unlinkSync(outPath);
          fs.renameSync(tmp, outPath);
          item.status = "done";
          item.output_path = outPath;
          item.size_bytes = Number(info.size_bytes || 0);
          item.frames = Number(info.frames || 0);
          item.duration = Number(info.duration || 0);
          item.fps = Number(info.fps || 30);
          item.error = "";
        } catch (err) {
          if (err instanceof JobCancelled || cancelState.aborted || j.cancelled) {
            item.status = "cancelled";
            item.error = "Interrompu.";
            done -= 1;
            break;
          }
          failures += 1;
          item.status = "failed";
          item.error = err instanceof Error ? err.message.slice(0, 600) : String(err);
        }
        batch.message = `Ligne ${done}/${todo.length} — ${failures} echec(s).`;
        saveDb(state);
        j.setProgress(done, todo.length, `${done}/${todo.length} lignes`);
      }

      batch.status = cancelState.aborted || j.cancelled ? "cancelled" : "done";
      batch.finished_at = new Date().toISOString();
      batch.message = `${done} ligne(s) sur ${todo.length} rendues, ${failures} echec(s).`;
      saveDb(state);
      raiseIfCancelled(j);
      return { rendered: done, failures, total: todo.length, counters: computeCounters(batch) };
    } finally {
      ACTIVE.delete(batchId);
    }
  });

  const entry = ACTIVE.get(batchId);
  if (entry) entry.jobId = job.id;
  return { batch: getBatch(batchId), job_id: job.id, status: job.status };
}

export function retryFailed(batchId: string) {
  const db = loadDb();
  const b = db[batchId];
  if (!b) throw new HttpError(404, "Lot introuvable.");
  let reset = 0;
  for (const item of b.items) {
    if (item.status === "failed") {
      item.status = "queued";
      item.error = "";
      reset += 1;
    }
  }
  if (reset === 0) throw new HttpError(400, "Aucune ligne en echec a relancer.");
  saveDb(db);
  return { batch: getBatch(batchId), requeued: reset };
}

export function cancel(batchId: string) {
  const active = ACTIVE.get(batchId);
  if (!active) throw new HttpError(400, "Ce lot n'est pas en cours de rendu.");
  active.cancel.aborted = true;
  const job = active.jobId ? getJob(active.jobId) : undefined;
  if (job) job.cancel();
  return { batch: getBatch(batchId), message: job?.snapshot().message || "Annulation demandee…" };
}

export function forgetBatch(batchId: string) {
  if (ACTIVE.has(batchId)) throw new HttpError(400, "Le lot est en cours : annulez-le d'abord.");
  const db = loadDb();
  if (!db[batchId]) throw new HttpError(404, "Lot introuvable.");
  delete db[batchId];
  saveDb(db);
  return { deleted: batchId };
}

export function writeManifest(batchId: string, fmt = "json") {
  const format = (fmt || "json").toLowerCase();
  if (format !== "json" && format !== "csv") {
    throw new HttpError(400, "Manifeste demande en json ou csv.");
  }
  const batch = getBatch(batchId, { items: true }) as unknown as BatchRecord & { counters: ReturnType<typeof computeCounters> };
  fs.mkdirSync(MANIFEST_DIR, { recursive: true });
  const stem = `${batchId}-${safeName(batch.name)}`;
  const dest = path.join(MANIFEST_DIR, `${stem}.${format}`);
  const rows = batch.items.map((item) => ({
    position: item.position,
    nom: item.name,
    fichier: path.basename(item.filename),
    statut: item.status,
    chemin: item.output_path || "",
    octets: item.size_bytes || 0,
    frames: item.frames || 0,
    duree_s: item.duration || 0,
    fps: item.fps || 0,
    erreurs: item.error || "",
  }));

  if (format === "json") {
    fs.writeFileSync(
      dest,
      JSON.stringify({ batch: { ...batch, items: undefined }, summary: batch.counters, rows }, null, 2),
      "utf8",
    );
  } else {
    const cols = rows.length > 0 ? Object.keys(rows[0]) : ["position"];
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc((r as Record<string, unknown>)[c])).join(","))].join("\n");
    fs.writeFileSync(dest, "\uFEFF" + csv, "utf8");
  }
  return { manifest: dest, format, rows: rows.length, summary: batch.counters };
}
