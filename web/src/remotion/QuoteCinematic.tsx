import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { MediaUtilsAudioData } from "@remotion/media-utils";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  continueRender,
  delayRender,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { isWordUnit, splitUnits, unitVisual, normalizeWord } from "./animations";
import { AudioMeter } from "./effects/audio";
import type { AudioEnergy, EffectCtx } from "./effects/common";
import { KeyedImage } from "./effects/image";
import { applyLayerEffects, layerUid, type LayerFx } from "./effects/layer";
import { findEffect, needsMeasuredAudio } from "./effects/registry";
import { SceneEffects } from "./effects/scene";
import { SceneOverlays } from "./effects/overlay";
import { cssFamily, loadFontsFor, nearestWeight } from "./fonts";
import { renderMediaUrl } from "./mediaUrl";
import type {
  ImageLayer,
  Layer,
  ResolvedAudio,
  ResolvedLayer,
  ResolvedScene,
  StudioProject,
  TextLayer,
} from "./types";

/**
 * Modele « Citation cinematique » (version 2).
 *
 * Le meme composant sert a l'aperçu (Remotion Player) et a l'export
 * (`remotion render`) : il ne lit que des frames, jamais une horloge
 * independante. Les temps d'entree, de maintien et de sortie viennent du bloc
 * ``resolved`` calcule cote Python, donc l'aperçu et le rendu partagent le
 * meme calcul de chronologie.
 *
 * Mise en scene : accroche revelée par masque, citation amenée mot a mot avec
 * mots mis en valeur, plan final de signature. Trois scenes, rythme 4 s /
 * 6 s / 3,5 s, soit 13,5 s.
 */

const VIDEO_EXTENSIONS = [".mp4", ".mov", ".webm", ".mkv"];
const SCRIM_TOP = "rgba(6,6,10,0.30)";
const SCRIM_BOTTOM = "rgba(6,6,10,0.62)";
const BACKDROP_FADE_FRAMES = 8;

function isVideo(media: string): boolean {
  const clean = media.split("?")[0].toLowerCase();
  return VIDEO_EXTENSIONS.some((ext) => clean.endsWith(ext));
}

/** Arriere-plan d'une scene : media ou degrade de la palette, avec pousse lente. */
const Backdrop: React.FC<{
  scene: ResolvedScene;
  theme: StudioProject["theme"];
  frame: number;
  width: number;
  height: number;
}> = ({ scene, theme, frame, width, height }) => {
  const local = frame - scene.start_frame;
  const progress = Math.min(1, Math.max(0, local / Math.max(1, scene.duration_frames)));
  const anim = scene.background.animation;
  let scale = 1;
  if (anim === "zoom_slow") scale = 1.03 + 0.09 * progress;
  if (anim === "zoom_out") scale = 1.13 - 0.09 * progress;
  const fade = Math.min(1, local / BACKDROP_FADE_FRAMES);
  const media = renderMediaUrl(scene.background.media);
  const fit = scene.background.fit === "contain" ? "contain" : "cover";

  return (
    <AbsoluteFill style={{ opacity: fade, backgroundColor: theme.background_color }}>
      {media ? (
        isVideo(media) ? (
          <OffthreadVideo
            src={media}
            muted
            style={{ width: "100%", height: "100%", objectFit: fit, transform: `scale(${scale})` }}
          />
        ) : (
          <Img
            src={media}
            style={{
              position: "absolute",
              width: "100%",
              height: "100%",
              objectFit: fit,
              objectPosition: "50% 45%",
              transform: `scale(${scale})`,
            }}
          />
        )
      ) : (
        <AbsoluteFill
          style={{
            background: `radial-gradient(120% 90% at 50% 12%, ${theme.surface_color} 0%, ${theme.background_color} 62%, #05050A 100%)`,
            transform: anim === "zoom_slow" ? `scale(${scale})` : undefined,
          }}
        />
      )}
      {/* voile de lisibilite : le texte reste lisible sur un fond image ou video */}
      <AbsoluteFill style={{ background: `linear-gradient(180deg, ${SCRIM_TOP} 0%, rgba(6,6,10,0.18) 42%, ${SCRIM_BOTTOM} 100%)` }} />
    </AbsoluteFill>
  );
};

