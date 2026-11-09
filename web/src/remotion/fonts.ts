import { staticFile } from "remotion";

import catalog from "./fontCatalog.json";

/**
 * Source unique des polices du studio : web/src/remotion/fontCatalog.json.
 *
 * Les fichiers .ttf vivent dans web/public/fonts. Le Player les recoit sous
 * /fonts/<fichier> (web/dist servis par l'app FastAPI) et le navigateur de
 * rendu sous /public/fonts/<fichier> : staticFile() applique ce seul prefixe
 * selon le contexte, donc l'aperçu et l'export chargent le meme fichier.
 *
 * Les polices systeme Windows ne sont pas utilisees : leur licence ne permet
 * ni de les servir ni de les embarquer dans une production.
 */

export interface FontWeight {
  weight: number;
  style: string;
  file: string;
}

export interface FontFamily {
  id: string;
  css_family: string;
  label: string;
  role: string;
  license: string;
  source: string;
  retrieved: string;
  weights: FontWeight[];
}

export const FONT_CATALOG = catalog as unknown as { version: number; families: FontFamily[] };

export const FONT_FAMILIES: FontFamily[] = FONT_CATALOG.families;

const FALLBACK_CSS = "Inter, sans-serif";

/** Chemin d'un fichier de police, resolllu selon le contexte de rendu. */
export function fontUrl(file: string): string {
  return staticFile(`fonts/${file}`);
}

export function familyById(id: string): FontFamily | undefined {
  return FONT_FAMILIES.find((f) => f.id === id);
}

/** Nom CSS a utiliser dans font-family. */
export function cssFamily(id: string | undefined): string {
  const family = id ? familyById(id) : undefined;
  if (!family) return FALLBACK_CSS;
  return `${family.css_family}, ${family.role === "serif" ? "serif" : "sans-serif"}`;
}

export function weightsOf(id: string): number[] {
  return familyById(id)?.weights.map((w) => w.weight) ?? [];
}

/** Poids disponible le plus proche (le navigateur ne dispose que des poids declares). */
export function nearestWeight(id: string, wanted: number): number {
  const available = weightsOf(id);
  if (available.length === 0) return wanted;
  return available.reduce((best, w) => (Math.abs(w - wanted) < Math.abs(best - wanted) ? w : best), available[0]);
}

const STYLE_ELEMENT_ID = "studio-font-faces";
let injected = false;

/** Declare les @font-face du catalogue une seule fois dans le document. */
export function injectFontFaces(): void {
  if (injected || typeof document === "undefined") return;
  if (document.getElementById(STYLE_ELEMENT_ID)) {
    injected = true;
    return;
  }
  const css = FONT_FAMILIES.flatMap((family) =>
    family.weights.map(
      (weight) => `@font-face {
  font-family: '${family.css_family}';
  font-style: ${weight.style};
  font-weight: ${weight.weight};
  font-display: block;
  src: url('${fontUrl(weight.file)}') format('truetype');
}`,
    ),
  ).join("\n");
  const style = document.createElement("style");
  style.id = STYLE_ELEMENT_ID;
  style.textContent = css;
  document.head.appendChild(style);
  injected = true;
}

const loadedRequests = new Set<string>();

/** Charge les polices utilisees par un projet AVANT mesure et rendu. */
export async function loadFontsFor(
  wants: Array<{ family: string; weight: number }>,
  sampleSizePx = 64,
): Promise<void> {
  if (typeof document === "undefined") return;
  injectFontFaces();
  const jobs = wants.map(({ family, weight }) => {
    const css = cssFamily(family);
    const key = `${weight} ${sampleSizePx}px ${css}`;
    if (loadedRequests.has(key)) return null;
    loadedRequests.add(key);
    return document.fonts.load(key, "éàçùÆ”“— 0123456789");
  });
  await Promise.all(jobs.filter(Boolean));
  await document.fonts.ready;
}

/** Toutes les familles du catalogue, pour un prechargement complet. */
export async function preloadAllFonts(): Promise<void> {
  const wants = FONT_FAMILIES.flatMap((family) =>
    family.weights.map((w) => ({ family: family.id, weight: w.weight })),
  );
  await loadFontsFor(wants);
}

/** Licence d'une famille, telle qu'enregistree ; jamais devinee. */
export function licenseOf(id: string): { license: string; source: string; retrieved: string } {
  const family = familyById(id);
  if (!family) return { license: "inconnue", source: "", retrieved: "" };
  return { license: family.license, source: family.source, retrieved: family.retrieved };
}
