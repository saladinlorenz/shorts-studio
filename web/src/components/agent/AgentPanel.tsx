import React from "react";
import { BrainCircuit, Eye, Loader2, Send, Sparkles, Square } from "lucide-react";
import { Button } from "../ui/button";
import {
  api,
  apiErrorMessage,
  type AgentRun,
  type AgentStatus,
  type Proposal,
  type Project,
} from "../../api/client";
import { cancelJob, useJobPolling } from "../../lib/jobs";
import ProposalCard from "./ProposalCard";
import SourcesPanel from "./SourcesPanel";

interface Turn {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  project: Project | null;
  projectName?: string;
  selection?: { sceneId: string | null; layerId: string | null };
  /** "design" : projets et calques. "production" : colonnes CSV comme données. */
  mode?: "design" | "production";
  csvColumns?: string[];
  onApply?: (candidate: Project) => void;
  onLibrarySave?: (candidate: Project, label: string, description: string) => void;
  /** Production only : un plan accepté remplit le mapping local, sans lancer quoi que ce soit. */
  onBatchPlan?: (batch: NonNullable<Proposal["batch"]>) => void;
  notify: (message: string, kind?: "ok" | "error" | "info") => void;
  /**
   * Demande envoyee depuis une autre page (cockpit, palette) : le tiroir est
   * une seule conversation, une clef `nonce` evite de rejouer la meme demande.
   */
  externalRequest?: { text: string; nonce: number } | null;
  /** Absence d'éditeur sur la page : texte affiché à la place des boutons d'application. */
  applyHint?: string;
  /** Tiroir ouvert : l'état de l'assistant est relu à chaque ouverture. */
  visible?: boolean;
  /** Chemin vers la configuration guidée (cockpit), proposé quand non configuré. */
  onConfigure?: () => void;
}

const PROVIDER_LABEL: Record<string, string> = {
  local: "serveur local",
  gemini: "Gemini",
  groq: "Groq",
};

const PLACEHOLDER: Record<string, string> = {
  design:
    "Ex. : mets l'accent en bleu pétrole, raccourcis la scène 2 à 4 s, ajoute une scène de conclusion.",
  production:
    "Ex. : associe la colonne Titre au texte d'accroche et Citation au calque de la scène 2, puis montre le plan.",
};

/**
 * Panneau Assistant du studio : la demande part au serveur, le serveur
 * orchestre (contexte borné → modèle → contrat → validation métier) et rend
 * une proposition. Rien n'est appliqué sans clic, et le candidat ne passe par
 * l'état de l'éditeur qu'après acceptation.
 */
