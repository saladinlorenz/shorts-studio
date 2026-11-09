# 4. Code des effets : texte, tracés, caméra

Convention : `const frame = useCurrentFrame(); const {fps, width, height} = useVideoConfig();`

**Sous-titres TikTok mot par mot** (`@remotion/captions`)

```tsx
const {pages} = createTikTokStyleCaptions({captions, combineTokensWithinMilliseconds: 800});
const ms = (frame / fps) * 1000;
const page = pages.find((p) => ms >= p.startMs && ms < p.startMs + p.durationMs);

return (
  <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 400}}>
    {page?.tokens.map((t) => {
      const active = ms >= t.fromMs && ms < t.toMs;
      const pop = spring({frame: frame - (t.fromMs / 1000) * fps, fps, config: {damping: 8}});
      return (
        <span key={t.fromMs} style={{
          color: active ? '#ffd166' : '#fff',
          transform: `scale(${active ? 1 + pop * 0.15 : 1})`,
          WebkitTextStroke: '6px #000', paintOrder: 'stroke fill',
          fontWeight: 900, fontSize: 100,
        }}>{t.text}</span>
      );
    })}
  </AbsoluteFill>
);
```

**Tracé qui se dessine** (`@remotion/paths`)

```tsx
const progress = interpolate(frame, [0, 60], [0, 1], {extrapolateRight: 'clamp'});
const {strokeDasharray, strokeDashoffset} = evolvePath(progress, path);

<svg viewBox='0 0 400 400'>
  <path d={path} fill='none' stroke='#fff' strokeWidth={6}
        strokeDasharray={strokeDasharray} strokeDashoffset={strokeDashoffset} />
</svg>
```

**Morphing de formes** : `const d = interpolatePath(progress, pathA, pathB);`

**Objet qui suit un chemin**

```tsx
const L = getLength(path);
const {x, y} = getPointAtLength(path, L * progress);
const t = getTangentAtLength(path, L * progress);
const angle = Math.atan2(t.y, t.x) * (180 / Math.PI);
// <div style={{transform: `translate(${x}px, ${y}px) rotate(${angle}deg)`}} />
```

**Formes prêtes** (`@remotion/shapes`) : `<Star points={5} innerRadius={60} outerRadius={120} fill='#ffd166' />`, `<Circle radius={80} />`, `<Pie progress={0.7} radius={100} />`, plus `makeStar()`, `makeCircle()` qui retournent un `path` réutilisable avec `evolvePath`.

**Tremblement de caméra** (`@remotion/noise`)

```tsx
const dx = noise2D('shake-x', frame / 4, 0) * 18;
const dy = noise2D('shake-y', 0, frame / 4) * 18;
<AbsoluteFill style={{transform: `translate(${dx}px, ${dy}px)`}}>{children}</AbsoluteFill>
```

**Zoom Ken Burns + parallaxe**

```tsx
const zoom = interpolate(frame, [0, durationInFrames], [1, 1.25]);
// Calque lointain : vitesse 0.3, calque proche : vitesse 1.2
const layerX = (speed: number) => -frame * speed;
```

**Flou de mouvement et traînée** (`@remotion/motion-blur`)

```tsx
<CameraMotionBlur shutterAngle={180} samples={10}><Animation /></CameraMotionBlur>
<Trail layers={20} lagInFrames={0.2} trailOpacity={0.5}><Animation /></Trail>
```

**Texte qui s'adapte à la largeur** (`@remotion/layout-utils`) : `const {fontSize} = fitText({text, withinWidth: 900, fontFamily: 'Inter', fontWeight: '800'});` ; `measureText` et `fillTextBox` mesurent et découpent le texte.

**Police Google** : `import {loadFont} from '@remotion/google-fonts/Inter'; const {fontFamily} = loadFont('normal', {weights: ['400', '800'], subsets: ['latin']});`
