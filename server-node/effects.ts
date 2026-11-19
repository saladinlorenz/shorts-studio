export interface EffectParamSpec {
  key: string;
  label: string;
  type: "number" | "integer" | "bool" | "color" | "select" | "text";
  default: unknown;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  options?: string[];
  max_chars?: number;
  placeholder?: string;
}

export interface EffectSpec {
  id: string;
  label: string;
  category: string;
  scopes: string[];
  targets: string[];
  needs_audio: boolean;
  description: string;
  note: string;
  params: EffectParamSpec[];
}

export const CATEGORIES: Array<[string, string]> = [
  ["motion", "Motion design et physique"],
  ["distort", "Distorsions et glitch"],
  ["space", "3D, camera et espace"],
  ["audio", "Reactif a l'audio"],
  ["screen", "Screencast et interface"],
  ["generative", "Generatif et shaders"],
  ["light", "Lumiere, couleur et keying"],
];

export const SCOPES = ["layer", "scene", "overlay"] as const;
export const MAX_EFFECTS_PER_TARGET = 4;

const num = (key: string, label: string, min: number, max: number, def: number, step = 0.01, unit = ""): EffectParamSpec => ({
  key, label, type: "number", min, max, default: def, step, unit,
});
const int = (key: string, label: string, min: number, max: number, def: number, step = 1): EffectParamSpec => ({
  key, label, type: "integer", min, max, default: def, step,
});
const bool = (key: string, label: string, def: boolean): EffectParamSpec => ({
  key, label, type: "bool", default: def,
});
const color = (key: string, label: string, def: string): EffectParamSpec => ({
  key, label, type: "color", default: def,
});
const select = (key: string, label: string, options: string[], def: string): EffectParamSpec => ({
  key, label, type: "select", options, default: def,
});
const text = (key: string, label: string, def: string, max_chars: number, placeholder = ""): EffectParamSpec => ({
  key, label, type: "text", default: def, max_chars, placeholder,
});

