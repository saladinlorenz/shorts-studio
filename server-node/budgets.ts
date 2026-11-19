import { cancelAllJobs } from "./jobs.ts";
import { logAgentEvent } from "./logger.ts";
import { HttpError } from "./security.ts";

export interface BudgetLimits {
  auto_confirms_per_hour: number;
  llm_calls_per_hour: number;
  exports_per_hour: number;
  autopilot_runs_per_hour: number;
}

export const DEFAULT_BUDGET_LIMITS: BudgetLimits = {
  auto_confirms_per_hour: 15,
  llm_calls_per_hour: 60,
  exports_per_hour: 10,
  autopilot_runs_per_hour: 5,
};

// Actions explicitly allowed for bounded auto-confirmation.
// Never includes image_generate, settings/secret changes, deletions, or file overwrites.
export const AUTO_CONFIRM_ALLOWLIST = new Set([
  "project_patch",
  "project_new",
  "project_review",
  "project_check_render",
  "project_export",
  "montage_render",
  "brand_apply",
  "brand_capture",
  "tts_generate",
  "copywriting_generate",
  "autopilot_start",
]);

export const AUTO_CONFIRM_BLOCKLIST = new Set([
  "image_generate",
  "settings_update",
  "delete_project",
  "delete_media",
]);

const WINDOW_MS = 3600 * 1000;

interface BudgetCounters {
  auto_confirms: number[];
  llm_calls: number[];
  exports: number[];
  autopilot_runs: number[];
}

const counters: BudgetCounters = {
  auto_confirms: [],
  llm_calls: [],
  exports: [],
  autopilot_runs: [],
};

let stopped = false;
let stopReason = "";
let stoppedAt = "";
const stopListeners = new Set<(reason: string) => void>();

function prune(list: number[], now: number): number[] {
  const cutoff = now - WINDOW_MS;
  return list.filter((ts) => ts >= cutoff);
}

function pruneAll(now = Date.now()): void {
  counters.auto_confirms = prune(counters.auto_confirms, now);
  counters.llm_calls = prune(counters.llm_calls, now);
  counters.exports = prune(counters.exports, now);
  counters.autopilot_runs = prune(counters.autopilot_runs, now);
}

export function onGlobalStop(listener: (reason: string) => void): () => void {
  stopListeners.add(listener);
  return () => stopListeners.delete(listener);
}

export function isGlobalStopped(): boolean {
  return stopped;
}

export function assertNotStopped(): void {
  if (stopped) {
    throw new HttpError(409, `Arrêt global actif${stopReason ? ` (${stopReason})` : ""}. Réinitialisez ou relancez une nouvelle demande.`);
  }
}

export function triggerGlobalStop(reason = "Arrêt d'urgence demandé par l'utilisateur"): {
  stopped: boolean;
  reason: string;
  stopped_at: string;
  cancelled_jobs: number;
} {
  stopped = true;
  stopReason = reason;
  stoppedAt = new Date().toISOString();
  const cancelledJobs = cancelAllJobs();
  for (const listener of stopListeners) {
    try {
      listener(reason);
    } catch {
      // keep stopping remaining listeners
    }
  }
  logAgentEvent({
    event: "global_stop",
    actor: "user",
    status: "stopped",
    detail: { reason, cancelled_jobs: cancelledJobs },
  });
  return {
    stopped: true,
    reason,
    stopped_at: stoppedAt,
    cancelled_jobs: cancelledJobs,
  };
}

export function clearGlobalStop(): void {
  if (stopped) {
    stopped = false;
    stopReason = "";
    stoppedAt = "";
    logAgentEvent({ event: "global_stop_cleared", actor: "user", status: "ok" });
  }
}

