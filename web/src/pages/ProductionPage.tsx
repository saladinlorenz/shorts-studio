import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FolderInput,
  Play,
  RefreshCw,
  RotateCcw,
  ScanSearch,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  api,
  apiErrorMessage,
  type Batch,
  type BatchField,
  type BatchPayload,
  type BatchPlan,
  type BatchSetup,
  type ConnectedFolder,
  type CsvUploadResult,
  type Proposal,
} from "../api/client";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Badge } from "../components/ui/badge";
import { ErrorNote, JobStatus } from "../components/job-status";
import { useAssistant, usePublishAssistant } from "../lib/assistant";
import { formatBytes, cancelJob, useJobPolling } from "../lib/jobs";

/**
 * Production par lots : un modèle + un CSV + des dossiers de médias connectés
 * → N projets résolus → N vidéos, rendus par la même chaîne que l'export
 * unitaire et suivis dans la file SQLite persistante.
 *
 * La page n'invente aucune règle : elle montre le plan calculé par le serveur
 * (source et passe de chaque ressource) avant de lancer le lot.
 */

const RESOURCE_MODES = [
  { value: "auto", label: "Rotation sur les dossiers connectés" },
  { value: "column", label: "Uniquement ce que dit le CSV" },
  { value: "none", label: "Rien ajouter (garder le modèle)" },
];

const FOLDER_KIND_LABELS: Record<string, string> = {
  video: "vidéos de fond",
  audio: "musiques",
  image: "images",
  any: "tout",
};

const FOLDER_KINDS = Object.keys(FOLDER_KIND_LABELS);

const ITEM_BADGES: Record<string, string> = {
  done: "border-success/50 text-success",
  running: "border-accent/50 text-accent-foreground",
  queued: "border-border text-muted-foreground",
  failed: "border-destructive/50 text-destructive",
  cancelled: "border-warning/50 text-warning",
  blocked: "border-warning/50 text-warning",
};

const BATCH_TITLES: Record<string, string> = {
  ready: "prêt à lancer",
  running: "en cours de rendu",
  paused: "en pause — relancez",
  done: "terminé",
  cancelled: "annulé",
};

/** Noms des médias utilisés, dédoublonnés : une scène sur 3 partage le même fond. */
function assetNames(assets: Array<{ name?: string; media_id?: string }>): string {
  const names = assets.map((a) => a.name ?? a.media_id ?? "").filter(Boolean);
  const unique = Array.from(new Set(names));
  return unique.length ? unique.join(", ") : "—";
}

function Select({
  value,
  onChange,
  children,
  className,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <select
      className={[
        "h-8 w-full rounded-md border border-input bg-transparent px-2 text-xs",
        "focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50",
        className ?? "",
      ].join(" ")}
      disabled={disabled}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {children}
    </select>
  );
}

