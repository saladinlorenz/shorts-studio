import React from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { useSearchParams } from "react-router-dom";
import {
  Save,
  FolderOpen,
  Download,
  Upload,
  X,
  Play,
  AlertTriangle,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { api, mediaUrl, type JobSnapshot } from "../api/client";
import {
  QuoteVertical,
  defaultQuoteProject,
  projectDims,
  type QuoteProject,
} from "../remotion/QuoteVertical";
import { Button } from "../components/ui/button";
import { Input, Textarea } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Slider } from "../components/ui/slider";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Progress } from "../components/ui/progress";

const FONTS = [
  { value: "arialbd.ttf", label: "Arial Bold" },
  { value: "arial.ttf", label: "Arial" },
  { value: "impact.ttf", label: "Impact" },
  { value: "georgia.ttf", label: "Georgia" },
  { value: "times.ttf", label: "Times New Roman" },
  { value: "segoeui.ttf", label: "Segoe UI" },
  { value: "verdana.ttf", label: "Verdana" },
  { value: "calibrib.ttf", label: "Calibri Bold" },
];

type SaveState = { kind: "idle" | "saving" | "saved" | "error"; msg: string };

export default function ShortVideosPage() {
  const [searchParams] = useSearchParams();

  const [project, setProject] = React.useState<QuoteProject>(() => defaultQuoteProject());
  const [name, setName] = React.useState("citation");
  const [dirty, setDirty] = React.useState(false);
  const [validation, setValidation] = React.useState<{ errors: string[]; warnings: string[] }>({
    errors: [],
    warnings: [],
  });
  const [save, setSave] = React.useState<SaveState>({ kind: "idle", msg: "" });
  const [projects, setProjects] = React.useState<string[]>([]);
  const [showOpen, setShowOpen] = React.useState(false);

  // Export
  const [showExport, setShowExport] = React.useState(false);
  const [exportName, setExportName] = React.useState("citation");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [job, setJob] = React.useState<JobSnapshot | null>(null);
  const [exportError, setExportError] = React.useState("");
  const [needsOverwrite, setNeedsOverwrite] = React.useState(false);

  const playerRef = React.useRef<PlayerRef>(null);
  const [playing, setPlaying] = React.useState(false);
  const [frame, setFrame] = React.useState(0);

  const dims = projectDims(project);
  const hasErrors = validation.errors.length > 0;

  const update = React.useCallback((mutator: (p: QuoteProject) => void) => {
    setProject((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as QuoteProject;
      mutator(next);
      return next;
    });
    setDirty(true);
  }, []);

  // --- Validation côté serveur (logique métier Python, pas de doublon client) ---
  React.useEffect(() => {
    const handle = window.setTimeout(() => {
      api
        .validateProject(project)
        .then(setValidation)
        .catch((e) => setValidation({ errors: [String(e)], warnings: [] }));
    }, 400);
    return () => window.clearTimeout(handle);
  }, [project]);

  // --- Ouverture via ?project= (depuis la page Projets) ---
  React.useEffect(() => {
    const q = searchParams.get("project");
    if (q) void openProject(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshList = React.useCallback(async () => {
    try {
      const items = await api.listProjects();
      setProjects(items.map((i) => i.name));
    } catch {
      /* liste indisponible : non bloquant */
    }
  }, []);

  React.useEffect(() => {
    void refreshList();
  }, [refreshList]);

  async function openProject(projectName: string) {
    try {
      const res = await api.loadProject(projectName);
      setProject(res.project as QuoteProject);
      setName(res.name);
      setExportName(res.name);
      setDirty(false);
      setSave({
        kind: "saved",
        msg:
          res.migrated_media.length > 0
            ? `Ouvert · médias réimportés : ${res.migrated_media.join(", ")}`
            : `Projet « ${res.name} » ouvert.`,
      });
      setShowOpen(false);
    } catch (e) {
      setSave({ kind: "error", msg: String(e) });
    }
  }

  async function saveProject() {
    setSave({ kind: "saving", msg: "Enregistrement…" });
    try {
      await api.saveProject(name, project as Record<string, any>);
      setDirty(false);
      setSave({ kind: "saved", msg: `Enregistré : ${name}.json` });
      void refreshList();
    } catch (e) {
      setSave({ kind: "error", msg: String(e) });
    }
  }

  // --- Export (polling du job) ---
  React.useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const snap = await api.exportStatus(jobId);
        if (stopped) return;
        setJob(snap);
        if (snap.status !== "running") setJobId(null);
      } catch (e) {
        if (!stopped) {
          setExportError(String(e));
          setJobId(null);
        }
      }
    };
    void tick();
    const interval = window.setInterval(tick, 500);
    return () => {
      stopped = true;
      window.clearInterval(interval);
    };
  }, [jobId]);

  async function startExport(overwrite: boolean) {
    setExportError("");
    setNeedsOverwrite(false);
    setJob(null);
    try {
      const res = await api.startExport(exportName, project as Record<string, any>, overwrite);
      setJobId(res.job_id);
    } catch (e: any) {
      if (e?.status === 409) {
        setNeedsOverwrite(true);
        setExportError(e.message);
      } else {
        setExportError(String(e?.message ?? e));
      }
    }
  }

  async function cancelExport() {
    if (!jobId) return;
    try {
      await api.cancelExport(jobId);
    } catch (e) {
      setExportError(String(e));
    }
  }

  // --- Médias ---
  async function uploadMedia(field: "background_image" | "logo", file: File | null) {
    if (!file) return;
    try {
      const res = await api.uploadMedia(file);
      update((p) => {
        p.content[field] = `media://${res.id}`;
      });
    } catch (e) {
      setSave({ kind: "error", msg: `Import impossible : ${e}` });
    }
  }

  // --- Aperçu échelle ---
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [scale, setScale] = React.useState(0.25);
  React.useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setScale(Math.min(rect.width / dims.width, rect.height / dims.height));
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [dims.width, dims.height]);

  React.useEffect(() => {
    const ref = playerRef.current;
    if (!ref) return;
    const onFrame = (e: { detail: { frame: number } }) => setFrame(e.detail.frame);
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
  }, []);

  const bgUrl = mediaUrl(project.content.background_image);
  const logoUrl = mediaUrl(project.content.logo);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ---------- BARRE HAUTE : nom + sauvegarde + export ---------- */}
      <header className="flex items-center gap-3 border-b border-border bg-card/40 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Label htmlFor="project-name" className="mr-1">
            Projet
          </Label>
          <Input
            id="project-name"
            className="h-8 w-48"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="nom du projet"
          />
          {dirty && <span className="text-[11px] text-warning">modifié</span>}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { setShowOpen(true); void refreshList(); }}>
            <FolderOpen size={14} /> Ouvrir
          </Button>
          <Button variant="secondary" size="sm" onClick={saveProject} disabled={save.kind === "saving"}>
            {save.kind === "saving" ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Sauvegarder
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={() => {
              setShowExport(true);
              setExportError("");
              setJob(null);
              setNeedsOverwrite(false);
            }}
            disabled={hasErrors}
            title={hasErrors ? "Corrigez les erreurs du projet avant l'export" : undefined}
          >
            <Download size={14} /> Exporter
          </Button>
        </div>

        {save.msg && (
          <span
            className={
              "max-w-[320px] truncate text-xs " +
              (save.kind === "error"
                ? "text-destructive"
                : save.kind === "saved"
                  ? "text-success"
                  : "text-muted-foreground")
            }
            title={save.msg}
          >
            {save.msg}
          </span>
        )}
        {hasErrors && (
          <Badge variant="destructive">{validation.errors.length} erreur(s)</Badge>
        )}
        {!hasErrors && validation.warnings.length > 0 && (
          <Badge variant="warning">{validation.warnings.length} avertissement(s)</Badge>
        )}
      </header>

      {/* ---------- 3 PANNEAUX ---------- */}
      <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_300px]">
        {/* ---- GAUCHE : contenu / médias / modèle ---- */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto border-r border-border p-3">
          <div className="panel p-3">
            <div className="panel-title">Modèle</div>
            <div className="mt-2 flex items-center justify-between rounded-md border border-primary/50 bg-primary/10 px-2.5 py-2 text-sm">
              Citation verticale (1080×1920)
              <Badge>actif</Badge>
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Seul modèle disponible dans cette tranche. D'autres modèles seront ajoutés après
              validation.
            </p>
          </div>

          <div className="panel p-3">
            <div className="panel-title">Contenu</div>
            <div className="mt-2 space-y-2">
              <div>
                <Label htmlFor="text">Citation</Label>
                <Textarea
                  id="text"
                  value={project.content.text}
                  onChange={(e) => update((p) => void (p.content.text = e.target.value))}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="author">Auteur (optionnel)</Label>
                <Input
                  id="author"
                  className="mt-1"
                  value={project.content.author}
                  onChange={(e) => update((p) => void (p.content.author = e.target.value))}
                  placeholder="ex. Aristote"
                />
              </div>
            </div>
          </div>

          <div className="panel p-3">
            <div className="panel-title">Médias</div>
            <MediaField
              label="Fond image"
              url={bgUrl}
              raw={project.content.background_image}
              onFile={(f) => uploadMedia("background_image", f)}
              onClear={() => update((p) => void (p.content.background_image = ""))}
            />
            <MediaField
              label="Logo"
              url={logoUrl}
              raw={project.content.logo}
              onFile={(f) => uploadMedia("logo", f)}
              onClear={() => update((p) => void (p.content.logo = ""))}
              className="mt-3"
            />
          </div>
        </section>

        {/* ---- CENTRE : aperçu vertical ---- */}
        <section className="flex min-h-0 flex-col bg-background">
          <div ref={wrapRef} className="flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4">
            <div
              className="overflow-hidden rounded-lg border border-border shadow-2xl"
              style={{ width: dims.width * scale, height: dims.height * scale }}
            >
              <Player
                ref={playerRef}
                component={QuoteVertical as any}
                inputProps={{ project }}
                compositionWidth={dims.width}
                compositionHeight={dims.height}
                fps={dims.fps}
                durationInFrames={dims.durationInFrames}
                controls
                loop
                acknowledgeRemotionLicense
                style={{ width: "100%", height: "100%" }}
              />
            </div>
          </div>
          <div className="border-t border-border px-4 py-2 text-center text-[11px] text-muted-foreground">
            Aperçu Remotion Player — mêmes compositions que l'export MP4. Les polices du navigateur
            peuvent habiller le texte légèrement autrement que le rendu serveur.
          </div>
        </section>

        {/* ---- DROITE : propriétés ---- */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto border-l border-border p-3">
          <div className="panel p-3">
            <div className="panel-title">Style du texte</div>
            <div className="mt-2 space-y-3">
              <div>
                <Label>Police</Label>
                <select
                  className="input-base mt-1"
                  value={project.theme.font_family}
                  onChange={(e) => update((p) => void (p.theme.font_family = e.target.value))}
                >
                  {FONTS.map((f) => (
                    <option key={f.value} value={f.value}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
              <Slider
                label="Taille du texte"
                display={`${project.theme.font_size} px`}
                min={8}
                max={400}
                step={1}
                value={[project.theme.font_size]}
                onValueChange={([v]) => update((p) => void (p.theme.font_size = v))}
              />
              <ColorField
                label="Couleur du texte"
                value={project.theme.text_color}
                onChange={(v) => update((p) => void (p.theme.text_color = v))}
              />
              <ColorField
                label="Couleur de l'auteur"
                value={project.theme.author_color}
                onChange={(v) => update((p) => void (p.theme.author_color = v))}
              />
              <div className="flex items-center justify-between">
                <Label htmlFor="shadow">Ombre portée</Label>
                <Switch
                  id="shadow"
                  checked={project.theme.shadow}
                  onCheckedChange={(v) => update((p) => void (p.theme.shadow = v))}
                />
              </div>
            </div>
          </div>

          <div className="panel p-3">
            <div className="panel-title">Position du bloc</div>
            <div className="mt-2 space-y-3">
              <Slider
                label="X"
                display={project.position.x.toFixed(2)}
                min={0}
                max={1}
                step={0.01}
                value={[project.position.x]}
                onValueChange={([v]) => update((p) => void (p.position.x = v))}
              />
              <Slider
                label="Y"
                display={project.position.y.toFixed(2)}
                min={0}
                max={1}
                step={0.01}
                value={[project.position.y]}
                onValueChange={([v]) => update((p) => void (p.position.y = v))}
              />
              <Slider
                label="Largeur du texte"
                display={project.position.width.toFixed(2)}
                min={0.1}
                max={1}
                step={0.01}
                value={[project.position.width]}
                onValueChange={([v]) => update((p) => void (p.position.width = v))}
              />
            </div>
          </div>

          <div className="panel p-3">
            <div className="panel-title">Durée &amp; animations</div>
            <div className="mt-2 space-y-3">
              <Slider
                label="Durée de la scène"
                display={`${project.timing.duration.toFixed(1)} s`}
                min={0.5}
                max={60}
                step={0.1}
                value={[project.timing.duration]}
                onValueChange={([v]) => update((p) => void (p.timing.duration = v))}
              />
              <Slider
                label="Début du texte"
                display={`${project.timing.text_start.toFixed(1)} s`}
                min={0}
                max={Math.max(0, project.timing.duration - 0.1)}
                step={0.1}
                value={[project.timing.text_start]}
                onValueChange={([v]) => update((p) => void (p.timing.text_start = v))}
              />
              <Slider
                label="Fondu d'entrée"
                display={`${project.timing.fade_in.toFixed(1)} s`}
                min={0}
                max={10}
                step={0.1}
                value={[project.timing.fade_in]}
                onValueChange={([v]) => update((p) => void (p.timing.fade_in = v))}
              />
              <Slider
                label="Fondu de sortie"
                display={`${project.timing.fade_out.toFixed(1)} s`}
                min={0}
                max={10}
                step={0.1}
                value={[project.timing.fade_out]}
                onValueChange={([v]) => update((p) => void (p.timing.fade_out = v))}
              />
              <div>
                <Label>Entrée du texte</Label>
                <select
                  className="input-base mt-1"
                  value={project.animation.text_in}
                  onChange={(e) => update((p) => void (p.animation.text_in = e.target.value))}
                >
                  <option value="fade">Fondu</option>
                  <option value="slide">Glissement</option>
                </select>
              </div>
              <div>
                <Label>Fond</Label>
                <select
                  className="input-base mt-1"
                  value={project.animation.background}
                  onChange={(e) => update((p) => void (p.animation.background = e.target.value))}
                >
                  <option value="static">Statique</option>
                  <option value="zoom_slow">Zoom lent</option>
                </select>
              </div>
            </div>
          </div>

          {(validation.errors.length > 0 || validation.warnings.length > 0) && (
            <div className="panel p-3">
              <div className="panel-title">Validation (serveur)</div>
              <ul className="mt-2 space-y-1.5 text-xs">
                {validation.errors.map((e, i) => (
                  <li key={`e${i}`} className="flex gap-1.5 text-destructive">
                    <X size={13} className="mt-0.5 shrink-0" /> {e}
                  </li>
                ))}
                {validation.warnings.map((w, i) => (
                  <li key={`w${i}`} className="flex gap-1.5 text-warning">
                    <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {w}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      {/* ---------- BARRE BASSE : lecture + durées ---------- */}
      <footer className="flex items-center gap-4 border-t border-border bg-card/40 px-4 py-2 text-xs text-muted-foreground">
        <button
          className="flex items-center gap-1.5 rounded-md border border-input px-2 py-1 text-foreground hover:bg-accent"
          onClick={() => {
            const ref = playerRef.current;
            if (!ref) return;
            if (playing) ref.pause();
            else void ref.play();
          }}
        >
          {playing ? <X size={13} /> : <Play size={13} />}
          {playing ? "Pause" : "Lecture"}
        </button>
        <span className="font-mono">
          t = {(frame / dims.fps).toFixed(2)} s / {project.timing.duration.toFixed(2)} s
        </span>
        <span className="font-mono">frame {frame + 1}/{dims.durationInFrames}</span>
        <span className="ml-auto font-mono">
          {dims.width}×{dims.height} · {dims.fps} fps · {dims.durationInFrames} frames
        </span>
        {hasErrors ? (
          <Badge variant="destructive">Export bloqué : {validation.errors.length} erreur(s)</Badge>
        ) : (
          <Badge variant="success">Prêt à exporter</Badge>
        )}
      </footer>

      {/* ---------- DIALOGUE : ouvrir ---------- */}
      {showOpen && (
        <Modal title="Ouvrir un projet" onClose={() => setShowOpen(false)}>
          {projects.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun projet enregistré.</p>
          ) : (
            <ul className="divide-y divide-border">
              {projects.map((p) => (
                <li key={p} className="flex items-center justify-between py-2">
                  <span className="text-sm">{p}</span>
                  <Button size="sm" variant="outline" onClick={() => void openProject(p)}>
                    Ouvrir
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}

      {/* ---------- DIALOGUE : export ---------- */}
      {showExport && (
        <Modal title="Export MP4 (Remotion)" onClose={() => setShowExport(false)}>
          <div className="space-y-3">
            <div>
              <Label>Nom du fichier</Label>
              <div className="mt-1 flex gap-2">
                <Input
                  value={exportName}
                  onChange={(e) => setExportName(e.target.value)}
                  placeholder="citation"
                />
                <span className="self-center text-sm text-muted-foreground">.mp4</span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Destination : dossier <code>exports/</code> du projet.
              </p>
            </div>

            {job?.status === "running" && (
              <div className="rounded-md border border-border p-3">
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5">
                    <Loader2 size={13} className="animate-spin" /> {job.message || "Rendu en cours…"}
                  </span>
                  <span className="font-mono">{Math.round(job.progress * 100)} %</span>
                </div>
                <Progress value={job.progress} />
                <Button size="sm" variant="destructive" className="mt-2" onClick={cancelExport}>
                  Annuler le rendu
                </Button>
              </div>
            )}

            {job?.status === "done" && (
              <div className="rounded-md border border-success/50 bg-success/10 p-3 text-xs">
                <div className="flex items-center gap-1.5 font-medium text-success">
                  <CheckCircle2 size={14} /> Export terminé
                </div>
                <div className="mt-1 font-mono text-foreground/90">
                  exports/{job.result?.path} · {job.result?.width}×{job.result?.height} ·{" "}
                  {job.result?.duration} s · {job.result?.frames} frames ·{" "}
                  {job.result?.size_bytes ? Math.round(job.result.size_bytes / 1024) : "?"} Ko
                </div>
              </div>
            )}

            {job?.status === "cancelled" && (
              <div className="rounded-md border border-warning/50 bg-warning/10 p-3 text-xs text-warning">
                Rendu annulé. Les fichiers temporaires ont été nettoyés.
              </div>
            )}

            {job?.status === "error" && (
              <pre className="max-h-48 overflow-auto rounded-md border border-destructive/50 bg-destructive/10 p-2 text-[11px] text-destructive">
                {job.error}
                {job.result?.traceback ? `\n${job.result.traceback}` : ""}
              </pre>
            )}

            {exportError && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
                {exportError}
                {needsOverwrite && (
                  <Button
                    size="sm"
                    variant="destructive"
                    className="mt-2"
                    onClick={() => void startExport(true)}
                  >
                    Remplacer le fichier existant
                  </Button>
                )}
              </div>
            )}

            {!job && !exportError && (
              <Button
                className="w-full"
                onClick={() => void startExport(false)}
                disabled={hasErrors}
              >
                <Download size={14} /> Lancer l'export
              </Button>
            )}

            {job?.status === "running" && (
              <p className="text-[11px] text-muted-foreground">
                Le rendu tourne dans un sous-processus hors du thread de requête. Première exécution :
                téléchargement unique du navigateur de rendu (~150 Mo).
              </p>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ---------- sous-composants ---------- */

function MediaField({
  label,
  url,
  raw,
  onFile,
  onClear,
  className = "",
}: {
  label: string;
  url: string | null;
  raw: string;
  onFile: (f: File | null) => void;
  onClear: () => void;
  className?: string;
}) {
  const inputId = React.useId();
  const missing = raw && !url;
  return (
    <div className={className}>
      <div className="mb-1 flex items-center justify-between">
        <Label>{label}</Label>
        {raw && (
          <button
            className="text-[11px] text-muted-foreground hover:text-destructive"
            onClick={onClear}
          >
            Retirer
          </button>
        )}
      </div>
      <div className="flex items-center gap-2">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded border border-border bg-secondary/40">
          {url ? (
            <img src={url} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="text-[10px] text-muted-foreground">—</span>
          )}
        </div>
        <label
          htmlFor={inputId}
          className="flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-input px-2.5 text-xs hover:bg-accent"
        >
          <Upload size={13} /> Importer…
        </label>
        <input
          id={inputId}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
      </div>
      {missing && (
        <p className="mt-1 text-[11px] text-warning">
          Média non résolvable (ancien chemin local) — réimportez le fichier.
        </p>
      )}
      {!raw && <p className="mt-1 text-[11px] text-muted-foreground">Aucun fichier sélectionné.</p>}
    </div>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <Label>{label}</Label>
      <div className="mt-1 flex items-center gap-2">
        <input
          type="color"
          className="h-8 w-10 cursor-pointer rounded border border-input bg-background p-1"
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
        />
        <Input
          className="h-8 font-mono uppercase"
          value={value}
          onChange={(e) => {
            const v = e.target.value;
            if (/^#[0-9a-fA-F]{0,6}$/.test(v)) onChange(v.toUpperCase());
          }}
        />
      </div>
    </div>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-lg p-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button className="text-muted-foreground hover:text-foreground" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
