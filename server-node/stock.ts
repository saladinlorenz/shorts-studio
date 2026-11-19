import fs from "node:fs";
import path from "node:path";
import * as mediaMod from "./media.ts";
import { EXPORTS_DIR } from "./security.ts";
import * as sourcesMod from "./sources.ts";

export interface StockItem {
  id: string;
  source: string;
  kind: string;
  title: string;
  license: string;
  url: string;
  author?: string;
}

export async function searchStock(query: string, opts: { source?: string; kind?: string; limit?: number } = {}): Promise<StockItem[]> {
  const source = (opts.source || "").toLowerCase();
  const limit = Math.max(1, Math.min(10, Number(opts.limit || 5)));
  const items: StockItem[] = [];

  if (!source || source === "pexels") {
    const key = sourcesMod.keyOf("pexels");
    if (key) {
      try {
        const isVideo = (opts.kind || "video") === "video";
        const endpoint = isVideo
          ? `https://api.pexels.com/videos/search?query=${encodeURIComponent(query)}&per_page=${limit}`
          : `https://api.pexels.com/v1/search?query=${encodeURIComponent(query)}&per_page=${limit}`;
        const res = await fetch(endpoint, { headers: { Authorization: key }, signal: AbortSignal.timeout(10_000) });
        if (res.ok) {
          const data = (await res.json()) as Record<string, any>;
          if (isVideo) {
            for (const v of (data.videos || []) as any[]) {
              const file = (v.video_files || []).find((f: any) => f.file_type === "video/mp4") || (v.video_files || [])[0];
              if (file?.link) {
                items.push({ id: String(v.id), source: "pexels", kind: "video", title: v.url || `pexels-${v.id}`, license: "Pexels License", url: file.link, author: v.user?.name });
              }
            }
          } else {
            for (const p of (data.photos || []) as any[]) {
              if (p.src?.large2x || p.src?.original) {
                items.push({ id: String(p.id), source: "pexels", kind: "photo", title: p.alt || `pexels-${p.id}`, license: "Pexels License", url: p.src.large2x || p.src.original, author: p.photographer });
              }
            }
          }
        }
      } catch {
        // ignore search error
      }
    }
  }

  return items.slice(0, limit);
}

export async function importStockUrl(url: string, opts: { source: string; title?: string; license?: string }): Promise<string> {
  const res = await fetch(url, { signal: AbortSignal.timeout(30_000) });
  if (!res.ok) throw new Error(`Telechargement stock echoue (${res.status}).`);
  const buf = Buffer.from(await res.arrayBuffer());
  const ext = url.includes(".mp4") ? ".mp4" : ".jpg";
  fs.mkdirSync(EXPORTS_DIR, { recursive: true });
  const tmp = path.join(EXPORTS_DIR, `_stock_${Date.now()}${ext}`);
  try {
    fs.writeFileSync(tmp, buf);
    return mediaMod.importFileToMedia(tmp, opts.source, opts.license || "Stock License");
  } finally {
    if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
  }
}
