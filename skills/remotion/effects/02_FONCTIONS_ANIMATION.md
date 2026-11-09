# 2. Fonctions d'animation (référence détaillée)

| Fonction | Signature | Options importantes |
| --- | --- | --- |
| `interpolate` | `interpolate(valeur, plageEntrée, plageSortie, options)` | `extrapolateLeft` / `extrapolateRight` : `clamp`, `extend`, `identity`, `wrap` ; `easing` |
| `interpolateColors` | `interpolateColors(valeur, plageEntrée, [couleurs])` | accepte hex, rgb, hsl, noms CSS |
| `spring` | `spring({frame, fps, config, delay, durationInFrames, from, to, reverse})` | `config: {damping, mass, stiffness, overshootClamping}` |
| `measureSpring` | `measureSpring({fps, config})` | retourne la durée réelle du spring en frames |
| `Easing` | `Easing.in()`, `Easing.out()`, `Easing.inOut()` | `linear`, `ease`, `quad`, `cubic`, `poly(n)`, `sin`, `circle`, `exp`, `elastic(b)`, `back(s)`, `bounce`, `bezier(x1,y1,x2,y2)`, `step0`, `step1` |
| `random` | `random(seed)` | même seed = même résultat à chaque rendu ; `random(null)` renvoie un vrai hasard : à éviter en rendu |

**Réglages de spring courants**

| Effet recherché | `config` |
| --- | --- |
| Lisse, sans rebond | `{damping: 200}` |
| Vif et net | `{damping: 20, stiffness: 200}` |
| Rebondissant | `{damping: 8}` |
| Lourd et lent | `{mass: 3, damping: 10, stiffness: 100}` |

**Exemples de base**

```tsx
const frame = useCurrentFrame();
const {fps, durationInFrames} = useVideoConfig();

// Fondu entrant puis sortant
const opacity = interpolate(
  frame,
  [0, 20, durationInFrames - 20, durationInFrames],
  [0, 1, 1, 0],
  {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
);

// Entrée avec rebond, décalée de 10 frames
const s = spring({frame, fps, delay: 10, config: {damping: 8}});
const scale = interpolate(s, [0, 1], [0.5, 1]);

// Couleur animée
const color = interpolateColors(frame, [0, 60], ['#ff4d8d', '#00e5ff']);
```

**Utilitaires de style** (`@remotion/animation-utils`) : `makeTransform([translateX(10), rotate(45), scale(1.2)])`, `interpolateStyles(frame, [0, 30], [stylesA, stylesB])`, et les helpers `translateX/Y/Z`, `rotate`, `scale`, `skew`, `perspective`, `matrix`.
