import React from "react";
import { Download, Trash2 } from "lucide-react";
import { Button } from "../components/ui/button";
import { Slider } from "../components/ui/slider";
import {
  api,
  apiErrorMessage,
  type TtsGenerateResult,
  type TtsStatus,
} from "../api/client";
import { cancelJob, useJobPolling } from "../lib/jobs";
import { ErrorNote, JobStatus } from "../components/job-status";
import { VoiceSelect } from "../components/VoiceSelect";

/**
 * Section « Voix off » autonome.
 *
 * Génération d'un WAV à partir d'un texte, sans projet ni scène : le fichier
 * part dans media/ et reste téléchargeable ici. Le catalogue (Piper + Kokoro,
 * 53 langues) est celui renvoyé par /api/tts/status ; rien n'est téléchargé
 * sans un clic explicite sur la voix choisie.
 */

interface Result extends TtsGenerateResult {
  text: string;
  at: number;
}

const MAX_CHARS = 5000;

export default function TtsPage() {
  const [status, setStatus] = React.useState<TtsStatus | null>(null);
  const [statusError, setStatusError] = React.useState("");
  const [text, setText] = React.useState("");
  const [voiceId, setVoiceId] = React.useState("piper-fr-siwis");
  const [speed, setSpeed] = React.useState(1.0);
  const [downloadJobId, setDownloadJobId] = React.useState<string | null>(null);
  const [generateJobId, setGenerateJobId] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState("");
  const [results, setResults] = React.useState<Result[]>([]);

  const refreshStatus = React.useCallback(() => {
    api
      .ttsStatus()
      .then((s) => {
        setStatus(s);
        setStatusError("");
      })
      .catch((e) => setStatusError(apiErrorMessage(e)));
  }, []);
  React.useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const downloadPoll = useJobPolling(downloadJobId);
  const generatePoll = useJobPolling(generateJobId);

  const dlDoneRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    const job = downloadPoll.job;
    if (job && job.status === "done" && dlDoneRef.current !== job.id) {
      dlDoneRef.current = job.id;
      refreshStatus();
    }
  }, [downloadPoll.job, refreshStatus]);

  const genDoneRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    const job = generatePoll.job;
    if (job && job.status === "done" && job.result && genDoneRef.current !== job.id) {
      genDoneRef.current = job.id;
      const result = job.result as TtsGenerateResult;
      setResults((current) => [{ ...result, text, at: Date.now() }, ...current].slice(0, 12));
    }
  }, [generatePoll.job, text]);

  const voices = status?.voices ?? [];
  const voice = voices.find((v) => v.id === voiceId) ?? null;
  const engine = voice ? status?.engines[voice.engine] : null;
  const engineAvailable = Boolean(engine?.available);
  const busy =
    downloadPoll.job?.status === "running" || generatePoll.job?.status === "running";

  const startDownload = () => {
    setActionError("");
    api
      .ttsDownload(voiceId)
      .then((r) => setDownloadJobId(r.job_id))
      .catch((e) => setActionError(apiErrorMessage(e)));
  };
  const startGenerate = () => {
    setActionError("");
    api
      .ttsGenerate({ text, voice_id: voiceId, speed })
      .then((r) => setGenerateJobId(r.job_id))
      .catch((e) => setActionError(apiErrorMessage(e)));
  };

  const languages = new Set(voices.map((v) => v.language)).size;

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="text-lg font-semibold">Voix off (TTS)</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Synthèse vocale locale, sans service cloud : le texte reste sur ce poste. Choisissez une
        langue et une voix, générez, écoutez et téléchargez le WAV.
      </p>

      <div className="panel mt-4 max-w-2xl p-4">
        <div className="panel-title">Générer une voix off</div>

        {statusError && <ErrorNote>{statusError}</ErrorNote>}

        <label className="mt-3 block">
          <span className="field-label">texte à lire</span>
          <textarea
            className="input-base min-h-[92px] resize-y font-medium"
            value={text}
            placeholder="Bonjour, voici une voix off…"
            maxLength={MAX_CHARS}
            onChange={(e) => setText(e.target.value)}
          />
          <span className="mt-0.5 block text-[11px] text-muted-foreground">
            {text.length}/{MAX_CHARS} caractères
          </span>
        </label>

        <div className="mt-3">
          <span className="field-label">voix</span>
          <VoiceSelect voices={voices} value={voiceId} onChange={setVoiceId} />
          {voice && (
            <span className="mt-1 block text-[11px] text-muted-foreground">
              {voice.engine === "piper" ? "Piper" : "Kokoro"} ·{" "}
              {voice.downloaded ? "téléchargée sur ce poste" : `à télécharger (~${voice.approx_mb} Mo)`}
              {voice.quality ? ` · qualité ${voice.quality}` : ""}
            </span>
          )}
        </div>

        <div className="mt-3">
          <Slider
            label="vitesse"
            display={`${speed.toFixed(2)}×`}
            min={0.5}
            max={2}
            step={0.05}
            value={[speed]}
            onValueChange={([v]) => setSpeed(v)}
          />
        </div>

        {voice && !engineAvailable && (
          <div className="mt-3">
            <ErrorNote>{engine?.reason || "Moteur indisponible : installez requirements.txt."}</ErrorNote>
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          {voice && engineAvailable && !voice.downloaded && (
            <Button size="sm" variant="secondary" onClick={startDownload} disabled={busy}>
              Télécharger la voix (~{voice.approx_mb} Mo)
            </Button>
          )}
          <Button size="sm" onClick={startGenerate} disabled={busy || !text.trim() || !voice?.ready}>
            Générer la voix off
          </Button>
        </div>

        <div className="mt-3">
          <JobStatus
            job={downloadPoll.job}
            pollError={downloadPoll.pollError}
            runningLabel="Téléchargement de la voix…"
            onCancel={
              downloadJobId && downloadPoll.job?.status === "running"
                ? () => void cancelJob(downloadJobId)
                : undefined
            }
          />
          <JobStatus
            job={generatePoll.job}
            pollError={generatePoll.pollError}
            runningLabel="Synthèse vocale…"
            onCancel={
              generateJobId && generatePoll.job?.status === "running"
                ? () => void cancelJob(generateJobId)
                : undefined
            }
            doneMessage={
              generatePoll.job?.status === "done"
                ? `Voix off prête (${results.length} dans cette session).`
                : undefined
            }
          />
        </div>

        {actionError && <ErrorNote>{actionError}</ErrorNote>}

        <p className="mt-3 text-[11px] text-muted-foreground">
          {voices.length} voix disponibles dans {languages} langues, réparties entre Piper et
          Kokoro. Utilisez le filtre pour retrouver une langue (arabe, anglais, français…).
        </p>
      </div>

      {results.length > 0 && (
        <div className="panel mt-4 max-w-2xl p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="panel-title">Générations de cette session</div>
            <button
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground"
              onClick={() => setResults([])}
              title="Vider la liste (les fichiers restent dans media/)"
            >
              <Trash2 size={12} /> Vider
            </button>
          </div>
          <ul className="mt-3 flex flex-col gap-3">
            {results.map((item) => (
              <li key={`${item.media_id}-${item.at}`} className="rounded-md border border-border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="truncate text-xs text-muted-foreground">
                    {item.voice} · {item.engine} · {item.duration.toFixed(1)} s ·{" "}
                    {item.sample_rate} Hz
                  </span>
                  <a
                    className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-foreground hover:bg-accent"
                    href={item.url}
                    download={`voix-off-${item.media_id}.wav`}
                  >
                    <Download size={12} /> Télécharger le WAV
                  </a>
                </div>
                <p className="mt-1.5 line-clamp-2 text-sm">{item.text}</p>
                <audio controls src={item.url} className="mt-2 w-full" />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
