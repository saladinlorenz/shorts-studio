# 01 — LE CŒUR : paquet `remotion`

`import {…} from 'remotion'`

## 1. Enregistrement & structure
| Fonction / composant | Rôle |
|---|---|
| `registerRoot(Root)` | Point d'entrée (dans `src/index.ts`) |
| `<Composition id component width height fps durationInFrames defaultProps schema calculateMetadata />` | Déclare une vidéo rendable |
| `<Still id component width height />` | Déclare une **image fixe** (miniature, OG image, affiche) |
| `<Folder name>` | Range les compositions dans le Studio |
| `calculateMetadata` | Calcule **durée, dimensions, fps, props** dynamiquement (fetch API, durée d'un audio…) avant le rendu. Peut aussi retourner `defaultCodec`, `defaultOutName` (selon version) |
| `schema` (zod) | Génère un **formulaire éditable dans le Studio** pour les props (couleurs avec `zColor()`, etc.) |
| `getInputProps()` | Récupère `--props` passé en CLI (côté composant) |

## 2. Le temps
| Fonction | Rôle |
|---|---|
| `useCurrentFrame()` | Frame courante (relative à la `<Sequence>` parente) |
| `useVideoConfig()` | `{fps, width, height, durationInFrames, id, defaultProps}` |
| `<Sequence from durationInFrames name layout premountFor>` | Décale/limite un enfant dans le temps ; `layout="none"` pour ne pas créer de calque ; `premountFor` précharge avant l'entrée |
| `<Series>` + `<Series.Sequence durationInFrames offset>` | Enchaîne des scènes l'une après l'autre (offset négatif = chevauchement) |
| `<Loop durationInFrames times layout>` | Boucle une animation |
| `<Freeze frame>` | Fige l'enfant sur une frame (arrêt sur image) |
| `<AbsoluteFill>` | Calque plein écran (position absolute) — base de tout |
| `useCurrentScale()` | Échelle actuelle du Player/Studio (pour compenser la taille) |

## 3. L'animation (la boîte à outils)
### `interpolate(valeur, plageEntrée, plageSortie, options)`
Convertit une plage vers une autre. Options : `extrapolateLeft/Right: 'clamp'|'extend'|'identity'|'wrap'`, `easing: Easing.xxx`.
```ts
const opacity = interpolate(frame, [0, 30], [0, 1], {extrapolateRight: 'clamp'});
```
### `interpolateColors(valeur, plageEntrée, [couleurs])`
Transition de couleur (hex, rgb, hsl, noms CSS). 
### `spring({frame, fps, config, delay, durationInFrames, from, to, reverse})`
Animation physique (rebond naturel). `config: {damping, mass, stiffness, overshootClamping}`.
- `measureSpring({fps, config})` → durée réelle d'un spring en frames (utile pour caler une scène).
- Réglages classiques : `{damping:200}` (lisse, sans rebond), `{damping:20, stiffness:200}` (vif), `{damping:8}` (rebondissant), `{mass:3, damping:10}` (lourd).
### `Easing`
`Easing.linear`, `ease`, `quad`, `cubic`, `poly(n)`, `sin`, `circle`, `exp`, `elastic(bounciness)`, `back(s)`, `bounce`, `bezier(x1,y1,x2,y2)`, `step0`, `step1`, et modificateurs `Easing.in()`, `Easing.out()`, `Easing.inOut()`.
### `random(seed | null)`
Hasard **déterministe** : même seed = même résultat à chaque rendu. `random('mon-id-'+i)`.

## 4. Médias
| Composant | Rôle / props clés |
|---|---|
| `<Img src>` | Image qui attend son chargement avant le rendu (préférer à `<img>`) |
| `<Video src>` / `<Html5Video>` | Vidéo (rendu dans le navigateur). `volume`, `playbackRate`, `muted`, `startFrom/endAt` (ou `trimBefore/trimAfter`), `loop` |
| `<OffthreadVideo src>` | Vidéo extraite **hors navigateur via FFmpeg** → plus rapide et précise au rendu. `transparent`, `toneMapped`, `playbackRate`, `volume`, `startFrom/endAt` |
| `<Audio src>` / `<Html5Audio>` | Piste audio. `volume` (nombre **ou fonction `(frame)=>0..1`** pour fondus), `playbackRate`, `toneFrequency` (changer la hauteur sans changer la vitesse), `loop`, `loopVolumeCurveBehavior`, `startFrom/endAt` |
| `<IFrame src>` | Intègre une page web (attend le chargement) |
| `<AnimatedImage src>` | GIF/WebP/AVIF animé synchronisé à la frame |
| `staticFile('x.mp4')` | URL d'un fichier du dossier `public/` |
| `prefetch(url)` | Précharge un média pour éviter les saccades (Player) |
| `<Artifact>` / `Artifact` (selon version) | Émet un fichier supplémentaire pendant le rendu (ex. sous-titres .srt, miniature) |

## 5. Synchronisation / environnement
| Fonction | Rôle |
|---|---|
| `delayRender(label)` → handle | Bloque le rendu tant que ce n'est pas prêt |
| `continueRender(handle)` | Libère le rendu |
| `cancelRender(erreur)` | Annule proprement avec message |
| `useDelayRender()` (selon version) | Version hook, recommandée |
| `getRemotionEnvironment()` / `useRemotionEnvironment()` | `isRendering`, `isStudio`, `isPlayer`, `isProduction` → adapter l'affichage |
| `watchStaticFile(nom, cb)` (via `@remotion/studio`) | Recharge quand un fichier de `public/` change |
| `Config.*` (`remotion.config.ts`, `@remotion/cli/config`) | Options globales (codec, CRF, concurrency, overwrite, webpack, chromium…) |
| `Config.overrideWebpackConfig(fn)` | Personnaliser Webpack (SCSS, SVGR, alias…) |

## 6. Utilitaires de style (paquet `@remotion/animation-utils`)
`makeTransform([translateX(10), rotate(45), scale(1.2)])`, `interpolateStyles(frame, [0,30], [{opacity:0,transform:…},{opacity:1,…}])`, `flip`, `translateX/Y`, `rotate`, `scale`, `skew`, `perspective`, `matrix`.

## 7. Ce que Remotion permet « de base » (capacités)
- Animations déclaratives de **n'importe quelle propriété** CSS/SVG/Canvas.
- Vidéos **pilotées par des données** (API, CSV, base de données, IA).
- **Montage** : couper, enchaîner, superposer, accélérer/ralentir, figer, boucler.
- **Compositions multiples** et formats multiples (16:9, 9:16, 1:1) depuis le même code (réutiliser le composant avec d'autres dimensions).
- **Audio** : plusieurs pistes, volume dynamique, fondus, vitesse.
- **Texte** sans limite : polices Google, locales, texte sur chemin, mesures.
- **Stills** : images PNG/JPEG/WebP/PDF d'une frame.
