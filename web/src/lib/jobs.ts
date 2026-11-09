/**
 * Suivi des jobs du serveur (polling + annulation) et formats d'affichage.
 * Utilise les types du client existant sans le modifier.
 */
import React from "react";
import type { JobSnapshot } from "../api/client";

export type { JobSnapshot };

export class HttpError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function readableMessage(raw: unknown, status: number): string {
  if (typeof raw === "string") return raw || `Erreur HTTP ${status}`;
  if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    if ("detail" in obj) return readableMessage(obj.detail, status);
    if ("message" in obj) return String(obj.message);
  }
  return JSON.stringify(raw);
}

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(detail as string);
    } catch {
      /* texte brut */
    }
    throw new HttpError(readableMessage(detail, res.status), res.status, detail);
  }
  return res.json() as Promise<T>;
}

/** Interroge GET /api/jobs/<id> jusqu'a la fin du job. */
export function useJobPolling(jobId: string | null, intervalMs = 700) {
  const [job, setJob] = React.useState<JobSnapshot | null>(null);
  const [pollError, setPollError] = React.useState("");

  React.useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let handle = 0;

    const tick = async () => {
      try {
        const snap = await call<JobSnapshot>(`/api/jobs/${jobId}`);
        if (stopped) return;
        setJob(snap);
        setPollError("");
        if (snap.status !== "running") window.clearInterval(handle);
      } catch (e) {
        if (stopped) return;
        setPollError(e instanceof Error ? e.message : String(e));
        window.clearInterval(handle);
      }
    };

    void tick();
    handle = window.setInterval(tick, intervalMs);
    return () => {
      stopped = true;
      window.clearInterval(handle);
    };
  }, [jobId, intervalMs]);

  return { job, pollError };
}

export function cancelJob(jobId: string) {
  return call<JobSnapshot>(`/api/jobs/${jobId}/cancel`, { method: "POST" });
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "?";
  if (value < 1024) return `${value} o`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} Ko`;
  return `${(value / (1024 * 1024)).toFixed(1)} Mo`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "?";
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")} min`;
}
