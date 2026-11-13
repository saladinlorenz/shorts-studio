import React from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { useSearchParams } from "react-router-dom";
import { Download, FilePlus2, FolderOpen, Library, Loader2, Palette, Redo2, Save, Sparkles, Undo2, X } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api, apiErrorMessage, type EffectsManifest, type ModelInfo } from "../api/client";
import { COMPOSITION_INDEX, MODEL_REGISTRY } from "../remotion/registry";
import * as edit from "./design/edit";
import { measureProject, type TextFit } from "./design/measure";
import { InspectorPanel, ScenesPanel, TimelineBar } from "./design/panels";
import ExportDialog from "./design/ExportDialog";
import LibraryDialog from "./design/LibraryDialog";
import BrandPacksDialog from "./design/BrandPacksDialog";
import { useAssistant, usePublishAssistant } from "../lib/assistant";
import { useProject } from "../lib/project";

/**
 * Espace Design d'un projet v2 — l'éditeur avancé.
 *
 * Le document et son historique vivent dans le ProjectProvider partagé avec la
 * page d'accueil ; cette page ajoute les panneaux scènes/inspecteur, la mesure
 * des débordements et le lecteur. Elle envoie le projet édité au serveur, reçoit
 * le projet résolu (frames absolues, URLs de rendu, polices vérifiées) et le
 * donne tel quel au Remotion Player — le même objet que celui du rendu MP4.
 */

