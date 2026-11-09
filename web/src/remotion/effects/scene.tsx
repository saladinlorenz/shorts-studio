import React from "react";

import type { Effect, EffectCtx, EffectParams } from "./common";
import { clamp, clamp01, filterId, flag, intg, num, ramp } from "./common";
import { channelDecor, glitchDecor } from "./channels";

/**
 * Effets de scene : ils transforment la scene entiere (fond + calques).
 *
 * L'ordre d'application est celui d'une post-production : camera, deformation,
 * glitch et canaux, flou de profondeur, puis etalonnage et vignette. Deux
 * effets du meme role se disputent la meme place : seul le premier declare est
 * applique, et l'inspecteur le dit.
 */

/** Rendus predefinis : courbes de transfert, aucune table LUT externe. */
const LOOK_TABLES: Record<string, { r: string; g: string; b: string }> = {
  teal_orange: { r: "0 0.22 0.46 0.7 0.88 1", g: "0 0.16 0.38 0.62 0.82 0.97", b: "0.05 0.24 0.44 0.6 0.72 0.84" },
  bleute: { r: "0 0.1 0.24 0.44 0.64 0.84", g: "0 0.14 0.32 0.54 0.76 0.96", b: "0.08 0.3 0.5 0.68 0.84 1" },
  sepia: { r: "0.14 0.36 0.58 0.78 0.92 1", g: "0.08 0.28 0.5 0.7 0.86 0.98", b: "0.02 0.14 0.3 0.48 0.66 0.82" },
  bleu_nuit: { r: "0 0.06 0.16 0.3 0.5 0.7", g: "0 0.08 0.2 0.36 0.56 0.76", b: "0.12 0.32 0.5 0.68 0.84 1" },
  lavande: { r: "0.1 0.3 0.5 0.68 0.84 0.97", g: "0.04 0.18 0.36 0.56 0.76 0.92", b: "0.18 0.42 0.62 0.78 0.9 1" },
  noir_blanc: { r: "0 0.2 0.45 0.7 0.88 1", g: "0 0.2 0.45 0.7 0.88 1", b: "0 0.2 0.45 0.7 0.88 1" },
};

function pickFirst(effects: Effect[], ids: string[]): Effect | null {
  for (const id of ids) {
    const found = effects.find((e) => e.id === id);
    if (found) return found;
  }
  return null;
}

/** Travelling : la scene s'approche ou s'eloigne dans un espace en perspective. */
function dollyTransform(params: EffectParams, ctx: EffectCtx) {
  const p = ramp(ctx, 0, ctx.sceneFrames, String(params.easing ?? "ease_out_cubic"));
  const focal = intg(params, "perspective_px", 1600);
  const start = num(params, "start_z", -0.25);
  const end = num(params, "end_z", 0.08);
  const z = (start + (end - start) * p) * focal;
  const swing = Math.sin(p * Math.PI);
  return {
    perspective: `${focal}px`,
    transform: `translateZ(${z.toFixed(1)}px) rotateX(${(swing * num(params, "rotate_x_deg", 4)).toFixed(2)}deg) rotateY(${(
      swing * num(params, "rotate_y_deg", -6)
    ).toFixed(2)}deg)`,
  };
}

/** Surface liquide : turbulence SVG deplacee par feDisplacementMap. */
function LiquidDefs({ effect, ctx }: { effect: Effect; ctx: EffectCtx }) {
  const params = effect.params;
  const frequency = num(params, "frequency", 0.012);
  const octaves = intg(params, "octaves", 2);
  const displacement = num(params, "displacement", 42);
  const animated = flag(params, "animate", true);
  const cycle = intg(params, "cycle_frames", 40);
  const seed = Math.round(ctx.seed + num(params, "seed_shift", 0));
  // L'animation est pilote par la frame, pas par un timer SVG : la frame N
  // donne toujours la meme image, en aperçu comme a l'export.
  const phase = animated ? (ctx.local % Math.max(1, cycle)) / Math.max(1, cycle) : 0;
  const factor = 1 + 0.35 * Math.sin(phase * Math.PI * 2);
  const id = filterId(ctx, "liquid");
  return (
    <filter id={id} x="-12%" y="-12%" width="124%" height="124%" colorInterpolationFilters="sRGB">
      <feTurbulence
        type="fractalNoise"
        baseFrequency={`${(frequency * factor).toFixed(4)} ${(frequency * 1.6 * factor).toFixed(4)}`}
        numOctaves={octaves}
        seed={seed}
        result="map"
      />
      <feDisplacementMap
        in="SourceGraphic"
        in2="map"
        scale={(displacement * (animated ? 0.8 + 0.4 * factor : 1)).toFixed(2)}
        xChannelSelector="R"
        yChannelSelector="G"
      />
    </filter>
  );
}

/** Etalonnage : saturation, exposition, contraste puis courbe du rendu choisi. */
function GradeDefs({ effect, ctx }: { effect: Effect; ctx: EffectCtx }) {
  const params = effect.params;
  const tables = LOOK_TABLES[String(params.look ?? "teal_orange")] ?? LOOK_TABLES.teal_orange;
  const contrast = num(params, "contrast", 1);
  const exposure = num(params, "exposure", 1);
  const saturation = num(params, "saturation", 1);
  const id = filterId(ctx, "grade");
  return (
    <filter id={id} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
      <feColorMatrix type="saturate" values={saturation.toFixed(3)} />
      <feComponentTransfer>
        <feFuncR type="linear" slope={contrast.toFixed(3)} intercept={(((exposure - 1) * 0.5) - (contrast - 1) * 0.5).toFixed(4)} />
        <feFuncG type="linear" slope={contrast.toFixed(3)} intercept={(((exposure - 1) * 0.5) - (contrast - 1) * 0.5).toFixed(4)} />
        <feFuncB type="linear" slope={contrast.toFixed(3)} intercept={(((exposure - 1) * 0.5) - (contrast - 1) * 0.5).toFixed(4)} />
      </feComponentTransfer>
      <feComponentTransfer>
        <feFuncR type="table" tableValues={tables.r} />
        <feFuncG type="table" tableValues={tables.g} />
        <feFuncB type="table" tableValues={tables.b} />
      </feComponentTransfer>
    </filter>
  );
}

