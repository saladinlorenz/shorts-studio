export const SCHEMA_VERSION_V2 = 2;

// P6: includes quote_horizontal (16:9 landscape model)
export const MODELS: Record<string, number> = {
  quote_cinematic: 1,
  quote_vertical: 1,
  quote_horizontal: 1,
};

export const ANIM_IN = ["fade", "slide_up", "slide_left", "scale", "mask_reveal", "none"] as const;
export const ANIM_OUT = ["none", "fade"] as const;
export const ANIM_UNITS = ["block", "line", "word"] as const;
export const EASINGS = ["linear", "ease_out_cubic", "ease_out_quint", "spring"] as const;
export const BACKGROUND_FIT = ["cover", "contain"] as const;
export const BACKGROUND_ANIM = ["static", "zoom_slow", "zoom_out"] as const;
export const ALIGNMENTS = ["left", "center", "right"] as const;
export const DIRECTIONS = ["ltr", "rtl"] as const;

export const TRANSITION_TYPES = [
  "none",
  "fade",
  "dip_black",
  "slide_left",
  "slide_right",
  "slide_up",
  "slide_down",
  "wipe",
  "zoom",
  "push",
] as const;

export const TRANSITION_FRAMES_MAX = 60;
export const REF_HEIGHT = 1920;

export const TOTAL_DURATION_MIN = 0.5;
export const TOTAL_DURATION_MAX = 300.0;
export const SCENE_DURATION_MIN = 0.5;
export const SCENE_DURATION_MAX = 120.0;

export type AnyRecord = Record<string, any>;

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function anim(overrides: AnyRecord = {}): AnyRecord {
  return {
    in: "fade",
    out: "fade",
    unit: "block",
    stagger_frames: 0,
    start_frames: 0,
    in_frames: 18,
    out_frames: 12,
    easing: "ease_out_cubic",
    spring: { damping: 16, stiffness: 140, mass: 1 },
    distance: 0.06,
    ...overrides,
  };
}

export function textLayer(
  layerId: string,
  text: string,
  opts: {
    role?: string;
    start_frames?: number;
    in_frames?: number;
    animation?: AnyRecord;
    style?: AnyRecord;
    position?: AnyRecord;
    effects?: AnyRecord[];
    emphasis?: string[];
  } = {},
): AnyRecord {
  return {
    id: layerId,
    type: "text",
    role: opts.role ?? "body",
    text,
    emphasis: opts.emphasis ? [...opts.emphasis] : [],
    hidden: false,
    locked: false,
    effects: opts.effects ? clone(opts.effects) : [],
    position: {
      x: 0.5,
      y: 0.5,
      width: 0.84,
      align: "center",
      direction: "ltr",
      ...(opts.position || {}),
    },
    style: { ...(opts.style || {}) },
    animation: anim({
      start_frames: opts.start_frames ?? 0,
      in_frames: opts.in_frames ?? 18,
      ...(opts.animation || {}),
    }),
  };
}

export function imageLayer(
  layerId: string,
  media = "",
  opts: {
    start_frames?: number;
    in_frames?: number;
    position?: AnyRecord;
    animation?: AnyRecord;
    effects?: AnyRecord[];
  } = {},
): AnyRecord {
  return {
    id: layerId,
    type: "image",
    role: "mark",
    media,
    hidden: false,
    locked: false,
    opacity: 1.0,
    effects: opts.effects ? clone(opts.effects) : [],
    position: {
      x: 0.82,
      y: 0.9,
      width: 0.16,
      align: "center",
      direction: "ltr",
      ...(opts.position || {}),
    },
    animation: anim({
      start_frames: opts.start_frames ?? 0,
      in_frames: opts.in_frames ?? 16,
      out: "none",
      ...(opts.animation || {}),
    }),
  };
}

export function defaultTransition(): { type: string; frames: number } {
  return { type: "none", frames: 0 };
}

export function scene(
  sceneId: string,
  label: string,
  duration: number,
  layers: AnyRecord[],
  opts: {
    effects?: AnyRecord[];
    transition?: AnyRecord;
    media?: string;
    fit?: string;
    animation?: string;
  } = {},
): AnyRecord {
  return {
    id: sceneId,
    label,
    duration,
    hidden: false,
    effects: opts.effects ? clone(opts.effects) : [],
    background: {
      media: opts.media ?? "",
      fit: opts.fit ?? "cover",
      animation: opts.animation ?? "static",
    },
    transition: opts.transition ? clone(opts.transition) : defaultTransition(),
    layers,
  };
}

