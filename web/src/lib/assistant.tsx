/**
 * Tiroir d'assistant global.
 *
 * L'assistant est le point d'entrée du studio : il vit hors des pages, donc la
 * conversation survit aux navigations et la meme instance peut agir sur le
 * projet affiche, sur un mapping de lot ou sur rien du tout (questions de
 * documentation). Une page publie le contexte que l'assistant lit ; elle ne
 * rend plus son propre panneau.
 *
 * Les gestionnaires (appliquer, enregistrer, notifier) sont stockes dans une
 * ref : ils changent a chaque rendu d'editeur sans provoquer de re-render du
 * tiroir, et l'appel se fait toujours sur la derniere closure.
 */
import React from "react";
import type { Project, Proposal } from "../api/client";

export type AssistantMode = "design" | "production";

export type AssistantSelection = { sceneId: string | null; layerId: string | null };

/** Ce que l'assistant lit : uniquement des donnees, jamais de code. */
export type AssistantData = {
  project?: Project | null;
  projectName?: string;
  selection?: AssistantSelection;
  mode?: AssistantMode;
  csvColumns?: string[];
  /** Nom de la page qui publie, affiche dans l'en-tete du tiroir. */
  source?: string;
};

/** Ce que la page accepte de recevoir en retour. */
export type AssistantHandlers = {
  onApply?: (candidate: Project) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  onLibrarySave?: (candidate: Project, label: string, description: string) => void;
  onBatchPlan?: (batch: NonNullable<Proposal["batch"]>) => void;
  notify?: (message: string, kind?: "ok" | "error" | "info") => void;
};

export type AssistantRequest = { text: string; nonce: number };

export type AssistantStore = {
  open: boolean;
  setOpen: (value: boolean) => void;
  toggle: () => void;
  request: AssistantRequest | null;
  /** Ouvre le tiroir et envoie la demande telle quelle. */
  ask: (text: string) => void;
  data: AssistantData;
  handlers: React.MutableRefObject<AssistantHandlers>;
  publish: (data: AssistantData, handlers?: AssistantHandlers) => void;
};

const OPEN_KEY = "studio.assistant.open";

const AssistantCtx = React.createContext<AssistantStore | null>(null);

export function AssistantProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpenState] = React.useState(() => {
    try {
      return localStorage.getItem(OPEN_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [request, setRequest] = React.useState<AssistantRequest | null>(null);
  const [data, setData] = React.useState<AssistantData>({});
  const handlers = React.useRef<AssistantHandlers>({});
  const nonce = React.useRef(0);

  const setOpen = React.useCallback((value: boolean) => {
    setOpenState(value);
    try {
      localStorage.setItem(OPEN_KEY, value ? "1" : "0");
    } catch {
      /* stockage indisponible : le tiroir reste utilisable */
    }
  }, []);

  const toggle = React.useCallback(() => setOpen(!open), [open, setOpen]);

  const ask = React.useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      nonce.current += 1;
      setRequest({ text: trimmed, nonce: nonce.current });
      setOpen(true);
    },
    [setOpen],
  );

  const publish = React.useCallback((next: AssistantData, withHandlers?: AssistantHandlers) => {
    if (withHandlers) handlers.current = withHandlers;
    setData((current) => {
      const sameProject =
        (current.project === next.project) ||
        (!current.project && !next.project);
      const unchanged =
        sameProject &&
        current.projectName === next.projectName &&
        current.mode === next.mode &&
        current.source === next.source &&
        current.selection?.sceneId === next.selection?.sceneId &&
        current.selection?.layerId === next.selection?.layerId &&
        (current.csvColumns || []).join("|") === (next.csvColumns || []).join("|");
      return unchanged ? current : { ...next };
    });
  }, []);

  const value = React.useMemo<AssistantStore>(
    () => ({ open, setOpen, toggle, request, ask, data, handlers, publish }),
    [open, setOpen, toggle, request, ask, data, publish],
  );

  return <AssistantCtx.Provider value={value}>{children}</AssistantCtx.Provider>;
}

export function useAssistant(): AssistantStore {
  const store = React.useContext(AssistantCtx);
  if (!store) throw new Error("useAssistant doit etre utilise sous AssistantProvider");
  return store;
}

/**
 * Publie le contexte lu par l'assistant. L'appel se fait dans un effet : le
 * publier pendant le rendu declencherait une boucle d'etat.
 */
export function usePublishAssistant(data: AssistantData, handlers: AssistantHandlers) {
  const { publish } = useAssistant();
  const stable = React.useMemo(
    () => ({
      project: data.project ?? null,
      projectName: data.projectName ?? "",
      mode: data.mode ?? "design",
      source: data.source ?? "",
      sceneId: data.selection?.sceneId ?? null,
      layerId: data.selection?.layerId ?? null,
      csvColumns: (data.csvColumns ?? []).join("|"),
    }),
    [
      data.project,
      data.projectName,
      data.mode,
      data.source,
      data.selection?.sceneId,
      data.selection?.layerId,
      data.csvColumns,
    ],
  );

  React.useEffect(() => {
    publish(
      {
        project: data.project ?? null,
        projectName: data.projectName ?? "",
        selection: data.selection ?? { sceneId: null, layerId: null },
        mode: data.mode ?? "design",
        csvColumns: data.csvColumns ?? [],
        source: data.source ?? "",
      },
      handlers,
    );
    // Les gestionnaires sont rafraichis a chaque rendu ; les donnees publiques
    // ne dependent que des cles comparees par `stable`.
  }, [stable, publish, handlers]);

  // En quittant la page, le contexte et les gestionnaires sont retirés : sans
  // ça, le tiroir garderait un bouton « Appliquer » pointé vers un éditeur
  // déjà démonté, dont la page ne montre plus le résultat.
  React.useEffect(() => () => publish({}, {}), [publish]);
}
