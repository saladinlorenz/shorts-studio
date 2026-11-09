import { cssFamily, nearestWeight } from "../../remotion/fonts";
import type { Project } from "../../api/client";
import { layerById } from "./edit";

/**
 * Detection des debordements de texte mesuree dans le NAVIGATEUR, avec la
 * police reellement chargee et la meme feuille de style que la composition.
 *
 * C'est la source pertinente : estimer le debordement avec un autre moteur
 * de mesure donnerait un resultat different de celui de l'aperçu et de
 * l'export. Le calcul n'est donc pas duplique en Python.
 */

export interface TextFit {
  sceneId: string;
  layerId: string;
  label: string;
  lines: number;
  textHeightPx: number;
  boxHeightPx: number;
  topPx: number;
  bottomPx: number;
  frameHeightPx: number;
  overflow: boolean;
  clippedWords: number;
}

const SAFE_TOP_RATIO = 0.04;
const SAFE_BOTTOM_RATIO = 0.96;

function host(): HTMLDivElement {
  const id = "studio-measure-host";
  let node = document.getElementById(id) as HTMLDivElement | null;
  if (!node) {
    node = document.createElement("div");
    node.id = id;
    node.style.position = "absolute";
    node.style.left = "-99999px";
    node.style.top = "0";
    node.style.visibility = "hidden";
    node.style.pointerEvents = "none";
    document.body.appendChild(node);
  }
  return node;
}

export function measureTextLayer(
  project: Project,
  sceneId: string,
  resolvedLayer: any,
  frame: { width: number; height: number },
): TextFit | null {
  const layer = layerById(project, sceneId, resolvedLayer.id);
  if (!layer || layer.type !== "text" || layer.hidden) return null;
  if (!String(layer.text ?? "").trim()) return null;

  const probe = document.createElement("div");
  probe.style.position = "absolute";
  probe.style.left = "0";
  probe.style.top = "0";
  probe.style.width = `${(layer.position.width ?? 0.8) * frame.width}px`;
  probe.style.fontFamily = cssFamily(resolvedLayer.font_family);
  probe.style.fontWeight = String(nearestWeight(resolvedLayer.font_family, resolvedLayer.font_weight));
  probe.style.fontSize = `${resolvedLayer.font_size_px}px`;
  probe.style.lineHeight = String(resolvedLayer.line_height ?? 1.2);
  probe.style.letterSpacing = `${resolvedLayer.letter_spacing_em ?? 0}em`;
  probe.style.textAlign = resolvedLayer.align ?? "center";
  probe.style.direction = resolvedLayer.direction ?? "ltr";
  probe.style.wordBreak = "break-word";
  probe.style.whiteSpace = "pre-wrap";
  probe.textContent = String(layer.text);

  const container = host();
  container.innerHTML = "";
  container.appendChild(probe);
  const textHeight = probe.offsetHeight;
  const lineCount = probe.getClientRects().length || 1;
  container.removeChild(probe);

  const centerY = (layer.position.y ?? 0.5) * frame.height;
  const topPx = centerY - textHeight / 2;
  const bottomPx = centerY + textHeight / 2;
  const limitTop = frame.height * SAFE_TOP_RATIO;
  const limitBottom = frame.height * SAFE_BOTTOM_RATIO;
  const overflow = topPx < limitTop - 1 || bottomPx > limitBottom + 1;

  // Mots hors cadre : estimation par la hauteur qui depasse la zone sure.
  const lineHeightPx = (resolvedLayer.font_size_px ?? 40) * (resolvedLayer.line_height ?? 1.2);

  return {
    sceneId,
    layerId: layer.id,
    label: String(layer.role ?? layer.id),
    lines: lineCount,
    textHeightPx: Math.round(textHeight),
    boxHeightPx: Math.round(limitBottom - limitTop),
    topPx: Math.round(topPx),
    bottomPx: Math.round(bottomPx),
    frameHeightPx: frame.height,
    overflow,
    clippedWords: overflow ? Math.max(1, Math.round((textHeight - (limitBottom - limitTop)) / lineHeightPx)) : 0,
  };
}

export function measureProject(
  project: Project,
  resolved: any,
): TextFit[] {
  if (!resolved?.scenes) return [];
  const frame = { width: resolved.width ?? 1080, height: resolved.height ?? 1920 };
  const out: TextFit[] = [];
  for (const scene of resolved.scenes) {
    if (scene.hidden) continue;
    for (const layer of scene.layers ?? []) {
      if (layer.type !== "text") continue;
      const fit = measureTextLayer(project, scene.id, layer, frame);
      if (fit) out.push(fit);
    }
  }
  return out;
}
