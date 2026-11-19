import * as effectsMod from "./effects.ts";
import * as fontsMod from "./fonts.ts";
import * as schema from "./schema.ts";
import { validateProject } from "./validation.ts";

export function compositionId(project: schema.AnyRecord): string {
  const modelId = String(project?.model?.id || "");
  if (modelId === "quote_vertical" || modelId === "quote_cinematic" || modelId === "quote_horizontal") {
    return modelId;
  }
  throw new Error(`Aucune composition associee au modele '${modelId}'.`);
}

function resolveFont(family: string, weight: unknown): [string, number, string] {
  const fam = fontsMod.isKnownFamily(family) ? family : "inter";
  const w = fontsMod.fallbackWeight(fam, Number(weight) || 400);
  const url = fontsMod.fontUrl(fam, w);
  return [fam, w, url];
}

function effectiveLayerStyle(
  layerStyle: schema.AnyRecord,
  theme: schema.AnyRecord,
  scale: number,
  layerText: string,
  explicitDirection?: string,
) {
  const hasArabic = fontsMod.containsArabic(layerText);
  const requestedFamily = String(layerStyle.font_family || theme.font_family || "playfair-display");
  const requestedFamObj = fontsMod.familyById().get(requestedFamily);
  const supportsArabic = Boolean(requestedFamObj?.scripts?.includes("arabic"));

  const familyRaw =
    hasArabic && !supportsArabic ? fontsMod.preferredArabicFontId() : requestedFamily;
  const weightRaw = layerStyle.font_weight ?? theme.font_weight ?? 700;
  const [familyId, weight, fontUrl] = resolveFont(familyRaw, weightRaw);

  const fontSizeRef = Number(layerStyle.font_size ?? theme.font_size ?? 84);
  const direction: "ltr" | "rtl" = explicitDirection === "rtl" || hasArabic ? "rtl" : "ltr";

  return {
    direction,
    font_id: familyId,
    font_weight: weight,
    font_url: fontUrl,
    font_size_px: Math.max(12, Math.round(fontSizeRef * scale)),
    line_height: Number(layerStyle.line_height ?? theme.line_height ?? 1.18),
    letter_spacing_em: hasArabic ? 0 : Number(layerStyle.letter_spacing ?? theme.letter_spacing ?? 0.0),
    color: String(layerStyle.color || theme.text_color || "#F7F5EF"),
    accent_color: String(layerStyle.accent_color || theme.accent_color || "#E2B458"),
    shadow: Boolean(layerStyle.shadow ?? theme.shadow ?? true),
    stroke_width_px: Math.max(0, Math.round(Number(layerStyle.stroke_width ?? 0) * scale)),
    stroke_color: String(layerStyle.stroke_color || "#000000"),
  };
}

function resolveAnimationTiming(
  raw: schema.AnyRecord,
  sceneStartFrame: number,
  sceneFrames: number,
) {
  const a = raw || {};
  const offset = Math.max(0, Math.min(Number(a.start_frames ?? 0), Math.max(0, sceneFrames - 1)));
  const startFrame = sceneStartFrame + Math.round(offset);
  const maxIn = Math.max(1, sceneFrames - offset);
  const inFrames = Math.max(1, Math.min(Number(a.in_frames ?? 18), maxIn));
  const outFrames = a.out === "none"
    ? 0
    : Math.max(0, Math.min(Number(a.out_frames ?? 12), Math.max(0, sceneFrames - offset - inFrames)));
  const endFrame = sceneStartFrame + sceneFrames;
  const outStartFrame = Math.max(startFrame + Math.round(inFrames), endFrame - Math.round(outFrames));
  const inEndFrame = startFrame + Math.round(inFrames);
  const spreadFrames = a.unit === "block" ? 0 : Math.max(0, Number(a.stagger_frames ?? 0));

  return {
    start_frame: startFrame,
    in_end_frame: inEndFrame,
    spread_frames: spreadFrames,
    units: 1,
    out_start_frame: outStartFrame,
    end_frame: endFrame,
    hold_frames: Math.max(0, outStartFrame - inEndFrame),
    duration_frames: Math.max(1, endFrame - startFrame),
  };
}