export const EFFECTS: EffectSpec[] = [
  {
    id: "spring_pop", label: "Ressort d'apparition", category: "motion", scopes: ["layer"], targets: ["text", "image"], needs_audio: false,
    description: "Le calque entre avec un ressort physique reglable : surtension d'echelle et rotation qui se stabilisent.", note: "",
    params: [num("damping", "Amortissement", 1, 40, 8, 0.5), num("stiffness", "Raideur", 20, 500, 200, 5), num("mass", "Masse", 0.1, 6, 1, 0.1), num("overshoot", "Surtension d'echelle", 1.0, 1.8, 1.18, 0.01), num("rotate_deg", "Rotation de depart", -45, 45, -8, 1, "degres")],
  },
  {
    id: "kinetic_letters", label: "Typographie cinematique lettre a lettre", category: "motion", scopes: ["layer"], targets: ["text"], needs_audio: false,
    description: "Chaque lettre recoit son propre ressort : montee, rotation et flou de mouvement decales.", note: "",
    params: [int("stagger_frames", "Decalage par lettre", 0, 8, 2), num("rise", "Hauteur de montee", 0, 0.5, 0.12, 0.01, "fraction"), num("rotate_deg", "Rotation", -45, 45, -12, 1, "degres"), num("blur_px", "Flou de depart", 0, 24, 6, 0.5, "px"), num("damping", "Amortissement", 4, 40, 12, 0.5)],
  },
  {
    id: "flip_card", label: "Revelation par carte retournee", category: "motion", scopes: ["layer"], targets: ["text", "image"], needs_audio: false,
    description: "Le calque arrive comme une carte qui pivote.", note: "",
    params: [select("axis", "Axe", ["y", "x"], "y"), int("duration_frames", "Duree", 10, 120, 40), int("delay_frames", "Attente avant pivot", 0, 300, 0), int("perspective_px", "Perspective", 400, 4000, 1200, 50), color("plate_color", "Face de la carte", "#E2B458")],
  },
  {
    id: "path_trace", label: "Tracer un contour SVG", category: "motion", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Une forme se dessine trait apres trait via @remotion/paths.", note: "Le chemin est verifie avant le rendu.",
    params: [text("path", "Chemin SVG (attribut d)", "M 40 200 C 120 40, 240 360, 340 200 S 520 60, 600 220", 600, "M 0 100 L 200 100"), color("stroke_color", "Couleur du trait", "#E2B458"), int("stroke_width_px", "Epaisseur", 1, 40, 5, 1), int("draw_frames", "Frames de tracage", 5, 300, 45), int("hold_frames", "Maintien apres tracage", 0, 600, 30), bool("fade_out", "Disparaitre a la fin", true)],
  },
  {
    id: "path_morph", label: "Morphing de forme", category: "motion", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Interpolation reelle entre deux traces SVG via @remotion/paths.", note: "Les deux traces doivent avoir le meme nombre de segments.",
    params: [text("from_path", "Forme de depart", "M 100 20 L 300 200 L 100 380 Z", 600), text("to_path", "Forme d'arrivee", "M 200 20 A 180 180 0 1 1 199 20 Z", 600), int("morph_frames", "Frames d'interpolation", 5, 300, 50), int("delay_frames", "Attente avant morphing", 0, 300, 0), color("fill_color", "Remplissage", "#E2B458"), num("fill_opacity", "Opacite du remplissage", 0, 1, 0.85, 0.05)],
  },
  {
    id: "chromatic_aberration", label: "Aberration chromatique", category: "distort", scopes: ["layer", "scene"], targets: ["text", "image"], needs_audio: false,
    description: "Separation RGB decalee par filtres SVG.", note: "",
    params: [num("offset_px", "Decalage", 0, 60, 12, 0.5, "px"), num("angle_deg", "Direction", 0, 360, 0, 1, "degres"), bool("animate", "Animer le decalage", true), int("cycle_frames", "Periode d'animation", 6, 240, 24)],
  },
  {
    id: "glitch_slices", label: "Glitch par tranches", category: "distort", scopes: ["layer", "scene"], targets: ["text", "image"], needs_audio: false,
    description: "Tranches horizontales deterministes selon la graine.", note: "",
    params: [int("delay_frames", "Debut dans la scene", 0, 600, 0), int("duration_frames", "Duree du glitch", 4, 180, 24), int("slice_count", "Nombre de tranches", 2, 24, 8), num("max_offset", "Decalage maximal", 0, 1, 0.08, 0.01, "fraction"), int("reroll_frames", "Frames par saut", 1, 12, 2), num("intensity", "Opacite", 0, 1, 0.55, 0.05)],
  },
  {
    id: "scanlines", label: "Scanlines CRT", category: "distort", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Rayures horizontales animees façon ecran cathodique.", note: "",
    params: [int("line_height_px", "Pas des lignes", 2, 40, 6, 1), int("thickness_px", "Epaisseur du trait", 1, 8, 1, 1), num("opacity", "Opacite", 0, 1, 0.35, 0.05), bool("roll", "Faire defiler", true), num("roll_speed", "Vitesse de defilement", -4, 4, 0.6, 0.1, "px/frame"), color("color", "Couleur", "#000000")],
  },
  {
    id: "white_noise", label: "Bruit blanc", category: "distort", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Grain analogique deterministe genere par feTurbulence.", note: "",
    params: [num("opacity", "Opacite", 0, 1, 0.22, 0.02), num("scale", "Granulosite", 1, 60, 14, 0.5), bool("animated", "Faire bouillonner", true), int("cycle_frames", "Periode", 2, 120, 3), select("kind", "Type de turbulence", ["fractalNoise", "turbulence"], "fractalNoise"), int("octaves", "Octaves", 1, 5, 2)],
  },
  {
    id: "perspective_dolly", label: "Travelling de camera 3D", category: "space", scopes: ["scene"], targets: ["text", "image"], needs_audio: false,
    description: "Mouvement camera en espace CSS 3D.", note: "",
    params: [num("start_z", "Profondeur de depart", -0.9, 0.9, -0.25, 0.05, "fraction"), num("end_z", "Profondeur d'arrivee", -0.9, 0.9, 0.08, 0.05, "fraction"), num("rotate_x_deg", "Pendule vertical", -25, 25, 4, 0.5, "degres"), num("rotate_y_deg", "Pendule horizontal", -25, 25, -6, 0.5, "degres"), int("perspective_px", "Focale", 400, 4000, 1600, 50), select("easing", "Courbe", ["ease_out_cubic", "ease_out_quint", "linear", "spring"], "ease_out_cubic")],
  },
  {
    id: "parallax_depth", label: "Parallaxe par profondeur", category: "space", scopes: ["layer"], targets: ["text", "image"], needs_audio: false,
    description: "Derive de parallaxe entre les plans.", note: "",
    params: [num("depth", "Profondeur", 0, 1, 0.6, 0.05), num("drift_x", "Derive horizontale", -1, 1, 0.12, 0.02, "fraction"), num("drift_y", "Derive verticale", -1, 1, -0.05, 0.02, "fraction"), num("scale_from", "Echelle au debut", 0.6, 1.6, 1.04, 0.02), num("scale_to", "Echelle a la fin", 0.6, 1.6, 1, 0.02)],
  },
  {
    id: "cylinder_wrap", label: "Texte enveloppe sur un cylindre", category: "space", scopes: ["layer"], targets: ["text"], needs_audio: false,
    description: "Lettres reparties sur la surface d'un cylindre en CSS 3D.", note: "",
    params: [int("radius_px", "Rayon du cylindre", 80, 1600, 420, 10), num("arc_deg", "Arc occupe", 20, 340, 150, 5, "degres"), num("rotation_deg", "Orientation", -360, 360, -60, 5, "degres"), bool("spin", "Rotation continue", true), num("spin_deg_per_s", "Vitesse", -180, 180, 24, 1, "degres/s"), num("opacity_back", "Opacite dos", 0, 1, 0.15, 0.05)],
  },
  {
    id: "sphere_wrap", label: "Texte enveloppe sur une sphere", category: "space", scopes: ["layer"], targets: ["text"], needs_audio: false,
    description: "Projection par tranches sur une sphere CSS 3D.", note: "Approximation par tranches.",
    params: [int("radius_px", "Rayon de la sphere", 80, 1200, 320, 10), num("lat_deg", "Latitude", -80, 80, 12, 1, "degres"), num("spread_deg", "Etalement", 20, 320, 140, 5, "degres"), num("rotation_deg", "Rotation", -360, 360, 0, 5, "degres"), num("spin_deg_per_s", "Vitesse", -180, 180, 18, 1, "degres/s"), num("opacity_back", "Opacite dos", 0, 1, 0.1, 0.05)],
  },
  {
    id: "audio_pulse", label: "Pulse sur les graves", category: "audio", scopes: ["layer"], targets: ["text", "image"], needs_audio: true,
    description: "Reaction d'echelle aux graves/mediums/aigus via @remotion/media-utils.", note: "",
    params: [select("band", "Bande", ["bass", "mid", "treble"], "bass"), num("min_scale", "Echelle silence", 0.6, 1.2, 0.97, 0.01), num("max_scale", "Echelle pic", 1, 2.2, 1.14, 0.01), num("smoothing", "Lissage", 0, 0.95, 0.6, 0.05), num("glow", "Halo", 0, 60, 18, 1, "px")],
  },
  {
    id: "audio_spectrum", label: "Spectre frequentiel", category: "audio", scopes: ["overlay"], targets: ["text", "image"], needs_audio: true,
    description: "Barres de spectre FFT temps reel.", note: "",
    params: [int("bars", "Nombre de barres", 8, 96, 32), num("max_height", "Hauteur max", 0.02, 0.6, 0.18, 0.01, "fraction"), color("color", "Couleur", "#E2B458"), select("edge", "Position", ["bottom", "top"], "bottom"), num("smoothing", "Lissage", 0, 0.95, 0.75, 0.05), num("tilt", "Compensation aigus", 0, 4, 1.2, 0.1), num("opacity", "Opacite", 0, 1, 0.9, 0.05)],
  },
  {
    id: "audio_waveform", label: "Forme d'onde", category: "audio", scopes: ["overlay"], targets: ["text", "image"], needs_audio: true,
    description: "Trace d'enveloppe sonore reelle.", note: "",
    params: [int("samples", "Points traces", 32, 512, 96), num("window_seconds", "Fenetre", 0.2, 10, 2.5, 0.1, "s"), num("max_height", "Amplitude", 0.02, 0.5, 0.12, 0.01, "fraction"), color("color", "Couleur", "#F7F5EF"), num("position_y", "Position Y", 0, 1, 0.8, 0.02, "fraction"), num("opacity", "Opacite", 0, 1, 0.8, 0.05), bool("normalize", "Normaliser", true)],
  },
  {
    id: "cursor_tour", label: "Curseur anime et clic", category: "screen", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Curseur anime entre des points de passage.", note: "",
    params: [text("points", "Points (x,y)", "0.18,0.72 0.5,0.42 0.78,0.6", 240, "0.2,0.8 0.6,0.4"), int("duration_frames", "Duree", 12, 480, 70), num("cursor_scale", "Taille", 0.4, 3, 1.1, 0.1), color("cursor_color", "Curseur", "#F7F5EF"), color("ripple_color", "Onde", "#E2B458"), select("easing", "Courbe", ["ease_out_cubic", "ease_out_quint", "linear", "spring"], "ease_out_cubic")],
  },
  {
    id: "code_type", label: "Code qui se tape", category: "screen", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Frappe de code animee.", note: "",
    params: [text("code", "Code affiche", "def etat(plateforme):\n    return 'studio'", 1200), int("chars_per_frame", "Caracteres/frame", 1, 40, 3), int("delay_frames", "Attente", 0, 300, 6), int("font_size_px", "Taille", 12, 72, 28, 1), select("theme", "Theme", ["sombre", "clair"], "sombre"), bool("line_numbers", "Numeros", true), bool("caret", "Curseur", true), num("opacity", "Opacite", 0, 1, 1, 0.05)],
  },
  {
    id: "liquid_contours", label: "Contours liquides", category: "generative", scopes: ["scene"], targets: ["text", "image"], needs_audio: false,
    description: "Deformation liquide par feTurbulence + feDisplacementMap.", note: "",
    params: [num("frequency", "Frequence", 0.001, 0.09, 0.012, 0.001), int("octaves", "Octaves", 1, 5, 2), num("displacement", "Amplitude", 0, 160, 42, 1, "px"), bool("animate", "Animer", true), int("cycle_frames", "Periode", 6, 240, 40), num("seed_shift", "Variante", 0, 8, 0, 1)],
  },
  {
    id: "plasma_field", label: "Champ de plasma", category: "generative", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Interferences organiques en canvas 2D.", note: "",
    params: [color("color_a", "Couleur chaude", "#E2B458"), color("color_b", "Couleur froide", "#2B6CE6"), num("scale", "Zoom", 0.4, 8, 2.2, 0.1), num("complexity", "Complexite", 0.5, 6, 2, 0.1), num("speed", "Vitesse", 0, 4, 0.7, 0.05), num("opacity", "Opacite", 0, 1, 0.35, 0.02), select("blend", "Fusion", ["screen", "lighten", "normal", "color-dodge"], "screen")],
  },
  {
    id: "shine", label: "Reflet qui traverse", category: "light", scopes: ["layer"], targets: ["text", "image"], needs_audio: false,
    description: "Balayage lumineux masque sur le calque.", note: "",
    params: [num("width", "Largeur", 0.05, 0.8, 0.22, 0.01, "fraction"), num("angle_deg", "Inclinaison", -90, 90, 20, 1, "degres"), int("period_frames", "Periode", 18, 300, 50), num("intensity", "Intensite", 1, 3, 1.9, 0.05, "x"), num("opacity", "Opacite", 0, 1, 0.75, 0.05), bool("once", "Un seul passage", false)],
  },
  {
    id: "light_leak", label: "Fuite de lumiere", category: "light", scopes: ["overlay"], targets: ["text", "image"], needs_audio: false,
    description: "Halos chauds en fusion ecran.", note: "",
    params: [color("color_a", "Teinte 1", "#FF6B3D"), color("color_b", "Teinte 2", "#FFD166"), num("intensity", "Intensite", 0, 1, 0.4, 0.05), num("size", "Taille", 0.2, 1.6, 0.75, 0.05, "fraction"), int("cycle_frames", "Periode", 40, 900, 180), select("blend", "Fusion", ["screen", "lighten", "color-dodge"], "screen")],
  },
  {
    id: "color_grade", label: "Etalonnage", category: "light", scopes: ["scene"], targets: ["text", "image"], needs_audio: false,
    description: "Courbes de transfert SVG par look + exposition/contraste/saturation.", note: "",
    params: [select("look", "Rendu", ["teal_orange", "bleute", "sepia", "bleu_nuit", "lavande", "noir_blanc"], "teal_orange"), num("strength", "Melange", 0, 1, 0.75, 0.05), num("exposure", "Exposition", 0.4, 2, 1, 0.05), num("contrast", "Contraste", 0.4, 2, 1, 0.05), num("saturation", "Saturation", 0, 2, 1, 0.05), num("vignette", "Vignettage", 0, 1, 0.25, 0.05)],
  },
  {
    id: "depth_blur", label: "Flou progressif et profondeur de champ", category: "light", scopes: ["scene"], targets: ["text", "image"], needs_audio: false,
    description: "Flou progressif autour d'une bande de nettete.", note: "",
    params: [num("focus_y", "Zone de nettete", 0, 1, 0.45, 0.02, "fraction"), num("blur_px", "Flou max", 0, 60, 18, 1, "px"), num("falloff", "Progressivite", 0.15, 2, 0.8, 0.05), bool("top_to_bottom", "Axe vertical", true)],
  },
  {
    id: "chroma_key", label: "Keying sur fond vert", category: "light", scopes: ["layer"], targets: ["image"], needs_audio: false,
    description: "Retrait d'une couleur sur un calque image.", note: "",
    params: [color("key_color", "Couleur a retirer", "#00FF00"), num("similarity", "Similarite", 0, 1, 0.32, 0.02), num("blend", "Adoucissement", 0, 0.4, 0.08, 0.01), num("spill", "Suppression du renvoi", 0, 1, 0.4, 0.05)],
  },
];

