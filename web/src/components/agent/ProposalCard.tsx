import React from "react";
import { AlertTriangle, Check, Pencil, X } from "lucide-react";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import type { Proposal } from "../../api/client";

interface Props {
  proposal: Proposal;
  applying: boolean;
  conflict: string;
  onAccept: (rebase: boolean) => void;
  onReject: () => void;
  onCorrect: () => void;
  /** Libellé du bouton d'acceptation d'un plan de lot (Production : le plan repart dans le formulaire). */
  batchAcceptLabel?: string;
  /** Page sans éditeur : remplace les boutons d'application par ce qu'il faut ouvrir. */
  applyHint?: string;
}

const TYPE_LABEL: Record<string, string> = {
  question: "Question",
  unavailable: "Non disponible",
  project_new: "Nouveau projet",
  project_patch: "Modification",
  library_save: "Enregistrer en modèle",
  batch_plan: "Plan de lot",
};

/**
 * Une proposition, son détail et aucun bouton magique : le projet candidat
 * n'est appliqué qu'après un clic, dans l'historique Annuler/Rétablir.
 */
export default function ProposalCard({
  proposal,
  applying,
  conflict,
  onAccept,
  onReject,
  onCorrect,
  batchAcceptLabel,
  applyHint,
}: Props) {
  const changes = proposal.changes || [];
  const warnings = proposal.warnings || [];
  const state = proposal.validation?.state || "invalide";
  const applicable = proposal.type === "project_patch" || proposal.type === "project_new";
  const isBatch = proposal.type === "batch_plan";
  const isLibrary = proposal.type === "library_save";

  return (
    <div className="panel mt-2 p-2.5">
      <div className="flex items-center gap-2">
        <Badge variant={state === "valid" ? "default" : "secondary"} className="text-[10px]">
          {TYPE_LABEL[proposal.type] || proposal.type}
        </Badge>
        <Badge variant={state === "valid" ? "outline" : "destructive"} className="text-[10px]">
          {state === "valid" ? "validé par le studio" : "rejeté"}
        </Badge>
        {proposal.status === "accepted" && <span className="text-[10px] text-success">acceptée</span>}
        {proposal.status === "rejected" && <span className="text-[10px] text-muted-foreground">refusée</span>}
      </div>

      <p className="mt-1.5 text-xs leading-snug">{proposal.summary}</p>

      {proposal.type === "question" && (
        <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs">
          {(proposal.questions || []).map((question, index) => (
            <li key={index}>{question}</li>
          ))}
        </ul>
      )}

      {proposal.type === "unavailable" && (
        <div className="mt-1.5 space-y-1 text-xs">
          <p className="text-warning">Non pris en charge : {proposal.capability}</p>
          <p className="text-muted-foreground">À la place : {proposal.alternative}</p>
        </div>
      )}

      {changes.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {changes.slice(0, 12).map((change, index) => (
            <li key={index} className="rounded border border-border/60 bg-muted/20 px-1.5 py-1 text-[11px]">
              <span className="font-mono text-muted-foreground">{change.target}</span>
              <div className="mt-0.5 flex flex-wrap items-center gap-1">
                <span className="line-through opacity-60">{change.before}</span>
                <span aria-hidden>→</span>
                <span className="font-medium">{change.after}</span>
              </div>
            </li>
          ))}
          {changes.length > 12 && (
            <li className="text-[10px] text-muted-foreground">+ {changes.length - 12} autre(s) changement(s)</li>
          )}
        </ul>
      )}

      {isBatch && proposal.batch && (
        <div className="mt-1.5 space-y-1 text-[11px]">
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
          <p className="text-muted-foreground">
            options {Object.entries(proposal.batch.options).map(([k, v]) => `${k}=${v}`).join(" · ")}
          </p>
          {proposal.batch.notes && <p className="text-muted-foreground">{proposal.batch.notes}</p>}
          <p className="text-[10px] italic text-muted-foreground">
            Le plan réel est recalculé par le moteur du studio ; aucun lot n'est lancé ici.
          </p>
        </div>
      )}

      {isLibrary && proposal.library && (
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Modèle « {proposal.library.label} » — {proposal.library.description}
        </p>
      )}

      {warnings.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {warnings.map((warning, index) => (
            <li key={index} className="flex items-start gap-1 text-[11px] text-warning">
              <AlertTriangle size={11} className="mt-0.5 shrink-0" />
              {warning}
            </li>
          ))}
        </ul>
      )}

      {(proposal.validation?.errors || []).length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-[11px] text-destructive">
          {(proposal.validation?.errors || []).map((error, index) => (
            <li key={index}>{error}</li>
          ))}
        </ul>
      )}

      {conflict && (
        <div className="mt-1.5 rounded border border-warning/50 bg-warning/10 p-1.5 text-[11px]">
          <p className="text-warning">{conflict}</p>
          <p className="mt-0.5 text-muted-foreground">
            Rien n'a été appliqué : vos changements récents sont conservés.
          </p>
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-1.5">
        {state === "valid" && applyHint ? (
          <p className="w-full rounded border border-border/60 bg-muted/20 px-1.5 py-1 text-[11px] leading-snug text-muted-foreground">
            {applyHint}
          </p>
        ) : (
          <>
            {applicable && state === "valid" && (
              <Button size="sm" className="h-7 gap-1 text-xs" onClick={() => onAccept(false)} disabled={applying}>
                <Check size={12} /> Appliquer
              </Button>
            )}
            {(isBatch || isLibrary) && state === "valid" && (
              <Button size="sm" className="h-7 gap-1 text-xs" onClick={() => onAccept(false)} disabled={applying}>
                <Check size={12} /> {isBatch ? batchAcceptLabel || "Préparer dans Production" : "Enregistrer le modèle"}
              </Button>
            )}
          </>
        )}
        {conflict && (
          <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={() => onAccept(true)} disabled={applying}>
            Rejouer sur mon projet
          </Button>
        )}
        <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={onCorrect} disabled={applying}>
          <Pencil size={12} /> Corriger
        </Button>
        <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs" onClick={onReject} disabled={applying}>
          <X size={12} /> Refuser
        </Button>
      </div>
    </div>
  );
}
