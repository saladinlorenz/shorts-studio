import type { SubtitleCue } from "./captions.ts";

export const EDL_VERSION = 1;

export const RESOLUTIONS = ["1080x1920", "1920x1080", "1080x1080"] as const;
export const TRANSITIONS = ["cut", "none", "fade", "dissolve", "fadeblack", "wipeleft", "wiperight", "slideup"] as const;
export const GRADES = ["none", "warm", "cool", "sepia", "mono", "teal_orange"] as const;
export const SPEED_MIN = 0.25;
export const SPEED_MAX = 4.0;

export interface EdlCut {
  media: string;
  in: number;
  out: number;
  speed: number;
  role: string;
  reason: string;
  transition: string;
  transition_duration: number;
}

export interface EdlAudio {
  music: string;
  voice: string;
  music_volume: number;
  voice_volume: number;
  gain_db: number;
  duck: boolean;
  fade_in: number;
  fade_out: number;
  loudnorm: boolean;
}

export interface EdlSubtitles {
  enabled: boolean;
  burn_in: boolean;
  style: {
    font_size: number;
    color: string;
    position: "bottom" | "center";
  };
  cues: SubtitleCue[];
}

export interface NormalizedEdl {
  version: number;
  title: string;
  resolution: string;
  canvas: { width: number; height: number; fps: number };
  fps: number;
  transition_seconds: number;
  cuts: EdlCut[];
  audio: EdlAudio;
  subtitles: EdlSubtitles;
  grade: { look: string; saturation: number; contrast: number };
}

const MEDIA_REF_RE = /^media:\/\/([0-9a-zA-Z_-]{4,64})$/;
const HEX_COLOR_RE = /^#[0-9A-Fa-f]{6}$/;

