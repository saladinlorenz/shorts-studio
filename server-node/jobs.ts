import crypto from "node:crypto";
import type { ChildProcess } from "node:child_process";

export class JobCancelled extends Error {
  constructor(message = "Tache annulee.") {
    super(message);
    this.name = "JobCancelled";
  }
}

export interface JobSnapshot {
  id: string;
  kind: string;
  status: "running" | "done" | "error" | "cancelled";
  progress: number;
  message: string;
  result: unknown;
  error: string | null;
  created_at: number;
  finished_at: number | null;
}

export class Job {
  id: string;
  kind: string;
  status: "running" | "done" | "error" | "cancelled" = "running";
  progress = 0;
  message = "En cours…";
  result: unknown = null;
  error: string | null = null;
  createdAt: number = Date.now() / 1000;
  finishedAt: number | null = null;
  cancelController: AbortController = new AbortController();
  resultProcess: ChildProcess | null = null;

  constructor(id: string, kind: string) {
    this.id = id;
    this.kind = kind;
  }

  get cancelled(): boolean {
    return this.cancelController.signal.aborted;
  }

  setProgress(current: number, total: number, message = ""): void {
    if (total > 0) {
      this.progress = Math.max(0, Math.min(1, current / total));
    }
    if (message) {
      this.message = message;
    }
  }

  cancel(): void {
    if (!this.cancelController.signal.aborted) {
      this.cancelController.abort();
    }
    const proc = this.resultProcess;
    if (proc && !proc.killed) {
      try {
        proc.kill("SIGTERM");
        setTimeout(() => {
          try {
            if (!proc.killed) proc.kill("SIGKILL");
          } catch {
            // ignore
          }
        }, 1500);
      } catch {
        // ignore
      }
    }
    if (this.status === "running") {
      this.status = "cancelled";
      this.message = "Annule.";
      this.finishedAt = Date.now() / 1000;
    }
  }

  snapshot(): JobSnapshot {
    return {
      id: this.id,
      kind: this.kind,
      status: this.status,
      progress: Math.round(this.progress * 10000) / 10000,
      message: this.message,
      result: this.result,
      error: this.error,
      created_at: this.createdAt,
      finished_at: this.finishedAt,
    };
  }
}

const MAX_FINISHED_JOBS = 200;
const JOBS = new Map<string, Job>();

function pruneFinished(): void {
  const finished = [...JOBS.values()]
    .filter((j) => j.status !== "running")
    .sort((a, b) => (a.finishedAt ?? 0) - (b.finishedAt ?? 0));
  while (finished.length > MAX_FINISHED_JOBS) {
    const oldest = finished.shift();
    if (oldest) JOBS.delete(oldest.id);
  }
}

export function createJob(kind: string, worker: (job: Job) => Promise<unknown> | unknown): Job {
  const id = crypto.randomBytes(6).toString("hex");
  const job = new Job(id, kind);
  JOBS.set(id, job);
  pruneFinished();

  Promise.resolve()
    .then(() => worker(job))
    .then((result) => {
      if (job.cancelled) {
        job.status = "cancelled";
        job.message = "Annule.";
      } else {
        job.result = result;
        job.progress = 1;
        job.status = "done";
        job.message = "Termine.";
      }
    })
    .catch((err: unknown) => {
      if (err instanceof JobCancelled || job.cancelled) {
        job.status = "cancelled";
        job.message = "Annule.";
      } else {
        job.status = "error";
        job.error = err instanceof Error ? err.message : String(err);
        job.message = "Erreur.";
      }
    })
    .finally(() => {
      if (job.finishedAt === null) {
        job.finishedAt = Date.now() / 1000;
      }
    });

  return job;
}

export function getJob(jobId: string): Job | undefined {
  return JOBS.get(jobId);
}

export function cancelJob(jobId: string): Job | undefined {
  const job = JOBS.get(jobId);
  if (!job) return undefined;
  job.cancel();
  return job;
}

export function cancelAllJobs(): number {
  let count = 0;
  for (const job of JOBS.values()) {
    if (job.status === "running") {
      job.cancel();
      count += 1;
    }
  }
  return count;
}

export function raiseIfCancelled(job: Job): void {
  if (job.cancelled) {
    throw new JobCancelled();
  }
}