export default function ProductionPage() {
  const [setup, setSetup] = React.useState<BatchSetup | null>(null);
  const [folders, setFolders] = React.useState<ConnectedFolder[]>([]);
  const [model, setModel] = React.useState("");
  const [fields, setFields] = React.useState<BatchField[]>([]);
  const [csv, setCsv] = React.useState<CsvUploadResult | null>(null);
  const [mapping, setMapping] = React.useState<Record<string, string>>({});
  const [options, setOptions] = React.useState<Record<string, string>>({ background: "auto", music: "auto" });
  const [lotName, setLotName] = React.useState("lot");
  const [overwrite, setOverwrite] = React.useState(false);
  const [plan, setPlan] = React.useState<BatchPlan | null>(null);
  const [batch, setBatch] = React.useState<Batch | null>(null);
  const [batches, setBatches] = React.useState<Batch[]>([]);
  const [inspect, setInspect] = React.useState<{ position: number; json: string } | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  // assistant IA : aide au mapping uniquement, jamais de lancement automatique
  const [agentNote, setAgentNote] = React.useState("");

  // dossiers : formulaire d'enregistrement + job de scan
  const [folderPath, setFolderPath] = React.useState("");
  const [folderKind, setFolderKind] = React.useState("video");
  const [folderName, setFolderName] = React.useState("");
  const [folderLicence, setFolderLicence] = React.useState("");
  const [scanJobId, setScanJobId] = React.useState<string | null>(null);
  const [folderError, setFolderError] = React.useState("");

  const [jobId, setJobId] = React.useState<string | null>(null);

  const { job, pollError } = useJobPolling(jobId);
  const { job: scanJob } = useJobPolling(scanJobId, 900);

  const rendering = job?.status === "running";

  // lu par les effets pour ne pas faire dépendre leur déclenchement de l'objet batch
  const batchIdRef = React.useRef("");
  React.useEffect(() => {
    batchIdRef.current = batch?.id ?? "";
  }, [batch?.id]);

  const payload = React.useMemo<BatchPayload>(
    () => ({
      model,
      csv_id: csv?.csv_id ?? "",
      mapping,
      options,
      name: lotName,
      overwrite,
    }),
    [model, csv, mapping, options, lotName, overwrite],
  );

  /** Un plan accepté remplit le formulaire local. Le calcul du plan et le
   *  lancement restent ceux de Production : l'assistant ne déclenche aucun lot. */
  const applyAgentPlan = async (plan: NonNullable<Proposal["batch"]>) => {
    const rejected: string[] = [];
    let targetFields = fields;
    if (plan.model && plan.model !== model) {
      if (setup?.models.some((m) => m.id === plan.model)) {
        try {
          targetFields = (await api.batchFields(plan.model)).fields;
        } catch (e) {
          rejected.push(`champs du modèle ${plan.model} illisibles : ${apiErrorMessage(e)}`);
          targetFields = [];
        }
        setModel(plan.model);
      } else {
        rejected.push(`modèle ${plan.model} absent de la bibliothèque`);
      }
    }
    const keys = new Set(targetFields.map((f) => f.key));
    const columns = new Set(csv?.columns ?? []);
    const nextMapping: Record<string, string> = {};
    for (const [field, column] of Object.entries(plan.mapping || {})) {
      if (!keys.has(field)) {
        rejected.push(`${field} : champ inconnu du modèle`);
        continue;
      }
      if (columns.size && !columns.has(String(column))) {
        rejected.push(`${field} → ${column} : colonne absente du CSV`);
        continue;
      }
      nextMapping[field] = String(column);
    }
    const nextOptions: Record<string, string> = { ...options };
    for (const [key, value] of Object.entries(plan.options || {})) {
      if (!["background", "music"].includes(key)) {
        rejected.push(`option ${key} non gérée`);
        continue;
      }
      if (!RESOURCE_MODES.some((mode) => mode.value === value)) {
        rejected.push(`option ${key}=${value} refusée`);
        continue;
      }
      nextOptions[key] = String(value);
    }
    if (Object.keys(nextMapping).length > 0) setMapping(nextMapping);
    setOptions(nextOptions);
    setAgentNote(
      [
        `${Object.keys(nextMapping).length} champ(s) câblé(s) par l'assistant`,
        plan.notes ? `note : ${plan.notes}` : "",
        rejected.length ? `écarté(s) : ${rejected.join(" · ")}` : "",
        "Recalculez le plan (bouton 6) ; le lancement reste votre clic.",
      ]
        .filter(Boolean)
        .join(" — "),
    );
  };

  /* ---------------- assistant : contexte publié par la page ---------------- */

  // Le panneau n'est plus embarqué ici : la page publie ses colonnes CSV et
  // reçoit le plan accepté dans le formulaire. Le calcul du plan (bouton 6) et
  // le lancement restent des clics de Production.
  const { setOpen: showAssistant } = useAssistant();

  usePublishAssistant(
    {
      project: null,
      projectName: lotName,
      mode: "production",
      csvColumns: csv?.columns ?? [],
      source: "Production",
    },
    {
      onBatchPlan: (plan) => void applyAgentPlan(plan),
      notify: (message, kind) => setAgentNote(kind === "error" ? `Assistant : ${message}` : message),
    },
  );

  const refreshSetup = React.useCallback(async () => {
    try {
      const res = await api.batchSetup();
      setSetup(res);
      setFolders(res.folders);
      setModel((current) => current || res.models.find((m) => !m.unreadable)?.id || "");
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }, []);

  const loadBatches = React.useCallback(async () => {
    try {
      setBatches((await api.batchList()).batches);
    } catch {
      setBatches([]);
    }
  }, []);

  React.useEffect(() => {
    setBusy(true);
    void refreshSetup();
    void loadBatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // les champs adressables dépendent du modèle : on les recharge à chaque choix
  React.useEffect(() => {
    if (!model) return;
    let stopped = false;
    (async () => {
      setBusy(true);
      try {
        const res = await api.batchFields(model);
        if (stopped) return;
        setFields(res.fields);
        // un changement de modèle invalide le plan : les câblages inconnus sont écartés
        setMapping((current) => {
          const kept: Record<string, string> = {};
          for (const [key, column] of Object.entries(current)) {
            if (res.fields.some((f) => f.key === key)) kept[key] = column;
          }
          return kept;
        });
        setPlan(null);
        setInspect(null);
      } catch (e) {
        if (!stopped) setError(apiErrorMessage(e));
      } finally {
        if (!stopped) setBusy(false);
      }
    })();
    return () => {
      stopped = true;
    };
  }, [model]);

  // fin de rendu : on relit le lot et l'historique
  React.useEffect(() => {
    if (!jobId || !job || job.status === "running") return;
    const id = batchIdRef.current;
    if (!id) return;
    let stopped = false;
    (async () => {
      try {
        const fresh = await api.batchDetail(id, true);
        if (!stopped) setBatch(fresh);
      } catch (e) {
        if (!stopped) setError(apiErrorMessage(e));
      }
      void loadBatches();
    })();
    return () => {
      stopped = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status, jobId, loadBatches]);

  // pendant le rendu : statuts des lignes au rythme de la progression
  React.useEffect(() => {
    if (!rendering) return;
    const id = batchIdRef.current;
    if (!id) return;
    let stopped = false;
    (async () => {
      try {
        const fresh = await api.batchDetail(id, true);
        if (!stopped) setBatch(fresh);
      } catch {
        /* le suivi du job affiche l'erreur de polling */
      }
    })();
    return () => {
      stopped = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rendering, job?.progress]);

  React.useEffect(() => {
    if (scanJob && scanJob.status !== "running") void refreshSetup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanJob?.status]);

  const pickCsv = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    setBusy(true);
    try {
      const res = await api.uploadCsv(file, model);
      setCsv(res);
      setMapping(res.suggested_mapping ?? {});
      setPlan(null);
      setInspect(null);
      if (res.fields) setFields(res.fields);
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const buildPlan = async () => {
    setError("");
    setBusy(true);
    try {
      setPlan(await api.batchPlan(payload));
      setInspect(null);
    } catch (e) {
      setError(apiErrorMessage(e));
      setPlan(null);
    } finally {
      setBusy(false);
    }
  };

  const startBatch = async () => {
    setError("");
    setBusy(true);
    try {
      const res = await api.batchStart(payload);
      setBatch(res.batch);
      setJobId(res.job_id);
      await loadBatches();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const runExisting = async (id: string) => {
    setError("");
    try {
      const res = await api.batchRun(id);
      setBatch(res.batch);
      setJobId(res.job_id);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const retryFailed = async (id: string) => {
    setError("");
    try {
      const res = await api.batchRetry(id);
      setBatch(res.batch);
      setJobId(res.started);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const cancelBatch = async () => {
    if (!batch) return;
    setError("");
    try {
      const res = await api.batchCancel(batch.id);
      setBatch(res.batch);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const inspectLine = async (position: number) => {
    setError("");
    try {
      const res = await api.batchLine(payload, position);
      setInspect({ position, json: JSON.stringify(res.project, null, 2) });
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const addFolder = async () => {
    setFolderError("");
    setBusy(true);
    try {
      await api.addFolder(folderPath, folderKind, folderName, folderLicence);
      setFolderPath("");
      setFolderName("");
      await refreshSetup();
    } catch (e) {
      setFolderError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const scanFolder = async (id: string) => {
    setFolderError("");
    try {
      const res = await api.scanFolder(id);
      setScanJobId(res.job_id);
    } catch (e) {
      setFolderError(apiErrorMessage(e));
    }
  };

  const removeFolder = async (folder: ConnectedFolder) => {
    if (!window.confirm(`Retirer le dossier « ${folder.name} » ? Les médias déjà importés restent en médiathèque.`))
      return;
    setFolderError("");
    try {
      await api.removeFolder(folder.id);
      await refreshSetup();
    } catch (e) {
      setFolderError(apiErrorMessage(e));
    }
  };

  const forgetBatch = async (id: string) => {
    if (!window.confirm("Retirer ce lot de la file ? Les MP4 déjà produits ne sont pas supprimés.")) return;
    setError("");
    try {
      await api.batchForget(id);
      if (batch?.id === id) {
        setBatch(null);
        setJobId(null);
      }
      await loadBatches();
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const selectedModel = setup?.models.find((m) => m.id === model);
  const assets = setup?.assets ?? { video: [], audio: [], image: [] };
  const mappedCount = Object.values(mapping).filter(Boolean).length;
  const canPlan = !!model && !!csv && csv.row_count > 0;
  const planReady = (plan?.summary.ready ?? 0) > 0;
  const items = batch?.items ?? [];

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="text-lg font-semibold">Production par lots</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
        Un modèle, un CSV, éventuellement des dossiers de fonds vidéo et de musiques connectés : chaque
        ligne du CSV devient un projet version 2 complet, rendu par la même chaîne que l'export unitaire.
        Le plan est calculé et affiché avant lancement — y compris le bouclage des ressources quand elles
        sont moins nombreuses que les lignes.
      </p>

      {error && (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        {/* ---------------- colonne gauche : sources ---------------- */}
        <div className="space-y-4">
          <section className="panel p-4">
            <h2 className="text-sm font-semibold">1. Modèle</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Les modèles de la bibliothèque, versions 2 uniquement.
            </p>
            <div className="mt-2">
              <Select value={model} onChange={setModel}>
                {(setup?.models ?? [])
                  .filter((m) => !m.unreadable)
                  .map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label} — {m.scenes} scène(s) · {m.duration} s
                    </option>
                  ))}
              </Select>
            </div>
            {selectedModel && (
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <div>Composition</div>
                <div className="text-right text-foreground">{selectedModel.model_id ?? "—"}</div>
                <div>Cadre</div>
                <div className="text-right text-foreground">
                  {selectedModel.width}×{selectedModel.height} · {selectedModel.fps} fps
                </div>
                <div>Médias du modèle</div>
                <div className="text-right text-foreground">{selectedModel.media_count}</div>
              </dl>
            )}
            {setup?.models.length === 0 && (
              <p className="mt-2 text-xs text-warning">
                Aucun modèle version 2 en bibliothèque : enregistrez d'abord un projet depuis Design.
              </p>
            )}
          </section>

          <section className="panel p-4">
            <h2 className="text-sm font-semibold">2. Dossiers de médias connectés</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Fonds vidéo et musiques de fond. Un dossier n'est lisible qu'après enregistrement explicite
              (chemin absolu, racine de lecteur refusée) ; ses fichiers sont copiés dans la médiathèque,
              jamais référencés par un chemin Windows.
            </p>

            <div className="mt-3 space-y-2">
              <Input
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder="D:\client-01\fonds-video"
                className="font-mono text-xs"
              />
              <div className="grid grid-cols-2 gap-2">
                <Select value={folderKind} onChange={setFolderKind}>
                  {FOLDER_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {FOLDER_KIND_LABELS[k]}
                    </option>
                  ))}
                </Select>
                <Input
                  value={folderLicence}
                  onChange={(e) => setFolderLicence(e.target.value)}
                  placeholder="licence (vide = inconnue)"
                  className="text-xs"
                />
              </div>
              <div className="flex items-center gap-2">
                <Input
                  value={folderName}
                  onChange={(e) => setFolderName(e.target.value)}
                  placeholder="nom affiché (optionnel)"
                  className="text-xs"
                />
                <Button size="sm" variant="outline" onClick={() => void addFolder()} disabled={!folderPath.trim() || busy}>
                  <FolderInput size={13} /> Enregistrer
                </Button>
              </div>
            </div>

            <ErrorNote>{folderError}</ErrorNote>

            <ul className="mt-3 space-y-2">
              {folders.length === 0 && (
                <li className="text-xs text-muted-foreground">Aucun dossier connecté pour l'instant.</li>
              )}
              {folders.map((folder) => (
                <li key={folder.id} className="rounded-md border border-border p-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium">{folder.name}</span>
                    <span className="flex shrink-0 items-center gap-1">
                      <Badge variant="outline">{folder.kind}</Badge>
                      <Badge variant="outline">
                        {folder.licence === "inconnue" ? "licence inconnue" : folder.licence}
                      </Badge>
                    </span>
                  </div>
                  <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{folder.path}</div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <span className="text-muted-foreground">
                      {folder.imported} média(s) importé(s)
                      {folder.last_scan ? ` · scan ${new Date(folder.last_scan.at).toLocaleString("fr-FR")}` : " · jamais scanné"}
                      {folder.last_scan?.interrupted ? " · scan interrompu" : ""}
                      {folder.last_scan && folder.last_scan.skipped > 0
                        ? ` · ${folder.last_scan.skipped} ignoré(s)`
                        : ""}
                    </span>
                    {!folder.present && <span className="text-warning">dossier introuvable</span>}
                    <Button size="sm" variant="outline" onClick={() => void scanFolder(folder.id)}>
                      <ScanSearch size={12} /> Scanner
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void removeFolder(folder)}>
                      <Trash2 size={12} />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>

            {scanJob && (
              <div className="mt-2">
                <JobStatus
                  job={scanJob}
                  onCancel={() => {
                    if (scanJobId) void cancelJob(scanJobId);
                  }}
                  runningLabel="Import des médias…"
                  doneMessage="Médias importés : la médiathèque et le plan sont à jour."
                />
              </div>
            )}

            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              {(["video", "audio", "image"] as const).map((kind) => (
                <div key={kind} className="rounded-md border border-border p-2">
                  <div className="text-base font-semibold text-foreground">{assets[kind]?.length ?? 0}</div>
                  <div className="text-muted-foreground">{kind === "video" ? "fonds" : kind === "audio" ? "musiques" : "images"}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="panel p-4">
            <h2 className="text-sm font-semibold">3. Attribution des ressources</h2>
            <div className="mt-2 space-y-3">
              {(["background", "music"] as const).map((key) => (
                <div key={key}>
                  <Label className="text-xs text-muted-foreground">
                    {key === "background" ? "Fonds vidéo" : "Musique de fond"}
                  </Label>
                  <div className="mt-1">
                    <Select
                      value={options[key] ?? "auto"}
                      onChange={(value) => setOptions((current) => ({ ...current, [key]: value }))}
                    >
                      {RESOURCE_MODES.map((mode) => (
                        <option key={mode.value} value={mode.value}>
                          {mode.label}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {key === "background"
                      ? "Rotation déterministe sur les fonds importés ; le cycle reprend s'il y a moins de vidéos que de lignes."
                      : "Une musique par ligne en rotation ; le fichier est bouclé ou coupé à la durée du projet, jamais accéléré."}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* ---------------- colonne droite : CSV, mapping, plan ---------------- */}
        <div className="space-y-4">
          <section className="panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">4. Import CSV</h2>
              <label className="cursor-pointer rounded-md border border-input px-3 py-1.5 text-xs hover:bg-accent">
                <input
                  type="file"
                  accept=".csv,.txt,text/csv"
                  className="hidden"
                  onChange={(e) => void pickCsv(e.target.files?.[0])}
                />
                Choisir un fichier
              </label>
            </div>
            {csv ? (
              <div className="mt-2 text-xs text-muted-foreground">
                <span className="text-foreground">{csv.file}</span> · {csv.row_count} ligne(s) · {csv.columns.length}{" "}
                colonne(s) · encodage {csv.encoding} · séparateur{" "}
                <code className="text-[11px]">{csv.delimiter === "\t" ? "tabulation" : csv.delimiter}</code>
                <div className="mt-1 flex flex-wrap gap-1">
                  {csv.columns.map((column) => (
                    <Badge key={column} variant="outline">
                      {column}
                    </Badge>
                  ))}
                </div>
                {csv.warnings.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {csv.warnings.map((w) => (
                      <li key={w} className="flex items-start gap-1.5 text-warning">
                        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                        <span>{w}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">
                En-têtes obligatoires sur la première ligne. Séparateur <code className="text-[11px]">;</code>,{" "}
                <code className="text-[11px]">,</code>, tabulation ou <code className="text-[11px]">|</code> ; UTF-8,
                UTF-8 avec BOM ou Windows-1252 détectés. Maximum{" "}
                {setup?.csv_limits.max_rows ?? 2000} lignes.
              </p>
            )}

            {csv && csv.preview.length > 0 && (
              <div className="mt-3 overflow-x-auto rounded-md border border-border">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="border-b border-border bg-card/60 text-left uppercase tracking-wider text-muted-foreground">
                      {csv.columns.map((c) => (
                        <th key={c} className="px-2 py-1.5 font-medium">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {csv.preview.slice(0, 5).map((row, i) => (
                      <tr key={i} className="border-b border-border/50 last:border-0">
                        {csv.columns.map((c) => (
                          <td key={c} className="max-w-[16rem] truncate px-2 py-1.5">
                            {row[c] ?? ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="border-t border-border px-2 py-1 text-[11px] text-muted-foreground">
                  {csv.preview.length > 5 ? `5 premières lignes sur ${csv.row_count} · ` : ""}
                  {csv.row_count} projet(s) à produire
                </div>
              </div>
            )}
          </section>

          <section className="panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">5. Mapping des colonnes</h2>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {mappedCount} champ(s) câblé(s) sur {fields.length}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 text-xs"
                  onClick={() => showAssistant(true)}
                  disabled={!csv || fields.length === 0}
                  title={csv ? "Suggérer un mapping d'après les colonnes réelles" : "Importez d'abord un CSV"}
                >
                  <Sparkles size={12} /> Aider avec l'IA
                </Button>
              </div>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Une colonne mappée gagne toujours sur l'attribution automatique. Un nom de fichier introuvable dans
              les dossiers connectés bloque la ligne — rien n'est remplacé en silence.
            </p>

            {fields.length === 0 ? (
              <p className="mt-3 text-xs text-muted-foreground">
                Sélectionnez un modèle pour lister ses champs adressables.
              </p>
            ) : (
              <div className="mt-3 max-h-80 space-y-1.5 overflow-y-auto pr-1">
                {fields.map((field) => (
                  <div key={field.key} className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-xs font-medium">{field.label}</span>
                        {field.required && <Badge variant="outline">requis</Badge>}
                        {field.type === "media" && <Badge variant="outline">{field.kind}</Badge>}
                      </div>
                      <div className="truncate font-mono text-[10px] text-muted-foreground">{field.key}</div>
                    </div>
                    <div className="w-40 shrink-0">
                      <Select
                        value={mapping[field.key] ?? ""}
                        onChange={(value) =>
                          setMapping((current) => {
                            const next = { ...current };
                            if (value) next[field.key] = value;
                            else delete next[field.key];
                            return next;
                          })
                        }
                        disabled={!csv}
                      >
                        <option value="">— non câblé —</option>
                        {(csv?.columns ?? []).map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </Select>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {!csv && fields.length > 0 && (
              <p className="mt-2 text-[11px] text-muted-foreground">Importez un CSV pour câbler les colonnes.</p>
            )}

            {agentNote && (
              <p className="mt-3 border-t border-border/60 pt-3 text-[11px] leading-snug text-muted-foreground">
                {agentNote}
              </p>
            )}
          </section>

          <section className="panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">6. Plan du lot</h2>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <Label className="text-[11px] text-muted-foreground">Nom</Label>
                  <Input value={lotName} onChange={(e) => setLotName(e.target.value)} className="h-7 w-32 text-xs" />
                </div>
                <div className="flex items-center gap-1.5">
                  <Switch checked={overwrite} onCheckedChange={(v) => setOverwrite(Boolean(v))} />
                  <Label className="text-[11px] text-muted-foreground">écraser les fichiers existants</Label>
                </div>
                <Button size="sm" variant="outline" onClick={() => void buildPlan()} disabled={!canPlan || busy}>
                  <RefreshCw size={13} /> Calculer le plan
                </Button>
                <Button size="sm" onClick={() => void startBatch()} disabled={!canPlan || !planReady || busy || rendering}>
                  <Play size={13} /> Lancer
                </Button>
              </div>
            </div>

            {!plan && (
              <p className="mt-2 text-xs text-muted-foreground">
                {canPlan
                  ? "Le plan détaille, ligne par ligne, le fichier produit, la source de chaque ressource et ses avertissements."
                  : "Choisissez un modèle et importez un CSV pour calculer le plan."}
              </p>
            )}

            {plan && (
              <>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                  <div className="rounded-md border border-border p-2">
                    <div className="text-base font-semibold text-foreground">{plan.summary.ready}</div>
                    <div className="text-muted-foreground">ligne(s) prête(s) / {plan.summary.rows}</div>
                  </div>
                  <div className="rounded-md border border-border p-2">
                    <div className="text-base font-semibold text-foreground">{plan.summary.video_assets}</div>
                    <div className="text-muted-foreground">
                      fonds dispo {plan.summary.background_passes ? `· ${plan.summary.background_passes} passe(s)` : ""}
                    </div>
                  </div>
                  <div className="rounded-md border border-border p-2">
                    <div className="text-base font-semibold text-foreground">{plan.summary.audio_assets}</div>
                    <div className="text-muted-foreground">
                      musiques {plan.summary.music_passes ? `· ${plan.summary.music_passes} passe(s)` : ""}
                    </div>
                  </div>
                  <div className="rounded-md border border-border p-2">
                    <div className="text-base font-semibold text-warning">{plan.summary.invalid_rows.length}</div>
                    <div className="text-muted-foreground">ligne(s) bloquée(s)</div>
                  </div>
                </div>

                {(plan.summary.cycled_background || plan.summary.cycled_music) && (
                  <p className="mt-2 flex items-start gap-1.5 rounded-md border border-accent/40 bg-accent/10 p-2 text-xs">
                    <RotateCcw size={13} className="mt-0.5 shrink-0 text-accent-foreground" />
                    <span>
                      Bouclage : les ressources sont moins nombreuses que les lignes, le cycle reprend au début.
                      Chaque fond sert au plus {plan.summary.background_passes || 1} fois, chaque musique au plus{" "}
                      {plan.summary.music_passes || 1} fois.
                    </span>
                  </p>
                )}

                {plan.warnings.length > 0 && (
                  <ul className="mt-2 space-y-1 text-xs">
                    {plan.warnings.map((w) => (
                      <li key={w} className="flex items-start gap-1.5 text-warning">
                        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                        <span>{w}</span>
                      </li>
                    ))}
                  </ul>
                )}

                <div className="mt-3 overflow-x-auto rounded-md border border-border">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="border-b border-border bg-card/60 text-left uppercase tracking-wider text-muted-foreground">
                        <th className="px-2 py-1.5 font-medium">#</th>
                        <th className="px-2 py-1.5 font-medium">Fichier</th>
                        <th className="px-2 py-1.5 font-medium">Durée</th>
                        <th className="px-2 py-1.5 font-medium">Fond</th>
                        <th className="px-2 py-1.5 font-medium">Musique</th>
                        <th className="px-2 py-1.5 font-medium">Diagnostic</th>
                        <th className="px-2 py-1.5" />
                      </tr>
                    </thead>
                    <tbody>
                      {plan.items.slice(0, 50).map((item) => (
                        <tr
                          key={item.index}
                          className={["border-b border-border/50 last:border-0", item.errors.length ? "bg-destructive/5" : ""].join(" ")}
                        >
                          <td className="px-2 py-1.5 font-mono">{item.index}</td>
                          <td className="max-w-[14rem] truncate px-2 py-1.5 font-medium">{item.filename}</td>
                          <td className="px-2 py-1.5 text-muted-foreground">{item.duration} s</td>
                          <td className="max-w-[12rem] truncate px-2 py-1.5">
                            {assetNames(item.assets_used.filter((a) => a.field.endsWith(".background")))}
                            <span className="text-muted-foreground">
                              {" "}
                              · {item.background_source}
                              {item.background_pass ? ` (passe ${item.background_pass})` : ""}
                            </span>
                          </td>
                          <td className="max-w-[12rem] truncate px-2 py-1.5">
                            {assetNames(item.assets_used.filter((a) => a.field === "audio.music"))}
                            <span className="text-muted-foreground">
                              {" "}
                              · {item.music_source}
                              {item.music_pass ? ` (passe ${item.music_pass})` : ""}
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            {item.errors.length > 0 && (
                              <span className="text-destructive">{item.errors[0]}</span>
                            )}
                            {item.errors.length === 0 && item.warnings.length > 0 && (
                              <span className="text-warning">{item.warnings[0]}</span>
                            )}
                            {item.errors.length === 0 && item.warnings.length === 0 && (
                              <span className="flex items-center gap-1 text-success">
                                <CheckCircle2 size={12} /> ok
                              </span>
                            )}
                            {item.errors.length + item.warnings.length > 1 && (
                              <span className="text-muted-foreground">
                                {" "}
                                (+{item.errors.length + item.warnings.length - 1})
                              </span>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-right">
                            <button
                              className="rounded-md border border-input px-2 py-1 text-[10px] hover:bg-accent"
                              onClick={() => void inspectLine(item.index)}
                            >
                              voir
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {plan.items.length > 50 && (
                    <div className="border-t border-border px-2 py-1 text-[11px] text-muted-foreground">
                      50 premières lignes affichées sur {plan.items.length} — le lot rend la totalité.
                    </div>
                  )}
                </div>
              </>
            )}

            {inspect && (
              <div className="mt-3 rounded-md border border-border">
                <div className="flex items-center justify-between border-b border-border px-2 py-1.5 text-xs">
                  <span className="font-medium">Projet résolu — ligne {inspect.position}</span>
                  <button className="text-muted-foreground hover:text-foreground" onClick={() => setInspect(null)}>
                    fermer
                  </button>
                </div>
                <pre className="max-h-64 overflow-auto p-2 text-[10px] leading-relaxed">{inspect.json}</pre>
              </div>
            )}
          </section>

          <section className="panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">7. File de production</h2>
              {batch && (
                <div className="flex items-center gap-2">
                  <a
                    href={api.batchManifestUrl(batch.id, "csv")}
                    className="rounded-md border border-input px-2.5 py-1 text-xs hover:bg-accent"
                  >
                    <Download size={12} className="mr-1 inline" /> Manifeste CSV
                  </a>
                  <a
                    href={api.batchManifestUrl(batch.id, "json")}
                    className="rounded-md border border-input px-2.5 py-1 text-xs hover:bg-accent"
                  >
                    <Download size={12} className="mr-1 inline" /> Manifeste JSON
                  </a>
                </div>
              )}
            </div>

            {batch ? (
              <div className="mt-2 space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-medium">{batch.name}</span>
                  <Badge variant="outline">{BATCH_TITLES[batch.status] ?? batch.status}</Badge>
                  <span className="text-muted-foreground">
                    {batch.counters.rendered}/{batch.counters.total} rendues
                    {batch.counters.failed ? ` · ${batch.counters.failed} échec(s)` : ""}
                    {batch.counters.blocked ? ` · ${batch.counters.blocked} bloquée(s)` : ""}
                  </span>
                  <span className="truncate font-mono text-[11px] text-muted-foreground">{batch.message}</span>
                  {rendering && (
                    <Button size="sm" variant="destructive" onClick={() => void cancelBatch()}>
                      Annuler le lot
                    </Button>
                  )}
                  {!rendering && batch.counters.failed + batch.counters.cancelled > 0 && (
                    <Button size="sm" variant="outline" onClick={() => void retryFailed(batch.id)}>
                      <RotateCcw size={12} /> Relancer les échecs
                    </Button>
                  )}
                  {!rendering && batch.status === "paused" && (
                    <Button size="sm" variant="outline" onClick={() => void runExisting(batch.id)}>
                      Reprendre
                    </Button>
                  )}
                </div>

                <JobStatus
                  job={job && job.kind === "batch" ? job : null}
                  pollError={pollError}
                  onCancel={() => void cancelBatch()}
                  runningLabel="Rendu du lot…"
                />

                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="border-b border-border bg-card/60 text-left uppercase tracking-wider text-muted-foreground">
                        <th className="px-2 py-1.5 font-medium">#</th>
                        <th className="px-2 py-1.5 font-medium">Fichier</th>
                        <th className="px-2 py-1.5 font-medium">Statut</th>
                        <th className="px-2 py-1.5 font-medium">Sortie</th>
                        <th className="px-2 py-1.5 font-medium">Détail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.position} className="border-b border-border/50 last:border-0">
                          <td className="px-2 py-1.5 font-mono">{item.position}</td>
                          <td className="max-w-[14rem] truncate px-2 py-1.5">{item.filename}</td>
                          <td className="px-2 py-1.5">
                            <span
                              className={[
                                "rounded-full border px-1.5 py-0.5 text-[10px] uppercase tracking-wider",
                                ITEM_BADGES[item.status] ?? "border-border",
                              ].join(" ")}
                            >
                              {item.status}
                            </span>
                          </td>
                          <td className="max-w-[14rem] truncate px-2 py-1.5 text-muted-foreground">
                            {item.status === "done" ? (
                              <a
                                href={api.batchFileUrl(batch.id, item.position)}
                                target="_blank"
                                rel="noreferrer"
                                className="text-foreground hover:underline"
                              >
                                {formatBytes(item.size_bytes)} · contrôle visuel
                              </a>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-2 py-1.5">
                            {item.error && <span className="text-destructive">{item.error}</span>}
                            {!item.error && item.assets.length > 0 && (
                              <span className="text-muted-foreground">{assetNames(item.assets)}</span>
                            )}
                            {!item.error && (item.warnings?.length ?? 0) > 0 && (
                              <span className="text-warning"> {item.warnings[0]}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  File persistante : {setup?.batch_dir}/queue.sqlite3. Un arrêt du serveur met le lot en pause
                  sans relancer tout seul ; une ligne interrompue repasse dans la file d'attente.
                </p>
              </div>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">
                Aucun lot sélectionné — calculez un plan puis lancez-le, ou reprenez un lot de l'historique.
              </p>
            )}
          </section>

          <section className="panel p-4">
            <h2 className="text-sm font-semibold">Historique des lots</h2>
            {batches.length === 0 ? (
              <p className="mt-2 text-xs text-muted-foreground">Aucun lot enregistré.</p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {batches.map((row) => (
                  <li key={row.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-2 py-1.5 text-xs">
                    <span className="truncate font-medium">{row.name}</span>
                    <Badge variant="outline">{BATCH_TITLES[row.status] ?? row.status}</Badge>
                    <span className="text-muted-foreground">
                      {row.counters.rendered}/{row.counters.total} · {row.model_id}
                    </span>
                    <span className="text-muted-foreground">{new Date(row.created_at).toLocaleString("fr-FR")}</span>
                    <span className="ml-auto flex items-center gap-2">
                      {(row.status === "ready" || row.status === "paused" || row.status === "cancelled") && (
                        <button
                          className="rounded-md border border-input px-2 py-1 hover:bg-accent disabled:opacity-50"
                          onClick={() => void runExisting(row.id)}
                          disabled={row.is_running || rendering}
                        >
                          Lancer
                        </button>
                      )}
                      {row.counters.failed > 0 && (
                        <button
                          className="rounded-md border border-input px-2 py-1 hover:bg-accent"
                          onClick={() => void retryFailed(row.id)}
                        >
                          Relancer les échecs
                        </button>
                      )}
                      <button
                        className="rounded-md border border-input px-2 py-1 hover:bg-accent"
                        onClick={() => {
                          void api.batchDetail(row.id, true).then((detail) => {
                            setBatch(detail);
                            if (detail.job_id) setJobId(detail.job_id);
                          });
                        }}
                      >
                        Détail
                      </button>
                      <button
                        className="rounded-md border border-destructive/60 px-2 py-1 text-destructive hover:bg-destructive/10"
                        onClick={() => void forgetBatch(row.id)}
                      >
                        Retirer
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
