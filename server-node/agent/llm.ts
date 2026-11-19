import { GoogleGenAI } from "@google/genai";
import { consumeBudget } from "../budgets.ts";
import * as settingsMod from "../settings.ts";

export class LLMError extends Error {
  kind: string;
  constructor(message: string, kind = "llm_error") {
    super(message);
    this.name = "LLMError";
    this.kind = kind;
  }
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export function isReady(cfg: settingsMod.LlmConfig): [boolean, string] {
  if (!cfg.enabled) {
    return [false, "Assistant IA desactive dans Reglages."];
  }
  if (!cfg.base_url && cfg.provider !== "gemini") {
    return [false, "URL du serveur IA manquante dans Reglages."];
  }
  if ((cfg.provider === "gemini" || cfg.provider === "groq") && !cfg.api_key) {
    return [false, `Cle API ${cfg.provider} manquante dans Reglages ou variables d'environnement.`];
  }
  if (!cfg.model && cfg.provider !== "local") {
    return [false, `Modele ${cfg.provider} non selectionne dans Reglages.`];
  }
  return [true, ""];
}

function normalizeBaseUrl(raw: string): string {
  const trimmed = String(raw || "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (/\/v1$/i.test(trimmed) || /\/api\/agent\/v1$/i.test(trimmed) || /\/openai(\/v1)?$/i.test(trimmed)) {
    return trimmed;
  }
  return `${trimmed}/v1`;
}

function stripJsonFences(text: string): string {
  const s = text.trim();
  const fenced = s.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced) return fenced[1].trim();
  return s;
}

export async function listModels(cfg: settingsMod.LlmConfig): Promise<string[]> {
  if (cfg.provider === "gemini") {
    return ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"];
  }
  const baseUrl = normalizeBaseUrl(cfg.base_url);
  if (!baseUrl) throw new LLMError("URL de base manquante.", "config");
  const headers: Record<string, string> = {};
  if (cfg.api_key) headers.Authorization = `Bearer ${cfg.api_key}`;
  if (cfg.pin) headers["X-PIN"] = cfg.pin;
  const res = await fetch(`${baseUrl}/models`, {
    headers,
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new LLMError(`HTTP ${res.status} sur /models`, "http");
  const data = (await res.json()) as { data?: Array<{ id: string }>; models?: Array<{ name?: string; model?: string }> };
  const openaiIds = (data.data || []).map((m) => m.id).filter(Boolean);
  if (openaiIds.length > 0) return openaiIds;
  return (data.models || []).map((m) => String(m.model || m.name || "")).filter(Boolean);
}

export async function checkConnection(cfg: settingsMod.LlmConfig) {
  const [ready, reason] = isReady(cfg);
  if (!ready) {
    return { ok: false, error: reason, error_kind: "config", capabilities: {}, models: [] };
  }
  const started = Date.now();
  try {
    const models = await listModels(cfg);
    return {
      ok: true,
      provider: cfg.provider,
      base_url: normalizeBaseUrl(cfg.base_url),
      model: cfg.model || models[0] || "local",
      is_cloud: cfg.provider !== "local",
      latency_ms: Date.now() - started,
      error: undefined,
      error_kind: undefined,
      capabilities: {
        json_mode: cfg.json_mode,
        vision: cfg.vision_review ? "active" : "off",
      },
      models,
    };
  } catch (err) {
    return {
      ok: false,
      provider: cfg.provider,
      base_url: normalizeBaseUrl(cfg.base_url),
      latency_ms: Date.now() - started,
      error: err instanceof Error ? err.message : String(err),
      error_kind: err instanceof LLMError ? err.kind : "network",
      capabilities: {},
      models: [],
    };
  }
}

export async function chatCompletion(
  cfg: settingsMod.LlmConfig,
  messages: ChatMessage[],
  opts: { jsonMode?: boolean; maxTokens?: number; temperature?: number; signal?: AbortSignal } = {},
): Promise<{ content: string; model: string }> {
  const [ready, reason] = isReady(cfg);
  if (!ready) throw new LLMError(reason, "config");

  consumeBudget("llm_calls", { provider: cfg.provider, model: cfg.model });

  const timeoutMs = (cfg.timeout || 120) * 1000;
  const signal = opts.signal
    ? AbortSignal.any([opts.signal, AbortSignal.timeout(timeoutMs)])
    : AbortSignal.timeout(timeoutMs);

  // Use @google/genai when provider is gemini
  if (cfg.provider === "gemini") {
    const ai = new GoogleGenAI({ apiKey: cfg.api_key });
    const sysMsg = messages.find((m) => m.role === "system")?.content || "";
    const conv = messages
      .filter((m) => m.role !== "system")
      .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
      .join("\n\n");
    const response = await ai.models.generateContent({
      model: cfg.model || "gemini-2.5-flash",
      contents: conv,
      config: {
        systemInstruction: sysMsg || undefined,
        temperature: opts.temperature ?? cfg.temperature,
        maxOutputTokens: opts.maxTokens ?? cfg.max_tokens,
        responseMimeType: opts.jsonMode ? "application/json" : undefined,
        abortSignal: signal,
      },
    });
    const text = response.text || "";
    if (!text) throw new LLMError("Reponse vide du modele Gemini.", "empty");
    return { content: opts.jsonMode ? stripJsonFences(text) : text, model: cfg.model };
  }

  // Local llama.cpp (OpenAI-compatible) or optional Groq
  const baseUrl = normalizeBaseUrl(cfg.base_url);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (cfg.api_key) headers.Authorization = `Bearer ${cfg.api_key}`;
  if (cfg.pin) headers["X-PIN"] = cfg.pin;

  const baseBody: Record<string, unknown> = {
    model: cfg.model || "local",
    messages,
    temperature: opts.temperature ?? cfg.temperature,
    max_tokens: opts.maxTokens ?? cfg.max_tokens,
  };
  const sendBody = { ...baseBody };
  if (opts.jsonMode && cfg.json_mode !== "off") {
    sendBody.response_format = { type: "json_object" };
  }

  let res = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify(sendBody),
    signal,
  });

  // Fallback cleanly for llama.cpp builds that reject response_format in auto mode
  if (!res.ok && sendBody.response_format && cfg.provider === "local" && cfg.json_mode === "auto" && (res.status === 400 || res.status === 422)) {
    res = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers,
      body: JSON.stringify(baseBody),
      signal,
    });
  }

  if (!res.ok) {
    const errText = await res.text();
    throw new LLMError(`HTTP ${res.status} du fournisseur IA: ${errText.slice(0, 240)}`, "http");
  }
  const data = (await res.json()) as Record<string, any>;
  const rawContent = String(data.choices?.[0]?.message?.content || "");
  if (!rawContent) throw new LLMError("Reponse vide du modele.", "empty");
  return {
    content: opts.jsonMode ? stripJsonFences(rawContent) : rawContent,
    model: String(data.model || cfg.model || "local"),
  };
}
