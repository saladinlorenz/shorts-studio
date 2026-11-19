import * as schema from "./schema.ts";

export const POLICY = {
  column_wins: true,
  missing_named_file: "erreur bloquante pour la ligne",
  rotation: "ordre trie des dossiers connectes, deterministe",
  cycling: "le cycle reprend quand les ressources sont moins nombreuses que les lignes",
  never: "aucun raccourcissement de texte, aucun chemin dans un projet",
};

function slug(value: string, fallback = "video"): string {
  const clean = String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/[\s_]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  return clean.slice(0, 60) || fallback;
}

function norm(value: string): string {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function fillableFields(template: schema.AnyRecord): Array<Record<string, unknown>> {
  if (template?.version !== schema.SCHEMA_VERSION_V2) {
    throw new Error("fillable_fields attend un projet version 2.");
  }
  const fields: Array<Record<string, unknown>> = [
    { key: "title", label: "Titre (sert aussi de nom de fichier)", type: "text", scene: "", required: false },
  ];
  for (const sc of (template.content?.scenes || []) as schema.AnyRecord[]) {
    const sid = String(sc.id || "");
    const slabel = String(sc.label || sid);
    for (const layer of (sc.layers || []) as schema.AnyRecord[]) {
      if (layer.type !== "text") continue;
      const role = String(layer.role || layer.id || "text");
      fields.push({
        key: `scene.${sid}.${role}.text`,
        label: `${slabel} · ${role}`,
        type: "text",
        scene: sid,
        required: role === "hook" || role === "quote",
        sample: String(layer.text || "").slice(0, 80),
      });
    }
    fields.push({
      key: `scene.${sid}.duration`,
      label: `${slabel} — duree (s)`,
      type: "number",
      scene: sid,
      required: false,
      min: 0.5,
      max: 60.0,
      sample: sc.duration,
    });
    fields.push({
      key: `scene.${sid}.background`,
      label: `${slabel} — fond`,
      type: "media",
      kind: "video",
      scene: sid,
      required: false,
      sample: String(sc.background?.media || ""),
    });
  }
  const sig = template.content?.signature || {};
  fields.push({ key: "signature.handle", label: "Signature — @pseudo", type: "text", scene: "", required: false, sample: String(sig.handle || "") });
  fields.push({ key: "signature.media", label: "Signature — logo", type: "media", kind: "image", scene: "", required: false, sample: String(sig.media || "") });
  fields.push({ key: "audio.music", label: "Musique de fond", type: "media", kind: "audio", scene: "", required: false, sample: String(template.audio?.music || "") });
  fields.push({ key: "audio.voice", label: "Voix (voix-off)", type: "media", kind: "audio", scene: "", required: false, sample: String(template.audio?.voice || "") });
  return fields;
}

const AUTONAMES: Record<string, string[]> = {
  title: ["title", "titre", "name", "nom", "video"],
  "scene.s1.hook.text": ["hook", "accroche", "teaser"],
  "scene.s2.quote.text": ["quote", "citation", "texte", "text", "content", "contenu"],
  "scene.s2.author.text": ["author", "auteur", "source", "by"],
  "scene.s3.reveal.text": ["reveal", "signature", "cta"],
  "audio.music": ["music", "musique", "audio", "bgm"],
  "audio.voice": ["voice", "voix", "voiceover"],
  "signature.handle": ["handle", "pseudo", "marque", "brand"],
};

export function suggestMapping(columns: string[], fields: Array<Record<string, unknown>>): Record<string, string> {
  const byCol = new Map<string, string>();
  columns.forEach((c) => {
    if (c.trim()) byCol.set(norm(c), c);
  });
  const mapping: Record<string, string> = {};
  for (const field of fields) {
    const key = String(field.key);
    const candidates = [...(AUTONAMES[key] || []).map(norm), norm(String(field.label))];
    for (const c of candidates) {
      const col = byCol.get(c);
      if (col && !Object.values(mapping).includes(col)) {
        mapping[key] = col;
        break;
      }
    }
  }
  return mapping;
}

export function buildPlan(
  template: schema.AnyRecord,
  rows: Array<Record<string, string>>,
  mapping: Record<string, string>,
  assets: Record<string, Array<Record<string, unknown>>> = {},
  options: Record<string, string> = {},
) {
  const videoPool = assets.video || [];
  const audioPool = assets.audio || [];
  const modeBg = String(options.background || "auto").toLowerCase();
  const modeMusic = String(options.music || "auto").toLowerCase();
  const warnings: string[] = [];

  if (modeBg === "auto" && videoPool.length === 0) {
    warnings.push("Aucun dossier de videos de fond connecte : les scenes gardent le fond du theme.");
  }
  if (modeMusic === "auto" && audioPool.length === 0) {
    warnings.push("Aucune musique de fond disponible : les videos seront silencieuses.");
  }

  const fields = fillableFields(template);
  const fieldsByKey = new Map(fields.map((f) => [String(f.key), f]));

  const items = rows.map((row, idx0) => {
    const index = idx0 + 1;
    const project = schema.clone(template);
    const rowErrors: string[] = [];
    const rowWarnings: string[] = [];
    const assetsUsed: Array<Record<string, unknown>> = [];

    const titleCol = mapping.title;
    const titleVal = titleCol ? String(row[titleCol] || "").trim() : "";
    project.name = slug(titleVal, `lot-${String(index).padStart(3, "0")}`);

    for (const [key, colName] of Object.entries(mapping)) {
      if (key === "title" || !(colName in row)) continue;
      const val = String(row[colName] ?? "").trim();
      const spec = fieldsByKey.get(key);
      if (!spec || spec.type === "media") continue;
      if (!val) {
        if (spec.required) rowErrors.push(`ligne ${index} : '${spec.label}' vide.`);
        continue;
      }
      if (key.endsWith(".duration")) {
        const sid = key.split(".")[1];
        const num = Number(val.replace(",", "."));
        if (!Number.isFinite(num) || num < 0.5 || num > 60) {
          rowErrors.push(`ligne ${index} : duree invalide (${val}).`);
        } else {
          for (const sc of project.content.scenes) {
            if (sc.id === sid) sc.duration = num;
          }
        }
      } else if (key.startsWith("scene.")) {
        const [, sid, role, sub] = key.split(".");
        for (const sc of project.content.scenes) {
          if (sc.id !== sid) continue;
          for (const l of sc.layers) {
            if ((l.role || l.id) === role && sub === "text") l.text = val;
          }
        }
      } else if (key === "signature.handle") {
        project.content.signature.handle = val.slice(0, 80);
      }
    }

    let bgSource = "modele (fond du theme)";
    let bgPass: number | null = null;
    if (modeBg === "auto" && videoPool.length > 0) {
      const pick = videoPool[idx0 % videoPool.length];
      bgPass = Math.floor(idx0 / videoPool.length) + 1;
      bgSource = "rotation";
      for (const sc of project.content.scenes) {
        if (!sc.background?.media) {
          if (!sc.background) sc.background = { media: "", fit: "cover", animation: "static" };
          sc.background.media = String(pick.ref);
          assetsUsed.push({ field: `scene.${sc.id}.background`, ...pick, pass: bgPass });
        }
      }
    }

    let musicSource = "aucune";
    let musicPass: number | null = null;
    if (modeMusic === "auto" && audioPool.length > 0 && !mapping["audio.music"]) {
      const pick = audioPool[idx0 % audioPool.length];
      musicPass = Math.floor(idx0 / audioPool.length) + 1;
      musicSource = "rotation";
      project.audio.music = String(pick.ref);
      project.audio.enabled = true;
      assetsUsed.push({ field: "audio.music", ...pick, pass: musicPass });
    }

    project.variation = { seed: Number(template.variation?.seed || 1) + idx0 };
    const baseFn = titleVal ? `${String(index).padStart(3, "0")}-${slug(titleVal)}` : `lot-${String(index).padStart(3, "0")}`;
    project.export.filename = baseFn;

    const preview: Record<string, string> = {};
    Object.entries(row).slice(0, 6).forEach(([k, v]) => { preview[k] = String(v); });

    return {
      index,
      name: project.name,
      filename: `${baseFn}.mp4`,
      project,
      row_preview: preview,
      assets_used: assetsUsed,
      background_source: bgSource,
      background_pass: bgPass,
      music_source: musicSource,
      music_pass: musicPass,
      errors: rowErrors,
      warnings: rowWarnings,
    };
  });

  const invalid = items.filter((i) => i.errors.length > 0).map((i) => i.index);
  return {
    items,
    warnings,
    policy: POLICY,
    summary: {
      rows: rows.length,
      ready: rows.length - invalid.length,
      invalid_rows: invalid,
      video_assets: videoPool.length,
      audio_assets: audioPool.length,
      background_passes: videoPool.length > 0 ? Math.ceil(rows.length / videoPool.length) : 0,
      music_passes: audioPool.length > 0 ? Math.ceil(rows.length / audioPool.length) : 0,
      cycled_background: videoPool.length > 0 && videoPool.length < rows.length,
      cycled_music: audioPool.length > 0 && audioPool.length < rows.length,
      auto_background: modeBg === "auto" && videoPool.length > 0,
      auto_music: modeMusic === "auto" && audioPool.length > 0,
    },
  };
}