export function defaultTheme(): AnyRecord {
  return {
    palette_id: "noir_or",
    background_color: "#0B0B10",
    surface_color: "#15151F",
    text_color: "#F7F5EF",
    accent_color: "#E2B458",
    author_color: "#E2B458",
    muted_color: "#9A9AA8",
    font_family: "playfair-display",
    font_weight: 700,
    font_size: 84,
    line_height: 1.18,
    letter_spacing: -0.015,
    shadow: true,
  };
}

export function defaultSignature(): AnyRecord {
  return {
    enabled: true,
    media: "",
    handle: "@votre.marque",
    font_family: "space-grotesk",
    font_weight: 500,
    font_size: 34,
    color: "#9A9AA8",
    logo_width: 0.14,
    position: { x: 0.5, y: 0.945 },
    start_frames: 0,
    in_frames: 24,
  };
}

export function cinematicProject(): AnyRecord {
  const hook = textLayer("hook", "Ce que personne ne te dit", {
    role: "hook",
    start_frames: 4,
    in_frames: 26,
    position: { x: 0.5, y: 0.42, width: 0.86, align: "center" },
    style: {
      font_family: "anton",
      font_weight: 400,
      font_size: 132,
      line_height: 1.02,
      letter_spacing: 0.01,
      color: "#F7F5EF",
    },
    animation: {
      in: "mask_reveal",
      out: "fade",
      unit: "line",
      stagger_frames: 5,
      easing: "spring",
      out_frames: 10,
    },
  });
  const hookCaption = textLayer("hook-caption", "épisode 01", {
    role: "caption",
    start_frames: 20,
    in_frames: 20,
    position: { x: 0.5, y: 0.62, width: 0.6, align: "center" },
    style: {
      font_family: "space-grotesk",
      font_weight: 500,
      font_size: 34,
      letter_spacing: 0.24,
      color: "#E2B458",
    },
    animation: { in: "fade", out: "fade", unit: "block", in_frames: 20 },
  });

  const quote = textLayer(
    "quote",
    "Le courage n'est pas l'absence de peur, mais la decision de continuer malgre elle.",
    {
      role: "quote",
      start_frames: 6,
      in_frames: 22,
      position: { x: 0.5, y: 0.46, width: 0.82, align: "center" },
      style: {
        font_family: "playfair-display",
        font_weight: 700,
        font_size: 88,
        line_height: 1.16,
        letter_spacing: -0.015,
        color: "#F7F5EF",
      },
      animation: {
        in: "slide_up",
        out: "fade",
        unit: "word",
        stagger_frames: 3,
        in_frames: 16,
        easing: "spring",
        distance: 0.045,
      },
      emphasis: ["courage", "continuer"],
    },
  );

  const author = textLayer("author", "— Amelia Runa", {
    role: "author",
    start_frames: 48,
    in_frames: 20,
    position: { x: 0.5, y: 0.68, width: 0.7, align: "center" },
    style: {
      font_family: "space-grotesk",
      font_weight: 500,
      font_size: 42,
      letter_spacing: 0.04,
      color: "#E2B458",
    },
    animation: { in: "fade", out: "fade", unit: "block", in_frames: 20 },
  });

  const reveal = textLayer("reveal", "Agir", {
    role: "reveal",
    start_frames: 4,
    in_frames: 30,
    position: { x: 0.5, y: 0.4, width: 0.9, align: "center" },
    style: {
      font_family: "archivo-black",
      font_weight: 400,
      font_size: 210,
      line_height: 1.0,
      letter_spacing: -0.03,
      color: "#E2B458",
    },
    animation: {
      in: "scale",
      out: "none",
      unit: "block",
      in_frames: 30,
      easing: "spring",
    },
  });
  const revealNote = textLayer("reveal-note", "La marque · votre signature", {
    role: "caption",
    start_frames: 34,
    in_frames: 22,
    position: { x: 0.5, y: 0.58, width: 0.8, align: "center" },
    style: {
      font_family: "inter",
      font_weight: 400,
      font_size: 36,
      letter_spacing: 0.02,
      color: "#F7F5EF",
    },
    animation: { in: "slide_up", out: "none", unit: "block", distance: 0.03 },
  });

  return {
    version: SCHEMA_VERSION_V2,
    model: { id: "quote_cinematic", version: MODELS.quote_cinematic },
    name: "citation-cinematique",
    content: {
      scenes: [
        scene("s1", "Accroche", 4.0, [hook, hookCaption]),
        scene("s2", "Citation", 6.0, [quote, author]),
        scene("s3", "Signature", 3.5, [reveal, revealNote]),
      ],
      signature: defaultSignature(),
    },
    theme: defaultTheme(),
    audio: {
      music: "",
      voice: "",
      music_volume: 0.3,
      voice_volume: 1.0,
      music_fade_in: 1.0,
      music_fade_out: 1.5,
      markers: [],
      enabled: false,
    },
    variation: { seed: 1 },
    export: {
      width: 1080,
      height: 1920,
      fps: 30,
      output_dir: "",
      filename: "",
    },
  };
}

