import React from "react";
import { useNavigate } from "react-router-dom";
import {
  AudioLines,
  Check,
  Copy,
  FileText,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
  WandSparkles,
} from "lucide-react";
import {
  api,
  apiErrorMessage,
  type AnalysisRecord,
  type AnalysisSummary,
  type BrandPackSummary,
  type MediaAsset,
  type MomentGenerateResult,
  type MomentItem,
  type MomentsSetup,
} from "../api/client";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ErrorNote, JobStatus } from "../components/job-status";
import { cancelJob, formatDuration, useJobPolling } from "../lib/jobs";

/**
 * Page Moments forts : transcrire, detector, puis appliquer au clic.
 *
 * Deux temps, toujours separees :
 *
 * - analyser = transcrite et scoree, ecrite dans moments/ seulement. Aucun projet
 *   de travail n'est cree la : la file SQLite et projects/ ne bougent pas ;
 * - generer = le clic qui ecrit un projet v2, son .srt jumeau, son extrait vocal et
 *   sa miniature. Ecraser un projet existant reste une option explicite.
 *
 * Les reglages de detection (duree, nombre) se rejouent sur la transcription deja
 * stockee : un « Recalculer » ne relance jamais d'appel de transcription.
 */

const KIND_LABEL: Record<string, string> = { video: "vidéo", audio: "audio" };

function Select({
  value,
  onChange,
  children,
  disabled,
  title,
}: {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      title={title}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm disabled:opacity-60"
    >
      {children}
    </select>
  );
}

