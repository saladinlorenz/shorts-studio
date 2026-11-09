import React from "react";
import { interpolate } from "remotion";
import { getBoundingBox, getLength, interpolatePath, normalizePath } from "@remotion/paths";
import { visualizeAudio, visualizeAudioWaveform } from "@remotion/media-utils";

import type { Effect, EffectCtx } from "./common";
import { loopedFrame } from "./audio";
import { clamp, clamp01, col, curve, filterId, flag, intg, num, pick, ramp, rnd, text as textParam } from "./common";
import type { OverlayEffectId } from "./registry";

/**
 * Effets plein cadre : ils se posent par-dessus la scene, sans la modifier.
 * Chacun se lit independamment, ce qui permet d'accumuler un grain, des
 * scanlines et un spectre sans que l'un cache l'autre.
 */

type OverlayProps = { effect: Effect; ctx: EffectCtx };

const FRAME: React.CSSProperties = { position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" };

// --- Matiere et matteresque -------------------------------------------------

const Scanlines: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const line = Math.max(2, intg(params, "line_height_px", 6));
  const thickness = clamp(intg(params, "thickness_px", 1), 1, line);
  const opacity = num(params, "opacity", 0.35);
  const color = col(params, "color", "#000000");
  const roll = flag(params, "roll", true);
  const speed = num(params, "roll_speed", 0.6);
  const offset = roll ? ((ctx.local * speed) % line + line) % line : 0;
  return (
    <div
      aria-hidden
      style={{
        ...FRAME,
        opacity,
        backgroundImage: `repeating-linear-gradient(to bottom, ${color} 0 ${thickness}px, transparent ${thickness}px ${line}px)`,
        backgroundPositionY: `${-offset}px`,
      }}
    />
  );
};

const WhiteNoise: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const opacity = num(params, "opacity", 0.22);
  const scale = num(params, "scale", 14);
  const animated = flag(params, "animated", true);
  const cycle = intg(params, "cycle_frames", 3);
  const kind = pick(params, "kind", "fractalNoise");
  const octaves = intg(params, "octaves", 2);
  const id = filterId(ctx, "noise");
  // Le grain se renouvelle par pas de frames deterministes : la frame N donne
  // toujours la meme image, en aperçu comme a l'export.
  const step = animated ? Math.floor(ctx.local / Math.max(1, cycle)) : 0;
  const seed = Math.round(ctx.seed) + step * 7;
  const frequency = clamp(1 / Math.max(1, scale), 0.005, 0.9);
  return (
    <div style={{ ...FRAME, opacity }}>
      <svg width="100%" height="100%" viewBox={`0 0 ${ctx.width} ${ctx.height}`} preserveAspectRatio="none" aria-hidden>
        <defs>
          <filter id={id} x="0" y="0" width="100%" height="100%" filterUnits="objectBoundingBox" primitiveUnits="userSpaceOnUse">
            <feTurbulence type={kind} baseFrequency={frequency.toFixed(4)} numOctaves={octaves} seed={seed} stitchTiles="stitch" result="n" />
            <feColorMatrix
              type="matrix"
              values="0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0.33 0.33 0.33 0 0  0 0 0 0 1"
              in="n"
            />
          </filter>
        </defs>
        <rect width={ctx.width} height={ctx.height} filter={`url(#${id})`} />
      </svg>
    </div>
  );
};