export default function DesignPage() {
  const [searchParams] = useSearchParams();
  const {
    project, name, dirty, selection, prepared, prepareError, save, notes, projectList, fontsReady,
    canUndo, canRedo, setName, setSelection, setNotes, setSave,
    applyEdit, undo, redo, openProject, openModel, newProject, saveNow, refreshProjects,
  } = useProject();

  const [model, setModel] = React.useState<ModelInfo | null>(null);
  const [effectCatalog, setEffectCatalog] = React.useState<EffectsManifest | null>(null);
  const [fits, setFits] = React.useState<TextFit[]>([]);
  const [showOpen, setShowOpen] = React.useState(false);
  const [showExport, setShowExport] = React.useState(false);
  const [showLibrary, setShowLibrary] = React.useState(false);
  const [showBrands, setShowBrands] = React.useState(false);

  const playerRef = React.useRef<PlayerRef>(null);
  const [playing, setPlaying] = React.useState(false);
  const [loop, setLoop] = React.useState(true);
  const [frame, setFrame] = React.useState(0);

  /* --------------------- assistant : contexte publié par la page --------------------- */

  const { setOpen: showAssistant } = useAssistant();

  usePublishAssistant(
    { project, projectName: name, selection, mode: "design", source: "Design" },
    {
      onApply: (candidate) => applyEdit(candidate, true),
      onUndo: undo,
      onRedo: redo,
      onLibrarySave: (candidate, label, description) => {
        api
          .saveLibraryModel(candidate, label, description)
          .then(() => setSave({ kind: "saved", msg: `Modèle ajouté : ${label}.` }))
          .catch((e) => setSave({ kind: "error", msg: apiErrorMessage(e) }));
      },
      notify: (msg, kind) =>
        setSave({ kind: kind === "error" ? "error" : kind === "info" ? "idle" : "saved", msg }),
    },
  );

  React.useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey && !typing) {
        event.preventDefault();
        undo();
      } else if ((key === "z" && event.shiftKey) || key === "y") {
        event.preventDefault();
        redo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  /* --------------------- modèle et catalogue d'effets --------------------- */

  React.useEffect(() => {
    api
      .studioModels()
      .then((res) => setModel(res.models.find((m) => m.id === res.default) ?? res.models[0] ?? null))
      .catch(() => setModel(null));
  }, []);

  // Le catalogue d'effets vient du serveur : l'inspecteur ne propose que ce qui
  // est réellement implémenté au rendu, avec ses bornes.
  React.useEffect(() => {
    api
      .studioEffects()
      .then(setEffectCatalog)
      .catch(() => setEffectCatalog(null));
  }, []);

  /* ------------------------ mesure des débordements ------------------------ */

  React.useEffect(() => {
    if (!prepared || !fontsReady) return;
    const handle = window.setTimeout(() => {
      try {
        setFits(measureProject(prepared.project, prepared.resolved));
      } catch {
        setFits([]);
      }
    }, 80);
    return () => window.clearTimeout(handle);
  }, [prepared, fontsReady]);

  /* --------------------------- ouverture depuis l'URL -------------------------- */

  React.useEffect(() => {
    const projectName = searchParams.get("project");
    const modelId = searchParams.get("model");
    if (projectName) void openProject(String(projectName));
    else if (modelId) void openModel(String(modelId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ------------------------------- player ------------------------------- */

  const resolved = prepared?.resolved ?? null;
  const composition = prepared?.composition ?? String((project as any)?.model?.id ?? "quote-cinematic");
  const definition = COMPOSITION_INDEX[composition] ?? MODEL_REGISTRY.quote_cinematic;

  React.useEffect(() => {
    const ref = playerRef.current;
    if (!ref) return;
    const onFrame = (event: { detail: { frame: number } }) => setFrame(event.detail.frame);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    ref.addEventListener("frameupdate", onFrame as any);
    ref.addEventListener("play", onPlay);
    ref.addEventListener("pause", onPause);
    return () => {
      ref.removeEventListener("frameupdate", onFrame as any);
      ref.removeEventListener("play", onPlay);
      ref.removeEventListener("pause", onPause);
    };
  }, [prepared]);

  const previewRef = React.useRef<HTMLDivElement>(null);
  const [scale, setScale] = React.useState(0.22);
  React.useEffect(() => {
    const el = previewRef.current;
    if (!el || !resolved) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setScale(Math.min(rect.width / resolved.width, rect.height / resolved.height));
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [resolved]);

  /* ------------------------------- handlers ------------------------------ */

  const onScene = (sceneId: string, patch: Record<string, unknown>, commit = true) => {
    if (!project) return;
    applyEdit(edit.updateScene(project, sceneId, patch), commit);
  };

  const onLayer = (sceneId: string, layerId: string, patch: Record<string, unknown>, commit = true) => {
    if (!project) return;
    applyEdit(edit.updateLayer(project, sceneId, layerId, patch), commit);
  };

  const onAllScenes = (patch: Record<string, unknown>) => {
    if (!project) return;
    applyEdit(edit.updateAllScenes(project, patch), true);
  };

  const onStyle = (part: "style" | "position" | "animation", patch: Record<string, unknown>, commit = true) => {
    if (!project || !selection.sceneId || !selection.layerId) return;
    applyEdit(edit.updateLayerPart(project, selection.sceneId, selection.layerId, part, patch), commit);
  };

  const onTheme = (patch: Record<string, unknown>, commit = true) => {
    if (!project) return;
    applyEdit(edit.updateTheme(project, patch), commit);
  };

  const onSignature = (patch: Record<string, unknown>, commit = true) => {
    if (!project) return;
    applyEdit(edit.updateSignature(project, patch), commit);
  };

  const onExportSettings = (patch: Record<string, unknown>, commit = true) => {
    if (!project) return;
    applyEdit(edit.updateExport(project, patch), commit);
  };

  const onVariation = (patch: Record<string, unknown>, commit = true) => {
    if (!project) return;
    applyEdit(edit.updateVariation(project, patch), commit);
  };

  const onAudio = (patch: Record<string, unknown>, commit = true) => {
    if (!project) return;
    applyEdit(edit.updateAudio(project, patch), commit);
  };

  const onMedia = (
    target: { sceneId: string; layerId?: string; slot: "background" | "layer" | "signature" },
    media: string,
  ) => {
    if (!project) return;
    let next = project;
    if (target.slot === "background") {
      const scene = edit.sceneById(next, target.sceneId);
      next = edit.updateScene(next, target.sceneId, { background: { ...(scene?.background ?? {}), media } });
    } else if (target.slot === "layer" && target.layerId) {
      next = edit.updateLayer(next, target.sceneId, target.layerId, { media });
    } else {
      next = edit.updateSignature(next, { media });
    }
    applyEdit(next, true);
  };

  const errors = prepared?.errors ?? [];
  const warnings = prepared?.warnings ?? [];
  const sceneMarks = (resolved?.scenes ?? []).map((scene: any) => ({
    id: scene.id,
    label: scene.label ?? scene.id,
    startFrame: scene.start_frame,
    durationFrames: scene.duration_frames,
  }));

  /* --------------------------------- rendu -------------------------------- */

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-border bg-card/40 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="field-label">Projet</span>
          <input
            className="input-base h-8 w-44"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => refreshProjects()}
            placeholder="nom du projet"
            aria-label="nom du projet"
          />
          {dirty && <span className="text-[11px] text-warning">modifications non enregistrées</span>}
        </div>

        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={undo} disabled={!canUndo} title="Annuler (Ctrl+Z)">
            <Undo2 size={14} /> Annuler
          </Button>
          <Button variant="ghost" size="sm" onClick={redo} disabled={!canRedo} title="Rétablir (Ctrl+Maj+Z)">
            <Redo2 size={14} /> Rétablir
          </Button>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => showAssistant(true)}
            title="Ouvrir l'assistant (Ctrl+I)"
          >
            <Sparkles size={14} /> Assistant
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void newProject()}>
            <FilePlus2 size={14} /> Nouveau
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setShowOpen(true);
              refreshProjects();
            }}
          >
            <FolderOpen size={14} /> Ouvrir
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void saveNow()} disabled={save.kind === "saving"}>
            {save.kind === "saving" ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Sauvegarder
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowLibrary(true)}
            disabled={!project || errors.length > 0}
            title={
              errors.length > 0
                ? "Le projet doit être valide pour devenir un modèle"
                : "Enregistrer ce projet comme modèle réutilisable (dossier models/)"
            }
          >
            <Library size={14} /> Bibliothèque
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowBrands(true)}
            disabled={!project}
            title="Packs de marque client (logo, couleurs, signature, musique)"
          >
            <Palette size={14} /> Packs
          </Button>
          <Button
            size="sm"
            onClick={() => setShowExport(true)}
            disabled={errors.length > 0 || !prepared || !fontsReady}
            title={
              errors.length > 0
                ? "Corrigez les erreurs du projet avant l'export"
                : !fontsReady
                  ? "Chargement des polices en cours"
                  : undefined
            }
          >
            <Download size={14} /> Exporter
          </Button>
        </div>

        {save.msg && (
          <span
            className={
              "max-w-[260px] truncate text-[11px] " +
              (save.kind === "error" ? "text-destructive" : save.kind === "saved" ? "text-success" : "text-muted-foreground")
            }
            title={save.msg}
          >
            {save.msg}
          </span>
        )}
        {errors.length > 0 && <Badge variant="destructive">{errors.length} erreur(s)</Badge>}
        {errors.length === 0 && warnings.length > 0 && <Badge variant="warning">{warnings.length} avertissement(s)</Badge>}
        {!fontsReady && <Badge variant="outline">polices…</Badge>}
        <span className="font-mono text-[11px] text-muted-foreground">
          {resolved ? `${resolved.width}×${resolved.height} · ${resolved.fps} fps · ${resolved.total_frames} f · ${resolved.duration}s` : "—"}
        </span>
      </header>

      {notes.length > 0 && (
        <div className="flex items-start gap-2 border-b border-border bg-warning/10 px-3 py-2">
          <div className="text-[11px] leading-relaxed">
            <strong>Conversion v1 → v2 :</strong>
            {notes.map((note, index) => (
              <div key={index}>· {note}</div>
            ))}
            <div className="text-muted-foreground">
              Le fichier d'origine n'a pas été modifié : l'enregistrement se fera sous « {name} ».
            </div>
          </div>
          <button className="ml-auto text-muted-foreground hover:text-foreground" onClick={() => setNotes([])} aria-label="Masquer les notes">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Les colonnes fixes ont un plancher et un plafond : l'aperçu garde de
          l'air quand le tiroir d'assistant s'ouvre ou que la fenêtre est étroite. */}
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(215px,250px)_minmax(0,1fr)_minmax(255px,300px)] xl:grid-cols-[minmax(250px,290px)_minmax(0,1fr)_minmax(280px,330px)]">
        <section className="min-h-0 border-r border-border p-3">
          {project && (
            <ScenesPanel
              model={model}
              project={project}
              selection={selection}
              onSelect={setSelection}
              onScene={onScene}
              onLayer={onLayer}
              onAddScene={() => {
                if (!project) return;
                const next = edit.addScene(project);
                applyEdit(next, true);
              }}
              onDuplicateScene={(sceneId) => project && applyEdit(edit.duplicateScene(project, sceneId), true)}
              onRemoveScene={(sceneId) => project && applyEdit(edit.removeScene(project, sceneId), true)}
              onMoveScene={(sceneId, delta) => project && applyEdit(edit.moveScene(project, sceneId, delta), true)}
              onAddLayer={(sceneId, type) => project && applyEdit(edit.addLayer(project, sceneId, type), true)}
              onRemoveLayer={(sceneId, layerId) => project && applyEdit(edit.removeLayer(project, sceneId, layerId), true)}
              onMoveLayer={(sceneId, layerId, delta) => project && applyEdit(edit.moveLayer(project, sceneId, layerId, delta), true)}
              onToggleLayer={(sceneId, layerId, key) => project && applyEdit(edit.toggleLayer(project, sceneId, layerId, key), true)}
              onMedia={onMedia}
              fontsReady={fontsReady}
            />
          )}
        </section>

        <section className="flex min-h-0 flex-col">
          <div ref={previewRef} className="flex min-h-0 flex-1 items-center justify-center bg-black/40 p-3">
            {resolved && fontsReady && prepared ? (
              <div
                style={{ width: resolved.width * scale, height: resolved.height * scale }}
                className="overflow-hidden rounded-md border border-border shadow-xl"
              >
                <Player
                  ref={playerRef}
                  component={definition.component as any}
                  inputProps={{ project: prepared.project }}
                  compositionWidth={resolved.width}
                  compositionHeight={resolved.height}
                  fps={resolved.fps}
                  durationInFrames={Math.max(1, resolved.total_frames)}
                  controls
                  loop={loop}
                  // Licence Remotion : « For individuals and companies of up to 3
                  // people — Free License — Unlimited commercial use ». Le studio est
                  // exploité dans ce cadre, donc l'avertissement est reconnu plutôt que
                  // laissé à chaque ouverture d'aperçu.
                  acknowledgeRemotionLicense
                  style={{ width: "100%", height: "100%" }}
                />
              </div>
            ) : (
              <div className="max-w-md p-4 text-center text-sm text-muted-foreground">
                {prepareError ? (
                  <span className="text-destructive">{prepareError}</span>
                ) : (
                  <span className="flex items-center gap-2">
                    <Loader2 size={14} className="animate-spin" /> Préparation du projet résolu…
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="border-t border-border px-4 py-1.5 text-center text-[11px] text-muted-foreground">
            Aperçu Remotion Player avec le projet résolu par le serveur — même objet que celui du rendu MP4.
            {!fontsReady && " Polices en cours de chargement : aucune mesure ni rendu avant leur disponibilité."}
          </div>
          {project && (
            <TimelineBar
              project={project}
              resolved={resolved}
              frame={frame}
              playing={playing}
              loop={loop}
              errors={errors}
              sceneMarks={sceneMarks}
              onSeek={(nextFrame) => playerRef.current?.seekTo(nextFrame)}
              onTogglePlay={() => {
                const ref = playerRef.current;
                if (!ref) return;
                if (ref.isPlaying()) ref.pause();
                else ref.play();
              }}
              onToggleLoop={() => setLoop((value) => !value)}
            />
          )}
        </section>

        <section className="flex min-h-0 flex-col border-l border-border p-3">
          <div className="min-h-0 flex-1 overflow-hidden">
            {project && resolved ? (
              <InspectorPanel
                project={project}
                selection={selection}
                fits={fits}
                errors={errors}
                warnings={warnings}
                resolved={resolved}
                effects={effectCatalog}
                audioReady={Boolean(project.audio?.enabled && (project.audio?.music || project.audio?.voice))}
                onScene={onScene}
                onLayer={onLayer}
                onAllScenes={onAllScenes}
                onStyle={onStyle}
                onTheme={onTheme}
                onSignature={onSignature}
                onExport={onExportSettings}
                onVariation={onVariation}
                onAudio={onAudio}
              />
            ) : (
              <p className="text-xs text-muted-foreground">
                Les réglages du projet apparaissent ici dès que l'aperçu est prêt.
              </p>
            )}
          </div>
        </section>
      </div>

      {showOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowOpen(false)}>
          <div className="panel w-full max-w-md p-4" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Ouvrir un projet</h2>
              <button className="text-muted-foreground hover:text-foreground" onClick={() => setShowOpen(false)} aria-label="Fermer">
                <X size={16} />
              </button>
            </div>
            <p className="mb-2 text-[11px] text-muted-foreground">
              Les projets v1 sont convertis explicitement en v2, avec la liste des changements. Le fichier
              d'origine reste intact jusqu'à un enregistrement volontaire.
            </p>
            <div className="grid max-h-[50vh] gap-1 overflow-y-auto">
              {projectList.length === 0 && <p className="text-xs text-muted-foreground">Aucun projet enregistré.</p>}
              {projectList.map((item) => (
                <button
                  key={item.name}
                  className="flex items-center justify-between rounded-md border border-border px-2.5 py-1.5 text-left text-sm hover:bg-accent/60"
                  onClick={() => void openProject(item.name).then(() => setShowOpen(false))}
                >
                  <span className="truncate">{item.name}</span>
                  <Badge variant={item.version === 2 ? "success" : item.version === 1 ? "warning" : "outline"}>
                    v{item.version ?? "?"}
                  </Badge>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {showExport && project && (
        <ExportDialog project={project} defaultName={name} onClose={() => setShowExport(false)} />
      )}

      {showLibrary && project && (
        <LibraryDialog
          project={project}
          defaultLabel={name.trim() || "mon modele"}
          onClose={() => setShowLibrary(false)}
          onSaved={(modelId) => {
            setShowLibrary(false);
            setSave({ kind: "saved", msg: `Modèle ajouté à la bibliothèque : ${modelId}.` });
          }}
        />
      )}

      {showBrands && project && (
        <BrandPacksDialog
          project={project}
          onClose={() => setShowBrands(false)}
          onApply={(patched) => applyEdit(patched, true)}
        />
      )}
    </div>
  );
}
