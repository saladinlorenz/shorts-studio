/**
 * État du projet actif, partagé par tout le studio.
 *
 * La page d'accueil (chat + vidéo) et la page Design lisent le même projet :
 * une modification demandée dans la conversation est visible des deux côtés,
 * et l'historique Annuler/Rétablir est unique. Les pages ne possèdent plus leur
 * copie du document — elles publient seulement ce que l'assistant doit lire.
 */
import React from "react";
import { api, apiErrorMessage, type PrepareResponse, type Project } from "../api/client";
import { injectFontFaces, preloadAllFonts } from "../remotion/fonts";
import * as edit from "../pages/design/edit";

export type SaveState = { kind: "idle" | "saving" | "saved" | "error"; msg: string };

const HISTORY_LIMIT = 80;

export type ProjectStore = {
  project: Project | null;
  name: string;
  dirty: boolean;
  selection: edit.Selection;
  prepared: PrepareResponse | null;
  prepareError: string;
  save: SaveState;
  notes: string[];
  projectList: Array<{ name: string; version: number | null }>;
  fontsReady: boolean;
  canUndo: boolean;
  canRedo: boolean;
  setName: (value: string) => void;
  setSelection: (value: edit.Selection) => void;
  setNotes: (value: string[]) => void;
  setSave: (value: SaveState) => void;
  applyEdit: (next: Project, commit: boolean) => void;
  undo: () => void;
  redo: () => void;
  openProject: (projectName: string) => Promise<void>;
  openModel: (modelId: string) => Promise<void>;
  newProject: () => Promise<void>;
  saveNow: () => Promise<void>;
  refreshProjects: () => void;
};

