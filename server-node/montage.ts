import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { toSrt, type SubtitleCue } from "./captions.ts";
import * as edlMod from "./edl.ts";
import { Job, JobCancelled, raiseIfCancelled } from "./jobs.ts";
import { hasAudioStream, probeMp4 } from "./probe.ts";

export class TimelineError extends Error {}
export class TimelineCancelled extends JobCancelled {}

function buildAtempoChain(speed: number): string {
  const parts: string[] = [];
  let remaining = speed;
  while (remaining > 2.0) {
    parts.push("atempo=2.0");
    remaining /= 2.0;
  }
  while (remaining < 0.5) {
    parts.push("atempo=0.5");
    remaining /= 0.5;
  }
  parts.push(`atempo=${remaining.toFixed(4)}`);
  return parts.join(",");
}

function escapeSubtitlesPath(p: string): string {
  return p.replace(/\\/g, "/").replace(/:/g, "\\:").replace(/'/g, "\\'");
}

function hexToAssColor(hex: string): string {
  const clean = hex.replace("#", "").padStart(6, "F");
  const rr = clean.slice(0, 2);
  const gg = clean.slice(2, 4);
  const bb = clean.slice(4, 6);
  return `&H00${bb}${gg}${rr}`;
}

function runFfmpeg(job: Job, args: string[], progressLabel = "FFmpeg"): Promise<void> {
  return new Promise((resolve, reject) => {
    raiseIfCancelled(job);
    const proc = spawn("ffmpeg", ["-hide_banner", "-y", ...args], { stdio: ["ignore", "pipe", "pipe"] });
    job.resultProcess = proc;
    const tail: string[] = [];
    const onData = (chunk: Buffer) => {
      const lines = chunk.toString("utf8").split(/\r?\n/).filter(Boolean);
      for (const l of lines) {
        tail.push(l);
        if (tail.length > 40) tail.shift();
      }
      if (job.cancelled) {
        try { proc.kill("SIGTERM"); } catch { /* ignore */ }
      }
    };
    proc.stdout.on("data", onData);
    proc.stderr.on("data", onData);
    proc.on("error", (err) => {
      job.resultProcess = null;
      reject(new TimelineError(`Impossible de lancer FFmpeg: ${err.message}`));
    });
    proc.on("close", (code) => {
      job.resultProcess = null;
      if (job.cancelled) {
        reject(new TimelineCancelled());
        return;
      }
      if (code !== 0) {
        reject(new TimelineError(`${progressLabel} a echoue (code ${code}):\n${tail.slice(-12).join("\n")}`));
        return;
      }
      resolve();
    });
  });
}

function deriveAutoCues(edl: edlMod.NormalizedEdl): SubtitleCue[] {
  if (edl.subtitles.cues.length > 0) return edl.subtitles.cues;
  const cues: SubtitleCue[] = [];
  let cursor = 0;
  edl.cuts.forEach((cut, i) => {
    const dur = Math.max(0.2, (cut.out - cut.in) / (cut.speed || 1));
    const text = cut.reason || `Plan ${i + 1} (${cut.role})`;
    cues.push({
      start: Math.round(cursor * 1000) / 1000,
      end: Math.round((cursor + dur) * 1000) / 1000,
      text,
    });
    cursor += dur;
  });
  return cues;
}

export async function renderTimeline(
  job: Job,
  rawEdl: unknown,
  outPath: string,
  opts: { mediaLookup: (mediaId: string) => string },
): Promise<Record<string, unknown>> {
  const edl = edlMod.normalize(rawEdl);
  const [errors, warnings] = edlMod.validate(edl, {
    mediaExists: (id) => {
      try {
        return fs.existsSync(opts.mediaLookup(id));
      } catch {
        return false;
      }
    },
  });
  if (errors.length > 0) {
    throw new TimelineError(`EDL invalide :\n- ${errors.join("\n- ")}`);
  }

  const [wStr, hStr] = edl.resolution.split("x");
  const width = Number(wStr) || 1080;
  const height = Number(hStr) || 1920;
  const fps = edl.fps;
  const workDir = path.join(path.dirname(outPath), `_montage_${job.id}`);
  fs.mkdirSync(workDir, { recursive: true });

  const segmentPaths: string[] = [];
  try {
    // 1. Cut, scale, and re-speed each segment cleanly
    for (let i = 0; i < edl.cuts.length; i++) {
      raiseIfCancelled(job);
      const cut = edl.cuts[i];
      const mediaId = cut.media.replace(/^media:\/\//, "");
      const srcPath = opts.mediaLookup(mediaId);
      const hasAudio = await hasAudioStream(srcPath);
      const segPath = path.join(workDir, `seg_${i}.mp4`);
      const speed = cut.speed || 1.0;
      const trimDur = cut.out - cut.in;

      job.setProgress(i, edl.cuts.length + 2, `Preparation plan ${i + 1}/${edl.cuts.length} (vitesse ${speed}x)…`);

      const vf = [
        `trim=start=${cut.in}:duration=${trimDur}`,
        `setpts=(PTS-STARTPTS)/${speed}`,
        `scale=${width}:${height}:force_original_aspect_ratio=increase`,
        `crop=${width}:${height}`,
        `fps=${fps}`,
        `format=yuv420p`,
      ].join(",");

      const args = ["-i", srcPath];
      if (!hasAudio) {
        // Generate silent audio track matching adjusted cut duration so concat is always consistent
        const adjustedDur = trimDur / speed;
        args.push("-f", "lavfi", "-t", adjustedDur.toFixed(4), "-i", "anullsrc=channel_layout=stereo:sample_rate=48000");
        args.push(
          "-filter_complex",
          `[0:v]${vf}[v];[1:a]aresample=48000[a]`,
          "-map", "[v]", "-map", "[a]",
        );
      } else {
        const af = [
          `atrim=start=${cut.in}:duration=${trimDur}`,
          "asetpts=PTS-STARTPTS",
          ...(Math.abs(speed - 1.0) > 0.001 ? [buildAtempoChain(speed)] : []),
          "aresample=48000",
        ].join(",");
        args.push(
          "-filter_complex",
          `[0:v]${vf}[v];[0:a]${af}[a]`,
          "-map", "[v]", "-map", "[a]",
        );
      }
      args.push("-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", segPath);
      await runFfmpeg(job, args, `Plan ${i + 1}`);
      segmentPaths.push(segPath);
    }

    raiseIfCancelled(job);
    job.setProgress(edl.cuts.length, edl.cuts.length + 2, "Assemblage timeline…");

    const concatPath = path.join(workDir, "concat.mp4");
    if (segmentPaths.length === 1) {
      fs.copyFileSync(segmentPaths[0], concatPath);
    } else {
      const listFile = path.join(workDir, "list.txt");
      fs.writeFileSync(
        listFile,
        segmentPaths.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join("\n"),
        "utf8",
      );
      await runFfmpeg(
        job,
        ["-f", "concat", "-safe", "0", "-i", listFile, "-c", "copy", concatPath],
        "Assemblage",
      );
    }

    // 2. Final finishing pass: external audio mix + P5 burn-in subtitles + P5 loudnorm
    raiseIfCancelled(job);
    job.setProgress(edl.cuts.length + 1, edl.cuts.length + 2, "Finition (sous-titres & loudness)…");

    const finishArgs = ["-i", concatPath];
    let musicIdx = -1;
    let voiceIdx = -1;
    if (edl.audio.music) {
      musicIdx = 1;
      finishArgs.push("-stream_loop", "-1", "-i", opts.mediaLookup(edl.audio.music.replace(/^media:\/\//, "")));
    }
    if (edl.audio.voice) {
      voiceIdx = edl.audio.music ? 2 : 1;
      finishArgs.push("-i", opts.mediaLookup(edl.audio.voice.replace(/^media:\/\//, "")));
    }

    let srtPath = "";
    const vFilters: string[] = [];
    if (edl.grade.look === "mono") {
      vFilters.push("hue=s=0");
    } else if (edl.grade.look === "sepia") {
      vFilters.push("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131");
    } else if (edl.grade.look === "warm") {
      vFilters.push("colorbalance=rs=0.06:gs=0.02:bs=-0.06");
    } else if (edl.grade.look === "cool") {
      vFilters.push("colorbalance=rs=-0.06:gs=0.0:bs=0.08");
    } else if (edl.grade.look === "teal_orange") {
      vFilters.push("colorbalance=rs=0.06:gs=-0.02:bs=-0.06:rm=0.04:bm=-0.05");
    }
    if (Math.abs(edl.grade.saturation - 1.0) > 0.01 || Math.abs(edl.grade.contrast - 1.0) > 0.01) {
      vFilters.push(`eq=saturation=${edl.grade.saturation.toFixed(2)}:contrast=${edl.grade.contrast.toFixed(2)}`);
    }

    if (edl.subtitles.enabled && edl.subtitles.burn_in) {
      const cues = deriveAutoCues(edl);
      if (cues.length > 0) {
        srtPath = path.join(workDir, "subs.srt");
        fs.writeFileSync(srtPath, toSrt(cues), "utf8");
        const alignment = edl.subtitles.style.position === "center" ? 5 : 2;
        const primary = hexToAssColor(edl.subtitles.style.color);
        const fontSize = Math.max(12, Math.min(72, edl.subtitles.style.font_size));
        const styleSpec = `Fontsize=${fontSize},PrimaryColour=${primary},OutlineColour=&H00000000,Outline=2,Alignment=${alignment}`;
        vFilters.push(`subtitles='${escapeSubtitlesPath(srtPath)}':force_style='${styleSpec}'`);
      }
    }

    const filterParts: string[] = [];
    let audioOut = "0:a";
    if (musicIdx >= 0 || voiceIdx >= 0) {
      const mixInputs: string[] = ["[0:a]"];
      if (musicIdx >= 0) {
        filterParts.push(`[${musicIdx}:a]volume=${edl.audio.music_volume}[m]`);
        mixInputs.push("[m]");
      }
      if (voiceIdx >= 0) {
        filterParts.push(`[${voiceIdx}:a]volume=${edl.audio.voice_volume}[vo]`);
        mixInputs.push("[vo]");
      }
      filterParts.push(`${mixInputs.join("")}amix=inputs=${mixInputs.length}:duration=first:dropout_transition=2[amixed]`);
      audioOut = "[amixed]";
    }

    if (edl.audio.loudnorm) {
      const srcLabel = audioOut.startsWith("[") ? audioOut : `[${audioOut}]`;
      filterParts.push(`${srcLabel}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[afinal]`);
      audioOut = "[afinal]";
    } else if (audioOut === "0:a") {
      // keep 0:a directly
    }

    if (vFilters.length > 0) {
      filterParts.push(`[0:v]${vFilters.join(",")}[vfinal]`);
    }

    if (filterParts.length > 0) {
      finishArgs.push("-filter_complex", filterParts.join(";"));
      finishArgs.push("-map", vFilters.length > 0 ? "[vfinal]" : "0:v");
      finishArgs.push("-map", audioOut);
    }

    if (vFilters.length > 0) {
      finishArgs.push("-c:v", "libx264", "-preset", "veryfast", "-crf", "19");
    } else {
      finishArgs.push("-c:v", "copy");
    }
    finishArgs.push("-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", outPath);

    await runFfmpeg(job, finishArgs, "Finition montage");

    const info = await probeMp4(outPath);
    return {
      ...info,
      planned_duration: edlMod.timelineDuration(edl),
      cuts: edl.cuts.length,
      music: Boolean(edl.audio.music),
      grade: edl.grade.look,
      loudnorm_applied: edl.audio.loudnorm,
      subtitles_burned: Boolean(srtPath),
      warnings,
    };
  } finally {
    try {
      fs.rmSync(workDir, { recursive: true, force: true });
    } catch {
      // ignore cleanup failures
    }
  }
}