/** Un mot, une ligne ou un bloc anime. */
const AnimatedUnit: React.FC<{
  visual: { opacity: number; translateX: number; translateY: number; scale: number; revealHidden: number };
  emphasized: boolean;
  accentColor: string;
  children: React.ReactNode;
  inline: boolean;
}> = ({ visual, emphasized, accentColor, children, inline }) => {
  const clip = visual.revealHidden > 0 ? `inset(-12% ${visual.revealHidden * 100}% -12% -6%)` : undefined;
  return (
    <span
      style={{
        display: inline ? "inline-block" : "block",
        opacity: Math.max(0, Math.min(1, visual.opacity)),
        transform: `translate3d(${visual.translateX}px, ${visual.translateY}px, 0) scale(${visual.scale})`,
        transformOrigin: "50% 60%",
        WebkitClipPath: clip,
        clipPath: clip,
        color: emphasized ? accentColor : undefined,
        whiteSpace: inline ? "pre" : "normal",
      }}
    >
      {children}
    </span>
  );
};

/** Lettre a lettre : les mots restent coloriés si le projet les met en valeur. */
function letterAccents(text: string, emphasis: string[]): boolean[] {
  const accented: boolean[] = [];
  for (const token of text.split(/(\s+)/)) {
    const hit = isWordUnit(token) && emphasis.includes(normalizeWord(token));
    for (let index = Array.from(token).length; index > 0; index -= 1) accented.push(hit);
  }
  return accented;
}

/** Conteneur qui porte les styles ajoutes par les effets du calque. */
function fxBox(fx: LayerFx): React.CSSProperties {
  return {
    position: "relative",
    transform: fx.transform || undefined,
    transformStyle: fx.transformStyle ?? undefined,
    filter: fx.filter || undefined,
    opacity: fx.opacity,
  };
}

