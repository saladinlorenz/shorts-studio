import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import * as budgets from "../budgets.ts";
import * as effectsMod from "../effects.ts";
import * as fontsMod from "../fonts.ts";
import { Job, raiseIfCancelled } from "../jobs.ts";
import * as libraryMod from "../library.ts";
import { logAgentEvent } from "../logger.ts";
import * as retrievalMod from "../retrieval.ts";
import * as schema from "../schema.ts";
import { HttpError, KNOWLEDGE_DIR, MEDIA_DIR, safeName } from "../security.ts";
import * as settingsMod from "../settings.ts";
import * as actionsMod from "./actions.ts";
import * as autopilotMod from "./autopilot.ts";
import * as llmMod from "./llm.ts";
import * as proposalsMod from "./proposals.ts";
import * as toolsMod from "./tools.ts";

const PROPOSALS_DIR = path.join(KNOWLEDGE_DIR, "proposals");
const PROPOSALS = new Map<string, Record<string, any>>();

function saveProposal(rec: Record<string, any>): void {
  PROPOSALS.set(String(rec.id), rec);
  try {
    fs.mkdirSync(PROPOSALS_DIR, { recursive: true });
    fs.writeFileSync(path.join(PROPOSALS_DIR, `${safeName(String(rec.id))}.json`), JSON.stringify(rec, null, 2), "utf8");
  } catch {
    // non-fatal
  }
}

export function getRecord(proposalId: string): Record<string, any> {
  const clean = safeName(proposalId);
  const mem = PROPOSALS.get(clean);
  if (mem) return mem;
  const full = path.join(PROPOSALS_DIR, `${clean}.json`);
  if (!fs.existsSync(full)) {
    throw new HttpError(404, `Proposition introuvable ou expiree : ${proposalId}`);
  }
  const parsed = JSON.parse(fs.readFileSync(full, "utf8")) as Record<string, any>;
  PROPOSALS.set(clean, parsed);
  return parsed;
}

export function ensureIndex(force = false) {
  return retrievalMod.build(force);
}

export function status() {
  const cfg = settingsMod.llmConfig();
  const [ready, reason] = llmMod.isReady(cfg);
  const k = retrievalMod.status();
  const mediaCount = fs.existsSync(MEDIA_DIR)
    ? fs.readdirSync(MEDIA_DIR).filter((f) => f !== "provenance" && !f.endsWith(".part")).length
    : 0;
  const models = Object.keys(schema.MODELS);
  const templates = libraryMod.listLibrary().map((m) => String(m.id));
  const fonts = fontsMod.familyIds();

  return {
    enabled: cfg.enabled,
    ready,
    reason,
    provider: cfg.provider,
    is_cloud: cfg.provider === "gemini" || cfg.provider === "groq",
    model: cfg.model,
    base_url: cfg.base_url,
    key_configured: Boolean(cfg.api_key),
    pin_configured: Boolean(cfg.pin),
    temperature: cfg.temperature,
    max_tokens: cfg.max_tokens,
    context_budget: cfg.context_budget,
    timeout: cfg.timeout,
    json_mode: cfg.json_mode,
    stream: cfg.stream,
    max_repairs: cfg.max_repairs,
    max_tool_calls: cfg.max_tool_calls,
    knowledge: {
      built: k.indexed,
      engine: k.engine,
      docs: k.chunks,
      chunks: k.chunks,
    },
    tools: {
      read: [...toolsMod.READ_TOOLS],
      propose: ["project_new", "project_patch", "library_save", "autopilot_plan", "studio_action", "copywriting"],
      execute_with_user: actionsMod.ACTIONS_CATALOG.map((a) => a.name),
      forbidden: ["exec_shell", "exfiltrate_keys"],
    },
    capabilities: {
      models,
      templates,
      fonts,
      media_count: mediaCount,
      animation_in: [...schema.ANIM_IN],
      remotion: "4.0",
      remotion_packages: ["@remotion/paths", "@remotion/media-utils", "@remotion/transitions"],
      not_available: [],
      knowledge_sources: [{ id: "skills/remotion", title: "Documentation Remotion", version: "4.0" }],
    },
    budget: budgets.getBudgetState(),
  };
}

export function manifest() {
  return {
    status: status(),
    effects: effectsMod.ids(),
    actions: actionsMod.ACTIONS_CATALOG,
    autopilot_steps: proposalsMod.AUTOPILOT_STEPS,
    read_tools: toolsMod.READ_TOOLS,
  };
}