/**
 * P6 : Modèle horizontal natif 16:9 (1920x1080) pour YouTube, LinkedIn et présentations.
 * Les positions Y, largeurs de bloc et tailles de police sont calibrées pour un cadre 16:9.
 */
export function horizontalProject(): AnyRecord {
  const hook = textLayer("hook", "Ce qui distingue l'essentiel du bruit", {
    role: "hook",
    start_frames: 4,
    in_frames: 24,
    position: { x: 0.5, y: 0.44, width: 0.78, align: "center" },
    style: {
      font_family: "anton",
      font_weight: 400,
      font_size: 104,
      line_height: 1.05,
      letter_spacing: 0.01,
      color: "#F7F5EF",
    },
    animation: {
      in: "mask_reveal",
      out: "fade",
      unit: "line",
      stagger_frames: 5,
      easing: "spring",
      out_frames: 10,
    },
  });
  const hookCaption = textLayer("hook-caption", "FORMAT PAYSAGE 16:9 · ÉPISODE 01", {
    role: "caption",
    start_frames: 18,
    in_frames: 18,
    position: { x: 0.5, y: 0.66, width: 0.68, align: "center" },
    style: {
      font_family: "space-grotesk",
      font_weight: 500,
      font_size: 28,
      letter_spacing: 0.2,
      color: "#E2B458",
    },
    animation: { in: "fade", out: "fade", unit: "block", in_frames: 18 },
  });

  const quote = textLayer(
    "quote",
    "La clarté d'une idée se mesure à la simplicité avec laquelle elle traverse l'écran.",
    {
      role: "quote",
      start_frames: 6,
      in_frames: 22,
      position: { x: 0.5, y: 0.44, width: 0.78, align: "center" },
      style: {
        font_family: "playfair-display",
        font_weight: 700,
        font_size: 72,
        line_height: 1.18,
        letter_spacing: -0.015,
        color: "#F7F5EF",
      },
      animation: {
        in: "slide_up",
        out: "fade",
        unit: "word",
        stagger_frames: 3,
        in_frames: 16,
        easing: "spring",
        distance: 0.04,
      },
      emphasis: ["clarté", "simplicité"],
    },
  );
  const author = textLayer("author", "— Studio Vidéo", {
    role: "author",
    start_frames: 42,
    in_frames: 18,
    position: { x: 0.5, y: 0.68, width: 0.65, align: "center" },
    style: {
      font_family: "space-grotesk",
      font_weight: 500,
      font_size: 34,
      letter_spacing: 0.04,
      color: "#E2B458",
    },
    animation: { in: "fade", out: "fade", unit: "block", in_frames: 18 },
  });

  const reveal = textLayer("reveal", "Agir", {
    role: "reveal",
    start_frames: 4,
    in_frames: 28,
    position: { x: 0.5, y: 0.42, width: 0.8, align: "center" },
    style: {
      font_family: "archivo-black",
      font_weight: 400,
      font_size: 164,
      line_height: 1.0,
      letter_spacing: -0.025,
      color: "#E2B458",
    },
    animation: { in: "scale", out: "none", unit: "block", in_frames: 28, easing: "spring" },
  });
  const revealNote = textLayer("reveal-note", "Votre marque · format cinéma 16:9", {
    role: "caption",
    start_frames: 30,
    in_frames: 20,
    position: { x: 0.5, y: 0.63, width: 0.72, align: "center" },
    style: {
      font_family: "inter",
      font_weight: 400,
      font_size: 32,
      letter_spacing: 0.02,
      color: "#F7F5EF",
    },
    animation: { in: "slide_up", out: "none", unit: "block", distance: 0.03 },
  });

  return {
    version: SCHEMA_VERSION_V2,
    model: { id: "quote_horizontal", version: MODELS.quote_horizontal },
    name: "citation-horizontale",
    content: {
      scenes: [
        scene("s1", "Accroche 16:9", 4.0, [hook, hookCaption]),
        scene("s2", "Message principal", 6.0, [quote, author]),
        scene("s3", "Signature 16:9", 3.5, [reveal, revealNote]),
      ],
      signature: {
        ...defaultSignature(),
        font_size: 28,
        logo_width: 0.09,
        position: { x: 0.5, y: 0.91 },
      },
    },
    theme: {
      ...defaultTheme(),
      font_size: 72,
    },
    audio: {
      music: "",
      voice: "",
      music_volume: 0.3,
      voice_volume: 1.0,
      music_fade_in: 1.0,
      music_fade_out: 1.5,
      markers: [],
      enabled: false,
    },
    variation: { seed: 1 },
    export: {
      width: 1920,
      height: 1080,
      fps: 30,
      output_dir: "",
      filename: "",
    },
  };
}