export function resolveProject(project: schema.AnyRecord): schema.AnyRecord {
  const [errors] = validateProject(project);
  if (errors.length > 0) {
    throw new Error(`Projet invalide avant resolution :\n- ${errors.join("\n- ")}`);
  }

  const out = schema.clone(project);
  const exp = out.export || {};
  const width = Number(exp.width || 1080);
  const height = Number(exp.height || 1920);
  const fps = Number(exp.fps || 30);
  // P6 fix: short-side scaling so both 1080x1920 and 1920x1080 keep scale = 1.0
  const scale = Math.min(width, height) / 1080;

  const theme = out.theme || schema.defaultTheme();
  const audio = out.audio || {};
  const audioReady = Boolean(audio.enabled && (audio.music || audio.voice));
  const seed = Number(out.variation?.seed ?? 1);

  const fontMap = new Map<string, Set<number>>();
  const registerFont = (id: string, weight: number) => {
    if (!fontMap.has(id)) fontMap.set(id, new Set());
    fontMap.get(id)!.add(weight);
  };

  const assets: Array<{ kind: string; ref: string; scene: string }> = [];
  const resolvedScenes: schema.AnyRecord[] = [];
  let cursor = 0;

  for (const sc of out.content.scenes as schema.AnyRecord[]) {
    const scFrames = Math.max(1, Math.round(Number(sc.duration) * fps));
    const startFrame = cursor;
    const endFrame = cursor + scFrames;
    cursor = endFrame;

    const bg = sc.background || {};
    if (bg.media) assets.push({ kind: "background", ref: bg.media, scene: sc.id });

    const [scEffects] = effectsMod.normalize(sc.effects, "scene", "scene", {
      path: `${sc.id}.effects`,
      audioReady,
    });

    const resolvedLayers: schema.AnyRecord[] = [];
    for (const layer of (sc.layers || []) as schema.AnyRecord[]) {
      if (layer.hidden) continue;
      const [layerEffects] = effectsMod.normalize(layer.effects, "layer", layer.type, {
        path: `${sc.id}.${layer.id}.effects`,
        audioReady,
      });
      const timing = resolveAnimationTiming(layer.animation || {}, startFrame, scFrames);

      if (layer.type === "text") {
        const eff = effectiveLayerStyle(
          layer.style || {},
          theme,
          scale,
          String(layer.text || ""),
          layer.position?.direction,
        );
        registerFont(eff.font_id, eff.font_weight);
        resolvedLayers.push({
          id: layer.id,
          type: "text",
          effects: layerEffects,
          ...timing,
          align: (layer.position?.align || "center") as "left" | "center" | "right",
          direction: eff.direction,
          font_family: eff.font_id,
          font_weight: eff.font_weight,
          font_size_px: eff.font_size_px,
          line_height: eff.line_height,
          letter_spacing_em: eff.letter_spacing_em,
          color: eff.color,
          accent_color: eff.accent_color,
          shadow: eff.shadow,
          stroke_width_px: eff.stroke_width_px,
          stroke_color: eff.stroke_color,
        });
      } else {
        if (layer.media) assets.push({ kind: "layer_image", ref: layer.media, scene: sc.id });
        resolvedLayers.push({
          id: layer.id,
          type: "image",
          effects: layerEffects,
          ...timing,
          align: "center",
          direction: "ltr",
          font_family: "inter",
          font_weight: 400,
          font_size_px: 0,
          line_height: 1,
          letter_spacing_em: 0,
          color: theme.text_color || "#F7F5EF",
          accent_color: theme.accent_color || "#E2B458",
          shadow: false,
          stroke_width_px: 0,
          stroke_color: "#000000",
        });
      }
    }

    const tr = sc.transition || {};
    const tType = String(tr.type || "none");
    const tFrames = tType === "none" ? 0 : Math.max(0, Math.min(Number(tr.frames || 0), Math.floor(scFrames / 2)));

    resolvedScenes.push({
      id: sc.id,
      label: sc.label || sc.id,
      hidden: Boolean(sc.hidden),
      start_frame: startFrame,
      end_frame: endFrame,
      duration_frames: scFrames,
      background: {
        media: String(bg.media || ""),
        fit: String(bg.fit || "cover"),
        animation: String(bg.animation || "static"),
      },
      transition: { type: tType, frames: tFrames },
      effects: scEffects,
      layers: resolvedLayers,
    });
  }

  const totalFrames = Math.max(1, cursor);
  const sigRaw = { ...(out.content.signature || schema.defaultSignature()) };
  const sigFamilyRaw = String(sigRaw.font_family || "space-grotesk");
  const sigHandle = String(sigRaw.handle || "");
  const sigUsesArabic = fontsMod.containsArabic(sigHandle);
  const sigFamilyResolved = sigUsesArabic && !fontsMod.familyById().get(sigFamilyRaw)?.scripts?.includes("arabic")
    ? fontsMod.preferredArabicFontId()
    : sigFamilyRaw;
  const [sigFamId, sigWeight] = resolveFont(sigFamilyResolved, sigRaw.font_weight ?? 500);

  if (sigRaw.enabled && (sigRaw.media || sigHandle)) {
    registerFont(sigFamId, sigWeight);
  }
  if (sigRaw.media) assets.push({ kind: "signature", ref: sigRaw.media, scene: "signature" });
  if (audio.music) assets.push({ kind: "music", ref: audio.music, scene: "audio" });
  if (audio.voice) assets.push({ kind: "voice", ref: audio.voice, scene: "audio" });

  const resolvedSig = {
    ...sigRaw,
    font_family: sigFamId,
    font_weight: sigWeight,
    start_frame: Number(sigRaw.start_frames ?? 12),
    in_frames: Math.max(1, Number(sigRaw.in_frames ?? 18)),
    end_frame: totalFrames,
    font_size_px: Math.max(10, Math.round(Number(sigRaw.font_size ?? 34) * scale)),
    logo_width_px: Math.max(24, Math.round(Number(sigRaw.logo_width ?? 140) * scale)),
  };

  const duration = Math.round((totalFrames / fps) * 10000) / 10000;
  const fontsOut = [...fontMap.entries()].map(([id, weights]) => ({
    id,
    known: fontsMod.isKnownFamily(id),
    weights: [...weights].sort((a, b) => a - b),
  }));

  const comp = compositionId(out);

  out.resolved = {
    model: { id: out.model.id, version: out.model.version },
    composition_id: comp,
    fps,
    width,
    height,
    scale,
    total_frames: totalFrames,
    duration,
    duration_seconds: duration,
    seed,
    fonts: fontsOut,
    signature: resolvedSig,
    audio: {
      enabled: Boolean(audio.enabled),
      music: String(audio.music || ""),
      voice: String(audio.voice || ""),
      music_volume: Number(audio.music_volume ?? 0.3),
      voice_volume: Number(audio.voice_volume ?? 1.0),
      music_fade_in: Number(audio.music_fade_in ?? 1.0),
      music_fade_out: Number(audio.music_fade_out ?? 1.5),
      start_frame: 0,
      end_frame: totalFrames,
      total_frames: totalFrames,
      fps,
      duration,
      markers: Array.isArray(audio.markers) ? audio.markers : [],
    },
    assets,
    scenes: resolvedScenes,
  };

  return out;
}
