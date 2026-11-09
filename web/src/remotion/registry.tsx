import React from "react";
import { QuoteCinematic } from "./QuoteCinematic";
import { QuoteVertical, defaultQuoteProject, projectDims } from "./QuoteVertical";
import type { StudioProject } from "./types";

/**
 * Registre des modeles.
 *
 * L'identifiant de la composition vient du PROJET (model.id), jamais d'une
 * chaine codee en dur dans le serveur : l'aperçu et le rendu resolution
 * toujours le meme entree. Ajouter un modele = ajouter une entree ici et la
 * reference correspondante dans shortvideos/schema.MODELS.
 */

export interface CompositionDims {
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
}

export interface ModelDefinition {
  id: string;
  /** Identifiant Remotion de la composition : Remotion refuse les « _ »,
   *  les ids de modele du projet restent donc en snake_case et sont maps ici. */
  compositionId: string;
  label: string;
  version: number;
  component: React.ComponentType<Record<string, unknown>>;
  defaultProps: Record<string, unknown>;
  dims: (props: Record<string, unknown>) => CompositionDims;
}

function studioDims(props: Record<string, unknown>): CompositionDims {
  const project = (props?.project ?? null) as StudioProject | null;
  const resolved = project?.resolved;
  if (!resolved) {
    return { width: 1080, height: 1920, fps: 30, durationInFrames: 1 };
  }
  return {
    width: resolved.width,
    height: resolved.height,
    fps: resolved.fps,
    durationInFrames: Math.max(1, resolved.total_frames),
  };
}

function legacyDims(props: Record<string, unknown>): CompositionDims {
  const project = props?.project as Parameters<typeof projectDims>[0] | undefined;
  return projectDims(project ?? defaultQuoteProject());
}

export const MODEL_REGISTRY: Record<string, ModelDefinition> = {
  quote_cinematic: {
    id: "quote_cinematic",
    compositionId: "quote-cinematic",
    label: "Citation cinématique",
    version: 1,
    component: QuoteCinematic as unknown as React.ComponentType<Record<string, unknown>>,
    defaultProps: { project: null },
    dims: studioDims,
  },
  quote_vertical: {
    id: "quote_vertical",
    compositionId: "quote-vertical",
    label: "Citation verticale (héritage v1)",
    version: 1,
    component: QuoteVertical as unknown as React.ComponentType<Record<string, unknown>>,
    defaultProps: { project: defaultQuoteProject() },
    dims: legacyDims,
  },
};

/** Index par identifiant Remotion : c'est celui que renvoie /api/studio/prepare. */
export const COMPOSITION_INDEX: Record<string, ModelDefinition> = Object.fromEntries(
  Object.values(MODEL_REGISTRY).map((model) => [model.compositionId, model]),
);
