# 7. Rendu, automatisation et déploiement

**Commandes CLI (`npx remotion ...`)**

| Commande | Usage |
| --- | --- |
| `studio` | Ouvre l'éditeur visuel avec rechargement à chaud |
| `render <id> <sortie>` | Rend une vidéo |
| `still <id> <sortie> --frame=30` | Rend une image fixe |
| `compositions` | Liste les compositions |
| `bundle` | Empaquette le site pour Lambda ou un serveur |
| `benchmark` | Compare concurrence et codecs |
| `upgrade` / `versions` | Met à jour ou liste les versions |
| `ffmpeg` / `ffprobe` | FFmpeg embarqué |
| `lambda ...` / `cloudrun ...` | Commandes de déploiement cloud |

**Options de rendu principales**

| Option | Effet |
| --- | --- |
| `--codec` | `h264`, `h265`, `vp8`, `vp9`, `prores`, `gif`, `mp3`, `aac`, `wav` (`av1` selon version) |
| `--crf` | Qualité : plus bas = meilleure (16 à 18 pour une qualité élevée) |
| `--scale` | Rend en plus grande résolution (`--scale=2` : 1080p vers 4K) |
| `--props` | JSON ou chemin de fichier passé aux composants |
| `--frames=0-120` | Rend une plage de frames |
| `--concurrency` | Nombre d'onglets parallèles |
| `--image-format` | `jpeg` ou `png` (png pour la transparence) |
| `--prores-profile=4444` | ProRes avec canal alpha |
| `--muted`, `--enforce-audio-track` | Contrôle de la piste audio |
| `--sequence` | Sortie en séquence d'images |
| `--gl` | Moteur WebGL (`angle`, `swiftshader`, `vulkan`) pour la 3D |
| `--every-nth-frame`, `--number-of-gif-loops` | Réglages GIF |

**API Node : une vidéo par appel**

```ts
import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia} from '@remotion/renderer';

const serveUrl = await bundle({entryPoint: './src/index.ts'});
const inputProps = {nom: 'Léa'};
const composition = await selectComposition({serveUrl, id: 'Promo', inputProps});

await renderMedia({
  composition, serveUrl, inputProps,
  codec: 'h264', outputLocation: 'out/lea.mp4',
  onProgress: ({progress}) => console.log(Math.round(progress * 100) + '%'),
});
```

**AWS Lambda : rendu massivement parallèle**

```ts
const {renderId, bucketName} = await renderMediaOnLambda({
  region: 'eu-west-3', functionName, serveUrl, composition: 'Promo',
  inputProps: {nom: 'Léa'}, codec: 'h264', privacy: 'public',
});
const progress = await getRenderProgress({renderId, bucketName, functionName, region: 'eu-west-3'});
```

Autres fonctions : `deployFunction`, `deploySite`, `renderStillOnLambda`, `downloadMedia`, `presignUrl`, `estimatePrice`, `validateWebhookSignature` (webhooks de fin de rendu).

**Player React : la vidéo dans un site**

```tsx
<Player component={Promo} inputProps={{nom: 'Léa'}}
  durationInFrames={150} fps={30} compositionWidth={1920} compositionHeight={1080}
  controls loop style={{width: '100%'}} />
```

Le `ref` du Player expose `play()`, `pause()`, `toggle()`, `seekTo(frame)`, `getCurrentFrame()`, `isPlaying()`, `mute()`, `setVolume()`, `requestFullscreen()` et `addEventListener('frameupdate' | 'ended' | 'play' | 'pause' | 'seeked')`. `<Thumbnail>` affiche une frame fixe.

**Formats de sortie** : MP4 (H.264, H.265), WebM (VP8, VP9), ProRes avec alpha, MKV, GIF, audio seul (MP3, AAC, WAV), séquence PNG ou JPEG, images fixes PNG, JPEG, WebP et PDF.

**Transparence** : rendre en ProRes 4444 (`--codec=prores --prores-profile=4444`) ou en WebM VP8 / VP9 avec `--image-format=png` ; relire une vidéo transparente avec `<OffthreadVideo transparent>`.
