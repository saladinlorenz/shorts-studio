import React from "react";
import { ArrowDown, ArrowUp, Film, Plus, Scissors, Trash2 } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Slider } from "../components/ui/slider";
import { Switch } from "../components/ui/switch";
import {
  api,
  apiErrorMessage,
  type Edl,
  type EdlCut,
  type MediaAsset,
  type MontageResult,
  type MontageValidation,
} from "../api/client";
import { cancelJob, formatBytes, formatDuration, useJobPolling } from "../lib/jobs";
import { ErrorNote, JobStatus } from "../components/job-status";

/**
 * Section « Montage footage » autonome.
 *
 * Un éditeur d'EDL fermé (edit decision list) : POST /api/montage/validate et
 * POST /api/montage (rendu FFmpeg en job avec vitesse, loudnorm et sous-titres
 * incrustés). Aucune source distante : les plans ne référencent que des rushes
 * déjà ingérés media://, choisis dans la médiathèque.
 */

const ROLES = ["hook", "body", "broll", "quote", "detail", "transition", "end"] as const;
const TRANSITIONS = ["cut", "fade", "dissolve", "wipeleft", "slideup"] as const;
const GRADES = ["none", "warm", "cool", "sepia", "mono", "teal_orange"] as const;

const CANVAS_PRESETS = [
  { label: "16:9 · 1920×1080", width: 1920, height: 1080 },
  { label: "9:16 · 1080×1920", width: 1080, height: 1920 },
  { label: "1:1 · 1080×1080", width: 1080, height: 1080 },
];

interface CutState {
  media: string;
  in: number;
  out: number;
  speed: number;
  role: string;
  transitionType: string;
  transitionDuration: number;
}

const MAX_CUTS = 80;

function newCut(media: string): CutState {
  return { media, in: 0, out: 5, speed: 1, role: "body", transitionType: "cut", transitionDuration: 0.5 };
}

function toNumber(value: string): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function parseSubtitleCues(raw: string): Array<{ start: number; end: number; text: string }> {
  const cues: Array<{ start: number; end: number; text: string }> = [];
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const m = trimmed.match(/^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*[|:]\s*(.+)$/);
    if (m) {
      const start = Number(m[1]);
      const end = Number(m[2]);
      const text = m[3].trim();
      if (Number.isFinite(start) && Number.isFinite(end) && end > start && text) {
        cues.push({ start, end, text });
      }
    }
  }
  return cues;
}

