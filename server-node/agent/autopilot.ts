import { execFile } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import * as asrMod from "../asr.ts";
import * as brollMod from "../broll.ts";
import * as budgets from "../budgets.ts";
import * as captionsMod from "../captions.ts";
import * as deliveryMod from "../delivery.ts";
import * as fontsMod from "../fonts.ts";
import { createJob, getJob, Job, JobCancelled, raiseIfCancelled } from "../jobs.ts";
import { logAgentEvent } from "../logger.ts";
import * as mediaMod from "../media.ts";
import * as probeMod from "../probe.ts";
import * as renderMod from "../render.ts";
import * as schema from "../schema.ts";
import { EXPORTS_DIR, HttpError, PROJECTS_DIR, TTS_MODELS_DIR, safeName } from "../security.ts";
import * as settingsMod from "../settings.ts";
import * as ttsMod from "../tts.ts";
import * as actionsMod from "./actions.ts";
import * as llmMod from "./llm.ts";
import * as proposalsMod from "./proposals.ts";
import * as reviewMod from "./review.ts";

const execFileAsync = promisify(execFile);
const AUTOPILOT_DIR = path.join(PROJECTS_DIR, "autopilot");

export type StepStatus = "pending" | "running" | "done" | "skipped" | "failed" | "cancelled";

export interface AutopilotStepState {
  id: string;
  label: string;
  status: StepStatus;
  message: string;
  error: string;
}

export interface AutopilotFormatArtifact {
  ratio: string;
  name: string;
  url: string;
  size_bytes: number;
  width: number;
  height: number;
}

export interface AutopilotRunState {
  job_id: string;
  proposal_id: string;
  status: "running" | "done" | "error" | "cancelled" | "interrupted";
  project_name: string;
  language: string;
  steps: AutopilotStepState[];
  voice_ref: string | null;
  video: {
    name: string;
    url: string;
    size_bytes: number | null;
    duration: number | null;
    formats?: AutopilotFormatArtifact[];
  } | null;
  qc?: Record<string, unknown> | null;
  publish?: proposalsMod.CopywritingBlock | null;
  error: string;
  resumable: boolean;
  created_at: number;
  updated_at: number;
  progress: number;
  message: string;
  video_file?: string;
  formats_dir?: string;
  spec?: Record<string, any>;
}

const RUNS = new Map<string, AutopilotRunState>();

function statePath(jobId: string): string {
  return path.join(AUTOPILOT_DIR, `${safeName(jobId)}.json`);
}

function saveState(state: AutopilotRunState): void {
  state.updated_at = Math.floor(Date.now() / 1000);
  RUNS.set(state.job_id, state);
  fs.mkdirSync(AUTOPILOT_DIR, { recursive: true });
  fs.writeFileSync(statePath(state.job_id), JSON.stringify(state, null, 2), "utf8");
}

function loadState(jobId: string): AutopilotRunState {
  const mem = RUNS.get(jobId);
  if (mem) return mem;
  const p = statePath(jobId);
  if (!fs.existsSync(p)) {
    throw new HttpError(404, `Execution autopilote introuvable : ${jobId}`);
  }
  const parsed = JSON.parse(fs.readFileSync(p, "utf8")) as AutopilotRunState;
  RUNS.set(jobId, parsed);
  return parsed;
}

budgets.onGlobalStop(() => {
  for (const state of RUNS.values()) {
    if (state.status === "running") {
      state.status = "cancelled";
      state.message = "Arret global active.";
      for (const st of state.steps) {
        if (st.status === "running" || st.status === "pending") {
          st.status = "cancelled";
          st.message = "Interrompu par l'arret global.";
        }
      }
      saveState(state);
    }
  }
});

function detectLanguage(prompt: string): string {
  const low = prompt.toLowerCase();
  if (fontsMod.containsArabic(prompt) || /\b(arabe|arabic|ar)\b/i.test(low)) return "ar";
  if (/\b(anglais|english|en)\b/i.test(low)) return "en";
  if (/\b(espagnol|spanish|es)\b/i.test(low)) return "es";
  return "fr";
}

function detectAspect(prompt: string): "9:16" | "16:9" | "1:1" {
  const low = prompt.toLowerCase();
  if (/16\s*:\s*9|horizontal|paysage|landscape|youtube/.test(low)) return "16:9";
  if (/1\s*:\s*1|carre|square|instagram/.test(low)) return "1:1";
  return "9:16";
}

