# 1. Modèle de rendu et règles techniques

Remotion calcule chaque image comme une fonction pure du numéro de frame : `image = f(frame, props)`. Le rendu est parallèle (plusieurs onglets Chrome headless), donc chaque frame doit pouvoir être produite seule, sans état partagé.

**Pipeline de rendu**

1. `bundle()` empaquette le projet avec Webpack.
2. `selectComposition()` lit la composition et exécute `calculateMetadata` (durée, dimensions, props).
3. `renderFrames()` ouvre N onglets Chrome et capture chaque frame en JPEG ou PNG.
4. `stitchFramesToVideo()` assemble les images et l'audio avec FFmpeg (codec, CRF, bitrate).
5. Le fichier final est écrit (MP4, WebM, ProRes, GIF, audio seul ou séquence d'images).

**Règles à respecter absolument**

- Tout dépend de `useCurrentFrame()` : aucune animation CSS (`transition`, `@keyframes`), aucun `setTimeout`, aucun `requestAnimationFrame`.
- Pas de `Math.random()` ni de `Date.now()` : utiliser `random(seed)`, qui est déterministe.
- Tout chargement asynchrone (fetch, police, modèle 3D) passe par `delayRender()` puis `continueRender(handle)` (ou `useDelayRender()` selon la version).
- Les médias passent par `<Img>`, `<OffthreadVideo>` et `<Audio>`, pas par les balises HTML natives, pour que le rendu attende leur chargement.
- Les animations de la librairie 3D se pilotent par la frame, jamais par `useFrame` de react-three-fiber.
- Toutes les versions `remotion` et `@remotion/*` doivent être identiques (`npx remotion upgrade`).

**Éléments du temps**

| Élément | Rôle | Paramètres clés |
| --- | --- | --- |
| `useCurrentFrame()` | Frame courante, relative à la `<Sequence>` parente | aucun |
| `useVideoConfig()` | Configuration de la composition | retourne `fps`, `width`, `height`, `durationInFrames`, `id`, `defaultProps` |
| `<Sequence>` | Décale ou limite un enfant dans le temps | `from`, `durationInFrames`, `name`, `layout`, `premountFor` |
| `<Series>` / `<Series.Sequence>` | Enchaîne des scènes | `durationInFrames`, `offset` (négatif = chevauchement) |
| `<Loop>` | Répète un contenu | `durationInFrames`, `times`, `layout` |
| `<Freeze>` | Fige sur une frame | `frame` |
| `<AbsoluteFill>` | Calque plein écran | style CSS standard |
| `useCurrentScale()` | Échelle du Player ou du Studio | aucun |
