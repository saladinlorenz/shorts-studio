import fs from "node:fs";
import path from "node:path";
import { ROOT } from "./security.ts";

const SETTINGS_PATH = path.join(ROOT, "server-node", "settings.json");
const LEGACY_SETTINGS_PATH = path.join(ROOT, "server", "settings.json");

export const PROVIDERS = ["local", "gemini", "groq"] as const;
export type LlmProvider = (typeof PROVIDERS)[number];

export const CLOUD_BASE_URLS: Record<string, string> = {
  gemini: "https://generativelanguage.googleapis.com/v1beta/openai",
  groq: "https://api.groq.com/openai/v1",
};

export const PROVIDER_LABELS: Record<LlmProvider, string> = {
  local: "Serveur local (llama.cpp / compatible OpenAI)",
  gemini: "API Gemini (Google)",
  groq: "API Groq",
};

export const CLOUD_CONTEXT_FLOOR = 20000;

export interface ServerSettings {
  groq_api_key: string;
  host: string;
  port: number;
  llm_enabled: boolean;
  llm_provider: string;
  llm_local_base_url: string;
  llm_local_api_key: string;
  llm_local_pin: string;
  llm_local_model: string;
  llm_gemini_api_key: string;
  llm_gemini_model: string;
  llm_groq_api_key: string;
  llm_groq_model: string;
  llm_temperature: number;
  llm_max_tokens: number;
  llm_context_budget: number;
  llm_timeout: number;
  llm_max_repairs: number;
  llm_max_tool_calls: number;
  llm_stream: boolean;
  llm_json_mode: string;
  llm_vision_review: boolean;
  asr_provider: string;
  asr_groq_api_key: string;
  asr_groq_model: string;
  asr_language: string;
}

const DEFAULTS: ServerSettings = {
  groq_api_key: process.env.GROQ_API_KEY || "",
  host: "0.0.0.0",
  port: Number(process.env.DEFAULT_APP_PORT) || 3000,
  llm_enabled: true,
  // Local-first: always default to local llama.cpp server unless user explicitly selects a cloud provider
  llm_provider: "local",
  llm_local_base_url: process.env.LLAMA_BASE_URL || "http://127.0.0.1:8080/v1",
  llm_local_api_key: "",
  llm_local_pin: "",
  llm_local_model: process.env.LLAMA_MODEL || "local",
  llm_gemini_api_key: process.env.GEMINI_API_KEY || "",
  llm_gemini_model: process.env.GEMINI_API_KEY ? "gemini-2.5-flash" : "",
  llm_groq_api_key: process.env.GROQ_API_KEY || "",
  llm_groq_model: process.env.GROQ_API_KEY ? "llama-3.3-70b-versatile" : "",
  llm_temperature: 0.4,
  llm_max_tokens: 900,
  llm_context_budget: 3000,
  llm_timeout: 120,
  llm_max_repairs: 2,
  llm_max_tool_calls: 3,
  llm_stream: true,
  llm_json_mode: "auto",
  // P4: vision review is optional and strictly OFF by default
  llm_vision_review: false,
  asr_provider: "auto",
  asr_groq_api_key: process.env.GROQ_API_KEY || "",
  asr_groq_model: "whisper-large-v3-turbo",
  asr_language: "",
};

const ALLOWED_KEYS = new Set(Object.keys(DEFAULTS));

const NUMBER_BOUNDS: Record<string, [number, number, number, boolean]> = {
  llm_temperature: [0.0, 0.4, 2.0, false],
  llm_max_tokens: [64, 900, 32000, true],
  llm_context_budget: [1000, 3000, 200000, true],
  llm_timeout: [5, 120, 1800, true],
  llm_max_repairs: [0, 2, 5, true],
  llm_max_tool_calls: [0, 3, 10, true],
};

