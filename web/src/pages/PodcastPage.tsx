import React from "react";
import { Database, Loader2, Mic, Plus, RefreshCw, Search, Video } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input, Textarea } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import { ErrorNote, JobStatus } from "../components/job-status";
import { HttpError, call, cancelJob, formatBytes, formatDuration, useJobPolling } from "../lib/jobs";

interface PodcastStats {
  total_clips: number;
  speakers: string[];
  speaker_count: number;
  folder: string;
  legacy: { exists: boolean; total_clips: number; speakers: number };
}

interface CatalogRow {
  clip: string;
  url: string | null;
  speaker: string;
  phrase: string;
  start: number | null;
  end: number | null;
  duration: number | null;
  source: string;
}

interface CatalogResponse {
  total: number;
  shown: number;
  clips: CatalogRow[];
}

interface AddResult {
  clips_created: number;
  total_clips: number;
  speaker_count: number;
  note: string | null;
}

interface ImportResult {
  copied: number;
  failed: string[];
  total_clips: number;
  speaker_count: number;
}

interface GenerateResult {
  name: string;
  url: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  duration: number | null;
  fps?: number;
  frames?: number;
  unreadable: boolean;
}

export default function PodcastPage() {
  const [stats, setStats] = React.useState<PodcastStats | null>(null);
  const [statsError, setStatsError] = React.useState("");
  const [loadingStats, setLoadingStats] = React.useState(true);
  const [catalog, setCatalog] = React.useState<CatalogResponse>({ total: 0, shown: 0, clips: [] });
  const [catalogError, setCatalogError] = React.useState("");
  const [loadingCatalog, setLoadingCatalog] = React.useState(true);

  const [url, setUrl] = React.useState("");
  const [speaker, setSpeaker] = React.useState("");
  const [filterSpeaker, setFilterSpeaker] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [preview, setPreview] = React.useState<string | null>(null);

  const [script, setScript] = React.useState("");
  const [altern, setAltern] = React.useState(true);
  const [name, setName] = React.useState("generated_video");
  const [generated, setGenerated] = React.useState<GenerateResult | null>(null);
  const [addResult, setAddResult] = React.useState<AddResult | null>(null);
  const [importResult, setImportResult] = React.useState<ImportResult | null>(null);

  const [startError, setStartError] = React.useState("");
  const [needsOverwrite, setNeedsOverwrite] = React.useState(false);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const { job, pollError } = useJobPolling(jobId);
  const busy = job?.status === "running";

  const loadStats = React.useCallback(async () => {
    setLoadingStats(true);
    try {
      setStats(await call<PodcastStats>("/api/podcast/stats"));
      setStatsError("");
    } catch (e) {
      setStatsError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingStats(false);
    }
  }, []);

  const loadCatalog = React.useCallback(async (spk: string, q: string) => {
    setLoadingCatalog(true);
    try {
      const params = new URLSearchParams({ speaker: spk, q, limit: "100" });
      setCatalog(await call<CatalogResponse>(`/api/podcast/clips?${params.toString()}`));
      setCatalogError("");
    } catch (e) {
      setCatalogError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingCatalog(false);
    }
  }, []);

  React.useEffect(() => {
    void loadStats();
    void loadCatalog("", "");
  }, [loadStats, loadCatalog]);

  React.useEffect(() => {
    if (!job || job.status !== "done") return;
    if (job.kind === "podcast_add") setAddResult(job.result as AddResult);
    if (job.kind === "podcast_generate") setGenerated(job.result as GenerateResult);
    if (job.kind === "podcast_legacy_import") setImportResult(job.result as ImportResult);
    void loadStats();
    void loadCatalog(filterSpeaker, query);
  }, [job, loadStats, loadCatalog, filterSpeaker, query]);

  async function start(path: string, body: Record<string, unknown>) {
    setStartError("");
    setNeedsOverwrite(false);
    try {
      const res = await call<{ job_id: string }>(path, { method: "POST", body: JSON.stringify(body) });
      setJobId(res.job_id);
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) setNeedsOverwrite(true);
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-card/40 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Mic size={16} className="text-primary" />
          <h1 className="text-sm font-semibold">Podcast</h1>
        </div>
        {stats && (
          <Badge variant={stats.total_clips > 0 ? "success" : "warning"}>
            {stats.total_clips} phrase(s) · {stats.speaker_count} source(s)
          </Badge>
        )}
        <span className="text-[11px] text-muted-foreground">
          base locale : <code className="text-[11px]">{stats?.folder ?? "podcast_db"}/</code>
        </span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={busy}
          onClick={() => {
            void loadStats();
            void loadCatalog(filterSpeaker, query);
          }}
        >
          <RefreshCw size={14} /> Actualiser
        </Button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[360px_minmax(0,1fr)] overflow-hidden">
        {/* ---- GAUCHE : base de phrases ---- */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto border-r border-border p-3">
          <div className="panel p-3">
            <div className="panel-title">Base de phrases</div>
            {loadingStats && <p className="mt-2 text-xs text-muted-foreground">Chargement…</p>}
            {!loadingStats && statsError && <ErrorNote>{statsError}</ErrorNote>}
            {!loadingStats && !statsError && stats && (
              <>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-semibold tabular-nums">{stats.total_clips}</span>
                  <span className="text-xs text-muted-foreground">clips stockés</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {stats.speakers.length === 0 && (
                    <span className="text-xs text-muted-foreground">Aucune source enregistrée.</span>
                  )}
                  {stats.speakers.map((s) => (
                    <Badge key={s} variant="secondary">
                      {s}
                    </Badge>
                  ))}
                </div>
              </>
            )}
            {stats?.legacy.exists && stats.total_clips === 0 && (
              <div className="mt-3 rounded-md border border-warning/50 bg-warning/10 p-2 text-[11px] text-warning">
                <p>
                  Ancienne base Tkinter trouvée ({stats.legacy.total_clips} clip(s),{" "}
                  {stats.legacy.speakers} source(s)) dans votre dossier personnel.
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-1.5"
                  disabled={busy}
                  onClick={() => void start("/api/podcast/legacy/import", {})}
                >
                  <Database size={13} /> Importer dans le projet
                </Button>
              </div>
            )}
            {importResult && (
              <p className="mt-2 text-[11px] text-success">
                {importResult.copied} fichier(s) importé(s) · {importResult.total_clips} phrase(s) en base.
                {importResult.failed.length > 0 ? ` Échecs : ${importResult.failed.join(", ")}` : ""}
              </p>
            )}
          </div>

          <div className="panel p-3">
            <div className="panel-title">Ajouter une vidéo source</div>
            <div className="mt-2 space-y-2">
              <div>
                <Label htmlFor="podcast-url">URL YouTube</Label>
                <Input
                  id="podcast-url"
                  className="mt-1"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=…"
                  disabled={busy}
                />
              </div>
              <div>
                <Label htmlFor="podcast-speaker">Nom du locuteur (optionnel)</Label>
                <Input
                  id="podcast-speaker"
                  className="mt-1"
                  value={speaker}
                  onChange={(e) => setSpeaker(e.target.value)}
                  placeholder="utilisé : titre de la vidéo"
                  disabled={busy}
                />
              </div>
              <Button
                size="sm"
                className="w-full"
                disabled={!url.trim() || busy}
                onClick={() =>
                  void start("/api/podcast/videos", { url: url.trim(), speaker: speaker.trim() || null })
                }
              >
                {busy && job?.kind === "podcast_add" ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Plus size={14} />
                )}
                Ajouter à la base
              </Button>
              <p className="text-[11px] text-muted-foreground">
                Télécharge la vidéo, récupère les sous-titres et découpe phrase par phrase (FFmpeg).
              </p>
            </div>
            {addResult && (
              <div className="mt-2 rounded-md border border-border p-2 text-xs">
                {addResult.clips_created > 0 ? (
                  <span className="text-success">
                    {addResult.clips_created} phrase(s) ajoutée(s) · {addResult.total_clips} en base ·{" "}
                    {addResult.speaker_count} source(s).
                  </span>
                ) : (
                  <span className="text-warning">{addResult.note ?? "Aucune phrase ajoutée."}</span>
                )}
              </div>
            )}
            <ErrorNote>{startError && !needsOverwrite ? startError : ""}</ErrorNote>
          </div>
        </section>

        {/* ---- DROITE : catalogue + generation ---- */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto p-3">
          <div className="panel p-3">
            <div className="panel-title">Catalogue de phrases</div>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <div className="min-w-[180px] flex-1">
                <Label htmlFor="catalog-search">Recherche (mot ou phrase approchante)</Label>
                <Input
                  id="catalog-search"
                  className="mt-1"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void loadCatalog(filterSpeaker, query.trim());
                  }}
                  placeholder="ex. bonjour"
                />
              </div>
              <div className="w-44">
                <Label htmlFor="catalog-speaker">Source</Label>
                <select
                  id="catalog-speaker"
                  className="input-base mt-1"
                  value={filterSpeaker}
                  onChange={(e) => {
                    setFilterSpeaker(e.target.value);
                    void loadCatalog(e.target.value, "");
                    setQuery("");
                  }}
                >
                  <option value="">toutes</option>
                  {(stats?.speakers ?? []).map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => void loadCatalog(filterSpeaker, query.trim())}
              >
                <Search size={14} /> Chercher
              </Button>
            </div>

            {catalogError && <div className="mt-2"><ErrorNote>{catalogError}</ErrorNote></div>}
            <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
              {loadingCatalog ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 size={12} className="animate-spin" /> Chargement du catalogue…
                </span>
              ) : (
                <span>
                  {catalog.total} correspondance(s){catalog.total > catalog.shown ? `, ${catalog.shown} affichées` : ""}
                </span>
              )}
            </div>
            <div className="mt-2 max-h-64 overflow-y-auto rounded-md border border-border">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-card">
                  <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-1.5">Phrase</th>
                    <th className="px-2 py-1.5">Source</th>
                    <th className="px-2 py-1.5">Début</th>
                    <th className="px-2 py-1.5">Fin</th>
                    <th className="px-2 py-1.5">Durée</th>
                    <th className="px-2 py-1.5 text-right">Aperçu</th>
                  </tr>
                </thead>
                <tbody>
                  {!loadingCatalog && catalog.clips.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-2 py-4 text-center text-muted-foreground">
                        Aucune phrase dans la base pour ce filtre — ajoutez d'abord une vidéo source.
                      </td>
                    </tr>
                  )}
                  {catalog.clips.map((row) => (
                    <tr key={`${row.clip}-${row.start}`} className="border-b border-border/50 last:border-0">
                      <td className="px-2 py-1.5">{row.phrase}</td>
                      <td className="px-2 py-1.5 text-muted-foreground">{row.speaker}</td>
                      <td className="px-2 py-1.5 font-mono text-muted-foreground">{row.start ?? "?"}</td>
                      <td className="px-2 py-1.5 font-mono text-muted-foreground">{row.end ?? "?"}</td>
                      <td className="px-2 py-1.5 font-mono text-muted-foreground">
                        {row.duration === null ? "?" : `${row.duration} s`}
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <button
                          className="inline-flex items-center gap-1 rounded-md border border-input px-2 py-0.5 text-[11px] hover:bg-accent disabled:opacity-50"
                          disabled={!row.url}
                          onClick={() => setPreview(row.url)}
                        >
                          <Video size={11} /> clip
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {preview && (
              <div className="mt-2 rounded-md border border-border p-2">
                <video controls autoPlay src={preview} className="max-h-56 w-full rounded bg-black" />
                <button
                  className="mt-1 text-[11px] text-muted-foreground hover:text-foreground"
                  onClick={() => setPreview(null)}
                >
                  Masquer l'aperçu
                </button>
              </div>
            )}
          </div>

          <div className="panel p-3">
            <div className="panel-title">Générer une vidéo</div>
            <div className="mt-2 space-y-2">
              <div>
                <Label htmlFor="script">Texte à énoncer</Label>
                <Textarea
                  id="script"
                  className="mt-1"
                  value={script}
                  onChange={(e) => setScript(e.target.value)}
                  placeholder="Une phrase par ligne ou séparée par des points. Chaque phrase doit exister dans la base."
                />
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <div className="min-w-[180px] flex-1">
                  <Label htmlFor="gen-name">Nom du fichier</Label>
                  <div className="mt-1 flex items-center gap-2">
                    <Input id="gen-name" className="h-8" value={name} onChange={(e) => setName(e.target.value)} />
                    <span className="text-xs text-muted-foreground">.mp4</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Label htmlFor="gen-altern">Alterner les sources</Label>
                  <Switch id="gen-altern" checked={altern} onCheckedChange={setAltern} disabled={busy} />
                </div>
              </div>
              <Button
                className="w-full"
                disabled={!script.trim() || busy || (stats?.total_clips ?? 0) === 0}
                title={
                  (stats?.total_clips ?? 0) === 0
                    ? "Ajoutez d'abord une vidéo source à la base"
                    : undefined
                }
                onClick={() =>
                  void start("/api/podcast/generate", {
                    script,
                    altern,
                    name: name.trim() || "generated_video",
                    overwrite: needsOverwrite,
                  })
                }
              >
                {busy && job?.kind === "podcast_generate" ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Video size={14} />
                )}
                Générer la vidéo
              </Button>
              {busy && job?.kind === "podcast_generate" && (
                <div className="space-y-1">
                  <Progress value={job?.progress ?? 0} />
                  <p className="text-[11px] text-muted-foreground">{job?.message}</p>
                </div>
              )}
            </div>

            {needsOverwrite && (
              <div className="mt-2 rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
                {startError}
                <Button
                  size="sm"
                  variant="destructive"
                  className="mt-2"
                  disabled={busy}
                  onClick={() =>
                    void start("/api/podcast/generate", {
                      script,
                      altern,
                      name: name.trim() || "generated_video",
                      overwrite: true,
                    })
                  }
                >
                  Remplacer le fichier existant
                </Button>
              </div>
            )}

            {generated && job?.status === "done" && (
              <div className="mt-2 rounded-md border border-success/50 bg-success/10 p-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="success">vidéo générée</Badge>
                  <span className="font-mono text-[11px]">
                    {generated.name} · {formatBytes(generated.size_bytes)} ·{" "}
                    {generated.width && generated.height ? `${generated.width}×${generated.height}` : "dimensions inconnues"} ·{" "}
                    {formatDuration(generated.duration)}
                  </span>
                </div>
                <video controls src={generated.url} className="mt-2 max-h-64 w-full rounded bg-black" />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Enregistrée dans <code className="text-[11px]">{stats?.folder ?? "podcast_db"}/output/</code>
                  {generated.unreadable ? " · fichier illisible à la vérification" : ""}
                </p>
              </div>
            )}
          </div>

          <JobStatus
            job={job}
            pollError={pollError}
            runningLabel="Opération en cours…"
            onCancel={() => jobId && void cancelJob(jobId)}
            doneMessage={
              job?.kind === "podcast_generate" && generated
                ? `${generated.name} · ${formatBytes(generated.size_bytes)} · ${formatDuration(generated.duration)}`
                : job?.kind === "podcast_add" && addResult
                  ? `${addResult.clips_created} phrase(s) ajoutée(s).`
                  : job?.kind === "podcast_legacy_import" && importResult
                    ? `${importResult.copied} fichier(s) importé(s).`
                    : undefined
            }
          />
        </section>
      </div>
    </div>
  );
}
