import React, { useEffect, useMemo, useRef, useState } from "react";
import { Img, continueRender, delayRender } from "remotion";

import type { EffectParams } from "./common";
import { clamp01, col, num } from "./common";

/**
 * Effets qui travaillent les pixels d'un media : keying sur fond vert.
 *
 * Le catalogue serveur (shortvideos/effects.py) ne propose ce traitement qu'aux
 * calques image. Le decoupe est calcule une seule fois par couple
 * (media, reglages) puis recopie a chaque frame : le cout reste a l'import, pas
 * au rendu. Aucune video de fond n'est tractee, la note du catalogue le dit.
 */

/** Le decoupe se fait a resolution reduite : 1024 px de cote suffisent pour un logo. */
const MAX_SIDE = 1024;
const CACHE_LIMIT = 6;
const cache = new Map<string, HTMLCanvasElement>();

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

/**
 * Decoupe un canal dominant : la couleur cle est retiree, le trop-plein de la
 * meme teinte (le « spill ») est ramene vers les autres canaux.
 */
function keyOut(image: HTMLImageElement, params: EffectParams): HTMLCanvasElement | null {
  const keyColor = col(params, "key_color", "#00FF00");
  const similarity = num(params, "similarity", 0.32);
  const blend = Math.max(0.0001, num(params, "blend", 0.08));
  const spill = clamp01(num(params, "spill", 0.4));

  const ratio = Math.min(1, MAX_SIDE / Math.max(1, image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * ratio));
  const height = Math.max(1, Math.round(image.naturalHeight * ratio));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, width, height);

  let frame: ImageData;
  try {
    frame = context.getImageData(0, 0, width, height);
  } catch {
    // Media distant sans en-tete CORS : le canvas est « taint », la lecture est
    // refusee par le navigateur. On retombe sur l'image entiere.
    return null;
  }

  const [kr, kg, kb] = hexToRgb(keyColor);
  const dominant = kr >= kg && kr >= kb ? 0 : kg >= kb ? 1 : 2;
  const data = frame.data;

  for (let index = 0; index < data.length; index += 4) {
    const r = data[index];
    const g = data[index + 1];
    const b = data[index + 2];
    const dr = (r - kr) / 255;
    const dg = (g - kg) / 255;
    const db = (b - kb) / 255;
    const distance = Math.sqrt(dr * dr + dg * dg + db * db) / Math.sqrt(3);
    let alpha = clamp01((distance - similarity) / blend);
    // Bord souple : la transition n'est pas une marche, sinon le logo crepite.
    alpha = alpha * alpha * (3 - 2 * alpha);
    if (alpha > 0 && spill > 0 && g > 0) {
      if (dominant === 1) {
        data[index + 1] = Math.round(g * (1 - spill) + Math.min(g, Math.max(r, b)) * spill);
      } else if (dominant === 0) {
        data[index] = Math.round(r * (1 - spill) + Math.min(r, Math.max(g, b)) * spill);
      } else {
        data[index + 2] = Math.round(b * (1 - spill) + Math.min(b, Math.max(r, g)) * spill);
      }
    }
    data[index + 3] = Math.round(data[index + 3] * alpha);
  }

  const output = document.createElement("canvas");
  output.width = width;
  output.height = height;
  const outContext = output.getContext("2d");
  if (!outContext) return null;
  outContext.putImageData(frame, 0, 0);
  return output;
}

function cachedKeying(cacheKey: string, image: HTMLImageElement, params: EffectParams): HTMLCanvasElement | null {
  const existing = cache.get(cacheKey);
  if (existing) return existing;
  const keyed = keyOut(image, params);
  if (keyed) {
    cache.set(cacheKey, keyed);
    while (cache.size > CACHE_LIMIT) {
      const oldest = cache.keys().next().value;
      if (oldest === undefined) break;
      cache.delete(oldest);
    }
  }
  return keyed;
}

interface Props {
  src: string;
  params: EffectParams;
  style: React.CSSProperties;
}

/** Image avec la couleur cle retiree, aux memes proprietes CSS que `<Img>`. */
export const KeyedImage: React.FC<Props> = ({ src, params, style }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [keyed, setKeyed] = useState<HTMLCanvasElement | null>(null);
  const [failed, setFailed] = useState(false);

  const cacheKey = useMemo(
    () =>
      [
        src,
        col(params, "key_color", "#00FF00"),
        num(params, "similarity", 0.32).toFixed(3),
        num(params, "blend", 0.08).toFixed(3),
        num(params, "spill", 0.4).toFixed(3),
      ].join("|"),
    [src, params],
  );

  const handle = useState(() => delayRender(`keying ${src}`))[0];
  useEffect(() => {
    let alive = true;
    setFailed(false);
    setKeyed(null);
    loadImage(src).then((image) => {
      if (!alive) return;
      if (!image) {
        setFailed(true);
        return;
      }
      setKeyed(cachedKeying(cacheKey, image, params));
    });
    return () => {
      alive = false;
    };
  }, [cacheKey, src, params]);

  useEffect(() => {
    if (keyed || failed) continueRender(handle);
  }, [keyed, failed, handle]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !keyed) return;
    if (canvas.width !== keyed.width || canvas.height !== keyed.height) {
      canvas.width = keyed.width;
      canvas.height = keyed.height;
    }
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(keyed, 0, 0);
  }, [keyed]);

  if (failed || !keyed) {
    // Media illisible ou cle impossible : l'image brute reste a l'ecran.
    return <Img src={src} style={style} />;
  }
  return <canvas ref={canvasRef} style={{ ...style, display: "block" }} />;
};