const LightLeak: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const intensity = num(params, "intensity", 0.4);
  const size = num(params, "size", 0.75);
  const cycle = intg(params, "cycle_frames", 180);
  const blend = pick(params, "blend", "screen") as React.CSSProperties["mixBlendMode"];
  const colorA = col(params, "color_a", "#FF6B3D");
  const colorB = col(params, "color_b", "#FFD166");
  const step = Math.floor(ctx.local / Math.max(1, cycle));
  const phase = clamp01((ctx.local % Math.max(1, cycle)) / Math.max(1, cycle));
  const drift = Math.sin(phase * Math.PI);
  const blobs = [
    { color: colorA, x: 0.1 + rnd(ctx, "leak-a", step) * 0.25, y: 0.15 + rnd(ctx, "leak-a-y", step) * 0.3 },
    { color: colorB, x: 0.65 + rnd(ctx, "leak-b", step) * 0.3, y: 0.55 + rnd(ctx, "leak-b-y", step) * 0.35 },
  ];
  return (
    <div style={{ ...FRAME, mixBlendMode: blend }}>
      {blobs.map((blob, index) => (
        <div
          key={index}
          aria-hidden
          style={{
            position: "absolute",
            left: `${(blob.x * 100).toFixed(2)}%`,
            top: `${(blob.y * 100).toFixed(2)}%`,
            width: `${size * 100}%`,
            aspectRatio: "1",
            transform: `translate(-50%, -50%) scale(${(0.8 + drift * 0.5).toFixed(3)})`,
            background: `radial-gradient(circle at 50% 50%, ${blob.color} 0%, transparent 62%)`,
            opacity: intensity * (0.55 + 0.45 * drift),
            filter: "blur(6px)",
          }}
        />
      ))}
    </div>
  );
};

// --- Formes vectorielles ----------------------------------------------------

/** Une forme invalide ne doit jamais faire echouer un rendu : on n'affiche rien. */
function safePath(d: string): { d: string; length: number; box: { x1: number; y1: number; width: number; height: number } } | null {
  try {
    const normalized = normalizePath(d);
    const box = getBoundingBox(normalized);
    if (!Number.isFinite(box.width) || box.width <= 0 || box.height <= 0) return null;
    return { d: normalized, length: getLength(normalized), box: { x1: box.x1, y1: box.y1, width: box.width, height: box.height } };
  } catch {
    return null;
  }
}

const PathTrace: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const raw = textParam(params, "path", "");
  const shape = React.useMemo(() => safePath(raw), [raw]);
  if (!shape) return null;
  const drawFrames = intg(params, "draw_frames", 45);
  const hold = intg(params, "hold_frames", 30);
  const fadeOut = flag(params, "fade_out", true);
  const color = col(params, "stroke_color", "#E2B458");
  const width = intg(params, "stroke_width_px", 5);
  const drawn = ramp(ctx, 0, drawFrames, "ease_out_cubic");
  const endAt = drawFrames + hold;
  const opacity = fadeOut && ctx.local > endAt ? clamp01(1 - (ctx.local - endAt) / Math.max(1, drawFrames)) : 1;
  const pad = width * 1.6;
  return (
    <div style={{ ...FRAME, opacity }}>
      <svg
        width="100%"
        height="100%"
        viewBox={`${shape.box.x1 - pad} ${shape.box.y1 - pad} ${shape.box.width + pad * 2} ${shape.box.height + pad * 2}`}
        preserveAspectRatio="xMidYMid meet"
        aria-hidden
      >
        <path
          d={shape.d}
          fill="none"
          stroke={color}
          strokeWidth={width}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={shape.length}
          strokeDashoffset={shape.length * (1 - drawn)}
        />
      </svg>
    </div>
  );
};

const PathMorph: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const from = textParam(params, "from_path", "");
  const to = textParam(params, "to_path", "");
  const frames = intg(params, "morph_frames", 50);
  const delay = intg(params, "delay_frames", 0);
  const fill = col(params, "fill_color", "#E2B458");
  const fillOpacity = num(params, "fill_opacity", 0.85);
  const shape = React.useMemo(() => {
    const a = safePath(from);
    const b = safePath(to);
    if (!a || !b) return null;
    const x = Math.min(a.box.x1, b.box.x1);
    const y = Math.min(a.box.y1, b.box.y1);
    const width = Math.max(a.box.x1 + a.box.width, b.box.x1 + b.box.width) - x;
    const height = Math.max(a.box.y1 + a.box.height, b.box.y1 + b.box.height) - y;
    if (width <= 0 || height <= 0) return null;
    return { x, y, width, height };
  }, [from, to]);
  if (!shape) return null;
  const t = ramp(ctx, delay, frames, "ease_out_cubic");
  let d = from;
  try {
    d = interpolatePath(t, normalizePath(from), normalizePath(to));
  } catch {
    return null;
  }
  const pad = 8;
  return (
    <div style={{ ...FRAME, opacity: fillOpacity }}>
      <svg
        width="100%"
        height="100%"
        viewBox={`${shape.x - pad} ${shape.y - pad} ${shape.width + pad * 2} ${shape.height + pad * 2}`}
        preserveAspectRatio="xMidYMid meet"
        aria-hidden
      >
        <path d={d} fill={fill} stroke={fill} strokeWidth={2} strokeLinejoin="round" />
      </svg>
    </div>
  );
};

