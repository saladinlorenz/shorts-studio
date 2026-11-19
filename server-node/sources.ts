import fs from "node:fs";
import path from "node:path";
import { HttpError, ROOT } from "./security.ts";

const SOURCES_PATH = path.join(ROOT, "server-node", "sources.json");

export interface SourceSpec {
  id: string;
  label: string;
  tagline: string;
  kinds: string[];
  key_required: boolean;
  key_label: string;
  signup_url: string;
  docs_url: string;
  test: {
    url: string;
    params: Record<string, string>;
    key_mode: "header" | "query" | "none";
    key_name: string;
    key_prefix: string;
    default_key?: string;
  };
}

export const CATALOG: SourceSpec[] = [
  {
    id: "pexels",
    label: "Pexels",
    tagline: "Videos et photos libres de droits, recherche par mots-cles.",
    kinds: ["video", "photo"],
    key_required: true,
    key_label: "Cle API",
    signup_url: "https://www.pexels.com/api/",
    docs_url: "https://www.pexels.com/api/documentation/",
    test: { url: "https://api.pexels.com/v1/curated", params: { per_page: "1" }, key_mode: "header", key_name: "Authorization", key_prefix: "" },
  },
  {
    id: "pixabay",
    label: "Pixabay",
    tagline: "Images, videos et musiques libres.",
    kinds: ["video", "photo", "music"],
    key_required: true,
    key_label: "Cle API",
    signup_url: "https://pixabay.com/api/docs/",
    docs_url: "https://pixabay.com/api/docs/",
    test: { url: "https://pixabay.com/api/", params: { image_type: "photo", per_page: "3" }, key_mode: "query", key_name: "key", key_prefix: "" },
  },
  {
    id: "unsplash",
    label: "Unsplash",
    tagline: "Photographies haute resolution.",
    kinds: ["photo"],
    key_required: true,
    key_label: "Access Key",
    signup_url: "https://unsplash.com/developers",
    docs_url: "https://unsplash.com/documentation",
    test: { url: "https://api.unsplash.com/photos", params: { per_page: "1" }, key_mode: "header", key_name: "Authorization", key_prefix: "Client-ID " },
  },
  {
    id: "nasa",
    label: "NASA",
    tagline: "Domaine public spatial.",
    kinds: ["space", "photo"],
    key_required: false,
    key_label: "Cle API (optionnelle, sinon DEMO_KEY)",
    signup_url: "https://api.nasa.gov/",
    docs_url: "https://api.nasa.gov/",
    test: { url: "https://api.nasa.gov/planetary/apod", params: {}, key_mode: "query", key_name: "api_key", key_prefix: "", default_key: "DEMO_KEY" },
  },
  {
    id: "freesound",
    label: "Freesound",
    tagline: "Bruitages Creative Commons.",
    kinds: ["audio"],
    key_required: true,
    key_label: "Cle API (token)",
    signup_url: "https://freesound.org/apiv2/apply",
    docs_url: "https://freesound.org/docs/api/",
    test: { url: "https://freesound.org/apiv2/search/text/", params: { query: "wind", page_size: "1" }, key_mode: "query", key_name: "token", key_prefix: "" },
  },
  {
    id: "archive",
    label: "Internet Archive",
    tagline: "Domaine public video et audio sans cle.",
    kinds: ["video", "audio", "archive"],
    key_required: false,
    key_label: "Aucune cle requise",
    signup_url: "",
    docs_url: "https://archive.org/developers/",
    test: { url: "https://archive.org/advancedsearch.php", params: { q: "mediatype:movies", rows: "1", output: "json" }, key_mode: "none", key_name: "", key_prefix: "" },
  },
];

const BY_ID = new Map(CATALOG.map((s) => [s.id, s]));