export default function MontagePage() {
  const [videos, setVideos] = React.useState<MediaAsset[]>([]);
  const [musics, setMusics] = React.useState<MediaAsset[]>([]);
  const [assetsError, setAssetsError] = React.useState("");

  const [canvas, setCanvas] = React.useState({ width: 1920, height: 1080, fps: 30 });
  const [cuts, setCuts] = React.useState<CutState[]>([]);
  const [music, setMusic] = React.useState("");
  const [gainDb, setGainDb] = React.useState(-18);
  const [duck, setDuck] = React.useState(true);
  const [fadeIn, setFadeIn] = React.useState(1);
  const [fadeOut, setFadeOut] = React.useState(2);
  const [loudnorm, setLoudnorm] = React.useState(true);
  const [subtitlesEnabled, setSubtitlesEnabled] = React.useState(false);
  const [subtitlesPosition, setSubtitlesPosition] = React.useState<"bottom" | "center">("bottom");
  const [subtitlesFontSize, setSubtitlesFontSize] = React.useState(44);
  const [subtitlesColor, setSubtitlesColor] = React.useState("#ffffff");
  const [cuesText, setCuesText] = React.useState("0.0-2.5 | L'accroche de votre vidéo\n2.5-5.0 | Le message clé");
  const [gradeLook, setGradeLook] = React.useState<string>("none");
  const [saturation, setSaturation] = React.useState(1);
  const [contrast, setContrast] = React.useState(1);

  const [name, setName] = React.useState("montage");
  const [overwrite, setOverwrite] = React.useState(false);

  const [validation, setValidation] = React.useState<MontageValidation | null>(null);
  const [validating, setValidating] = React.useState(false);
  const [actionError, setActionError] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);

  React.useEffect(() => {
    Promise.all([api.folderAssets("video"), api.folderAssets("audio")])
      .then(([v, a]) => {
        setVideos(v.assets);
        setMusics(a.assets);
        setAssetsError("");
      })
      .catch((e) => setAssetsError(apiErrorMessage(e)));
  }, []);

  const renderPoll = useJobPolling(jobId);
  const busy = renderPoll.job?.status === "running";

  // Toute édition invalide le contrôle précédent : on ne rend jamais un plan périmé.
  const touch = () => {
    setValidation(null);
    setActionError("");
  };

  const buildEdl = React.useCallback((): Edl => {
    const edlCuts: EdlCut[] = cuts.map((c) => ({
      media: c.media,
      in: c.in,
      out: c.out,
      speed: c.speed,
      role: c.role,
      transition: {
        type: c.transitionType,
        duration: c.transitionType === "cut" ? 0 : c.transitionDuration,
      },
    }));
    const cues = subtitlesEnabled ? parseSubtitleCues(cuesText) : [];
    return {
      version: 1,
      canvas,
      cuts: edlCuts,
      audio: {
        ...(music ? { music, gain_db: gainDb, duck, fade_in: fadeIn, fade_out: fadeOut } : {}),
        loudnorm,
      },
      grade: { look: gradeLook, saturation, contrast },
      subtitles: subtitlesEnabled
        ? {
            enabled: true,
            burn_in: true,
            style: {
              font_size: subtitlesFontSize,
              color: subtitlesColor,
              position: subtitlesPosition,
            },
            cues,
          }
        : { enabled: false, burn_in: false },
    };
  }, [
    cuts,
    canvas,
    music,
    gainDb,
    duck,
    fadeIn,
    fadeOut,
    loudnorm,
    subtitlesEnabled,
    subtitlesPosition,
    subtitlesFontSize,
    subtitlesColor,
    cuesText,
    gradeLook,
    saturation,
    contrast,
  ]);

  const updateCut = (index: number, patch: Partial<CutState>) => {
    touch();
    setCuts((current) => current.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  };
  const addCut = () => {
    touch();
    setCuts((current) =>
      current.length >= MAX_CUTS ? current : [...current, newCut(videos[0]?.ref ?? "")],
    );
  };
  const removeCut = (index: number) => {
    touch();
    setCuts((current) => current.filter((_, i) => i !== index));
  };
  const moveCut = (index: number, dir: -1 | 1) => {
    touch();
    setCuts((current) => {
      const target = index + dir;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const validate = () => {
    setValidating(true);
    setActionError("");
    api
      .validateMontage(buildEdl())
      .then((v) => setValidation(v))
      .catch((e) => setActionError(apiErrorMessage(e)))
      .finally(() => setValidating(false));
  };

  const render = () => {
    setActionError("");
    api
      .startMontage(buildEdl(), name.trim() || "montage", overwrite)
      .then((r) => setJobId(r.job_id))
      .catch((e) => setActionError(apiErrorMessage(e)));
  };

  const result =
    renderPoll.job?.status === "done" ? (renderPoll.job.result as MontageResult) : null;
  const canRender = Boolean(validation?.valid) && Boolean(name.trim()) && !busy;

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="flex items-center gap-2 text-lg font-semibold">
        <Scissors size={18} /> Montage footage
      </h1>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
        Assemblez des rushes déjà importés en une vraie vidéo : plans, transitions, musique et
        étalonnage. Le rendu est confié à FFmpeg (pas Remotion) et ne référence que des médias
        locaux <span className="font-mono">media://</span>. Validez le plan, puis rendez-le.
      </p>

      {assetsError && (
        <div className="mt-4 max-w-3xl">
          <ErrorNote>{assetsError}</ErrorNote>
        </div>
      )}
      {!assetsError && videos.length === 0 && (
        <div className="mt-4 max-w-3xl rounded-md border border-warning/50 bg-warning/10 p-3 text-xs text-warning">
          Aucun rush vidéo dans la médiathèque. Connectez un dossier de vidéos dans Réglages, puis
          scannez-le pour alimenter cette page.
        </div>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_360px]">
        {/* Colonne gauche : les plans */}
        <div className="panel p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="panel-title">Plans ({cuts.length}/{MAX_CUTS})</div>
            <Button size="sm" variant="secondary" onClick={addCut} disabled={cuts.length >= MAX_CUTS}>
              <Plus size={14} /> Ajouter un plan
            </Button>
          </div>

          {cuts.length === 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              Aucun plan pour l'instant. Ajoutez un plan, choisissez un rush et ses bornes (en
              secondes).
            </p>
          )}

          <ul className="mt-3 flex flex-col gap-3">
            {cuts.map((cut, index) => (
              <li key={index} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <Film size={13} /> Plan {index + 1}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
                      onClick={() => moveCut(index, -1)}
                      disabled={index === 0}
                      title="Monter"
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
                      onClick={() => moveCut(index, 1)}
                      disabled={index === cuts.length - 1}
                      title="Descendre"
                    >
                      <ArrowDown size={14} />
                    </button>
                    <button
                      className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      onClick={() => removeCut(index)}
                      title="Retirer le plan"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <label className="block sm:col-span-2">
                    <span className="field-label">rush</span>
                    <select
                      className="input-base"
                      value={cut.media}
                      onChange={(e) => updateCut(index, { media: e.target.value })}
                    >
                      <option value="">— choisir un rush —</option>
                      {videos.map((v) => (
                        <option key={v.media_id} value={v.ref}>
                          {v.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="block">
                    <span className="field-label">début (s)</span>
                    <Input
                      type="number"
                      min={0}
                      step={0.1}
                      value={cut.in}
                      onChange={(e) => updateCut(index, { in: toNumber(e.target.value) })}
                    />
                  </label>
                  <label className="block">
                    <span className="field-label">fin (s)</span>
                    <Input
                      type="number"
                      min={0}
                      step={0.1}
                      value={cut.out}
                      onChange={(e) => updateCut(index, { out: toNumber(e.target.value) })}
                    />
                  </label>

                  <label className="block">
                    <span className="field-label">rôle</span>
                    <select
                      className="input-base"
                      value={cut.role}
                      onChange={(e) => updateCut(index, { role: e.target.value })}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="field-label">vitesse (×)</span>
                    <Input
                      type="number"
                      min={0.25}
                      max={4}
                      step={0.25}
                      value={cut.speed}
                      onChange={(e) => updateCut(index, { speed: Math.max(0.25, Math.min(4, toNumber(e.target.value) || 1)) })}
                    />
                  </label>
                  <label className="block">
                    <span className="field-label">transition vers ce plan</span>
                    <select
                      className="input-base"
                      value={cut.transitionType}
                      onChange={(e) => updateCut(index, { transitionType: e.target.value })}
                      disabled={index === 0}
                    >
                      {TRANSITIONS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </label>

                  {cut.transitionType !== "cut" && index > 0 && (
                    <label className="block sm:col-span-2">
                      <span className="field-label">durée de transition (s)</span>
                      <Input
                        type="number"
                        min={0.1}
                        max={2}
                        step={0.1}
                        value={cut.transitionDuration}
                        onChange={(e) =>
                          updateCut(index, { transitionDuration: toNumber(e.target.value) })
                        }
                      />
                    </label>
                  )}
                </div>
                {index === 0 && (
                  <p className="mt-1.5 text-[11px] text-muted-foreground">
                    Le premier plan n'a pas de transition (coupes franches ensuite).
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>

        {/* Colonne droite : réglages + contrôle + rendu */}
        <div className="flex flex-col gap-4">
          <div className="panel p-4">
            <div className="panel-title">Canevas</div>
            <label className="mt-3 block">
              <span className="field-label">format</span>
              <select
                className="input-base"
                value={`${canvas.width}x${canvas.height}`}
                onChange={(e) => {
                  const preset = CANVAS_PRESETS.find(
                    (p) => `${p.width}x${p.height}` === e.target.value,
                  );
                  if (preset) {
                    touch();
                    setCanvas((c) => ({ ...c, width: preset.width, height: preset.height }));
                  }
                }}
              >
                {CANVAS_PRESETS.map((p) => (
                  <option key={p.label} value={`${p.width}x${p.height}`}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-3">
              <Slider
                label="images / seconde"
                display={`${canvas.fps} fps`}
                min={12}
                max={60}
                step={1}
                value={[canvas.fps]}
                onValueChange={([v]) => {
                  touch();
                  setCanvas((c) => ({ ...c, fps: v }));
                }}
              />
            </div>
          </div>

          <div className="panel p-4">
            <div className="panel-title">Musique</div>
            <label className="mt-3 block">
              <span className="field-label">piste (optionnelle)</span>
              <select
                className="input-base"
                value={music}
                onChange={(e) => {
                  touch();
                  setMusic(e.target.value);
                }}
              >
                <option value="">— aucune —</option>
                {musics.map((m) => (
                  <option key={m.media_id} value={m.ref}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            {music && (
              <div className="mt-3 flex flex-col gap-3">
                <Slider
                  label="gain"
                  display={`${gainDb} dB`}
                  min={-60}
                  max={0}
                  step={1}
                  value={[gainDb]}
                  onValueChange={([v]) => {
                    touch();
                    setGainDb(v);
                  }}
                />
                <Slider
                  label="fondu d'entrée"
                  display={`${fadeIn.toFixed(1)} s`}
                  min={0}
                  max={10}
                  step={0.5}
                  value={[fadeIn]}
                  onValueChange={([v]) => {
                    touch();
                    setFadeIn(v);
                  }}
                />
                <Slider
                  label="fondu de sortie"
                  display={`${fadeOut.toFixed(1)} s`}
                  min={0}
                  max={10}
                  step={0.5}
                  value={[fadeOut]}
                  onValueChange={([v]) => {
                    touch();
                    setFadeOut(v);
                  }}
                />
                <label className="flex items-center justify-between gap-2">
                  <span className="field-label">ducking sous la voix</span>
                  <Switch
                    checked={duck}
                    onCheckedChange={(v) => {
                      touch();
                      setDuck(v);
                    }}
                  />
                </label>
              </div>
            )}
            <label className="mt-3 flex items-center justify-between gap-2">
              <span className="field-label">normalisation audio (−14 LUFS)</span>
              <Switch
                checked={loudnorm}
                onCheckedChange={(v) => {
                  touch();
                  setLoudnorm(v);
                }}
              />
            </label>
          </div>

          <div className="panel p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="panel-title">Sous-titres incrustés</div>
              <Switch
                checked={subtitlesEnabled}
                onCheckedChange={(v) => {
                  touch();
                  setSubtitlesEnabled(v);
                }}
              />
            </div>
            {subtitlesEnabled && (
              <div className="mt-3 flex flex-col gap-2.5">
                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    <span className="field-label">position</span>
                    <select
                      className="input-base"
                      value={subtitlesPosition}
                      onChange={(e) => {
                        touch();
                        setSubtitlesPosition(e.target.value === "center" ? "center" : "bottom");
                      }}
                    >
                      <option value="bottom">Bas</option>
                      <option value="center">Centre</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="field-label">taille (px)</span>
                    <Input
                      type="number"
                      min={18}
                      max={96}
                      step={2}
                      value={subtitlesFontSize}
                      onChange={(e) => {
                        touch();
                        setSubtitlesFontSize(Math.max(18, Math.min(96, toNumber(e.target.value) || 44)));
                      }}
                    />
                  </label>
                </div>
                <label className="block">
                  <span className="field-label">couleur</span>
                  <Input
                    type="text"
                    value={subtitlesColor}
                    onChange={(e) => {
                      touch();
                      setSubtitlesColor(e.target.value);
                    }}
                  />
                </label>
                <label className="block">
                  <span className="field-label">répliques (début-fin | texte)</span>
                  <textarea
                    className="input-base min-h-[76px] w-full font-mono text-[11px]"
                    value={cuesText}
                    onChange={(e) => {
                      touch();
                      setCuesText(e.target.value);
                    }}
                  />
                </label>
              </div>
            )}
          </div>

          <div className="panel p-4">
            <div className="panel-title">Étalonnage</div>
            <label className="mt-3 block">
              <span className="field-label">look</span>
              <select
                className="input-base"
                value={gradeLook}
                onChange={(e) => {
                  touch();
                  setGradeLook(e.target.value);
                }}
              >
                {GRADES.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-3 flex flex-col gap-3">
              <Slider
                label="saturation"
                display={saturation.toFixed(2)}
                min={0}
                max={2}
                step={0.05}
                value={[saturation]}
                onValueChange={([v]) => {
                  touch();
                  setSaturation(v);
                }}
              />
              <Slider
                label="contraste"
                display={contrast.toFixed(2)}
                min={0}
                max={2}
                step={0.05}
                value={[contrast]}
                onValueChange={([v]) => {
                  touch();
                  setContrast(v);
                }}
              />
            </div>
          </div>

          <div className="panel p-4">
            <div className="panel-title">Contrôle et rendu</div>

            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={validate} disabled={validating || cuts.length === 0}>
                {validating ? "Contrôle…" : "Valider le plan"}
              </Button>
              <Button size="sm" onClick={render} disabled={!canRender}>
                Rendre le montage
              </Button>
            </div>

            {validation && (
              <div className="mt-3 flex flex-col gap-2">
                {validation.valid ? (
                  <div className="rounded-md border border-success/50 bg-success/10 p-2.5 text-xs text-success">
                    Plan valide : {validation.cuts} plan(s), {formatDuration(validation.duration_seconds)}.
                  </div>
                ) : (
                  <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2.5 text-xs text-destructive">
                    <div className="mb-1 font-medium">Plan invalide — erreurs indexées :</div>
                    <ul className="list-inside list-disc space-y-0.5">
                      {validation.errors.map((err, i) => (
                        <li key={i} className="break-words">{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {validation.warnings.length > 0 && (
                  <div className="rounded-md border border-warning/50 bg-warning/10 p-2.5 text-xs text-warning">
                    <ul className="list-inside list-disc space-y-0.5">
                      {validation.warnings.map((w, i) => (
                        <li key={i} className="break-words">{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {!validation && cuts.length > 0 && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Validez le plan avant de rendre : le rendu n'est proposé que pour un plan contrôlé.
              </p>
            )}

            <label className="mt-3 block">
              <span className="field-label">nom du fichier</span>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="montage"
              />
              <span className="mt-0.5 block text-[11px] text-muted-foreground">
                Sortie : exports/{(name.trim() || "montage").replace(/\.mp4$/i, "")}.mp4
              </span>
            </label>
            <label className="mt-2 flex items-center justify-between gap-2">
              <span className="field-label">écraser si le fichier existe</span>
              <Switch checked={overwrite} onCheckedChange={setOverwrite} />
            </label>

            {actionError && (
              <div className="mt-3">
                <ErrorNote>{actionError}</ErrorNote>
              </div>
            )}

            <div className="mt-3">
              <JobStatus
                job={renderPoll.job}
                pollError={renderPoll.pollError}
                runningLabel="Rendu FFmpeg du montage…"
                onCancel={
                  jobId && renderPoll.job?.status === "running"
                    ? () => void cancelJob(jobId)
                    : undefined
                }
              />
            </div>

            {result && jobId && (
              <div className="mt-3 rounded-md border border-border p-3">
                <div className="text-xs font-medium">Montage rendu</div>
                <div className="mt-1 text-[11px] text-muted-foreground">
                  {result.width}×{result.height} · {result.fps} fps · {result.cuts} plan(s) ·{" "}
                  {formatDuration(result.duration)} (prévu {formatDuration(result.planned_duration)}) ·{" "}
                  {formatBytes(result.size_bytes)} · {result.has_audio ? "audio" : "muet"} · look{" "}
                  {result.grade}
                </div>
                <video controls src={api.montageFileUrl(jobId)} className="mt-2 w-full rounded-md" />
                <a
                  className="mt-2 inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-foreground hover:bg-accent"
                  href={api.montageFileUrl(jobId)}
                  download={result.path}
                >
                  Télécharger le MP4
                </a>
                {result.warnings.length > 0 && (
                  <ul className="mt-2 list-inside list-disc space-y-0.5 text-[11px] text-warning">
                    {result.warnings.map((w, i) => (
                      <li key={i} className="break-words">{w}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}