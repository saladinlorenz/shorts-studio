import type { Project } from "../../api/client";

/**
 * Modifications pures du projet v2 : chaque fonction recoit un projet et en
 * retourne une COPIE. Ces fonctions sont partagees par l'editeur pour que
 * l'historique d'annulation enregistre des snapshots complets et que
 * l'enregistrement automatique reste deterministe.
 *
 * Aucune de ces regles n'est reimplementee cote serveur : la chronologie
 * resolue (frames absolues) reste calculee par shortvideos/resolve.py.
 */

export type Selection = { sceneId: string | null; layerId: string | null };

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function scenes(project: Project): any[] {
  return project?.content?.scenes ?? [];
}

export function sceneById(project: Project, sceneId: string | null): any | null {
  return scenes(project).find((s) => s.id === sceneId) ?? null;
}

export function layerById(project: Project, sceneId: string | null, layerId: string | null): any | null {
  const scene = sceneById(project, sceneId);
  return scene?.layers?.find((l: any) => l.id === layerId) ?? null;
}

export function layersOf(project: Project, sceneId: string | null): any[] {
  return sceneById(project, sceneId)?.layers ?? [];
}

function withScenes(project: Project, mutate: (scenes: any[]) => void): Project {
  const next = clone(project);
  mutate(next.content.scenes);
  return next;
}

/** Identifiant unique dans la portee donnee (scenes ou calques d'une scene). */
export function uniqueId(existing: string[], base: string): string {
  let index = 1;
  let candidate = `${base}-${index}`;
  while (existing.includes(candidate)) {
    index += 1;
    candidate = `${base}-${index}`;
  }
  return candidate;
}

export function updateScene(project: Project, sceneId: string, patch: Record<string, unknown>): Project {
  return withScenes(project, (list) => {
    const scene = list.find((s) => s.id === sceneId);
    if (scene) Object.assign(scene, patch);
  });
}

/** Un seul geste d'historique pour appliquer le meme reglage a toutes les scenes. */
export function updateAllScenes(project: Project, patch: Record<string, unknown>): Project {
  return withScenes(project, (list) => {
    for (const scene of list) Object.assign(scene, patch);
  });
}

export function updateLayer(project: Project, sceneId: string, layerId: string, patch: Record<string, unknown>): Project {
  return withScenes(project, (list) => {
    const scene = list.find((s) => s.id === sceneId);
    const layer = scene?.layers?.find((l: any) => l.id === layerId);
    if (layer) Object.assign(layer, patch);
  });
}

export function updateLayerPart(
  project: Project,
  sceneId: string,
  layerId: string,
  part: "style" | "position" | "animation",
  patch: Record<string, unknown>,
): Project {
  return withScenes(project, (list) => {
    const scene = list.find((s) => s.id === sceneId);
    const layer = scene?.layers?.find((l: any) => l.id === layerId);
    if (!layer) return;
    layer[part] = { ...(layer[part] ?? {}), ...patch };
    if (part === "animation") {
      layer[part].spring = { ...(layer[part].spring ?? {}), ...(patch.spring ?? {}) };
    }
  });
}

export function updateTheme(project: Project, patch: Record<string, unknown>): Project {
  const next = clone(project);
  next.theme = { ...(next.theme ?? {}), ...patch };
  return next;
}

export function updateSignature(project: Project, patch: Record<string, unknown>): Project {
  const next = clone(project);
  next.content.signature = { ...(next.content.signature ?? {}), ...patch };
  return next;
}

export function updateExport(project: Project, patch: Record<string, unknown>): Project {
  const next = clone(project);
  next.export = { ...(next.export ?? {}), ...patch };
  return next;
}

export function updateAudio(project: Project, patch: Record<string, unknown>): Project {
  const next = clone(project);
  next.audio = { ...(next.audio ?? {}), ...patch };
  return next;
}

/** Variations contrôlées : seule la graine est modifiable pour l'instant,
 *  elle est enregistrée dans le projet et reprise telle quelle au rendu. */
export function updateVariation(project: Project, patch: Record<string, unknown>): Project {
  const next = clone(project);
  next.variation = { ...(next.variation ?? {}), ...patch };
  return next;
}