export function normalize(raw: unknown): NormalizedEdl {
  const src = (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {}) as Record<string, any>;

  const rawCanvas = (src.canvas && typeof src.canvas === "object" ? src.canvas : null) as Record<string, any> | null;
  let resolution = String(src.resolution || "").trim();
  let width = Number(rawCanvas?.width || 0);
  let height = Number(rawCanvas?.height || 0);
  let fps = Number(rawCanvas?.fps ?? src.fps ?? 30);

  if (!resolution && width > 0 && height > 0) {
    resolution = `${width}x${height}`;
  } else if (!resolution) {
    resolution = "1080x1920";
  }
  const [rw, rh] = resolution.split("x").map(Number);
  if (!width) width = rw || 1080;
  if (!height) height = rh || 1920;
  fps = Number.isFinite(fps) ? Math.round(fps) : 30;

  const rawCuts = Array.isArray(src.cuts) ? src.cuts : [];
  const cuts: EdlCut[] = rawCuts.map((c: any) => {
    const cut = c && typeof c === "object" ? c : {};
    const speedRaw = Number(cut.speed ?? 1.0);
    let trType = "none";
    let trDur = Number(src.transition_seconds ?? 0.35);
    if (typeof cut.transition === "string") {
      trType = cut.transition.trim() || "none";
    } else if (cut.transition && typeof cut.transition === "object") {
      trType = String(cut.transition.type || "cut").trim();
      if (Number.isFinite(Number(cut.transition.duration))) {
        trDur = Number(cut.transition.duration);
      }
    }
    return {
      media: String(cut.media || "").trim(),
      in: Number(cut.in ?? 0),
      out: Number(cut.out ?? 0),
      speed: Number.isFinite(speedRaw) ? Math.round(speedRaw * 1000) / 1000 : 1.0,
      role: String(cut.role || "body").trim(),
      reason: String(cut.reason || "").trim(),
      transition: trType,
      transition_duration: Math.max(0, Math.min(2, trDur)),
    };
  });

  const rawAudio = (src.audio && typeof src.audio === "object" ? src.audio : {}) as Record<string, any>;
  const gainDb = Number.isFinite(Number(rawAudio.gain_db)) ? Number(rawAudio.gain_db) : -12;
  const computedMusicVol = Number.isFinite(Number(rawAudio.music_volume))
    ? Number(rawAudio.music_volume)
    : Math.min(1, Math.max(0.01, Math.pow(10, gainDb / 20)));

  const audio: EdlAudio = {
    music: String(rawAudio.music || "").trim(),
    voice: String(rawAudio.voice || "").trim(),
    music_volume: computedMusicVol,
    voice_volume: Number.isFinite(Number(rawAudio.voice_volume)) ? Number(rawAudio.voice_volume) : 1.0,
    gain_db: gainDb,
    duck: rawAudio.duck === undefined ? true : Boolean(rawAudio.duck),
    fade_in: Number.isFinite(Number(rawAudio.fade_in)) ? Number(rawAudio.fade_in) : 1.0,
    fade_out: Number.isFinite(Number(rawAudio.fade_out)) ? Number(rawAudio.fade_out) : 1.5,
    loudnorm: rawAudio.loudnorm === undefined ? true : Boolean(rawAudio.loudnorm),
  };

  const rawSubs = (src.subtitles && typeof src.subtitles === "object" ? src.subtitles : {}) as Record<string, any>;
  const rawStyle = (rawSubs.style && typeof rawSubs.style === "object" ? rawSubs.style : {}) as Record<string, any>;
  const rawCues = Array.isArray(rawSubs.cues) ? rawSubs.cues : [];
  const cues: SubtitleCue[] = rawCues
    .filter((q: any) => q && typeof q === "object" && typeof q.text === "string")
    .map((q: any) => ({
      start: Math.max(0, Number(q.start || 0)),
      end: Math.max(0, Number(q.end || 0)),
      text: String(q.text).trim().slice(0, 200),
    }));

  const subtitles: EdlSubtitles = {
    enabled: Boolean(rawSubs.enabled),
    burn_in: rawSubs.burn_in === undefined ? Boolean(rawSubs.enabled) : Boolean(rawSubs.burn_in),
    style: {
      font_size: Number.isFinite(Number(rawStyle.font_size)) ? Math.round(Number(rawStyle.font_size)) : 28,
      color: typeof rawStyle.color === "string" && HEX_COLOR_RE.test(rawStyle.color.trim())
        ? rawStyle.color.trim()
        : "#FFFFFF",
      position: rawStyle.position === "center" ? "center" : "bottom",
    },
    cues,
  };

  const rawGrade = (src.grade && typeof src.grade === "object" ? src.grade : {}) as Record<string, any>;
  const grade = {
    look: String(rawGrade.look || "none").trim(),
    saturation: Number.isFinite(Number(rawGrade.saturation)) ? Number(rawGrade.saturation) : 1.0,
    contrast: Number.isFinite(Number(rawGrade.contrast)) ? Number(rawGrade.contrast) : 1.0,
  };

  return {
    version: Number(src.version || EDL_VERSION),
    title: String(src.title || "Montage").trim().slice(0, 120),
    resolution,
    canvas: { width, height, fps },
    fps,
    transition_seconds: Number.isFinite(Number(src.transition_seconds)) ? Number(src.transition_seconds) : 0.35,
    cuts,
    audio,
    subtitles,
    grade,
  };
}

