import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { Job, JobCancelled, raiseIfCancelled } from "./jobs.ts";
import * as mediacache from "./mediacache.ts";
import { checkRenderedMp4, hasAudioStream, probeMp4 } from "./probe.ts";
import { resolveProject } from "./resolve.ts";
import * as schema from "./schema.ts";
import { EXPORTS_DIR, WEB_DIR } from "./security.ts";

const ENTRY = "src/remotion/index.tsx";
const PROGRESS_RE = /(?:Rendered|Rendering|Encoded)\s+(\d+)\s*\/\s*(\d+)/i;

export function prepareForRender(project: schema.AnyRecord): schema.AnyRecord {
  const base =
    project?.version === schema.SCHEMA_VERSION_V2 ? resolveProject(project) : schema.clone(project);
  return mediacache.toRenderUrls(base);
}

export function compositionIdOf(project: schema.AnyRecord): string {
  if (project?.version === schema.SCHEMA_VERSION_V2) {
    const modelId = String(project?.model?.id || "");
    if (!(modelId in schema.MODELS)) {
      throw new Error(`Modele inconnu pour le rendu : ${modelId}`);
    }
    return modelId.replace(/_/g, "-");
  }
  const tmpl = String(project?.template || "");
  if (!(tmpl in schema.MODELS)) {
    throw new Error(`Modele inconnu pour le rendu : ${tmpl}`);
  }
  return tmpl.replace(/_/g, "-");
}

function remotionCliPath(): string {
  const cli = path.join(WEB_DIR, "node_modules", "@remotion", "cli", "remotion-cli.js");
  if (!fs.existsSync(cli)) {
    throw new Error("Remotion CLI introuvable : executez npm install.");
  }
  return cli;
}