const TextLayerView: React.FC<{
  layer: TextLayer;
  resolved: ResolvedLayer;
  frame: number;
  fps: number;
  height: number;
  sceneCtx: EffectCtx;
}> = ({ layer, resolved, frame, fps, height, sceneCtx }) => {
  const anim = layer.animation;
  const units = splitUnits(layer.text, anim.unit);
  const stagger = anim.unit === "block" ? 0 : anim.stagger_frames;
  const emphasis = (layer.emphasis ?? []).map((w) => normalizeWord(w));
  const inline = anim.unit === "word";

  // Les effets d'un calque se jouent depuis l'apparition du calque, pas depuis
  // le debut de la scene : un ressort ou un retard doit le meme rendu quel que
  // soit l'emplacement du calque dans la chronologie.
  const ctx: EffectCtx = { ...sceneCtx, uid: layerUid(sceneCtx.uid, layer.id), local: frame - resolved.start_frame };

  const contentRef = useRef<HTMLDivElement | null>(null);
  const [measured, setMeasured] = useState(0);
  useLayoutEffect(() => {
    const node = contentRef.current;
    if (!node) return;
    const next = node.offsetHeight;
    setMeasured((previous) => (Math.abs(previous - next) > 1 ? next : previous));
  });

  const fx = applyLayerEffects({
    effects: resolved.effects,
    ctx,
    fontSizePx: resolved.font_size_px,
    contentHeight: measured,
  });
  const perLetter = fx.letterTransform;
  const letters = perLetter ? Array.from(layer.text) : null;

  const args = {
    startFrame: resolved.start_frame,
    inFrames: anim.in_frames,
    staggerFrames: stagger,
    outStartFrame: resolved.out_start_frame,
    outFrames: anim.out === "fade" ? anim.out_frames : 0,
    easing: anim.easing,
    springConfig: anim.spring,
    fps,
    heightPx: height,
  };

  const textStyle: React.CSSProperties = {
    textAlign: resolved.align,
    direction: resolved.direction,
    fontFamily: cssFamily(resolved.font_family),
    fontWeight: nearestWeight(resolved.font_family, resolved.font_weight),
    fontSize: `${resolved.font_size_px}px`,
    lineHeight: resolved.line_height,
    letterSpacing: `${resolved.letter_spacing_em}em`,
    color: resolved.color,
    textShadow: resolved.shadow ? "0 6px 26px rgba(0,0,0,0.55), 0 2px 4px rgba(0,0,0,0.45)" : "none",
    WebkitTextStroke: resolved.stroke_width_px > 0 ? `${resolved.stroke_width_px}px ${resolved.stroke_color}` : undefined,
    wordBreak: "break-word",
  };

  const boxStyle: React.CSSProperties = {
    position: "absolute",
    left: `${layer.position.x * 100}%`,
    top: `${layer.position.y * 100}%`,
    width: `${layer.position.width * 100}%`,
    transform: "translate(-50%, -50%)",
    perspective: fx.perspectivePx ? `${fx.perspectivePx}px` : undefined,
    ...textStyle,
  };

  let body: React.ReactNode;
  if (perLetter && letters) {
    // Mise en page lettre a lettre : le decoupage par unite laisse place aux
    // lettres ; l'entree du calque ne garde que l'opacite, la courbe 3D des
    // lettres devant rester seule maitresse du mouvement.
    const block = unitVisual(frame, anim, 0, { ...args, staggerFrames: 0 });
    const accents = letterAccents(layer.text, emphasis);
    let cursor = 0;
    body = (
      <span
        style={{
          ...fx.letterContainer,
          display: "inline-block",
          opacity: Math.max(0, Math.min(1, block.opacity)),
        }}
      >
        {layer.text
          .split(/(\s+)/)
          .map((token, groupIndex) => {
            const chars = Array.from(token);
            const start = cursor;
            cursor += chars.length;
            const spans = chars.map((char, index) => {
              const style = perLetter(start + index, letters.length, letters) ?? {};
              return (
                <span key={index} style={{ ...style, color: accents[start + index] ? resolved.accent_color : undefined }}>
                  {char}
                </span>
              );
            });
            return groupIndex % 2 === 1 ? (
              <React.Fragment key={groupIndex}>{spans}</React.Fragment>
            ) : (
              <span key={groupIndex} style={{ display: "inline-block", whiteSpace: "nowrap" }}>
                {spans}
              </span>
            );
          })}
      </span>
    );
  } else {
    body = units.map((unit, index) => {
      const visual = unitVisual(frame, anim, index, args);
      if (frame < resolved.start_frame && visual.opacity <= 0) return null;
      const emphasized = emphasis.includes(normalizeWord(unit));
      return (
        <AnimatedUnit
          key={`${layer.id}-${index}`}
          visual={visual}
          inline={inline}
          emphasized={emphasized}
          accentColor={resolved.accent_color}
        >
          {unit}
        </AnimatedUnit>
      );
    });
  }

  const content = fx.decorate ? fx.decorate(body) : body;

  return (
    <div style={boxStyle}>
      <div ref={contentRef} style={fxBox(fx)}>
        {content}
      </div>
    </div>
  );
};

