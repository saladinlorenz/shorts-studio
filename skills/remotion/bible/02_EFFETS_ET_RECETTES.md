# 02 — EFFETS & RECETTES « INCROYABLES » (avec le code)

Convention : `const frame = useCurrentFrame(); const {fps, width, height} = useVideoConfig();`
Fonctions-clés entre **gras**.

---
## A. TEXTE

### 1. Apparition en fondu / glissement — `interpolate`
```tsx
const o = interpolate(frame, [0, 20], [0, 1], {extrapolateRight: 'clamp'});
const y = interpolate(frame, [0, 20], [40, 0], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
<h1 style={{opacity: o, transform: `translateY(${y}px)`}}>Titre</h1>
```
### 2. Rebond « pop » — `spring`
```tsx
const s = spring({frame, fps, config: {damping: 8}});
<h1 style={{transform: `scale(${s})`}}>POP</h1>
```
### 3. Machine à écrire — `string.slice`
```tsx
const n = Math.floor(interpolate(frame, [0, 60], [0, text.length], {extrapolateRight: 'clamp'}));
<span>{text.slice(0, n)}<span style={{opacity: frame % 20 < 10 ? 1 : 0}}>|</span></span>
```
### 4. Compteur animé — `interpolate` + `toLocaleString`
```tsx
const v = interpolate(frame, [0, 60], [0, 1_250_000], {easing: Easing.out(Easing.exp), extrapolateRight: 'clamp'});
<div>{Math.round(v).toLocaleString('fr-FR')} €</div>
```
### 5. Révélation par masque — CSS `clipPath`
```tsx
const p = interpolate(frame, [0, 25], [100, 0], {extrapolateRight: 'clamp'});
<h1 style={{clipPath: `inset(0 ${p}% 0 0)`}}>Révélé de gauche à droite</h1>
```
### 6. Mot par mot décalé (stagger) — `spring` avec `delay`
```tsx
words.map((w,i)=>{ const s = spring({frame, fps, delay: i*4, config:{damping:14}});
  return <span style={{display:'inline-block', opacity:s, transform:`translateY(${(1-s)*60}px)`}}>{w}&nbsp;</span>})
```
### 7. Lettre par lettre avec vague — `Math.sin(frame/…)`
`transform: translateY(${Math.sin((frame - i*3)/6)*12}px)`
### 8. Texte qui s'adapte à la largeur — `fitText` (`@remotion/layout-utils`)
```tsx
const {fontSize} = fitText({text, withinWidth: 900, fontFamily: 'Inter', fontWeight: '800'});
```
### 9. Mesurer le texte / retour à la ligne auto — `measureText`, `fillTextBox`
### 10. Texte néon / lueur — `textShadow` multiple + `filter: drop-shadow`
`textShadow: '0 0 10px #0ff, 0 0 40px #0ff, 0 0 80px #0ff'`
### 11. Texte dégradé animé — `background-clip:text` + `interpolateColors`
```tsx
const c1 = interpolateColors(frame, [0,90], ['#ff4d8d','#00e5ff']);
<h1 style={{background:`linear-gradient(90deg, ${c1}, #7c5cff)`, WebkitBackgroundClip:'text', color:'transparent'}}>
```
### 12. Texte contour / outline — `WebkitTextStroke` + `paintOrder: 'stroke fill'`
### 13. Texte sur un chemin courbe — SVG `<textPath>` + `startOffset` animé
### 14. Texte avec police personnalisée — `loadFont` (`@remotion/google-fonts/Inter`) ou `@remotion/fonts`

---
## B. FORMES, TRAITS & MORPHING

### 15. Tracer un trait qui se dessine — `evolvePath` (`@remotion/paths`)
```tsx
const {strokeDasharray, strokeDashoffset} = evolvePath(progress, path);
<path d={path} stroke="#fff" strokeDasharray={strokeDasharray} strokeDashoffset={strokeDashoffset}/>
```
### 16. Morphing d'une forme vers une autre — `interpolatePath`
`const d = interpolatePath(progress, pathA, pathB);`
### 17. Objet qui suit un chemin — `getLength`, `getPointAtLength`, `getTangentAtLength`
```tsx
const L = getLength(path); const {x,y} = getPointAtLength(path, L*progress);
const {x:tx, y:ty} = getTangentAtLength(path, L*progress); // angle = Math.atan2(ty,tx)
```
### 18. Formes géométriques prêtes — `@remotion/shapes`
`<Circle/>`, `<Rect/>`, `<Triangle/>`, `<Star/>`, `<Polygon/>`, `<Ellipse/>`, `<Pie/>` (+ `<Heart/>` selon version) et `makeCircle()`, `makeStar()`… qui retournent un `path` utilisable avec `evolvePath`/`interpolatePath`.
### 19. Anneau de progression — `<Pie progress>` ou `strokeDashoffset`
### 20. Transformer / déformer un tracé — `scalePath`, `translatePath`, `reversePath`, `warpPath`, `normalizePath`
### 21. Courbe lisse d'onde — `createSmoothSvgPath` (`@remotion/media-utils`)

---
## C. MOUVEMENT, CAMÉRA & PROFONDEUR

### 22. Zoom caméra / Ken Burns
```tsx
const scale = interpolate(frame, [0, durationInFrames], [1, 1.25]);
<Img src={...} style={{transform:`scale(${scale}) translate(${x}px, ${y}px)`}}/>
```
### 23. Tremblement de caméra (shake) — `noise2D` / `noise3D` (`@remotion/noise`)
```tsx
const dx = noise2D('sx', frame/5, 0) * 20; const dy = noise2D('sy', 0, frame/5) * 20;
```
### 24. Parallaxe multi-calques — chaque calque avec `translateX = frame * vitesse_i`
### 25. Perspective 3D CSS — `perspective`, `rotateX/Y`, `translateZ`, `transformStyle:'preserve-3d'`
### 26. Flou de mouvement réaliste — `<CameraMotionBlur samples shutterAngle>` (`@remotion/motion-blur`)
### 27. Traînée (trail / écho) — `<Trail layers lagInFrames trailOpacity>` (`@remotion/motion-blur`)
### 28. Rebond physique & élasticité — `spring`, `Easing.elastic`, `Easing.bounce`, `Easing.back`
### 29. Objets qui flottent — `Math.sin(frame/…)` ou `noise2D`
### 30. Orbites / rotation — `Math.cos/sin(angle + frame*vitesse)`

---
## D. EFFETS VISUELS (FILTRES, GLITCH, LUMIÈRE)

### 31. Glitch RGB split — 3 copies, `mixBlendMode:'screen'`, décalage par `random()`
```tsx
const j = random(`g${Math.floor(frame/2)}`) * 12 - 6;
['#f00','#0f0','#00f'].map((c,i)=><div style={{color:c, mixBlendMode:'screen', transform:`translateX(${j*(i-1)}px)`}}>TEXTE</div>)
```
### 32. Distorsion liquide / chaleur — SVG `<feTurbulence baseFrequency={anim}>` + `<feDisplacementMap>`
`baseFrequency = 0.01 + Math.sin(frame/30)*0.005`
### 33. Flou, contraste, teinte — CSS `filter: blur() contrast() hue-rotate() saturate() brightness() grayscale() sepia()` animés via `interpolate`
### 34. Verre dépoli (glassmorphism) — `backdropFilter: 'blur(20px)'`
### 35. Modes de fusion — `mixBlendMode: 'overlay'|'multiply'|'screen'|'color-dodge'|'difference'`
### 36. Balayage lumineux (shine) — dégradé `linear-gradient` skew qui traverse + `interpolate`
### 37. Fuites de lumière (light leaks) — `@remotion/light-leaks` (selon version) ou vidéo overlay + `mixBlendMode:'screen'`
### 38. Grain de film / bruit — SVG `<feTurbulence type="fractalNoise">` ou `noise2D`
### 39. Vignette / lueur — `radial-gradient`, `boxShadow`, `filter: drop-shadow`
### 40. Dégradés animés (« aurora », blobs) — `noise2D` pour positions + `radial-gradient` + `filter: blur(60px)`
### 41. Shaders GPU — `@remotion/skia` (`<SkiaCanvas>` + RuntimeEffect/GLSL) ou `@remotion/three` (ShaderMaterial)

---
## E. TRANSITIONS DE SCÈNES
### 42. Transitions prêtes — `@remotion/transitions`
```tsx
<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={90}><A/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-right'})} timing={springTiming({config:{damping:200}})}/>
  <TransitionSeries.Sequence durationInFrames={90}><B/></TransitionSeries.Sequence>
</TransitionSeries>
```
Présentations : `fade()`, `slide()`, `wipe()`, `flip()`, `clockWipe()`, `iris()`, `cube()` (selon version). Timings : `linearTiming()`, `springTiming()`. Possibilité de **créer sa propre présentation** (type `TransitionPresentation`).
### 43. Wipe circulaire / iris — `clipPath: circle(r% at x y)` animé
### 44. Cut sur le beat — `<Sequence from>` calés sur des frames issues de l'analyse audio

---
## F. VIDÉO & MONTAGE
### 45. Ralenti / accéléré — `<OffthreadVideo playbackRate={0.5}>`
### 46. Rampe de vitesse (speed ramp) — découper en `<Sequence>` avec `playbackRate` différent, ou `interpolate` de la progression temporelle
### 47. Arrêt sur image — `<Freeze frame={n}>`
### 48. Image dans l'image (PiP) / écran partagé — plusieurs `<OffthreadVideo>` dans des `div` positionnés + `borderRadius`, `overflow:hidden`
### 49. Découpe d'un extrait — `trimBefore/trimAfter` (ou `startFrom/endAt`)
### 50. Vidéo transparente (calque alpha) — rendre en **ProRes 4444** (`--codec=prores --prores-profile=4444`) ou **VP8/VP9 WebM** (`--codec=vp8` + `--image-format=png`) ; lire avec `<OffthreadVideo transparent>`
### 51. Incrustation fond vert (chroma key) — `<canvas>` + lecture de pixels (`getImageData`) + `delayRender`, ou SVG filter `feColorMatrix`
### 52. Fondu audio — `volume={(f)=>interpolate(f,[0,30],[0,1],{extrapolateRight:'clamp'})}`
### 53. Réactivité audio — `visualizeAudio` → échelle/couleur/position des éléments
### 54. Ducking (baisser la musique quand on parle) — `volume` fonction selon plages de voix
### 55. Changer la hauteur de voix — `<Audio toneFrequency={1.3}>`

---
## G. DONNÉES, GRAPHIQUES & INFOGRAPHIES
### 56. Barres / lignes / camemberts animés — SVG + `interpolate` + (optionnel `d3-scale`, `d3-shape`)
### 57. Bar chart race — rang lissé par `smoothstep` + `interpolate` entre étapes
### 58. Cartes / géo — `d3-geo` + `evolvePath`
### 59. Données live — `calculateMetadata` (fetch avant rendu) ou `delayRender` + `fetch`
### 60. Tableaux / KPIs — `interpolate` + `toLocaleString`

---
## H. 3D, PARTICULES, MOTEURS
### 61. Scène 3D complète — `@remotion/three` : `<ThreeCanvas>` + react-three-fiber (⚠ pas `useFrame` : piloter par `useCurrentFrame`)
### 62. Modèles GLTF — `useGLTF` (drei) + `delayRender`
### 63. Vidéo en texture 3D — `useVideoTexture` (`@remotion/three`)
### 64. Particules déterministes — boucle + `random(i)` + `noise2D`
### 65. Lottie (After Effects) — `<Lottie animationData>` (`@remotion/lottie`)
### 66. Rive — `<RemotionRiveCanvas>` (`@remotion/rive`)
### 67. GIF — `<Gif src>` (`@remotion/gif`)
### 68. Emojis animés — `<AnimatedEmoji emoji="fire">` (`@remotion/animated-emoji`)

---
## I. TYPES DE VIDÉOS À FORT IMPACT (assemblages)
- **Sous-titres TikTok/Reels** (mot surligné) : `@remotion/captions` + `createTikTokStyleCaptions` + `spring`
- **Karaoké / lyrics video** : timestamps par mot + `interpolateColors`
- **Intro/outro de chaîne**, **logo reveal**, **lower thirds** (bandeaux de titre)
- **Pubs produit** : `TransitionSeries` + `Img` + `spring`
- **Stories / Reels / Shorts** : composition 1080×1920
- **Vidéos de résultats / stats / « wrapped »** : données + `calculateMetadata`
- **Podcasts → clips vidéo** : waveform + sous-titres Whisper
- **Visualiseurs musicaux** : `visualizeAudio`
- **Vidéos personnalisées en masse** (1 vidéo par client, nom dans l'image) : props + Lambda
- **Miniatures / posters** : `<Still>` + `renderStill`
