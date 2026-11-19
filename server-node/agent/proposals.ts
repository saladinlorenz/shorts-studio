import * as fontsMod from "../fonts.ts";
import * as schema from "../schema.ts";
import { validateProject } from "../validation.ts";

export class ProposalError extends Error {
  errors: string[];
  constructor(message: string, errors: string[] = []) {
    super(message);
    this.name = "ProposalError";
    this.errors = errors;
  }
}

export const PROPOSAL_TYPES = [
  "question",
  "unavailable",
  "project_new",
  "project_patch",
  "library_save",
  "batch_plan",
  "autopilot_plan",
  "studio_action",
  "copywriting", // P7: validated structured copywriting proposal
] as const;

// P2: Conditional multi-step autopilot pipeline
export const AUTOPILOT_STEPS: Array<{ id: string; label: string; conditional?: boolean }> = [
  { id: "script", label: "Script & structure" },
  { id: "design", label: "Design & format" },
  { id: "media", label: "Medias / B-roll", conditional: true },
  { id: "voice", label: "Voix off & ASR", conditional: true },
  { id: "export", label: "Export MP4" },
  { id: "qc", label: "Controle QC", conditional: true },
  { id: "metadata", label: "Copywriting & SRT", conditional: true },
  { id: "delivery", label: "Livraison multi-formats", conditional: true },
];

export interface CopywritingBlock {
  title: string;
  description: string;
  hashtags: string[];
  hook_lines: string[];
  cta: string;
  language: string;
}

/**
 * P7: Validates and normalizes structured marketing copywriting before returning a proposal.
 */
export function validateCopywriting(raw: unknown, fallbackLang = "fr"): [CopywritingBlock, string[]] {
  const errors: string[] = [];
  const obj = (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {}) as Record<string, unknown>;

  const title = String(obj.title || "").replace(/<[^>]+>/g, "").trim();
  if (!title) errors.push("copywriting.title : titre obligatoire.");
  if (title.length > 100) errors.push("copywriting.title : maximum 100 caracteres.");

  const description = String(obj.description || "").replace(/<[^>]+>/g, "").trim();
  if (!description) errors.push("copywriting.description : description obligatoire.");
  if (description.length > 2200) errors.push("copywriting.description : maximum 2200 caracteres.");

  const rawTags = Array.isArray(obj.hashtags) ? obj.hashtags : [];
  const hashtags = rawTags
    .map((t) => String(t || "").trim())
    .filter(Boolean)
    .map((t) => (t.startsWith("#") ? t : `#${t}`).replace(/\s+/g, ""))
    .slice(0, 12);
  if (hashtags.length === 0) errors.push("copywriting.hashtags : au moins 1 hashtag (#...) requis.");

  const hookLines = (Array.isArray(obj.hook_lines) ? obj.hook_lines : [])
    .map((h) => String(h || "").trim())
    .filter(Boolean)
    .slice(0, 5);

  const cta = String(obj.cta || "").trim().slice(0, 140);
  const language = String(obj.language || fallbackLang || "fr").trim().toLowerCase().slice(0, 8);

  return [
    {
      title: title.slice(0, 100),
      description: description.slice(0, 2200),
      hashtags,
      hook_lines: hookLines,
      cta,
      language,
    },
    errors,
  ];
}