function summarizeChanges(beforeProj: schema.AnyRecord | null, afterProj: schema.AnyRecord): Array<{ target: string; before: string; after: string }> {
  const changes: Array<{ target: string; before: string; after: string }> = [];
  if (!beforeProj) {
    changes.push({ target: "projet", before: "(aucun)", after: `${afterProj.model?.id || "quote_cinematic"} (${afterProj.export?.width}x${afterProj.export?.height})` });
    return changes;
  }
  const bTheme = beforeProj.theme || {};
  const aTheme = afterProj.theme || {};
  if (bTheme.background_color !== aTheme.background_color || bTheme.accent_color !== aTheme.accent_color) {
    changes.push({
      target: "theme.palette",
      before: `${bTheme.background_color || ""} / ${bTheme.accent_color || ""}`,
      after: `${aTheme.background_color || ""} / ${aTheme.accent_color || ""}`,
    });
  }
  const bScenes = (beforeProj.content?.scenes || []) as schema.AnyRecord[];
  const aScenes = (afterProj.content?.scenes || []) as schema.AnyRecord[];
  for (let i = 0; i < aScenes.length; i++) {
    const bs = bScenes[i];
    const as = aScenes[i];
    if (!bs) continue;
    for (const al of as.layers || []) {
      const bl = (bs.layers || []).find((x: any) => x.id === al.id);
      if (bl && al.type === "text" && bl.text !== al.text) {
        changes.push({
          target: `${as.id}.${al.id}`,
          before: String(bl.text || "").slice(0, 60),
          after: String(al.text || "").slice(0, 60),
        });
      }
    }
  }
  if (JSON.stringify(beforeProj.publish || null) !== JSON.stringify(afterProj.publish || null)) {
    changes.push({
      target: "publish",
      before: beforeProj.publish?.title ? String(beforeProj.publish.title) : "(vide)",
      after: afterProj.publish?.title ? String(afterProj.publish.title) : "(mis a jour)",
    });
  }
  if (changes.length === 0) {
    changes.push({ target: "projet", before: "etat precedent", after: "mis a jour" });
  }
  return changes;
}

function makeProposalId(): string {
  return `prop_${crypto.randomBytes(6).toString("hex")}`;
}