const BY_ID = new Map<string, EffectSpec>(EFFECTS.map((e) => [e.id, e]));

export function allEffects(): EffectSpec[] {
  return EFFECTS;
}

export function ids(): string[] {
  return EFFECTS.map((e) => e.id);
}

export function get(effectId: string): EffectSpec | undefined {
  return BY_ID.get(String(effectId));
}

export function manifest() {
  return {
    categories: CATEGORIES.map(([id, label]) => ({ id, label })),
    scopes: [...SCOPES],
    scope_labels: {
      layer: "sur un calque",
      scene: "sur une scene entiere",
      overlay: "plein cadre, par-dessus la scene",
    },
    max_per_target: MAX_EFFECTS_PER_TARGET,
    effects: EFFECTS,
  };
}

function isHexColor(textVal: string): boolean {
  return /^#[0-9a-fA-F]{6}$/.test(textVal);
}

function coerce(
  spec: EffectParamSpec,
  raw: unknown,
  path: string,
  errors: string[],
  warnings: string[],
): unknown {
  if (spec.type === "number" || spec.type === "integer") {
    const n = Number(raw);
    if (raw === null || raw === "" || typeof raw === "boolean" || !Number.isFinite(n)) {
      errors.push(`${path} : valeur numerique attendue, recu ${JSON.stringify(raw)}.`);
      return spec.default;
    }
    let val = spec.type === "integer" ? Math.round(n) : n;
    const lo = spec.min ?? -Infinity;
    const hi = spec.max ?? Infinity;
    if (val < lo || val > hi) {
      val = Math.min(Math.max(val, lo), hi);
      warnings.push(`${path} = ${raw} hors bornes (${lo} a ${hi}) : ramene a ${val} pour le rendu.`);
    }
    return spec.type === "integer" ? Math.round(val) : Math.round(val * 10000) / 10000;
  }
  if (spec.type === "bool") {
    if (typeof raw === "boolean") return raw;
    if (typeof raw === "string" && (raw.toLowerCase() === "true" || raw.toLowerCase() === "false")) {
      return raw.toLowerCase() === "true";
    }
    errors.push(`${path} : attendu vrai/faux, recu ${JSON.stringify(raw)}.`);
    return spec.default;
  }
  if (spec.type === "color") {
    const t = String(raw || "").trim();
    if (isHexColor(t)) return t;
    errors.push(`${path} : couleur hexadecimale attendue (#RRGGBB), recu ${JSON.stringify(raw)}.`);
    return spec.default;
  }
  if (spec.type === "select") {
    const t = String(raw || "").trim();
    if (spec.options && spec.options.includes(t)) return t;
    errors.push(`${path} : valeur inconnue ${JSON.stringify(raw)} (choix : ${(spec.options || []).join(", ")}).`);
    return spec.default;
  }
  let t = raw == null ? "" : String(raw);
  const limit = spec.max_chars ?? 1200;
  if (t.length > limit) {
    errors.push(`${path} : texte trop long (${t.length} caracteres, maximum ${limit}).`);
    t = t.slice(0, limit);
  }
  return t;
}

