import React from "react";
import { api, type Project } from "../api/client";

/** Page Projets : liste, ouverture, suppression (données réelles du serveur). */
export default function ProjectsPage() {
  const [items, setItems] = React.useState<
    Array<{ name: string; version: number | null; size: number; modified: number }>
  >([]);
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.listProjects());
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const remove = async (name: string) => {
    if (!window.confirm(`Supprimer le projet « ${name} » ? Cette action est définitive.`)) return;
    try {
      await api.deleteProject(name);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const openInEditor = (name: string, version: number | null) => {
    // v2 → espace Design ; v1 → éditeur historique (qui propose la conversion).
    const page = version === 2 ? "design" : "short-videos";
    window.location.href = `/${page}?project=${encodeURIComponent(name)}`;
  };

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="text-lg font-semibold">Projets</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Projets enregistrés par le serveur (dossier <code className="text-xs">projects/</code>).
      </p>

      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

      <div className="panel mt-4 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2.5">Nom</th>
              <th className="px-4 py-2.5">Format</th>
              <th className="px-4 py-2.5">Taille</th>
              <th className="px-4 py-2.5">Modifié</th>
              <th className="px-4 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  Chargement…
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  Aucun projet enregistré. Créez un projet dans Design, ou convertissez un projet v1.
                </td>
              </tr>
            )}
            {!loading &&
              items.map((it) => (
                <tr key={it.name} className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-2.5 font-medium">{it.name}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {it.version === null ? <span className="text-warning">illisible</span> : `v${it.version}`}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">{Math.ceil(it.size / 1024)} Ko</td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {new Date(it.modified * 1000).toLocaleString("fr-FR")}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      className="rounded-md border border-input px-2.5 py-1 text-xs hover:bg-accent"
                      onClick={() => openInEditor(it.name, it.version)}
                    >
                      Ouvrir
                    </button>
                    <button
                      className="ml-2 rounded-md border border-destructive/60 px-2.5 py-1 text-xs text-destructive hover:bg-destructive/10"
                      onClick={() => remove(it.name)}
                    >
                      Supprimer
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export type { Project };
