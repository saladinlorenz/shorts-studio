import React from "react";
import { useAudioData, visualizeAudio } from "@remotion/media-utils";
import type { MediaUtilsAudioData } from "@remotion/media-utils";

import type { AudioEnergy } from "./common";

/**
 * Mesure reelle de la piste du projet.
 *
 * Les valeurs viennent du decodage du fichier (FFT embarquee dans
 * @remotion/media-utils), jamais d'une simulation : un pulse ou un spectre
 * racontent ce que la vidéo fait entendre. Le decodage est asynchrone et
 * `useAudioData` retient lui-meme le rendu jusqu'aux donnees.
 */

const SAMPLES = 32;

function bandAverage(samples: number[], from: number, to: number): number {
  const slice = samples.slice(from, to);
  if (!slice.length) return 0;
  return slice.reduce((sum, value) => sum + value, 0) / slice.length;
}

/**
 * La musique du studio est bouclee a l'ecoute (SoundBed) : la mesure doit
 * suivre le meme cycle, sinon un spectre ou un pulse s'eteint des que la piste
 * se termine alors que l'audition continue.
 */
export function loopedFrame(audioData: MediaUtilsAudioData, frame: number, fps: number): number {
  const trackFrames = Math.round(audioData.durationInSeconds * Math.max(1, fps));
  if (!Number.isFinite(trackFrames) || trackFrames <= 0) return frame;
  return frame % trackFrames;
}

/** Energies de la frame courante, sur toute la piste chargee. */
export function energyAt(
  audioData: ReturnType<typeof useAudioData>,
  frame: number,
  fps: number,
): AudioEnergy | null {
  if (!audioData) return null;
  const samples = visualizeAudio({
    audioData,
    frame: loopedFrame(audioData, frame, fps),
    fps,
    numberOfSamples: SAMPLES,
    // 'speed' : la FFT rapide suffit aux bandes d'energie et garde l'aperçu fluide.
    optimizeFor: "speed",
    smoothing: false,
  });
  return {
    bass: bandAverage(samples, 0, 6),
    mid: bandAverage(samples, 6, 16),
    treble: bandAverage(samples, 16, SAMPLES),
    level: bandAverage(samples, 0, SAMPLES),
    samples,
  };
}

interface MeterProps {
  src: string;
  frame: number;
  fps: number;
  /** Recoit les energies mesurees et les donnees brutes, null tant que le decodage n'est pas fini. */
  measure: (audio: AudioEnergy | null, audioData: MediaUtilsAudioData | null) => React.ReactNode;
}

/**
 * Monte uniquement quand un effet reactif en a besoin ET qu'une piste existe :
 * decoder une musique pour rien couterait du temps a chaque frame.
 */
export const AudioMeter: React.FC<MeterProps> = ({ src, frame, fps, measure }) => {
  const data = useAudioData(src);
  return <>{measure(energyAt(data, frame, fps), data)}</>;
};

export { visualizeAudio };