/** Flou progressif : copies de plus en plus floues, chacune limite a sa couronne. */
function DepthBlur({ effect, ctx, children }: { effect: Effect; ctx: EffectCtx; children: React.ReactNode }) {
  const params = effect.params;
  const focus = num(params, "focus_y", 0.45);
  const max = num(params, "blur_px", 18);
  const falloff = clamp(num(params, "falloff", 0.8), 0.15, 2);
  const axis = flag(params, "top_to_bottom", true) ? "to bottom" : "to right";
  const levels = [1, 2, 3];
  return (
    <>
      {children}
      {levels.map((level) => {
        const radius = (level / 3) * falloff;
        const inner = clamp(focus - radius, 0, 1);
        const outer = clamp(focus + radius, 0, 1);
        const mask = `linear-gradient(${axis}, black ${(Math.max(0, inner - 0.08) * 100).toFixed(1)}%, transparent ${(
          inner * 100
        ).toFixed(1)}%, transparent ${(outer * 100).toFixed(1)}%, black ${Math.min(1, outer + 0.08) * 100}%)`;
        return (
          <div
            key={level}
            style={{
              position: "absolute",
              inset: 0,
              filter: `blur(${((max * level) / 3).toFixed(2)}px)`,
              WebkitMaskImage: mask,
              maskImage: mask,
            }}
          >
            {children}
          </div>
        );
      })}
    </>
  );
}

interface Props {
  effects: Effect[];
  ctx: EffectCtx;
  children: React.ReactNode;
}

export const SceneEffects: React.FC<Props> = ({ effects, ctx, children }) => {
  const sceneEffects = effects.filter((e) => e.scope === "scene");
  if (!sceneEffects.length) return <>{children}</>;

  const camera = pickFirst(sceneEffects, ["perspective_dolly"]);
  const liquid = pickFirst(sceneEffects, ["liquid_contours"]);
  const grade = pickFirst(sceneEffects, ["color_grade"]);
  const blur = pickFirst(sceneEffects, ["depth_blur"]);
  const glitch = pickFirst(sceneEffects, ["glitch_slices"]);
  const channels = pickFirst(sceneEffects, ["chromatic_aberration"]);

  // 1. duplication du contenu (glitch, canaux de couleur)
  let content: React.ReactNode = children;
  if (glitch) content = glitchDecor(glitch, { ...ctx, uid: `${ctx.uid}-glitch` }, ctx.height)(content);
  if (channels) content = channelDecor(channels, { ...ctx, uid: `${ctx.uid}-chroma` }, "scene", { fill: true })(content);

  // 2. flou de profondeur (nouvelles copies masquees)
  if (blur) {
    content = (
      <DepthBlur effect={blur} ctx={{ ...ctx, uid: `${ctx.uid}-blur` }}>
        {content}
      </DepthBlur>
    );
  }

  // 3. deformation liquide
  if (liquid) {
    content = (
      <div
        style={{
          position: "absolute",
          inset: 0,
          filter: `url(#${filterId({ ...ctx, uid: `${ctx.uid}-liquid` }, "liquid")})`,
        }}
      >
        {content}
      </div>
    );
  }

  // 4. camera
  if (camera) {
    const { perspective, transform } = dollyTransform(camera.params, ctx);
    content = (
      <div style={{ position: "absolute", inset: 0, perspective, transformStyle: "preserve-3d" }}>
        <div style={{ position: "absolute", inset: 0, transform, transformOrigin: "50% 50%" }}>{content}</div>
      </div>
    );
  }

  // 5. etalonnage : la copie forcee se pose sur l'original, melange par opacite
  const strength = grade ? clamp01(num(grade.params, "strength", 0.75)) : 0;
  const vignetteStrength = grade ? num(grade.params, "vignette", 0) : 0;

  return (
    <>
      {liquid || grade ? (
        <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden focusable="false">
          <defs>
            {liquid ? <LiquidDefs effect={liquid} ctx={{ ...ctx, uid: `${ctx.uid}-liquid` }} /> : null}
            {grade ? <GradeDefs effect={grade} ctx={{ ...ctx, uid: `${ctx.uid}-grade` }} /> : null}
          </defs>
        </svg>
      ) : null}
      <div style={{ position: "absolute", inset: 0 }}>{content}</div>
      {grade ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            opacity: strength,
            filter: `url(#${filterId({ ...ctx, uid: `${ctx.uid}-grade` }, "grade")})`,
          }}
        >
          {content}
        </div>
      ) : null}
      {vignetteStrength > 0.001 ? (
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            background: `radial-gradient(120% 90% at 50% 50%, transparent 42%, rgba(0,0,0,${(
              vignetteStrength * 0.45
            ).toFixed(3)}) 78%, rgba(0,0,0,${(vignetteStrength * 0.78).toFixed(3)}) 100%)`,
          }}
        />
      ) : null}
    </>
  );
};
