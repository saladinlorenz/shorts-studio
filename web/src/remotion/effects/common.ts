import { random } from "remotion";
import type { MediaUtilsAudioData } from "@remotion/media-utils";

import { EASING_CURVES } from "../animations";
import type { EasingName } from "../types";

/**
 * Socle commun des effets du studio.
 *
 * Un effet est toujours pilote par la frame de la composition et par la graine
 * du projet : jamais Date.now(), requestAnimationFrame ni Math.random(). Deux
 * rendus des memes props produisent donc les memes images, en aperçu comme a
 * l'export (cahier des charges, section 8).
 */

export type EffectScope = "layer" | "scene" | "overlay";

export interface EffectParams {
  [key: string]: number | boolean | string;
}

export interface Effect {
  id: string;
  label: string;
  scope: EffectScope;
  params: EffectParams;
  /** Repris du catalogue serveur : dit si l'effet a besoin d'une piste mesuree. */
  needs_audio?: boolean;
}

/** Energies mesurees sur la vraie piste du projet (voir effects/audio.ts). */
export interface AudioEnergy {
  bass: number;
  mid: number;
  treble: number;
  level: number;
  samples: number[];
}

export interface EffectCtx {
  /** Identifiant stable : sert a nommer les filtres SVG sans collision. */
  uid: string;
  /** Frame absolue dans la composition. */
  frame: number;
  /** Frames ecoulees depuis le debut de la scene. */
  local: number;
  sceneFrames: number;
  fps: number;
  width: number;
  height: number;
  seed: number;
  /** URL resolue de la piste mesuree, null si le projet n'a pas de musique. */
  audioSrc: string | null;
  /** Null quand le projet n'a pas de piste audio chargee. */
  audio: AudioEnergy | null;
  /** Donnees decodées brutes : les effets en demandent la resolution exacte. */
  audioData: MediaUtilsAudioData | null;
}

/** Reglage numerique : une valeur absente ou mal typée retombe sur le defaut. */
export function num(params: EffectParams, key: string, def: number): number {
  const raw = params[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : def;
}

export function intg(params: EffectParams, key: string, def: number): number {
  return Math.round(num(params, key, def));
}

export function flag(params: EffectParams, key: string, def: boolean): boolean {
  const raw = params[key];
  if (typeof raw === "boolean") return raw;
  if (typeof raw === "string") return raw.toLowerCase() === "true";
  return def;
}

export function col(params: EffectParams, key: string, def: string): string {
  const raw = params[key];
  return typeof raw === "string" && /^#[0-9a-fA-F]{6}$/.test(raw.trim()) ? raw.trim() : def;
}

export function pick(params: EffectParams, key: string, def: string): string {
  const raw = params[key];
  return typeof raw === "string" && raw.trim() ? raw.trim() : def;
}

export function text(params: EffectParams, key: string, def: string): string {
  const raw = params[key];
  return typeof raw === "string" ? raw : def;
}

export function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

export function clamp01(value: number): number {
  return clamp(value, 0, 1);
}

/** Pseudo-aleatoire deterministe : graine du projet + identifiant de la cible. */
export function rnd(ctx: EffectCtx, salt: string, index: number): number {
  return random(`${ctx.seed}|${ctx.uid}|${salt}|${index}`);
}

/** Pseudo-aleatoire qui se renouvelle tous les `every` frames (glitch, fuite de lumiere). */
export function rndStep(ctx: EffectCtx, salt: string, index: number, every: number): number {
  const step = Math.floor(ctx.local / Math.max(1, every));
  return random(`${ctx.seed}|${ctx.uid}|${salt}|${index}|${step}`);
}

export function curve(name: string): (t: number) => number {
  return EASING_CURVES[name as EasingName] ?? EASING_CURVES.ease_out_cubic;
}

/** Avancement 0..1 d'une sequence dans la scene, courbe appliquee. */
export function ramp(
  ctx: EffectCtx,
  delayFrames: number,
  durationFrames: number,
  easing = "ease_out_cubic",
): number {
  const local = ctx.local - delayFrames;
  if (local <= 0) return 0;
  const span = Math.max(1, durationFrames);
  if (local >= span) return 1;
  return curve(easing)(local / span);
}

/** Progression lineaire 0..1 sur toute la duree de la scene. */
export function sceneProgress(ctx: EffectCtx): number {
  return clamp01(ctx.local / Math.max(1, ctx.sceneFrames - 1));
}

/** Nom d'identifiant pour un filtre SVG, unique par cible et par effet. */
export function filterId(ctx: EffectCtx, suffix: string): string {
  return `fx-${ctx.uid}-${suffix}`.replace(/[^a-zA-Z0-9_-]/g, "-");
}

/** Un <filter> SVG applique a un sous-arbre : meme mecanisme en aperçu et en rendu. */
export function svgFilterUrl(ctx: EffectCtx, suffix: string): string {
  return `url(#${filterId(ctx, suffix)})`;
}