// --- Generatif --------------------------------------------------------------

const PlasmaField: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const colorA = col(params, "color_a", "#E2B458");
  const colorB = col(params, "color_b", "#2B6CE6");
  const scale = num(params, "scale", 2.2);
  const complexity = num(params, "complexity", 2);
  const speed = num(params, "speed", 0.7);
  const opacity = num(params, "opacity", 0.35);
  const blend = pick(params, "blend", "screen") as React.CSSProperties["mixBlendMode"];

  // Basse resolution puis etirement CSS : le cout reste maitrise a 1080x1920.
  const columns = 96;
  const rows = Math.max(16, Math.round((columns * ctx.height) / Math.max(1, ctx.width)));

  React.useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    if (canvas.width !== columns || canvas.height !== rows) {
      canvas.width = columns;
      canvas.height = rows;
    }
    const image = context.createImageData(columns, rows);
    const time = (ctx.local / Math.max(1, ctx.fps)) * speed;
    const from = [parseInt(colorA.slice(1, 3), 16), parseInt(colorA.slice(3, 5), 16), parseInt(colorA.slice(5, 7), 16)];
    const to = [parseInt(colorB.slice(1, 3), 16), parseInt(colorB.slice(3, 5), 16), parseInt(colorB.slice(5, 7), 16)];
    for (let y = 0; y < rows; y += 1) {
      for (let x = 0; x < columns; x += 1) {
        // Coordonnees centrees : sans elles le champ ne varie qu'en x et le
        // plasma se reduit a des bandes verticales.
        const cx = (x / columns - 0.5) * scale * 4;
        const cy = (y / rows - 0.5) * scale * 4;
        const field =
          Math.sin(cx * 1.3 + time) +
          Math.sin(cy * 1.7 - time * 0.8) +
          Math.sin((cx + cy) * 1.1 * complexity + time * 1.2) +
          Math.sin(Math.sqrt(cx * cx + cy * cy + 1) * (1 + complexity) + time);
        const mix = clamp01((field + 4) / 8);
        const index = (y * columns + x) * 4;
        image.data[index] = Math.round(from[0] + (to[0] - from[0]) * mix);
        image.data[index + 1] = Math.round(from[1] + (to[1] - from[1]) * mix);
        image.data[index + 2] = Math.round(from[2] + (to[2] - from[2]) * mix);
        image.data[index + 3] = 255;
      }
    }
    context.putImageData(image, 0, 0);
  }, [columns, rows, ctx.local, ctx.fps, speed, scale, complexity, colorA, colorB]);

  return (
    <div style={{ ...FRAME, opacity, mixBlendMode: blend }}>
      <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block", imageRendering: "auto" }} />
    </div>
  );
};

// --- Reactif a l'audio ------------------------------------------------------