function CopyField({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  if (!value) return null;
  return (
    <div className="mt-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
        <button
          className="flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted"
          onClick={onCopy}
          title={`Copier ${label.toLowerCase()}`}
        >
          {copied ? <Check size={10} /> : <Copy size={10} />}
          {copied ? "copié" : "copier"}
        </button>
      </div>
      <textarea
        readOnly
        rows={label === "titre" ? 1 : 4}
        className="input-base mt-1 w-full resize-y bg-background/60 text-xs"
        value={value}
      />
    </div>
  );
}

export default function MomentsPage() {
  const navigate = useNavigate();
  const [setup, setSetup] = React.useState<MomentsSetup | null>(null);
  const [sources, setSources] = React.useState<MediaAsset[]>([]);
  const [source, setSource] = React.useState("");
  const [provider, setProvider] = React.useState("auto");
  const [model, setModel] = React.useState("");
  const [language, setLanguage] = React.useState("");
  const [keyFromClips, setKeyFromClips] = React.useState(false);
  const [preset, setPreset] = React.useState("standard");
  const [top, setTop] = React.useState(6);

  const [analyses, setAnalyses] = React.useState<AnalysisSummary[]>([]);
  const [analysisId, setAnalysisId] = React.useState("");
  const [analysis, setAnalysis] = React.useState<AnalysisRecord | null>(null);
  const [chosen, setChosen] = React.useState<string[]>([]);

  const [brands, setBrands] = React.useState<BrandPackSummary[]>([]);
  const [brandId, setBrandId] = React.useState("");
  const [handle, setHandle] = React.useState("");
  const [fromSource, setFromSource] = React.useState(true);
  const [overwrite, setOverwrite] = React.useState(false);

  const [jobId, setJobId] = React.useState<string | null>(null);
  const [generated, setGenerated] = React.useState<MomentGenerateResult[]>([]);
  const [genErrors, setGenErrors] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [copied, setCopied] = React.useState("");
  const [uploadName, setUploadName] = React.useState("");

  const { job, pollError } = useJobPolling(jobId);

  const loadSources = React.useCallback(async () => {
    try {
      const [video, audio] = await Promise.all([api.folderAssets("video"), api.folderAssets("audio")]);
      setSources([...video.assets, ...audio.assets]);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }, []);

  const loadAnalyses = React.useCallback(async () => {
    try {
      setAnalyses((await api.momentsList()).analyses);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }, []);

  const openAnalysis = React.useCallback(async (id: string) => {
    if (!id) {
      setAnalysis(null);
      return;
    }
    try {
      setAnalysis(await api.momentsAnalysis(id));
      setChosen([]);
    } catch (e) {
      setError(apiErrorMessage(e));
      setAnalysis(null);
    }
  }, []);

  React.useEffect(() => {
    void (async () => {
      try {
        const s = await api.momentsSetup();
        setSetup(s);
        setProvider(s.default_provider || "auto");
        setModel(s.default_model || "");
        setLanguage(s.language || "");
        setTop(s.top_default || 6);
        setKeyFromClips(!s.asr_key_configured && s.clips_key_configured);
      } catch (e) {
        setError(apiErrorMessage(e));
      }
    })();
    void loadSources();
    void loadAnalyses();
    void (async () => {
      try {
        setBrands((await api.brandList()).brands);
      } catch {
        /* la génération reste possible sans pack de marque */
      }
    })();
  }, [loadAnalyses, loadSources]);

  React.useEffect(() => {
    void openAnalysis(analysisId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId]);

  // une analyse finie devient la sélection courante : c'est là que les moments sont lisibles
  React.useEffect(() => {
    if (!job || job.status !== "done") return;
    void loadAnalyses();
    const created = job.result?.analysis?.id as string | undefined;
    if (created) setAnalysisId(created);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  const window_ = setup?.duration_presets?.[preset] ?? { min_seconds: 10, max_seconds: 45 };
  const groqState = setup?.providers.find((item) => item.id === "groq");
  const localState = setup?.providers.find((item) => item.id === "local");
  const keyAvailable = provider === "local" || (keyFromClips ? setup?.clips_key_configured : setup?.asr_key_configured);
  const canAnalyze = !!source && !busy && job?.status !== "running" && (!!localState?.available || !!keyAvailable);

  const analyze = async () => {
    if (!canAnalyze) return;
    setError("");
    setGenerated([]);
    setGenErrors([]);
    try {
      const res = await api.momentsAnalyze({
        source,
        provider,
        api_key_source: keyFromClips ? "clips" : "asr",
        model: provider === "groq" ? model : "",
        language,
        min_seconds: window_.min_seconds,
        max_seconds: window_.max_seconds,
        top,
      });
      setJobId(res.job_id);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const recompute = async () => {
    if (!analysisId) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.momentsRecompute(analysisId, {
        min_seconds: window_.min_seconds,
        max_seconds: window_.max_seconds,
        top,
      });
      setAnalysis((current) =>
        current
          ? {
              ...current,
              moments: res.moments,
              summary: res.analysis ?? current.summary,
              detect: { ...window_, top, algorithm: current.detect?.algorithm ?? "score+energie" },
            }
          : current,
      );
      setChosen([]);
      void loadAnalyses();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (momentId: string) =>
    setChosen((current) =>
      current.includes(momentId) ? current.filter((id) => id !== momentId) : [...current, momentId],
    );

  /** Le seul chemin qui écrit dans projects/ : un clic, un moment, un projet. */
  const generateChosen = async () => {
    if (!analysisId || chosen.length === 0) return;
    setBusy(true);
    setError("");
    setGenErrors([]);
    const results: MomentGenerateResult[] = [];
    const failures: string[] = [];
    for (const moment of analysis?.moments ?? []) {
      if (!chosen.includes(moment.id)) continue;
      try {
        results.push(
          await api.momentsGenerate(analysisId, {
            moment_id: moment.id,
            brand_id: brandId,
            handle,
            use_source_thumbnail: fromSource,
            overwrite,
          }),
        );
      } catch (e) {
        failures.push(`${moment.id} : ${apiErrorMessage(e)}`);
      }
    }
    setGenerated(results);
    setGenErrors(failures);
    setBusy(false);
    void loadAnalyses();
  };

  const copy = async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(""), 1600);
    } catch {
      setError("Copie refusée par le navigateur : le champ reste sélectionnable à la souris.");
    }
  };

  const removeAnalysis = async (id: string) => {
    if (!window.confirm("Supprimer cette analyse ? La transcription déjà payée serait perdue ; les projets générés restent dans Projets.")) return;
    try {
      await api.momentsDelete(id);
      if (analysisId === id) {
        setAnalysisId("");
        setAnalysis(null);
      }
      void loadAnalyses();
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const upload = async (file: File) => {
    setBusy(true);
    setError("");
    setUploadName(file.name);
    try {
      const res = await api.uploadMedia(file, { source: "téléversement Moments" });
      const ref = `media://${res.id}`;
      setSources((current) => [
        { media_id: res.id, ref, name: res.filename, kind: "video", folder: "téléversé", size: res.size },
        ...current,
      ]);
      setSource(ref);
    } catch (e) {
      setError(apiErrorMessage(e));
      setUploadName("");
    } finally {
      setBusy(false);
    }
  };

  const moments = analysis?.moments ?? [];
  const transcriptWarnings = analysis?.transcript?.warnings ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold">
            <AudioLines size={20} /> Moments forts
          </h1>
          <p className="text-xs text-muted-foreground">
            Transcription Whisper d'une source importée, moments détectés et scorés — puis projet
            Remotion, sous-titres, miniature et métadonnées au clic.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void loadAnalyses()}>
          <RefreshCw size={14} className="mr-1" /> Recharger
        </Button>
      </div>

      <ErrorNote>{error}</ErrorNote>

      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        {/* ---------------- GAUCHE : source, fournisseur, réglages ---------------- */}
        <div className="space-y-4">
          <section className="panel p-4">
            <div className="panel-title">Source à transcrire</div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Un fichier déjà importé dans la médiathèque : le client ne choisit jamais un chemin.
            </p>
            <div className="mt-2">
              <Select value={source} onChange={setSource}>
                {sources.length === 0 ? (
                  <option value="">Aucun média importé</option>
                ) : (
                  <option value="">Choisir une source</option>
                )}
                {sources.map((asset) => (
                  <option key={asset.ref} value={asset.ref}>
                    {asset.name} — {KIND_LABEL[asset.kind] ?? asset.kind} · {asset.folder}
                  </option>
                ))}
              </Select>
            </div>
            <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="file"
                accept="video/*,audio/*"
                className="w-full text-[11px]"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void upload(file);
                  e.target.value = "";
                }}
              />
            </label>
            {uploadName && (
              <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
                <Loader2 size={11} className="animate-spin" /> import de {uploadName}…
              </p>
            )}
            {sources.length === 0 && !uploadName && (
              <p className="mt-1 text-[11px] text-warning">
                Médiathèque vide : connectez un dossier de médias dans Réglages, ou téléversez un
                fichier ci-dessus.
              </p>
            )}
          </section>

          <section className="panel p-4">
            <div className="panel-title">Transcription</div>
            <div className="mt-2 space-y-2">
              <label className="block text-xs">
                <span className="font-medium text-muted-foreground">Fournisseur</span>
                <Select
                  value={provider}
                  onChange={setProvider}
                  title={
                    (provider === "groq" ? groqState?.reason : localState?.reason) ||
                    "auto : tente le Whisper local, puis Groq"
                  }
                >
                  <option value="auto">auto — local d'abord, puis Groq</option>
                  {(setup?.providers ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                      {item.cloud ? " (cloud)" : ""}
                      {item.available ? "" : " — indisponible"}
                    </option>
                  ))}
                </Select>
              </label>
              {setup && (
                <p className="text-[11px] text-muted-foreground">
                  {localState?.available
                    ? `Whisper local détecté : ${localState.kind}.`
                    : localState?.reason || "Whisper local : aucun détecté."}
                </p>
              )}
              {provider === "groq" && (
                <label className="block text-xs">
                  <span className="font-medium text-muted-foreground">Modèle Groq</span>
                  <Select value={model} onChange={setModel}>
                    {(groqState?.models ?? []).map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </Select>
                </label>
              )}
              <label className="block text-xs">
                <span className="font-medium text-muted-foreground">
                  Langue {language ? "" : "(détection automatique)"}
                </span>
                <input
                  className="input-base mt-1 w-full font-mono text-xs"
                  maxLength={8}
                  value={language}
                  placeholder="fr"
                  onChange={(e) => setLanguage(e.target.value)}
                />
              </label>
              {provider !== "local" && setup?.clips_key_configured && (
                <label className="flex items-start gap-2 text-xs">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={keyFromClips}
                    onChange={(e) => setKeyFromClips(e.target.checked)}
                  />
                  <span>
                    Réutiliser la clé de Clips
                    <span className="block text-[10px] text-muted-foreground">
                      Cette clé sert uniquement à Clips ; elle n'est reprise que sur demande
                      explicite, et ne sort jamais du serveur.
                    </span>
                  </span>
                </label>
              )}
              {!keyAvailable && provider !== "local" && (
                <p className="rounded border border-warning/40 bg-warning/10 p-1.5 text-[11px] text-warning">
                  Aucune clé de transcription disponible : renseignez-la dans Réglages, ou cochez la
                  réutilisation de la clé de Clips.
                </p>
              )}
            </div>
          </section>

          <section className="panel p-4">
            <div className="panel-title">Détection</div>
            <div className="mt-2 space-y-2">
              <label className="block text-xs">
                <span className="font-medium text-muted-foreground">Bande de durée</span>
                <Select value={preset} onChange={setPreset}>
                  {Object.entries(setup?.duration_presets ?? {
                    short: { label: "Punchy (10-24 s)", min_seconds: 10, max_seconds: 24 },
                    standard: { label: "Standard (10-45 s)", min_seconds: 10, max_seconds: 45 },
                    long: { label: "Développé (20-70 s)", min_seconds: 20, max_seconds: 70 },
                  }).map(([id, item]) => (
                    <option key={id} value={id}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="block text-xs">
                <span className="font-medium text-muted-foreground">Nombre de moments</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  className="input-base mt-1 w-full"
                  value={top}
                  onChange={(e) => setTop(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                />
              </label>
              <Button size="sm" className="w-full" onClick={() => void analyze()} disabled={!canAnalyze}>
                {job?.status === "running" ? (
                  <>
                    <Loader2 size={14} className="mr-1 animate-spin" /> Analyse en cours…
                  </>
                ) : (
                  <>
                    <Sparkles size={14} className="mr-1" /> Analyser la source
                  </>
                )}
              </Button>
              <p className="text-[10px] text-muted-foreground">
                L'analyse écrit dans moments/ uniquement : aucun projet de travail n'est créé sans
                votre clic.
              </p>
            </div>
          </section>

          {job && (
            <section className="panel p-4">
              <h2 className="mb-2 text-sm font-semibold">Analyse en cours</h2>
              <JobStatus
                job={job}
                pollError={pollError}
                runningLabel="Transcription de la source…"
                onCancel={job.status === "running" && jobId ? () => void cancelJob(jobId) : undefined}
              />
            </section>
          )}

          <section className="panel overflow-hidden">
            <h2 className="border-b border-border px-4 py-2 text-sm font-semibold">
              Analyses ({analyses.length})
            </h2>
            <ul className="max-h-72 divide-y divide-border overflow-y-auto text-xs">
              {analyses.length === 0 && (
                <li className="px-3 py-2 text-muted-foreground">Aucune analyse sur ce poste.</li>
              )}
              {analyses.map((item) => (
                <li key={item.id} className="flex items-center gap-2 px-3 py-2">
                  <button
                    className="min-w-0 flex-1 text-left hover:underline"
                    onClick={() => setAnalysisId(item.id)}
                    title={item.id}
                  >
                    <span className="block truncate">{item.unreadable ? `${item.id} (illisible)` : item.source_title}</span>
                    <span className="block text-[10px] text-muted-foreground">
                      {item.unreadable
                        ? "fichier JSON illisible"
                        : `${item.moment_count} moment(s) · score ${item.best_score} · ${formatDuration(item.duration)} · ${item.provider || "?"}`}
                    </span>
                  </button>
                  <button
                    className="rounded border border-border px-1 py-0.5 text-[10px] text-muted-foreground hover:bg-muted"
                    onClick={() => void openAnalysis(item.id)}
                    title="Recharger le détail"
                  >
                    <RefreshCw size={10} />
                  </button>
                  <button
                    className="rounded border border-destructive/50 px-1 py-0.5 text-[10px] text-destructive hover:bg-destructive/10"
                    onClick={() => void removeAnalysis(item.id)}
                    title="Supprimer l'analyse (aucun projet touché)"
                  >
                    <Trash2 size={10} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {/* ---------------- DROITE : moments, génération, résultats ---------------- */}
        <div className="space-y-4">
          {!analysis && !job && (
            <section className="panel p-6 text-sm text-muted-foreground">
              Choisissez une source puis lancez une analyse, ou ouvrez une analyse existante : les
              moments détectés s'afficheront ici.
            </section>
          )}

          {analysis && (
            <section className="panel p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">{analysis.source_title || analysis.id}</h2>
                <Badge variant="outline">{analysis.summary?.provider || "inconnu"}</Badge>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                <span>{formatDuration(analysis.summary?.duration ?? 0)}</span>
                <span>{analysis.summary?.segments ?? 0} segment(s) ASR</span>
                <span>{analysis.summary?.moment_count ?? 0} moment(s) retenu(s)</span>
                {analysis.detect && (
                  <span>
                    fenêtre {analysis.detect.min_seconds}–{analysis.detect.max_seconds} s · top{" "}
                    {analysis.detect.top} · {analysis.detect.algorithm}
                  </span>
                )}
                <span>{analysis.created_at}</span>
              </div>
              {transcriptWarnings.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-[11px] text-warning">
                  {transcriptWarnings.map((w, i) => (
                    <li key={i}>— {w}</li>
                  ))}
                </ul>
              )}
              <div className="mt-3 flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => void recompute()} disabled={busy}>
                  <RefreshCw size={13} className="mr-1" /> Recalculer les moments
                </Button>
                <span className="text-[11px] text-muted-foreground">
                  sans nouvelle transcription, sur la bande de durée choisie à gauche
                </span>
              </div>
            </section>
          )}

          {moments.length > 0 && (
            <section className="panel p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">Moments détectés</h2>
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <button className="hover:underline" onClick={() => setChosen(moments.map((m) => m.id))}>
                    tout sélectionner
                  </button>
                  <button className="hover:underline" onClick={() => setChosen([])}>
                    aucun
                  </button>
                </div>
              </div>
              <ul className="mt-2 space-y-2">
                {moments.map((moment: MomentItem) => (
                  <MomentCard
                    key={moment.id}
                    moment={moment}
                    checked={chosen.includes(moment.id)}
                    onToggle={() => toggle(moment.id)}
                  />
                ))}
              </ul>
            </section>
          )}

          {analysis && moments.length === 0 && (
            <section className="panel p-4 text-xs text-muted-foreground">
              Aucun moment dans cette bande : élargissez la durée ou relancez le calcul. La
              transcription reste disponible ({analysis.summary?.segments ?? 0} segment(s)).
            </section>
          )}

          {chosen.length > 0 && (
            <section className="panel p-4">
              <div className="panel-title flex items-center gap-2">
                <WandSparkles size={14} /> Générer {chosen.length} projet(s)
              </div>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <label className="block text-xs">
                  <span className="font-medium text-muted-foreground">Pack de marque</span>
                  <Select value={brandId} onChange={setBrandId}>
                    <option value="">aucun — projet brut</option>
                    {brands.map((brand) => (
                      <option key={brand.id} value={brand.id}>
                        {brand.label}
                      </option>
                    ))}
                  </Select>
                </label>
                <label className="block text-xs">
                  <span className="font-medium text-muted-foreground">
                    Identifiant social (@…) pour les hashtags
                  </span>
                  <input
                    className="input-base mt-1 w-full font-mono text-xs"
                    placeholder="@atelier"
                    value={handle}
                    onChange={(e) => setHandle(e.target.value.trim().slice(0, 40))}
                  />
                </label>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={fromSource} onChange={(e) => setFromSource(e.target.checked)} />
                  miniature reprise de la source
                </label>
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
                  écraser un projet du même nom
                </label>
              </div>
              {!brandId && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Sans pack choisi, la marque du client n'apparaît nulle part : le texte des scènes
                  reste celui de la transcription.
                </p>
              )}
              <Button size="sm" className="mt-3" onClick={() => void generateChosen()} disabled={busy}>
                {busy ? (
                  <>
                    <Loader2 size={14} className="mr-1 animate-spin" /> Génération…
                  </>
                ) : (
                  <>
                    <Sparkles size={14} className="mr-1" /> Générer les projets
                  </>
                )}
              </Button>
            </section>
          )}

          {genErrors.length > 0 && (
            <section className="panel p-4">
              <h2 className="mb-1 text-sm font-semibold text-destructive">Générations refusées</h2>
              <ul className="space-y-1 text-[11px] text-destructive">
                {genErrors.map((message, i) => (
                  <li key={i}>— {message}</li>
                ))}
              </ul>
              {!overwrite && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Un refus « existe déjà » se lève avec l'option « écraser un projet du même nom ».
                </p>
              )}
            </section>
          )}

          {generated.map((result) => (
            <GeneratedCard key={result.name} result={result} copied={copied} onCopy={copy} onOpen={() => navigate(`/design?project=${encodeURIComponent(result.name)}`)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function MomentCard({
  moment,
  checked,
  onToggle,
}: {
  moment: MomentItem;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li className="rounded-md border border-border p-2.5">
      <label className="flex items-start gap-2 text-xs">
        <input type="checkbox" className="mt-0.5" checked={checked} onChange={onToggle} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{moment.id}</Badge>
            <span className="font-mono text-[11px] text-muted-foreground">
              {formatDuration(moment.start)} → {formatDuration(moment.end)}
            </span>
            <span className="text-[11px]">{moment.duration.toFixed(1)} s</span>
            <span className="ml-auto font-mono text-[11px]">score {moment.score}</span>
          </span>
          <span className="mt-1 block leading-snug">{moment.text}</span>
        </span>
      </label>
      <div className="mt-1.5 flex flex-wrap gap-1 pl-6 text-[10px] text-muted-foreground">
        {moment.reasons.map((reason, i) => (
          <span key={i} className="rounded border border-border/60 px-1 py-0.5">
            {reason}
          </span>
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 pl-6 text-[10px] text-muted-foreground">
        <span>{moment.cues.length} sous-titre(s)</span>
        {moment.keywords.length > 0 && <span>mots : {moment.keywords.slice(0, 6).join(", ")}</span>}
      </div>
    </li>
  );
}

function GeneratedCard({
  result,
  copied,
  onCopy,
  onOpen,
}: {
  result: MomentGenerateResult;
  copied: string;
  onCopy: (key: string, value: string) => void;
  onOpen: () => void;
}) {
  const title = result.publish.title ?? "";
  const description = result.publish.description ?? "";
  const hashtags = (result.publish.hashtags ?? []).join(" ");
  return (
    <section className="panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold">
          <FileText size={14} /> {result.name}
        </h2>
        <Button size="sm" variant="outline" onClick={onOpen}>
          Ouvrir dans Design
        </Button>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span>{formatDuration(result.duration)}</span>
        <span>{result.cues} scène(s) = sous-titre(s)</span>
        <span>{result.srt_available ? ".srt écrit" : "pas de .srt"}</span>
        <span>{result.voice_ref ? "voix isolée" : "sans voix isolée"}</span>
        <span>{result.thumbnail_ref ? "miniature importée" : "sans miniature"}</span>
      </div>
      <CopyField label="titre" value={title} copied={copied === `${result.name}-t`} onCopy={() => void onCopy(`${result.name}-t`, title)} />
      <CopyField label="description" value={description} copied={copied === `${result.name}-d`} onCopy={() => void onCopy(`${result.name}-d`, description)} />
      <CopyField label="hashtags" value={hashtags} copied={copied === `${result.name}-h`} onCopy={() => void onCopy(`${result.name}-h`, hashtags)} />
      {result.warnings.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-warning">
          {result.warnings.map((w, i) => (
            <li key={i}>— {w}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
