import type { CSSProperties } from "react";

/**
 * Transitions de scene « maison » (CSS uniquement, aucune dependance).
 *
 * Une transition decrit l'ENTREE d'une scene depuis la precedente. Le rendu
 * fait chevaucher les deux scenes sur la fenetre [B - D, B) ou B est la frame
 * de debut de la scene entrante et D la duree de la transition. La chronologie
 * resolue (start_frame / end_frame / fenetres des calques) n'est jamais modifiee :
 * le chevauchement n'existe qu'au rendu, donc l'aperçu et l'export restent
 * alignes et les projets sans transition gardent exactement le meme rendu.
 *
 * Pendant le chevauchement, la scene entrante est peinte par-dessus la sortante
 * (ordre chronologique du DOM). La progression p va de 0 (debut) a 1 (fin).
 */

export function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/** Style de la scene ENTRANTE pendant le chevauchement (p : 0 -> 1). */
export function enterStyle(type: string, p: number): CSSProperties {
  const t = clamp01(p);
  switch (type) {
    case "fade":
      // fondu enchainé : la nouvelle scene apparait par-dessus l'ancienne pleine
      return { opacity: t };
    case "dip_black":
      // creux noir : la scene entrante ne revient qu'apres la moitie de la fenetre
      return { opacity: clamp01((t - 0.5) * 2) };
    case "slide_left":
      return { transform: `translateX(${(1 - t) * 100}%)` };
    case "slide_right":
      return { transform: `translateX(${(t - 1) * 100}%)` };
    case "slide_up":
      return { transform: `translateY(${(1 - t) * 100}%)` };
    case "slide_down":
      return { transform: `translateY(${(t - 1) * 100}%)` };
    case "wipe":
      return { clipPath: `inset(0 ${(1 - t) * 100}% 0 0)` };
    case "zoom":
      return { opacity: t, transform: `scale(${0.8 + 0.2 * t})` };
    case "push":
      return { transform: `translateX(${(1 - t) * 100}%)` };
    default:
      return {};
  }
}

/** Style de la scene SORTANTE pendant le chevauchement (p : 0 -> 1). */
export function exitStyle(type: string, p: number): CSSProperties {
  const t = clamp01(p);
  switch (type) {
    case "fade":
      // l'ancienne reste pleine : le fondu entrant suffit au crossfade
      return {};
    case "dip_black":
      return { opacity: clamp01(1 - t * 2) };
    case "slide_left":
    case "slide_right":
    case "slide_up":
    case "slide_down":
      // glissement par-dessus : l'ancienne reste en place, la nouvelle la couvre
      return {};
    case "wipe":
      return {};
    case "zoom":
      return { transform: `scale(${1 + 0.1 * t})` };
    case "push":
      return { transform: `translateX(${-t * 100}%)` };
    default:
      return {};
  }
}