# 04 — RENDRE, AUTOMATISER, DÉPLOYER, INTÉGRER

## 1. Studio (éditeur visuel : `npx remotion studio`)
- Prévisualisation en direct (hot reload), timeline, zoom, lecture à toute vitesse
- Édition des **props par formulaire** (schéma zod), sauvegarde des props par défaut
- **Render queue** : rendre depuis l'interface (codec, qualité, plage de frames)
- Rendu d'**images fixes**, de **GIF**, d'**audio seul**
- Dossier `public/` explorable, liens de partage de props

## 2. Commandes CLI (`npx remotion …`)
| Commande | Usage |
|---|---|
| `studio` | Ouvre le Studio |
| `render <comp> <out>` | Rend une vidéo |
| `still <comp> <out>` | Rend une image (`--frame=`) |
| `compositions` | Liste les compositions |
| `bundle` | Empaquette le site (pour Lambda/serveur) |
| `benchmark` | Compare concurrence/codecs |
| `upgrade` | Met à jour tous les paquets |
| `versions` | Affiche les versions installées |
| `ffmpeg` / `ffprobe` | FFmpeg embarqué |
| `browser ensure` | Télécharge Chrome Headless |
| `lambda …` / `cloudrun …` | Déploiement et rendu cloud |

### Options de rendu principales
`--codec` (`h264`, `h265`, `vp8`, `vp9`, `av1` (selon version), `prores`, `gif`, `mp3`, `aac`, `wav`, `h264-mkv`)
`--crf` (qualité), `--video-bitrate`, `--audio-bitrate`, `--x264-preset`, `--scale` (rendre en 4K depuis du 1080p), `--width/--height`, `--fps` (selon version),
`--props='{"nom":"Léa"}'` ou `--props=fichier.json`, `--frames=0-120`, `--every-nth-frame`, `--number-of-gif-loops`,
`--concurrency` (parallélisme), `--image-format` (`jpeg`/`png`), `--jpeg-quality`, `--pixel-format` (`yuva444p10le` pour alpha), `--prores-profile` (`4444` = transparence),
`--muted`, `--enforce-audio-track`, `--sequence` (séquence d'images), `--gl` (`angle`, `swiftshader`, `vulkan`…), `--hardware-acceleration`, `--timeout`, `--log`, `--overwrite`, `--color-space`, `--disable-web-security`, `--offthreadvideo-cache-size-in-bytes`.

## 3. API Node (`@remotion/bundler` + `@remotion/renderer`)
```ts
import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia, renderStill} from '@remotion/renderer';

const serveUrl = await bundle({entryPoint: './src/index.ts'});
const comp = await selectComposition({serveUrl, id: 'Promo', inputProps: {nom: 'Léa'}});
await renderMedia({composition: comp, serveUrl, codec: 'h264', outputLocation: 'out/lea.mp4',
                   inputProps: {nom: 'Léa'}, onProgress: ({progress}) => console.log(progress)});
await renderStill({composition: comp, serveUrl, output: 'out/thumb.png', frame: 30});
```
Fonctions : `bundle`, `getCompositions`, `selectComposition`, `renderMedia`, `renderFrames`, `renderStill`, `stitchFramesToVideo`, `openBrowser`, `ensureBrowser`, `makeCancelSignal`, `getSilentParts`, `getVideoMetadata`, `RenderInternals`.
→ Idéal pour un **serveur Express/Next.js/Fastify** : une API qui reçoit un JSON et renvoie une vidéo.

## 4. AWS Lambda (`@remotion/lambda`)
Rendu **massivement parallèle** : une vidéo d'une minute en quelques secondes ; paiement à l'usage.
- Déploiement : `deployFunction`, `deploySite`, `getOrCreateBucket`, `getFunctions`, `deleteFunction`, `getSites`, `deleteSite`
- Rendu : **`renderMediaOnLambda`**, **`renderStillOnLambda`**, **`getRenderProgress`**, `downloadMedia`, `presignUrl`
- Outils : `estimatePrice`, `getRegions`, `speculateFunctionName`, `validateWebhookSignature`, `simulatePermissions`, `getCompositionsOnLambda`
- **Webhooks** de fin de rendu, **S3** pour le stockage, rendu **distribué en chunks**, `framesPerLambda`, `privacy: 'public'|'private'`, `downloadBehavior`, `outName`, `logLevel`.

## 5. Google Cloud Run (`@remotion/cloudrun`)
`deployService`, `deploySite`, `renderMediaOnCloudrun`, `renderStillOnCloudrun`, `getServices`, `getRenderProgress`.

## 6. Player React (`@remotion/player`) — la vidéo **dans votre site/app**
```tsx
<Player component={MaComp} inputProps={{nom:'Léa'}} durationInFrames={150} fps={30}
        compositionWidth={1920} compositionHeight={1080} controls loop autoPlay style={{width:'100%'}} />
```
- Props : `controls`, `loop`, `autoPlay`, `clickToPlay`, `doubleClickToFullscreen`, `spaceKeyToPlayOrPause`, `showVolumeControls`, `allowFullscreen`, `playbackRate`, `inFrame/outFrame`, `renderLoading`, `errorFallback`, `numberOfSharedAudioTags`
- `playerRef` : `play()`, `pause()`, `toggle()`, `seekTo(frame)`, `getCurrentFrame()`, `isPlaying()`, `mute()`, `unmute()`, `setVolume()`, `requestFullscreen()`, `exitFullscreen()`, `addEventListener('frameupdate'|'ended'|'play'|'pause'|'seeked'|'ratechange'|…)`
- `<Thumbnail>` : affiche une frame fixe (aperçu de listes de vidéos)
- Cas d'usage : **éditeur vidéo en ligne**, **aperçu client temps réel**, **configurateur de produit**, **vidéos interactives**.

## 7. Formats de sortie
MP4 (H.264/H.265), WebM (VP8/VP9/AV1), **ProRes (alpha)**, MKV, **GIF** animé, **MP3/AAC/WAV** (audio seul), **séquence PNG/JPEG**, **images fixes** PNG/JPEG/WebP/PDF.
Résolutions : jusqu'à 4K/8K (`--scale`), formats verticaux/carrés/larges.

## 8. Qualité & performance
- `<OffthreadVideo>` plutôt que `<Video>` pour le rendu
- `--concurrency` ≈ moitié des cœurs ; `--gl=angle` pour WebGL/3D en cloud
- `useMemo` pour calculs lourds ; éviter `box-shadow`/`filter: blur` énormes sur beaucoup d'éléments
- Mettre en cache les données dans `calculateMetadata`
- `<Sequence premountFor>` pour précharger les scènes
- Licence : gratuit pour particuliers/petites équipes ; **licence entreprise requise pour grandes structures** (voir remotion.pro)

## 9. Produits & templates officiels
Templates `create-video` : Hello World, Blank, TikTok (captions Whisper), Audiogram, Next.js, Remotion + Lambda, Still images, Skia, Three.js, Javascript, Tailwind, Recorder…
**Remotion Recorder** (enregistrement/montage assisté), **Editor Starter** (éditeur vidéo complet, payant), **Remotion Convert** (conversion dans le navigateur).
