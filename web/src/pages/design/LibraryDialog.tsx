import React from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { api, apiErrorMessage, type Project } from "../../api/client";

/**
 * Enregistrement du projet courant comme modèle réutilisable de la bibliothèque.
 *
 * Le serveur refuse un modèle invalide : la liste des erreurs est affichée
 * telle quelle plutôt que d'écrire un fichier qui casserait au premier rendu.
 */
export default function LibraryDialog({
  project,
  defaultLabel,
  onClose,
  onSaved,
}: {
  project: Project;
  defaultLabel: string;
  onClose: () => void;
  onSaved: (modelId: string) => void;
}) {
  const [label, setLabel] = React.useState(defaultLabel);
  const [description, setDescription] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string[]>([]);

  const submit = async () => {
    if (!label.trim()) {
      setError(["Le modèle doit avoir un nom."]);
      return;
    }
    setBusy(true);
    setError([]);
    try {
      const res = await api.saveLibraryModel(project, label.trim(), description.trim());
      onSaved(res.model.id);
    } catch (e) {
      setError([apiErrorMessage(e)]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="panel w-full max-w-md p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Enregistrer dans la bibliothèque</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Le projet courant devient un modèle réutilisable, écrit dans le dossier{" "}
              <code className="text-xs">models/</code>. Vous pouvez aussi le modifier à la main dans ce
              dossier.
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fermer">
            <X size={16} />
          </Button>
        </div>

        <div className="mt-4 space-y-3">
          <div>
            <Label htmlFor="model-label">Nom du modèle</Label>
            <Input
              id="model-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="ex. Citation énergique 9:16"
              disabled={busy}
            />
          </div>
          <div>
            <Label htmlFor="model-description">Description (optionnelle)</Label>
            <textarea
              id="model-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              maxLength={400}
              placeholder="Ce que le modèle produit, pour le retrouver dans la liste."
              className="mt-1 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
              disabled={busy}
            />
          </div>
        </div>

        {error.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-destructive">
            {error.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            Annuler
          </Button>
          <Button size="sm" onClick={submit} disabled={busy}>
            {busy && <Loader2 size={14} className="animate-spin" />}
            Ajouter le modèle
          </Button>
        </div>
      </div>
    </div>
  );
}