const ProjectCtx = React.createContext<ProjectStore | null>(null);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [project, setProject] = React.useState<Project | null>(null);
  const [name, setName] = React.useState("citation");
  const [dirty, setDirty] = React.useState(false);
  const [selection, setSelection] = React.useState<edit.Selection>({ sceneId: null, layerId: null });
  const [prepared, setPrepared] = React.useState<PrepareResponse | null>(null);
  const [prepareError, setPrepareError] = React.useState("");
  const [fontsReady, setFontsReady] = React.useState(false);
  const [save, setSave] = React.useState<SaveState>({ kind: "idle", msg: "" });
  const [notes, setNotes] = React.useState<string[]>([]);
  const [projectList, setProjectList] = React.useState<Array<{ name: string; version: number | null }>>([]);

  /* ---------------- historique annulation / rétablissement ---------------- */

  const past = React.useRef<Project[]>([]);
  const future = React.useRef<Project[]>([]);
  const gesture = React.useRef(false);
  const gestureTimer = React.useRef(0);
  const present = React.useRef<Project | null>(null);
  present.current = project;
  const [, bumpHistory] = React.useReducer((n: number) => n + 1, 0);

  const applyEdit = React.useCallback((next: Project, commit: boolean) => {
    const previous = present.current;
    if (previous) {
      const startGesture = !commit && !gesture.current;
      if (commit || startGesture) {
        past.current = [...past.current.slice(-(HISTORY_LIMIT - 1)), previous];
        future.current = [];
      }
      gesture.current = commit ? false : true;
      window.clearTimeout(gestureTimer.current);
      if (!commit) {
        // Un glissement (slider) trop long devient plusieurs moves d'un même geste.
        gestureTimer.current = window.setTimeout(() => {
          gesture.current = false;
        }, 800);
      }
    }
    setProject(next);
    setDirty(true);
    bumpHistory();
  }, []);

  const undo = React.useCallback(() => {
    const previous = past.current.pop();
    const current = present.current;
    if (!previous || !current) return;
    future.current = [...future.current, current];
    gesture.current = false;
    setProject(previous);
    setDirty(true);
    bumpHistory();
  }, []);

  const redo = React.useCallback(() => {
    const next = future.current.pop();
    const current = present.current;
    if (!next || !current) return;
    past.current = [...past.current, current];
    gesture.current = false;
    setProject(next);
    setDirty(true);
    bumpHistory();
  }, []);

  /* ------------------------- polices du catalogue ------------------------- */

  React.useEffect(() => {
    injectFontFaces();
    let alive = true;
    preloadAllFonts()
      .then(() => alive && setFontsReady(true))
      .catch(() => alive && setFontsReady(false));
    return () => {
      alive = false;
    };
  }, []);

  /* --------------------- projet par défaut au démarrage ------------------- */

  React.useEffect(() => {
    if (project) return;
    api
      .studioDefault("quote_cinematic")
      .then((res) => {
        setProject(res.project);
        const first = res.project?.content?.scenes?.[0];
        if (first) setSelection({ sceneId: first.id, layerId: first.layers?.[0]?.id ?? null });
      })
      .catch((e) => setPrepareError(apiErrorMessage(e)));
  }, [project]);

  const refreshProjects = React.useCallback(() => {
    api
      .listProjects()
      .then((items) => setProjectList(items.map((i) => ({ name: i.name, version: i.version }))))
      .catch(() => setProjectList([]));
  }, []);

  /* ------------------- préparation serveur (résolu + validé) ------------------ */

  React.useEffect(() => {
    if (!project) return;
    let alive = true;
    const handle = window.setTimeout(() => {
      api
        .studioPrepare(project)
        .then((res) => {
          if (!alive) return;
          setPrepared(res);
          setPrepareError("");
        })
        .catch((e) => {
          if (!alive) return;
          setPrepareError(apiErrorMessage(e));
        });
    }, 220);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [project]);

  /* ----------------------------- sauvegarde auto ---------------------------- */

  React.useEffect(() => {
    if (!dirty || !project || !name.trim()) return;
    const handle = window.setTimeout(() => {
      setSave({ kind: "saving", msg: "Enregistrement automatique…" });
      api
        .saveProject(name.trim(), project)
        .then(() => {
          setDirty(false);
          setSave({ kind: "saved", msg: `Enregistré : ${name.trim()}.json` });
        })
        .catch((e) => setSave({ kind: "error", msg: apiErrorMessage(e) }));
    }, 1400);
    return () => window.clearTimeout(handle);
  }, [dirty, project, name]);

  /* ------------------------------ sélection ------------------------------ */

  React.useEffect(() => {
    if (!project) return;
    const scenes = edit.scenes(project);
    if (scenes.length === 0) return;
    const sceneStillThere = scenes.some((s: any) => s.id === selection.sceneId);
    if (!sceneStillThere) {
      const first = scenes[0];
      setSelection({ sceneId: first.id, layerId: first.layers?.[0]?.id ?? null });
      return;
    }
    const layerStillThere = edit.layersOf(project, selection.sceneId).some((l: any) => l.id === selection.layerId);
    if (!layerStillThere) {
      const layers = edit.layersOf(project, selection.sceneId);
      setSelection({ sceneId: selection.sceneId, layerId: layers[0]?.id ?? null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  /* --------------------------- ouverture / création -------------------------- */

  const openProject = React.useCallback(async (projectName: string) => {
    try {
      const res = await api.loadProject(projectName);
      const version = (res.project as any)?.version;
      if (version === 1) {
        const upgraded = await api.studioUpgrade(res.project);
        setProject(upgraded.project);
        setName(`${res.name}_v2`);
        setNotes(upgraded.notes);
        const first = upgraded.project?.content?.scenes?.[0];
        if (first) setSelection({ sceneId: first.id, layerId: first.layers?.[0]?.id ?? null });
      } else {
        setProject(res.project);
        setName(res.name);
        setNotes([]);
        const first = (res.project as any)?.content?.scenes?.[0];
        if (first) setSelection({ sceneId: first.id, layerId: first.layers?.[0]?.id ?? null });
      }
      past.current = [];
      future.current = [];
      setDirty(false);
      bumpHistory();
      setSave({ kind: "saved", msg: `Projet « ${res.name} » ouvert.` });
    } catch (e) {
      setSave({ kind: "error", msg: apiErrorMessage(e) });
    }
  }, []);

  const openModel = React.useCallback(async (modelId: string) => {
    try {
      const res = await api.libraryModel(modelId);
      setProject(res.project);
      setName(String((res.project as any).label || res.id).toLowerCase().replace(/\s+/g, "-"));
      setNotes([]);
      past.current = [];
      future.current = [];
      setDirty(false);
      const first = (res.project as any)?.content?.scenes?.[0];
      if (first) setSelection({ sceneId: first.id, layerId: first.layers?.[0]?.id ?? null });
      bumpHistory();
      setSave({ kind: "saved", msg: `Modèle « ${modelId} » chargé : vos réglages créeront un nouveau projet.` });
    } catch (e) {
      setSave({ kind: "error", msg: apiErrorMessage(e) });
    }
  }, []);

  const newProject = React.useCallback(async () => {
    try {
      const res = await api.studioDefault("quote_cinematic");
      setProject(res.project);
      past.current = [];
      future.current = [];
      setDirty(false);
      setNotes([]);
      const first = res.project?.content?.scenes?.[0];
      if (first) setSelection({ sceneId: first.id, layerId: first.layers?.[0]?.id ?? null });
      bumpHistory();
    } catch (e) {
      setSave({ kind: "error", msg: apiErrorMessage(e) });
    }
  }, []);

  const saveNow = React.useCallback(async () => {
    if (!present.current) return;
    setSave({ kind: "saving", msg: "Enregistrement…" });
    try {
      await api.saveProject(name.trim() || "citation", present.current);
      setDirty(false);
      setSave({ kind: "saved", msg: `Enregistré : ${name.trim() || "citation"}.json` });
      refreshProjects();
    } catch (e) {
      setSave({ kind: "error", msg: apiErrorMessage(e) });
    }
  }, [name, refreshProjects]);

  const value = React.useMemo<ProjectStore>(
    () => ({
      project, name, dirty, selection, prepared, prepareError, save, notes, projectList, fontsReady,
      canUndo: past.current.length > 0,
      canRedo: future.current.length > 0,
      setName, setSelection, setNotes, setSave,
      applyEdit, undo, redo, openProject, openModel, newProject, saveNow, refreshProjects,
    }),
    [project, name, dirty, selection, prepared, prepareError, save, notes, projectList, fontsReady,
      applyEdit, undo, redo, openProject, openModel, newProject, saveNow, refreshProjects],
  );

  return <ProjectCtx.Provider value={value}>{children}</ProjectCtx.Provider>;
}

export function useProject(): ProjectStore {
  const store = React.useContext(ProjectCtx);
  if (!store) throw new Error("useProject doit être utilisé sous ProjectProvider");
  return store;
}