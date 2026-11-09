# 6. Paquets officiels `@remotion/*` et leurs fonctions

Tous les paquets doivent partager la même version que `remotion`.

| Paquet | Fonctions et composants principaux | Sert à |
| --- | --- | --- |
| `@remotion/transitions` | `TransitionSeries`, `linearTiming`, `springTiming`, `slide`, `fade`, `wipe`, `flip`, `clockWipe`, `iris`, `cube` | Transitions entre scènes |
| `@remotion/animation-utils` | `makeTransform`, `interpolateStyles`, `translateX`, `rotate`, `scale`, `skew`, `perspective` | Écrire des transformations CSS |
| `@remotion/motion-blur` | `CameraMotionBlur`, `Trail` | Flou de mouvement, traînées |
| `@remotion/noise` | `noise2D`, `noise3D`, `noise4D` | Mouvements organiques, tremblements, fonds |
| `@remotion/shapes` | `Circle`, `Rect`, `Triangle`, `Star`, `Polygon`, `Ellipse`, `Pie`, `makeCircle`, `makeStar`, `makePie`… | Formes géométriques et chemins |
| `@remotion/paths` | `getLength`, `getPointAtLength`, `getTangentAtLength`, `evolvePath`, `interpolatePath`, `scalePath`, `translatePath`, `reversePath`, `normalizePath`, `parsePath`, `warpPath`, `getBoundingBox`, `getSubpaths` | Tracés, morphing, trajectoires |
| `@remotion/google-fonts` | `loadFont` par police | Polices Google |
| `@remotion/fonts` | `loadFont({family, url})` | Polices locales |
| `@remotion/layout-utils` | `measureText`, `fillTextBox`, `fitText` | Mesure et ajustement du texte |
| `@remotion/three` | `ThreeCanvas`, `useVideoTexture` | 3D avec react-three-fiber |
| `@remotion/skia` | `SkiaCanvas` | Dessin 2D accéléré, shaders |
| `@remotion/lottie` | `Lottie`, `getLottieMetadata` | Animations After Effects |
| `@remotion/rive` | `RemotionRiveCanvas` | Animations Rive |
| `@remotion/gif` | `Gif`, `getGifDurationInSeconds`, `preloadGif` | GIF synchronisés |
| `@remotion/animated-emoji` | `AnimatedEmoji`, `getAvailableEmojis` | Emojis animés |
| `@remotion/media-utils` | `useAudioData`, `getAudioData`, `visualizeAudio`, `visualizeAudioWaveform`, `createSmoothSvgPath`, `getAudioDurationInSeconds`, `getVideoMetadata`, `getImageDimensions` | Analyse audio, métadonnées |
| `@remotion/media-parser` | `parseMedia` | Lire durée, codec, résolution sans FFmpeg |
| `@remotion/webcodecs` | `convertMedia`, `extractFrames` | Transcodage dans le navigateur |
| `@remotion/preload` | `preloadVideo`, `preloadAudio`, `preloadImage`, `preloadFont` | Éviter les saccades |
| `@remotion/captions` | `parseSrt`, `serializeSrt`, `createTikTokStyleCaptions`, type `Caption` | Sous-titres |
| `@remotion/install-whisper-cpp` | `installWhisperCpp`, `downloadWhisperModel`, `transcribe`, `toCaptions` | Transcription locale |
| `@remotion/openai-whisper` | `openAiWhisperApiToCaptions` | Convertir la réponse de l'API Whisper |
| `@remotion/zod-types` | `zColor`, `zTextarea`, `zMatrix` | Champs du formulaire Studio |
| `@remotion/tailwind` | configuration Webpack | Tailwind CSS |
| `@remotion/enable-scss` | configuration Webpack | SCSS |
| `@remotion/cli` | commandes `remotion` | Studio et rendu en ligne de commande |
| `@remotion/bundler` | `bundle` | Empaqueter le projet |
| `@remotion/renderer` | `renderMedia`, `renderStill`, `renderFrames`, `selectComposition`, `getCompositions`, `stitchFramesToVideo`, `ensureBrowser`, `makeCancelSignal` | Rendu côté Node |
| `@remotion/lambda` | `deployFunction`, `deploySite`, `renderMediaOnLambda`, `renderStillOnLambda`, `getRenderProgress` | Rendu sur AWS |
| `@remotion/cloudrun` | `deployService`, `renderMediaOnCloudrun` | Rendu sur Google Cloud |
| `@remotion/player` | `Player`, `Thumbnail` | Intégrer la vidéo dans un site |
| `@remotion/studio` | `getStaticFiles`, `watchStaticFile` | Interaction avec le Studio |

Selon la version, d'autres paquets existent : `@remotion/light-leaks`, `@remotion/sfx`, `@remotion/media`, `@remotion/svg-3d-engine`, `@remotion/vercel`.
