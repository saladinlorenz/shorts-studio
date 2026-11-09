# 03 — TOUS LES PAQUETS OFFICIELS `@remotion/*`

> Tous doivent avoir **la même version** que `remotion`.

## 🎞 Animation & scènes
### `@remotion/transitions`
- `TransitionSeries`, `TransitionSeries.Sequence`, `TransitionSeries.Transition`, `TransitionSeries.Overlay` (selon version)
- Timings : `linearTiming({durationInFrames, easing})`, `springTiming({config, durationInFrames, durationRestThreshold})`
- Présentations (import depuis sous-chemins) : `slide` (`/slide`), `fade` (`/fade`), `wipe` (`/wipe`), `flip` (`/flip`), `clockWipe` (`/clock-wipe`), `iris` (`/iris`), `cube` (`/cube`, selon version)
- Types pour créer vos présentations : `TransitionPresentation`, `TransitionPresentationComponentProps`
### `@remotion/animation-utils`
`makeTransform`, `interpolateStyles`, `translate/translateX/Y/Z`, `rotate/rotateX/Y/Z`, `scale/scaleX/Y`, `skew`, `perspective`, `matrix`, `flip`.
### `@remotion/motion-blur`
`<CameraMotionBlur samples shutterAngle>` (flou de mouvement cinéma), `<Trail layers lagInFrames trailOpacity>` (traînée).
### `@remotion/noise`
`noise2D(seed, x, y)`, `noise3D(seed, x, y, z)`, `noise4D(seed, x, y, z, w)` — bruit de Simplex déterministe (organique : mouvements, fonds, tremblements).
### `@remotion/light-leaks` (selon version)
Effet de fuites de lumière cinématiques en overlay.

## 🔷 Formes & tracés
### `@remotion/shapes`
Composants : `Circle`, `Rect`, `Triangle`, `Star`, `Polygon`, `Ellipse`, `Pie`, (`Heart` selon version).
Générateurs de chemin : `makeCircle`, `makeRect`, `makeTriangle`, `makeStar`, `makePolygon`, `makeEllipse`, `makePie` → renvoient `{path, width, height, transformOrigin, instructions}`.
### `@remotion/paths`
`getLength`, `getPointAtLength`, `getTangentAtLength`, `evolvePath`, `interpolatePath`, `scalePath`, `translatePath`, `reversePath`, `normalizePath`, `resetPath`, `parsePath`, `serializeInstructions`, `warpPath`, `getBoundingBox`, `getSubpaths`, `reduceInstructions`, `extendViewBox`, `getParts` (selon version).
### `@remotion/svg-3d-engine` (selon version)
Mini-moteur 3D en SVG (rotations, extrusion, projection).

## 🔤 Texte & polices
### `@remotion/google-fonts`
`import {loadFont} from '@remotion/google-fonts/Inter'; const {fontFamily} = loadFont('normal', {weights:['400','800'], subsets:['latin']});` — des centaines de polices Google.
### `@remotion/fonts`
`loadFont({family, url})` pour polices locales/personnalisées (dans `public/`).
### `@remotion/layout-utils`
`measureText`, `fillTextBox` (retour à la ligne automatique), `fitText`, `fitTextOnNLines` (selon version).

## 🧊 Rendus graphiques avancés
### `@remotion/three`
`<ThreeCanvas>` (react-three-fiber synchronisé), `useVideoTexture`. Compatible `@react-three/drei`, `@react-three/postprocessing` (bloom, profondeur de champ…). Matériaux PBR, lumières, ombres, GLTF, shaders GLSL.
### `@remotion/skia`
`<SkiaCanvas>` — dessin 2D accéléré (React Native Skia) : shaders runtime, filtres, blur, dégradés complexes, masques, paths.
### `@remotion/lottie`
`<Lottie animationData>`, `getLottieMetadata`, `LottieAnimationData` — animations After Effects (Bodymovin).
### `@remotion/rive`
`<RemotionRiveCanvas src>` — animations Rive.
### `@remotion/gif`
`<Gif src fit playbackRate>`, `getGifDurationInSeconds`, `preloadGif`.
### `@remotion/animated-emoji`
`<AnimatedEmoji emoji="fire" scale>`, `getAvailableEmojis()` — emojis animés (Noto Animated Emoji).

