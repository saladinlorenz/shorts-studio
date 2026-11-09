import React from "react";

import type { EffectCtx, EffectParams } from "./common";
import { filterId, flag, intg, num, rndStep } from "./common";

/**
 * Emballages partages par les calques et les scenes : les effets qui dupliquent
 * le contenu (canaux de couleur, tranches de glitch) s'appliquent de la meme
 * facon sur un texte, une image ou une scene entiere.
 */

export type Decorator = (inner: React.ReactNode) => React.ReactNode;
/** Copies monocanales recomposees en fusion ecran : l'aberration chromatique. */
export function channelDecor(
  effect: { params: EffectParams },
  ctx: EffectCtx,
  scopeName: string,
  options?: { fill?: boolean },
): Decorator {
  const params = effect.params;
  // Portee scene : l'emballage doit garder la taille du parent. Un conteneur
  // « relative » auto-dimensionne a 0 x 0 (les calques sont absolus) et tous les
  // pourcentages de positionnement des calques retombent sur 0 : la scene se
  // colle en haut a gauche.
  const fill = options?.fill ?? false;
  const offset = num(params, "offset_px", 12);
  const angle = num(params, "angle_deg", 0);
  const animate = flag(params, "animate", true);
  const cycle = intg(params, "cycle_frames", 24);
  const rad = (angle * Math.PI) / 180;
  const wobble = animate ? 1 + 0.35 * Math.sin((ctx.local / Math.max(1, cycle)) * Math.PI * 2) : 1;
  const dx = Math.cos(rad) * offset * wobble;
  const dy = Math.sin(rad) * offset * wobble;
  const id = filterId({ ...ctx, uid: `${ctx.uid}-${scopeName}` }, "channels");
  return (inner: React.ReactNode) => (
    <>
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden focusable="false">
        <defs>
          {[
            ["r", "1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"],
            ["g", "0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0"],
            ["b", "0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"],
          ].map(([name, values]) => (
            <filter key={name} id={`${id}-${name}`} colorInterpolationFilters="sRGB">
              <feColorMatrix type="matrix" values={values} />
            </filter>
          ))}
        </defs>
      </svg>
      <div
        style={{
          position: fill ? "absolute" : "relative",
          inset: fill ? 0 : undefined,
          isolation: "isolate",
        }}
      >
        {[
          ["r", -dx, -dy],
          ["g", 0, 0],
          ["b", dx, dy],
        ].map(([name, tx, ty]) => (
          <div
            key={String(name)}
            style={{
              position: fill || name !== "r" ? "absolute" : "relative",
              inset: fill || name !== "r" ? 0 : undefined,
              filter: `url(#${id}-${name})`,
              mixBlendMode: name === "r" ? "normal" : "screen",
              transform: `translate(${(tx as number).toFixed(2)}px, ${(ty as number).toFixed(2)}px)`,
            }}
          >
            {inner}
          </div>
        ))}
      </div>
    </>
  );
}

export function glitchDecor(effect: { params: EffectParams }, ctx: EffectCtx, contentHeight: number): Decorator {
  const params = effect.params;
  const delay = intg(params, "delay_frames", 0);
  const duration = intg(params, "duration_frames", 24);
  const slices = intg(params, "slice_count", 8);
  const maxOffset = num(params, "max_offset", 0.08);
  const reroll = intg(params, "reroll_frames", 2);
  const intensity = num(params, "intensity", 0.55);
  return (inner: React.ReactNode) => {
    const active = ctx.local >= delay && ctx.local <= delay + duration;
    if (!active) return inner;
    const band = Math.max(1, contentHeight / slices);
    const copies = Array.from({ length: slices }, (_, index) => {
      const shift = (rndStep(ctx, "glitch", index, reroll) * 2 - 1) * maxOffset;
      const tint = rndStep(ctx, "tint", index, reroll);
      const top = index * band;
      return (
        <div
          key={index}
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: `${top}px`,
            height: `${band}px`,
            overflow: "hidden",
            transform: `translateX(${(shift * ctx.width).toFixed(2)}px)`,
            opacity: intensity,
            filter: tint > 0.66 ? "url(#fx-glitch-r)" : tint > 0.33 ? "url(#fx-glitch-c)" : "none",
          }}
        >
          <div style={{ transform: `translateY(${-top}px)` }}>{inner}</div>
        </div>
      );
    });
    return (
      <>
        <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden focusable="false">
          <defs>
            <filter id="fx-glitch-r" colorInterpolationFilters="sRGB">
              <feColorMatrix type="matrix" values="1 0 0 0 0.2  0 0 0 0 0  0 0 0.2 0 0  0 0 0 1 0" />
            </filter>
            <filter id="fx-glitch-c" colorInterpolationFilters="sRGB">
              <feColorMatrix type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 1 0 0.2  0 0 0 1 0" />
            </filter>
          </defs>
        </svg>
        {inner}
        {copies}
      </>
    );
  };
}
