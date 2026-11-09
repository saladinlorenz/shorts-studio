/** Types du format de projet version 2, alignes sur shortvideos/schema.py
 *  et sur le bloc ``resolved`` produit par shortvideos/resolve.py.
 *
 *  Le calque ne connait que des FRAMES ABSOLUES : l'horloge est celle de la
 *  composition, jamais un timer independant, donc l'aperçu et le rendu
 *  parcourent les memes valeurs.
 */

import type { Effect } from "./effects/common";

export type { Effect };

export type AnimIn = "fade" | "slide_up" | "slide_left" | "scale" | "mask_reveal" | "none";
export type AnimOut = "none" | "fade";
export type AnimUnit = "block" | "line" | "word";
export type EasingName = "linear" | "ease_out_cubic" | "ease_out_quint" | "spring";

export interface AnimationSettings {
  in: AnimIn;
  out: AnimOut;
  unit: AnimUnit;
  stagger_frames: number;
  start_frames: number;
  in_frames: number;
  out_frames: number;
  easing: EasingName;
  spring: { damping: number; stiffness: number; mass: number };
  distance: number;
}

export interface TextPosition {
  x: number;
  y: number;
  width: number;
  align: "left" | "center" | "right";
  direction: "ltr" | "rtl";
}

export interface LayerStyle {
  font_family?: string;
  font_weight?: number;
  font_size?: number;
  line_height?: number;
  letter_spacing?: number;
  color?: string;
  accent_color?: string;
  shadow?: boolean;
  stroke_width?: number;
  stroke_color?: string;
}

/** Effet tel que l'auteur le saisit : forme courte "glitch_slices" ou reglee. */
export type RawEffect =
  | string
  | { id?: string; params?: Record<string, number | boolean | string> };

/** Identifiant d'un effet saisi, la forme courte et la forme reglee se resument ici. */
export function effectId(raw: RawEffect): string {
  return typeof raw === "string" ? raw : String(raw.id ?? "");
}

export interface TextLayer {
  id: string;
  type: "text";
  role: string;
  text: string;
  emphasis: string[];
  hidden: boolean;
  locked: boolean;
  effects?: RawEffect[];
  position: TextPosition;
  style: LayerStyle;
  animation: AnimationSettings;
}

export interface ImageLayer {
  id: string;
  type: "image";
  role: string;
  media: string;
  hidden: boolean;
  locked: boolean;
  opacity: number;
  effects?: RawEffect[];
  position: TextPosition;
  animation: AnimationSettings;
}

export type Layer = TextLayer | ImageLayer;

export interface SceneBackground {
  media: string;
  fit: "cover" | "contain";
  animation: "static" | "zoom_slow" | "zoom_out";
}

export interface Scene {
  id: string;
  label: string;
  duration: number;
  hidden: boolean;
  effects?: RawEffect[];
  background: SceneBackground;
  layers: Layer[];
}

export interface SignatureSettings {
  enabled: boolean;
  media: string;
  handle: string;
  font_family: string;
  font_weight: number;
  font_size: number;
  color: string;
  logo_width: number;
  position: { x: number; y: number };
  start_frames: number;
  in_frames: number;
}

export interface Theme {
  palette_id: string;
  background_color: string;
  surface_color: string;
  text_color: string;
  accent_color: string;
  author_color: string;
  muted_color: string;
  font_family: string;
  font_weight: number;
  font_size: number;
  line_height: number;
  letter_spacing: number;
  shadow: boolean;
}

export interface ResolvedLayer {
  id: string;
  type: "text" | "image";
  /** Effets normalises par le serveur : reglages complets et bornes garanties. */
  effects: Effect[];
  start_frame: number;
  in_end_frame: number;
  spread_frames: number;
  units: number;
  out_start_frame: number;
  end_frame: number;
  hold_frames: number;
  duration_frames: number;
  align: "left" | "center" | "right";
  direction: "ltr" | "rtl";
  font_family: string;
  font_weight: number;
  font_size_px: number;
  line_height: number;
  letter_spacing_em: number;
  color: string;
  accent_color: string;
  shadow: boolean;
  stroke_width_px: number;
  stroke_color: string;
}

export interface ResolvedScene {
  id: string;
  label: string;
  effects: Effect[];
  start_frame: number;
  duration_frames: number;
  end_frame: number;
  hidden: boolean;
  background: SceneBackground & { media: string };
  layers: ResolvedLayer[];
}

export interface ResolvedSignature extends SignatureSettings {
  start_frame: number;
  in_frames: number;
  font_size_px: number;
  logo_width_px: number;
  end_frame: number;
}

export interface ResolvedAudio {
  enabled: boolean;
  music: string;
  voice: string;
  music_volume: number;
  voice_volume: number;
  music_fade_in: number;
  music_fade_out: number;
  start_frame: number;
  end_frame: number;
  total_frames: number;
  fps: number;
  duration: number;
}

export interface Resolved {
  model: { id: string; version: number };
  fps: number;
  width: number;
  height: number;
  scale: number;
  total_frames: number;
  duration: number;
  scenes: ResolvedScene[];
  signature: ResolvedSignature;
  assets: Array<{ kind: string; ref: string; scene: string }>;
  fonts: Array<{ id: string; known: boolean; weights: number[] }>;
  audio: ResolvedAudio;
  seed: number;
}

export interface StudioProject {
  version: 2;
  model: { id: string; version: number };
  name: string;
  content: { scenes: Scene[]; signature: SignatureSettings };
  theme: Theme;
  audio: Record<string, unknown>;
  variation: { seed: number };
  export: { width: number; height: number; fps: number; output_dir: string; filename: string };
  resolved: Resolved;
}

export function layerOf(project: StudioProject, sceneId: string, layerId: string): Layer | undefined {
  const scene = project.content.scenes.find((s) => s.id === sceneId);
  return scene?.layers.find((l) => l.id === layerId);
}

export function sceneOf(project: StudioProject, sceneId: string): Scene | undefined {
  return project.content.scenes.find((s) => s.id === sceneId);
}
