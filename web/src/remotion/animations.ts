import { spring } from "remotion";
import type { AnimationSettings, EasingName } from "./types";

/**
 * Animations pilotees par la frame de la composition uniquement.
 *
 * Aucune de ces fonctions ne lit l'heure wall-clock et aucune n'utilise de
 * timer : deux executions avec les memes props donnent les memes images, en
 * aperçu comme a l'export (cahier des charges, section 8).
 */

export interface UnitVisual {
  opacity: number;
  translateX: number;
  translateY: number;
  scale: number;
  /** Fraction du calque encore masquee par le bandeau de revelation (0..1). */
  revealHidden: number;
}

export const EASING_CURVES: Record<EasingName, (t: number) => number> = {
  linear: (t) => t,
  ease_out_cubic: (t) => 1 - Math.pow(1 - t, 3),
  ease_out_quint: (t) => 1 - Math.pow(1 - t, 5),
  spring: (t) => t,
};

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** Avancement d'entree d'UNE unite (bloc, ligne ou mot), 0 -> 1. */
export function entranceProgress(
  frame: number,
  unitStartFrame: number,
  inFrames: number,
  easing: EasingName,
  settings: AnimationSettings,
  fps: number,
): number {
  if (settings.in === "none") return 1;
  const local = frame - unitStartFrame;
  if (local < 0) return 0;
  if (easing === "spring") {
    return spring({
      frame: local,
      fps,
      durationInFrames: Math.max(1, inFrames),
      config: {
        damping: settings.spring?.damping ?? 16,
        stiffness: settings.spring?.stiffness ?? 140,
        mass: settings.spring?.mass ?? 1,
      },
    });
  }
  if (inFrames <= 0) return 1;
  const curve = EASING_CURVES[easing] ?? EASING_CURVES.ease_out_cubic;
  return curve(clamp01(local / inFrames));
}

/** Sortie lineaire a la fin de la presence du calque. */
export function exitProgress(frame: number, outStartFrame: number, outFrames: number): number {
  if (outFrames <= 0) return 1;
  if (frame <= outStartFrame) return 1;
  return clamp01(1 - (frame - outStartFrame) / outFrames);
}

/**
 * Etat visuel d'une unite d'animation.
 *
 * @param heightPx hauteur de la composition : les distances sont exprimees en
 *                 fraction de hauteur, donc l'animation ne change pas avec la
 *                 resolution.
 */
export function unitVisual(
  frame: number,
  settings: AnimationSettings,
  unitIndex: number,
  args: {
    startFrame: number;
    inFrames: number;
    staggerFrames: number;
    outStartFrame: number;
    outFrames: number;
    easing: EasingName;
    springConfig: AnimationSettings["spring"];
    fps: number;
    heightPx: number;
  },
): UnitVisual {
  const unitStart = args.startFrame + unitIndex * args.staggerFrames;
  const progress = entranceProgress(frame, unitStart, args.inFrames, args.easing, settings, args.fps);
  const exit = args.outFrames > 0 && settings.out === "fade" ? exitProgress(frame, args.outStartFrame, args.outFrames) : 1;
  const distance = (settings.distance ?? 0.06) * args.heightPx;
  const eased = clamp01(progress);

  const visual: UnitVisual = { opacity: eased * exit, translateX: 0, translateY: 0, scale: 1, revealHidden: 0 };

  switch (settings.in) {
    case "fade":
      break;
    case "slide_up":
      visual.translateY = (1 - progress) * distance;
      break;
    case "slide_left":
      visual.translateX = (1 - progress) * -distance;
      break;
    case "scale":
      visual.scale = 0.86 + progress * 0.14;
      break;
    case "mask_reveal":
      visual.revealHidden = clamp01(1 - progress);
      visual.translateX = (1 - eased) * distance * 0.35;
      break;
    case "none":
      visual.opacity = exit;
      break;
  }
  if (settings.in === "fade" || settings.in === "mask_reveal") {
    visual.opacity = clamp01(visual.opacity);
  }
  return visual;
}

/** Decoupe le texte en unites d'animation (bloc, lignes ou mots). */
export function splitUnits(text: string, unit: AnimationSettings["unit"]): string[] {
  if (unit === "block") return [text];
  if (unit === "line") {
    const lines = text.split("\n").filter((l) => l.trim().length > 0);
    return lines.length ? lines : [text];
  }
  const words = text.split(/(\s+)/);
  return words.length ? words : [text];
}

/** Index visible ignore les blancs quand on compte les mots. */
export function isWordUnit(unit: string): boolean {
  return unit.trim().length > 0;
}

export function normalizeWord(word: string): string {
  return word
    .toLowerCase()
    .replace(/[.,;:!?"“”'’()]/g, "")
    .trim();
}