export default function AgentPanel({
  project,
  projectName = "",
  selection = { sceneId: null, layerId: null },
  mode = "design",
  csvColumns = [],
  onApply,
  onLibrarySave,
  onBatchPlan,
  notify,
  externalRequest = null,
  applyHint,
  visible,
  onConfigure,
}: Props) {
  const [status, setStatus] = React.useState<AgentStatus | null>(null);
  const [message, setMessage] = React.useState("");
  const [history, setHistory] = React.useState<Turn[]>([]);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [run, setRun] = React.useState<AgentRun | null>(null);
  const [error, setError] = React.useState("");
  const [conflict, setConflict] = React.useState("");
  const [applying, setApplying] = React.useState(false);
  const [preview, setPreview] = React.useState<Project | null>(null);
  const { job, pollError } = useJobPolling(jobId, 500);

  const refreshStatus = React.useCallback(async () => {
    try {
      setStatus(await api.agentStatus());
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }, []);

  // Au montage et à chaque ouverture du tiroir : une configuration faite
  // pendant que le tiroir était fermé doit être visible sans rechargement.
  React.useEffect(() => {
    if (visible !== false) void refreshStatus();
  }, [visible, refreshStatus]);

  // Une demande à la fois : le résultat du job devient la proposition courante.
  React.useEffect(() => {
    if (!job || job.status === "running") return;
    setJobId(null);
    if (job.status === "error") {
      setError(job.error || "Le serveur n'a pas pu terminer la demande.");
      setRun(null);
    } else if (job.status === "cancelled") {
      setError("Demande annulée.");
    } else if (job.result) {
      const data = job.result as AgentRun;
      setRun(data);
      setError("");
      setConflict("");
      setPreview(null);
      setHistory((prev) =>
        [...prev, { role: "assistant", content: data.proposal.summary } as Turn].slice(-8),
      );
    }
  }, [job]);

  if (pollError && !error) setError(pollError);

  const submit = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || jobId) return;
    setError("");
    setConflict("");
    setPreview(null);
    setRun(null);
    try {
      const response = await api.agentAsk({
        message: trimmed,
        project,
        project_name: projectName,
        selection: selection.sceneId || selection.layerId ? { ...selection } : null,
        history,
        mode,
        csv_columns: csvColumns,
      });
      setHistory((prev) => [...prev, { role: "user", content: trimmed } as Turn].slice(-8));
      setMessage("");
      setJobId(response.job_id);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const ask = () => void submit(message);

  // Demande venue d'une autre page : le nonce garantit un seul envoi.
  const playedNonce = React.useRef(0);
  React.useEffect(() => {
    if (!externalRequest || externalRequest.nonce === playedNonce.current) return;
    playedNonce.current = externalRequest.nonce;
    void submit(externalRequest.text);
  }, [externalRequest, project, projectName, selection, mode, csvColumns, history]);

  const stop = async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const accept = async (rebase: boolean) => {
    if (!run) return;
    setApplying(true);
    setError("");
    setConflict("");
    try {
      const result = await api.agentAccept(run.proposal.id, project, rebase);
      if (result.kind === "project" && result.project) {
        onApply?.(result.project);
        notify(
          (rebase ? "Opérations rejouées sur votre projet actuel. " : "") +
            "Modifications appliquées — Annuler est disponible.",
          "ok",
        );
      } else if (result.kind === "library_save" && result.project) {
        onLibrarySave?.(result.project, result.library?.label || projectName, result.library?.description || "");
      } else if (result.kind === "batch_plan" && result.batch) {
        if (onBatchPlan) {
          onBatchPlan(result.batch);
          notify("Réglages proposés repris dans le formulaire. Le plan reste calculé par le moteur, le lancement est votre clic.", "ok");
        } else {
          notify("Ce plan se prépare dans Production.", "info");
        }
      }
      setRun((current) =>
        current ? { ...current, proposal: { ...current.proposal, status: "accepted" } } : current,
      );
    } catch (e: any) {
      if (e?.status === 409) {
        const detail = (e.detail as any)?.detail ?? e.detail ?? {};
        setConflict(String(detail.message || e.message));
      } else {
        setError(apiErrorMessage(e));
      }
    } finally {
      setApplying(false);
    }
  };

  const reject = async () => {
    if (!run) return;
    try {
      await api.agentReject(run.proposal.id);
      setRun((current) =>
        current ? { ...current, proposal: { ...current.proposal, status: "rejected" } } : current,
      );
      notify("Proposition refusée : le projet n'a pas changé.", "info");
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const showPreview = async () => {
    if (!run) return;
    if (preview) {
      setPreview(null);
      return;
    }
    try {
      const r = await api.agentProposal(run.proposal.id, true);
      setPreview(r.proposal?.candidate ?? null);
      if (!r.proposal?.candidate) notify("Cette proposition n'a pas de projet candidat.", "info");
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const ready = status?.ready;
  const provider = status?.provider || "local";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Sparkles size={13} className={ready ? "text-primary" : "text-muted-foreground"} />
        <span className="text-xs font-medium">Assistant</span>
        <button
          className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
          onClick={refreshStatus}
          title="Recharger l'état de l'assistant"
        >
          <BrainCircuit size={11} />
          {PROVIDER_LABEL[provider] || provider} · {status?.model || "aucun modèle"}
        </button>
      </div>

      {!ready && (
        <div className="mb-1.5 rounded border border-warning/40 bg-warning/10 px-2 py-1 text-[11px] text-warning">
          <p>{status?.reason || "Assistant non configuré : Réglages → Assistant IA."}</p>
          {onConfigure && (
            <button
              className="mt-1 font-medium underline hover:no-underline"
              onClick={onConfigure}
            >
              Configurer l'assistant
            </button>
          )}
        </div>
      )}

      <textarea
        className="input-base min-h-[72px] flex-1 resize-none text-xs"
        placeholder={PLACEHOLDER[mode]}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask();
        }}
        disabled={!!jobId}
      />

      <div className="mt-1.5 flex items-center gap-1.5">
        <Button size="sm" className="h-7 flex-1 gap-1 text-xs" onClick={ask} disabled={!!jobId || !message.trim()}>
          {jobId ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          {jobId ? "En cours…" : "Générer une proposition"}
        </Button>
        {jobId && (
          <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={stop}>
            <Square size={11} /> Stop
          </Button>
        )}
      </div>

      {job && job.status === "running" && (
        <p className="mt-1 text-[10px] text-muted-foreground">
          {job.message} · {Math.round((job.progress || 0) * 100)} %
        </p>
      )}

      {error && <p className="mt-1.5 text-[11px] leading-snug text-destructive">{error}</p>}

      {run && (
        <div className="mt-1.5 min-h-0 flex-1 overflow-auto">
          <ProposalCard
            proposal={run.proposal as Proposal}
            applying={applying}
            conflict={conflict}
            batchAcceptLabel={mode === "production" ? "Reprendre le mapping" : undefined}
            applyHint={applyHint}
            onAccept={(rebase) => void accept(rebase)}
            onReject={() => void reject()}
            onCorrect={() => {
              setMessage("");
              notify("Répondez aux questions puis relancez la demande.", "info");
            }}
          />
          {(run.proposal.type === "project_patch" || run.proposal.type === "project_new") && (
            <button
              className="mt-1.5 flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={showPreview}
            >
              <Eye size={11} /> {preview ? "Masquer l'aperçu du candidat" : "Aperçu du candidat"}
            </button>
          )}
          {preview && (
            <pre className="mt-1 max-h-56 overflow-auto rounded border border-border/60 bg-muted/20 p-1.5 text-[10px] leading-tight">
              {JSON.stringify(
                {
                  theme: preview.theme,
                  audio: preview.audio,
                  export: preview.export,
                  scenes: (preview.content?.scenes || []).map((scene: any) => ({
                    id: scene.id,
                    duration: scene.duration,
                    layers: (scene.layers || []).map((layer: any) => ({
                      id: layer.id,
                      text: layer.text,
                      style: layer.style?.color,
                      font: layer.style?.font_family,
                    })),
                  })),
                },
                null,
                1,
              )}
            </pre>
          )}
          <SourcesPanel
            sources={run.proposal.sources || []}
            meta={run.meta}
            knowledge={status?.knowledge || null}
          />
        </div>
      )}

      {!run && (
        <div className="mt-2 min-h-0 flex-1 overflow-auto text-[11px] text-muted-foreground">
          <p>
            {mode === "production"
              ? "L'assistant lit les colonnes réelles du CSV, les champs remplissables du modèle et le policy du planificateur. Il propose un mapping et des options ; le plan est ensuite recalculé par le moteur de Production, et aucun lot n'est lancé sans votre clic."
              : "L'assistant lit le projet affiché, la sélection en cours et la documentation du studio, puis propose des opérations bornées. Il ne lance jamais de rendu, n'installe rien et ne supprime aucun fichier."}
          </p>
          {status?.capabilities?.not_available?.length ? (
            <ul className="mt-1.5 space-y-1">
              {status.capabilities.not_available.slice(0, 3).map((item, index) => (
                <li key={index} className="rounded border border-border/50 px-1.5 py-1">
                  {item.split(" : ")[0]}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}