export function loadSettings(): ServerSettings {
  const data: Record<string, unknown> = { ...DEFAULTS };
  const candidate = fs.existsSync(SETTINGS_PATH)
    ? SETTINGS_PATH
    : fs.existsSync(LEGACY_SETTINGS_PATH)
      ? LEGACY_SETTINGS_PATH
      : null;
  if (candidate) {
    try {
      const parsed = JSON.parse(fs.readFileSync(candidate, "utf8")) as Record<string, unknown>;
      if (parsed && typeof parsed === "object") {
        for (const [k, v] of Object.entries(parsed)) {
          if (ALLOWED_KEYS.has(k) && v !== undefined) {
            data[k] = v;
          }
        }
      }
    } catch {
      // corrupt settings file -> fall back to defaults
    }
  }
  // Env vars provide non-persisted defaults if stored keys are empty
  if (!data.groq_api_key && process.env.GROQ_API_KEY) data.groq_api_key = process.env.GROQ_API_KEY;
  if (!data.llm_gemini_api_key && process.env.GEMINI_API_KEY) {
    data.llm_gemini_api_key = process.env.GEMINI_API_KEY;
    if (!data.llm_gemini_model) data.llm_gemini_model = "gemini-2.5-flash";
  }
  if (!data.llm_groq_api_key && process.env.GROQ_API_KEY) {
    data.llm_groq_api_key = process.env.GROQ_API_KEY;
    if (!data.llm_groq_model) data.llm_groq_model = "llama-3.3-70b-versatile";
  }
  if (!data.asr_groq_api_key && process.env.GROQ_API_KEY) {
    data.asr_groq_api_key = process.env.GROQ_API_KEY;
  }
  return data as unknown as ServerSettings;
}

export function saveSettings(updates: Record<string, unknown>): ServerSettings {
  const current = loadSettings() as unknown as Record<string, unknown>;
  for (const [k, v] of Object.entries(updates)) {
    if (ALLOWED_KEYS.has(k) && v !== undefined) {
      current[k] = v;
    }
  }
  fs.mkdirSync(path.dirname(SETTINGS_PATH), { recursive: true });
  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(current, null, 2), "utf8");
  return current as unknown as ServerSettings;
}

export function providerOf(data?: ServerSettings): LlmProvider {
  const s = data || loadSettings();
  const p = String(s.llm_provider || "local").trim().toLowerCase();
  return (PROVIDERS as readonly string[]).includes(p) ? (p as LlmProvider) : "local";
}

export interface LlmConfig {
  enabled: boolean;
  provider: LlmProvider;
  base_url: string;
  api_key: string;
  pin: string;
  model: string;
  stream: boolean;
  json_mode: string;
  vision_review: boolean;
  temperature: number;
  max_tokens: number;
  context_budget: number;
  timeout: number;
  max_repairs: number;
  max_tool_calls: number;
}

export function llmConfig(): LlmConfig {
  const data = loadSettings();
  const provider = providerOf(data);
  const base_url =
    provider in CLOUD_BASE_URLS
      ? CLOUD_BASE_URLS[provider]
      : String(data.llm_local_base_url || "").trim().replace(/\/+$/, "");

  const rawMap = data as unknown as Record<string, unknown>;
  const cfg: Record<string, unknown> = {
    enabled: Boolean(data.llm_enabled),
    provider,
    base_url,
    api_key: String(rawMap[`llm_${provider}_api_key`] || "").trim(),
    pin: provider === "local" ? String(data.llm_local_pin || "").trim() : "",
    model: String(rawMap[`llm_${provider}_model`] || "").trim(),
    stream: Boolean(data.llm_stream ?? true),
    json_mode: String(data.llm_json_mode || "auto").toLowerCase(),
    vision_review: Boolean(data.llm_vision_review ?? false),
  };

  for (const [key, [lo, def, hi, isInt]] of Object.entries(NUMBER_BOUNDS)) {
    const n = Number(rawMap[key]);
    const bounded = Math.min(hi, Math.max(lo, Number.isFinite(n) ? n : def));
    const short = key.replace(/^llm_/, "");
    cfg[short] = isInt ? Math.round(bounded) : Math.round(bounded * 1000) / 1000;
  }

  return cfg as unknown as LlmConfig;
}

export function effectiveContextBudget(cfg: LlmConfig, configured: number): number {
  const num = Number(configured) || 3000;
  return cfg.provider in CLOUD_BASE_URLS ? Math.max(num, CLOUD_CONTEXT_FLOOR) : num;
}

export function getApiKey(): string {
  return String(loadSettings().groq_api_key || "");
}