export async function planSpec(
  message: string,
  history: Array<{ role: string; content: string }> = [],
): Promise<{
  spec: Record<string, any>;
  plan: Record<string, unknown>;
  sources: Array<Record<string, unknown>>;
}> {
  budgets.assertNotStopped();
  const prompt = String(message || "").trim();
  if (!prompt) throw new HttpError(400, "Decrivez la video a produire.");

  const lang = detectLanguage(prompt);
  const aspect = detectAspect(prompt);
  const cfg = settingsMod.llmConfig();
  const [ready] = llmMod.isReady(cfg);

  let spec: Record<string, any> | null = null;
  if (ready) {
    try {
      const sys = [
        "Tu planifies un short video Studio. Reponds uniquement en JSON strict :",
        '{"language":"fr|en|ar","aspect":"9:16|16:9|1:1","hook":"...","hook_caption":"...","quote":"...","author":"— ...","reveal":"...","reveal_note":"...","use_voice":true,"use_broll":true,"run_qc":true,"deliver_formats":["1:1"],"copywriting":{"title":"...","description":"...","hashtags":["#..."],"hook_lines":["..."],"cta":"...","language":"fr"}}',
        `Respecte la langue demandee (${lang}) et le format (${aspect}).`,
      ].join("\n");
      const conv = [
        { role: "system" as const, content: sys },
        ...history.slice(-4).map((m) => ({
          role: (m.role === "assistant" ? "assistant" : "user") as "user" | "assistant",
          content: m.content,
        })),
        { role: "user" as const, content: prompt },
      ];
      const res = await llmMod.chatCompletion(cfg, conv, { jsonMode: true, maxTokens: 700, temperature: 0.4 });
      spec = JSON.parse(res.content) as Record<string, any>;
    } catch {
      spec = null;
    }
  }

  if (!spec) {
    const clean = prompt.replace(/\s+/g, " ").trim();
    const isAr = lang === "ar";
    const isEn = lang === "en";
    spec = {
      language: lang,
      aspect,
      hook: clean.slice(0, 64),
      hook_caption: aspect === "16:9" ? "16:9 · EDITION STUDIO" : isAr ? "مقطع قصير" : isEn ? "SHORT EDITION" : "EDITION STUDIO",
      quote: clean.length > 20 ? clean.slice(0, 180) : isAr ? "الفكرة الواضحة تصنع الأثر الحقيقي." : isEn ? "Clarity turns a simple idea into lasting impact." : "Une idee claire traverse l'ecran plus vite qu'un long discours.",
      author: isAr ? "— الاستوديو" : "— Studio Video",
      reveal: isAr ? "تابع" : isEn ? "Act" : "Agir",
      reveal_note: isAr ? "تابع للمزيد" : isEn ? "Save for later" : "Enregistrer · Partager",
      use_voice: true,
      use_broll: true,
      run_qc: true,
      deliver_formats: aspect === "9:16" ? ["1:1"] : [],
    };
  }

  spec.language = String(spec.language || lang).toLowerCase().slice(0, 8);
  spec.aspect = ["9:16", "16:9", "1:1"].includes(String(spec.aspect)) ? spec.aspect : aspect;

  if (!spec.copywriting) {
    spec.copywriting = await actionsMod.generateCopywritingBlock(
      `${spec.hook || ""} — ${spec.quote || ""}`,
      spec.language,
    );
  } else {
    const [cw] = proposalsMod.validateCopywriting(spec.copywriting, spec.language);
    spec.copywriting = cw;
  }

  const pickedVoice = ttsMod.pickVoiceForLanguage(spec.language, TTS_MODELS_DIR);
  const templateId = spec.aspect === "16:9" ? "quote_horizontal" : "quote_cinematic";
  const exportName = `autopilot-${crypto.randomBytes(3).toString("hex")}`;

  const plan = {
    template_id: templateId,
    aspect: spec.aspect,
    language: spec.language,
    script: [
      { scene: "Accroche", hook: spec.hook, caption: spec.hook_caption },
      { scene: "Citation", quote: spec.quote, author: spec.author },
      { scene: "Signature", reveal: spec.reveal, note: spec.reveal_note },
    ],
    design: [
      { format: spec.aspect, font: spec.language === "ar" ? "Noto Sans Arabic (RTL)" : "Playfair Display / Inter" },
    ],
    voice: spec.use_voice !== false && pickedVoice
      ? { voice_id: pickedVoice.id, speed: 1.0, text: `${spec.hook}. ${spec.quote}`, language: spec.language }
      : null,
    export: { name: exportName },
    steps: proposalsMod.AUTOPILOT_STEPS,
  };

  return { spec, plan, sources: [] };
}

