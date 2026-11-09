# 3. Médias, métadonnées et environnement

| Composant ou fonction | Rôle | Props ou usage clés |
| --- | --- | --- |
| `<Img>` | Image qui attend son chargement avant la capture | `src` |
| `<OffthreadVideo>` | Vidéo extraite hors navigateur par FFmpeg : précise et rapide au rendu | `src`, `volume`, `playbackRate`, `transparent`, `toneMapped`, `startFrom` / `endAt` (ou `trimBefore` / `trimAfter`) |
| `<Video>` / `<Html5Video>` | Vidéo lue par le navigateur | `volume`, `playbackRate`, `muted`, `loop` |
| `<Audio>` / `<Html5Audio>` | Piste audio | `volume` (nombre ou fonction de la frame), `playbackRate`, `toneFrequency`, `loop`, `loopVolumeCurveBehavior`, `muted` |
| `<AnimatedImage>` | GIF, WebP ou AVIF animé synchronisé à la frame | `src`, `fit` |
| `<IFrame>` | Page web intégrée, attendue au rendu | `src` |
| `staticFile()` | URL d'un fichier du dossier `public/` | `staticFile('logo.png')` |
| `prefetch()` | Précharge un média pour éviter les saccades | `prefetch(url)` |
| `calculateMetadata` | Calcule durée, dimensions, fps et props avant le rendu | async, peut faire un `fetch` ou lire la durée d'un audio |
| `getInputProps()` | Lit les props passées par `--props` | retourne un objet |
| `delayRender()` / `continueRender()` | Bloque puis libère le rendu | `delayRender('chargement police')` |
| `cancelRender()` | Annule avec une erreur propre | `cancelRender(new Error('...'))` |
| `getRemotionEnvironment()` | Détecte le contexte | `isRendering`, `isStudio`, `isPlayer`, `isProduction` |

**Déclaration des compositions**

| Élément | Rôle |
| --- | --- |
| `registerRoot(Root)` | Point d'entrée du projet |
| `<Composition>` | Vidéo rendable : `id`, `component`, `width`, `height`, `fps`, `durationInFrames`, `defaultProps`, `schema`, `calculateMetadata` |
| `<Still>` | Image fixe : `id`, `component`, `width`, `height` |
| `<Folder name>` | Range les compositions dans le Studio |
| `schema` (zod) | Génère un formulaire éditable dans le Studio ; `zColor()` pour une couleur, `zTextarea()` pour un texte long (`@remotion/zod-types`) |

**Durée dynamique avec `calculateMetadata`**

```tsx
export const calculateMetadata: CalculateMetadataFunction<Props> = async ({props}) => {
  const seconds = await getAudioDurationInSeconds(props.audioUrl);
  return {
    durationInFrames: Math.ceil(seconds * 30),
    props: {...props, loadedAt: 'calculé au rendu'},
  };
};
```
