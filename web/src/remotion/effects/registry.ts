import type { Effect } from "./common";

/**
 * Registre des effets implémentés côté rendu.
 *
 * Le catalogue normatif est serveur (shortvideos/effects.py) : c'est lui qui
 * donne les reglages, les bornes et les portees. Ce fichier dit seulement
 * « tel identifiant a bien un composant qui le rend ». `tests/test_effects.py`
 * compare les deux listes, donc un effet declare au catalogue sans rendu, ou
 * l'inverse, casse les tests au lieu de passer inapercu.
 *
 * Les types `Record<Id, ...>` utilises par les fichiers d'implementation
 * obligent TypeScript a couvrir exactement ces identifiants : en ajouter un ici
 * sans ecrire le composant est une erreur de compilation.
 */

/** Effets de calque rendus par `applyLayerEffects` (styles + mises en page). */
export const LAYER_EFFECT_IDS = [
  "spring_pop",
  "kinetic_letters",
  "flip_card",
  "chromatic_aberration",
  "glitch_slices",
  "parallax_depth",
  "cylinder_wrap",
  "sphere_wrap",
  "audio_pulse",
  "shine",
] as const;

/** Effets de calque rendus a l'interieur du media (decoupe de pixels). */
export const IMAGE_EFFECT_IDS = ["chroma_key"] as const;

/** Effets de scene rendus par `SceneEffects` (camera, deformation, etalonnage). */
export const SCENE_EFFECT_IDS = [
  "perspective_dolly",
  "liquid_contours",
  "color_grade",
  "depth_blur",
  "glitch_slices",
  "chromatic_aberration",
] as const;

/** Effets plein cadre rendus par `SceneOverlays`. */
export const OVERLAY_EFFECT_IDS = [
  "scanlines",
  "white_noise",
  "light_leak",
  "path_trace",
  "path_morph",
  "plasma_field",
  "audio_spectrum",
  "audio_waveform",
  "cursor_tour",
  "code_type",
] as const;

export type LayerEffectId = (typeof LAYER_EFFECT_IDS)[number];
export type ImageEffectId = (typeof IMAGE_EFFECT_IDS)[number];
export type SceneEffectId = (typeof SCENE_EFFECT_IDS)[number];
export type OverlayEffectId = (typeof OVERLAY_EFFECT_IDS)[number];

/** Tous les identifiants réellement rendus, sans doublon. */
export const IMPLEMENTED_EFFECT_IDS: string[] = Array.from(
  new Set<string>([
    ...LAYER_EFFECT_IDS,
    ...IMAGE_EFFECT_IDS,
    ...SCENE_EFFECT_IDS,
    ...OVERLAY_EFFECT_IDS,
  ]),
);

export function hasEffect(effects: Effect[], id: string): boolean {
  return effects.some((effect) => effect.id === id);
}

export function findEffect(effects: Effect[], id: string): Effect | null {
  return effects.find((effect) => effect.id === id) ?? null;
}

/** Un effet « mesure l'audio » n'a de sens que si une piste est chargee. */
export function needsMeasuredAudio(effects: Effect[]): boolean {
  return effects.some((effect) => effect.needs_audio);
}
