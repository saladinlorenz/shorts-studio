import fs from "node:fs";
import path from "node:path";
import * as schema from "./schema.ts";
import { MODELS_DIR, ROOT, HttpError, safeName } from "./security.ts";

export interface BuiltinInfo {
  id: string;
  label: string;
  description: string;
  factory: () => schema.AnyRecord;
}

export const BUILTINS: Record<string, BuiltinInfo> = {
  "citation-cinematique": {
    id: "citation-cinematique",
    label: "Citation cinématique",
    description: "Modèle du studio : 3 scènes, masque d'accroche, citation mot à mot, signature.",
    factory: schema.cinematicProject,
  },
  "recit-cinematique": {
    id: "recit-cinematique",
    label: "Récit cinématique (5 scènes)",
    description: "Narration rythmée en 5 temps : accroche, contexte, tension, déclic, conclusion.",
    factory: () => schema.presetProject("recit-cinematique"),
  },
  "showcase-cinematique": {
    id: "showcase-cinematique",
    label: "Showcase produit (4 scènes)",
    description: "Présentation haut de gamme : promesse, détail, bénéfice et invitation.",
    factory: () => schema.presetProject("showcase-cinematique"),
  },
  // P6: horizontal 16:9 model builtin
  "citation-horizontale": {
    id: "citation-horizontale",
    label: "Citation horizontale 16:9",
    description: "Modèle paysage 16:9 (1920x1080) pour YouTube, LinkedIn et présentations.",
    factory: () => schema.horizontalProject(),
  },
};

function summary(project: schema.AnyRecord, id: string, opts: { builtin: boolean; description?: string; label?: string; updatedAt?: number }) {
  const scenes = (project.content?.scenes || []) as schema.AnyRecord[];
  const exp = project.export || {};
  const meta = project.library_meta || {};
  const duration = Math.round(scenes.reduce((s, sc) => s + Number(sc.duration || 0), 0) * 100) / 100;
  return {
    id,
    label: opts.label || meta.label || project.name || id,
    description: opts.description || meta.description || "",
    builtin: opts.builtin,
    model: project.model?.id || "",
    version: project.version,
    scenes: scenes.length,
    duration,
    dimensions: `${exp.width || 1080}x${exp.height || 1920}`,
    palette_id: project.theme?.palette_id || "",
    background_color: project.theme?.background_color || "#0B0B10",
    accent_color: project.theme?.accent_color || "#E2B458",
    updated_at: opts.updatedAt ?? null,
  };
}

export function listLibrary(): Array<ReturnType<typeof summary>> {
  const items: Array<ReturnType<typeof summary>> = [];
  for (const [id, info] of Object.entries(BUILTINS)) {
    items.push(
      summary(info.factory(), id, {
        builtin: true,
        label: info.label,
        description: info.description,
      }),
    );
  }
  if (fs.existsSync(MODELS_DIR)) {
    const files = fs.readdirSync(MODELS_DIR).filter((f) => f.endsWith(".json")).sort();
    for (const file of files) {
      const full = path.join(MODELS_DIR, file);
      const id = path.basename(file, ".json");
      try {
        const data = JSON.parse(fs.readFileSync(full, "utf8")) as schema.AnyRecord;
        const stat = fs.statSync(full);
        items.push(summary(data, id, { builtin: false, updatedAt: stat.mtimeMs / 1000 }));
      } catch {
        // skip unreadable files
      }
    }
  }
  return items;
}

export function getProject(modelId: string): schema.AnyRecord {
  const id = String(modelId || "").trim();
  if (id in BUILTINS) {
    return BUILTINS[id].factory();
  }
  const clean = safeName(id);
  const full = path.join(MODELS_DIR, clean.endsWith(".json") ? clean : `${clean}.json`);
  if (!fs.existsSync(full)) {
    throw new HttpError(404, `Modele introuvable : ${id}`);
  }
  return JSON.parse(fs.readFileSync(full, "utf8")) as schema.AnyRecord;
}

export function saveModel(
  project: schema.AnyRecord,
  label = "",
  description = "",
  modelId?: string | null,
): Record<string, unknown> {
  if (!project || typeof project !== "object") {
    throw new HttpError(400, "Projet invalide.");
  }
  const slugBase = (modelId || label || project.name || "modele")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "modele";
  const finalId = slugBase in BUILTINS ? `${slugBase}-perso` : slugBase;
  const safeId = safeName(finalId);
  fs.mkdirSync(MODELS_DIR, { recursive: true });
  const cloned = schema.clone(project);
  delete cloned.resolved;
  cloned.library_meta = {
    label: label.trim() || cloned.name || safeId,
    description: description.trim(),
    saved_at: new Date().toISOString(),
  };
  const dest = path.join(MODELS_DIR, `${safeId}.json`);
  fs.writeFileSync(dest, JSON.stringify(cloned, null, 2), "utf8");
  return {
    id: safeId,
    model: summary(cloned, safeId, { builtin: false, updatedAt: Date.now() / 1000 }),
    path: path.relative(ROOT, dest),
  };
}

export function deleteModel(modelId: string): { deleted: string } {
  if (modelId in BUILTINS) {
    throw new HttpError(400, "Un modele integre du studio ne peut pas etre supprime.");
  }
  const safeId = safeName(modelId);
  const target = path.join(MODELS_DIR, `${safeId}.json`);
  if (!fs.existsSync(target)) {
    throw new HttpError(404, `Modele introuvable : ${modelId}`);
  }
  fs.unlinkSync(target);
  return { deleted: safeId };
}
