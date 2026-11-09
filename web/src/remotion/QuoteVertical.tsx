import React from "react";
import { AbsoluteFill, Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { renderMediaUrl } from "./mediaUrl";

/**
 * Composition Remotion du modèle « citation verticale ».
 *
 * C'est la SOURCE UNIQUE de rendu côté web : la même composant sert au
 * Remotion Player (aperçu) et au rendu MP4 (`npx remotion render`),
 * exactement comme `compose_frame` sert de source unique côté Python.
 *
 * Le format de projet est celui de shortvideos/PROJECT_FORMAT.md (v1).
 */

export interface QuoteProject {
  version: number;
  template: string;
  content: {
    text: string;
    author: string;
    background_image: string;
    logo: string;
  };
  theme: {
    font_family: string;
    font_size: number;
    text_color: string;
    author_color: string;
    accent_color: string;
    shadow: boolean;
  };
  position: { x: number; y: number; width: number };
  timing: { duration: number; text_start: number; fade_in: number; fade_out: number };
  animation: { text_in: string; background: string };
  export: { width: number; height: number; fps: number; output_dir: string };
}

export interface QuoteProps {
  project: QuoteProject;
}

/** Fichier de police Windows → police navigateur (habillage possibly différent). */
const FONT_MAP: Record<string, string> = {
  "arialbd.ttf": "Arial",
  "arial.ttf": "Arial",
  "impact.ttf": "Impact",
  "georgia.ttf": "Georgia",
  "times.ttf": "Times New Roman",
  "segoeui.ttf": "Segoe UI",
  "segoeuib.ttf": "Segoe UI",
  "verdana.ttf": "Verdana",
  "calibrib.ttf": "Calibri",
  "calibri.ttf": "Calibri",
};

export function browserFont(family: string): string {
  const mapped = FONT_MAP[family];
  if (mapped) return mapped;
  // Chemin absolu ou inconnu : sans-serif (signalé comme limite).
  return "Arial, sans-serif";
}

export function mediaSrc(value: string): string | null {
  // Regles communes avec la composition studio : le cache de rendu est adresse
  // par staticFile() pour que la meme chaine fonctionne dans le Player et dans
  // le navigateur de rendu Remotion.
  return renderMediaUrl(value);
}

/** Mêmes règles que shortvideos/timing.py. */
function textAlpha(t: number, p: QuoteProject): number {
  const { duration, text_start, fade_in, fade_out } = p.timing;
  if (t < text_start || t >= duration) return 0;
  if (fade_in > 0 && t < text_start + fade_in) return Math.min(1, (t - text_start) / fade_in);
  const fadeOutStart = duration - fade_out;
  if (fade_out > 0 && t > fadeOutStart) return Math.max(0, (duration - t) / fade_out);
  return 1;
}

function entranceProgress(t: number, p: QuoteProject): number {
  const { text_start, fade_in } = p.timing;
  if (t < text_start) return 0;
  if (fade_in <= 0) return 1;
  return Math.min(1, (t - text_start) / fade_in);
}

function backgroundScale(t: number, p: QuoteProject): number {
  if (p.animation.background !== "zoom_slow") return 1.0;
  const dur = Math.max(p.timing.duration, 1e-6);
  const ratio = Math.min(1, Math.max(0, t / dur));
  return 1.0 + 0.08 * ratio; // ZOOM_MAX = 1.08 (timing.py)
}

export const QuoteVertical: React.FC<QuoteProps> = ({ project: p }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;

  const alpha = textAlpha(t, p);
  const scale = backgroundScale(t, p);
  const progress = entranceProgress(t, p);
  const slideOffset =
    p.animation.text_in === "slide" ? (1 - progress) * 0.05 * height : 0;

  const fontSize = Math.round((p.theme.font_size * height) / 1920);
  const fontFamily = browserFont(p.theme.font_family);
  const bgSrc = mediaSrc(p.content.background_image);
  const logoSrc = mediaSrc(p.content.logo);

  const blockWidth = Math.round(p.position.width * width);
  const centerX = Math.round(p.position.x * width);
  const centerY = Math.round(p.position.y * height);

  return (
    <AbsoluteFill style={{ backgroundColor: "#121218", overflow: "hidden" }}>
      {/* Fond image en « cover » + zoom lent */}
      {bgSrc && (
        <Img
          src={bgSrc}
          style={{
            position: "absolute",
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale})`,
            transformOrigin: "center center",
          }}
        />
      )}

      {/* Logo : coin bas-droite, 18 % de la largeur */}
      {logoSrc && (
        <Img
          src={logoSrc}
          style={{
            position: "absolute",
            right: Math.round(width * 0.04),
            bottom: Math.round(height * 0.04),
            width: Math.round(width * 0.18),
            height: "auto",
          }}
        />
      )}

      {/* Bloc de texte centré sur (x, y) */}
      <div
        style={{
          position: "absolute",
          left: centerX,
          top: centerY,
          width: blockWidth,
          transform: `translate(-50%, -50%) translateY(${slideOffset}px)`,
          textAlign: "center",
          opacity: alpha,
          color: p.theme.text_color,
          fontFamily,
          fontSize,
          fontWeight: 700,
          lineHeight: 1.4,
          textShadow: p.theme.shadow ? "2px 3px 6px rgba(0,0,0,0.75)" : "none",
          wordWrap: "break-word",
        }}
      >
        <div>{p.content.text}</div>
        {p.content.author?.trim() && (
          <div
            style={{
              marginTop: Math.round(fontSize * 0.35),
              fontSize: Math.round(fontSize * 0.5),
              fontWeight: 600,
              color: p.theme.author_color,
            }}
          >
            — {p.content.author}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

/** Projet par défaut (miroir de shortvideos.project.default_project). */
export function defaultQuoteProject(): QuoteProject {
  return {
    version: 1,
    template: "quote_vertical",
    content: {
      text: "Le courage est le premier des vertus.",
      author: "",
      background_image: "",
      logo: "",
    },
    theme: {
      font_family: "arialbd.ttf",
      font_size: 72,
      text_color: "#FFFFFF",
      author_color: "#F2C14E",
      accent_color: "#F2C14E",
      shadow: true,
    },
    position: { x: 0.5, y: 0.45, width: 0.85 },
    timing: { duration: 8.0, text_start: 0.5, fade_in: 0.8, fade_out: 0.8 },
    animation: { text_in: "fade", background: "zoom_slow" },
    export: { width: 1080, height: 1920, fps: 30, output_dir: "" },
  };
}

export function projectDims(p: QuoteProject): {
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
} {
  return {
    width: p.export.width,
    height: p.export.height,
    fps: p.export.fps,
    durationInFrames: Math.max(1, Math.round(p.timing.duration * p.export.fps)),
  };
}

// Interpolation gardée pour usage externe (utilisée par le contrôleur bas de page).
export { interpolate };
