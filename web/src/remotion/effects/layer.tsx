import React from "react";
import { spring } from "remotion";

import type { Effect, EffectCtx, EffectParams } from "./common";
import {
  clamp,
  clamp01,
  col,
  flag,
  intg,
  num,
  ramp,
  sceneProgress,
} from "./common";
import { channelDecor, glitchDecor, type Decorator } from "./channels";
import type { LayerEffectId } from "./registry";

/**
 * Effets de calque : transformees, mises en page lettre a lettre et copies
 * colorees. Ils ne remplacent pas l'animation du calque (entree, sortie,
 * decalage) : ils s'y ajoutent, ce qui permet de combiner un masque progressif
 * et un ressort, par exemple.
 *
 * Tout est exprime en frames et en graine de projet. Aucun timer, aucun
 * Math.random().
 */

/** Ce qu'un effet ajoute au contenant du calque. */
export interface LayerFx {
  /** Transformee supplementaire, appliquee apres celle de l'animation. */
  transform: string;
  /** Filtres CSS supplementaires (flou, luminosite...). */
  filter: string;
  opacity: number;
  /** Perspective 3D du parent, si l'effet en a besoin. */
  perspectivePx: number | null;
  /** Les effets 3D empilent les faces arriere de leurs enfants. */
  transformStyle: "preserve-3d" | null;
  /** Mise en page lettre a lettre : remplace le decoupage par unite. */
  letterTransform: ((index: number, total: number, letters: string[]) => React.CSSProperties | null) | null;
  /** Style du conteneur immediate des lettres (taille de police, inline-block...). */
  letterContainer: React.CSSProperties | null;
  /** Emballe le contenu deja rendu (copies, plateaux, reflets). */
  decorate: ((inner: React.ReactNode) => React.ReactNode) | null;
}

const NEUTRAL: LayerFx = {
  transform: "",
  filter: "",
  opacity: 1,
  perspectivePx: null,
  transformStyle: null,
  letterTransform: null,
  letterContainer: null,
  decorate: null,
};

/** Ce qu'un effet apporte au calque ; les effets d'un meme calque se cumulent. */
interface Fragment {
  transform?: string;
  filter?: string;
  opacity?: number;
  perspectivePx?: number | null;
  transformStyle?: "preserve-3d" | null;
  layout?: LetterLayout;
  decorate?: Decorator;
}

function join(parts: string[]): string {
  return parts.filter(Boolean).join(" ");
}

/** Repartit les calques d'une scene pour que chaque filtre SVG ait son nom. */
export function layerUid(sceneId: string, layerId: string): string {
  return `${sceneId}-${layerId}`.replace(/[^a-zA-Z0-9_-]/g, "-");
}

function springFor(params: EffectParams) {
  return {
    damping: num(params, "damping", 12),
    stiffness: num(params, "stiffness", 180),
    mass: num(params, "mass", 1),
  };
}

// --- Transformees -----------------------------------------------------------

function springPop(effect: Effect, ctx: EffectCtx): Fragment {
  const p = spring({
    frame: Math.max(0, ctx.local),
    fps: ctx.fps,
    config: springFor(effect.params),
  });
  const overshoot = num(effect.params, "overshoot", 1.18);
  const rotate = num(effect.params, "rotate_deg", -8);
  return {
    transform: `scale(${1 + (overshoot - 1) * (1 - p)}) rotate(${(rotate * (1 - p)).toFixed(3)}deg)`,
    opacity: clamp01(p * 1.4),
  };
}

function parallax(effect: Effect, ctx: EffectCtx): Fragment {
  const params = effect.params;
  const depth = num(params, "depth", 0.6);
  const p = sceneProgress(ctx);
  const tx = (p - 0.5) * num(params, "drift_x", 0.12) * ctx.width * depth;
  const ty = (p - 0.5) * num(params, "drift_y", -0.05) * ctx.height * depth;
  const scale = num(params, "scale_from", 1.04) + (num(params, "scale_to", 1) - num(params, "scale_from", 1.04)) * p;
  return {
    transform: `translate3d(${tx.toFixed(2)}px, ${ty.toFixed(2)}px, ${(depth - 0.5) * -120}px) scale(${scale.toFixed(4)})`,
  };
}

