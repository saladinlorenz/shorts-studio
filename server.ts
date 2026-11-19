import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import express from "express";
import type { NextFunction, Request, Response } from "express";
import multer from "multer";

import * as agentActions from "./server-node/agent/actions.ts";
import * as autopilotMod from "./server-node/agent/autopilot.ts";
import * as llmMod from "./server-node/agent/llm.ts";
import * as agentProposals from "./server-node/agent/proposals.ts";
import * as agentService from "./server-node/agent/service.ts";
import * as asrMod from "./server-node/asr.ts";
import * as batchMod from "./server-node/batch.ts";
import * as brandsMod from "./server-node/brands.ts";
import * as budgets from "./server-node/budgets.ts";
import * as captionsMod from "./server-node/captions.ts";
import * as clipsMod from "./server-node/clips.ts";
import * as csvMod from "./server-node/csv_source.ts";
import * as deliveryMod from "./server-node/delivery.ts";
import * as edlMod from "./server-node/edl.ts";
import * as effectsMod from "./server-node/effects.ts";
import * as foldersMod from "./server-node/folders.ts";
import * as fontsMod from "./server-node/fonts.ts";
import { cancelJob, createJob, getJob, Job, raiseIfCancelled } from "./server-node/jobs.ts";
import * as libraryMod from "./server-node/library.ts";
import { readRecentLogs } from "./server-node/logger.ts";
import * as mediaMod from "./server-node/media.ts";
import * as mediacache from "./server-node/mediacache.ts";
import * as momentsMod from "./server-node/moments.ts";
import * as montageMod from "./server-node/montage.ts";
import * as podcastMod from "./server-node/podcast.ts";
import * as queueMod from "./server-node/queue.ts";
import * as renderMod from "./server-node/render.ts";
import { resolveProject } from "./server-node/resolve.ts";
import * as retrievalMod from "./server-node/retrieval.ts";
import * as schema from "./server-node/schema.ts";
import {
  BATCH_DIR,
  BRANDS_DIR,
  EXPORTS_DIR,
  HttpError,
  MODELS_DIR,
  PROJECTS_DIR,
  ROOT,
  TTS_MODELS_DIR,
  WEB_DIR,
  WEB_DIST,
  WEB_PUBLIC,
  checkOrigin,
  ensureDirs,
  safeName,
} from "./server-node/security.ts";
import * as settingsMod from "./server-node/settings.ts";
import * as skillsMod from "./server-node/skills.ts";
import * as sourcesMod from "./server-node/sources.ts";
import * as ttsMod from "./server-node/tts.ts";
import { validateProject } from "./server-node/validation.ts";

ensureDirs();
queueMod.recover();
retrievalMod.build(false);

const app = express();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 500 * 1024 * 1024 } });

app.use(express.json({ limit: "20mb" }));
app.use((req: Request, _res: Response, next: NextFunction) => {
  try {
    checkOrigin(req);
    next();
  } catch (err) {
    next(err);
  }
});

// Static asset mounts for Remotion & preview
app.use("/fonts", express.static(path.join(WEB_PUBLIC, "fonts")));
app.use("/media-cache", express.static(path.join(WEB_PUBLIC, "media-cache")));