async function scaleSocialFormat(
  srcMp4: string,
  destMp4: string,
  targetW: number,
  targetH: number,
): Promise<boolean> {
  try {
    await execFileAsync(
      "ffmpeg",
      [
        "-hide_banner", "-y", "-i", srcMp4,
        "-vf", `scale=${targetW}:${targetH}:force_original_aspect_ratio=decrease,pad=${targetW}:${targetH}:(ow-iw)/2:(oh-ih)/2:black`,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "copy", "-movflags", "+faststart",
        destMp4,
      ],
      { timeout: 120_000 },
    );
    return fs.existsSync(destMp4) && fs.statSync(destMp4).size > 0;
  } catch {
    return false;
  }
}

export function start(
  spec: Record<string, any>,
  plan: Record<string, any>,
  proposalId = "",
): AutopilotRunState {
  budgets.assertNotStopped();
  budgets.consumeBudget("autopilot_runs", { proposal_id: proposalId });

  const steps: AutopilotStepState[] = proposalsMod.AUTOPILOT_STEPS.map((s) => ({
    id: s.id,
    label: s.label,
    status: "pending",
    message: "",
    error: "",
  }));

  let runState!: AutopilotRunState;

  const job = createJob("autopilot", async (j: Job) => {
    runState.job_id = j.id;
    const setStep = (id: string, status: StepStatus, message = "", error = "") => {
      const st = runState.steps.find((x) => x.id === id);
      if (st) {
        st.status = status;
        st.message = message;
        st.error = error;
      }
      runState.message = message || st?.label || "";
      const finished = runState.steps.filter((x) => x.status === "done" || x.status === "skipped").length;
      runState.progress = Math.round((finished / runState.steps.length) * 1000) / 1000;
      j.setProgress(finished, runState.steps.length, runState.message);
      saveState(runState);
    };

    try {
      logAgentEvent({
        event: "autopilot_started",
        actor: "auto",
        proposal_id: proposalId,
        job_id: j.id,
        status: "running",
        detail: { language: spec.language, aspect: spec.aspect },
      });

      // 1. Script & copywriting validation
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      setStep("script", "running", "Structuration du script…");
      const [cw] = proposalsMod.validateCopywriting(
        spec.copywriting || {
          title: spec.hook || "Short Video",
          description: spec.quote || spec.hook || "Video",
          hashtags: ["#video"],
          hook_lines: [String(spec.hook || "")].filter(Boolean),
          cta: "",
          language: spec.language || "fr",
        },
        String(spec.language || "fr"),
      );
      runState.publish = cw;
      setStep("script", "done", "Script valide (3 scenes).");

      // 2. Design & format (includes P3 Arabic RTL & P6 horizontal 16:9)
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      setStep("design", "running", `Application du format ${spec.aspect || "9:16"}…`);
      const project = proposalsMod.buildAutopilotProject(spec);
      const exportName = safeName(String(plan.export?.name || `autopilot-${j.id}`));
      project.name = exportName;
      project.export.filename = exportName;
      project.publish = cw;
      runState.project_name = exportName;
      setStep("design", "done", `${project.export.width}x${project.export.height} (${project.model.id}).`);

      // 3. Conditional media/broll assignment
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      if (spec.use_broll === false) {
        setStep("media", "skipped", "B-roll desactive dans la demande.");
      } else {
        setStep("media", "running", "Recherche B-roll dans les dossiers connectes…");
        const pick = brollMod.pickMediaForScenes(project, { kind: "any" });
        if (pick.assigned === 0) {
          setStep("media", "skipped", "Aucun media compatible dans les dossiers connectes — fond du theme conserve.");
        } else {
          setStep("media", "done", `${pick.assigned} scene(s) illustrees par B-roll local.`);
        }
      }

      // 4. Conditional voice + captions + optional ASR
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      const lang = String(spec.language || "fr").toLowerCase();
      const voiceCfg = ttsMod.status(TTS_MODELS_DIR) as Record<string, any>;
      const piperAvailable = Boolean(voiceCfg?.engines?.piper?.available);
      const pickedVoice = ttsMod.pickVoiceForLanguage(lang, TTS_MODELS_DIR);
      const voiceInstalled = pickedVoice ? ttsMod.isVoiceInstalled(pickedVoice.id, TTS_MODELS_DIR) : false;

      if (spec.use_voice === false) {
        setStep("voice", "skipped", "Voix off desactivee dans la demande.");
      } else if (!piperAvailable || !pickedVoice || !voiceInstalled) {
        const why = !piperAvailable
          ? "Binaire 'piper' absent — voix off ignoree."
          : !pickedVoice
            ? `Aucune voix configuree pour '${lang}'.`
            : `Modele vocal '${pickedVoice.id}' non telecharge — voix off ignoree.`;
        setStep("voice", "skipped", why);
      } else {
        setStep("voice", "running", `Synthese vocale (${pickedVoice.label})…`);
        const fullVoiceText = `${spec.hook || ""}. ${spec.quote || ""}`.trim();
        const tmpWav = path.join(EXPORTS_DIR, `_ap_tts_${j.id}.wav`);
        try {
          const ttsRes = await ttsMod.synthesize(fullVoiceText, pickedVoice.id, TTS_MODELS_DIR, tmpWav, {
            speed: 1.0,
            cancel: () => raiseIfCancelled(j),
          });
          const mediaId = mediaMod.importFileToMedia(tmpWav, `autopilot:${pickedVoice.id}`, "Piper TTS");
          const voiceRef = `media://${mediaId}`;
          project.audio.voice = voiceRef;
          project.audio.enabled = true;
          runState.voice_ref = voiceRef;

          let timedWords = captionsMod.alignScriptToWav(fullVoiceText, tmpWav, ttsRes.duration);
          const s = settingsMod.loadSettings();
          if (spec.use_asr && (s.asr_groq_api_key || s.groq_api_key)) {
            try {
              const groqRes = await asrMod.transcribeWithGroq(tmpWav, s.asr_groq_api_key || s.groq_api_key, {
                model: s.asr_groq_model,
                language: lang,
              });
              if (groqRes.segments.length > 0) {
                timedWords = groqRes.segments.map((seg) => ({ word: seg.text, start: seg.start, end: seg.end }));
              }
            } catch {
              // Keep energy-aligned captions on ASR fallback
            }
          }
          project.audio.markers = captionsMod.wrapWords(timedWords, {
            rtl: lang === "ar" || fontsMod.containsArabic(fullVoiceText),
          });
          setStep("voice", "done", `Voix generee (${ttsRes.duration}s, ${pickedVoice.id}).`);
        } finally {
          if (fs.existsSync(tmpWav)) fs.unlinkSync(tmpWav);
        }
      }

      actionsMod.saveProjectFile(exportName, project);

      // 5. Export MP4
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      setStep("export", "running", "Rendu video MP4…");
      budgets.consumeBudget("exports", { autopilot: j.id, file: `${exportName}.mp4` });
      const outPath = path.join(EXPORTS_DIR, `${exportName}.mp4`);
      const tmpMp4 = `${outPath}.part.mp4`;
      const renderInfo = await renderMod.renderProjectToMp4(j, project, tmpMp4);
      if (fs.existsSync(outPath)) fs.unlinkSync(outPath);
      fs.renameSync(tmpMp4, outPath);
      runState.video_file = outPath;
      runState.video = {
        name: `${exportName}.mp4`,
        url: `/api/agent/autopilot/${encodeURIComponent(j.id)}/file`,
        size_bytes: Number(renderInfo.size_bytes || fs.statSync(outPath).size),
        duration: Number(renderInfo.duration || 0),
        formats: [],
      };
      setStep("export", "done", `MP4 exporte (${runState.video.duration}s).`);

      // 6. Conditional QC (DOM probe + MP4 integrity + optional vision OFF by default)
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      if (spec.run_qc === false) {
        setStep("qc", "skipped", "Controle QC desactive pour cette execution.");
      } else {
        setStep("qc", "running", "Verification QC (MP4 + sonde DOM)…");
        const mp4Check = await probeMod.checkRenderedMp4(outPath);
        const review = await reviewMod.reviewProject(j, project, { allowVision: false });
        runState.qc = { mp4: mp4Check, review };
        const warnCount = mp4Check.warnings.length + review.findings.filter((f) => f.severity === "warning").length;
        setStep(
          "qc",
          "done",
          warnCount === 0
            ? "Controle QC valide sans avertissement."
            : `Controle QC termine (${warnCount} avertissement(s)).`,
        );
      }

      // 7. Conditional Metadata & SRT
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      const srtText = deliveryMod.srtFromProject(project);
      const srtPath = path.join(EXPORTS_DIR, `${exportName}.srt`);
      if (srtText) {
        fs.writeFileSync(srtPath, srtText, "utf8");
      }
      setStep("metadata", "done", srtText ? "Metadonnees validees & sous-titres SRT generes." : "Metadonnees validees.");

      // 8. Conditional Social Delivery (derived aspect ratios + thumbnail)
      raiseIfCancelled(j);
      budgets.assertNotStopped();
      const wantedFormats = Array.isArray(spec.deliver_formats) ? spec.deliver_formats.map(String) : [];
      if (wantedFormats.length === 0) {
        setStep("delivery", "skipped", "Aucun format social derive demande.");
      } else {
        setStep("delivery", "running", "Generation des formats sociaux & miniature…");
        const fmtDir = path.join(AUTOPILOT_DIR, "formats", j.id);
        fs.mkdirSync(fmtDir, { recursive: true });
        runState.formats_dir = fmtDir;
        const formatsOut: AutopilotFormatArtifact[] = [];

        for (const ratio of wantedFormats) {
          if (ratio === spec.aspect) continue;
          const [w, h] = ratio === "1:1" ? [1080, 1080] : ratio === "16:9" ? [1920, 1080] : [1080, 1920];
          const fname = `${exportName}-${ratio.replace(":", "x")}.mp4`;
          const dest = path.join(fmtDir, fname);
          if (await scaleSocialFormat(outPath, dest, w, h)) {
            formatsOut.push({
              ratio,
              name: fname,
              url: `/api/agent/autopilot/${encodeURIComponent(j.id)}/format/${encodeURIComponent(fname)}`,
              size_bytes: fs.statSync(dest).size,
              width: w,
              height: h,
            });
          }
        }
        await deliveryMod.makeThumbnail(outPath, path.join(fmtDir, `${exportName}-thumb.png`));
        if (runState.video) runState.video.formats = formatsOut;
        setStep("delivery", formatsOut.length > 0 ? "done" : "skipped",
          formatsOut.length > 0 ? `${formatsOut.length} format(s) social genere(s).` : "Aucun format derive supplementaire requis.");
      }

      runState.status = "done";
      runState.progress = 1;
      runState.message = "Production autopilote terminee.";
      saveState(runState);
      logAgentEvent({
        event: "autopilot_completed",
        actor: "auto",
        proposal_id: proposalId,
        job_id: j.id,
        status: "done",
        detail: { project: exportName },
      });
      return runState;
    } catch (err) {
      const isCancelled = err instanceof JobCancelled || j.cancelled || budgets.isGlobalStopped();
      runState.status = isCancelled ? "cancelled" : "error";
      runState.error = err instanceof Error ? err.message : String(err);
      runState.message = isCancelled ? "Production interrompue." : runState.error;
      for (const st of runState.steps) {
        if (st.status === "running") {
          st.status = isCancelled ? "cancelled" : "failed";
          st.error = runState.error;
        }
      }
      saveState(runState);
      logAgentEvent({
        event: isCancelled ? "autopilot_cancelled" : "autopilot_failed",
        actor: "system",
        proposal_id: proposalId,
        job_id: j.id,
        status: runState.status,
        detail: { error: runState.error },
      });
      throw err;
    }
  });

  runState = {
    job_id: job.id,
    proposal_id: proposalId,
    status: "running",
    project_name: String(plan.export?.name || `autopilot-${job.id}`),
    language: String(spec.language || "fr"),
    steps,
    voice_ref: null,
    video: null,
    qc: null,
    publish: null,
    error: "",
    resumable: false,
    created_at: Math.floor(Date.now() / 1000),
    updated_at: Math.floor(Date.now() / 1000),
    progress: 0,
    message: "Initialisation autopilote…",
    spec,
  };
  saveState(runState);
  return runState;
}

export function status(jobId: string): AutopilotRunState {
  return loadState(jobId);
}

export function cancel(jobId: string): AutopilotRunState {
  const st = loadState(jobId);
  const job = getJob(jobId);
  if (job) job.cancel();
  st.status = "cancelled";
  st.message = "Annule par l'utilisateur.";
  for (const s of st.steps) {
    if (s.status === "running" || s.status === "pending") {
      s.status = "cancelled";
    }
  }
  saveState(st);
  return st;
}

export function videoPath(jobId: string): string {
  const st = loadState(jobId);
  if (!st.video_file || !fs.existsSync(st.video_file)) {
    throw new HttpError(404, "Video autopilote introuvable.");
  }
  return st.video_file;
}

export function formatPath(jobId: string, name: string): string {
  const st = loadState(jobId);
  const clean = safeName(name);
  const dir = st.formats_dir || path.join(AUTOPILOT_DIR, "formats", safeName(jobId));
  const full = path.join(dir, clean);
  if (!fs.existsSync(full)) {
    throw new HttpError(404, "Format derive introuvable.");
  }
  return full;
}