function runSubprocess(
  job: Job,
  command: string,
  args: string[],
  cwd: string,
  onLine?: (line: string) => void,
  timeoutMs = 300_000,
): Promise<{ code: number; output: string }> {
  return new Promise((resolve, reject) => {
    raiseIfCancelled(job);
    const proc = spawn(command, args, { cwd, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    job.resultProcess = proc;
    const lines: string[] = [];
    const timer = setTimeout(() => {
      try { proc.kill("SIGTERM"); } catch { /* ignore */ }
      reject(new Error(`Sous-processus expire apres ${Math.round(timeoutMs / 1000)}s.`));
    }, timeoutMs);

    const handleChunk = (buf: Buffer) => {
      for (const line of buf.toString("utf8").split(/\r?\n/)) {
        if (!line) continue;
        lines.push(line);
        if (lines.length > 200) lines.shift();
        onLine?.(line);
      }
      if (job.cancelled) {
        try { proc.kill("SIGTERM"); } catch { /* ignore */ }
      }
    };

    proc.stdout.on("data", handleChunk);
    proc.stderr.on("data", handleChunk);
    proc.on("error", (err) => {
      clearTimeout(timer);
      job.resultProcess = null;
      reject(err);
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      job.resultProcess = null;
      if (job.cancelled) {
        reject(new JobCancelled());
        return;
      }
      resolve({ code: code ?? 1, output: lines.join("\n") });
    });
  });
}

async function normalizeLoudness(job: Job, outPath: string): Promise<boolean> {
  if (!(await hasAudioStream(outPath))) return false;
  const parsed = path.parse(outPath);
  const temp = path.join(parsed.dir, `${parsed.name}.loudnorm.mp4`);
  try {
    const { code } = await runSubprocess(
      job,
      "ffmpeg",
      [
        "-hide_banner", "-y", "-i", outPath,
        "-c:v", "copy",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        temp,
      ],
      WEB_DIR,
      undefined,
      180_000,
    );
    if (code === 0 && fs.existsSync(temp) && fs.statSync(temp).size > 0) {
      fs.renameSync(temp, outPath);
      return true;
    }
    return false;
  } catch (err) {
    if (err instanceof JobCancelled) throw err;
    return false;
  } finally {
    if (fs.existsSync(temp)) {
      try { fs.unlinkSync(temp); } catch { /* ignore */ }
    }
  }
}

export async function renderProjectToMp4(
  job: Job,
  project: schema.AnyRecord,
  outPath: string,
): Promise<Record<string, unknown>> {
  const prepared = prepareForRender(project);
  const composition = compositionIdOf(project);
  const propsPath = mediacache.writeProps(prepared, job.id);
  let totalSeen = 0;

  try {
    const cli = remotionCliPath();
    const { code, output } = await runSubprocess(
      job,
      process.execPath,
      [cli, "render", ENTRY, composition, outPath, `--props=${propsPath}`, "--codec=h264", "--log=info"],
      WEB_DIR,
      (line) => {
        const m = PROGRESS_RE.exec(line);
        if (m) {
          const cur = Number(m[1]);
          const tot = Number(m[2]) || 1;
          totalSeen = Math.max(totalSeen, tot);
          job.setProgress(cur, tot, `Rendu ${cur}/${tot}`);
        }
      },
      600_000,
    );
    if (code !== 0 || !fs.existsSync(outPath) || fs.statSync(outPath).size === 0) {
      throw new Error(`Le rendu Remotion a echoue (code ${code}):\n${output.slice(-1500)}`);
    }
    const normalized = await normalizeLoudness(job, outPath);
    const info = await probeMp4(outPath);
    return {
      ...info,
      path: outPath,
      composition,
      frames_expected: totalSeen,
      loudness_normalized: normalized,
    };
  } finally {
    if (fs.existsSync(propsPath)) {
      try { fs.unlinkSync(propsPath); } catch { /* ignore */ }
    }
  }
}

export async function renderProjectFrames(
  job: Job,
  project: schema.AnyRecord,
  frames: number[],
  outDir: string,
  auditLayout = false,
): Promise<string[]> {
  if (!Array.isArray(frames) || frames.length < 1 || frames.length > 6) {
    throw new Error("frames doit contenir entre 1 et 6 numeros d'images entiers.");
  }
  const clean = schema.clone(project);
  delete clean.resolved;
  const prepared = prepareForRender(clean);
  const resolved = prepared.resolved || {};
  const exp = prepared.export || {};
  const width = Number(resolved.width || exp.width || 1080);
  const height = Number(resolved.height || exp.height || 1920);
  const composition = compositionIdOf(prepared);
  const scale = Math.floor(Math.min(1.0, 540 / width, 1024 / height) * 1_000_000) / 1_000_000;

  fs.mkdirSync(outDir, { recursive: true });
  const paths = frames.map((f) => path.join(outDir, `frame-${f}.png`));
  const propsPath = mediacache.writeProps(prepared, `${job.id}-frames-${crypto.randomBytes(4).toString("hex")}`);

  try {
    const cli = remotionCliPath();
    if (auditLayout) {
      if (composition !== "quote-cinematic" && composition !== "quote-vertical" && composition !== "quote-horizontal") {
        throw new Error(`Sonde DOM indisponible pour ${composition}.`);
      }
      const { code, output } = await runSubprocess(
        job,
        process.execPath,
        [path.join(WEB_DIR, "audit-layout.mjs"), propsPath, composition, outDir, JSON.stringify(frames), scale.toFixed(6)],
        WEB_DIR,
        undefined,
        180_000,
      );
      if (code !== 0) {
        throw new Error(`Sonde DOM Remotion echouee:\n${output.slice(-1200)}`);
      }
    } else {
      for (let i = 0; i < frames.length; i++) {
        const { code, output } = await runSubprocess(
          job,
          process.execPath,
          [cli, "still", ENTRY, composition, paths[i], `--frame=${frames[i]}`, `--props=${propsPath}`, `--scale=${scale.toFixed(6)}`, "--image-format=png", "--log=error"],
          WEB_DIR,
          undefined,
          120_000,
        );
        if (code !== 0) {
          throw new Error(`Rendu frame ${frames[i]} echoue:\n${output.slice(-1000)}`);
        }
        job.setProgress(i + 1, frames.length, `Frames ${frames[i]}`);
      }
    }
    return paths;
  } finally {
    if (fs.existsSync(propsPath)) {
      try { fs.unlinkSync(propsPath); } catch { /* ignore */ }
    }
  }
}

/**
 * P8 : check_render — vérifie techniquement un export MP4 existant et/ou réalise
 * une sonde DOM rapide d'un projet pour prévenir les défauts avant livraison.
 */
export async function checkRender(opts: {
  exportName?: string;
  project?: schema.AnyRecord | null;
}): Promise<Record<string, unknown>> {
  const report: Record<string, unknown> = { ok: true, warnings: [] as string[], errors: [] as string[] };
  const warnings = report.warnings as string[];
  const errors = report.errors as string[];

  if (opts.exportName) {
    const safeFile = path.basename(opts.exportName.endsWith(".mp4") ? opts.exportName : `${opts.exportName}.mp4`);
    const target = path.join(EXPORTS_DIR, safeFile);
    if (!fs.existsSync(target)) {
      errors.push(`Export introuvable : ${safeFile}`);
      report.ok = false;
    } else {
      const mp4Check = await checkRenderedMp4(target);
      report.mp4 = mp4Check;
      warnings.push(...mp4Check.warnings);
      errors.push(...mp4Check.errors);
      if (!mp4Check.ok) report.ok = false;
    }
  }

  if (opts.project && typeof opts.project === "object") {
    const resolved = resolveProject(opts.project);
    const r = resolved.resolved;
    report.resolved_summary = {
      composition_id: r.composition_id,
      width: r.width,
      height: r.height,
      fps: r.fps,
      total_frames: r.total_frames,
      duration_seconds: r.duration_seconds,
      fonts: r.fonts,
      assets_count: Array.isArray(r.assets) ? r.assets.length : 0,
    };
    const tempJob = new Job("check-render", "check_render");
    const tmpDir = path.join(EXPORTS_DIR, `_check_${crypto.randomBytes(4).toString("hex")}`);
    try {
      const mid = Math.max(0, Math.floor((r.total_frames || 30) / 2));
      const frames = [0, mid, Math.max(0, (r.total_frames || 30) - 2)];
      const uniqFrames = [...new Set(frames)];
      await renderProjectFrames(tempJob, opts.project, uniqFrames, tmpDir, true);
      const probes: Array<Record<string, unknown>> = [];
      for (const f of uniqFrames) {
        const jf = path.join(tmpDir, `frame-${f}.json`);
        if (fs.existsSync(jf)) {
          probes.push(JSON.parse(fs.readFileSync(jf, "utf8")) as Record<string, unknown>);
        }
      }
      report.dom_probes = probes;
    } catch (err) {
      warnings.push(`Sonde DOM ignoree (${err instanceof Error ? err.message.slice(0, 180) : String(err)})`);
    } finally {
      try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
    }
  }

  return report;
}

export function renderPropsPreview(project: schema.AnyRecord): schema.AnyRecord {
  return JSON.parse(JSON.stringify(prepareForRender(project))) as schema.AnyRecord;
}
