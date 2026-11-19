import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import * as brandsMod from "../brands.ts";
import * as budgets from "../budgets.ts";
import * as captionsMod from "../captions.ts";
import * as edlMod from "../edl.ts";
import * as fontsMod from "../fonts.ts";
import { createJob, Job, raiseIfCancelled } from "../jobs.ts";
import { logAgentEvent } from "../logger.ts";
import * as mediaMod from "../media.ts";
import * as mediacache from "../mediacache.ts";
import * as montageMod from "../montage.ts";
import * as renderMod from "../render.ts";
import * as schema from "../schema.ts";
import { EXPORTS_DIR, HttpError, PROJECTS_DIR, TTS_MODELS_DIR, safeName } from "../security.ts";
import * as settingsMod from "../settings.ts";
import * as stockMod from "../stock.ts";
import * as ttsMod from "../tts.ts";
import { validateProject } from "../validation.ts";
import * as llmMod from "./llm.ts";
import * as proposalsMod from "./proposals.ts";
import * as reviewMod from "./review.ts";

export interface ActionSpec {
  name: string;
  label: string;
  description: string;
  auto_confirm_eligible: boolean;
  requires_project: boolean;
}

export const ACTIONS_CATALOG: ActionSpec[] = [
  {
    name: "project_patch",
    label: "Appliquer modifications projet",
    description: "Applique des operations validees sur le projet courant.",
    auto_confirm_eligible: true,
    requires_project: true,
  },
  {
    name: "project_new",
    label: "Nouveau projet",
    description: "Cree un nouveau projet a partir d'un modele du studio (9:16 ou 16:9).",
    auto_confirm_eligible: true,
    requires_project: false,
  },
  {
    name: "project_review",
    label: "Controle qualite QC",
    description: "Audit DOM des images et passe vision optionnelle (desactivee par defaut).",
    auto_confirm_eligible: true,
    requires_project: true,
  },
  {
    name: "project_check_render",
    label: "Verification check_render",
    description: "Controle technique du rendu (images noires, audio, mise en page DOM).",
    auto_confirm_eligible: true,
    requires_project: false,
  },
  {
    name: "project_export",
    label: "Exporter MP4",
    description: "Lance le rendu MP4 complet vers exports/ (confirmation manuelle si ecrasement).",
    auto_confirm_eligible: true,
    requires_project: true,
  },
  {
    name: "montage_render",
    label: "Rendu montage EDL",
    description: "Assemble une timeline EDL fermee (vitesse, sous-titres incrustes, loudnorm).",
    auto_confirm_eligible: true,
    requires_project: false,
  },
  {
    name: "brand_apply",
    label: "Appliquer pack de marque",
    description: "Applique les couleurs, signature et musique d'un pack de marque.",
    auto_confirm_eligible: true,
    requires_project: true,
  },
  {
    name: "brand_capture",
    label: "Capturer pack de marque",
    description: "Enregistre l'identite visuelle du projet dans brands/.",
    auto_confirm_eligible: true,
    requires_project: true,
  },
  {
    name: "tts_generate",
    label: "Generer voix off",
    description: "Synthetise une piste voix off dans la langue demandee (Piper TTS).",
    auto_confirm_eligible: true,
    requires_project: false,
  },
  {
    name: "copywriting_generate",
    label: "Rediger copywriting",
    description: "Genere un bloc titre/description/hashtags/CTA valide et structure.",
    auto_confirm_eligible: true,
    requires_project: false,
  },
  {
    name: "stock_import",
    label: "Importer media stock",
    description: "Telecharge un media stock libre de droits vers la mediatheque locale.",
    auto_confirm_eligible: false,
    requires_project: false,
  },
  {
    name: "image_generate",
    label: "Generer une image (manuel)",
    description: "Generation d'image par modele externe — confirmation humaine obligatoire.",
    auto_confirm_eligible: false,
    requires_project: false,
  },
];

export function describeAction(actionName: string): ActionSpec | undefined {
  return ACTIONS_CATALOG.find((a) => a.name === actionName);
}