function asyncHandler(fn: (req: Request, res: Response, next: NextFunction) => Promise<unknown> | unknown) {
  return (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

function projectFilePath(name: string): string {
  const clean = safeName(name);
  return path.join(PROJECTS_DIR, clean.endsWith(".json") ? clean : `${clean}.json`);
}

function publicSettings() {
  const s = settingsMod.loadSettings();
  const cfg = settingsMod.llmConfig();
  const [ready] = llmMod.isReady(cfg);
  const providerMeta = settingsMod.PROVIDERS.map((id) => ({
    id,
    label: settingsMod.PROVIDER_LABELS[id],
    is_cloud: id !== "local",
    base_url: settingsMod.CLOUD_BASE_URLS[id] || s.llm_local_base_url,
  }));
  const asrKeyConfigured = Boolean(s.asr_groq_api_key || s.groq_api_key);

  return {
    groq_configured: Boolean(s.groq_api_key || s.llm_groq_api_key),
    host: s.host,
    port: s.port,
    llm: {
      enabled: cfg.enabled,
      provider: cfg.provider,
      providers: providerMeta,
      local: {
        model: s.llm_local_model,
        key_configured: Boolean(s.llm_local_api_key),
        is_cloud: false,
        base_url: s.llm_local_base_url,
        pin_configured: Boolean(s.llm_local_pin),
      },
      gemini: {
        model: s.llm_gemini_model,
        key_configured: Boolean(s.llm_gemini_api_key),
        is_cloud: true,
        base_url: settingsMod.CLOUD_BASE_URLS.gemini,
      },
      groq: {
        model: s.llm_groq_model,
        key_configured: Boolean(s.llm_groq_api_key || s.groq_api_key),
        is_cloud: true,
        base_url: settingsMod.CLOUD_BASE_URLS.groq,
      },
      active: {
        model: cfg.model,
        key_configured: Boolean(cfg.api_key),
        is_cloud: cfg.provider !== "local",
        base_url: cfg.base_url,
        pin_configured: Boolean(cfg.pin),
      },
      base_url: cfg.base_url,
      model: cfg.model,
      key_configured: Boolean(cfg.api_key),
      pin_configured: Boolean(cfg.pin),
      is_cloud: cfg.provider !== "local",
      clips_groq_key_available: Boolean(s.groq_api_key),
      temperature: cfg.temperature,
      max_tokens: cfg.max_tokens,
      context_budget: cfg.context_budget,
      timeout: cfg.timeout,
      max_repairs: cfg.max_repairs,
      max_tool_calls: cfg.max_tool_calls,
      stream: cfg.stream,
      json_mode: cfg.json_mode,
      vision_review: cfg.vision_review,
      ready,
    },
    asr: {
      provider: s.asr_provider || "auto",
      groq_models: [...asrMod.GROQ_WHISPER_MODELS],
      model: s.asr_groq_model,
      language: s.asr_language,
      key_configured: asrKeyConfigured,
      clips_key_available: Boolean(s.groq_api_key),
      providers: asrMod.providers({ groqKeyPresent: asrKeyConfigured }),
      local_backend: asrMod.localBackend(),
    },
  };
}

// --- Health ---
app.get("/api/health", (_req, res) => {
  const s = settingsMod.loadSettings();
  res.json({
    status: "ok",
    groq_configured: Boolean(s.groq_api_key || s.llm_groq_api_key),
    web_dist: fs.existsSync(WEB_DIST),
  });
});

// --- Projects ---
app.get("/api/projects", (_req, res) => {
  if (!fs.existsSync(PROJECTS_DIR)) return res.json([]);
  const files = fs.readdirSync(PROJECTS_DIR).filter((f) => f.endsWith(".json")).sort();
  const list = files.map((f) => {
    const full = path.join(PROJECTS_DIR, f);
    const stat = fs.statSync(full);
    let version: number | null = null;
    try {
      const parsed = JSON.parse(fs.readFileSync(full, "utf8")) as Record<string, any>;
      version = typeof parsed.version === "number" ? parsed.version : null;
    } catch {
      // ignore
    }
    return {
      name: path.basename(f, ".json"),
      version,
      size: stat.size,
      modified: Math.floor(stat.mtimeMs / 1000),
    };
  });
  res.json(list);
});

app.get("/api/projects/:name", (req, res) => {
  const full = projectFilePath(String(req.params.name || ""));
  if (!fs.existsSync(full)) throw new HttpError(404, "Projet introuvable.");
  const raw = JSON.parse(fs.readFileSync(full, "utf8")) as schema.AnyRecord;
  const [migratedProj, migratedMedia] = mediaMod.migrateMediaRefs(raw);
  const [errors, warnings] = validateProject(migratedProj);
  res.json({
    name: path.basename(full, ".json"),
    project: migratedProj,
    errors,
    warnings,
    migrated_media: migratedMedia,
  });
});

app.post("/api/projects", (req, res) => {
  const name = String(req.body?.name || "").trim();
  const proj = req.body?.project;
  if (!name || !proj || typeof proj !== "object") {
    throw new HttpError(400, "Nom et contenu du projet requis.");
  }
  const clean = safeName(name.replace(/\.json$/i, ""));
  agentActions.saveProjectFile(clean, proj);
  res.json({ name: clean });
});

app.delete("/api/projects/:name", (req, res) => {
  const full = projectFilePath(String(req.params.name || ""));
  if (!fs.existsSync(full)) throw new HttpError(404, "Projet introuvable.");
  fs.unlinkSync(full);
  res.json({ deleted: path.basename(full, ".json") });
});

app.post("/api/projects/validate", (req, res) => {
  const proj = req.body?.project;
  if (!proj || typeof proj !== "object") throw new HttpError(400, "Projet invalide.");
  const [errors, warnings] = mediaMod.validateProjectRefs(proj);
  res.json({ errors, warnings });
});

// --- Studio ---
app.get("/api/studio/models", (_req, res) => {
  const models = [
    {
      id: "quote_cinematic",
      label: "Citation cinématique (9:16)",
      description: "Format vertical 1080x1920 : accroche masquée, citation mot à mot, signature.",
      version: 1,
      recommended_duration: [8, 25],
      aspect_ratios: ["9:16", "1:1"],
      editable: ["scenes", "theme", "audio", "signature", "effects"],
      limits: ["max 4 effets par cible", "duree totale 0.5-300s"],
    },
    {
      id: "quote_horizontal",
      label: "Citation horizontale (16:9)",
      description: "Format paysage 1920x1080 pour YouTube, LinkedIn et présentations.",
      version: 1,
      recommended_duration: [10, 45],
      aspect_ratios: ["16:9"],
      editable: ["scenes", "theme", "audio", "signature", "effects"],
      limits: ["max 4 effets par cible", "1920x1080 natif"],
    },
    {
      id: "quote_vertical",
      label: "Citation verticale classique (9:16)",
      description: "Disposition verticale sobre pour citations rapides.",
      version: 1,
      recommended_duration: [6, 20],
      aspect_ratios: ["9:16"],
      editable: ["scenes", "theme", "audio"],
      limits: ["compatibilite v1/v2"],
    },
  ];
  res.json({ models, default: "quote_cinematic" });
});

app.get("/api/studio/effects", (_req, res) => {
  res.json(effectsMod.manifest());
});

app.get("/api/studio/fonts", (_req, res) => {
  const families = fontsMod.families().map((f) => {
    const vars = f.weights || f.variants || [];
    return {
      id: f.id,
      css_family: f.css_family,
      label: f.label,
      role: f.role || f.category || "sans",
      license: f.license || f.licence || "OFL",
      source: f.source || "",
      retrieved: f.retrieved || "",
      weights: vars.map((v) => ({
        weight: v.weight,
        style: v.style,
        file: v.file,
        url: `/fonts/${v.file}`,
        available: fs.existsSync(path.join(fontsMod.FONTS_DIR, v.file)),
      })),
      complete: vars.length > 0 && vars.every((v) => fs.existsSync(path.join(fontsMod.FONTS_DIR, v.file))),
    };
  });
  res.json({
    families,
    missing_files: fontsMod.missingFiles(),
    catalog: fontsMod.CATALOG_PATH,
  });
});

app.get("/api/studio/default", (req, res) => {
  const model = String(req.query.model || "quote_cinematic");
  if (!(model in schema.MODELS)) {
    throw new HttpError(404, `Modele inconnu : ${model}`);
  }
  res.json({ project: schema.newProject(model) });
});

app.post("/api/studio/prepare", (req, res) => {
  const project = req.body?.project;
  if (!project || typeof project !== "object") throw new HttpError(400, "Projet manquant.");
  const [errors, warnings] = mediaMod.validateProjectRefs(project);
  if (errors.length > 0) {
    throw new HttpError(400, { message: "Projet invalide.", errors, warnings });
  }
  const resolved = renderMod.prepareForRender(project);
  const comp = renderMod.compositionIdOf(resolved);
  const assets = (resolved.resolved?.assets || []) as Array<{ kind: string; ref: string }>;
  const licences = assets
    .filter((a) => String(a.ref || "").startsWith("media://"))
    .map((a) => {
      const id = String(a.ref).slice("media://".length);
      const prov = mediaMod.provenanceOf(id);
      return {
        ref: a.ref,
        kind: a.kind,
        licence: String(prov.licence || "inconnue"),
        source: String(prov.source || ""),
        declared: Boolean(prov.declared),
      };
    });
  res.json({
    project: resolved,
    resolved: resolved.resolved,
    errors,
    warnings,
    licences,
    composition: comp,
  });
});

app.post("/api/studio/upgrade", (req, res) => {
  const raw = req.body?.project;
  if (!raw || typeof raw !== "object") throw new HttpError(400, "Projet manquant.");
  if (raw.version === 1) {
    const [proj, notes] = schema.upgradeV1ToV2(raw);
    const [errors, warnings] = validateProject(proj);
    return res.json({ project: proj, notes, errors, warnings });
  }
  const [errors, warnings] = validateProject(raw);
  res.json({ project: raw, notes: ["Projet deja en version 2."], errors, warnings });
});

app.post("/api/studio/inspect", (req, res) => {
  const proj = req.body?.project;
  if (!proj || typeof proj !== "object") throw new HttpError(400, "Projet manquant.");
  const resolved = resolveProject(proj);
  res.json({ resolved: resolved.resolved });
});

app.get("/api/studio/provenance/:mediaId", (req, res) => {
  res.json(mediaMod.provenanceOf(String(req.params.mediaId || "")));
});

app.post("/api/studio/provenance", (req, res) => {
  const mediaId = String(req.body?.media_id || "").trim();
  if (!mediaId) throw new HttpError(400, "media_id requis.");
  mediaMod.resolveMedia(mediaId);
  const cur = mediaMod.provenanceOf(mediaId);
  const next = {
    ...cur,
    id: mediaId,
    source: String(req.body?.source ?? cur.source ?? "").trim(),
    licence: String(req.body?.licence ?? cur.licence ?? "inconnue").trim(),
  };
  mediaMod.writeProvenance(mediaId, next);
  res.json({ media_id: mediaId, source: next.source, licence: next.licence });
});

// --- Library ---
app.get("/api/library", (_req, res) => {
  const raw = libraryMod.listLibrary();
  const models = raw.map((m) => ({
    id: m.id,
    builtin: m.builtin,
    label: m.label,
    description: m.description,
    model_id: m.model,
    model_version: 1,
    version: m.version,
    scenes: m.scenes,
    duration: m.duration,
    width: Number(String(m.dimensions).split("x")[0]) || 1080,
    height: Number(String(m.dimensions).split("x")[1]) || 1920,
    fps: 30,
    media_count: 0,
    modified: m.updated_at || 0,
    file: m.builtin ? null : `${m.id}.json`,
  }));
  res.json({ models, folder: "models", folder_path: MODELS_DIR });
});

app.get("/api/library/:id", (req, res) => {
  const id = String(req.params.id || "");
  res.json({ id, project: libraryMod.getProject(id) });
});

app.post("/api/library", (req, res) => {
  const out = libraryMod.saveModel(
    req.body?.project,
    String(req.body?.label || ""),
    String(req.body?.description || ""),
    req.body?.model_id ?? null,
  );
  res.json({ model: out.model, warnings: [] });
});

app.delete("/api/library/:id", (req, res) => {
  res.json(libraryMod.deleteModel(String(req.params.id || "")));
});

// --- Folders ---
app.get("/api/folders", (_req, res) => {
  const raw = foldersMod.listRoots().map((f) => ({
    id: f.id,
    name: f.name,
    path: f.path,
    kind: f.kind,
    licence: f.licence,
    added_at: f.added_at,
    present: fs.existsSync(f.path),
    imported: (f.files || []).length,
    files: (f.files || []).map((x) => ({
      rel: x.name,
      name: x.name,
      kind: x.kind,
      size: x.size,
      media_id: x.media_id,
      ref: `media://${x.media_id}`,
    })),
    last_scan: f.last_scan ? { at: f.last_scan, found: (f.files || []).length, imported: (f.files || []).length, new: 0, existing: 0, skipped: 0, interrupted: false } : null,
  }));
  res.json({
    folders: raw,
    kinds: [...foldersMod.KINDS, "any"],
    registry_path: path.join(BATCH_DIR, "folders.json"),
    limits: {
      max_files_per_folder: foldersMod.MAX_FILES_PER_FOLDER,
      max_depth: foldersMod.MAX_DEPTH,
      max_bytes: foldersMod.MAX_BYTES,
    },
  });
});

app.get("/api/folders/assets", (req, res) => {
  const kind = String(req.query.kind || "any");
  res.json({ kind, assets: foldersMod.assetsByKind(kind) });
});

app.post("/api/folders", (req, res) => {
  const entry = foldersMod.register(
    String(req.body?.path || ""),
    String(req.body?.kind || "any"),
    String(req.body?.name || ""),
    String(req.body?.licence || ""),
  );
  res.json({ ...entry, present: fs.existsSync(entry.path), imported: entry.files.length, last_scan: null });
});

app.post("/api/folders/:id/scan", (req, res) => {
  const folderId = String(req.params.id || "");
  foldersMod.getRoot(folderId);
  const job = createJob("folder_scan", (j: Job) =>
    foldersMod.scan(folderId, {
      shouldCancel: () => j.cancelled,
      onProgress: (c, t) => j.setProgress(c, t, `Scan ${c}/${t}…`),
    }),
  );
  res.json({ job_id: job.id, folder_id: folderId, status: job.status });
});

app.delete("/api/folders/:id", (req, res) => {
  const removed = foldersMod.unregister(String(req.params.id || ""));
  res.json({ id: removed.id, removed: true, note: `Dossier '${removed.name}' deconnecte.` });
});

// --- Batch ---
app.get("/api/batch/setup", (_req, res) => {
  const models = libraryMod.listLibrary();
  const assets = {
    video: foldersMod.assetsByKind("video"),
    audio: foldersMod.assetsByKind("audio"),
    image: foldersMod.assetsByKind("image"),
  };
  res.json({
    models,
    folders: foldersMod.listRoots(),
    assets,
    csv_limits: { max_rows: csvMod.MAX_ROWS, max_bytes: 5 * 1024 * 1024 },
    batch_dir: BATCH_DIR,
    policy: batchMod.POLICY,
  });
});

app.get("/api/batch/fields", (req, res) => {
  const model = String(req.query.model || "citation-cinematique");
  const template = libraryMod.getProject(model);
  res.json({ model, fields: batchMod.fillableFields(template) });
});

app.post("/api/batch/csv", upload.single("file"), (req, res) => {
  if (!req.file) throw new HttpError(400, "Fichier CSV manquant.");
  const stored = csvMod.store(req.file.buffer, req.file.originalname);
  const model = String(req.body?.model || "citation-cinematique");
  const template = libraryMod.getProject(model);
  const fields = batchMod.fillableFields(template);
  const suggested_mapping = batchMod.suggestMapping(stored.columns, fields);
  res.json({
    csv_id: stored.id,
    file: stored.file,
    columns: stored.columns,
    rows: stored.rows.slice(0, 50),
    preview: stored.rows.slice(0, 8),
    row_count: stored.rows.length,
    encoding: stored.encoding,
    delimiter: stored.delimiter,
    warnings: stored.warnings,
    fields,
    suggested_mapping,
  });
});

app.post("/api/batch/plan", (req, res) => {
  const model = String(req.body?.model || "citation-cinematique");
  const csvId = String(req.body?.csv_id || "");
  const csv = csvMod.load(csvId);
  const template = libraryMod.getProject(model);
  const assets = {
    video: foldersMod.assetsByKind("video"),
    audio: foldersMod.assetsByKind("audio"),
    image: foldersMod.assetsByKind("image"),
  };
  const plan = batchMod.buildPlan(template, csv.rows, req.body?.mapping || {}, assets, req.body?.options || {});
  res.json({
    model,
    csv_id: csvId,
    mapping: req.body?.mapping || {},
    options: req.body?.options || {},
    ...plan,
  });
});

app.post("/api/batch/line", (req, res) => {
  const model = String(req.body?.model || "citation-cinematique");
  const csv = csvMod.load(String(req.body?.csv_id || ""));
  const pos = Number(req.query.position || 1);
  const template = libraryMod.getProject(model);
  const assets = {
    video: foldersMod.assetsByKind("video"),
    audio: foldersMod.assetsByKind("audio"),
    image: foldersMod.assetsByKind("image"),
  };
  const plan = batchMod.buildPlan(template, csv.rows, req.body?.mapping || {}, assets, req.body?.options || {});
  const item = plan.items.find((i) => i.index === pos) || plan.items[0];
  if (!item) throw new HttpError(404, "Ligne introuvable.");
  res.json({ item, project: item.project });
});

app.post("/api/batch/start", (req, res) => {
  const model = String(req.body?.model || "citation-cinematique");
  const csvId = String(req.body?.csv_id || "");
  const csv = csvMod.load(csvId);
  const template = libraryMod.getProject(model);
  const assets = {
    video: foldersMod.assetsByKind("video"),
    audio: foldersMod.assetsByKind("audio"),
    image: foldersMod.assetsByKind("image"),
  };
  const plan = batchMod.buildPlan(template, csv.rows, req.body?.mapping || {}, assets, req.body?.options || {});
  const created = queueMod.createBatch(plan, {
    name: String(req.body?.name || "lot"),
    model_id: model,
    csv_id: csvId,
    mapping: req.body?.mapping || {},
    options: req.body?.options || {},
    overwrite: Boolean(req.body?.overwrite),
  });
  const started = queueMod.startBatch(String(created.id));
  res.json({
    batch: started.batch,
    job_id: started.job_id,
    plan_summary: plan.summary,
    plan_warnings: plan.warnings,
  });
});

app.get("/api/batch", (_req, res) => {
  res.json({ batches: queueMod.listBatches() });
});

app.get("/api/batch/:id", (req, res) => {
  const items = String(req.query.items || "false") === "true";
  res.json(queueMod.getBatch(String(req.params.id || ""), { items }));
});

app.post("/api/batch/:id/start", (req, res) => {
  res.json(queueMod.startBatch(String(req.params.id || "")));
});

app.post("/api/batch/:id/cancel", (req, res) => {
  res.json(queueMod.cancel(String(req.params.id || "")));
});

app.post("/api/batch/:id/retry", (req, res) => {
  const retried = queueMod.retryFailed(String(req.params.id || ""));
  const started = queueMod.startBatch(String(req.params.id || ""));
  res.json({ batch: started.batch, requeued: retried.requeued, started: started.job_id });
});

app.get("/api/batch/:id/manifest/file", (req, res) => {
  const fmt = String(req.query.format || "json");
  const out = queueMod.writeManifest(String(req.params.id || ""), fmt);
  res.download(out.manifest);
});

app.get("/api/batch/:id/file", (req, res) => {
  const pos = Number(req.query.position || 1);
  const batch = queueMod.getBatch(String(req.params.id || ""), { items: true }) as Record<string, any>;
  const item = (batch.items || []).find((i: any) => i.position === pos);
  if (!item || !item.output_path || !fs.existsSync(item.output_path)) {
    throw new HttpError(404, "Fichier video introuvable pour cette ligne.");
  }
  res.sendFile(item.output_path);
});

app.delete("/api/batch/:id", (req, res) => {
  res.json(queueMod.forgetBatch(String(req.params.id || "")));
});

// --- Media ---
app.post("/api/media/upload", upload.single("file"), (req, res) => {
  if (!req.file) throw new HttpError(400, "Fichier manquant.");
  const result = mediaMod.saveUploadedBuffer(
    req.file.buffer,
    req.file.originalname,
    req.file.mimetype,
    String(req.body?.source || ""),
    String(req.body?.licence || ""),
  );
  res.json(result);
});

app.get("/api/media/:mediaId", (req, res) => {
  const full = mediaMod.resolveMedia(String(req.params.mediaId || ""));
  res.type(mediaMod.contentTypeOf(full));
  res.sendFile(full);
});

// --- Exports & Montage ---
app.post("/api/exports", (req, res) => {
  budgets.assertNotStopped();
  const proj = req.body?.project;
  const rawName = String(req.body?.name || proj?.name || "export").trim();
  const overwrite = Boolean(req.body?.overwrite);
  if (!proj || typeof proj !== "object") throw new HttpError(400, "Projet manquant.");

  const [errs] = mediaMod.validateProjectRefs(proj);
  if (errs.length > 0) throw new HttpError(400, { message: "Projet invalide.", errors: errs });
  const outPath = mediacache.outputPath(rawName);
  if (fs.existsSync(outPath) && !overwrite) {
    throw new HttpError(409, { message: `Le fichier '${path.basename(outPath)}' existe deja.`, code: "exists" });
  }
  budgets.consumeBudget("exports", { file: path.basename(outPath) });

  const job = createJob("export", async (j: Job) => {
    const tmp = `${outPath}.part.mp4`;
    const info = await renderMod.renderProjectToMp4(j, proj, tmp);
    if (fs.existsSync(outPath) && overwrite) fs.unlinkSync(outPath);
    fs.renameSync(tmp, outPath);
    return { ...info, path: outPath, file: path.basename(outPath) };
  });
  res.json({ job_id: job.id });
});

app.get("/api/exports/:jobId", (req, res) => {
  const job = getJob(String(req.params.jobId || ""));
  if (!job) throw new HttpError(404, "Tache d'export introuvable.");
  res.json(job.snapshot());
});

app.post("/api/exports/:jobId/cancel", (req, res) => {
  const job = cancelJob(String(req.params.jobId || ""));
  if (!job) throw new HttpError(404, "Tache introuvable.");
  res.json(job.snapshot());
});

app.get("/api/exports/:jobId/file", (req, res) => {
  const job = getJob(String(req.params.jobId || ""));
  if (!job || job.status !== "done" || !job.result) {
    throw new HttpError(404, "Export non termine ou introuvable.");
  }
  const p = String((job.result as Record<string, any>).path || "");
  if (!p || !fs.existsSync(p)) throw new HttpError(404, "Fichier MP4 introuvable.");
  res.sendFile(p);
});

app.post("/api/montage/validate", (req, res) => {
  const edl = edlMod.normalize(req.body?.edl);
  const [errors, warnings] = edlMod.validate(edl, {
    mediaExists: (id) => {
      try {
        return fs.existsSync(mediaMod.resolveMedia(id));
      } catch {
        return false;
      }
    },
  });
  res.json({
    valid: errors.length === 0,
    errors,
    warnings,
    duration_seconds: edlMod.timelineDuration(edl),
    cuts: edl.cuts.length,
    edl,
  });
});

app.post("/api/montage", (req, res) => {
  budgets.assertNotStopped();
  const edl = edlMod.normalize(req.body?.edl);
  const [errors] = edlMod.validate(edl, {
    mediaExists: (id) => {
      try {
        return fs.existsSync(mediaMod.resolveMedia(id));
      } catch {
        return false;
      }
    },
  });
  if (errors.length > 0) throw new HttpError(400, { message: "EDL invalide.", errors });
  const overwrite = Boolean(req.body?.overwrite);
  const outPath = mediacache.outputPath(String(req.body?.name || edl.title || "montage"));
  if (fs.existsSync(outPath) && !overwrite) {
    throw new HttpError(409, { message: `Le fichier '${path.basename(outPath)}' existe deja.`, code: "exists" });
  }
  budgets.consumeBudget("exports", { montage: path.basename(outPath) });

  const job = createJob("montage", async (j: Job) => {
    const tmp = `${outPath}.part.mp4`;
    const info = await montageMod.renderTimeline(j, edl, tmp, {
      mediaLookup: (id) => mediaMod.resolveMedia(id),
    });
    if (fs.existsSync(outPath) && overwrite) fs.unlinkSync(outPath);
    fs.renameSync(tmp, outPath);
    return { ...info, path: outPath };
  });
  res.json({ job_id: job.id });
});

app.get("/api/montage/:jobId", (req, res) => {
  const job = getJob(String(req.params.jobId || ""));
  if (!job) throw new HttpError(404, "Montage introuvable.");
  res.json(job.snapshot());
});

app.get("/api/montage/:jobId/file", (req, res) => {
  const job = getJob(String(req.params.jobId || ""));
  if (!job || job.status !== "done" || !job.result) {
    throw new HttpError(404, "Montage non termine ou introuvable.");
  }
  const p = String((job.result as Record<string, any>).path || "");
  if (!p || !fs.existsSync(p)) throw new HttpError(404, "Fichier MP4 introuvable.");
  res.sendFile(p);
});

// --- Generic Jobs ---
app.get("/api/jobs/:jobId", (req, res) => {
  const job = getJob(String(req.params.jobId || ""));
  if (!job) throw new HttpError(404, "Tache introuvable.");
  res.json(job.snapshot());
});

app.post("/api/jobs/:jobId/cancel", (req, res) => {
  const job = cancelJob(String(req.params.jobId || ""));
  if (!job) throw new HttpError(404, "Tache introuvable.");
  res.json(job.snapshot());
});

// --- Settings & Sources ---
app.get("/api/settings", (_req, res) => {
  res.json(publicSettings());
});

app.post("/api/settings", (req, res) => {
  const updates: Record<string, unknown> = {};
  const body = (req.body || {}) as Record<string, any>;

  if (typeof body.groq_api_key === "string") updates.groq_api_key = body.groq_api_key.trim();

  if (body.llm && typeof body.llm === "object") {
    const l = body.llm as Record<string, any>;
    if (typeof l.enabled === "boolean") updates.llm_enabled = l.enabled;
    if (typeof l.provider === "string") updates.llm_provider = l.provider;
    if (typeof l.local_base_url === "string") updates.llm_local_base_url = l.local_base_url;
    if (typeof l.local_model === "string") updates.llm_local_model = l.local_model;
    if (typeof l.local_api_key === "string") updates.llm_local_api_key = l.local_api_key;
    if (typeof l.local_pin === "string") updates.llm_local_pin = l.local_pin;
    if (typeof l.gemini_model === "string") updates.llm_gemini_model = l.gemini_model;
    if (typeof l.gemini_api_key === "string") updates.llm_gemini_api_key = l.gemini_api_key;
    if (typeof l.groq_model === "string") updates.llm_groq_model = l.groq_model;
    if (typeof l.groq_api_key === "string") updates.llm_groq_api_key = l.groq_api_key;
    if (l.use_groq_clips_key) updates.llm_groq_api_key = settingsMod.getApiKey();
    if (l.clear_key) {
      const p = settingsMod.providerOf();
      updates[`llm_${p}_api_key`] = "";
    }
    for (const k of ["temperature", "max_tokens", "context_budget", "timeout", "max_repairs", "max_tool_calls", "stream", "json_mode", "vision_review"]) {
      if (l[k] !== undefined) updates[`llm_${k}`] = l[k];
    }
  }

  if (body.asr && typeof body.asr === "object") {
    const a = body.asr as Record<string, any>;
    if (typeof a.provider === "string") updates.asr_provider = a.provider;
    if (typeof a.groq_api_key === "string") updates.asr_groq_api_key = a.groq_api_key;
    if (a.clear_key) updates.asr_groq_api_key = "";
    if (typeof a.groq_model === "string") updates.asr_groq_model = a.groq_model;
    if (typeof a.language === "string") updates.asr_language = a.language;
  }

  settingsMod.saveSettings(updates);
  const pub = publicSettings();
  res.json({ groq_configured: pub.groq_configured, llm: pub.llm, asr: pub.asr });
});

app.get("/api/sources", (_req, res) => {
  res.json(sourcesMod.listSources());
});

app.post("/api/sources/:id", (req, res) => {
  const state = sourcesMod.save(String(req.params.id || ""), {
    key: req.body?.key,
    enabled: req.body?.enabled,
    clear_key: Boolean(req.body?.clear_key),
  });
  res.json({ provider: state });
});

app.post("/api/sources/:id/test", asyncHandler(async (req, res) => {
  const result = await sourcesMod.testConnection(String(req.params.id || ""));
  res.json(result);
}));

// --- Agent, Autopilot, Guardrails (P2–P9) ---
app.get("/api/agent/status", (_req, res) => {
  res.json(agentService.status());
});

app.get("/api/agent/capabilities", (_req, res) => {
  res.json(agentService.manifest());
});

app.post("/api/agent/index", (req, res) => {
  const force = String(req.query.force || "false") === "true";
  res.json(agentService.ensureIndex(force));
});

app.post("/api/agent/check", asyncHandler(async (req, res) => {
  const base = settingsMod.llmConfig();
  const body = (req.body || {}) as Record<string, any>;
  const probeCfg: settingsMod.LlmConfig = {
    ...base,
    enabled: true,
    provider: (body.provider || base.provider) as settingsMod.LlmProvider,
    base_url: body.base_url ? String(body.base_url) : base.base_url,
    model: body.model ? String(body.model) : base.model,
    api_key: body.api_key ? String(body.api_key) : base.api_key,
    pin: body.pin ? String(body.pin) : base.pin,
  };
  res.json(await llmMod.checkConnection(probeCfg));
}));

app.post("/api/agent/models", asyncHandler(async (req, res) => {
  const base = settingsMod.llmConfig();
  const body = (req.body || {}) as Record<string, any>;
  const provider = (body.provider || base.provider) as settingsMod.LlmProvider;
  const probeCfg: settingsMod.LlmConfig = {
    ...base,
    provider,
    base_url: body.base_url ? String(body.base_url) : base.base_url,
    api_key: body.api_key ? String(body.api_key) : base.api_key,
    pin: body.pin ? String(body.pin) : base.pin,
  };
  const models = await llmMod.listModels(probeCfg);
  res.json({ models, provider });
}));

app.post("/api/agent/search", (req, res) => {
  const q = String(req.body?.query || "");
  const limit = Number(req.body?.limit || 5);
  const passages = retrievalMod.search(q, limit, 4000);
  res.json({ query: q, engine: retrievalMod.status().engine, passages });
});

app.post("/api/agent/ask", (req, res) => {
  budgets.clearGlobalStop();
  const body = (req.body || {}) as Record<string, any>;
  const job = createJob("agent_ask", (j: Job) => agentService.runRequest(j, body));
  res.json({ job_id: job.id, status: job.status });
});

app.get("/api/agent/proposals/:id", (req, res) => {
  const rec = agentService.getRecord(String(req.params.id || ""));
  res.json({ proposal: agentProposals.publicView(rec) });
});

app.post("/api/agent/proposals/:id/accept", (req, res) => {
  const result = agentService.accept(
    String(req.params.id || ""),
    req.body?.project || null,
    Boolean(req.body?.rebase),
  );
  res.json(result);
});

app.post("/api/agent/proposals/:id/execute", (req, res) => {
  const job = agentService.executeProposalAction(
    String(req.params.id || ""),
    String(req.body?.confirmation || ""),
    req.body?.project || null,
    Boolean(req.body?.auto_confirm),
  );
  res.json({ job_id: job.id, status: job.status });
});

app.post("/api/agent/proposals/:id/reject", (req, res) => {
  res.json(agentService.reject(String(req.params.id || "")));
});

app.post("/api/agent/autopilot/plan", (req, res) => {
  budgets.clearGlobalStop();
  const body = (req.body || {}) as Record<string, any>;
  const job = createJob("autopilot_plan", (j: Job) =>
    agentService.runRequest(j, { ...body, mode: "autopilot" }),
  );
  res.json({ job_id: job.id, status: job.status });
});

app.post("/api/agent/autopilot/start", (req, res) => {
  const proposalId = String(req.body?.proposal_id || "");
  if (proposalId) {
    const rec = agentService.getRecord(proposalId);
    const state = autopilotMod.start(rec.raw_spec || {}, rec.autopilot || {}, proposalId);
    return res.json({ job_id: state.job_id, status: state.status });
  }
  const jobId = String(req.body?.job_id || "");
  const st = autopilotMod.status(jobId);
  res.json({ job_id: st.job_id, status: st.status });
});

app.get("/api/agent/autopilot/:jobId", (req, res) => {
  res.json(autopilotMod.status(String(req.params.jobId || "")));
});

app.post("/api/agent/autopilot/:jobId/cancel", (req, res) => {
  res.json(autopilotMod.cancel(String(req.params.jobId || "")));
});

app.get("/api/agent/autopilot/:jobId/file", (req, res) => {
  res.sendFile(autopilotMod.videoPath(String(req.params.jobId || "")));
});

app.get("/api/agent/autopilot/:jobId/format/:name", (req, res) => {
  res.sendFile(autopilotMod.formatPath(String(req.params.jobId || ""), String(req.params.name || "")));
});

// P9 Guardrails: Global Stop, Resume, Budgets & Sanitized JSONL Logs
app.post("/api/agent/stop", (req, res) => {
  const reason = String(req.body?.reason || "Arret global demande par l'utilisateur.");
  res.json({ ...budgets.triggerGlobalStop(reason), budget: budgets.getBudgetState() });
});

app.post("/api/agent/resume", (_req, res) => {
  budgets.clearGlobalStop();
  res.json({ resumed: true, budget: budgets.getBudgetState() });
});

app.get("/api/agent/budget", (_req, res) => {
  res.json(budgets.getBudgetState());
});

app.get("/api/agent/logs", (req, res) => {
  const limit = Number(req.query.limit || 50);
  res.json({ entries: readRecentLogs(limit) });
});

// --- Delivery ---
app.get("/api/delivery/:batchId", (req, res) => {
  res.json(deliveryMod.status(String(req.params.batchId || "")));
});

app.post("/api/delivery/:batchId/package", (req, res) => {
  const batchId = String(req.params.batchId || "");
  const st = deliveryMod.status(batchId);
  const job = createJob("delivery_package", (j: Job) => deliveryMod.buildPackage(batchId, j));
  res.json({ job_id: job.id, items: st.rendered });
});

app.get("/api/delivery/:batchId/package/file", (req, res) => {
  const batchId = String(req.params.batchId || "");
  const batch = queueMod.getBatch(batchId) as Record<string, any>;
  const pack = deliveryMod.packagePath(batchId, batch.name);
  if (!fs.existsSync(pack)) throw new HttpError(404, "Paquet de livraison introuvable.");
  res.download(pack);
});

// --- Brands ---
app.get("/api/brands", (_req, res) => {
  const raw = brandsMod.listBrands().map((b) => ({
    id: b.id,
    label: b.label,
    notes: b.notes,
    models: b.models || [],
    has_logo: Boolean((b.signature as any)?.media),
    has_music: false,
    theme_keys: Object.keys(b.theme || {}),
    created_at: "",
    updated_at: "",
    file: `${b.id}.json`,
  }));
  res.json({ brands: raw, folder: "brands", folder_path: BRANDS_DIR });
});

app.get("/api/brands/:id", (req, res) => {
  const id = String(req.params.id || "");
  res.json({ id, pack: brandsMod.getPack(id) });
});

app.post("/api/brands", (req, res) => {
  const out = brandsMod.saveBrand(req.body?.pack || {}, req.body?.brand_id ?? null);
  res.json({
    brand: {
      id: out.id,
      label: out.pack.label,
      notes: out.pack.notes,
      models: out.pack.models || [],
      has_logo: Boolean((out.pack.signature as Record<string, unknown>)?.media),
      has_music: Boolean((out.pack.audio as Record<string, unknown>)?.music),
      theme_keys: Object.keys(out.pack.theme || {}),
      created_at: "",
      updated_at: "",
      file: `${out.id}.json`,
    },
    warnings: out.warnings,
  });
});

app.delete("/api/brands/:id", (req, res) => {
  res.json(brandsMod.deleteBrand(String(req.params.id || "")));
});

app.post("/api/brands/:id/apply", (req, res) => {
  const out = brandsMod.applyToProject(String(req.params.id || ""), req.body?.project);
  res.json({ project: out.project, warnings: out.warnings });
});

app.post("/api/brands/capture", (req, res) => {
  const out = brandsMod.captureFromProject(
    req.body?.project,
    String(req.body?.label || ""),
    String(req.body?.notes || ""),
  );
  res.json({
    brand: {
      id: out.id,
      label: out.pack.label,
      notes: out.pack.notes,
      models: out.pack.models || [],
      has_logo: Boolean((out.pack.signature as Record<string, unknown>)?.media),
      has_music: Boolean((out.pack.audio as Record<string, unknown>)?.music),
      theme_keys: Object.keys(out.pack.theme || {}),
      created_at: "",
      updated_at: "",
      file: `${out.id}.json`,
    },
    warnings: out.warnings,
  });
});

// --- Moments ---
app.get("/api/moments/providers", (_req, res) => {
  const st = momentsMod.providersState();
  const s = settingsMod.loadSettings();
  res.json({
    providers: st.providers,
    local_backend: st.local_backend,
    asr_key_configured: Boolean(s.asr_groq_api_key),
    clips_key_configured: Boolean(s.groq_api_key),
    default_provider: st.provider,
    default_model: s.asr_groq_model,
    language: s.asr_language,
    duration_presets: {
      short: { label: "Tres court (8-20s)", min_seconds: 8, max_seconds: 20 },
      standard: { label: "Standard (15-45s)", min_seconds: 15, max_seconds: 45 },
      deep: { label: "Developpe (30-60s)", min_seconds: 30, max_seconds: 60 },
    },
    top_default: 5,
  });
});

app.get("/api/moments", (_req, res) => {
  res.json({ analyses: momentsMod.listAnalyses() });
});

app.get("/api/moments/:id", (req, res) => {
  res.json(momentsMod.getAnalysis(String(req.params.id || "")));
});

app.post("/api/moments/analyze", (req, res) => {
  const job = momentsMod.analyzeCreateJob(String(req.body?.source || ""), req.body || {});
  res.json({ job_id: job.id, status: job.status });
});

app.post("/api/moments/:id/recompute", (req, res) => {
  const doc = momentsMod.recompute(String(req.params.id || ""), req.body || {});
  res.json({ analysis: doc, moments: doc.moments || [], energy_used: false });
});

app.post("/api/moments/:id/generate", (req, res) => {
  const out = momentsMod.generateProject(String(req.params.id || ""), String(req.body?.moment_id || ""), req.body || {});
  res.json(out);
});

app.delete("/api/moments/:id", (req, res) => {
  res.json(momentsMod.deleteAnalysis(String(req.params.id || "")));
});

// --- TTS ---
app.get("/api/tts/status", (_req, res) => {
  const raw = ttsMod.status(TTS_MODELS_DIR) as Record<string, any>;
  const voices = ((raw.voices || []) as Array<Record<string, any>>).map((v) => ({
    ...v,
    language_name: v.language === "fr" ? "Français" : v.language === "ar" ? "Arabe" : v.language === "en" ? "Anglais" : String(v.language || "").toUpperCase(),
    locale: v.id.split("-")[0] || v.language,
    downloaded: Boolean(v.installed),
    ready: Boolean(v.installed && raw.engines?.[v.engine]?.available),
    approx_mb: 60,
  }));
  res.json({ engines: raw.engines, voices });
});

app.post("/api/tts/download", (req, res) => {
  const voiceId = String(req.body?.voice_id || "");
  const job = createJob("tts_download", (j: Job) =>
    ttsMod.downloadVoice(voiceId, TTS_MODELS_DIR, {
      progress: (c, t, msg) => j.setProgress(c, t, msg),
      cancel: () => raiseIfCancelled(j),
    }),
  );
  res.json({ job_id: job.id, status: job.status });
});

app.post("/api/tts/generate", (req, res) => {
  const text = String(req.body?.text || "").trim();
  if (!text) throw new HttpError(400, "Texte manquant.");
  const voiceId = String(req.body?.voice_id || "");
  const speed = Number(req.body?.speed || 1.0);
  const job = createJob("tts_generate", async (j: Job) => {
    const tmpWav = path.join(EXPORTS_DIR, `_tts_${crypto.randomBytes(5).toString("hex")}.wav`);
    fs.mkdirSync(EXPORTS_DIR, { recursive: true });
    try {
      const resTts = await ttsMod.synthesize(text, voiceId, TTS_MODELS_DIR, tmpWav, {
        speed,
        progress: (c, t, msg) => j.setProgress(c, t, msg),
        cancel: () => raiseIfCancelled(j),
      });
      const mediaId = mediaMod.importFileToMedia(tmpWav, `tts:${voiceId}`, "Piper TTS");
      const words = captionsMod.alignScriptToWav(text, tmpWav, resTts.duration);
      const cues = captionsMod.wrapWords(words, { rtl: fontsMod.containsArabic(text) });
      return {
        media_id: mediaId,
        ref: `media://${mediaId}`,
        url: `/api/media/${mediaId}`,
        duration: resTts.duration,
        sample_rate: resTts.sample_rate,
        voice: resTts.voice,
        engine: resTts.engine,
        cues,
      };
    } finally {
      if (fs.existsSync(tmpWav)) fs.unlinkSync(tmpWav);
    }
  });
  res.json({ job_id: job.id, status: job.status });
});

// --- Skills / Clips / Podcast ---
app.get("/api/skills", (_req, res) => {
  res.json({ skills: skillsMod.listSkills(), provenance: skillsMod.provenance() });
});

app.get("/api/skills/:id", (req, res) => {
  const sk = skillsMod.findSkill(String(req.params.id || ""));
  res.json({ skill: sk, doc: skillsMod.readDocument(sk.entry) });
});

app.get("/api/clips", (_req, res) => {
  res.json({ yt_dlp: clipsMod.hasYtDlp(), sessions: clipsMod.listSessions() });
});

app.get("/api/podcast/stats", (_req, res) => {
  res.json(podcastMod.stats());
});

// JSON API error middleware (always { detail })
app.use("/api", (err: unknown, _req: Request, res: Response, _next: NextFunction) => {
  if (err instanceof HttpError) {
    res.status(err.status).json({ detail: err.detail });
    return;
  }
  const msg = err instanceof Error ? err.message : String(err);
  res.status(500).json({ detail: msg });
});

async function startServer() {
  const isProd = process.env.NODE_ENV === "production";
  if (!isProd) {
    const { createServer: createViteServer } = await import("vite");
    const vite = await createViteServer({
      configFile: path.join(WEB_DIR, "vite.config.ts"),
      server: { middlewareMode: true, hmr: false },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else if (fs.existsSync(WEB_DIST)) {
    app.use(express.static(WEB_DIST));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(WEB_DIST, "index.html"));
    });
  }

  const port = Number(process.env.DEFAULT_APP_PORT) || 3000;
  app.listen(port, "0.0.0.0", () => {
    console.log(`Studio Video server listening on http://0.0.0.0:${port} (root: ${ROOT})`);
  });
}

startServer().catch((err) => {
  console.error("Failed to start server:", err);
  process.exit(1);
});