## 🎧 Médias
### `@remotion/media-utils`
`getAudioData`, `useAudioData`, `visualizeAudio`, `visualizeAudioWaveform`, `getWaveformPortion`, `createSmoothSvgPath`, `getAudioDurationInSeconds`, `getVideoMetadata`, `getImageDimensions`.
### `@remotion/media-parser`
`parseMedia({src, fields:{durationInSeconds, dimensions, …}})` — lit métadonnées (durée, codec, résolution, pistes, GPS, images clés…) sans FFmpeg. Fonctionne navigateur & Node.
### `@remotion/webcodecs`
Conversion/ré-encodage **dans le navigateur** : `convertMedia`, `extractFrames`, `createVideoDecoder`, `canReencodeVideoTrack`, `getAvailableContainers`… (transcodage côté client, vignettes, recadrage).
### `@remotion/media` (versions récentes)
Nouveaux `<Video>`, `<Audio>` basés sur WebCodecs (extraction précise, rapide) — alternative à `<OffthreadVideo>`.
### `@remotion/preload`
`preloadVideo`, `preloadAudio`, `preloadImage`, `preloadFont`, `resolveRedirect` — évite les saccades dans le Player.
### `@remotion/sfx` (selon version)
Banque d'effets sonores prêts à l'emploi.

## 🗣 Sous-titres & IA
### `@remotion/captions`
Type `Caption`; `parseSrt`, `serializeSrt`, `createTikTokStyleCaptions({captions, combineTokensWithinMilliseconds})` → pages de mots surlignables.
### `@remotion/install-whisper-cpp`
`installWhisperCpp`, `downloadWhisperModel`, `transcribe` (Whisper local), `toCaptions` → transcription avec timestamps mot à mot, gratuite, sur votre machine.
### `@remotion/openai-whisper`
`openAiWhisperApiToCaptions` — convertit la réponse de l'API OpenAI Whisper en `Caption[]`.

## 🎨 Styles & intégrations
- `@remotion/tailwind` / `@remotion/tailwind-v4` — Tailwind CSS
- `@remotion/enable-scss` — SCSS
- `@remotion/zod-types` — champs Studio : `zColor()`, `zTextarea()`, `zMatrix()`
- `@remotion/eslint-plugin`, `@remotion/eslint-config` — règles de bonnes pratiques (interdit CSS transition, etc.)

## 🚀 Rendu, déploiement, lecture
- `@remotion/cli` — commandes `remotion studio|render|still|compositions|bundle|benchmark|upgrade|lambda|cloudrun…`
- `@remotion/renderer` — API Node : `renderMedia`, `renderStill`, `renderFrames`, `selectComposition`, `getCompositions`, `stitchFramesToVideo`, `openBrowser`, `ensureBrowser`, `makeCancelSignal`
- `@remotion/bundler` — `bundle()` : empaquette le projet
- `@remotion/lambda` — rendu sur AWS Lambda
- `@remotion/cloudrun` — rendu sur Google Cloud Run
- `@remotion/vercel` (selon version) — rendu via Vercel Sandbox
- `@remotion/player` — `<Player>`, `<Thumbnail>` pour **intégrer la vidéo interactive dans un site web**
- `@remotion/studio` — API du Studio (`getStaticFiles`, `watchStaticFile`…)
- `@remotion/compositor-*` — binaires FFmpeg/Rust internes
- `@remotion/licensing` — gestion des licences

Détails : voir `04_RENDU_CLI_NODE_LAMBDA_PLAYER.md` et `05_AUDIO_VIDEO_SOUSTITRES_IA.md`.
