import * as effectsMod from "./effects.ts";
import * as fontsMod from "./fonts.ts";
import * as schema from "./schema.ts";

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function safeFont(
  family: string,
  weight: unknown,
  path: string,
  errors: string[],
  warnings: string[],
): [string, number] {
  if (!fontsMod.isKnownFamily(family)) {
    errors.push(`${path} : police '${family}' absente du catalogue du studio.`);
    return [family, Number(weight) || 400];
  }
  const w = Number(weight);
  if (!Number.isInteger(w)) {
    errors.push(`${path} : graisse invalide (${JSON.stringify(weight)}).`);
    return [family, fontsMod.fallbackWeight(family, 400)];
  }
  if (!fontsMod.hasWeight(family, w)) {
    const fb = fontsMod.fallbackWeight(family, w);
    warnings.push(`${path} : '${family}' n'a pas la graisse ${w} ; repli sur ${fb}.`);
    return [family, fb];
  }
  return [family, w];
}

export function safePosition(pos: unknown, path: string, errors: string[]): void {
  if (!pos || typeof pos !== "object" || Array.isArray(pos)) {
    errors.push(`${path} : position attendue.`);
    return;
  }
  const p = pos as Record<string, unknown>;
  for (const axis of ["x", "y"] as const) {
    const val = p[axis];
    if (!isNum(val) || val < 0 || val > 1) {
      errors.push(`${path}.${axis} : doit etre entre 0 et 1 (recu ${JSON.stringify(val)}).`);
    }
  }
  if (p.width !== undefined) {
    const w = p.width;
    if (!isNum(w) || w < 0.05 || w > 1.0) {
      errors.push(`${path}.width : doit etre entre 0.05 et 1.0.`);
    }
  }
  if (p.align !== undefined && !(schema.ALIGNMENTS as readonly string[]).includes(String(p.align))) {
    errors.push(`${path}.align : '${p.align}' inconnu.`);
  }
  if (p.direction !== undefined && !(schema.DIRECTIONS as readonly string[]).includes(String(p.direction))) {
    errors.push(`${path}.direction : '${p.direction}' inconnu (ltr/rtl).`);
  }
}

export function validateProject(project: unknown): [string[], string[]] {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!project || typeof project !== "object" || Array.isArray(project)) {
    return [["Le projet doit etre un objet JSON."], warnings];
  }
  const proj = project as schema.AnyRecord;
  if (proj.version !== schema.SCHEMA_VERSION_V2) {
    errors.push(`Version de projet non prise en charge (${proj.version}).`);
    return [errors, warnings];
  }
  const model = proj.model || {};
  const modelId = String(model.id || "");
  if (!(modelId in schema.MODELS)) {
    errors.push(`Modele inconnu : '${modelId}'.`);
  }

  const content = proj.content || {};
  const scenes = content.scenes;
  if (!Array.isArray(scenes) || scenes.length === 0) {
    errors.push("Le projet doit contenir au moins une scene.");
    return [errors, warnings];
  }

  const exp = proj.export || {};
  const width = Number(exp.width || 1080);
  const height = Number(exp.height || 1920);
  const fps = Number(exp.fps || 30);
  if (!Number.isInteger(width) || width < 320 || width > 3840) {
    errors.push("export.width doit etre un entier entre 320 et 3840.");
  }
  if (!Number.isInteger(height) || height < 320 || height > 3840) {
    errors.push("export.height doit etre un entier entre 320 et 3840.");
  }
  if (!Number.isInteger(fps) || fps < 12 || fps > 60) {
    errors.push("export.fps doit etre un entier entre 12 et 60.");
  }

  const theme = proj.theme || {};
  if (theme.font_family) {
    safeFont(String(theme.font_family), theme.font_weight ?? 700, "theme", errors, warnings);
  }
  const audio = proj.audio || {};
  const audioReady = Boolean(audio.enabled && (audio.music || audio.voice));

  let totalDur = 0;
  scenes.forEach((sc: schema.AnyRecord, idx: number) => {
    const spath = `content.scenes[${idx}]`;
    const dur = Number(sc?.duration);
    if (!Number.isFinite(dur) || dur < schema.SCENE_DURATION_MIN || dur > schema.SCENE_DURATION_MAX) {
      errors.push(`${spath}.duration : duree entre ${schema.SCENE_DURATION_MIN} et ${schema.SCENE_DURATION_MAX} s requise.`);
    } else {
      totalDur += dur;
    }

    const transition = sc?.transition || {};
    if (transition.type && !(schema.TRANSITION_TYPES as readonly string[]).includes(String(transition.type))) {
      errors.push(`${spath}.transition.type : transition '${transition.type}' inconnue.`);
    }
    if (transition.frames !== undefined) {
      const tf = Number(transition.frames);
      if (!Number.isInteger(tf) || tf < 0 || tf > schema.TRANSITION_FRAMES_MAX) {
        errors.push(`${spath}.transition.frames : entier entre 0 et ${schema.TRANSITION_FRAMES_MAX}.`);
      }
    }

    const [, scErr, scWarn] = effectsMod.normalize(sc?.effects, "scene", "scene", {
      path: `${spath}.effects`,
      audioReady,
    });
    errors.push(...scErr);
    warnings.push(...scWarn);

    const layers = sc?.layers;
    if (!Array.isArray(layers)) {
      errors.push(`${spath}.layers : liste attendue.`);
      return;
    }
    layers.forEach((layer: schema.AnyRecord, lidx: number) => {
      const lpath = `${spath}.layers[${lidx}]`;
      if (!layer || typeof layer !== "object") {
        errors.push(`${lpath} : objet attendu.`);
        return;
      }
      if (layer.type !== "text" && layer.type !== "image") {
        errors.push(`${lpath}.type : '${layer.type}' inconnu.`);
        return;
      }
      safePosition(layer.position, `${lpath}.position`, errors);
      if (layer.type === "text") {
        const st = layer.style || {};
        if (st.font_family) {
          safeFont(String(st.font_family), st.font_weight ?? 400, `${lpath}.style`, errors, warnings);
        }
      }
      const [, lErr, lWarn] = effectsMod.normalize(layer.effects, "layer", layer.type, {
        path: `${lpath}.effects`,
        audioReady,
      });
      errors.push(...lErr);
      warnings.push(...lWarn);
    });
  });

  if (totalDur < schema.TOTAL_DURATION_MIN || totalDur > schema.TOTAL_DURATION_MAX) {
    errors.push(`Duree totale ${totalDur.toFixed(1)}s hors limites (${schema.TOTAL_DURATION_MIN}..${schema.TOTAL_DURATION_MAX}s).`);
  }

  return [errors, warnings];
}
