import React from "react";
import { BrainCircuit, Loader2, Rocket, Send, Sparkles, Square, Undo2 } from "lucide-react";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import {
  api,
  apiErrorMessage,
  type AgentRun,
  type AgentStatus,
  type Proposal,
  type Project,
} from "../../api/client";
import { cancelJob, useJobPolling } from "../../lib/jobs";
import SourcesPanel from "./SourcesPanel";
import AutopilotTracker from "./AutopilotTracker";
import ActionTracker, { actionObservation, reviewProposal } from "./ActionTracker";

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
  onUndo?: () => void;
  onRedo?: () => void;
  onLibrarySave?: (candidate: Project, label: string, description: string) => void;
  /** Production only : un plan accepté remplit le mapping local, sans lancer quoi que ce soit. */
  onBatchPlan?: (batch: NonNullable<Proposal["batch"]>) => void;
  notify: (message: string, kind?: "ok" | "error" | "info") => void;
  /**
   * Demande envoyee depuis une autre page (cockpit, palette) : le tiroir est
   * une seule conversation, une clef `nonce` evite de rejouer la meme demande.
   */
  externalRequest?: { text: string; nonce: number } | null;
  /** Absence d'éditeur sur la page : texte affiché à la place de l'application automatique. */
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
    "Demandez une modification… (Entrée pour envoyer, Maj+Entrée pour un retour à la ligne)",
  production:
    "Ex. : associe la colonne Titre à l'accroche et Citation au calque de la scène 2.",
  autopilot:
    "Ex. : crée une vidéo citation motivante en français, voix off féminine, export « citation-du-jour ».",
};

// Commandes purement locales : aucun appel au modèle pour annuler / rétablir.
const UNDO_RE = /^(annule(r)?(\s+la\s+derni[eè]re\s+modification)?|undo|d[eé]fais(\s+la\s+derni[eè]re\s+modification)?)\s*[.!]?$/i;
const REDO_RE = /^(r[eé]tabli(s|r)?(\s+la\s+derni[eè]re\s+modification)?|redo)\s*[.!]?$/i;

const OBSERVATION_PREFIX = "[UNTRUSTED OBSERVATION";

/**
 * Conversation du studio. La demande part au serveur, qui orchestre (contexte
 * borné → modèle → contrat → validation métier) et rend une proposition validée.
 * En mode « tout automatique », une proposition valide est appliquée sans clic :
 * le candidat passe par l'historique Annuler/Rétablir, une action du studio part
 * avec le jeton de confirmation émis par le serveur, un plan autopilote démarre.
 * Aucun résultat d'outil ne relance le modèle : les observations restent des
 * données affichées, jamais une nouvelle demande automatique.
 */