export function presetProject(presetId: string): AnyRecord {
  if (presetId === "citation-horizontale") {
    return horizontalProject();
  }
  if (presetId !== "recit-cinematique" && presetId !== "showcase-cinematique") {
    throw new Error(`Preset inconnu : ${JSON.stringify(presetId)}.`);
  }

  const project = cinematicProject();
  project.name = presetId;
  Object.assign(project.content.signature, { enabled: false, media: "", handle: "" });
  Object.assign(project.audio, {
    music: "",
    voice: "",
    enabled: false,
    music_volume: 0.12,
    voice_volume: 1.0,
    music_fade_in: 0.6,
    music_fade_out: 1.0,
  });

  const narrative = presetId === "recit-cinematique";
  type Beat = [string, number, string, string, string, number, number, string];
  let beats: Beat[];
  let sceneEffects: Record<number, AnyRecord[]>;
  let titleEffects: Record<number, AnyRecord[]>;

  if (narrative) {
    Object.assign(project.theme, {
      palette_id: "bleu_ambre",
      background_color: "#080F1E",
      surface_color: "#192D48",
      text_color: "#F6F3EC",
      accent_color: "#E8B46A",
      author_color: "#E8B46A",
      muted_color: "#AAB4C4",
      font_family: "space-grotesk",
      font_weight: 700,
      font_size: 84,
      line_height: 1.12,
      letter_spacing: -0.015,
    });
    beats = [
      ["Accroche", 3.0, "Tout part\nd’un choix.", "Une idée peut tout changer.", "hook", 0.38, 0.59, "mask_reveal"],
      ["Contexte", 4.0, "Chaque jour,\nle même chemin.", "Le confort avait pris toute la place.", "body", 0.46, 0.68, "slide_up"],
      ["Tension", 4.0, "Et si rien\nne changeait ?", "Attendre devenait le vrai risque.", "body", 0.40, 0.63, "mask_reveal"],
      ["Déclic", 4.0, "Un premier pas.", "Pas parfait. Mais bien réel.", "reveal", 0.48, 0.70, "scale"],
      ["Conclusion", 3.0, "À vous\nd’écrire la suite.", "Commencez petit. Commencez maintenant.", "reveal", 0.42, 0.64, "mask_reveal"],
    ];
    sceneEffects = {
      1: [{ id: "light_leak", params: { color_a: "#E8B46A", color_b: "#FFD99A", intensity: 0.12, size: 0.65, cycle_frames: 180 } }],
      4: [{ id: "color_grade", params: { look: "teal_orange", strength: 0.15, contrast: 1.05, vignette: 0.1 } }],
    };
    titleEffects = {
      1: [{ id: "shine", params: { once: true, period_frames: 55, width: 0.2, intensity: 1.5, opacity: 0.45 } }],
      4: [{ id: "spring_pop", params: { damping: 18, stiffness: 160, mass: 1, overshoot: 1.06, rotate_deg: 0 } }],
    };
  } else {
    Object.assign(project.theme, {
      palette_id: "noir_or",
      background_color: "#0B0B10",
      surface_color: "#24232B",
      text_color: "#FAF8F2",
      accent_color: "#D9BC7A",
      author_color: "#D9BC7A",
      muted_color: "#B7B3AA",
      font_family: "playfair-display",
      font_weight: 700,
      font_size: 92,
      line_height: 1.16,
      letter_spacing: 0.01,
    });
    beats = [
      ["Promesse", 3.0, "L’essentiel,\nsublimé.", "Une présence. Tout simplement.", "hook", 0.40, 0.62, "mask_reveal"],
      ["Détail", 4.0, "Le sens\ndu détail.", "Chaque ligne compte.", "body", 0.68, 0.83, "slide_up"],
      ["Bénéfice", 4.0, "Plus de place\npour l’essentiel.", "Votre quotidien, en plus simple.", "body", 0.68, 0.83, "mask_reveal"],
      ["Invitation", 3.0, "Faites place\nà l’exception.", "Découvrez votre prochain essentiel.", "reveal", 0.42, 0.65, "scale"],
    ];
    sceneEffects = {
      1: [{ id: "light_leak", params: { color_a: "#D9BC7A", color_b: "#FAF8F2", intensity: 0.08, size: 0.6, cycle_frames: 240 } }],
    };
    titleEffects = {
      4: [{ id: "shine", params: { once: true, period_frames: 60, width: 0.18, intensity: 1.4, opacity: 0.4 } }],
    };
  }

  const scenes: AnyRecord[] = [];
  beats.forEach(([label, duration, text, caption, role, titleY, captionY, entrance], idx0) => {
    const index = idx0 + 1;
    const titleStyle: AnyRecord = {};
    if (narrative && (index === 1 || index === 5)) {
      Object.assign(titleStyle, { font_family: "anton", font_weight: 400, font_size: 112, line_height: 1.04 });
    } else if (!narrative && (index === 2 || index === 3)) {
      titleStyle.font_size = 76;
    }
    const title = textLayer("title", text, {
      role,
      start_frames: 4,
      in_frames: 24,
      position: { y: titleY, width: 0.82 },
      style: titleStyle,
      animation: {
        in: entrance,
        unit: text.includes("\n") ? "line" : "block",
        stagger_frames: 4,
        out_frames: 10,
        easing: "ease_out_quint",
        distance: 0.035,
      },
      effects: titleEffects[index],
    });
    const subtitle = textLayer("subtitle", caption, {
      role: "caption",
      start_frames: 24,
      in_frames: 18,
      position: { y: captionY, width: 0.82 },
      style: {
        font_family: "space-grotesk",
        font_weight: 500,
        font_size: 32,
        line_height: 1.3,
        letter_spacing: 0.05,
      },
      animation: { in: "slide_up", unit: "block", distance: 0.02, out_frames: 10 },
      emphasis: [caption],
    });
    const layers: AnyRecord[] = [title, subtitle];
    if (!narrative && (index === 2 || index === 3)) {
      const visual = imageLayer("visual", "", {
        start_frames: 0,
        in_frames: 24,
        position: { x: 0.5, y: 0.36, width: 0.68 },
        animation: { in: "scale", out: "fade", out_frames: 10, easing: "ease_out_quint" },
      });
      visual.hidden = true;
      layers.unshift(visual);
    }
    scenes.push(
      scene(`s${index}`, label, duration, layers, {
        effects: sceneEffects[index],
        media: "",
        animation: index % 2 ? "zoom_slow" : "zoom_out",
      }),
    );
  });
  project.content.scenes = scenes;
  return project;
}