export async function runAction(
  job: Job,
  actionName: string,
  params: Record<string, any>,
  project: schema.AnyRecord | null,
  opts: { autoConfirm?: boolean; proposalId?: string } = {},
): Promise<Record<string, unknown>> {
  budgets.assertNotStopped();

  const actor: "auto" | "user" = opts.autoConfirm ? "auto" : "user";
  if (opts.autoConfirm) {
    const gate = budgets.canAutoConfirmAction(actionName, params);
    if (!gate.allowed) {
      logAgentEvent({
        event: "action_blocked",
        actor: "auto",
        action: actionName,
        proposal_id: opts.proposalId,
        job_id: job.id,
        status: "blocked",
        detail: { reason: gate.reason },
      });
      throw new HttpError(403, gate.reason);
    }
    budgets.consumeBudget("auto_confirms", { action: actionName, proposal_id: opts.proposalId });
  }

  logAgentEvent({
    event: "action_started",
    actor,
    action: actionName,
    proposal_id: opts.proposalId,
    job_id: job.id,
    status: "running",
    detail: params,
  });

  try {
    let result: Record<string, unknown>;

    if (actionName === "project_new") {
      const modelId = String(params.model_id || "quote_cinematic");
      const created = schema.newProject(modelId);
      if (Array.isArray(params.operations) && params.operations.length > 0) {
        const [patched, errors, warnings] = proposalsMod.applyOperations(created, params.operations);
        if (errors.length > 0) {
          throw new HttpError(400, { message: "Parametres projet invalides.", errors });
        }
        result = { action: actionName, project: patched, warnings };
      } else {
        result = { action: actionName, project: created, warnings: [] };
      }
    } else if (actionName === "project_patch") {
      if (!project) throw new HttpError(400, "Aucun projet actif pour appliquer les modifications.");
      const ops = Array.isArray(params.operations) ? params.operations : [];
      const [patched, errors, warnings] = proposalsMod.applyOperations(project, ops);
      if (errors.length > 0) {
        throw new HttpError(400, { message: "Modifications invalides.", errors });
      }
      result = { action: actionName, project: patched, warnings };
    } else if (actionName === "project_review") {
      if (!project) throw new HttpError(400, "Aucun projet actif pour le controle qualite.");
      job.setProgress(0.2, 1, "Controle QC du projet…");
      const report = await reviewMod.reviewProject(job, project, {
        allowVision: Boolean(params.allow_vision),
      });
      result = {
        action: actionName,
        verified: Boolean(report.ok),
        summary: report.summary || `QC : ${report.findings.length} observation(s)`,
        review: report,
      };
    } else if (actionName === "project_check_render") {
      job.setProgress(0.3, 1, "Verification technique du rendu (check_render)…");
      const report = await renderMod.checkRender({
        exportName: params.export_name ? String(params.export_name) : undefined,
        project: project || undefined,
      });
      const warnCount = Array.isArray(report.warnings) ? report.warnings.length : 0;
      const errCount = Array.isArray(report.errors) ? report.errors.length : 0;
      result = {
        action: actionName,
        verified: Boolean(report.ok),
        summary: report.ok
          ? `check_render valide (${warnCount} avertissement(s))`
          : `check_render : ${errCount} erreur(s), ${warnCount} avertissement(s)`,
        report,
      };
    } else if (actionName === "project_export") {
      if (!project) throw new HttpError(400, "Aucun projet actif a exporter.");
      const overwrite = Boolean(params.overwrite);
      const rawName = String(params.name || project.export?.filename || project.name || "export").trim();
      const outPath = mediacache.outputPath(rawName);
      if (fs.existsSync(outPath) && !overwrite) {
        throw new HttpError(409, `Le fichier '${path.basename(outPath)}' existe deja.`);
      }
      const [errs] = validateProject(project);
      if (errs.length > 0) throw new HttpError(400, { message: "Projet invalide.", errors: errs });
      const [refErrs] = mediaMod.validateProjectRefs(project);
      if (refErrs.length > 0) throw new HttpError(400, { message: "Medias manquants.", errors: refErrs });

      budgets.consumeBudget("exports", { action: actionName, file: path.basename(outPath) });
      const tmp = `${outPath}.part.mp4`;
      const info = await renderMod.renderProjectToMp4(job, project, tmp);
      if (fs.existsSync(outPath) && overwrite) fs.unlinkSync(outPath);
      fs.renameSync(tmp, outPath);
      result = {
        action: actionName,
        file: path.basename(outPath),
        url: `/api/exports/${encodeURIComponent(job.id)}/file`,
        info,
        output_path: outPath,
      };
    } else if (actionName === "montage_render") {
      const edl = edlMod.normalize(params.edl || {});
      const [errors] = edlMod.validate(edl, {
        mediaExists: (id) => {
          try {
            return fs.existsSync(mediaMod.resolveMedia(id));
          } catch {
            return false;
          }
        },
      });
      if (errors.length > 0) {
        throw new HttpError(400, { message: "EDL invalide.", errors });
      }
      const overwrite = Boolean(params.overwrite);
      const outPath = mediacache.outputPath(String(params.name || edl.title || "montage"));
      if (fs.existsSync(outPath) && !overwrite) {
        throw new HttpError(409, `Le fichier '${path.basename(outPath)}' existe deja.`);
      }
      budgets.consumeBudget("exports", { action: actionName, file: path.basename(outPath) });
      const tmp = `${outPath}.part.mp4`;
      const info = await montageMod.renderTimeline(job, edl, tmp, {
        mediaLookup: (id) => mediaMod.resolveMedia(id),
      });
      if (fs.existsSync(outPath) && overwrite) fs.unlinkSync(outPath);
      fs.renameSync(tmp, outPath);
      result = {
        action: actionName,
        file: path.basename(outPath),
        url: `/api/montage/${encodeURIComponent(job.id)}/file`,
        output_path: outPath,
        info,
      };
    } else if (actionName === "brand_apply") {
      if (!project) throw new HttpError(400, "Aucun projet actif.");
      const brandId = String(params.brand_id || "");
      const applied = brandsMod.applyToProject(brandId, project);
      result = { action: actionName, project: applied.project, warnings: applied.warnings };
    } else if (actionName === "brand_capture") {
      if (!project) throw new HttpError(400, "Aucun projet actif.");
      const cap = brandsMod.captureFromProject(
        project,
        String(params.label || project.name || "Ma marque"),
        String(params.notes || ""),
      );
      result = { action: actionName, brand: cap };
    } else if (actionName === "tts_generate") {
      const text = String(params.text || "").trim();
      if (!text) throw new HttpError(400, "Texte manquant pour la synthese vocale.");
      const lang = String(params.language || (fontsMod.containsArabic(text) ? "ar" : "fr")).toLowerCase();
      const picked = params.voice_id
        ? ttsMod.voiceById(String(params.voice_id))
        : ttsMod.pickVoiceForLanguage(lang, TTS_MODELS_DIR);
      if (!picked) {
        throw new HttpError(400, `Aucune voix TTS disponible pour la langue '${lang}'.`);
      }
      const speed = Math.max(0.5, Math.min(2.0, Number(params.speed || 1.0)));
      const tmpWav = path.join(EXPORTS_DIR, `_tts_${crypto.randomBytes(5).toString("hex")}.wav`);
      fs.mkdirSync(EXPORTS_DIR, { recursive: true });
      try {
        const ttsRes = await ttsMod.synthesize(text, picked.id, TTS_MODELS_DIR, tmpWav, {
          speed,
          progress: (c, t, msg) => job.setProgress(c, t, msg),
          cancel: () => raiseIfCancelled(job),
        });
        const mediaId = mediaMod.importFileToMedia(tmpWav, `tts:${picked.id}`, "Piper TTS");
        const words = captionsMod.alignScriptToWav(text, tmpWav, ttsRes.duration);
        const cues = captionsMod.wrapWords(words, { rtl: lang === "ar" || fontsMod.containsArabic(text) });
        result = {
          action: actionName,
          voice_id: picked.id,
          language: lang,
          media_id: mediaId,
          ref: `media://${mediaId}`,
          url: `/api/media/${mediaId}`,
          duration: ttsRes.duration,
          cues,
        };
      } finally {
        if (fs.existsSync(tmpWav)) fs.unlinkSync(tmpWav);
      }
    } else if (actionName === "copywriting_generate") {
      const lang = String(params.language || "fr").toLowerCase().slice(0, 8);
      const topic = String(params.topic || project?.name || "Video").trim();
      const rawText = collectProjectText(project) || topic;
      const cw = await generateCopywritingBlock(rawText, lang);
      result = { action: actionName, copywriting: cw };
    } else if (actionName === "stock_import") {
      const url = String(params.url || "").trim();
      if (!url) throw new HttpError(400, "URL stock manquante.");
      const mediaId = await stockMod.importStockUrl(url, {
        source: String(params.source || "stock"),
        title: String(params.title || ""),
        license: String(params.license || "Stock License"),
      });
      result = {
        action: actionName,
        media_id: mediaId,
        ref: `media://${mediaId}`,
        url: `/api/media/${mediaId}`,
      };
    } else if (actionName === "image_generate") {
      // Explicit manual-only action (never auto-confirmed)
      const prompt = String(params.prompt || "").trim();
      if (!prompt) throw new HttpError(400, "Prompt image manquant.");
      const cfg = settingsMod.llmConfig();
      if (cfg.provider !== "gemini" || !cfg.api_key) {
        throw new HttpError(400, "Generation d'image requiert une cle Gemini configuree.");
      }
      const { GoogleGenAI } = await import("@google/genai");
      const ai = new GoogleGenAI({ apiKey: cfg.api_key });
      const res = await ai.models.generateImages({
        model: "imagen-3.0-generate-002",
        prompt,
        config: { numberOfImages: 1, aspectRatio: String(params.aspect_ratio || "9:16") as any },
      });
      const b64 = res.generatedImages?.[0]?.image?.imageBytes;
      if (!b64) throw new Error("Aucune image generee par le modele.");
      const tmpPng = path.join(EXPORTS_DIR, `_gen_${crypto.randomBytes(5).toString("hex")}.png`);
      fs.mkdirSync(EXPORTS_DIR, { recursive: true });
      fs.writeFileSync(tmpPng, Buffer.from(b64, "base64"));
      try {
        const mediaId = mediaMod.importFileToMedia(tmpPng, "imagen-3", "Generated");
        result = {
          action: actionName,
          media_id: mediaId,
          ref: `media://${mediaId}`,
          url: `/api/media/${mediaId}`,
        };
      } finally {
        if (fs.existsSync(tmpPng)) fs.unlinkSync(tmpPng);
      }
    } else {
      throw new HttpError(400, `Action studio inconnue : '${actionName}'.`);
    }

    logAgentEvent({
      event: "action_completed",
      actor,
      action: actionName,
      proposal_id: opts.proposalId,
      job_id: job.id,
      status: "done",
    });
    return result;
  } catch (err) {
    logAgentEvent({
      event: "action_failed",
      actor,
      action: actionName,
      proposal_id: opts.proposalId,
      job_id: job.id,
      status: "error",
      detail: { error: err instanceof Error ? err.message : String(err) },
    });
    throw err;
  }
}