export function normalize(
  raw: unknown,
  host: "layer" | "scene",
  target: string,
  options: { path: string; audioReady?: boolean },
): [Array<{ id: string; label: string; scope: string; needs_audio: boolean; params: Record<string, unknown> }>, string[], string[]] {
  const errors: string[] = [];
  const warnings: string[] = [];
  const p = options.path;
  if (raw === null || raw === undefined || raw === "" || (Array.isArray(raw) && raw.length === 0)) {
    return [[], errors, warnings];
  }
  if (!Array.isArray(raw)) {
    errors.push(`${p} : liste d'effets attendue.`);
    return [[], errors, warnings];
  }
  if (raw.length > MAX_EFFECTS_PER_TARGET) {
    errors.push(`${p} : ${raw.length} effets, maximum ${MAX_EFFECTS_PER_TARGET} par cible.`);
  }
  const out: Array<{ id: string; label: string; scope: string; needs_audio: boolean; params: Record<string, unknown> }> = [];
  const seen = new Set<string>();

  for (let i = 0; i < Math.min(raw.length, MAX_EFFECTS_PER_TARGET + 8); i++) {
    const tag = `${p}[${i}]`;
    let item = raw[i];
    if (typeof item === "string") item = { id: item };
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      errors.push(`${tag} : objet attendu ({id, params}).`);
      continue;
    }
    const obj = item as Record<string, unknown>;
    const effectId = String(obj.id || "").trim();
    const effect = BY_ID.get(effectId);
    if (!effect) {
      errors.push(`${tag}.id : effet inconnu ${JSON.stringify(effectId)}. Disponibles : ${ids().join(", ")}.`);
      continue;
    }
    if (seen.has(effectId)) {
      errors.push(`${tag} : effet '${effectId}' declare deux fois sur la meme cible.`);
      continue;
    }
    seen.add(effectId);

    let scope: string;
    if (host === "layer") {
      if (!effect.scopes.includes("layer")) {
        errors.push(`${tag} : ${effectId} ne s'applique pas a un calque.`);
        continue;
      }
      if (!effect.targets.includes(target)) {
        errors.push(`${tag} : ${effectId} est prevu pour un calque ${effect.targets.join(" ou ")}, pas '${target}'.`);
        continue;
      }
      scope = "layer";
    } else {
      const allowed = effect.scopes.filter((s) => s === "scene" || s === "overlay");
      if (allowed.length === 0) {
        errors.push(`${tag} : ${effectId} ne s'applique pas a une scene.`);
        continue;
      }
      scope = allowed.includes("overlay") ? "overlay" : "scene";
    }

    if (effect.needs_audio && !options.audioReady) {
      warnings.push(`${tag} : ${effectId} mesure l'audio reelle ; sans musique ni voix active, mouvement regulier.`);
    }

    const paramsIn = (obj.params && typeof obj.params === "object" && !Array.isArray(obj.params))
      ? (obj.params as Record<string, unknown>)
      : {};
    if (obj.params && (typeof obj.params !== "object" || Array.isArray(obj.params))) {
      errors.push(`${tag}.params : objet attendu.`);
    }
    const known = new Set(effect.params.map((spec) => spec.key));
    for (const extra of Object.keys(paramsIn)) {
      if (!known.has(extra)) {
        warnings.push(`${tag}.params.${extra} : reglage inconnu pour ${effectId}, ignore.`);
      }
    }
    const params: Record<string, unknown> = {};
    for (const spec of effect.params) {
      const rawVal = Object.prototype.hasOwnProperty.call(paramsIn, spec.key)
        ? paramsIn[spec.key]
        : spec.default;
      params[spec.key] = coerce(spec, rawVal, `${tag}.params.${spec.key}`, errors, warnings);
    }
    out.push({
      id: effectId,
      label: effect.label,
      scope,
      needs_audio: Boolean(effect.needs_audio),
      params,
    });
  }

  return [out, errors, warnings];
}
