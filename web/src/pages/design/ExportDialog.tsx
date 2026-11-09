import React from "react";
import { Download, Loader2, X } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Progress } from "../../components/ui/progress";
import { api, apiErrorMessage, type JobSnapshot, type Project } from "../../api/client";
import { formatBytes, useJobPolling } from "../../lib/jobs";

/** Boîte d'export : la progression vient vraiment du rendu Remotion, aucune
 *  barre simulée. Un export unitaire et un rendu de lot utilisent la même
 *  chaîne serveur, donc ce dialogue ne connaît que des jobs. */

type Phase = "idle" | "running" | "done" | "error" | "cancelled";

export default function ExportDialog({
  project,
  defaultName,
  onClose,
}: {
  project: Project;
  defaultName: string;
  onClose: () => void;
}) {
  const [name, setName] = React.useState(defaultName || "citation");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [finished, setFinished] = React.useState<JobSnapshot | null>(null);
  const [error, setError] = React.useState("");
  const [overwrite, setOverwrite] = React.useState(false);
  const { job, pollError } = useJobPolling(jobId, 600);

  const current = job ?? finished;
  const phase: Phase = jobId ? "running" : current?.status === "done" ? "done" : current?.status === "cancelled" ? "cancelled" : current ? "error" : "idle";

  React.useEffect(() => {
    if (job && job.status !== "running") {
      setFinished(job);
      setJobId(null);
    }
  }, [job]);

  async function start(shouldOverwrite: boolean) {
    setError("");
    setFinished(null);
    setOverwrite(false);
    try {
      const res = await api.startExport(name, project, shouldOverwrite);
      setJobId(res.job_id);
    } catch (e: any) {
      if (e?.status === 409) setOverwrite(true);
      setError(apiErrorMessage(e));
    }
  }

  async function cancel() {
    if (!jobId) return;
    try {
      await api.cancelExport(jobId);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }

  const result = (current?.result ?? {}) as Record<string, any>;
  const warnings = Array.isArray(result.warnings) ? (result.warnings as string[]) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="panel w-full max-w-xl p-4 shadow-2xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Exporter la vidéo</h2>
          <button className="text-muted-foreground hover:text-foreground" onClick={onClose} aria-label="Fermer">
            <X size={16} />
          </button>
        </div>

        <div className="grid gap-3">
          <label className="block">
            <span className="field-label">Nom du fichier (dossier exports/)</span>
            <div className="mt-1 flex items-center gap-2">
              <input
                className="input-base"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={phase === "running"}
                placeholder="citation-mark"
              />
              <span className="text-xs text-muted-foreground">.mp4</span>
            </div>
          </label>

          {phase === "running" && (
            <div className="grid gap-2 rounded-md border border-border p-3">
              <div className="flex items-center gap-2 text-sm">
                <Loader2 size={14} className="animate-spin" />
                <span>{current?.message || "Préparation du rendu…"}</span>
                <span className="ml-auto font-mono text-xs text-muted-foreground">
                  {Math.round((current?.progress ?? 0) * 100)} %
                </span>
              </div>
              <Progress value={current?.progress ?? 0} />
              <p className="text-[11px] text-muted-foreground">
                Rendu Remotion réel (frames lues dans la sortie du processus). L'annulation termine le
                processus et supprime le fichier provisoire.
              </p>
              <Button variant="outline" size="sm" onClick={cancel} className="justify-self-start">
                Annuler le rendu
              </Button>
            </div>
          )}

          {phase === "done" && (
            <div className="grid gap-2 rounded-md border border-success/40 bg-success/10 p-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="success">export terminé</Badge>
                <Badge variant="outline">{result.width}×{result.height}</Badge>
                <Badge variant="outline">{Number(result.duration ?? 0).toFixed(2)} s</Badge>
                <Badge variant="outline">{result.fps} fps</Badge>
                <Badge variant="outline">{result.frames} images</Badge>
                <Badge variant="outline">{formatBytes(result.size_bytes)}</Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Fichier : exports/{result.path} · composition {result.composition}
              </p>
              <video
                src={api.exportFileUrl(current?.id ?? "")}
                controls
                className="max-h-[320px] w-full rounded-md border border-border bg-black"
              />
              {warnings.length > 0 && (
                <div className="grid gap-0.5">
                  {warnings.map((warning, index) => (
                    <p key={index} className="text-[11px] text-warning">⚠ {warning}</p>
                  ))}
                </div>
              )}
            </div>
          )}

          {(phase === "error" || phase === "cancelled") && (
            <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-[11px] text-destructive">
              {phase === "cancelled" ? "Rendu annulé." : current?.error || error || pollError || "Échec du rendu."}
            </p>
          )}

          {error && phase !== "error" && phase !== "cancelled" && (
            <p className="text-[11px] text-destructive">{error}</p>
          )}
          {pollError && phase === "running" && <p className="text-[11px] text-warning">{pollError}</p>}

          <div className="flex items-center gap-2">
            {overwrite ? (
              <Button size="sm" onClick={() => start(true)} disabled={!name.trim()}>
                Remplacer le fichier existant
              </Button>
            ) : (
              <Button size="sm" onClick={() => start(false)} disabled={phase === "running" || !name.trim()}>
                <Download size={14} /> Lancer l'export
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={onClose}>
              Fermer
            </Button>
            {overwrite && <span className="text-[11px] text-muted-foreground">Un fichier porte déjà ce nom.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