function loadStored(): Record<string, { key: string; enabled: boolean }> {
  const out: Record<string, { key: string; enabled: boolean }> = {};
  if (fs.existsSync(SOURCES_PATH)) {
    try {
      Object.assign(out, JSON.parse(fs.readFileSync(SOURCES_PATH, "utf8")));
    } catch {
      // ignore
    }
  }
  // Env defaults if not persisted
  const envMap: Record<string, string | undefined> = {
    pexels: process.env.PEXELS_API_KEY,
    pixabay: process.env.PIXABAY_API_KEY,
    freesound: process.env.FREESOUND_API_KEY,
  };
  for (const [id, val] of Object.entries(envMap)) {
    if (val && !out[id]?.key) {
      out[id] = { key: val, enabled: true };
    }
  }
  return out;
}

export function keyOf(sourceId: string): string {
  return loadStored()[sourceId]?.key || "";
}

function publicState(spec: SourceSpec, entry?: { key?: string; enabled?: boolean }) {
  const key = String(entry?.key || "");
  const configured = Boolean(key);
  const enabled = entry?.enabled ?? true;
  return {
    id: spec.id,
    label: spec.label,
    tagline: spec.tagline,
    kinds: spec.kinds,
    key_required: spec.key_required,
    key_label: spec.key_label,
    signup_url: spec.signup_url,
    docs_url: spec.docs_url,
    key_configured: configured,
    key_hint: configured ? `••••${key.slice(-4)}` : "",
    enabled,
    ready: enabled && (configured || !spec.key_required),
  };
}

export function listSources() {
  const data = loadStored();
  const providers = CATALOG.map((spec) => publicState(spec, data[spec.id]));
  return {
    providers,
    configured: providers.filter((p) => p.key_configured).length,
    ready: providers.filter((p) => p.ready).length,
    note: "Les cles restent sur le serveur.",
  };
}

export function save(sourceId: string, opts: { key?: string | null; enabled?: boolean | null; clear_key?: boolean }) {
  const spec = BY_ID.get(sourceId);
  if (!spec) throw new HttpError(404, `Source inconnue : ${sourceId}`);
  const data = loadStored();
  const entry = data[sourceId] || { key: "", enabled: true };
  if (opts.key && opts.key.trim()) {
    entry.key = opts.key.trim();
  }
  if (opts.clear_key) entry.key = "";
  if (typeof opts.enabled === "boolean") entry.enabled = opts.enabled;
  data[sourceId] = entry;
  fs.mkdirSync(path.dirname(SOURCES_PATH), { recursive: true });
  fs.writeFileSync(SOURCES_PATH, JSON.stringify(data, null, 2), "utf8");
  return publicState(spec, entry);
}

export async function testConnection(sourceId: string) {
  const spec = BY_ID.get(sourceId);
  if (!spec) throw new HttpError(404, `Source inconnue : ${sourceId}`);
  const key = keyOf(sourceId) || spec.test.default_key || "";
  if (spec.test.key_mode !== "none" && !key) {
    throw new HttpError(400, `Aucune cle enregistree pour ${spec.label}.`);
  }
  const url = new URL(spec.test.url);
  for (const [k, v] of Object.entries(spec.test.params)) {
    url.searchParams.set(k, v);
  }
  const headers: Record<string, string> = {};
  if (spec.test.key_mode === "query") {
    url.searchParams.set(spec.test.key_name, key);
  } else if (spec.test.key_mode === "header") {
    headers[spec.test.key_name] = spec.test.key_prefix + key;
  }
  const started = Date.now();
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(10_000) });
    const latency = Date.now() - started;
    if (!res.ok) {
      return { ok: false, message: `${spec.label} HTTP ${res.status}`, latency_ms: latency };
    }
    return { ok: true, message: `${spec.label} repond : acces valide.`, latency_ms: latency };
  } catch (err) {
    return {
      ok: false,
      message: `${spec.label} injoignable (${err instanceof Error ? err.message : String(err)}).`,
      latency_ms: Date.now() - started,
    };
  }
}
