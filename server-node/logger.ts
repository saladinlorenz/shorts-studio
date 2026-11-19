import fs from "node:fs";
import path from "node:path";
import { LOGS_DIR } from "./security.ts";

const LOG_FILE = path.join(LOGS_DIR, "agent-actions.jsonl");
const MAX_LINE_BYTES = 8000;

const SECRET_KEYS = new Set([
  "api_key",
  "apikey",
  "groq_api_key",
  "gemini_api_key",
  "llm_local_api_key",
  "llm_gemini_api_key",
  "llm_groq_api_key",
  "asr_groq_api_key",
  "llm_local_pin",
  "pin",
  "token",
  "authorization",
  "secret",
  "password",
]);

function redactString(input: string): string {
  let out = input;
  out = out.replace(/data:[^\s"<>]+/gi, "[data-redacted]");
  out = out.replace(
    /(authorization|bearer|api[_-]?key|token|password|secret|pin)[\s"':=]+[^\s,;]+/gi,
    "$1=[redacted]",
  );
  for (const [k, v] of Object.entries(process.env)) {
    if (v && v.length >= 6 && /(key|token|secret|password|pin)$/i.test(k)) {
      out = out.split(v).join("[redacted]");
    }
  }
  return out.length > 600 ? out.slice(0, 597) + "..." : out;
}

export function sanitizeForLog(value: unknown, depth = 0): unknown {
  if (depth > 4) return "[truncated]";
  if (value === null || value === undefined) return value;
  if (typeof value === "string") return redactString(value);
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) {
    return value.slice(0, 20).map((item) => sanitizeForLog(item, depth + 1));
  }
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (SECRET_KEYS.has(k.toLowerCase())) {
        out[k] = v ? "[redacted]" : "";
      } else {
        out[k] = sanitizeForLog(v, depth + 1);
      }
    }
    return out;
  }
  return String(value);
}

export interface AgentLogEntry {
  ts: string;
  event: string;
  actor?: "user" | "auto" | "system";
  action?: string;
  proposal_id?: string;
  job_id?: string;
  status?: string;
  detail?: unknown;
}

export function logAgentEvent(entry: Omit<AgentLogEntry, "ts">): void {
  try {
    fs.mkdirSync(LOGS_DIR, { recursive: true });
    const clean: AgentLogEntry = {
      ts: new Date().toISOString(),
      event: String(entry.event || "info"),
      actor: entry.actor || "system",
      ...(entry.action ? { action: String(entry.action) } : {}),
      ...(entry.proposal_id ? { proposal_id: String(entry.proposal_id) } : {}),
      ...(entry.job_id ? { job_id: String(entry.job_id) } : {}),
      ...(entry.status ? { status: String(entry.status) } : {}),
      ...(entry.detail !== undefined ? { detail: sanitizeForLog(entry.detail) } : {}),
    };
    let line = JSON.stringify(clean);
    if (line.length > MAX_LINE_BYTES) {
      line = JSON.stringify({
        ts: clean.ts,
        event: clean.event,
        actor: clean.actor,
        status: clean.status,
        detail: "[log line truncated]",
      });
    }
    fs.appendFileSync(LOG_FILE, line + "\n", "utf8");
  } catch {
    // Logging must never break execution
  }
}

export function readRecentLogs(limit = 50): AgentLogEntry[] {
  const cap = Math.max(1, Math.min(200, Math.floor(limit)));
  if (!fs.existsSync(LOG_FILE)) return [];
  try {
    const raw = fs.readFileSync(LOG_FILE, "utf8");
    const lines = raw.trim().split("\n").filter(Boolean);
    return lines
      .slice(-cap)
      .reverse()
      .map((line) => {
        try {
          return JSON.parse(line) as AgentLogEntry;
        } catch {
          return { ts: "", event: "parse_error", detail: line.slice(0, 120) };
        }
      });
  } catch {
    return [];
  }
}

export function logFilePath(): string {
  return LOG_FILE;
}
