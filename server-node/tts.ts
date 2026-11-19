import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PIPER_CATALOG_PATH = path.join(__dirname, "piper_voices.json");

export interface TtsVoice {
  id: string;
  label: string;
  language: string;
  engine: "piper" | "kokoro";
  gender?: string;
  quality?: string;
  download_url?: string;
  config_url?: string;
  files?: Array<{ name: string; url: string; size?: number }>;
  installed?: boolean;
}

let cachedCatalog: TtsVoice[] | null = null;

export function catalog(): TtsVoice[] {
  if (cachedCatalog) return cachedCatalog;
  const voices: TtsVoice[] = [];
  if (fs.existsSync(PIPER_CATALOG_PATH)) {
    try {
      const raw = JSON.parse(fs.readFileSync(PIPER_CATALOG_PATH, "utf8")) as Record<string, any>;
      const list = Array.isArray(raw) ? raw : Array.isArray(raw.voices) ? raw.voices : Object.values(raw);
      for (const item of list) {
        if (!item || typeof item !== "object" || !item.id) continue;
        voices.push({
          id: String(item.id),
          label: String(item.label || item.name || item.id),
          language: String(item.language || item.lang || "en").split(/[-_]/)[0].toLowerCase(),
          engine: "piper",
          gender: String(item.gender || ""),
          quality: String(item.quality || "medium"),
          download_url: item.download_url || item.onnx_url,
          config_url: item.config_url,
          files: Array.isArray(item.files) ? item.files : undefined,
        });
      }
    } catch {
      // ignore corrupt catalog
    }
  }
  // Ensure curated FR, EN, AR voices always exist cleanly in catalog
  const ensure = (v: TtsVoice) => {
    if (!voices.some((x) => x.id === v.id)) voices.unshift(v);
  };
  ensure({
    id: "ar_JO-kareem-medium",
    label: "Kareem (Arabe)",
    language: "ar",
    engine: "piper",
    gender: "male",
    quality: "medium",
  });
  ensure({
    id: "en_US-lessac-medium",
    label: "Lessac (English)",
    language: "en",
    engine: "piper",
    gender: "female",
    quality: "medium",
  });
  ensure({
    id: "fr_FR-siwis-medium",
    label: "Siwis (Français)",
    language: "fr",
    engine: "piper",
    gender: "female",
    quality: "medium",
  });
  cachedCatalog = voices;
  return voices;
}

export function voiceById(voiceId: string): TtsVoice {
  const found = catalog().find((v) => v.id === voiceId);
  if (!found) {
    throw new Error(`Voix TTS inconnue : '${voiceId}'.`);
  }
  return found;
}

/**
 * P3 : Sélection automatique de la voix en fonction de la langue demandée.
 */
export function pickVoiceForLanguage(lang: string, ttsModelsDir?: string): TtsVoice | null {
  const code = String(lang || "fr").trim().toLowerCase().split(/[-_]/)[0];
  const matches = catalog().filter((v) => v.language === code);
  if (matches.length === 0) return null;
  if (ttsModelsDir) {
    const installed = matches.find((v) => isVoiceInstalled(v.id, ttsModelsDir));
    if (installed) return installed;
  }
  return matches[0];
}

function commandExists(cmd: string): boolean {
  try {
    execFileSync("which", [cmd], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

export function isVoiceInstalled(voiceId: string, ttsModelsDir: string): boolean {
  const onnx = path.join(ttsModelsDir, `${voiceId}.onnx`);
  return fs.existsSync(onnx);
}

export function status(ttsModelsDir: string): Record<string, unknown> {
  const piperInstalled = commandExists("piper");
  const voices = catalog().map((v) => ({
    ...v,
    installed: isVoiceInstalled(v.id, ttsModelsDir),
  }));
  return {
    engines: {
      piper: {
        available: piperInstalled,
        reason: piperInstalled ? "Binaire piper detecte." : "Binaire 'piper' absent du systeme.",
      },
      kokoro: {
        available: false,
        reason: "Moteur Kokoro Python non installe dans le runtime Node.js.",
      },
    },
    voices,
    installed_count: voices.filter((v) => v.installed).length,
    models_dir: path.basename(ttsModelsDir),
  };
}

export async function downloadVoice(
  voiceId: string,
  ttsModelsDir: string,
  opts: { progress?: (c: number, t: number, msg: string) => void; cancel?: () => void } = {},
): Promise<Record<string, unknown>> {
  const voice = voiceById(voiceId);
  fs.mkdirSync(ttsModelsDir, { recursive: true });
  const files = voice.files || (voice.download_url ? [{ name: `${voice.id}.onnx`, url: voice.download_url }] : []);
  if (files.length === 0) {
    throw new Error(`Aucune URL de telechargement declaree pour ${voice.id}.`);
  }
  for (let i = 0; i < files.length; i++) {
    opts.cancel?.();
    const f = files[i];
    opts.progress?.(i, files.length, `Telechargement ${f.name}…`);
    const res = await fetch(f.url);
    if (!res.ok) throw new Error(`Telechargement echoue (${res.status}) pour ${f.name}`);
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(path.join(ttsModelsDir, path.basename(f.name)), buf);
  }
  opts.progress?.(1, 1, "Voix prete.");
  return { voice_id: voice.id, installed: true };
}

export async function synthesize(
  text: string,
  voiceId: string,
  ttsModelsDir: string,
  outWavPath: string,
  opts: { speed?: number; progress?: (c: number, t: number, msg: string) => void; cancel?: () => void } = {},
): Promise<{ duration: number; sample_rate: number; voice: string; engine: string }> {
  const voice = voiceById(voiceId);
  opts.cancel?.();
  if (!commandExists("piper")) {
    throw new Error(
      "Synthese vocale locale indisponible : binaire 'piper' non installe sur ce serveur.",
    );
  }
  const modelFile = path.join(ttsModelsDir, `${voice.id}.onnx`);
  if (!fs.existsSync(modelFile)) {
    throw new Error(`Modele vocal '${voice.id}' non telecharge. Telechargez-le d'abord.`);
  }
  opts.progress?.(0.3, 1.0, `Synthese vocale (${voice.label})…`);
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const execFileAsync = promisify(execFile);
  await execFileAsync(
    "piper",
    ["--model", modelFile, "--output_file", outWavPath, "--length_scale", String(1 / (opts.speed || 1.0))],
    { timeout: 120_000 },
  );
  opts.progress?.(1.0, 1.0, "Synthese terminee.");
  const stat = fs.statSync(outWavPath);
  const estDuration = Math.max(0.5, (stat.size - 44) / (22050 * 2));
  return {
    duration: Math.round(estDuration * 100) / 100,
    sample_rate: 22050,
    voice: voice.id,
    engine: "piper",
  };
}
