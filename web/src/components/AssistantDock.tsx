import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { PanelRightClose, Sparkles } from "lucide-react";
import AgentPanel from "./agent/AgentPanel";
import { useAssistant } from "../lib/assistant";

/**
 * Tiroir d'assistant : une seule conversation pour tout le studio.
 *
 * Il occupe une colonne de la fenêtre au lieu de passer par-dessus : fermé, il
 * laisse un rail de 26 px ; ouvert, il prend 400 px et les pages se resserrent.
 * Sur l'accueil Studio, la conversation est la surface principale : le tiroir est
 * toujours ouvert, à droite de l'aperçu vidéo. Le contenu reste monté quand il
 * est fermé, donc la conversation et le job en cours survivent au tiroir fermé.
 *
 * Une page sans éditeur (Clips, Podcast, Réglages) ne reçoit pas de faux bouton
 * « Appliquer » : le tiroir dit où aller.
 */
export default function AssistantDock() {
  const { open, setOpen, data, handlers, request } = useAssistant();
  const navigate = useNavigate();
  const location = useLocation();
  const isHome = location.pathname === "/";
  const expanded = isHome || open;

  const selectionLabel = React.useMemo(() => {
    const scene = data.selection?.sceneId;
    const layer = data.selection?.layerId;
    if (scene && layer) return `scène ${scene} · calque ${layer}`;
    if (scene) return `scène ${scene}`;
    if (layer) return `calque ${layer}`;
    return "";
  }, [data.selection]);

  const contextLabel = React.useMemo(() => {
    if (data.mode === "production") {
      return `Production${data.projectName ? ` · ${data.projectName}` : ""} · ${
        data.csvColumns?.length ? `${data.csvColumns.length} colonne(s) CSV` : "aucun CSV importé"
      }`;
    }
    if (!data.project) return "Aucun projet ouvert — réponses de documentation et de réglages";
    return [data.source || "Studio", data.projectName || "projet sans nom", selectionLabel]
      .filter(Boolean)
      .join(" · ");
  }, [data, selectionLabel]);

  const applyHint = React.useMemo(() => {
    const has = handlers.current;
    if (data.mode === "production") {
      return has.onBatchPlan
        ? undefined
        : "Le plan se reprend dans le formulaire de Production : ouvrez Production pour l'utiliser.";
    }
    return has.onApply
      ? undefined
      : "Aucun éditeur sur cette page : ouvrez Design, relancez la demande avec le projet affiché, puis appliquez.";
  }, [data, handlers]);

  // Les gestionnaires sont lus au moment de l'appel : la page a pu changer de
  // closure d'édition depuis le dernier rendu du tiroir.
  const forward = React.useCallback(
    (fn: ((...args: any[]) => void) | undefined, ...args: any[]) => {
      if (fn) fn(...args);
    },
    [],
  );

  React.useEffect(() => {
    if (!open || isHome) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, isHome, setOpen]);

  return (
    <>
      {!expanded && (
        <button
          onClick={() => setOpen(true)}
          className="flex w-[26px] shrink-0 flex-col items-center gap-2 border-l border-border bg-card/60 py-3 text-muted-foreground hover:text-foreground"
          title="Ouvrir l'assistant (Ctrl+I)"
          aria-label="Ouvrir l'assistant"
        >
          <Sparkles size={14} />
          <span className="[writing-mode:vertical-rl] text-[11px]">Assistant</span>
        </button>
      )}

      <aside
        className={
          "w-[400px] max-w-[92vw] shrink-0 flex-col border-l border-border bg-card " +
          (expanded ? "flex" : "hidden")
        }
        aria-label="Assistant du studio"
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2">
          <Sparkles size={14} className="text-primary" />
          <span className="text-sm font-medium">Assistant</span>
          {!isHome && (
            <button
              className="ml-auto text-muted-foreground hover:text-foreground"
              onClick={() => setOpen(false)}
              aria-label="Fermer l'assistant"
              title="Fermer (Échap)"
            >
              <PanelRightClose size={15} />
            </button>
          )}
        </header>
        <div className="shrink-0 border-b border-border px-3 py-1.5 text-[11px] leading-snug text-muted-foreground">
          {contextLabel}
        </div>
        <div className="min-h-0 flex-1 p-3">
          <AgentPanel
            project={data.project ?? null}
            projectName={data.projectName ?? ""}
            selection={data.selection ?? { sceneId: null, layerId: null }}
            mode={data.mode ?? "design"}
            csvColumns={data.csvColumns ?? []}
            externalRequest={request}
            applyHint={applyHint}
            visible={expanded}
            onConfigure={() => {
              setOpen(false);
              navigate("/cockpit");
            }}
            onApply={(candidate) => forward(handlers.current.onApply, candidate)}
            onUndo={() => forward(handlers.current.onUndo)}
            onRedo={() => forward(handlers.current.onRedo)}
            onLibrarySave={(candidate, label, description) =>
              forward(handlers.current.onLibrarySave, candidate, label, description)
            }
            onBatchPlan={(batch) => forward(handlers.current.onBatchPlan, batch)}
            notify={(message, kind) => forward(handlers.current.notify, message, kind)}
          />
        </div>
      </aside>
    </>
  );
}