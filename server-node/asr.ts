import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export const GROQ_WHISPER_MODELS = [
  "whisper-large-v3-turbo",
  "whisper-large-v3",
] as const;

export function localBackend(): { available: boolean; engine: string; reason: string } {
  for (const bin of ["whisper-cli", "whisper"]) {
    try {
      execFileSync("which", [bin], { stdio: "ignore" });
      return { available: true, engine: bin, reason: `Binaire ${bin} detecte.` };
    } catch {
      // continue
    }
  }
  return {
    available: false,
    engine: "none",
    reason: "Aucun moteur Whisper local installe (whisper-cli absent).",
  };
}

export function providers(opts: { groqKeyPresent: boolean }): Array<Record<string, unknown>> {
  const local = localBackend();
  return [
    {
      id: "auto",
      label: "Automatique (local puis Groq si configuré)",
      available: local.available || opts.groqKeyPresent,
      reason: local.available
        ? local.reason
        : opts.groqKeyPresent
          ? "Transcription cloud Groq prete."
          : "Ni moteur local ni cle Groq configures.",
    },
    {
      id: "local",
      label: "Whisper local",
      available: local.available,
      reason: local.reason,
    },
    {
      id: "groq",
      label: "Groq Whisper API",
      available: opts.groqKeyPresent,
      reason: opts.groqKeyPresent ? "Cle Groq configuree." : "Cle Groq non configuree.",
    },
  ];
}

export interface AsrSegment {
  start: number;
  end: number;
  text: string;
}

export interface AsrResult {
  text: string;
  language: string;
  segments: AsrSegment[];
  provider: string;
}

/**
 * P3 : Transcription optionnelle via Groq Whisper (verbose_json) avec découpage en segments.
 */
export async function transcribeWithGroq(
  audioPath: string,
  apiKey: string,
  opts: { model?: string; language?: string } = {},
): Promise<AsrResult> {
  if (!apiKey) {
    throw new Error("Cle API Groq manquante pour la transcription.");
  }
  if (!fs.existsSync(audioPath)) {
    throw new Error("Fichier audio introuvable pour la transcription.");
  }
  const blob = new Blob([fs.readFileSync(audioPath)]);
  const form = new FormData();
  form.append("file", blob, path.basename(audioPath));
  form.append("model", opts.model || GROQ_WHISPER_MODELS[0]);
  form.append("response_format", "verbose_json");
  if (opts.language) {
    form.append("language", opts.language.trim().slice(0, 8));
  }

  const res = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Groq Whisper erreur ${res.status}: ${errText.slice(0, 200)}`);
  }
  const data = (await res.json()) as Record<string, any>;
  const segments: AsrSegment[] = Array.isArray(data.segments)
    ? data.segments.map((s: any) => ({
        start: Number(s.start || 0),
        end: Number(s.end || 0),
        text: String(s.text || "").trim(),
      }))
    : [];
  return {
    text: String(data.text || "").trim(),
    language: String(data.language || opts.language || ""),
    segments,
    provider: "groq",
  };
}
