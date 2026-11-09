# 📚 BIBLE REMOTION — Tout ce qu'on peut faire (avec les fonctions à utiliser)

Remotion = créer des vidéos **avec React**. Une vidéo est une fonction du temps :
`image = f(frame)`. Tout ce que le navigateur sait dessiner (HTML, CSS, SVG, Canvas, WebGL, 3D)
peut devenir une vidéo MP4/WebM/GIF/ProRes/PNG/audio.

## Les fichiers de cette bibliothèque
| Fichier | Contenu |
|---|---|
| `01_COEUR_API_REMOTION.md` | Toutes les fonctions/composants du paquet `remotion` (temps, animation, médias, métadonnées) |
| `02_EFFETS_ET_RECETTES.md` | ~45 effets visuels « waouh » avec le code et les fonctions à appeler |
| `03_PAQUETS_OFFICIELS.md` | Tous les paquets `@remotion/*` : transitions, shapes, paths, noise, 3D, Lottie, Skia, motion-blur… |
| `04_RENDU_CLI_NODE_LAMBDA_PLAYER.md` | Rendre : CLI, API Node, Lambda, Cloud Run, Player React, Studio, formats, options |
| `05_AUDIO_VIDEO_SOUSTITRES_IA.md` | Audio, vidéo, spectres, sous-titres, Whisper, WebCodecs, parsing média |
| `06_IDEES_PROJETS_ET_SERVICES.md` | Quoi vendre / construire avec Remotion (Fiverr, Upwork, SaaS) |

## Modèle mental (à retenir absolument)
1. **`useCurrentFrame()`** donne le numéro d'image. Tout s'anime en fonction de lui.
2. **`useVideoConfig()`** donne `fps`, `width`, `height`, `durationInFrames`.
3. **Pas de hasard** (`Math.random`) ni d'horloge réelle (`Date.now`) : utiliser **`random(seed)`**.
4. **Pas d'animations CSS / transitions CSS / `setTimeout`** : elles ne sont pas synchronisées au rendu.
5. Le rendu est **parallèle** : chaque frame doit pouvoir être calculée seule.
6. Pour attendre un chargement (fetch, police, modèle 3D) : **`delayRender()` / `continueRender()`**.

## Démarrage rapide
```bash
npx create-video@latest        # assistant, choisir un template
npm run dev                    # = npx remotion studio
npx remotion render MaComposition out/video.mp4
npx remotion still MaComposition out/image.png --frame=30
```

## Structure type d'un projet
```
src/index.ts      -> registerRoot(Root)
src/Root.tsx      -> <Composition id=... component=... durationInFrames fps width height />
src/MaComp.tsx    -> le composant animé
public/           -> médias (accessibles via staticFile("nom.mp4"))
remotion.config.ts-> options globales (Config.*)
```

## Note sur les versions
Remotion évolue vite (v4.x). Certains noms ont changé dans les versions récentes :
- `<Video>` → aussi disponible sous **`<Html5Video>`** ; `<Audio>` → **`<Html5Audio>`** (selon version)
- `startFrom` / `endAt` → **`trimBefore` / `trimAfter`** (selon version)
- Un nouveau paquet **`@remotion/media`** (composants `<Video>`/`<Audio>` basés sur WebCodecs) existe dans les versions récentes.
Toujours vérifier sur https://www.remotion.dev/docs et garder **toutes les versions `remotion` / `@remotion/*` identiques** (`npx remotion upgrade`).
