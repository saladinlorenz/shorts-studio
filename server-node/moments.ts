import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import * as asrMod from "./asr.ts";
import { createJob, Job, raiseIfCancelled } from "./jobs.ts";
import * as mediaMod from "./media.ts";
import * as schema from "./schema.ts";
import * as settingsMod from "./settings.ts";
import { HttpError, MOMENTS_DIR, PROJECTS_DIR, safeName } from "./security.ts";

function analysisPath(analysisId: string): string {
  return path.join(MOMENTS_DIR, `${safeName(analysisId)}.json`);
}

export function providersState() {
  const cfg = settingsMod.loadSettings();
  const hasAsrKey = Boolean(cfg.asr_groq_api_key || cfg.groq_api_key);
  return {
    provider: cfg.asr_provider || "auto",
    local_backend: asrMod.localBackend(),
    providers: asrMod.providers({ groqKeyPresent: hasAsrKey }),
  };
}

export function listAnalyses() {
  if (!fs.existsSync(MOMENTS_DIR)) return [];
  return fs
    .readdirSync(MOMENTS_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .reverse()
    .map((f) => {
      try {
        const d = JSON.parse(fs.readFileSync(path.join(MOMENTS_DIR, f), "utf8")) as Record<string, any>;
        return {
          id: d.id,
          source: d.source,
          language: d.language || "",
          created_at: d.created_at,
          moments_count: Array.isArray(d.moments) ? d.moments.length : 0,
        };
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

export function getAnalysis(analysisId: string) {
  const p = analysisPath(analysisId);
  if (!fs.existsSync(p)) throw new HttpError(404, "Analyse introuvable.");
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

export function deleteAnalysis(analysisId: string) {
  const p = analysisPath(analysisId);
  if (!fs.existsSync(p)) throw new HttpError(404, "Analyse introuvable.");
  fs.unlinkSync(p);
  return { deleted: analysisId };
}

function buildMomentsFromSegments(
  segments: asrMod.AsrSegment[],
  opts: { minSeconds?: number | null; maxSeconds?: number | null; top?: number | null },
) {
  const minS = opts.minSeconds ?? 8;
  const maxS = opts.maxSeconds ?? 45;
  const top = opts.top ?? 5;
  const moments: Array<Record<string, unknown>> = [];

  let i = 0;
  while (i < segments.length) {
    const start = segments[i].start;
    const texts: string[] = [];
    let end = start;
    while (i < segments.length && end - start < minS) {
      texts.push(segments[i].text);
      end = segments[i].end;
      if (end - start >= maxS) break;
      i++;
    }
    const text = texts.join(" ").trim();
    if (text) {
      moments.push({
        id: `m${moments.length + 1}`,
        start: Math.round(start * 100) / 100,
        end: Math.round(end * 100) / 100,
        duration: Math.round((end - start) * 100) / 100,
        score: Math.min(100, 60 + Math.min(40, Math.round(text.length / 6))),
        text,
        title: text.slice(0, 60),
      });
    }
    if (moments.length >= top) break;
    i++;
  }
  return moments;
}

export function analyzeCreateJob(
  source: string,
  opts: {
    provider?: string;
    api_key_source?: string;
    model?: string;
    language?: string;
    min_seconds?: number | null;
    max_seconds?: number | null;
    top?: number | null;
  } = {},
) {
  if (!source || !source.startsWith("media://")) {
    throw new HttpError(400, "Source attendue sous forme media://<id>.");
  }
  const mediaId = source.slice("media://".length);
  const srcFile = mediaMod.resolveMedia(mediaId);
  const cfg = settingsMod.loadSettings();
  const apiKey = opts.api_key_source === "clips" ? cfg.groq_api_key : (cfg.asr_groq_api_key || cfg.groq_api_key);

  return createJob("moments_analyze", async (job: Job) => {
    raiseIfCancelled(job);
    job.setProgress(0.2, 1, "Transcription audio…");
    if (!apiKey) {
      throw new HttpError(400, "Cle API Groq requise pour analyser la transcription des moments.");
    }
    const result = await asrMod.transcribeWithGroq(srcFile, apiKey, {
      model: opts.model || cfg.asr_groq_model,
      language: opts.language || cfg.asr_language,
    });
    raiseIfCancelled(job);
    const moments = buildMomentsFromSegments(result.segments, {
      minSeconds: opts.min_seconds,
      maxSeconds: opts.max_seconds,
      top: opts.top,
    });
    const id = crypto.randomBytes(6).toString("hex");
    const doc = {
      id,
      source,
      language: result.language,
      provider: result.provider,
      transcript: result.text,
      segments: result.segments,
      moments,
      created_at: new Date().toISOString(),
    };
    fs.mkdirSync(MOMENTS_DIR, { recursive: true });
    fs.writeFileSync(analysisPath(id), JSON.stringify(doc, null, 2), "utf8");
    return doc;
  });
}

export function recompute(
  analysisId: string,
  opts: { min_seconds?: number | null; max_seconds?: number | null; top?: number | null },
) {
  const doc = getAnalysis(analysisId) as Record<string, any>;
  doc.moments = buildMomentsFromSegments(doc.segments || [], {
    minSeconds: opts.min_seconds,
    maxSeconds: opts.max_seconds,
    top: opts.top,
  });
  fs.writeFileSync(analysisPath(analysisId), JSON.stringify(doc, null, 2), "utf8");
  return doc;
}

export function generateProject(
  analysisId: string,
  momentId: string,
  opts: { handle?: string; source_title?: string; overwrite?: boolean } = {},
) {
  const doc = getAnalysis(analysisId) as Record<string, any>;
  const moment = (doc.moments || []).find((m: any) => m.id === momentId);
  if (!moment) throw new HttpError(404, "Moment introuvable.");
  const project = schema.newProject("quote_cinematic");
  const slugName = `moment-${analysisId}-${momentId}`;
  const outPath = path.join(PROJECTS_DIR, `${slugName}.json`);
  if (fs.existsSync(outPath) && !opts.overwrite) {
    throw new HttpError(409, { message: `Le projet '${slugName}' existe deja.`, code: "exists" });
  }
  project.name = slugName;
  project.content.scenes[1].layers[0].text = String(moment.text || "").slice(0, 180);
  if (opts.handle) project.content.signature.handle = opts.handle;
  fs.mkdirSync(PROJECTS_DIR, { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(project, null, 2), "utf8");
  return { name: slugName, project };
}