const ImageLayerView: React.FC<{
  layer: ImageLayer;
  resolved: ResolvedLayer;
  frame: number;
  fps: number;
  height: number;
  sceneCtx: EffectCtx;
}> = ({ layer, resolved, frame, fps, height, sceneCtx }) => {
  const media = renderMediaUrl(layer.media);

  const ctx: EffectCtx = { ...sceneCtx, uid: layerUid(sceneCtx.uid, layer.id), local: frame - resolved.start_frame };
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [measured, setMeasured] = useState(0);
  useLayoutEffect(() => {
    const node = contentRef.current;
    if (!node) return;
    const next = node.offsetHeight;
    setMeasured((previous) => (Math.abs(previous - next) > 1 ? next : previous));
  });

  const fx = applyLayerEffects({
    effects: resolved.effects,
    ctx,
    fontSizePx: 0,
    contentHeight: measured,
  });
  if (!media) return null;

  const visual = unitVisual(frame, layer.animation, 0, {
    startFrame: resolved.start_frame,
    inFrames: layer.animation.in_frames,
    staggerFrames: 0,
    outStartFrame: resolved.out_start_frame,
    outFrames: layer.animation.out === "fade" ? layer.animation.out_frames : 0,
    easing: layer.animation.easing,
    springConfig: layer.animation.spring,
    fps,
    heightPx: height,
  });

  const keying = findEffect(resolved.effects, "chroma_key");
  const mediaStyle: React.CSSProperties = { width: "100%", height: "auto", display: "block" };

  const inner = (
    <div
      style={{
        transform: `translate3d(${visual.translateX}px, ${visual.translateY}px, 0) scale(${visual.scale})`,
        opacity: Math.max(0, Math.min(1, visual.opacity)) * layer.opacity,
      }}
    >
      {keying ? <KeyedImage src={media} params={keying.params} style={mediaStyle} /> : <Img src={media} style={mediaStyle} />}
    </div>
  );

  return (
    <div
      style={{
        position: "absolute",
        left: `${layer.position.x * 100}%`,
        top: `${layer.position.y * 100}%`,
        width: `${layer.position.width * 100}%`,
        transform: "translate(-50%, -50%)",
        perspective: fx.perspectivePx ? `${fx.perspectivePx}px` : undefined,
      }}
    >
      <div ref={contentRef} style={fxBox(fx)}>
        {fx.decorate ? fx.decorate(inner) : inner}
      </div>
    </div>
  );
};

/** Piste sonore. Une musique plus courte que la video est bouclee, jamais
 *  ralent ni accelerate ; les fondus sont calcules en frames par l'horloge de
 *  la composition, donc l'aperçu et l'export entendent la meme chose. */
const SoundBed: React.FC<{ audio: ResolvedAudio }> = ({ audio }) => {
  if (!audio.enabled) return null;
  const music = renderMediaUrl(audio.music);
  const voice = renderMediaUrl(audio.voice);
  if (!music && !voice) return null;

  const fps = Math.max(1, audio.fps);
  const fadeIn = Math.round(audio.music_fade_in * fps);
  const fadeOut = Math.round(audio.music_fade_out * fps);
  const musicVolume = (frame: number) => {
    let level = audio.music_volume;
    if (fadeIn > 0) level *= Math.min(1, frame / fadeIn);
    if (fadeOut > 0) level *= Math.min(1, (audio.total_frames - frame) / fadeOut);
    return Math.max(0, Math.min(1, level));
  };

  return (
    <>
      {music && <Audio src={music} loop volume={musicVolume} />}
      {voice && <Audio src={voice} volume={audio.voice_volume} />}
    </>
  );
};

/** Signature de marque : logo + nom, pose par-dessus la composition. */
const Signature: React.FC<{ project: StudioProject; frame: number }> = ({ project, frame }) => {
  const sig = project.resolved.signature;
  if (!sig.enabled) return null;
  const inFrames = Math.max(1, sig.in_frames);
  const local = frame - sig.start_frame;
  if (local < 0) return null;
  const opacity = Math.max(0, Math.min(1, local / inFrames));
  const logo = renderMediaUrl(sig.media);
  return (
    <div
      style={{
        position: "absolute",
        left: `${sig.position.x * 100}%`,
        top: `${sig.position.y * 100}%`,
        transform: `translate(-50%, -50%) scale(${0.94 + 0.06 * opacity})`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: `${Math.round(sig.font_size_px * 0.4)}px`,
        opacity,
      }}
    >
      {logo && (
        <Img src={logo} style={{ width: `${sig.logo_width_px}px`, height: "auto", display: "block" }} />
      )}
      {sig.handle.trim() && (
        <div
          style={{
            fontFamily: cssFamily(sig.font_family),
            fontWeight: nearestWeight(sig.font_family, sig.font_weight),
            fontSize: `${sig.font_size_px}px`,
            letterSpacing: "0.16em",
            color: sig.color,
            textTransform: "uppercase",
            textShadow: "0 2px 12px rgba(0,0,0,0.6)",
          }}
        >
          {sig.handle}
        </div>
      )}
    </div>
  );
};