export function startActionJob(
  actionName: string,
  params: Record<string, any>,
  project: schema.AnyRecord | null,
  opts: { autoConfirm?: boolean; proposalId?: string } = {},
): Job {
  const cleanName = safeName(actionName);
  return createJob(`action:${cleanName}`, (job) =>
    runAction(job, actionName, params, project, opts),
  );
}

export function collectProjectText(project: schema.AnyRecord | null): string {
  if (!project || !project.content || !Array.isArray(project.content.scenes)) return "";
  const chunks: string[] = [];
  for (const sc of project.content.scenes) {
    for (const l of sc.layers || []) {
      if (l.type === "text" && l.text) chunks.push(String(l.text).trim());
    }
  }
  return chunks.join(" — ");
}

export async function generateCopywritingBlock(
  sourceText: string,
  language = "fr",
): Promise<proposalsMod.CopywritingBlock> {
  const lang = String(language || "fr").trim().toLowerCase().slice(0, 8);
  const cfg = settingsMod.llmConfig();
  const [ready] = llmMod.isReady(cfg);

  if (ready && !budgets.isGlobalStopped()) {
    try {
      const prompt = `Redige des metadonnees de publication en langue '${lang}' pour cette video :\n"""\n${sourceText.slice(0, 1200)}\n"""\nReponds uniquement en JSON valide : {"title":"...","description":"...","hashtags":["#..."],"hook_lines":["..."],"cta":"...","language":"${lang}"}`;
      const res = await llmMod.chatCompletion(
        cfg,
        [
          { role: "system", content: "Tu es un redacteur video concis. Reponds uniquement en JSON valide." },
          { role: "user", content: prompt },
        ],
        { jsonMode: true, maxTokens: 450, temperature: 0.4 },
      );
      const parsed = JSON.parse(res.content) as Record<string, unknown>;
      const [validated, errs] = proposalsMod.validateCopywriting(parsed, lang);
      if (errs.length === 0) return validated;
    } catch {
      // Fall back to deterministic validated copywriting
    }
  }

  const clean = sourceText.replace(/\s+/g, " ").trim() || "Creation Studio";
  const words = clean.split(" ").filter((w) => w.length >= 4);
  const tags = [...new Set(words.slice(0, 4).map((w) => `#${w.replace(/[^\p{L}\p{N}]/gu, "")}`))]
    .filter((t) => t.length > 2);
  if (tags.length === 0) tags.push("#video", "#studio");

  const title = clean.slice(0, 92);
  const cta = lang === "en" ? "Save and share this moment." : lang === "ar" ? "احفظ هذا المقطع وشاركه." : "Enregistrez et partagez cet extrait.";
  const [validated] = proposalsMod.validateCopywriting(
    {
      title,
      description: `${clean}\n\n${cta}`,
      hashtags: tags,
      hook_lines: [title],
      cta,
      language: lang,
    },
    lang,
  );
  return validated;
}

export function saveProjectFile(name: string, project: schema.AnyRecord): string {
  const clean = safeName(name);
  const out = path.join(PROJECTS_DIR, clean.endsWith(".json") ? clean : `${clean}.json`);
  fs.mkdirSync(PROJECTS_DIR, { recursive: true });
  const cloned = schema.clone(project);
  delete cloned.resolved;
  fs.writeFileSync(out, JSON.stringify(cloned, null, 2), "utf8");
  return out;
}