function audioPulse(effect: Effect, ctx: EffectCtx): Fragment {
  const params = effect.params;
  const band = String(params.band ?? "bass");
  const energy = ctx.audio ? clamp01(ctx.audio[band as "bass" | "mid" | "treble" | "level"] ?? 0) : 0;
  // Sans piste mesuree, un battement regulier prend le relais : le reglage
  // reste visible, l'avertissement serveur dit deja que ce n'est pas de l'audio reel.
  const beat = ctx.audio ? energy : 0.5 + 0.5 * Math.sin((ctx.local / Math.max(1, ctx.fps)) * Math.PI * 2 * 1.6);
  const smoothing = num(params, "smoothing", 0.6);
  const shaped = clamp01(beat * (1 - smoothing) + beat * smoothing);
  const scale = num(params, "min_scale", 0.97) + (num(params, "max_scale", 1.14) - num(params, "min_scale", 0.97)) * shaped;
  const glow = num(params, "glow", 18) * shaped;
  return {
    transform: `scale(${scale.toFixed(4)})`,
    filter: glow > 0.5 ? `drop-shadow(0 0 ${glow.toFixed(1)}px rgba(255,255,255,0.55))` : "",
  };
}

// --- Mise en page lettre a lettre ------------------------------------------

export interface LetterLayout {
  perLetter: (index: number, total: number, letter: string) => React.CSSProperties;
  container: React.CSSProperties;
  perspectivePx: number | null;
}

function kineticLayout(effect: Effect, ctx: EffectCtx, fontSizePx: number): LetterLayout {
  const params = effect.params;
  const stagger = intg(params, "stagger_frames", 2);
  const rise = num(params, "rise", 0.12) * ctx.height;
  const rotate = num(params, "rotate_deg", -12);
  const blur = num(params, "blur_px", 6);
  const config = springFor(params);
  return {
    container: { display: "inline-block" },
    perspectivePx: null,
    perLetter: (index) => {
      const p = spring({
        frame: Math.max(0, ctx.local - index * stagger),
        fps: ctx.fps,
        config: { ...config, damping: num(params, "damping", 12) },
      });
      const left = 1 - clamp01(p);
      return {
        display: "inline-block",
        whiteSpace: "pre",
        transform: `translateY(${(left * rise).toFixed(2)}px) rotate(${(left * rotate).toFixed(2)}deg)`,
        opacity: clamp01(p * 1.3),
        filter: left > 0.02 ? `blur(${(left * blur).toFixed(2)}px)` : "none",
        fontSize: `${fontSizePx}px`,
      };
    },
  };
}

function cylinderLayout(effect: Effect, ctx: EffectCtx): LetterLayout {
  const params = effect.params;
  const radius = intg(params, "radius_px", 420);
  const arc = num(params, "arc_deg", 150);
  const start = num(params, "rotation_deg", -60);
  const spin = flag(params, "spin", true) ? num(params, "spin_deg_per_s", 24) * (ctx.local / ctx.fps) : 0;
  const back = num(params, "opacity_back", 0.15);
  return {
    container: { display: "inline-block", transformStyle: "preserve-3d" },
    perspectivePx: Math.max(600, radius * 3),
    perLetter: (index, total, letter) => {
      const step = total > 1 ? arc / (total - 1) : 0;
      const angle = start + spin + (index - (total - 1) / 2) * step;
      const visible = Math.cos((angle * Math.PI) / 180);
      return {
        display: "inline-block",
        whiteSpace: "pre",
        transform: `rotateY(${angle.toFixed(2)}deg) translateZ(${radius}px)`,
        opacity: visible >= 0 ? 1 : back,
        filter: visible >= 0 ? "none" : `blur(${(Math.abs(visible) * 3).toFixed(2)}px)`,
        // Une lettre de dos se lit a l'envers : on la retourne plutot que de la cacher.
        backfaceVisibility: letter.trim() ? "visible" : "hidden",
      };
    },
  };
}