export default function AgentPanel({
  project,
  projectName = "",
  selection = { sceneId: null, layerId: null },
  mode = "design",
  csvColumns = [],
  onApply,
  onUndo,
  onRedo,
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
  const [applying, setApplying] = React.useState(false);
  const [applied, setApplied] = React.useState<{ rebased: boolean } | null>(null);
  const [autopilot, setAutopilot] = React.useState(false);
  const [planId, setPlanId] = React.useState<string | null>(null);
  const [actionJobId, setActionJobId] = React.useState<string | null>(null);
  const [actionRun, setActionRun] = React.useState<AgentRun | null>(null);
  const [launching, setLaunching] = React.useState(false);
  const [launchError, setLaunchError] = React.useState("");
  const actionLock = React.useRef(false);
  const observedActions = React.useRef(new Set<string>());
  const { job, pollError } = useJobPolling(jobId, 500);
  const { job: actionJob, pollError: actionPollError } = useJobPolling(actionJobId, 700);
  const actionActive = !!actionJobId || launching || actionJob?.status === "running";
  const busy = !!jobId || actionActive || applying;

  const scrollRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [history, run, applied, job?.message, actionJob?.message]);

  const pushTurn = React.useCallback((role: Turn["role"], content: string) => {
    setHistory((prev) => [...prev, { role, content } as Turn].slice(-12));
  }, []);

  const refreshStatus = React.useCallback(async () => {
    try {
      setStatus(await api.agentStatus());
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }, []);

  React.useEffect(() => {
    if (visible !== false) void refreshStatus();
  }, [visible, refreshStatus]);

  /* ----------------------- application automatique ----------------------- */

  const acceptProposal = React.useCallback(
    async (target: AgentRun, rebase: boolean) => {
      setApplying(true);
      setError("");
      try {
        const result = await api.agentAccept(target.proposal.id, project, rebase);
        if (result.kind === "project" && result.project) {
          onApply?.(result.project);
          setApplied({ rebased: rebase });
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
            notify("Réglages repris dans le formulaire de Production.", "ok");
          } else {
            notify("Ce plan se prépare dans Production.", "info");
          }
        }
        setRun((current) =>
          current && current.proposal.id === target.proposal.id
            ? { ...current, proposal: { ...current.proposal, status: "accepted" } }
            : current,
        );
      } catch (e: any) {
        if (e?.status === 409 && !rebase) {
          // Conflit de révision : on rejoue une seule fois sur le projet actuel.
          await acceptProposal(target, true);
        } else {
          setError(apiErrorMessage(e));
        }
      } finally {
        setApplying(false);
      }
    },
    [project, projectName, onApply, onLibrarySave, onBatchPlan, notify],
  );

  const executeActionFor = React.useCallback(
    async (target: AgentRun, confirmation: string) => {
      if (actionLock.current || actionActive) return;
      actionLock.current = true;
      setActionRun(target);
      setLaunching(true);
      setLaunchError("");
      try {
        const response = await api.agentExecute(target.proposal.id, confirmation, project);
        setActionJobId(response.job_id);
        setRun((current) =>
          current && current.proposal.id === target.proposal.id
            ? { ...current, proposal: { ...current.proposal, status: "accepted" } }
            : current,
        );
      } catch (e) {
        setLaunchError(apiErrorMessage(e));
      } finally {
        actionLock.current = false;
        setLaunching(false);
      }
    },
    [project, actionActive],
  );

  const startAutopilotFor = React.useCallback(
    async (target: AgentRun) => {
      setApplying(true);
      setError("");
      try {
        const response = await api.autopilotStart({ proposal_id: target.proposal.id });
        setPlanId(response.job_id);
        setRun((current) =>
          current && current.proposal.id === target.proposal.id
            ? { ...current, proposal: { ...current.proposal, status: "accepted" } }
            : current,
        );
        notify("Plan démarré : script, design, voix off et export s'enchaînent.", "ok");
      } catch (e) {
        setError(apiErrorMessage(e));
      } finally {
        setApplying(false);
      }
    },
    [notify],
  );

  // Une proposition valide est appliquée automatiquement, une seule fois.
  const autoApply = React.useCallback(
    (target: AgentRun) => {
      const proposal = target.proposal;
      if (proposal.validation?.state !== "valid") return;
      if (applyHint && (proposal.type === "project_patch" || proposal.type === "project_new" || proposal.type === "library_save")) {
        notify(applyHint, "info");
        return;
      }
      if (proposal.type === "project_patch" || proposal.type === "project_new" || proposal.type === "library_save" || proposal.type === "batch_plan") {
        void acceptProposal(target, false);
      } else if (proposal.type === "studio_action" && proposal.action?.confirmation
                 && proposal.action.name !== "image_generate") {
        // image_generate envoie le prompt à un service tiers : clic dédié obligatoire, jamais automatique.
        void executeActionFor(target, proposal.action.confirmation);
      } else if (proposal.type === "autopilot_plan") {
        void startAutopilotFor(target);
      }
    },
    [applyHint, acceptProposal, executeActionFor, startAutopilotFor, notify],
  );

  /* --------------------------- suivi des jobs --------------------------- */

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
      setApplied(null);
      pushTurn("assistant", data.proposal.summary);
      autoApply(data);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job]);

  if (pollError && !error) setError(pollError);

  React.useEffect(() => {
    if (!actionJob || actionJob.status === "running" || !actionRun) return;
    if (!observedActions.current.has(actionJob.id)) {
      observedActions.current.add(actionJob.id);
      pushTurn("assistant", actionObservation(actionRun.proposal, actionJob));
    }
    const correction = reviewProposal(actionJob.result);
    if (correction) {
      const corrected: AgentRun = { ...actionRun, proposal: correction };
      setRun(corrected);
      pushTurn("assistant", correction.summary);
      autoApply(corrected);
    }
    setActionJobId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actionJob, actionRun]);

  /* ------------------------------ envoi ------------------------------ */

  const submit = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    // Annuler / rétablir : purement local, aucun appel au modèle.
    if (UNDO_RE.test(trimmed)) {
      pushTurn("user", trimmed);
      setMessage("");
      setRun(null);
      setApplied(null);
      if (onUndo) {
        onUndo();
        pushTurn("assistant", "Dernière modification annulée.");
      } else {
        pushTurn("assistant", "Aucun éditeur sur cette page : ouvrez Design pour annuler.");
      }
      return;
    }
    if (REDO_RE.test(trimmed)) {
      pushTurn("user", trimmed);
      setMessage("");
      setRun(null);
      setApplied(null);
      if (onRedo) {
        onRedo();
        pushTurn("assistant", "Modification rétablie.");
      } else {
        pushTurn("assistant", "Aucun éditeur sur cette page : ouvrez Design pour rétablir.");
      }
      return;
    }

    setActionRun(null);
    setActionJobId(null);
    setLaunchError("");
    setError("");
    setApplied(null);
    setRun(null);
    setPlanId(null);
    try {
      const response = autopilot
        ? await api.autopilotPlan({ message: trimmed, history })
        : await api.agentAsk({
            message: trimmed,
            project,
            project_name: projectName,
            selection: selection.sceneId || selection.layerId ? { ...selection } : null,
            history,
            mode,
            csv_columns: csvColumns,
          });
      pushTurn("user", trimmed);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalRequest]);

  const stop = async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const ready = status?.ready;
  const provider = status?.provider || "local";
  const proposal = run?.proposal;
  const changes = proposal?.changes || [];
  const warnings = proposal?.warnings || [];
  const validationErrors = proposal?.validation?.errors || [];
  const isProjectChange = proposal?.type === "project_patch" || proposal?.type === "project_new";
  const imageActionPending =
    proposal?.type === "studio_action" &&
    proposal.action?.name === "image_generate" &&
    proposal.validation?.state === "valid" &&
    proposal.status !== "accepted" &&
    !actionActive;

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

      <div className="mb-1.5 flex gap-1">
        <button
          className={
            "flex h-6 items-center gap-1 rounded-md px-2 text-[11px] " +
            (!autopilot ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")
          }
          onClick={() => setAutopilot(false)}
        >
          <Sparkles size={11} /> Discussion
        </button>
        <button
          className={
            "flex h-6 items-center gap-1 rounded-md px-2 text-[11px] " +
            (autopilot ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")
          }
          onClick={() => setAutopilot(true)}
          title="Une vidéo complète : script, design, voix off, export — démarrée automatiquement."
        >
          <Rocket size={11} /> Autopilote
        </button>
      </div>

      {!ready && (
        <div className="mb-1.5 rounded border border-warning/40 bg-warning/10 px-2 py-1 text-[11px] text-warning">
          <p>{status?.reason || "Assistant non configuré : Réglages → Assistant IA."}</p>
          {onConfigure && (
            <button className="mt-1 font-medium underline hover:no-underline" onClick={onConfigure}>
              Configurer l'assistant
            </button>
          )}
        </div>
      )}

      {/* ------------------------- conversation ------------------------- */}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
        {history.length === 0 && !run && (
          <div className="rounded-md border border-border/60 bg-muted/20 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
            {autopilot
              ? "Décrivez la vidéo voulue : l'autopilote choisit un modèle réel, écrit le script, propose le design et une voix off, puis exporte en MP4. Le plan validé démarre tout seul — annulable et reprenable."
              : mode === "production"
                ? "L'assistant lit les colonnes réelles du CSV et les champs du modèle, puis propose un mapping repris dans le formulaire de Production."
                : "Discutez normalement : chaque modification validée est appliquée automatiquement et l'aperçu se met à jour. Dites « annule » ou « rétablis » à tout moment — ces commandes ne consomment aucun appel au modèle."}
          </div>
        )}

        {history.map((turn, index) => {
          const isUser = turn.role === "user";
          const isObservation = turn.content.startsWith(OBSERVATION_PREFIX);
          if (isObservation) {
            return (
              <div key={index} className="flex justify-start">
                <div className="max-w-[92%] rounded-md border border-border/60 bg-muted/20 px-2 py-1 text-[10px] italic text-muted-foreground">
                  Résultat de l'action pris en compte pour la suite de la conversation.
                </div>
              </div>
            );
          }
          return (
            <div key={index} className={"flex " + (isUser ? "justify-end" : "justify-start")}>
              <div
                className={
                  "max-w-[92%] whitespace-pre-wrap break-words rounded-lg px-2.5 py-1.5 text-[12px] leading-snug " +
                  (isUser ? "bg-primary text-primary-foreground" : "bg-muted/40 text-foreground")
                }
              >
                {turn.content}
              </div>
            </div>
          );
        })}

        {job && job.status === "running" && (
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Loader2 size={12} className="animate-spin" />
            {job.message} · {Math.round((job.progress || 0) * 100)} %
          </div>
        )}

        {error && <p className="text-[11px] leading-snug text-destructive">{error}</p>}

        {/* -------------------- résultat du tour courant -------------------- */}
        {run && proposal && (
          <div className="space-y-2 rounded-md border border-border/60 bg-card/40 p-2">
            {proposal.type === "question" && (proposal.questions || []).length > 0 && (
              <ul className="list-disc space-y-1 pl-4 text-[11px]">
                {(proposal.questions || []).map((question, index) => (
                  <li key={index}>{question}</li>
                ))}
              </ul>
            )}

            {proposal.type === "unavailable" && (
              <div className="space-y-1 text-[11px]">
                <p className="text-warning">Non pris en charge : {proposal.capability}</p>
                <p className="text-muted-foreground">À la place : {proposal.alternative}</p>
              </div>
            )}

            {changes.length > 0 && (
              <ul className="space-y-1">
                {changes.slice(0, 10).map((change, index) => (
                  <li key={index} className="rounded border border-border/60 bg-muted/20 px-1.5 py-1 text-[11px]">
                    <span className="font-mono text-muted-foreground">{change.target}</span>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1">
                      <span className="line-through opacity-60">{change.before}</span>
                      <span aria-hidden>→</span>
                      <span className="font-medium">{change.after}</span>
                    </div>
                  </li>
                ))}
                {changes.length > 10 && (
                  <li className="text-[10px] text-muted-foreground">+ {changes.length - 10} autre(s) changement(s)</li>
                )}
              </ul>
            )}

            {isProjectChange && applied && (
              <div className="flex flex-wrap items-center gap-2 rounded border border-success/40 bg-success/10 px-2 py-1 text-[11px]">
                <Badge variant="success" className="text-[10px]">
                  {applied.rebased ? "appliqué (rejoué)" : "appliqué"}
                </Badge>
                <span className="text-muted-foreground">Aperçu mis à jour.</span>
                {onUndo && (
                  <button
                    className="ml-auto flex items-center gap-1 font-medium text-foreground hover:underline"
                    onClick={onUndo}
                  >
                    <Undo2 size={12} /> Annuler
                  </button>
                )}
              </div>
            )}

            {isProjectChange && !applied && applying && (
              <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <Loader2 size={12} className="animate-spin" /> Application des modifications…
              </div>
            )}

            {proposal.type === "library_save" && proposal.library && (
              <p className="text-[11px] text-muted-foreground">
                Modèle « {proposal.library.label} » — {proposal.library.description}
              </p>
            )}

            {proposal.type === "batch_plan" && proposal.batch && (
              <div className="space-y-1 text-[11px]">
                <p>
                  modèle <span className="font-mono">{proposal.batch.model}</span>
                </p>
                <ul className="space-y-0.5">
                  {Object.entries(proposal.batch.mapping).map(([field, column]) => (
                    <li key={field} className="font-mono">
                      {field} <span aria-hidden>←</span> {column}
                    </li>
                  ))}
                </ul>
                {proposal.batch.notes && <p className="text-muted-foreground">{proposal.batch.notes}</p>}
              </div>
            )}

            {proposal.type === "studio_action" && proposal.action && (
              <div className="space-y-1 text-[11px]">
                <p className="font-medium">{proposal.action.label}</p>
                <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
                  {proposal.action.impact.map((impact, index) => (
                    <li key={index}>{impact}</li>
                  ))}
                </ul>
                {imageActionPending && (
                  <Button
                    size="sm"
                    className="mt-1 h-7 gap-1 text-xs"
                    onClick={() => {
                      if (run && proposal.action) void executeActionFor(run, proposal.action.confirmation);
                    }}
                  >
                    <Sparkles size={12} /> Générer l'image
                  </Button>
                )}
              </div>
            )}

            {actionRun && (
              <ActionTracker
                proposal={actionRun.proposal}
                jobId={actionJobId}
                job={actionJob}
                pollError={actionPollError}
                launchError={launchError}
                launching={launching}
              />
            )}
            {planId && <AutopilotTracker planId={planId} notify={notify} />}

            {warnings.length > 0 && (
              <ul className="space-y-0.5">
                {warnings.map((warning, index) => (
                  <li key={index} className="text-[11px] text-warning">{warning}</li>
                ))}
              </ul>
            )}

            {validationErrors.length > 0 && (
              <ul className="space-y-0.5 text-[11px] text-destructive">
                {validationErrors.map((validationError, index) => (
                  <li key={index}>{validationError}</li>
                ))}
              </ul>
            )}

            {proposal.validation?.state !== "valid" && (
              <p className="text-[11px] text-muted-foreground">
                Proposition non valide : rien n'a été appliqué. Reformulez ou corrigez la demande.
              </p>
            )}

            <SourcesPanel sources={proposal.sources || []} meta={run.meta} knowledge={status?.knowledge || null} />
          </div>
        )}
      </div>

      {/* --------------------------- saisie --------------------------- */}
      <div className="mt-1.5 shrink-0">
        <textarea
          className="input-base min-h-[56px] w-full resize-none text-xs"
          placeholder={PLACEHOLDER[autopilot ? "autopilot" : mode]}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
          disabled={busy}
        />
        <div className="mt-1.5 flex items-center gap-1.5">
          <Button size="sm" className="h-7 flex-1 gap-1 text-xs" onClick={ask} disabled={busy || !message.trim()}>
            {jobId ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            {jobId ? "En cours…" : autopilot ? "Créer la vidéo" : "Envoyer"}
          </Button>
          {jobId && (
            <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={stop}>
              <Square size={11} /> Stop
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}