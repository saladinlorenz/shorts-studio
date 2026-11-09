# 5. Code des effets : filtres, transitions, 3D, audio

**Glitch RGB**

```tsx
const jitter = random(`g-${Math.floor(frame / 2)}`) * 14 - 7;
{['#ff0000', '#00ff00', '#0000ff'].map((c, i) => (
  <div key={c} style={{
    position: 'absolute', color: c, mixBlendMode: 'screen',
    transform: `translateX(${jitter * (i - 1)}px)`,
  }}>TEXTE</div>
))}
```

**Distorsion liquide (filtre SVG animé)**

```tsx
const freq = 0.01 + Math.sin(frame / 30) * 0.005;
<svg width={0} height={0}>
  <filter id='liquid'>
    <feTurbulence type='fractalNoise' baseFrequency={freq} numOctaves={2} seed={3} />
    <feDisplacementMap in='SourceGraphic' scale={40} />
  </filter>
</svg>
<div style={{filter: 'url(#liquid)'}}>{children}</div>
```

**Fond « aurora »** : trois `div` en `radial-gradient` dont `left` et `top` valent `noise2D('a', frame / 90, 0) * width * 0.4 + width / 2`, avec `filter: blur(60px)`.

**Texte dégradé animé et néon**

```tsx
const c1 = interpolateColors(frame, [0, 90], ['#ff4d8d', '#00e5ff']);
<h1 style={{
  background: `linear-gradient(90deg, ${c1}, #7c5cff)`,
  WebkitBackgroundClip: 'text', color: 'transparent',
  textShadow: '0 0 20px #0ff, 0 0 60px #0ff',
}}>NEON</h1>
```

**Balayage lumineux (shine)** : un `div` en `linear-gradient(90deg, transparent, #ffffffcc, transparent)`, `transform: skewX(-20deg)`, dont `left` vaut `interpolate(frame, [30, 70], [-300, 1400])`, dans un parent `overflow: hidden`.

**Filtres CSS animables** : `filter: blur()`, `contrast()`, `hue-rotate()`, `saturate()`, `brightness()`, `grayscale()`, `sepia()`, `drop-shadow()` ; `backdropFilter: blur(20px)` pour le verre dépoli ; `mixBlendMode` : `screen`, `overlay`, `multiply`, `color-dodge`, `difference`.

**Transitions entre scènes** (`@remotion/transitions`)

```tsx
<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={90}><SceneA /></TransitionSeries.Sequence>
  <TransitionSeries.Transition
    presentation={slide({direction: 'from-right'})}
    timing={springTiming({config: {damping: 200}, durationInFrames: 22})} />
  <TransitionSeries.Sequence durationInFrames={90}><SceneB /></TransitionSeries.Sequence>
</TransitionSeries>
```

Présentations : `fade()`, `slide()`, `wipe()`, `flip()`, `clockWipe()`, `iris()`, `cube()` (selon version). Timings : `linearTiming()`, `springTiming()`. Durée totale = somme des séquences moins somme des transitions.

**Scène 3D** (`@remotion/three`)

```tsx
<ThreeCanvas width={width} height={height} camera={{position: [0, 2, 12], fov: 45}}>
  <ambientLight intensity={0.5} />
  <pointLight position={[10, 10, 10]} intensity={150} />
  <mesh rotation={[frame * 0.012, frame * 0.018, 0]}>
    <torusKnotGeometry args={[1.5, 0.45, 220, 36]} />
    <meshStandardMaterial color='#fff' metalness={0.95} roughness={0.12} />
  </mesh>
</ThreeCanvas>
```

**Visualiseur audio réactif** (`@remotion/media-utils`)

```tsx
const audioData = useAudioData(staticFile('musique.mp3'));
if (!audioData) return null;
const spectrum = visualizeAudio({fps, frame, audioData, numberOfSamples: 64, smoothing: true});
const bass = spectrum.slice(0, 4).reduce((a, b) => a + b, 0) / 4;
// bass pilote l'échelle d'un logo : scale(1 + bass * 0.3)
```

**Fondu audio et vitesse**

```tsx
<Audio src={staticFile('musique.mp3')}
  volume={(f) => interpolate(f, [0, 30], [0, 0.8], {extrapolateRight: 'clamp'})}
  playbackRate={1} toneFrequency={1} />
<OffthreadVideo src={staticFile('clip.mp4')} playbackRate={0.5} />
```