export function newProject(modelId = "quote_cinematic"): AnyRecord {
  if (!(modelId in MODELS)) {
    throw new Error(`Modele inconnu : ${JSON.stringify(modelId)} (connus : ${Object.keys(MODELS).join(", ")}).`);
  }
  if (modelId === "quote_horizontal") {
    return horizontalProject();
  }
  return cinematicProject();
}

export function fpsOf(project: AnyRecord): number {
  return Number(project?.export?.fps ?? 30) || 30;
}

export function totalDuration(project: AnyRecord): number {
  const scenes = (project?.content?.scenes || []) as AnyRecord[];
  return scenes.reduce((acc, sc) => acc + Number(sc.duration || 0), 0);
}

export function totalFrames(project: AnyRecord): number {
  const fps = fpsOf(project);
  const scenes = (project?.content?.scenes || []) as AnyRecord[];
  return scenes.reduce((acc, sc) => acc + Math.round(Number(sc.duration || 0) * fps), 0);
}

const V1_FONT_MAP: Record<string, [string, number]> = {
  "arialbd.ttf": ["inter", 700],
  "arial.ttf": ["inter", 400],
  "segoeuib.ttf": ["inter", 700],
  "segoeui.ttf": ["inter", 400],
  "verdana.ttf": ["inter", 400],
  "calibrib.ttf": ["inter", 700],
  "calibri.ttf": ["inter", 400],
  "georgia.ttf": ["playfair-display", 400],
  "times.ttf": ["playfair-display", 400],
  "impact.ttf": ["anton", 400],
};