export function canAutoConfirmAction(actionName: string, payload?: Record<string, unknown>): {
  allowed: boolean;
  reason: string;
} {
  if (stopped) {
    return { allowed: false, reason: "Arrêt global actif." };
  }
  if (AUTO_CONFIRM_BLOCKLIST.has(actionName)) {
    return { allowed: false, reason: `Action '${actionName}' exclue de l'auto-confirmation.` };
  }
  if (!AUTO_CONFIRM_ALLOWLIST.has(actionName)) {
    return { allowed: false, reason: `Action '${actionName}' non autorisée pour l'auto-confirmation.` };
  }
  if (payload && payload.overwrite === true) {
    return { allowed: false, reason: "Écrasement de fichier existant : confirmation manuelle requise." };
  }
  pruneAll();
  if (counters.auto_confirms.length >= DEFAULT_BUDGET_LIMITS.auto_confirms_per_hour) {
    return {
      allowed: false,
      reason: `Budget d'auto-confirmation atteint (${DEFAULT_BUDGET_LIMITS.auto_confirms_per_hour}/h).`,
    };
  }
  return { allowed: true, reason: "" };
}

export function consumeBudget(
  kind: keyof BudgetCounters,
  detail: Record<string, unknown> = {},
): void {
  if (stopped) {
    throw new HttpError(409, "Arrêt global actif : exécution bloquée.");
  }
  const now = Date.now();
  pruneAll(now);
  const limitMap: Record<keyof BudgetCounters, number> = {
    auto_confirms: DEFAULT_BUDGET_LIMITS.auto_confirms_per_hour,
    llm_calls: DEFAULT_BUDGET_LIMITS.llm_calls_per_hour,
    exports: DEFAULT_BUDGET_LIMITS.exports_per_hour,
    autopilot_runs: DEFAULT_BUDGET_LIMITS.autopilot_runs_per_hour,
  };
  if (counters[kind].length >= limitMap[kind]) {
    logAgentEvent({
      event: "budget_exceeded",
      actor: "system",
      status: "blocked",
      detail: { kind, limit: limitMap[kind], ...detail },
    });
    throw new HttpError(
      429,
      `Budget '${kind}' atteint (${limitMap[kind]}/h). Attendez ou lancez manuellement.`,
    );
  }
  counters[kind].push(now);
  logAgentEvent({
    event: `budget_${kind}`,
    actor: kind === "auto_confirms" ? "auto" : "system",
    status: "ok",
    detail: { used: counters[kind].length, limit: limitMap[kind], ...detail },
  });
}

export function getBudgetState(): {
  stopped: boolean;
  stop_reason: string;
  stopped_at: string;
  window_seconds: number;
  limits: BudgetLimits;
  used: {
    auto_confirms: number;
    llm_calls: number;
    exports: number;
    autopilot_runs: number;
  };
  remaining: {
    auto_confirms: number;
    llm_calls: number;
    exports: number;
    autopilot_runs: number;
  };
  allowlist: string[];
  manual_only: string[];
} {
  pruneAll();
  const used = {
    auto_confirms: counters.auto_confirms.length,
    llm_calls: counters.llm_calls.length,
    exports: counters.exports.length,
    autopilot_runs: counters.autopilot_runs.length,
  };
  return {
    stopped,
    stop_reason: stopReason,
    stopped_at: stoppedAt,
    window_seconds: WINDOW_MS / 1000,
    limits: { ...DEFAULT_BUDGET_LIMITS },
    used,
    remaining: {
      auto_confirms: Math.max(0, DEFAULT_BUDGET_LIMITS.auto_confirms_per_hour - used.auto_confirms),
      llm_calls: Math.max(0, DEFAULT_BUDGET_LIMITS.llm_calls_per_hour - used.llm_calls),
      exports: Math.max(0, DEFAULT_BUDGET_LIMITS.exports_per_hour - used.exports),
      autopilot_runs: Math.max(0, DEFAULT_BUDGET_LIMITS.autopilot_runs_per_hour - used.autopilot_runs),
    },
    allowlist: [...AUTO_CONFIRM_ALLOWLIST],
    manual_only: [...AUTO_CONFIRM_BLOCKLIST],
  };
}
