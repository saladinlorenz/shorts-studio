import React from "react";
import {
  CheckCircle2,
  Clock,
  Loader2,
  MinusCircle,
  Play,
  RotateCcw,
  Square,
  XCircle,
} from "lucide-react";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { api, apiErrorMessage, type AutopilotState, type AutopilotStep } from "../../api/client";
import { formatBytes, formatDuration } from "../../lib/jobs";

interface Props {
  planId: string;
  notify: (message: string, kind?: "ok" | "error" | "info") => void;
}

const STATUS_LABEL: Record<AutopilotState["status"], string> = {
  running: "en cours",
  done: "terminé",
  error: "échec",
  cancelled: "annulé",
  interrupted: "interrompu",
};

const STATUS_VARIANT: Record<AutopilotState["status"], "default" | "success" | "destructive" | "warning" | "secondary"> = {
  running: "default",
  done: "success",
  error: "destructive",
  cancelled: "secondary",
  interrupted: "warning",
};

function StepIcon({ status }: { status: AutopilotStep["status"] }) {
  switch (status) {
    case "done":
      return <CheckCircle2 size={14} className="shrink-0 text-success" />;
    case "running":
      return <Loader2 size={14} className="shrink-0 animate-spin text-primary" />;
    case "failed":
      return <XCircle size={14} className="shrink-0 text-destructive" />;
    case "cancelled":
      return <XCircle size={14} className="shrink-0 text-muted-foreground" />;
    case "skipped":
      return <MinusCircle size={14} className="shrink-0 text-muted-foreground" />;
    default:
      return <Clock size={14} className="shrink-0 text-muted-foreground" />;
  }
}

/**
 * Suivi d'un plan autopilote : une tâche par étape (script → design → voix →
 * export), progression, annulation, reprise et lien vers la vidéo finale.
 * L'état vient du serveur (persisté) : le suivi survit à un redémarrage.
 */
export default function AutopilotTracker({ planId, notify }: Props) {
  const [state, setState] = React.useState<AutopilotState | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    let stopped = false;
    let handle = 0;
    const tick = async () => {
      try {
        const snap = await api.autopilotStatus(planId);
        if (stopped) return;
        setState(snap);
        setError("");
        if (snap.status !== "running") window.clearInterval(handle);
      } catch (e) {
        if (stopped) return;
        setError(apiErrorMessage(e));
        window.clearInterval(handle);
      }
    };
    void tick();
    handle = window.setInterval(tick, 800);
    return () => {
      stopped = true;
      window.clearInterval(handle);
    };
  }, [planId]);

  const cancel = async () => {
    setBusy(true);
    try {
      setState(await api.autopilotCancel(planId));
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const resume = async () => {
    setBusy(true);
    setError("");
    try {
      await api.autopilotStart({ job_id: planId });
      notify("Plan repris à la première étape non terminée.", "info");
      setState(await api.autopilotStatus(planId));
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (!state) {
    return (
      <div className="panel mt-2 flex items-center gap-2 p-2.5 text-xs text-muted-foreground">
        <Loader2 size={13} className="animate-spin" /> Chargement du plan…
        {error && <span className="text-destructive">{error}</span>}
      </div>
    );
  }

  const running = state.status === "running";
  const progress = Math.round((state.progress ?? 0) * 100);

  return (
    <div className="panel mt-2 p-2.5">
      <div className="flex items-center gap-2">
        <Badge variant={STATUS_VARIANT[state.status]} className="text-[10px]">
          Autopilote · {STATUS_LABEL[state.status]}
        </Badge>
        {state.project_name && (
          <span className="truncate text-[10px] text-muted-foreground">{state.project_name}</span>
        )}
      </div>

      <ul className="mt-2 space-y-1">
        {state.steps.map((step) => (
          <li key={step.id} className="rounded border border-border/60 bg-muted/20 px-1.5 py-1">
            <div className="flex items-center gap-1.5 text-[11px]">
              <StepIcon status={step.status} />
              <span className={step.status === "pending" ? "text-muted-foreground" : "font-medium"}>
                {step.label}
              </span>
            </div>
            {step.status === "failed" && step.error ? (
              <p className="mt-0.5 pl-5 text-[10px] leading-snug text-destructive">{step.error}</p>
            ) : step.message ? (
              <p className="mt-0.5 pl-5 text-[10px] leading-snug text-muted-foreground">{step.message}</p>
            ) : null}
          </li>
        ))}
      </ul>

      {running && (
        <div className="mt-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {state.message || "En cours…"} · {progress} %
          </p>
        </div>
      )}

      {state.error && !running && (
        <p className="mt-1.5 text-[11px] leading-snug text-destructive">{state.error}</p>
      )}
      {error && <p className="mt-1.5 text-[11px] leading-snug text-destructive">{error}</p>}

      {state.status === "done" && state.video && (
        <div className="mt-2 grid gap-1.5 rounded-md border border-success/40 bg-success/10 p-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="success" className="text-[10px]">vidéo prête</Badge>
            <Badge variant="outline" className="text-[10px]">{formatBytes(state.video.size_bytes)}</Badge>
            <Badge variant="outline" className="text-[10px]">{formatDuration(state.video.duration)}</Badge>
          </div>
          <a
            href={api.autopilotFileUrl(planId)}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] font-medium text-primary underline hover:no-underline"
          >
            {state.video.name}
          </a>
          <video
            src={api.autopilotFileUrl(planId)}
            controls
            className="max-h-[280px] w-full rounded-md border border-border bg-black"
          />
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-1.5">
        {running && (
          <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={cancel} disabled={busy}>
            <Square size={11} /> Annuler
          </Button>
        )}
        {state.resumable && (
          <Button size="sm" className="h-7 gap-1 text-xs" onClick={resume} disabled={busy}>
            {busy ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />} Reprendre
          </Button>
        )}
        {state.status === "done" && state.video && (
          <a
            href={api.autopilotFileUrl(planId)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-7 items-center gap-1 rounded-md border border-input px-2 text-xs font-medium hover:bg-accent hover:text-accent-foreground"
          >
            <Play size={12} /> Ouvrir la vidéo
          </a>
        )}
      </div>
    </div>
  );
}