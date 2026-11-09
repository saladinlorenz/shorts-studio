import React from "react";
import {
  Clapperboard,
  Download,
  FolderOpen,
  Info,
  Loader2,
  ScanSearch,
  Trash2,
  Wand2,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input, Textarea } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Slider } from "../components/ui/slider";
import { Switch } from "../components/ui/switch";
import { Badge } from "../components/ui/badge";
import { ErrorNote, JobStatus } from "../components/job-status";
import { call, cancelJob, formatBytes, formatDuration, useJobPolling } from "../lib/jobs";

interface ClipInfo {
  title: string;
  duration: number;
  duration_display: string;
  formats: number;
  subtitles: string[];
  auto_captions: string[];
}

interface DownloadResult {
  sid: string;
  title: string;
  video_name: string;
  video_size_bytes: number;
  subtitle_name: string | null;
  segment_count: number;
  transcript_chars: number;
  warning: string | null;
}

interface AnalyzedClip {
  index: number;
  title: string;
  description: string;
  hook: string;
  social_score: number;
  start_time: string;
  end_time: string;
  start_seconds: number;
  end_seconds: number;
  duration: number;
}

interface ProducedFile {
  name: string;
  url: string;
  format: string;
  title: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  duration: number | null;
  unreadable: boolean;
}

interface ExtractResult {
  sid: string;
  files: ProducedFile[];
  errors: Array<{ clip: string; format: string; error: string }>;
  requested: number;
  formats: string[];
  output_folder: string;
}

interface SessionDetail {
  sid: string;
  title: string;
  video_name: string | null;
  video_exists: boolean;
  subtitle_name: string | null;
  segment_count: number;
  transcript_chars: number;
  transcript: string;
  transcript_truncated: boolean;
  clips: AnalyzedClip[];
  produced: ProducedFile[];
}

interface SessionSummary {
  sid: string;
  title: string;
  video_exists: boolean;
  created_at: number;
  analyzed_count: number;
  produced_count: number;
}