export function upgradeV1ToV2(v1: AnyRecord): [AnyRecord, string[]] {
  if (v1?.version !== 1) {
    throw new Error(`Conversion attendue un projet v1, recu version ${JSON.stringify(v1?.version)}.`);
  }
  const notes: string[] = [];
  const themeV1 = v1.theme || {};
  const timing = v1.timing || {};
  const position = v1.position || {};
  const animation = v1.animation || {};
  const content = v1.content || {};
  const exp = v1.export || {};
  const fps = Number(exp.fps || 30) || 30;

  const familyV1 = String(themeV1.font_family || "");
  const mapped = V1_FONT_MAP[familyV1.toLowerCase()];
  let family = "inter";
  let weight = Number(themeV1.font_weight || 700);
  if (mapped) {
    [family, weight] = mapped;
    notes.push(`Police : ${familyV1} remplacee par ${family} poids ${weight} sous licence OFL.`);
  } else {
    notes.push(`Police : ${familyV1 || "non definie"} remplacee par inter.`);
  }

  const frames = (sec: unknown): number => {
    const n = Number(sec);
    return Number.isFinite(n) ? Math.max(0, Math.round(n * fps)) : 0;
  };

  const quote = textLayer("quote", String(content.text || ""), {
    role: "quote",
    start_frames: frames(timing.text_start ?? 0),
    in_frames: frames(timing.fade_in ?? 0.8) || 1,
    position: {
      x: Number(position.x ?? 0.5),
      y: Number(position.y ?? 0.45),
      width: Number(position.width ?? 0.85),
      align: "center",
    },
    style: {
      font_family: family,
      font_weight: weight,
      font_size: Number(themeV1.font_size ?? 72),
      color: themeV1.text_color ?? "#FFFFFF",
      shadow: Boolean(themeV1.shadow ?? true),
    },
    animation: {
      in: animation.text_in === "slide" ? "slide_up" : "fade",
      out: "fade",
      unit: "block",
      out_frames: frames(timing.fade_out ?? 0.8) || 1,
    },
  });

  const layers: AnyRecord[] = [quote];
  const authorText = String(content.author || "").trim();
  if (authorText) {
    layers.push(
      textLayer("author", authorText.startsWith("—") ? authorText : `— ${authorText}`, {
        role: "author",
        start_frames: frames(timing.text_start ?? 0) + Math.max(8, frames(timing.fade_in ?? 0.8)),
        in_frames: frames(timing.fade_in ?? 0.8) || 1,
        position: {
          x: Number(position.x ?? 0.5),
          y: Math.min(0.95, Number(position.y ?? 0.45) + 0.22),
          width: 0.7,
        },
        style: {
          font_family: family,
          font_weight: weight,
          font_size: Math.max(20, Number(themeV1.font_size ?? 72) * 0.5),
          color: themeV1.author_color ?? "#F2C14E",
        },
        animation: { in: "fade", out: "fade" },
      }),
    );
  }

  const logo = String(content.logo || "");
  const signature = defaultSignature();
  signature.media = logo;
  signature.enabled = Boolean(logo);

  const duration = Number(timing.duration ?? 8.0);
  const project: AnyRecord = {
    version: SCHEMA_VERSION_V2,
    model: { id: "quote_cinematic", version: MODELS.quote_cinematic },
    name: String(v1.name || "projet-converti"),
    content: {
      scenes: [
        scene("s1", "Citation", duration, layers, {
          media: String(content.background_image || ""),
          fit: "cover",
          animation: String(animation.background || "static"),
        }),
      ],
      signature,
    },
    theme: {
      ...defaultTheme(),
      text_color: themeV1.text_color ?? defaultTheme().text_color,
      author_color: themeV1.author_color ?? defaultTheme().author_color,
      accent_color: themeV1.accent_color ?? defaultTheme().accent_color,
      font_family: family,
      font_weight: weight,
      font_size: Number(themeV1.font_size ?? 84),
      shadow: Boolean(themeV1.shadow ?? true),
    },
    audio: {
      music: "",
      voice: "",
      music_volume: 0.3,
      voice_volume: 1.0,
      music_fade_in: 1.0,
      music_fade_out: 1.5,
      markers: [],
      enabled: false,
    },
    variation: { seed: 1 },
    export: {
      width: Number(exp.width ?? 1080),
      height: Number(exp.height ?? 1920),
      fps,
      output_dir: String(exp.output_dir || ""),
      filename: "",
    },
  };
  return [project, notes];
}
