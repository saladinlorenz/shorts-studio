import React, { useLayoutEffect } from "react";
import { continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";

function opacityOf(element: Element, root: HTMLElement): number {
  let opacity = 1;
  for (let node: Element | null = element; node; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden") return 0;
    opacity *= Number(style.opacity);
    if (node === root) break;
  }
  return opacity;
}

export function measureLayout(root: HTMLElement, frame: number, width: number, height: number) {
  const canvas = root.getBoundingClientRect();
  if (!canvas.width || !canvas.height) throw new Error("Sonde : surface de rendu vide.");
  const sx = width / canvas.width;
  const sy = height / canvas.height;
  const round = (value: number) => Math.round(value * 100) / 100;
  const elements = Array.from(root.querySelectorAll<HTMLElement>("[data-probe]")).map((element) => {
    const style = getComputedStyle(element);
    const kind = element.dataset.probeKind || "image";
    const rects: DOMRect[] = [];
    let visibleOpacity = 0;
    if (kind === "text") {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const text = walker.currentNode;
        if (!text.textContent?.trim() || !text.parentElement) continue;
        const opacity = opacityOf(text.parentElement, root);
        visibleOpacity = Math.max(visibleOpacity, opacity);
        if (opacity <= 0.01) continue;
        const range = document.createRange();
        range.selectNodeContents(text);
        rects.push(...Array.from(range.getClientRects()));
      }
    } else {
      const leaves = element.querySelectorAll("img,video,canvas");
      for (const leaf of leaves) {
        const opacity = opacityOf(leaf, root);
        visibleOpacity = Math.max(visibleOpacity, opacity);
        if (opacity > 0.01) rects.push(leaf.getBoundingClientRect());
      }
    }
    const visible = rects.filter((r) => r.width > 0 && r.height > 0);
    const fallback = element.getBoundingClientRect();
    const left = visible.length ? Math.min(...visible.map((r) => r.left)) : fallback.left;
    const top = visible.length ? Math.min(...visible.map((r) => r.top)) : fallback.top;
    const right = visible.length ? Math.max(...visible.map((r) => r.right)) : fallback.right;
    const bottom = visible.length ? Math.max(...visible.map((r) => r.bottom)) : fallback.bottom;
    const x = (left - canvas.left) * sx;
    const y = (top - canvas.top) * sy;
    const w = (right - left) * sx;
    const h = (bottom - top) * sy;
    const isVisible = visible.length > 0 && visibleOpacity > 0.01;
    return {
      id: element.dataset.probe!, kind, frame,
      x: round(x), y: round(y), w: round(w), h: round(h),
      visible: isVisible, opacity: round(visibleOpacity),
      steady: element.dataset.probeSteady === "true",
      outOfFrame: isVisible && (x < -1 || y < -1 || x + w > width + 1 || y + h > height + 1),
      // Débordement horizontal réel : les boîtes texte ont une hauteur auto, un écart
      // vertical scrollH/clientH de quelques px n'est qu'un arrondi de ligne, pas un clipping.
      textOverflow: kind === "text" && isVisible && element.scrollWidth > element.clientWidth + 1,
      safeAreaWarning: isVisible && (y < height * 0.1 || y + h > height * 0.9),
      fontSize: kind === "text" ? round(parseFloat(style.fontSize)) : null,
      smallText: kind === "text" && parseFloat(style.fontSize) < height * 0.015,
      scrollW: kind === "text" ? element.scrollWidth : null,
      clientW: kind === "text" ? element.clientWidth : null,
      scrollH: kind === "text" ? element.scrollHeight : null,
      clientH: kind === "text" ? element.clientHeight : null,
      color: kind === "text" ? style.color : null,
      contrast: null,
    };
  });
  const overlaps: Array<{ first: string; second: string; area: number }> = [];
  const text = elements.filter((e) => e.kind === "text" && e.visible && e.steady);
  for (let i = 0; i < text.length; i++) {
    for (let j = i + 1; j < text.length; j++) {
      const a = text[i];
      const b = text[j];
      const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (w > 1 && h > 1) overlaps.push({ first: a.id, second: b.id, area: round(w * h) });
    }
  }
  return {
    frame, width, height, elements, overlaps,
    limits: "Mesures DOM sur frames échantillonnées. Entrées/sorties distinguées des phases stables. Chevauchements = rectangles, pas pixels. Marge indicative haut/bas 10 %. Petite police < 1,5 % de la hauteur. Débordement = horizontal (largeur du conteneur). Contraste non mesuré sur dégradés, effets ou médias. Masques, occlusions et visibilité sur toute la durée non garantis.",
  };
}

export default function LayoutProbe({ root }: { root: React.RefObject<HTMLDivElement> }) {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  useLayoutEffect(() => {
    const handle = delayRender("mesures de mise en page");
    let cancelled = false;
    let continued = false;
    const finish = () => {
      if (!continued) {
        continued = true;
        continueRender(handle);
      }
    };
    let raf = 0;
    void document.fonts.ready.then(() => {
      raf = requestAnimationFrame(() => {
        raf = requestAnimationFrame(() => {
          if (!cancelled && root.current) {
            console.log("STUDIO_LAYOUT_PROBE " + JSON.stringify(measureLayout(root.current, frame, width, height)));
          }
          finish();
        });
      });
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      finish();
    };
  }, [frame, width, height, root]);
  return null;
}
