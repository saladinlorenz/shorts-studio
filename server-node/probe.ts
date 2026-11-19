import { execFile } from "node:child_process";
import fs from "node:fs";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export class ProbeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProbeError";
  }
}

export interface VideoProbeInfo {
  width: number;
  height: number;
  duration: number;
  fps: number;
  frames: number;
  codec: string;
  has_audio: boolean;
  audio_codec: string | null;
  audio_sample_rate: number | null;
  size_bytes: number;
}

export async function ffprobeJson(filePath: string): Promise<Record<string, any>> {
  try {
    const { stdout } = await execFileAsync(
      "ffprobe",
      [
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filePath,
      ],
      { timeout: 30_000, maxBuffer: 4 * 1024 * 1024 },
    );
    return JSON.parse(stdout) as Record<string, any>;
  } catch (err) {
    throw new ProbeError(
      `ffprobe a echoue sur ${filePath}: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

function parseRatio(rate: string | undefined): number {
  if (!rate) return 30;
  const parts = rate.split("/");
  if (parts.length === 2) {
    const num = Number(parts[0]);
    const den = Number(parts[1]);
    if (Number.isFinite(num) && Number.isFinite(den) && den > 0) {
      return Math.round((num / den) * 1000) / 1000;
    }
  }
  const n = Number(rate);
  return Number.isFinite(n) && n > 0 ? n : 30;
}

export async function probeMp4(filePath: string): Promise<VideoProbeInfo> {
  if (!fs.existsSync(filePath)) {
    throw new ProbeError(`Fichier video introuvable : ${filePath}`);
  }
  const stat = fs.statSync(filePath);
  const data = await ffprobeJson(filePath);
  const streams = Array.isArray(data.streams) ? data.streams : [];
  const vStream = streams.find((s: any) => s.codec_type === "video");
  if (!vStream) {
    throw new ProbeError("Aucun flux video detecte dans le fichier.");
  }
  const aStream = streams.find((s: any) => s.codec_type === "audio");
  const duration = Number(data.format?.duration || vStream.duration || 0);
  const fps = parseRatio(vStream.r_frame_rate || vStream.avg_frame_rate);
  const frames = Number(vStream.nb_frames) || Math.max(1, Math.round(duration * fps));
  return {
    width: Number(vStream.width || 0),
    height: Number(vStream.height || 0),
    duration: Math.round(duration * 1000) / 1000,
    fps,
    frames,
    codec: String(vStream.codec_name || "unknown"),
    has_audio: Boolean(aStream),
    audio_codec: aStream ? String(aStream.codec_name || "unknown") : null,
    audio_sample_rate: aStream && aStream.sample_rate ? Number(aStream.sample_rate) : null,
    size_bytes: stat.size,
  };
}

export async function hasAudioStream(filePath: string): Promise<boolean> {
  try {
    const data = await ffprobeJson(filePath);
    const streams = Array.isArray(data.streams) ? data.streams : [];
    return streams.some((s: any) => s.codec_type === "audio");
  } catch {
    return false;
  }
}

export interface RenderCheckReport {
  ok: boolean;
  file: string;
  probe: VideoProbeInfo;
  black_segments: number;
  silent_audio: boolean;
  warnings: string[];
  errors: string[];
}

/**
 * P8 : check_render — vérifie techniquement un MP4 rendu (flux vidéo/audio,
 * images noires via blackdetect, piste silencieuse via volumedetect).
 */
export async function checkRenderedMp4(filePath: string): Promise<RenderCheckReport> {
  const probe = await probeMp4(filePath);
  const errors: string[] = [];
  const warnings: string[] = [];

  if (probe.width <= 0 || probe.height <= 0) {
    errors.push("Dimensions video invalides (0x0).");
  }
  if (probe.duration <= 0.1) {
    errors.push(`Duree quasi nulle (${probe.duration}s).`);
  }
  if (probe.size_bytes < 1024) {
    errors.push(`Fichier trop petit (${probe.size_bytes} octets).`);
  }

  let blackSegments = 0;
  try {
    const { stderr } = await execFileAsync(
      "ffmpeg",
      ["-hide_banner", "-i", filePath, "-vf", "blackdetect=d=0.8:pix_th=0.10", "-an", "-f", "null", "-"],
      { timeout: 30_000, maxBuffer: 2 * 1024 * 1024 },
    );
    const matches = stderr.match(/black_start:/g);
    blackSegments = matches ? matches.length : 0;
    if (blackSegments > 0) {
      warnings.push(`${blackSegments} segment(s) noir(s) detecte(s) (>= 0.8s).`);
    }
  } catch {
    // non-fatal diagnostic
  }

  let silentAudio = false;
  if (probe.has_audio) {
    try {
      const { stderr } = await execFileAsync(
        "ffmpeg",
        ["-hide_banner", "-i", filePath, "-af", "volumedetect", "-vn", "-f", "null", "-"],
        { timeout: 30_000, maxBuffer: 2 * 1024 * 1024 },
      );
      const maxVolMatch = stderr.match(/max_volume:\s*(-?[\d.]+)\s*dB/);
      if (maxVolMatch && Number(maxVolMatch[1]) <= -75) {
        silentAudio = true;
        warnings.push("Piste audio presente mais quasiment silencieuse (<= -75 dB).");
      }
    } catch {
      // non-fatal diagnostic
    }
  } else {
    warnings.push("Aucune piste audio dans le MP4 (video muette).");
  }

  return {
    ok: errors.length === 0,
    file: filePath,
    probe,
    black_segments: blackSegments,
    silent_audio: silentAudio,
    warnings,
    errors,
  };
}