/** Porte d'entree : aucune frame n'est mesuree ni rendue avant le chargement
 *  des polices declarees par le projet (section 7 du cahier des charges). */
function useProjectFonts(project: StudioProject): boolean {
  const wants = useMemo(
    () =>
      project.resolved.fonts
        .filter((f) => f.known)
        .flatMap((f) => f.weights.map((weight) => ({ family: f.id, weight }))),
    [project.resolved.fonts],
  );
  const [handle] = useState(() => delayRender("polices du projet"));
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    loadFontsFor(wants).then(() => {
      if (alive) setReady(true);
    });
    return () => {
      alive = false;
    };
  }, [wants]);

  useEffect(() => {
    if (ready) continueRender(handle);
  }, [ready, handle]);

  return ready;
}

export const QuoteCinematic: React.FC<{ project: StudioProject }> = ({ project }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  useProjectFonts(project);

  const resolved = project.resolved;
  const active = resolved.scenes.filter((s) => !s.hidden && frame >= s.start_frame && frame < s.end_frame);
  const music = resolved.audio.enabled ? renderMediaUrl(resolved.audio.music) : null;
  const wantsMeter = active.some(
    (scene) =>
      needsMeasuredAudio(scene.effects) ||
      scene.layers.some((layer) => needsMeasuredAudio(layer.effects)),
  );

  const renderScenes = (audio: AudioEnergy | null, audioData: MediaUtilsAudioData | null) =>
    active.map((scene) => {
      const sceneCtx: EffectCtx = {
        uid: scene.id,
        frame,
        local: frame - scene.start_frame,
        sceneFrames: scene.duration_frames,
        fps,
        width,
        height,
        seed: resolved.seed,
        audioSrc: music,
        audio,
        audioData,
      };
      const contentScene = project.content.scenes.find((s) => s.id === scene.id);
      return (
        <AbsoluteFill key={scene.id}>
          <SceneEffects effects={scene.effects} ctx={sceneCtx}>
            <Backdrop scene={scene} theme={project.theme} frame={frame} width={width} height={height} />
            {contentScene?.layers.map((layer) => {
              const layerResolved = scene.layers.find((l) => l.id === layer.id);
              if (!layerResolved || layer.hidden) return null;
              if (layer.type === "text") {
                return (
                  <TextLayerView
                    key={layer.id}
                    layer={layer}
                    resolved={layerResolved}
                    frame={frame}
                    fps={fps}
                    height={height}
                    sceneCtx={sceneCtx}
                  />
                );
              }
              return (
                <ImageLayerView
                  key={layer.id}
                  layer={layer}
                  resolved={layerResolved}
                  frame={frame}
                  fps={fps}
                  height={height}
                  sceneCtx={sceneCtx}
                />
              );
            })}
          </SceneEffects>
          {/* matieres plein cadre : grain, scanlines, spectre, curseur... */}
          <SceneOverlays effects={scene.effects} ctx={sceneCtx} />
        </AbsoluteFill>
      );
    });

  // Le decodage de la musique n'est demande que si un effet reactif en a besoin,
  // et jamais sur une scene sans piste : useAudioData echoue sur une URL vide.
  const scenes =
    wantsMeter && music ? (
      <AudioMeter src={music} frame={frame} fps={fps} measure={(audio, audioData) => renderScenes(audio, audioData)} />
    ) : (
      renderScenes(null, null)
    );

  return (
    <AbsoluteFill style={{ backgroundColor: project.theme.background_color, overflow: "hidden" }}>
      {scenes}
      <SoundBed audio={resolved.audio} />
      <Signature project={project} frame={frame} />
    </AbsoluteFill>
  );
};