function sphereLayout(effect: Effect, ctx: EffectCtx): LetterLayout {
  const params = effect.params;
  const radius = intg(params, "radius_px", 320);
  const lat = num(params, "lat_deg", 12);
  const spread = num(params, "spread_deg", 140);
  const start = num(params, "rotation_deg", 0);
  const spin = num(params, "spin_deg_per_s", 18) * (ctx.local / ctx.fps);
  const back = num(params, "opacity_back", 0.1);
  return {
    container: { display: "inline-block", transformStyle: "preserve-3d" },
    perspectivePx: Math.max(600, radius * 3),
    perLetter: (index, total) => {
      const step = total > 1 ? spread / (total - 1) : 0;
      const lon = start + spin + (index - (total - 1) / 2) * step;
      const cosLat = Math.cos((lat * Math.PI) / 180);
      const facing = Math.cos((lon * Math.PI) / 180) * cosLat;
      return {
        display: "inline-block",
        whiteSpace: "pre",
        transform: `rotateY(${lon.toFixed(2)}deg) rotateX(${(-lat).toFixed(2)}deg) translateZ(${radius}px)`,
        opacity: facing >= 0 ? clamp01(0.35 + facing) : back,
        filter: facing >= 0 ? "none" : "blur(2px)",
      };
    },
  };
}

// --- Emballages (copies, plateaux, reflets) --------------------------------

/**
 * Reflet qui traverse le calque.
 *
 * Une copie du contenu est eclairee puis masquee par une bande deplacee : le
 * reflet n'existe que la ou il y a des pixels (glyphes ou image). Une bande
 * pose en fusion additive, elle, blanchissait le fond derriere le texte.
 */
function shineDecor(effect: Effect, ctx: EffectCtx) {
  const params = effect.params;
  const period = intg(params, "period_frames", 50);
  const once = flag(params, "once", false);
  const width = clamp(num(params, "width", 0.22), 0.02, 1);
  const angle = num(params, "angle_deg", 20);
  const opacity = num(params, "opacity", 0.75);
  const boost = num(params, "intensity", 1.9);
  return (inner: React.ReactNode) => {
    const span = Math.max(1, once ? ctx.sceneFrames : period);
    const t = once ? clamp01(ctx.local / span) : (ctx.local % span) / span;
    if (once && ctx.local > span) return inner;
    const half = width * 50;
    const center = -half + t * (100 + width * 100);
    const stops = [
      `transparent ${(center - half).toFixed(2)}%`,
      `black ${center.toFixed(2)}%`,
      `transparent ${(center + half).toFixed(2)}%`,
    ].join(", ");
    const mask = `linear-gradient(${(90 + angle).toFixed(1)}deg, ${stops})`;
    return (
      <>
        {inner}
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            opacity,
            maskImage: mask,
            WebkitMaskImage: mask,
            maskRepeat: "no-repeat",
            WebkitMaskRepeat: "no-repeat",
            filter: `brightness(${boost.toFixed(2)}) saturate(0.8)`,
          }}
        >
          {inner}
        </div>
      </>
    );
  };
}

/** Plateau + recto : la carte se retourne et le contenu apparait a mi-parcours. */
function flipDecor(effect: Effect, ctx: EffectCtx) {
  const params = effect.params;
  const axis = String(params.axis ?? "y") === "x" ? "rotateX" : "rotateY";
  const duration = intg(params, "duration_frames", 40);
  const delay = intg(params, "delay_frames", 0);
  const plate = col(params, "plate_color", "#E2B458");
  return (inner: React.ReactNode) => (
    <>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: plate,
          transform: `${axis}(180deg)`,
          backfaceVisibility: "hidden",
          opacity: ctx.local < delay ? 0 : 1,
        }}
        aria-hidden
      />
      <div style={{ backfaceVisibility: "hidden" }}>{inner}</div>
    </>
  );
}

// --- Composition ------------------------------------------------------------

export interface LayerFxInput {
  effects: Effect[];
  ctx: EffectCtx;
  fontSizePx: number;
  /** Hauteur rendue du calque, pour les decoupes (glitch). */
  contentHeight: number;
}