export function validate(
  edl: NormalizedEdl,
  opts: { mediaExists?: (mediaId: string) => boolean } = {},
): [string[], string[]] {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!(RESOLUTIONS as readonly string[]).includes(edl.resolution)) {
    errors.push(`resolution : '${edl.resolution}' inconnue (choix : ${RESOLUTIONS.join(", ")}).`);
  }
  if (!Number.isInteger(edl.fps) || edl.fps < 12 || edl.fps > 60) {
    errors.push("fps : entier entre 12 et 60 requis.");
  }
  if (!Number.isFinite(edl.transition_seconds) || edl.transition_seconds < 0 || edl.transition_seconds > 2.0) {
    errors.push("transition_seconds : entre 0 et 2.0s.");
  }
  if (!Array.isArray(edl.cuts) || edl.cuts.length === 0) {
    errors.push("cuts : au moins un plan est requis.");
    return [errors, warnings];
  }
  if (edl.cuts.length > 80) {
    errors.push("cuts : maximum 80 plans par montage.");
  }

  edl.cuts.forEach((cut, idx) => {
    const tag = `cuts[${idx}]`;
    const m = MEDIA_REF_RE.exec(cut.media);
    if (!m) {
      errors.push(`${tag}.media : reference 'media://<id>' attendue.`);
    } else if (opts.mediaExists && !opts.mediaExists(m[1])) {
      errors.push(`${tag}.media : media introuvable (${cut.media}).`);
    }
    if (!Number.isFinite(cut.in) || cut.in < 0) {
      errors.push(`${tag}.in : temps d'entree >= 0 attendu.`);
    }
    if (!Number.isFinite(cut.out) || cut.out <= cut.in) {
      errors.push(`${tag}.out : doit etre strictement superieur a 'in'.`);
    }
    if (!Number.isFinite(cut.speed) || cut.speed < SPEED_MIN || cut.speed > SPEED_MAX) {
      errors.push(`${tag}.speed : vitesse entre ${SPEED_MIN}x et ${SPEED_MAX}x requise (recu ${cut.speed}).`);
    }
    if (!(TRANSITIONS as readonly string[]).includes(cut.transition)) {
      errors.push(`${tag}.transition : '${cut.transition}' inconnu (choix : ${TRANSITIONS.join(", ")}).`);
    }
    const rawDur = (cut.out - cut.in) / (cut.speed || 1);
    if (rawDur < 0.2) {
      warnings.push(`${tag} : plan tres court (${rawDur.toFixed(2)}s apres vitesse).`);
    }
  });

  if (edl.audio.music) {
    const m = MEDIA_REF_RE.exec(edl.audio.music);
    if (!m) errors.push("audio.music : reference 'media://<id>' invalide.");
    else if (opts.mediaExists && !opts.mediaExists(m[1])) errors.push("audio.music : media introuvable.");
  }
  if (edl.audio.voice) {
    const m = MEDIA_REF_RE.exec(edl.audio.voice);
    if (!m) errors.push("audio.voice : reference 'media://<id>' invalide.");
    else if (opts.mediaExists && !opts.mediaExists(m[1])) errors.push("audio.voice : media introuvable.");
  }

  if (edl.subtitles.enabled) {
    if (edl.subtitles.style.font_size < 14 || edl.subtitles.style.font_size > 96) {
      errors.push("subtitles.style.font_size : entre 14 et 96 px.");
    }
    if (edl.subtitles.cues.length === 0) {
      warnings.push("subtitles.enabled est actif mais aucune phrase (cues) n'est definie : des cues automatiques par plan seront utilises.");
    }
    edl.subtitles.cues.forEach((cue, i) => {
      if (cue.end <= cue.start) {
        errors.push(`subtitles.cues[${i}] : end (${cue.end}) doit depasser start (${cue.start}).`);
      }
      if (!cue.text) {
        errors.push(`subtitles.cues[${i}] : texte vide.`);
      }
    });
  }

  return [errors, warnings];
}

export function timelineDuration(edl: NormalizedEdl): number {
  let total = 0;
  edl.cuts.forEach((cut, idx) => {
    const dur = Math.max(0, (cut.out - cut.in) / (cut.speed || 1));
    total += dur;
    const isHardCut = cut.transition === "none" || cut.transition === "cut";
    const overlap = cut.transition_duration || edl.transition_seconds;
    if (idx > 0 && !isHardCut && overlap > 0) {
      total = Math.max(0.1, total - Math.min(overlap, dur * 0.4));
    }
  });
  return Math.round(total * 1000) / 1000;
}
