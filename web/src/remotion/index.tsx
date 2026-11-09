import React from "react";
import { Composition, registerRoot } from "remotion";
import { MODEL_REGISTRY } from "./registry";

/**
 * Point d'entree Remotion pour le rendu CLI (`remotion render`).
 *
 * Une entree du registre = une composition, avec les MEMES composants que
 * ceux montes dans le Remotion Player de l'interface. Dimensions, fps et
 * duree viennent des props du projet resollu (calculateMetadata), donc le
 * fichier de props est la seule source de verite du rendu.
 */
const RemotionRoot: React.FC = () => (
  <>
    {Object.values(MODEL_REGISTRY).map((model) => (
      <Composition
        key={model.compositionId}
        id={model.compositionId}
        component={model.component as never}
        width={1080}
        height={1920}
        fps={30}
        durationInFrames={1}
        defaultProps={model.defaultProps}
        calculateMetadata={({ props }) => {
          const dims = model.dims(props as Record<string, unknown>);
          return {
            width: dims.width,
            height: dims.height,
            fps: dims.fps,
            durationInFrames: dims.durationInFrames,
            props,
          };
        }}
      />
    ))}
  </>
);

registerRoot(RemotionRoot);