/**
 * Un rendu par identifiant de calque. `Record<LayerEffectId, ...>` oblige a
 * couvrir toute la liste du registre : declarer un effet sans handler est une
 * erreur de compilation, pas un calque qui reste fige sans explication.
 */
type LayerHandler = (effect: Effect, ctx: EffectCtx, opts: { fontSizePx: number; contentHeight: number }) => Fragment;

const LAYER_HANDLERS: Record<LayerEffectId, LayerHandler> = {
  spring_pop: (effect, ctx) => springPop(effect, ctx),
  parallax_depth: (effect, ctx) => parallax(effect, ctx),
  audio_pulse: (effect, ctx) => audioPulse(effect, ctx),
  kinetic_letters: (effect, ctx, opts) => ({ layout: kineticLayout(effect, ctx, opts.fontSizePx) }),
  cylinder_wrap: (effect, ctx) => {
    const layout = cylinderLayout(effect, ctx);
    return { layout, perspectivePx: layout.perspectivePx, transformStyle: "preserve-3d" };
  },
  sphere_wrap: (effect, ctx) => {
    const layout = sphereLayout(effect, ctx);
    return { layout, perspectivePx: layout.perspectivePx, transformStyle: "preserve-3d" };
  },
  shine: (effect, ctx) => ({ decorate: shineDecor(effect, ctx) }),
  chromatic_aberration: (effect, ctx) => ({ decorate: channelDecor(effect, ctx, "layer") }),
  glitch_slices: (effect, ctx, opts) => ({ decorate: glitchDecor(effect, ctx, opts.contentHeight) }),
  flip_card: (effect, ctx) => {
    const duration = intg(effect.params, "duration_frames", 40);
    const delay = intg(effect.params, "delay_frames", 0);
    const p = ramp(ctx, delay, duration, "ease_out_cubic");
    return {
      transform: `rotateY(${(180 * (1 - p)).toFixed(2)}deg)`,
      perspectivePx: intg(effect.params, "perspective_px", 1200),
      transformStyle: "preserve-3d",
      decorate: flipDecor(effect, ctx),
    };
  },
};

/**
 * Fusionne les effets d'un calque en un seul style + un seul emballage.
 * Les reglages viennent du catalogue serveur ; un identifiant inconnu est
 * tout simplement ignore (la validation serveur I'a deja signale).
 */
export function applyLayerEffects({ effects, ctx, fontSizePx, contentHeight }: LayerFxInput): LayerFx {
  const scoped = effects.filter((effect) => effect.scope === "layer");
  if (!scoped.length) return NEUTRAL;

  const transforms: string[] = [];
  const filters: string[] = [];
  let opacity = 1;
  let perspectivePx: number | null = null;
  let transformStyle: "preserve-3d" | null = null;
  let layout: LetterLayout | null = null;
  const decorators: Decorator[] = [];

  const opts = { fontSizePx, contentHeight };
  for (const effect of scoped) {
    const handler = LAYER_HANDLERS[effect.id as LayerEffectId];
    if (!handler) continue;
    const part = handler(effect, ctx, opts);
    if (part.transform) transforms.push(part.transform);
    if (part.filter) filters.push(part.filter);
    if (typeof part.opacity === "number") opacity *= part.opacity;
    if (part.layout) layout = part.layout;
    if (part.perspectivePx !== undefined && part.perspectivePx !== null) perspectivePx = part.perspectivePx;
    if (part.transformStyle) transformStyle = part.transformStyle;
    if (part.decorate) decorators.push(part.decorate);
  }

  const activeLayout = layout;
  const style: LayerFx = {
    transform: join(transforms),
    filter: join(filters),
    opacity: clamp01(opacity),
    perspectivePx,
    transformStyle,
    letterTransform: activeLayout
      ? (index, total, letters) => activeLayout.perLetter(index, total, letters[index])
      : null,
    letterContainer: activeLayout ? activeLayout.container : null,
    decorate: decorators.length
      ? (inner) => decorators.reduce((acc, decorate) => decorate(acc), inner)
      : null,
  };
  return style;
}