export function applyOperations(
  project: schema.AnyRecord,
  operations: Array<Record<string, any>>,
): [schema.AnyRecord, string[], string[]] {
  const patched = schema.clone(project);
  delete patched.resolved;
  const warnings: string[] = [];
  const errors: string[] = [];

  for (let i = 0; i < operations.length; i++) {
    const op = operations[i] || {};
    const kind = String(op.op || "");
    if (kind === "set_theme") {
      patched.theme = { ...(patched.theme || {}), ...(op.values || {}) };
    } else if (kind === "set_signature") {
      if (!patched.content) patched.content = {};
      patched.content.signature = { ...(patched.content.signature || {}), ...(op.values || {}) };
    } else if (kind === "set_publish") {
      // P7: validated metadata written to project.publish
      const [cw, cwErr] = validateCopywriting(op.publish || op.values || {});
      if (cwErr.length > 0) errors.push(...cwErr);
      else patched.publish = cw;
    } else if (kind === "set_export") {
      patched.export = { ...(patched.export || {}), ...(op.values || {}) };
    } else if (kind === "set_audio") {
      patched.audio = { ...(patched.audio || {}), ...(op.values || {}) };
    } else if (kind === "set_layer_text") {
      const sc = (patched.content?.scenes || []).find((s: any) => s.id === op.scene_id);
      const layer = sc?.layers?.find((l: any) => l.id === op.layer_id);
      if (!layer || layer.type !== "text") {
        errors.push(`operations[${i}] : calque texte '${op.scene_id}.${op.layer_id}' introuvable.`);
        continue;
      }
      layer.text = String(op.text ?? "");
      if (Array.isArray(op.emphasis)) layer.emphasis = op.emphasis.map(String);
      // P3: automatic Arabic font/RTL support if Arabic text injected
      if (fontsMod.containsArabic(layer.text)) {
        layer.position = { ...(layer.position || {}), direction: "rtl" };
        if (!layer.style) layer.style = {};
        if (!layer.style.font_family) layer.style.font_family = fontsMod.preferredArabicFontId();
      }
    } else if (kind === "set_layer_style") {
      const sc = (patched.content?.scenes || []).find((s: any) => s.id === op.scene_id);
      const layer = sc?.layers?.find((l: any) => l.id === op.layer_id);
      if (!layer) {
        errors.push(`operations[${i}] : calque '${op.scene_id}.${op.layer_id}' introuvable.`);
        continue;
      }
      layer.style = { ...(layer.style || {}), ...(op.style || op.values || {}) };
    } else if (kind === "set_scene_duration") {
      const sc = (patched.content?.scenes || []).find((s: any) => s.id === op.scene_id);
      if (!sc) {
        errors.push(`operations[${i}] : scene '${op.scene_id}' introuvable.`);
        continue;
      }
      sc.duration = Number(op.duration);
    } else if (kind === "set_scene_background") {
      const sc = (patched.content?.scenes || []).find((s: any) => s.id === op.scene_id);
      if (!sc) {
        errors.push(`operations[${i}] : scene '${op.scene_id}' introuvable.`);
        continue;
      }
      sc.background = { ...(sc.background || {}), ...(op.background || op.values || {}) };
    } else if (kind === "set_layer_effects") {
      const sc = (patched.content?.scenes || []).find((s: any) => s.id === op.scene_id);
      const layer = sc?.layers?.find((l: any) => l.id === op.layer_id);
      if (!layer) {
        errors.push(`operations[${i}] : calque '${op.scene_id}.${op.layer_id}' introuvable.`);
        continue;
      }
      layer.effects = Array.isArray(op.effects) ? op.effects : [];
    } else if (kind === "set_scene_effects") {
      const sc = (patched.content?.scenes || []).find((s: any) => s.id === op.scene_id);
      if (!sc) {
        errors.push(`operations[${i}] : scene '${op.scene_id}' introuvable.`);
        continue;
      }
      sc.effects = Array.isArray(op.effects) ? op.effects : [];
    } else {
      warnings.push(`operations[${i}] : operation '${kind}' inconnue, ignoree.`);
    }
  }

  const [vErr, vWarn] = validateProject(patched);
  errors.push(...vErr);
  warnings.push(...vWarn);
  return [patched, errors, warnings];
}

export function buildAutopilotProject(spec: Record<string, any>): schema.AnyRecord {
  const aspect = String(spec.aspect || "9:16");
  const modelId = aspect === "16:9" ? "quote_horizontal" : "quote_cinematic";
  const proj = schema.newProject(modelId);
  if (aspect === "1:1") {
    proj.export.width = 1080;
    proj.export.height = 1080;
  } else if (aspect === "16:9") {
    proj.export.width = 1920;
    proj.export.height = 1080;
  }

  const lang = String(spec.language || "fr").toLowerCase().slice(0, 8);
  const fullText = `${spec.hook || ""} ${spec.quote || ""} ${spec.author || ""} ${spec.reveal || ""}`;
  const isArabic = lang === "ar" || fontsMod.containsArabic(fullText);

  if (isArabic) {
    proj.theme.font_family = fontsMod.preferredArabicFontId();
    proj.theme.font_weight = 700;
  }

  const scenes = proj.content.scenes as schema.AnyRecord[];
  const setLayer = (sceneIdx: number, layerId: string, textVal: unknown) => {
    const val = String(textVal || "").trim();
    if (!val || !scenes[sceneIdx]) return;
    const layer = scenes[sceneIdx].layers.find((l: any) => l.id === layerId);
    if (layer) {
      layer.text = val;
      if (isArabic) {
        layer.position.direction = "rtl";
        layer.style.font_family = fontsMod.preferredArabicFontId();
        layer.style.font_weight = 700;
      }
    }
  };

  setLayer(0, "hook", spec.hook);
  setLayer(0, "hook-caption", spec.hook_caption);
  setLayer(1, "quote", spec.quote);
  setLayer(1, "author", spec.author);
  setLayer(2, "reveal", spec.reveal);
  setLayer(2, "reveal-note", spec.reveal_note);

  if (spec.palette_id && spec.background_color && spec.text_color && spec.accent_color) {
    proj.theme.palette_id = String(spec.palette_id);
    proj.theme.background_color = String(spec.background_color);
    proj.theme.text_color = String(spec.text_color);
    proj.theme.accent_color = String(spec.accent_color);
    proj.theme.author_color = String(spec.accent_color);
  }

  if (spec.copywriting) {
    const [cw, errs] = validateCopywriting(spec.copywriting, lang);
    if (errs.length === 0) proj.publish = cw;
  }

  return proj;
}

export function publicView(proposal: Record<string, any>) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(proposal)) {
    if (k === "candidate" || k === "raw_spec") continue;
    out[k] = v;
  }
  return out;
}
