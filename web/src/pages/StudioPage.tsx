import React from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { Link, useSearchParams } from "react-router-dom";
import { Download, FilePlus2, FolderOpen, Library, Loader2, Palette, PenTool, Redo2, Save, Undo2, X } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { api, apiErrorMessage } from "../api/client";
import { COMPOSITION_INDEX, MODEL_REGISTRY } from "../remotion/registry";
import { useProject } from "../lib/project";
import { usePublishAssistant } from "../lib/assistant";
import ExportDialog from "./design/ExportDialog";
import LibraryDialog from "./design/LibraryDialog";
import BrandPacksDialog from "./design/BrandPacksDialog";

/**
 * Accueil du studio : l'aperçu vidéo et la barre projet, la conversation étant
 * le tiroir d'assistant toujours ouvert à droite. Le document et son historique
 * viennent du ProjectProvider partagé avec Design : une modification demandée
 * dans le chat est appliquée automatiquement et l'aperçu se met à jour ici.
 */
export default function StudioPage() {
  const [searchParams] = useSearchParams();
  const {
    project, name, dirty, selection, prepared, prepareError, save, notes, projectList, fontsReady,
    canUndo, canRedo, setName, setSelection, setNotes, setSave,
    applyEdit, undo, redo, openProject, openModel, newProject, saveNow, refreshProjects,
  } = useProject();

  const [showOpen, setShowOpen] = React.useState(false);
  const [showExport, setShowExport] = React.useState(false);
  const [showLibrary, setShowLibrary] = React.useState(false);
  const [showBrands, setShowBrands] = React.useState(false);

  // Le chat (tiroir global) lit ce contexte et applique ses propositions ici.
  usePublishAssistant(
    { project, projectName: name, selection, mode: "design", source: "Studio" },
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
      if (!(event.ctrlKey || event.metaKey) || typing) return;
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) {
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

  React.useEffect(() => {
    const projectName = searchParams.get("project");
    const modelId = searchParams.get("model");
    if (projectName) void openProject(String(projectName));
    else if (modelId) void openModel(String(modelId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resolved = prepared?.resolved ?? null;
  const composition = prepared?.composition ?? String((project as any)?.model?.id ?? "quote-cinematic");
  const definition = COMPOSITION_INDEX[composition] ?? MODEL_REGISTRY.quote_cinematic;

  const playerRef = React.useRef<PlayerRef>(null);
  const previewRef = React.useRef<HTMLDivElement>(null);
  const [scale, setScale] = React.useState(0.3);
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

  const errors = prepared?.errors ?? [];
  const warnings = prepared?.warnings ?? [];

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
          {dirty && <span className="text-[11px] text-warning">non enregistré</span>}
        </div>

        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={undo} disabled={!canUndo} title="Annuler (Ctrl+Z)">
            <Undo2 size={14} />
          </Button>
          <Button variant="ghost" size="sm" onClick={redo} disabled={!canRedo} title="Rétablir (Ctrl+Maj+Z)">
            <Redo2 size={14} />
          </Button>
        </div>

        <div className="ml-auto flex items-center gap-2">
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
            title="Enregistrer ce projet comme modèle réutilisable"
          >
            <Library size={14} />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowBrands(true)}
            disabled={!project}
            title="Packs de marque client (logo, couleurs, signature, musique)"
          >
            <Palette size={14} />
          </Button>
          <Link
            to="/design"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-input px-2.5 text-xs font-medium hover:bg-accent hover:text-accent-foreground"
            title="Éditeur avancé : scènes, calques, inspecteur"
          >
            <PenTool size={14} /> Éditeur
          </Link>
          <Button
            size="sm"
            onClick={() => setShowExport(true)}
            disabled={errors.length > 0 || !prepared || !fontsReady}
            title={errors.length > 0 ? "Corrigez les erreurs du projet avant l'export" : !fontsReady ? "Chargement des polices…" : undefined}
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
        <span className="font-mono text-[11px] text-muted-foreground">
          {resolved ? `${resolved.width}×${resolved.height} · ${resolved.fps} fps · ${resolved.duration}s` : "—"}
        </span>
      </header>

      {notes.length > 0 && (
        <div className="flex items-start gap-2 border-b border-border bg-warning/10 px-3 py-2">
          <div className="text-[11px] leading-relaxed">
            <strong>Conversion v1 → v2 :</strong>
            {notes.map((note, index) => (
              <div key={index}>· {note}</div>
            ))}
          </div>
          <button className="ml-auto text-muted-foreground hover:text-foreground" onClick={() => setNotes([])} aria-label="Masquer les notes">
            <X size={14} />
          </button>
        </div>
      )}

      <div ref={previewRef} className="flex min-h-0 flex-1 items-center justify-center bg-black/40 p-4">
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
              loop
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
                <Loader2 size={14} className="animate-spin" /> Préparation de l'aperçu…
              </span>
            )}
          </div>
        )}
      </div>
      <div className="border-t border-border px-4 py-1.5 text-center text-[11px] text-muted-foreground">
        Demandez une modification dans la conversation à droite : elle est appliquée automatiquement et cet aperçu se met à jour.
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
        <BrandPacksDialog project={project} onClose={() => setShowBrands(false)} onApply={(patched) => applyEdit(patched, true)} />
      )}
    </div>
  );
}