const BLANK_SCENE_LAYERS = () => [
  {
    id: "text-1",
    type: "text",
    role: "body",
    text: "Nouveau texte",
    emphasis: [],
    hidden: false,
    locked: false,
    position: { x: 0.5, y: 0.5, width: 0.84, align: "center", direction: "ltr" },
    style: {},
    animation: {
      in: "fade",
      out: "fade",
      unit: "block",
      stagger_frames: 0,
      start_frames: 0,
      in_frames: 18,
      out_frames: 12,
      easing: "ease_out_cubic",
      spring: { damping: 16, stiffness: 140, mass: 1 },
      distance: 0.06,
    },
  },
];

export function addScene(project: Project, afterIndex: number | null = null): Project {
  return withScenes(project, (list) => {
    const ids = list.map((s) => s.id);
    const scene = {
      id: uniqueId(ids, "scene"),
      label: `Scene ${list.length + 1}`,
      duration: 3,
      hidden: false,
      background: { media: "", fit: "cover", animation: "static" },
      layers: BLANK_SCENE_LAYERS(),
    };
    const index = afterIndex === null ? list.length : afterIndex + 1;
    list.splice(index, 0, scene);
  });
}

export function removeScene(project: Project, sceneId: string): Project {
  return withScenes(project, (list) => {
    const index = list.findIndex((s) => s.id === sceneId);
    if (index >= 0) list.splice(index, 1);
  });
}

export function duplicateScene(project: Project, sceneId: string): Project {
  return withScenes(project, (list) => {
    const index = list.findIndex((s) => s.id === sceneId);
    if (index < 0) return;
    const copy = clone(list[index]);
    copy.id = uniqueId(list.map((s) => s.id), `${sceneId}-copie`);
    copy.label = `${list[index].label} (copie)`;
    copy.layers = copy.layers.map((l: any, i: number) => ({ ...l, id: `${copy.id}-l${i + 1}` }));
    list.splice(index + 1, 0, copy);
  });
}

export function moveScene(project: Project, sceneId: string, delta: number): Project {
  return withScenes(project, (list) => {
    const from = list.findIndex((s) => s.id === sceneId);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= list.length) return;
    const [item] = list.splice(from, 1);
    list.splice(to, 0, item);
  });
}

export function addLayer(project: Project, sceneId: string, type: "text" | "image"): Project {
  return withScenes(project, (list) => {
    const scene = list.find((s) => s.id === sceneId);
    if (!scene) return;
    const ids = (scene.layers ?? []).map((l: any) => l.id);
    const layer: any = BLANK_SCENE_LAYERS()[0];
    layer.id = uniqueId(ids, type === "text" ? "texte" : "image");
    if (type === "image") {
      layer.type = "image";
      layer.role = "mark";
      layer.media = "";
      layer.opacity = 1;
      layer.text = undefined;
      layer.emphasis = undefined;
      delete layer.text;
      delete layer.emphasis;
      layer.position = { x: 0.82, y: 0.9, width: 0.16, align: "center", direction: "ltr" };
      layer.animation = { ...layer.animation, out: "none", in: "fade" };
    }
    scene.layers = [...(scene.layers ?? []), layer];
  });
}

export function removeLayer(project: Project, sceneId: string, layerId: string): Project {
  return withScenes(project, (list) => {
    const scene = list.find((s) => s.id === sceneId);
    if (!scene) return;
    scene.layers = (scene.layers ?? []).filter((l: any) => l.id !== layerId);
  });
}

export function moveLayer(project: Project, sceneId: string, layerId: string, delta: number): Project {
  return withScenes(project, (list) => {
    const scene = list.find((s) => s.id === sceneId);
    if (!scene) return;
    const layers = scene.layers ?? [];
    const from = layers.findIndex((l: any) => l.id === layerId);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= layers.length) return;
    const [item] = layers.splice(from, 1);
    layers.splice(to, 0, item);
  });
}

export function toggleLayer(project: Project, sceneId: string, layerId: string, key: "hidden" | "locked"): Project {
  return withScenes(project, (list) => {
    const scene = list.find((s) => s.id === sceneId);
    const layer = scene?.layers?.find((l: any) => l.id === layerId);
    if (layer) layer[key] = !layer[key];
  });
}

/** Duree totale et repartition, pour l'affichage de la chronologie. */
export function durations(project: Project): { total: number; perScene: Array<{ id: string; label: string; duration: number }> } {
  const perScene = scenes(project).map((s) => ({ id: s.id, label: s.label ?? s.id, duration: Number(s.duration) || 0 }));
  return { total: perScene.reduce((sum, s) => sum + s.duration, 0), perScene };
}