const AudioSpectrum: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  // media-utils exige une FFT de taille 2^n : « numberOfSamples * 2 » doit etre
  // une puissance de deux. Un reglage intermediaire est ramene a la puissance
  // la plus proche plutot que de faire echouer la frame.
  const bars = React.useMemo(() => {
    const requested = clamp(intg(params, "bars", 32), 4, 128);
    const exponent = Math.round(Math.log2(requested));
    return clamp(Math.round(2 ** exponent), 4, 128);
  }, [params]);
  const maxHeight = num(params, "max_height", 0.18);
  const color = col(params, "color", "#E2B458");
  const edge = pick(params, "edge", "bottom");
  const smoothing = num(params, "smoothing", 0.75);
  const tilt = num(params, "tilt", 0.9);
  const opacity = num(params, "opacity", 0.9);
  const values = React.useMemo(() => {
    if (!ctx.audioData) return null;
    try {
      return visualizeAudio({
        audioData: ctx.audioData,
        frame: loopedFrame(ctx.audioData, ctx.frame, ctx.fps),
        fps: ctx.fps,
        numberOfSamples: bars,
        optimizeFor: "speed",
        smoothing: smoothing > 0.5,
      });
    } catch {
      return null;
    }
  }, [ctx.audioData, ctx.frame, ctx.fps, bars, smoothing]);
  // Sans piste mesuree, rien n'est simule : l'effet est absent plutot que faux.
  if (!values) return null;
  const gap = Math.max(1, Math.round(ctx.width * 0.002));
  const barWidth = (ctx.width - gap * (bars - 1)) / bars;
  // La FFT d'une musique decore en 1/f : sans compensation, le spectre est une
  // rampe monotone. Une compression de puissance releve les bins faibles sans
  // jamais inventer de donnee : la valeur affichee reste celle du fichier.
  const last = Math.max(1, values.length - 1);
  const levels = values.map((value, index) =>
    clamp01(Math.pow(clamp01(value), 0.6) * (1 + tilt * (index / last))),
  );
  return (
    <div style={{ ...FRAME, opacity, display: "flex", alignItems: edge === "top" ? "flex-start" : "flex-end", padding: gap }}>
      {levels.map((value, index) => (
        <div
          key={index}
          style={{
            width: `${barWidth}px`,
            height: `${Math.max(2, value * maxHeight * ctx.height)}px`,
            background: color,
            borderRadius: `${Math.min(barWidth / 2, 4)}px`,
          }}
        />
      ))}
    </div>
  );
};

const AudioWaveform: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const samples = clamp(intg(params, "samples", 96), 16, 512);
  const windowSeconds = num(params, "window_seconds", 2.5);
  const amplitude = num(params, "max_height", 0.12);
  const color = col(params, "color", "#F7F5EF");
  const posY = num(params, "position_y", 0.8);
  const opacity = num(params, "opacity", 0.8);
  const normalized = flag(params, "normalize", true);
  const values = React.useMemo(() => {
    if (!ctx.audioData) return null;
    try {
      return visualizeAudioWaveform({
        audioData: ctx.audioData,
        frame: loopedFrame(ctx.audioData, ctx.frame, ctx.fps),
        fps: ctx.fps,
        windowInSeconds: windowSeconds,
        numberOfSamples: samples,
        normalize: normalized,
      });
    } catch {
      return null;
    }
  }, [ctx.audioData, ctx.frame, ctx.fps, windowSeconds, samples, normalized]);
  if (!values) return null;
  const mid = ctx.height * posY;
  const span = amplitude * ctx.height;
  // Barres et non trace : l'amplitude signee change de signe a chaque point, ce
  // qui dessinait une dent de scie. Les barres portent l'enveloppe, la bascule
  // « normalize » laisse le choix entre le pic absolu et le pic de la fenetre.
  const gap = Math.max(1, Math.round((ctx.width / values.length) * 0.4));
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: `${(mid - span / 2).toFixed(1)}px`,
        height: `${span.toFixed(1)}px`,
        display: "flex",
        alignItems: "center",
        gap: `${gap}px`,
        padding: `0 ${gap}px`,
        opacity,
        pointerEvents: "none",
      }}
    >
      {values.map((value, index) => (
        <div
          key={index}
          style={{
            flex: "1 1 0",
            height: `${Math.max(2, Math.abs(value) * span).toFixed(1)}px`,
            background: color,
            borderRadius: `${Math.min(3, gap)}px`,
          }}
        />
      ))}
    </div>
  );
};

// --- Screencast et interface ------------------------------------------------

interface RoutePoint {
  x: number;
  y: number;
}

