# 05 — AUDIO, VIDÉO, SOUS-TITRES & IA

## 1. Audio
```tsx
<Audio src={staticFile('musique.mp3')} volume={(f)=>interpolate(f,[0,30],[0,0.8],{extrapolateRight:'clamp'})} />
```
- **Plusieurs pistes** : plusieurs `<Audio>` dans des `<Sequence>` (voix + musique + effets)
- Fondu entrée/sortie : `volume` fonction de `f`
- Vitesse : `playbackRate` ; hauteur : `toneFrequency`
- Boucle : `loop` + `loopVolumeCurveBehavior`
- Découpe : `startFrom`/`endAt` (ou `trimBefore`/`trimAfter`)
- Durée d'un fichier : `getAudioDurationInSeconds(src)` (idéal dans `calculateMetadata` : la vidéo dure exactement l'audio)
- Rendu audio seul : `--codec=mp3|aac|wav`

## 2. Analyse audio → visuels (`@remotion/media-utils`)
```tsx
const audioData = useAudioData(src);              // charge et décode
const spectrum = visualizeAudio({fps, frame, audioData, numberOfSamples: 64, smoothing: true, optimizeFor:'speed'});
const waveform = visualizeAudioWaveform({fps, frame, audioData, numberOfSamples: 64, windowInSeconds: 0.5});
const path = createSmoothSvgPath({points: waveform.map((y,i)=>({x:i*10, y:200+y*100}))});
```
Effets possibles : barres d'égaliseur, cercle réactif, onde animée, logo qui pulse sur la basse, caméra qui tremble sur les kicks, couleurs réactives, particules, détection de beat (seuil sur les basses `spectrum.slice(0,4)`).
`getAudioData(src)` → `{channelWaveforms, sampleRate, durationInSeconds, numberOfChannels, resultId, isRemote}`.

## 3. Vidéo
- `<OffthreadVideo>` : rendu précis ; `transparent` pour alpha ; `toneMapped` pour HDR
- Métadonnées : `getVideoMetadata(src)` (`@remotion/media-utils`) ou `parseMedia` (`@remotion/media-parser`)
- Effets : ralenti, accéléré, arrêt (`<Freeze>`), boucle (`<Loop>`), recadrage (`objectFit`, `clipPath`), filtres CSS, fusion, masques, incrustations, écrans partagés
- Vidéo en texture 3D : `useVideoTexture`
- Transcodage navigateur : `@remotion/webcodecs` (`convertMedia`, `extractFrames`)

## 4. Sous-titres automatiques (pipeline complet)
1. **Transcrire** — Whisper local :
```ts
import {installWhisperCpp, downloadWhisperModel, transcribe, toCaptions} from '@remotion/install-whisper-cpp';
await installWhisperCpp({to: whisperPath, version: '1.5.5'});
await downloadWhisperModel({model: 'medium.en', folder: whisperPath});
const out = await transcribe({inputPath: 'audio16k.wav', whisperPath, model: 'medium.en', tokenLevelTimestamps: true});
const {captions} = toCaptions({whisperCppOutput: out});
```
   (audio converti en WAV 16 kHz avec `npx remotion ffmpeg -i in.mp4 -ar 16000 out.wav`)
   ou API OpenAI → `openAiWhisperApiToCaptions` (`@remotion/openai-whisper`).
2. **Importer/Exporter** : `parseSrt({input})`, `serializeSrt({lines})`.
3. **Paginer** : `createTikTokStyleCaptions({captions, combineTokensWithinMilliseconds: 800})` → `{pages}` avec `tokens` (mot, `fromMs`, `toMs`).
4. **Afficher** : mot actif surligné, apparition en `spring`, contour, emoji, couleurs par locuteur, traduction.
5. **Exporter** les sous-titres avec la vidéo (`<Artifact>` selon version).

## 5. Idées « IA + Remotion »
- Texte → voix off (ElevenLabs/OpenAI TTS) → `calculateMetadata` (durée = audio) → vidéo
- Script LLM → scènes JSON → `<Series>` automatique
- Images IA (DALL·E/Flux) → Ken Burns + transitions
- Transcription → **clips courts** viraux avec sous-titres dynamiques
- Résumés vidéo, traduction + sous-titres multilingues
- Génération en masse : 1 JSON = 1 vidéo (Lambda)
