import fs from "node:fs";
import path from "node:path";
import { ROOT, WEB_PUBLIC } from "./security.ts";

export const CATALOG_PATH = path.join(ROOT, "web", "src", "remotion", "fontCatalog.json");
export const FONTS_DIR = path.join(WEB_PUBLIC, "fonts");

export interface FontVariant {
  weight: number;
  style: string;
  file: string;
}

export interface FontFamily {
  id: string;
  label: string;
  css_family: string;
  role?: string;
  category?: string;
  scripts?: string[];
  default_weight?: number;
  license?: string;
  licence?: string;
  retrieved?: string;
  source?: string;
  weights?: FontVariant[];
  variants?: FontVariant[];
}

function variantsOf(fam: FontFamily | undefined): FontVariant[] {
  if (!fam) return [];
  return fam.weights || fam.variants || [];
}

export function loadCatalog(): { families: FontFamily[] } {
  if (!fs.existsSync(CATALOG_PATH)) return { families: [] };
  return JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8")) as { families: FontFamily[] };
}

export function families(): FontFamily[] {
  return loadCatalog().families || [];
}

export function familyById(): Map<string, FontFamily> {
  return new Map(families().map((f) => [f.id, f]));
}

export function familyIds(): string[] {
  return families().map((f) => f.id);
}

export function isKnownFamily(fontId: string): boolean {
  return familyById().has(fontId);
}

export function weightsFor(fontId: string): number[] {
  const fam = familyById().get(fontId);
  if (!fam) return [];
  return [...new Set(variantsOf(fam).map((v) => Number(v.weight)))].sort((a, b) => a - b);
}

export function hasWeight(fontId: string, weight: number): boolean {
  return weightsFor(fontId).includes(Number(weight));
}

export function fallbackWeight(fontId: string, weight: number): number {
  const available = weightsFor(fontId);
  if (available.includes(Number(weight))) return Number(weight);
  const fam = familyById().get(fontId);
  const def = Number(fam?.default_weight || 400);
  return available.includes(def) ? def : (available[0] ?? 400);
}

export function fontUrl(fontId: string, weight: number): string {
  const fam = familyById().get(fontId);
  if (!fam) throw new Error(`Police inconnue : ${fontId}`);
  const match = variantsOf(fam).find((v) => Number(v.weight) === Number(weight));
  if (!match) throw new Error(`Graisse ${weight} absente pour ${fontId}`);
  return `/fonts/${match.file}`;
}

export function missingFiles(): string[] {
  const missing: string[] = [];
  for (const fam of families()) {
    for (const v of variantsOf(fam)) {
      const full = path.join(FONTS_DIR, v.file);
      if (!fs.existsSync(full)) {
        missing.push(v.file);
      }
    }
  }
  return missing;
}

const ARABIC_RE = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

export function containsArabic(text: string): boolean {
  return ARABIC_RE.test(String(text || ""));
}

export function preferredArabicFontId(): string {
  const byId = familyById();
  if (byId.has("noto-sans-arabic")) return "noto-sans-arabic";
  for (const fam of byId.values()) {
    if ((fam.scripts || []).includes("arabic")) return fam.id;
  }
  return "inter";
}