export default function ClipsPage() {
  const [url, setUrl] = React.useState("");
  const [info, setInfo] = React.useState<ClipInfo | null>(null);
  const [download, setDownload] = React.useState<DownloadResult | null>(null);
  const [session, setSession] = React.useState<SessionDetail | null>(null);
  const [sessions, setSessions] = React.useState<SessionSummary[]>([]);
  const [extract, setExtract] = React.useState<ExtractResult | null>(null);
  const [numClips, setNumClips] = React.useState(5);
  const [selected, setSelected] = React.useState<Record<number, boolean>>({});
  const [landscape, setLandscape] = React.useState(true);
  const [portrait, setPortrait] = React.useState(true);
  const [startError, setStartError] = React.useState("");
  const [groqConfigured, setGroqConfigured] = React.useState<boolean | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);

  const { job, pollError } = useJobPolling(jobId);
  const busy = job?.status === "running";

  const refreshSessions = React.useCallback(async () => {
    try {
      setSessions(await call<SessionSummary[]>("/api/clips/sessions"));
    } catch {
      setSessions([]);
    }
  }, []);

  React.useEffect(() => {
    void refreshSessions();
    call<{ groq_configured: boolean }>("/api/settings")
      .then((s) => setGroqConfigured(s.groq_configured))
      .catch(() => setGroqConfigured(null));
  }, [refreshSessions]);

  const openSession = React.useCallback(async (sid: string) => {
    try {
      const detail = await call<SessionDetail>(`/api/clips/sessions/${sid}`);
      setSession(detail);
      setSelected(Object.fromEntries(detail.clips.map((c) => [c.index, true])));
      setExtract(null);
      setStartError("");
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // Les resultats definitifs sont relus cote serveur : la page affiche l'etat reel.
  React.useEffect(() => {
    if (!job || job.status !== "done") return;
    const result = job.result;
    if (job.kind === "clips_info") setInfo(result as ClipInfo);
    if (job.kind === "clips_download") {
      setDownload(result as DownloadResult);
      void openSession((result as DownloadResult).sid);
    }
    if (job.kind === "clips_analyze" || job.kind === "clips_extract") {
      if (job.kind === "clips_extract") setExtract(result as ExtractResult);
      void openSession((result as { sid: string }).sid);
    }
    void refreshSessions();
  }, [job, openSession, refreshSessions]);

  async function start(path: string, body: Record<string, unknown>) {
    setStartError("");
    try {
      const res = await call<{ job_id: string }>(path, { method: "POST", body: JSON.stringify(body) });
      setJobId(res.job_id);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  const clips = session?.clips ?? [];
  const selectedIndexes = clips.filter((c) => selected[c.index] !== false).map((c) => c.index);
  const canAnalyze = !!session && session.transcript_chars > 0 && !busy && groqConfigured !== false;
  const canExtract = clips.length > 0 && selectedIndexes.length > 0 && !!session?.video_exists && !busy;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-card/40 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Clapperboard size={16} className="text-primary" />
          <h1 className="text-sm font-semibold">Clips YouTube</h1>
        </div>
        <Badge variant={groqConfigured ? "success" : "warning"}>
          {groqConfigured === null ? "État Groq inconnu" : groqConfigured ? "Clé Groq configurée" : "Clé Groq à saisir (Réglages)"}
        </Badge>
        <div className="ml-auto flex items-center gap-2">
          <Label htmlFor="session-picker" className="shrink-0">
            Session
          </Label>
          <select
            id="session-picker"
            className="input-base h-8 w-56"
            value={session?.sid ?? ""}
            disabled={busy}
            onChange={(e) => {
              const sid = e.target.value;
              if (!sid) {
                setSession(null);
                setInfo(null);
                setDownload(null);
                setExtract(null);
                return;
              }
              void openSession(sid);
            }}
          >
            <option value="">— nouvelle session —</option>
            {sessions.map((s) => (
              <option key={s.sid} value={s.sid}>
                {s.title || s.sid}
                {s.video_exists ? "" : " (vidéo absente)"}
              </option>
            ))}
          </select>
          {session && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              title="Supprime la session, la vidéo téléchargée et les clips produits"
              onClick={async () => {
                if (!session) return;
                if (!window.confirm(`Supprimer la session « ${session.title} », sa vidéo et ses clips ?`))
                  return;
                try {
                  await call(`/api/clips/sessions/${session.sid}`, { method: "DELETE" });
                  setSession(null);
                  setInfo(null);
                  setDownload(null);
                  setExtract(null);
                  void refreshSessions();
                } catch (e) {
                  setStartError(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              <Trash2 size={14} /> Nettoyage
            </Button>
          )}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[340px_minmax(0,1fr)] overflow-hidden">
        {/* ---- GAUCHE : les 4 etapes ---- */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto border-r border-border p-3">
          <div className="panel p-3">
            <div className="panel-title">1 · Source</div>
            <div className="mt-2 space-y-2">
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=…"
                disabled={busy}
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1"
                  disabled={!url.trim() || busy}
                  onClick={() => void start("/api/clips/info", { url: url.trim() })}
                >
                  {busy && job?.kind === "clips_info" ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Info size={14} />
                  )}
                  Infos
                </Button>
                <Button
                  size="sm"
                  className="flex-1"
                  disabled={!url.trim() || busy}
                  onClick={() => void start("/api/clips/download", { url: url.trim() })}
                >
                  {busy && job?.kind === "clips_download" ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Download size={14} />
                  )}
                  Télécharger
                </Button>
              </div>
            </div>

            {info && (
              <div className="mt-2 rounded-md border border-border p-2 text-xs">
                <div className="font-medium">{info.title}</div>
                <div className="mt-1 text-muted-foreground">
                  Durée {info.duration_display} · {info.formats} formats
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {info.subtitles.length > 0 && <Badge variant="secondary">SOUS-TITRES : {info.subtitles.join(", ")}</Badge>}
                  {info.auto_captions.length > 0 && (
                    <Badge variant="outline">AUTO : {info.auto_captions.join(", ")}</Badge>
                  )}
                  {!info.subtitles.length && !info.auto_captions.length && (
                    <Badge variant="warning">aucun sous-titre</Badge>
                  )}
                </div>
              </div>
            )}

            {download && (
              <div className="mt-2 rounded-md border border-border p-2 text-xs">
                <div className="font-medium">{download.title}</div>
                <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                  {download.video_name} · {formatBytes(download.video_size_bytes)}
                </div>
                <div className="mt-1 text-muted-foreground">
                  {download.subtitle_name
                    ? `${download.segment_count} segments · ${download.transcript_chars} caractères`
                    : "aucun sous-titre récupéré"}
                </div>
                {download.warning && (
                  <p className="mt-1 text-warning">{download.warning}</p>
                )}
              </div>
            )}
          </div>

          <div className="panel p-3">
            <div className="panel-title">2 · Analyse Groq</div>
            <Slider
              className="mt-2"
              label="Nombre de clips recherchés"
              display={`${numClips}`}
              min={1}
              max={20}
              step={1}
              value={[numClips]}
              onValueChange={([v]) => setNumClips(v)}
            />
            <Button
              size="sm"
              className="mt-2 w-full"
              disabled={!canAnalyze}
              title={
                session
                  ? session.transcript_chars > 0
                    ? undefined
                    : "Téléchargez une vidéo avec des sous-titres"
                  : "Téléchargez d'abord la vidéo"
              }
              onClick={() => session && void start("/api/clips/analyze", { sid: session.sid, num_clips: numClips })}
            >
              {busy && job?.kind === "clips_analyze" ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Wand2 size={14} />
              )}
              Analyser la transcription
            </Button>
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              {clips.length} clip(s) retenu(s) · la clé API reste sur le serveur.
            </p>
          </div>

          <div className="panel p-3">
            <div className="panel-title">3 · Extraction</div>
            <div className="mt-2 space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="fmt-landscape">Paysage 16:9 (1920×1080)</Label>
                <Switch id="fmt-landscape" checked={landscape} onCheckedChange={setLandscape} disabled={busy} />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="fmt-portrait">Portrait 9:16 (visage centré)</Label>
                <Switch id="fmt-portrait" checked={portrait} onCheckedChange={setPortrait} disabled={busy} />
              </div>
              <Button
                size="sm"
                className="w-full"
                disabled={!canExtract}
                title={
                  session?.video_exists
                    ? clips.length
                      ? undefined
                      : "Analysez la transcription d'abord"
                    : "La vidéo téléchargée est introuvable"
                }
                onClick={() =>
                  session &&
                  void start("/api/clips/extract", {
                    sid: session.sid,
                    clip_indexes: selectedIndexes,
                    landscape,
                    portrait,
                  })
                }
              >
                {busy && job?.kind === "clips_extract" ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <ScanSearch size={14} />
                )}
                Extraire {selectedIndexes.length} clip(s)
              </Button>
              {!landscape && !portrait && (
                <p className="text-[11px] text-warning">Choisissez au moins un format.</p>
              )}
            </div>
          </div>

          <ErrorNote>{startError}</ErrorNote>
        </section>

        {/* ---- DROITE : transcription, clips, resultats ---- */}
        <section className="flex min-h-0 flex-col gap-3 overflow-y-auto p-3">
          <div className="panel p-3">
            <div className="flex items-center justify-between">
              <div className="panel-title">Transcription</div>
              {session && (
                <span className="text-[11px] text-muted-foreground">
                  {session.segment_count} segments · {session.transcript_chars} caractères
                  {session.transcript_truncated ? " · aperçu tronqué" : ""}
                </span>
              )}
            </div>
            {session ? (
              <Textarea
                readOnly
                className="mt-2 max-h-56 font-mono text-[11px]"
                value={session.transcript || "Transcription vide."}
              />
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">
                Aucune session chargée : téléchargez une vidéo pour lire sa transcription.
              </p>
            )}
            {!session?.video_exists && session && (
              <p className="mt-1.5 text-[11px] text-warning">
                Le fichier vidéo de cette session n'est plus sur le disque — relancez le téléchargement.
              </p>
            )}
          </div>

          {clips.length > 0 && (
            <div className="panel p-3">
              <div className="flex items-center justify-between">
                <div className="panel-title">Clips détectés</div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    setSelected(
                      Object.fromEntries(clips.map((cl) => [cl.index, selectedIndexes.length !== clips.length])),
                    )
                  }
                >
                  {selectedIndexes.length === clips.length ? "Tout désélectionner" : "Tout sélectionner"}
                </Button>
              </div>
              <ul className="mt-2 space-y-2">
                {clips.map((cl) => (
                  <li key={cl.index} className="rounded-md border border-border p-2 text-xs">
                    <div className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        className="mt-1 accent-primary"
                        checked={selected[cl.index] !== false}
                        disabled={busy}
                        onChange={(e) => setSelected((prev) => ({ ...prev, [cl.index]: e.target.checked }))}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{cl.title}</span>
                          <Badge variant={cl.social_score >= 75 ? "success" : "secondary"}>
                            score {cl.social_score}/100
                          </Badge>
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {cl.start_time} → {cl.end_time} · {formatDuration(cl.duration)}
                          </span>
                        </div>
                        {cl.hook && <p className="mt-1 text-foreground/80 italic">{cl.hook}</p>}
                        {cl.description && (
                          <p className="mt-1 text-[11px] text-muted-foreground">{cl.description}</p>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(session?.produced.length || extract) && (
            <div className="panel p-3">
              <div className="panel-title">Clips produits</div>
              {extract && (
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  {extract.files.length} fichier(s) sur {extract.requested} clip(s) × {extract.formats.length} format(s)
                  {extract.errors.length > 0 ? ` · ${extract.errors.length} échec(s)` : ""} · dossier{" "}
                  <code className="text-[11px]">clips/{extract.output_folder}/</code>
                </p>
              )}
              <div className="mt-2 grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
                {(session?.produced ?? []).map((f) => (
                  <figure key={f.url} className="rounded-md border border-border p-2">
                    <video controls preload="metadata" src={f.url} className="w-full rounded bg-black" />
                    <figcaption className="mt-1.5 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <Badge variant={f.format === "portrait" ? "default" : "secondary"}>
                          {f.format === "portrait" ? "9:16" : "16:9"}
                        </Badge>
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {formatBytes(f.size_bytes)}
                        </span>
                      </div>
                      <p className="truncate text-xs font-medium" title={f.title}>
                        {f.title}
                      </p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {f.width && f.height ? `${f.width}×${f.height}` : "dimensions inconnues"} ·{" "}
                        {formatDuration(f.duration)}
                      </p>
                      {f.unreadable && (
                        <p className="text-[11px] text-warning">Fichier illisible (vérification impossible)</p>
                      )}
                      <a
                        className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                        href={f.url}
                        download={f.name}
                      >
                        <FolderOpen size={11} /> {f.name}
                      </a>
                    </figcaption>
                  </figure>
                ))}
              </div>
              {extract?.errors.length ? (
                <ul className="mt-2 space-y-1 text-[11px] text-destructive">
                  {extract.errors.map((er, i) => (
                    <li key={`${er.clip}-${er.format}-${i}`}>
                      {er.clip} ({er.format}) : {er.error}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}

          <JobStatus
            job={job}
            pollError={pollError}
            runningLabel="Opération en cours…"
            onCancel={() => jobId && void cancelJob(jobId)}
            doneMessage={
              job?.kind === "clips_extract"
                ? `${extract?.files.length ?? session?.produced.length ?? 0} clip(s) produit(s).`
                : job?.kind === "clips_analyze"
                  ? `${clips.length} clip(s) identifié(s).`
                  : job?.kind === "clips_download"
                    ? `Session ouverte : ${download?.title ?? ""}`
                    : info
                      ? `Infos lues : ${info.title}`
                      : undefined
            }
          />
        </section>
      </div>
    </div>
  );
}
