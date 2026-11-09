import React from "react";
import { Check, Loader2, Trash2, X } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { api, apiErrorMessage, type BrandPackSummary, type Project } from "../../api/client";

/**
 * Packs de marque client : appliquer, créer depuis le projet courant, supprimer.
 *
 * Le serveur ne remplace jamais un projet de lui-même : « Appliquer » renvoie le
 * projet patché, que l'éditeur reçoit comme une modification normale (Annuler /
 * Rétablir et sauvegarde automatique s'appliquent). Les avertissements du serveur
 * sont affichés tels quels, sans être masqués.
 */
export default function BrandPacksDialog({
  project,
  onClose,
  onApply,
}: {
  project: Project;
  onClose: () => void;
  onApply: (patched: Project) => void;
}) {
  const [brands, setBrands] = React.useState<BrandPackSummary[]>([]);
  const [selected, setSelected] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [warnings, setWarnings] = React.useState<string[]>([]);

  const refresh = React.useCallback(async () => {
    try {
      const res = await api.brandList();
      setBrands(res.brands);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const apply = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    setWarnings([]);
    try {
      const res = await api.brandApply(selected, project);
      onApply(res.project);
      setWarnings(res.warnings);
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const capture = async () => {
    if (!label.trim()) {
      setError("Un pack doit porter un nom de client.");
      return;
    }
    setBusy(true);
    setError("");
    setWarnings([]);
    try {
      const res = await api.brandCapture(project, label.trim(), notes.trim());
      setWarnings(res.warnings);
      setLabel("");
      setNotes("");
      await refresh();
      setSelected(res.brand.id);
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await api.brandDelete(selected);
      setSelected("");
      await refresh();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="panel w-full max-w-lg p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Packs de marque</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Logo, couleurs, polices, signature, musique et modèles autorisés d'un client, réutilisables
              d'une vidéo à l'autre. Écrits dans le dossier <code className="text-xs">brands/</code>.
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fermer" disabled={busy}>
            <X size={16} />
          </Button>
        </div>

        <div className="mt-4">
          <Label className="text-xs">Pack enregistré</Label>
          {brands.length === 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">Aucun pack : créez-en un depuis ce projet.</p>
          ) : (
            <div className="mt-1 max-h-44 space-y-1 overflow-y-auto">
              {brands.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => setSelected(b.id)}
                  className={
                    "flex w-full items-center justify-between rounded-md border px-2.5 py-1.5 text-left text-xs " +
                    (selected === b.id ? "border-ring bg-accent" : "border-border hover:bg-accent/60")
                  }
                >
                  <span className="truncate font-medium">{b.label}</span>
                  <span className="ml-2 shrink-0 text-muted-foreground">
                    {b.has_logo ? "logo " : ""}
                    {b.has_music ? "musique " : ""}
                    {b.models.length > 0 ? `${b.models.length} modèle(s)` : ""}
                    {b.unreadable ? " (illisible)" : ""}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 space-y-3 rounded-md border border-border p-3">
          <div>
            <Label htmlFor="brand-new-label" className="text-xs">
              Créer un pack depuis ce projet
            </Label>
            <Input
              id="brand-new-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="ex. Client Cinémoche"
              disabled={busy}
              className="mt-1"
            />
          </div>
          <div>
            <Label htmlFor="brand-new-notes" className="text-xs">
              Note interne (optionnelle)
            </Label>
            <textarea
              id="brand-new-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              maxLength={600}
              placeholder="Ce qui est imposé par le client, pour le retrouver."
              className="mt-1 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
              disabled={busy}
            />
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
        {warnings.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-warning">
            {warnings.map((w) => (
              <li key={w}>· {w}</li>
            ))}
          </ul>
        )}

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          {selected && (
            <Button variant="ghost" size="sm" onClick={remove} disabled={busy} title="Supprimer ce pack">
              <Trash2 size={14} />
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={capture} disabled={busy}>
            Créer depuis ce projet
          </Button>
          <Button size="sm" onClick={apply} disabled={busy || !selected}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            Appliquer au projet
          </Button>
        </div>
      </div>
    </div>
  );
}
