import React from "react";
import { AlertTriangle, Ban, CheckCircle2, Loader2, XCircle } from "lucide-react";
import type { JobSnapshot } from "../api/client";
import { Button } from "./ui/button";
import { Progress } from "./ui/progress";

/** Bloc d'etat d'un job : progression reelle, annulation, succes, erreur, annule. */
export function JobStatus({
  job,
  pollError,
  onCancel,
  runningLabel = "Traitement en cours…",
  doneMessage,
}: {
  job: JobSnapshot | null;
  pollError?: string;
  onCancel?: () => void;
  runningLabel?: string;
  doneMessage?: React.ReactNode;
}) {
  if (pollError) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
        Suivi de la tâche interrompu : {pollError}
      </div>
    );
  }
  if (!job) return null;

  if (job.status === "running") {
    return (
      <div className="rounded-md border border-border p-3">
        <div className="mb-2 flex items-center justify-between gap-3 text-xs">
          <span className="flex min-w-0 items-center gap-1.5">
            <Loader2 size={13} className="shrink-0 animate-spin" />
            <span className="truncate">{job.message || runningLabel}</span>
          </span>
          <span className="shrink-0 font-mono">{Math.round(job.progress * 100)} %</span>
        </div>
        <Progress value={job.progress} />
        {job.cancelable && onCancel && (
          <div className="mt-2 flex items-center gap-2">
            <Button size="sm" variant="destructive" onClick={onCancel}>
              Annuler
            </Button>
            <span className="text-[11px] text-muted-foreground">
              L'annulation s'applique à la fin de l'opération en cours.
            </span>
          </div>
        )}
      </div>
    );
  }

  if (job.status === "error") {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2.5 text-xs text-destructive">
        <div className="mb-1 flex items-center gap-1.5 font-medium">
          <XCircle size={14} /> Échec de la tâche
        </div>
        <p className="whitespace-pre-wrap break-words">{job.error || "Erreur inconnue."}</p>
      </div>
    );
  }

  if (job.status === "cancelled") {
    return (
      <div className="flex items-center gap-1.5 rounded-md border border-warning/50 bg-warning/10 p-2.5 text-xs text-warning">
        <Ban size={14} /> Tâche annulée : les fichiers partiels produits ont été rangés.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-success/50 bg-success/10 p-2.5 text-xs">
      <div className="flex items-center gap-1.5 font-medium text-success">
        <CheckCircle2 size={14} /> Terminé
      </div>
      {doneMessage && <div className="mt-1 text-foreground/90">{doneMessage}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div className="flex items-start gap-1.5 rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
      <span className="break-words">{children}</span>
    </div>
  );
}
