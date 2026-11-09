import React from "react";
import { api, apiErrorMessage, type LibraryModel } from "../api/client";

/**
 * Bibliothèque de modèles.
 *
 * Un modèle est un projet version 2 posé dans le dossier `models/` : il est
 * rendu par la composition Remotion déclarée dans `model.id`, donc ajouter un
 * modèle ne demande aucun code. Deux façons de l'ajouter — l'enregistrement
 * depuis l'éditeur Design, ou un fichier JSON déposé dans le dossier.
 */
export default function LibraryPage() {
  const [items, setItems] = React.useState<LibraryModel[]>([]);
  const [folder, setFolder] = React.useState("models");
  const [folderPath, setFolderPath] = React.useState("");
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.libraryModels();
      setItems(res.models);
      setFolder(res.folder);
      setFolderPath(res.folder_path);
      setError("");
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const remove = async (model: LibraryModel) => {
    if (!window.confirm(`Retirer le modèle « ${model.label } » de la bibliothèque ?`)) return;
    try {
      await api.deleteLibraryModel(model.id);
      await load();
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const useModel = (model: LibraryModel) => {
    window.location.href = `/design?model=${encodeURIComponent(model.id)}`;
  };

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="text-lg font-semibold">Bibliothèque de modèles</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Chaque modèle est un projet version 2 complet : scènes, calques, typographie, animations,
        thème et signature. Il s'ouvre dans Design comme point de départ, puis reste modifiable.
      </p>

      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

      <div className="panel mt-4 p-4 text-sm">
        <div className="font-medium">Ajouter vos propres modèles</div>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
          <li>
            Depuis Design : réglages faits, bouton <span className="text-foreground">Enregistrer dans la
            bibliothèque</span> — le projet courant devient un réutilisable.
          </li>
          <li>
            À la main : déposez un fichier JSON dans <code className="text-xs">{folder}/</code>
            {folderPath && <span className="text-foreground"> ({folderPath})</span>} en copiant un modèle
            existant. Seuls <code className="text-xs">version: 2</code> et
            un <code className="text-xs">model.id</code> connu sont acceptés ; rechargez cette page ensuite.
          </li>
        </ol>
        <p className="mt-2 text-xs text-muted-foreground">
          Un modèle invalide est refusé à l'enregistrement avec les mêmes erreurs que l'export ; les
          fichiers non conformes apparaissent en lecture impossible et ne sont jamais écrasés.
        </p>
      </div>

      {loading && <p className="mt-4 text-sm text-muted-foreground">Chargement…</p>}

      {!loading && items.length === 0 && (
        <p className="mt-4 text-sm text-muted-foreground">Aucun modèle dans la bibliothèque.</p>
      )}

      {!loading && (
        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {items.map((model) => (
            <article key={model.id} className="panel flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-sm font-semibold leading-tight">{model.label}</h2>
                <span
                  className={[
                    "shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
                    model.builtin
                      ? "border-border text-muted-foreground"
                      : "border-accent/50 text-accent-foreground",
                  ].join(" ")}
                >
                  {model.builtin ? "intégré" : "perso"}
                </span>
              </div>

              {model.description && (
                <p className="mt-2 line-clamp-3 text-xs text-muted-foreground">{model.description}</p>
              )}

              {model.unreadable ? (
                <p className="mt-2 text-xs text-warning">Fichier illisible : {model.file}</p>
              ) : (
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <div>Composition</div>
                  <div className="text-right text-foreground">{model.model_id ?? "—"}</div>
                  <div>Scènes</div>
                  <div className="text-right text-foreground">{model.scenes}</div>
                  <div>Durée</div>
                  <div className="text-right text-foreground">{model.duration} s</div>
                  <div>Cadre</div>
                  <div className="text-right text-foreground">
                    {model.width}×{model.height} · {model.fps} fps
                  </div>
                  <div>Médias</div>
                  <div className="text-right text-foreground">{model.media_count}</div>
                  {model.file && (
                    <>
                      <div>Fichier</div>
                      <div className="truncate text-right text-foreground">{model.file}</div>
                    </>
                  )}
                </dl>
              )}

              <div className="mt-4 flex items-center gap-2">
                <button
                  className="rounded-md border border-input px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
                  disabled={!!model.unreadable}
                  onClick={() => useModel(model)}
                >
                  Utiliser ce modèle
                </button>
                {!model.builtin && (
                  <button
                    className="rounded-md border border-destructive/60 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                    onClick={() => void remove(model)}
                  >
                    Retirer
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
