import * as fontsMod from "./fonts.ts";
import * as schema from "./schema.ts";

const MEDIA_REF_RE = /^media:\/\/[0-9A-Za-z_-]{4,64}$/;
const HEX_COLOR_RE = /^#[0-9A-Fa-f]{6}$/;

const THEME_KEYS = new Set(Object.keys(schema.defaultTheme()));
const SIGNATURE_KEYS = new Set(Object.keys(schema.defaultSignature()));
const AUDIO_KEYS = new Set(["enabled", "music", "music_volume"]);
const STRING_KEYS = new Set(["palette_id", "handle"]);
const MEDIA_KEYS = new Set(["media", "music"]);

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function checkRef(val: unknown, label: string, errors: string[]): string {
  const ref = String(val || "").trim();
  if (!ref) return "";
  if (ref.startsWith("media://")) {
    if (!MEDIA_REF_RE.test(ref)) {
      errors.push(`${label} : reference media invalide.`);
      return "";
    }
    return ref;
  }
  errors.push(`${label} : utilisez un media du studio (media://...).`);
  return "";
}

function checkSection(
  section: unknown,
  keys: Set<string>,
  label: string,
  errors: string[],
  warnings: string[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (!section || typeof section !== "object" || Array.isArray(section)) return out;
  for (const [key, value] of Object.entries(section as Record<string, unknown>)) {
    if (!keys.has(key)) {
      warnings.push(`${label} : reglage '${key}' inconnu, ignore.`);
      continue;
    }
    if (key === "position") {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        errors.push(`${label} : position invalide.`);
        continue;
      }
      const p: Record<string, number> = {};
      for (const [ax, n] of Object.entries(value as Record<string, unknown>)) {
        if ((ax === "x" || ax === "y") && isNum(n)) p[ax] = n;
      }
      out[key] = p;
      continue;
    }
    if (MEDIA_KEYS.has(key)) {
      const ref = checkRef(value, `${label} : ${key}`, errors);
      if (ref) out[key] = ref;
      continue;
    }
    if (STRING_KEYS.has(key)) {
      out[key] = String(value || "").trim().slice(0, 80);
      continue;
    }
    if (key.endsWith("_color") || key === "color") {
      if (typeof value !== "string" || !HEX_COLOR_RE.test(value.trim())) {
        errors.push(`${label} : couleur '${value}' invalide (#RRGGBB).`);
        continue;
      }
      out[key] = value.trim();
      continue;
    }
    if (key.endsWith("_family")) {
      const fam = String(value || "").trim();
      if (!fam || !fontsMod.isKnownFamily(fam)) {
        errors.push(`${label} : police '${fam}' absente du catalogue.`);
        continue;
      }
      out[key] = fam;
      continue;
    }
    if (typeof value === "boolean" || isNum(value)) {
      out[key] = value;
      continue;
    }
    errors.push(`${label} : valeur de '${key}' non prise en charge.`);
  }
  return out;
}

export function normalizeBrandPack(raw: unknown): [Record<string, unknown>, string[], string[]] {
  const errors: string[] = [];
  const warnings: string[] = [];
  const data = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};

  let label = String(data.label || "").trim();
  if (!label) errors.push("Pack : un nom de client est obligatoire.");
  if (label.length > 80) {
    label = label.slice(0, 80);
    warnings.push("Pack : nom raccourci a 80 caracteres.");
  }
  const notes = String(data.notes || "").trim().slice(0, 600);
  const theme = checkSection(data.theme, THEME_KEYS, "Theme", errors, warnings);
  const signature = checkSection(data.signature, SIGNATURE_KEYS, "Signature", errors, warnings);

  const audio: Record<string, unknown> = {};
  const rawAudio = data.audio && typeof data.audio === "object" ? (data.audio as Record<string, unknown>) : {};
  for (const [key, value] of Object.entries(rawAudio)) {
    if (!AUDIO_KEYS.has(key)) {
      warnings.push(`Audio : reglage '${key}' inconnu, ignore.`);
      continue;
    }
    if (key === "music") {
      const ref = checkRef(value, "Musique du pack", errors);
      if (ref) audio[key] = ref;
    } else if (key === "enabled") {
      audio[key] = Boolean(value);
    } else if (isNum(value)) {
      audio[key] = Math.round(Math.min(1, Math.max(0, value)) * 1000) / 1000;
    } else {
      errors.push("Audio : volume invalide.");
    }
  }

  const models: string[] = [];
  if (Array.isArray(data.models)) {
    for (const m of data.models) {
      const id = String(m || "");
      if (!(id in schema.MODELS)) {
        errors.push(`Modele '${id}' inconnu.`);
      } else {
        models.push(id);
      }
    }
  }

  return [{ label, notes, theme, signature, audio, models }, errors, warnings];
}

export function fromProject(project: schema.AnyRecord, label: string, notes = ""): Record<string, unknown> {
  const theme: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(project.theme || {})) {
    if (THEME_KEYS.has(k)) theme[k] = v;
  }
  const signature: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(project.content?.signature || {})) {
    if (SIGNATURE_KEYS.has(k)) signature[k] = v;
  }
  const audio: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(project.audio || {})) {
    if (AUDIO_KEYS.has(k)) audio[k] = v;
  }
  return {
    label,
    notes,
    theme,
    signature,
    audio,
    models: project.model?.id ? [String(project.model.id)] : [],
  };
}

export function applyBrand(project: schema.AnyRecord, pack: Record<string, unknown>): [schema.AnyRecord, string[]] {
  const warnings: string[] = [];
  const patched = schema.clone(project);
  delete patched.resolved;

  patched.theme = { ...schema.defaultTheme(), ...(patched.theme || {}), ...(pack.theme as Record<string, unknown> || {}) };
  if (!patched.content) patched.content = {};
  patched.content.signature = {
    ...schema.defaultSignature(),
    ...(patched.content.signature || {}),
    ...(pack.signature as Record<string, unknown> || {}),
  };
  if (!patched.audio) patched.audio = {};
  Object.assign(patched.audio, pack.audio || {});

  const allowed = (pack.models as string[]) || [];
  const modelId = String(patched.model?.id || "");
  if (allowed.length > 0 && modelId && !allowed.includes(modelId)) {
    warnings.push(`Modele '${modelId}' hors des modeles autorises du pack.`);
  }
  return [patched, warnings];
}
