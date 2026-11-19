import * as foldersMod from "./folders.ts";
import * as schema from "./schema.ts";

const STOPWORDS = new Set([
  "the", "and", "for", "with", "that", "this", "from", "your", "you", "are", "was",
  "les", "des", "une", "pour", "avec", "dans", "par", "sur", "qui", "que", "est", "pas",
  "plus", "tout", "mais", "comme", "son", "ses", "nos", "vos", "elle", "ils", "nous",
]);

export function extractKeywords(text: string): string[] {
  const words = String(text || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s_-]/gu, " ")
    .split(/\s+/)
    .filter((w) => w.length >= 3 && !STOPWORDS.has(w));
  return [...new Set(words)].slice(0, 12);
}

export function pickMediaForScenes(
  project: schema.AnyRecord,
  opts: { kind?: "video" | "image" | "any" } = {},
): { assigned: number; skipped: number; details: Array<{ scene_id: string; media: string | null }> } {
  const wantKind = opts.kind || "video";
  const pool =
    wantKind === "any"
      ? [...foldersMod.assetsByKind("video"), ...foldersMod.assetsByKind("image")]
      : foldersMod.assetsByKind(wantKind);

  const scenes = (project.content?.scenes || []) as schema.AnyRecord[];
  const details: Array<{ scene_id: string; media: string | null }> = [];
  let assigned = 0;
  let skipped = 0;

  if (pool.length === 0) {
    return { assigned: 0, skipped: scenes.length, details: scenes.map((s) => ({ scene_id: s.id, media: null })) };
  }

  let cursor = 0;
  for (const sc of scenes) {
    const existing = String(sc.background?.media || "").trim();
    if (existing) {
      skipped += 1;
      details.push({ scene_id: sc.id, media: existing });
      continue;
    }
    const textBlob = (sc.layers || [])
      .filter((l: schema.AnyRecord) => l.type === "text")
      .map((l: schema.AnyRecord) => String(l.text || ""))
      .join(" ");
    const kws = extractKeywords(textBlob);
    let best = pool[cursor % pool.length];
    let bestScore = -1;
    for (const candidate of pool) {
      const name = String(candidate.name || "").toLowerCase();
      let score = 0;
      for (const kw of kws) {
        if (name.includes(kw)) score += 1;
      }
      if (score > bestScore) {
        bestScore = score;
        best = candidate;
      }
    }
    cursor += 1;
    if (!sc.background) sc.background = { media: "", fit: "cover", animation: "static" };
    sc.background.media = String(best.ref);
    assigned += 1;
    details.push({ scene_id: sc.id, media: String(best.ref) });
  }

  return { assigned, skipped, details };
}
