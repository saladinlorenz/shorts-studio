import fs from "node:fs";
import path from "node:path";
import { KNOWLEDGE_DIR, SKILLS_DIR } from "./security.ts";

export class RetrievalUnavailable extends Error {}

interface DocChunk {
  id: string;
  path: string;
  source: string;
  version: string;
  title: string;
  text: string;
}

const INDEX_FILE = path.join(KNOWLEDGE_DIR, "index.json");
let memoryChunks: DocChunk[] | null = null;

function walkMd(dir: string, out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walkMd(full, out);
    else if (entry.isFile() && entry.name.endsWith(".md")) out.push(full);
  }
  return out;
}

export function build(force = false): { built: boolean; chunks: number; engine: string } {
  if (!force && fs.existsSync(INDEX_FILE)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(INDEX_FILE, "utf8")) as DocChunk[];
      if (Array.isArray(parsed) && parsed.length > 0) {
        memoryChunks = parsed;
        return { built: true, chunks: parsed.length, engine: "bm25-json" };
      }
    } catch {
      // rebuild
    }
  }
  const files = walkMd(SKILLS_DIR);
  const chunks: DocChunk[] = [];
  for (const file of files.slice(0, 120)) {
    const rel = path.relative(SKILLS_DIR, file);
    const text = fs.readFileSync(file, "utf8");
    const firstHeading = text.match(/^#\s+(.+)$/m)?.[1]?.trim() || path.basename(file, ".md");
    chunks.push({
      id: rel,
      path: rel,
      source: "skills/remotion",
      version: "4.0",
      title: firstHeading.slice(0, 100),
      text: text.slice(0, 4000),
    });
  }
  fs.mkdirSync(KNOWLEDGE_DIR, { recursive: true });
  fs.writeFileSync(INDEX_FILE, JSON.stringify(chunks), "utf8");
  memoryChunks = chunks;
  return { built: true, chunks: chunks.length, engine: "bm25-json" };
}

export function status() {
  if (!memoryChunks && fs.existsSync(INDEX_FILE)) {
    try {
      memoryChunks = JSON.parse(fs.readFileSync(INDEX_FILE, "utf8")) as DocChunk[];
    } catch {
      memoryChunks = null;
    }
  }
  return {
    indexed: Boolean(memoryChunks && memoryChunks.length > 0),
    chunks: memoryChunks?.length ?? 0,
    engine: "bm25-json",
  };
}

export function search(query: string, limit = 5, maxChars = 6000) {
  if (!memoryChunks) build(false);
  const docs = memoryChunks || [];
  const terms = String(query || "")
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length >= 2);
  if (terms.length === 0) return [];

  const scored = docs
    .map((doc) => {
      const hay = `${doc.title}\n${doc.path}\n${doc.text}`.toLowerCase();
      let score = 0;
      for (const term of terms) {
        if (doc.title.toLowerCase().includes(term)) score += 3;
        if (hay.includes(term)) score += 1;
      }
      return { doc, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  let usedChars = 0;
  return scored.map(({ doc, score }) => {
    const remaining = Math.max(200, maxChars - usedChars);
    const snippet = doc.text.slice(0, remaining);
    usedChars += snippet.length;
    return {
      id: doc.id,
      path: doc.path,
      source: doc.source,
      version: doc.version,
      title: doc.title,
      score,
      truncated: doc.text.length > snippet.length,
      text: snippet,
    };
  });
}
