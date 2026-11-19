import fs from "node:fs";

export interface TimedWord {
  word: string;
  start: number;
  end: number;
}

export interface SubtitleCue {
  start: number;
  end: number;
  text: string;
}

export function wrapWords(
  words: TimedWord[],
  opts: { maxWords?: number; maxChars?: number; rtl?: boolean } = {},
): SubtitleCue[] {
  const maxWords = opts.maxWords ?? 4;
  const maxChars = opts.maxChars ?? 30;
  const cues: SubtitleCue[] = [];
  let bucket: TimedWord[] = [];
  let charCount = 0;

  const flush = () => {
    if (bucket.length === 0) return;
    cues.push({
      start: Math.round(bucket[0].start * 1000) / 1000,
      end: Math.round(bucket[bucket.length - 1].end * 1000) / 1000,
      text: bucket.map((w) => w.word).join(" "),
    });
    bucket = [];
    charCount = 0;
  };

  for (const w of words) {
    const clean = w.word.trim();
    if (!clean) continue;
    const nextChars = charCount + (bucket.length > 0 ? 1 : 0) + clean.length;
    if (bucket.length > 0 && (bucket.length >= maxWords || nextChars > maxChars)) {
      flush();
    }
    bucket.push({ ...w, word: clean });
    charCount = nextChars;
  }
  flush();
  return cues;
}

export function readWavDurationAndEnergy(wavPath: string, windowMs = 40): {
  duration: number;
  energies: number[];
  windowSec: number;
} {
  const buf = fs.readFileSync(wavPath);
  if (buf.length < 44 || buf.toString("ascii", 0, 4) !== "RIFF") {
    return { duration: 0, energies: [], windowSec: windowMs / 1000 };
  }
  let offset = 12;
  let sampleRate = 22050;
  let channels = 1;
  let bitsPerSample = 16;
  let dataStart = 44;
  let dataLen = Math.max(0, buf.length - 44);

  while (offset + 8 <= buf.length) {
    const chunkId = buf.toString("ascii", offset, offset + 4);
    const chunkSize = buf.readUInt32LE(offset + 4);
    if (chunkId === "fmt " && offset + 24 <= buf.length) {
      channels = buf.readUInt16LE(offset + 10) || 1;
      sampleRate = buf.readUInt32LE(offset + 12) || 22050;
      bitsPerSample = buf.readUInt16LE(offset + 22) || 16;
    } else if (chunkId === "data") {
      dataStart = offset + 8;
      dataLen = Math.min(chunkSize, buf.length - dataStart);
      break;
    }
    offset += 8 + chunkSize + (chunkSize % 2);
  }

  const bytesPerSample = Math.max(1, bitsPerSample / 8);
  const totalFrames = Math.floor(dataLen / (bytesPerSample * channels));
  const duration = sampleRate > 0 ? totalFrames / sampleRate : 0;
  const framesPerWindow = Math.max(1, Math.floor((sampleRate * windowMs) / 1000));
  const energies: number[] = [];

  for (let f = 0; f < totalFrames; f += framesPerWindow) {
    let sumSq = 0;
    let count = 0;
    const end = Math.min(totalFrames, f + framesPerWindow);
    for (let i = f; i < end; i++) {
      const bytePos = dataStart + i * bytesPerSample * channels;
      if (bytePos + 1 >= buf.length) break;
      const sample = bitsPerSample === 16 ? buf.readInt16LE(bytePos) / 32768 : (buf.readUInt8(bytePos) - 128) / 128;
      sumSq += sample * sample;
      count += 1;
    }
    energies.push(count > 0 ? Math.sqrt(sumSq / count) : 0);
  }

  return { duration, energies, windowSec: windowMs / 1000 };
}

/**
 * P3 : Alignement des mots sur un fichier WAV (énergie audio réelle),
 * ou distribution uniforme si l'audio n'est pas disponible, et génération de sous-titres SRT.
 */
export function alignScriptToWav(script: string, wavPath?: string, durationFallback?: number): TimedWord[] {
  const rawWords = String(script || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (rawWords.length === 0) return [];

  let duration = durationFallback || Math.max(2.0, rawWords.length * 0.42);
  let energies: number[] = [];
  let winSec = 0.04;

  if (wavPath && fs.existsSync(wavPath)) {
    const measured = readWavDurationAndEnergy(wavPath);
    if (measured.duration > 0) {
      duration = measured.duration;
      energies = measured.energies;
      winSec = measured.windowSec;
    }
  }

  // Find active speech span using energy threshold
  let speechStart = 0;
  let speechEnd = duration;
  if (energies.length > 4) {
    const peak = Math.max(...energies);
    const thresh = peak * 0.06;
    const firstActive = energies.findIndex((e) => e > thresh);
    let lastActive = energies.length - 1;
    while (lastActive > 0 && energies[lastActive] <= thresh) lastActive--;
    if (firstActive >= 0 && lastActive > firstActive) {
      speechStart = Math.max(0, firstActive * winSec);
      speechEnd = Math.min(duration, (lastActive + 1) * winSec);
    }
  }

  const activeDuration = Math.max(0.5, speechEnd - speechStart);
  const weights = rawWords.map((w) => Math.max(2, w.replace(/[^\p{L}\p{N}]/gu, "").length));
  const totalWeight = weights.reduce((a, b) => a + b, 0) || rawWords.length;

  const timed: TimedWord[] = [];
  let cursor = speechStart;
  rawWords.forEach((word, i) => {
    const share = (weights[i] / totalWeight) * activeDuration;
    const end = i === rawWords.length - 1 ? speechEnd : cursor + share;
    timed.push({
      word,
      start: Math.round(cursor * 1000) / 1000,
      end: Math.round(Math.max(cursor + 0.08, end) * 1000) / 1000,
    });
    cursor = end;
  });
  return timed;
}

export function formatSrtTime(sec: number): string {
  const msTotal = Math.max(0, Math.round(sec * 1000));
  const ms = msTotal % 1000;
  const sTotal = Math.floor(msTotal / 1000);
  const s = sTotal % 60;
  const mTotal = Math.floor(sTotal / 60);
  const m = mTotal % 60;
  const h = Math.floor(mTotal / 60);
  const pad = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)},${pad(ms, 3)}`;
}

export function toSrt(cues: SubtitleCue[]): string {
  return cues
    .map((cue, idx) => `${idx + 1}\n${formatSrtTime(cue.start)} --> ${formatSrtTime(cue.end)}\n${cue.text}\n`)
    .join("\n");
}