export async function runRequest(
  job: Job,
  payload: Record<string, any>,
): Promise<{ proposal: Record<string, unknown>; meta: Record<string, unknown> }> {
  budgets.assertNotStopped();
  const startedAt = Date.now();
  const cfg = settingsMod.llmConfig();
  const [llmReady] = llmMod.isReady(cfg);
  const message = String(payload.message || "").trim();
  if (!message) throw new HttpError(400, "Message vide.");

  const mode = String(payload.mode || "design").toLowerCase();
  const project = (payload.project && typeof payload.project === "object" ? payload.project : null) as schema.AnyRecord | null;
  const projectName = String(payload.project_name || project?.name || "projet");
  const baseRevision = String(payload.revision || "");
  const history = Array.isArray(payload.history) ? payload.history : [];

  job.setProgress(0.15, 1, "Analyse de la demande…");

  // Mode autopilot
  if (mode === "autopilot") {
    const { spec, plan, sources } = await autopilotMod.planSpec(message, history);
    const id = makeProposalId();
    const rec = {
      id,
      type: "autopilot_plan",
      summary: `Plan autopilote (${spec.aspect}, langue ${spec.language}) : ${spec.hook}`,
      status: "pending",
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      project_name: projectName,
      base_revision: baseRevision,
      validation: { state: "valid", errors: [], warnings: [] },
      autopilot: plan,
      raw_spec: spec,
      sources,
    };
    saveProposal(rec);
    logAgentEvent({ event: "proposal_created", actor: "system", proposal_id: id, status: "pending", detail: { type: "autopilot_plan" } });
    return {
      proposal: proposalsMod.publicView(rec),
      meta: { model: cfg.model || "local", provider: cfg.provider, attempts: 1, tool_calls: 0, latency_ms: Date.now() - startedAt },
    };
  }

  // P7: explicit copywriting proposal mode or prompt intent
  const low = message.toLowerCase();
  if (mode === "copywriting" || /\b(copywriting|titre youtube|hashtags|description video|accroche publication)\b/.test(low)) {
    const lang = fontsMod.containsArabic(message) || /\b(arabe|arabic)\b/.test(low) ? "ar"
      : /\b(english|anglais)\b/.test(low) ? "en" : "fr";
    const src = actionsMod.collectProjectText(project) || message;
    const cw = await actionsMod.generateCopywritingBlock(src, lang);
    const id = makeProposalId();
    const rec: Record<string, any> = {
      id,
      type: "copywriting",
      summary: `Copywriting valide (${cw.language.toUpperCase()}) : ${cw.title}`,
      status: "pending",
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      project_name: projectName,
      base_revision: baseRevision,
      validation: { state: "valid", errors: [], warnings: [] },
      copywriting: cw,
      changes: [{ target: "publish", before: project?.publish?.title || "(vide)", after: cw.title }],
      sources: [],
    };
    if (project) {
      const [patched] = proposalsMod.applyOperations(project, [{ op: "set_publish", publish: cw }]);
      rec.candidate = patched;
      rec.has_candidate = true;
    }
    saveProposal(rec);
    logAgentEvent({ event: "proposal_created", actor: "system", proposal_id: id, status: "pending", detail: { type: "copywriting" } });
    return {
      proposal: proposalsMod.publicView(rec),
      meta: { model: cfg.model || "local", provider: cfg.provider, attempts: 1, tool_calls: 0, latency_ms: Date.now() - startedAt },
    };
  }

  // P8: check_render direct trigger via studio_action
  if (/\b(check_render|verifier le rendu|controle rendu|verifier l'export)\b/.test(low)) {
    const id = makeProposalId();
    const rec = {
      id,
      type: "studio_action",
      summary: "Lancer la verification technique du rendu (check_render)",
      status: "pending",
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      project_name: projectName,
      base_revision: baseRevision,
      validation: { state: "valid", errors: [], warnings: [] },
      action: {
        name: "project_check_render",
        params: {},
        label: "Verifier le rendu (check_render)",
        impact: ["Controle les images noires, le niveau audio et les debordements de texte."],
        confirmation: "ok",
        context: {},
      },
      sources: [],
    };
    saveProposal(rec);
    return {
      proposal: proposalsMod.publicView(rec),
      meta: { model: cfg.model || "local", provider: cfg.provider, attempts: 1, tool_calls: 1, latency_ms: Date.now() - startedAt },
    };
  }

  // P6: horizontal 16:9 model intent
  if (/\b(16:9|horizontal|paysage|landscape)\b/.test(low) && /\b(nouveau|cree|creer|modele|format|passe)\b/.test(low)) {
    const cand = schema.horizontalProject();
    if (fontsMod.containsArabic(message)) {
      cand.theme.font_family = fontsMod.preferredArabicFontId();
    }
    const id = makeProposalId();
    const rec = {
      id,
      type: "project_new",
      summary: "Creer un projet au format horizontal 16:9 (1920x1080)",
      status: "pending",
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      project_name: "citation-horizontale",
      base_revision: baseRevision,
      validation: { state: "valid", errors: [], warnings: [] },
      has_candidate: true,
      candidate: cand,
      changes: summarizeChanges(null, cand),
      warnings: [],
      errors: [],
      sources: [],
    };
    saveProposal(rec);
    return {
      proposal: proposalsMod.publicView(rec),
      meta: { model: cfg.model || "local", provider: cfg.provider, attempts: 1, tool_calls: 0, latency_ms: Date.now() - startedAt },
    };
  }

  // Standard design mode via configured LLM (or graceful unavailable notice if LLM is not configured)
  if (!llmReady) {
    const id = makeProposalId();
    const rec = {
      id,
      type: "unavailable",
      summary: "Aucun fournisseur IA configure pour les modifications libres.",
      status: "pending",
      project_name: projectName,
      base_revision: baseRevision,
      validation: { state: "none", errors: [], warnings: [] },
      capability: "Fournisseur LLM (Gemini / Groq / Serveur local)",
      alternative: "Configurez une cle API dans Reglages ou utilisez les commandes rapides (modele 16:9, copywriting, check_render, autopilote).",
      sources: [],
    };
    saveProposal(rec);
    return {
      proposal: proposalsMod.publicView(rec),
      meta: { model: "", provider: cfg.provider, attempts: 0, tool_calls: 0, latency_ms: Date.now() - startedAt },
    };
  }

  raiseIfCancelled(job);
  const passages = retrievalMod.search(message, 3, 2200);
  const contextText = passages.map((p) => `[${p.title}] ${p.text.slice(0, 600)}`).join("\n\n");
  const compactProject = project
    ? {
        model: project.model,
        export: project.export,
        theme: project.theme,
        scenes: (project.content?.scenes || []).map((sc: any) => ({
          id: sc.id,
          duration: sc.duration,
          layers: (sc.layers || []).map((l: any) => ({ id: l.id, type: l.type, role: l.role, text: l.text })),
        })),
      }
    : null;

  const sysPrompt = [
    "Tu es l'assistant de Studio Video. Reponds uniquement en JSON strict.",
    "Types de propositions autorises :",
    '1) {"type":"project_patch","summary":"...","operations":[{"op":"set_layer_text","scene_id":"s2","layer_id":"quote","text":"..."},{"op":"set_theme","values":{"accent_color":"#..."}},{"op":"set_publish","publish":{"title":"...","description":"...","hashtags":["#..."]}}]}',
    '2) {"type":"project_new","summary":"...","model_id":"quote_cinematic|quote_horizontal","operations":[...]}',
    '3) {"type":"copywriting","summary":"...","copywriting":{"title":"...","description":"...","hashtags":["#..."],"hook_lines":["..."],"cta":"...","language":"fr"}}',
    '4) {"type":"studio_action","summary":"...","action_name":"project_check_render|project_review|project_export|tts_generate","params":{...},"impact":["..."]}',
    '5) {"type":"question","summary":"...","questions":["..."]}',
    `Polices disponibles : ${fontsMod.familyIds().join(", ")}.`,
    contextText ? `Extraits doc :\n${contextText}` : "",
  ].filter(Boolean).join("\n");

  let parsed: Record<string, any> | null = null;
  let attempts = 0;
  let lastError = "";
  const conv: llmMod.ChatMessage[] = [
    { role: "system", content: sysPrompt },
    ...history.slice(-4).map((m: any) => ({
      role: (m.role === "assistant" ? "assistant" : "user") as "user" | "assistant",
      content: String(m.content || ""),
    })),
    {
      role: "user",
      content: compactProject
        ? `Projet actif :\n${JSON.stringify(compactProject)}\n\nDemande utilisateur : ${message}`
        : `Aucun projet charge.\n\nDemande utilisateur : ${message}`,
    },
  ];

  while (attempts <= cfg.max_repairs) {
    attempts += 1;
    raiseIfCancelled(job);
    const res = await llmMod.chatCompletion(cfg, conv, { jsonMode: true, maxTokens: cfg.max_tokens });
    try {
      parsed = JSON.parse(res.content) as Record<string, any>;
      break;
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
      conv.push({ role: "assistant", content: res.content });
      conv.push({ role: "user", content: `JSON invalide (${lastError}). Reponds uniquement avec un objet JSON valide.` });
    }
  }

  if (!parsed) {
    throw new HttpError(502, `Reponse IA non structurable : ${lastError}`);
  }

  const id = makeProposalId();
  const pType = String(parsed.type || "question");
  const sources = passages.map((p, idx) => ({
    id: idx + 1,
    path: p.path,
    source: p.source,
    version: p.version,
    title: p.title,
    score: p.score,
  }));

  const rec: Record<string, any> = {
    id,
    type: pType,
    summary: String(parsed.summary || "Proposition IA"),
    status: "pending",
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    project_name: projectName,
    base_revision: baseRevision,
    sources,
  };

  if (pType === "project_patch" && project) {
    const ops = Array.isArray(parsed.operations) ? parsed.operations : [];
    const [cand, errors, warnings] = proposalsMod.applyOperations(project, ops);
    if (errors.length > 0) {
      rec.type = "question";
      rec.validation = { state: "invalid", errors, warnings: [] };
      rec.questions = [`Impossible de valider les modifications : ${errors.join(" ; ")}`];
    } else {
      rec.validation = { state: "valid", errors: [], warnings };
      rec.has_candidate = true;
      rec.candidate = cand;
      rec.changes = summarizeChanges(project, cand);
      rec.warnings = warnings;
      rec.errors = [];
    }
  } else if (pType === "project_new") {
    const base = schema.newProject(String(parsed.model_id || "quote_cinematic"));
    const ops = Array.isArray(parsed.operations) ? parsed.operations : [];
    const [cand, errors, warnings] = ops.length > 0
      ? proposalsMod.applyOperations(base, ops)
      : [base, [], []];
    if (errors.length > 0) {
      rec.type = "question";
      rec.validation = { state: "invalid", errors, warnings: [] };
      rec.questions = [`Modele invalide : ${errors.join(" ; ")}`];
    } else {
      rec.validation = { state: "valid", errors: [], warnings };
      rec.has_candidate = true;
      rec.candidate = cand;
      rec.changes = summarizeChanges(null, cand);
      rec.warnings = warnings;
    }
  } else if (pType === "copywriting") {
    const [cw, errs] = proposalsMod.validateCopywriting(parsed.copywriting || parsed, "fr");
    if (errs.length > 0) {
      rec.type = "question";
      rec.validation = { state: "invalid", errors: errs, warnings: [] };
      rec.questions = errs;
    } else {
      rec.validation = { state: "valid", errors: [], warnings: [] };
      rec.copywriting = cw;
      rec.changes = [{ target: "publish", before: project?.publish?.title || "(vide)", after: cw.title }];
      if (project) {
        const [patched] = proposalsMod.applyOperations(project, [{ op: "set_publish", publish: cw }]);
        rec.candidate = patched;
        rec.has_candidate = true;
      }
    }
  } else if (pType === "studio_action") {
    const actionName = String(parsed.action_name || "project_check_render");
    const spec = actionsMod.describeAction(actionName);
    rec.validation = { state: "valid", errors: [], warnings: [] };
    rec.action = {
      name: actionName,
      params: (parsed.params && typeof parsed.params === "object") ? parsed.params : {},
      label: spec?.label || actionName,
      impact: Array.isArray(parsed.impact) ? parsed.impact.map(String) : [spec?.description || actionName],
      confirmation: "ok",
      context: {},
    };
  } else {
    rec.type = "question";
    rec.validation = { state: "none", errors: [], warnings: [] };
    rec.questions = Array.isArray(parsed.questions) && parsed.questions.length > 0
      ? parsed.questions.map(String)
      : [String(parsed.summary || "Pouvez-vous preciser votre demande ?")];
  }

  saveProposal(rec);
  logAgentEvent({ event: "proposal_created", actor: "system", proposal_id: id, status: "pending", detail: { type: rec.type } });
  return {
    proposal: proposalsMod.publicView(rec),
    meta: { model: cfg.model, provider: cfg.provider, attempts, tool_calls: 0, latency_ms: Date.now() - startedAt },
  };
}

export function accept(proposalId: string, _currentProject: schema.AnyRecord | null, _rebase = false) {
  const rec = getRecord(proposalId);
  rec.status = "accepted";
  saveProposal(rec);
  logAgentEvent({ event: "proposal_accepted", actor: "user", proposal_id: proposalId, status: "accepted", detail: { type: rec.type } });

  if (rec.type === "autopilot_plan") {
    const state = autopilotMod.start(rec.raw_spec || {}, rec.autopilot || {}, proposalId);
    return { kind: "autopilot", autopilot_job_id: state.job_id, changes: [] };
  }
  if (rec.candidate) {
    return {
      kind: rec.type === "library_save" ? "library_save" : "project",
      project: rec.candidate,
      warnings: rec.warnings || [],
      changes: rec.changes || [],
      copywriting: rec.copywriting,
    };
  }
  return { kind: rec.type, copywriting: rec.copywriting, changes: rec.changes || [] };
}

export function executeProposalAction(
  proposalId: string,
  confirmation: string,
  project: schema.AnyRecord | null,
  autoConfirm = false,
): Job {
  const rec = getRecord(proposalId);
  if (rec.type !== "studio_action" || !rec.action) {
    throw new HttpError(400, "Cette proposition ne contient pas d'action executable.");
  }
  if (!autoConfirm && !String(confirmation || "").trim()) {
    throw new HttpError(400, "Confirmation requise pour executer cette action.");
  }
  rec.status = "executed";
  saveProposal(rec);
  return actionsMod.startActionJob(
    String(rec.action.name),
    (rec.action.params || {}) as Record<string, any>,
    project,
    { autoConfirm, proposalId },
  );
}

export function reject(proposalId: string) {
  const rec = getRecord(proposalId);
  rec.status = "rejected";
  saveProposal(rec);
  logAgentEvent({ event: "proposal_rejected", actor: "user", proposal_id: proposalId, status: "rejected" });
  return { rejected: proposalId, project_unchanged: true };
}