function parsePoints(raw: string): RoutePoint[] {
  return raw
    .split(/[\s;]+/)
    .map((chunk) => chunk.split(","))
    .filter((pair) => pair.length === 2)
    .map(([x, y]) => ({ x: Number.parseFloat(x), y: Number.parseFloat(y) }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
}

const CursorTour: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const points = parsePoints(textParam(params, "points", ""));
  const duration = intg(params, "duration_frames", 70);
  const scale = num(params, "cursor_scale", 1.1);
  const cursorColor = col(params, "cursor_color", "#F7F5EF");
  const rippleColor = col(params, "ripple_color", "#E2B458");
  const easing = pick(params, "easing", "ease_out_cubic");
  if (points.length < 2) return null;

  const inputRange = points.map((_, index) => index / (points.length - 1));
  const shaped = ramp(ctx, 0, duration, easing);
  const xs = points.map((p) => p.x * ctx.width);
  const ys = points.map((p) => p.y * ctx.height);
  const options = { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };
  const x = interpolate(shaped, inputRange, xs, options);
  const y = interpolate(shaped, inputRange, ys, options);
  const size = Math.max(12, ctx.width * 0.018) * scale;

  // Une onde nait a l'arrivee reelle du curseur, donc au point d'inflexion de
  // la courbe et non a un temps lineaire : l'approximer par dichotomie evite
  // que l'onde ne parte avant que le curseur n'atteigne la cible.
  const fn = curve(easing);
  const arrivalFrame = (fraction: number): number => {
    if (fraction <= 0) return 0;
    if (fraction >= 1) return duration;
    let lo = 0;
    let hi = duration;
    for (let i = 0; i < 12; i += 1) {
      const mid = (lo + hi) / 2;
      if (fn(mid / duration) < fraction) lo = mid;
      else hi = mid;
    }
    return Math.round((lo + hi) / 2);
  };
  const life = Math.max(6, Math.round((duration / Math.max(1, points.length - 1)) * 0.6));

  return (
    <div style={FRAME}>
      {points.map((point, index) => {
        const age = ctx.local - arrivalFrame(index / (points.length - 1));
        if (age < 0 || age > life) return null;
        const progress = clamp01(age / life);
        return (
          <div
            key={`ripple-${index}`}
            aria-hidden
            style={{
              position: "absolute",
              left: point.x * ctx.width,
              top: point.y * ctx.height,
              width: size * 6,
              height: size * 6,
              marginLeft: -size * 3,
              marginTop: -size * 3,
              borderRadius: "50%",
              border: `${Math.max(2, size * 0.12)}px solid ${rippleColor}`,
              opacity: 1 - progress,
              transform: `scale(${(0.2 + progress * 1.4).toFixed(3)})`,
            }}
          />
        );
      })}
      <svg
        width={size * 1.6}
        height={size * 2}
        viewBox="0 0 12 19"
        style={{ position: "absolute", left: x, top: y, filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.55))" }}
        aria-hidden
      >
        <path d="M1 1 L1 15 L5 11.5 L7.6 17.4 L10 16.3 L7.5 10.6 L12 10 Z" fill={cursorColor} stroke="rgba(0,0,0,0.55)" strokeWidth="0.8" />
      </svg>
    </div>
  );
};

const KEYWORDS =
  /^(def|return|if|else|elif|for|while|import|from|as|with|class|lambda|yield|pass|break|continue|None|True|False|const|let|var|function|await|async|new|export|switch|case|default|null|undefined|true|false)$/;

/** Tokenizer maison : ni prism ni shiki, mais chaines, commentaires et mots-cles sont reconnus. */
function tokenize(line: string): Array<{ text: string; kind: string }> {
  const out: Array<{ text: string; kind: string }> = [];
  const pattern = /(\s+|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`|#.*|\/\/.*|[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|[^\sA-Za-z0-9_$]+)/g;
  let match: RegExpExecArray | null = pattern.exec(line);
  while (match !== null) {
    const token = match[0];
    let kind = "plain";
    if (/^["'`]/.test(token)) kind = "string";
    else if (/^(#|\/\/)/.test(token)) kind = "comment";
    else if (/^\d/.test(token)) kind = "number";
    else if (KEYWORDS.test(token)) kind = "keyword";
    out.push({ text: token, kind });
    match = pattern.exec(line);
  }
  return out;
}

const CODE_THEME: Record<string, Record<string, string>> = {
  sombre: { plain: "#E8E8F0", string: "#8FD694", comment: "#6B6B7E", number: "#E2B458", keyword: "#7AA2FF" },
  clair: { plain: "#1A1A22", string: "#1B7F3B", comment: "#8A8A98", number: "#A16207", keyword: "#1D4ED8" },
};

const CodeType: React.FC<OverlayProps> = ({ effect, ctx }) => {
  const params = effect.params;
  const code = textParam(params, "code", "");
  const perFrame = Math.max(1, intg(params, "chars_per_frame", 3));
  const delay = intg(params, "delay_frames", 6);
  const fontSize = intg(params, "font_size_px", 28);
  const theme = pick(params, "theme", "sombre");
  const numbers = flag(params, "line_numbers", true);
  const caret = flag(params, "caret", true);
  const opacity = num(params, "opacity", 1);
  const colors = CODE_THEME[theme] ?? CODE_THEME.sombre;
  const lines = code.split("\n");
  const visible = Math.max(0, (ctx.local - delay) * perFrame);
  let consumed = 0;
  const blink = caret && Math.floor(ctx.local / 12) % 2 === 0;

  return (
    <div
      style={{
        ...FRAME,
        opacity,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: theme === "clair" ? "rgba(248,248,250,0.92)" : "rgba(8,8,14,0.88)",
        padding: `${fontSize}px`,
      }}
    >
      <div style={{ fontFamily: "monospace", fontSize: `${fontSize}px`, lineHeight: 1.5, width: "100%", maxWidth: "86%" }}>
        {lines.map((line, index) => {
          const lineLength = line.length + 1;
          const shown = clamp(visible - consumed, 0, lineLength);
          consumed += lineLength;
          const typed = line.slice(0, Math.max(0, shown));
          const done = shown >= lineLength;
          return (
            <div key={index} style={{ display: "flex", gap: `${fontSize * 0.7}px`, whiteSpace: "pre" }}>
              {numbers ? (
                <span style={{ color: colors.comment, width: `${fontSize * 1.8}px`, textAlign: "right" }}>{index + 1}</span>
              ) : null}
              <span style={{ color: colors.plain }}>
                {tokenize(typed).map((token, tokenIndex) => (
                  <span key={tokenIndex} style={{ color: colors[token.kind] ?? colors.plain }}>
                    {token.text}
                  </span>
                ))}
                {!done && shown > 0 && blink ? <span style={{ background: colors.keyword }}>&nbsp;</span> : null}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// --- Registre ---------------------------------------------------------------

const OVERLAY_COMPONENTS: Record<OverlayEffectId, React.FC<OverlayProps>> = {
  scanlines: Scanlines,
  white_noise: WhiteNoise,
  light_leak: LightLeak,
  path_trace: PathTrace,
  path_morph: PathMorph,
  plasma_field: PlasmaField,
  audio_spectrum: AudioSpectrum,
  audio_waveform: AudioWaveform,
  cursor_tour: CursorTour,
  code_type: CodeType,
};

const rendersOverlay = (id: string): id is OverlayEffectId =>
  Object.prototype.hasOwnProperty.call(OVERLAY_COMPONENTS, id);

export const SceneOverlays: React.FC<{ effects: Effect[]; ctx: EffectCtx }> = ({ effects, ctx }) => {
  const active = effects.filter((e) => e.scope === "overlay" && rendersOverlay(e.id));
  if (!active.length) return null;
  return (
    <>
      {active.map((effect) => {
        const Component = OVERLAY_COMPONENTS[effect.id as OverlayEffectId];
        return <Component key={effect.id} effect={effect} ctx={{ ...ctx, uid: `${ctx.uid}-${effect.id}` }} />;
      })}
    </>
  );
};
