import React from "react";
import { Download, Package, RefreshCw } from "lucide-react";
import { api, apiErrorMessage, type Batch, type DeliveryStatus } from "../api/client";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { ErrorNote, JobStatus } from "../components/job-status";
import { cancelJob, formatBytes, formatDuration, useJobPolling } from "../lib/jobs";

/**
 * Page Livraison : assembler et telecharger le paquet commercial d'un lot.
 *
 * La page ne recalcule rien : elle lit l'etat du lot (via /api/delivery), lance
 * l'assemblage du ZIP dans un job deja utilise pour les lots, puis propose le
 * telechargement. Les sous-titres et miniatures viennent des fenetres reellement
 * rendues et du MP4 deja ecrit ; les metadonnees sont le bloc publish du projet,
 * recopie tel quel. Aucune valeur n'est inventee ici.
 */

const STATUT_LABEL: Record<string, string> = {
  queued: "en attente",
  running: "en cours",
  done: "rendue",
  failed: "echouee",
  cancelled: "annulee",
  blocked: "bloquee",
};

function Select({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (id: string) => void;
  children: React.ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
    >
      {children}
    </select>
  );
}

export default function LivraisonPage() {
  const [batches, setBatches] = React.useState<Batch[]>([]);
  const [batchId, setBatchId] = React.useState("");
  const [status, setStatus] = React.useState<DeliveryStatus | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");

  const { job, pollError } = useJobPolling(jobId);

  const loadBatches = React.useCallback(async () => {
    try {
      const res = await api.batchList();
      setBatches(res.batches);
      setBatchId((current) => current || res.batches[0]?.id || "");
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  }, []);

  const loadStatus = React.useCallback(async (id: string) => {
    if (!id) {
      setStatus(null);
      return;
    }
    try {
      setStatus(await api.deliveryStatus(id));
    } catch (e) {
      setError(apiErrorMessage(e));
      setStatus(null);
    }
  }, []);

  React.useEffect(() => {
    void loadBatches();
  }, [loadBatches]);

  React.useEffect(() => {
    void loadStatus(batchId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  // une fois le job d'assemblage termine : relire l'etat pour afficher le paquet
  React.useEffect(() => {
    if (!job || job.status === "running") return;
    void loadStatus(batchId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  const prepare = async () => {
    if (!batchId) return;
    setError("");
    try {
      const res = await api.deliveryPackage(batchId);
      setJobId(res.job_id);
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  const rendered = status?.rendered ?? 0;
  const pack = status?.package ?? null;

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold">
            <Package size={20} /> Livraison
          </h1>
          <p className="text-xs text-muted-foreground">
            Paquet ZIP d'un lot : vidéos, sous-titres (.srt), miniatures, métadonnées et manifeste.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void loadBatches()}>
          <RefreshCw size={14} className="mr-1" /> Recharger les lots
        </Button>
      </div>

      <ErrorNote>{error}</ErrorNote>

      <section className="panel p-4">
        <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
          <label className="space-y-1 text-xs">
            <span className="font-medium">Lot a livrer</span>
            <Select value={batchId} onChange={setBatchId}>
              {batches.length === 0 && <option value="">Aucun lot produit</option>}
              {batches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} — {b.counters.rendered}/{b.counters.total} rendues
                </option>
              ))}
            </Select>
          </label>
          <Button size="sm" onClick={() => void prepare()} disabled={!batchId || rendered === 0 || job?.status === "running"}>
            Préparer le paquet
          </Button>
        </div>

        {status && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline">{status.batch.name}</Badge>
            <span className="text-muted-foreground">
              {rendered}/{status.total} vidéos rendues
            </span>
            {status.is_packaging && <Badge variant="outline">empaquetage en cours</Badge>}
          </div>
        )}

        {!status && batchId && !error && <p className="mt-2 text-xs text-muted-foreground">Chargement de l'état…</p>}
        {status && rendered === 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            Aucune vidéo rendue dans ce lot : rien à livrer. Lancez le lot depuis Production.
          </p>
        )}
      </section>

      {job && (
        <section className="panel p-4">
          <h2 className="mb-2 text-sm font-semibold">Assemblage du paquet</h2>
          <JobStatus
            job={job}
            pollError={pollError}
            runningLabel="Empaquetage des vidéos…"
            onCancel={job.status === "running" && jobId ? () => void cancelJob(jobId) : undefined}
          />
        </section>
      )}

      {pack && (
        <section className="panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Paquet prêt</h2>
            <a
              href={api.deliveryPackageUrl(status!.batch.id)}
              className="inline-flex items-center gap-1 rounded-md border border-input px-2.5 py-1 text-xs hover:bg-accent"
            >
              <Download size={12} /> {pack.file}
            </a>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>{formatBytes(pack.bytes)}</span>
            <span>{pack.videos ?? 0} vidéo(s)</span>
            <span>{pack.subtitles ?? 0} sous-titre(s)</span>
            <span>{pack.thumbnails ?? 0} miniature(s)</span>
            <span>{pack.metadata ?? 0} métadonnée(s)</span>
            {pack.prepared_at && <span>préparé le {pack.prepared_at}</span>}
          </div>
          {pack.warnings && pack.warnings.length > 0 && (
            <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
              {pack.warnings.map((w, i) => (
                <li key={i}>— {w}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {status && status.items.length > 0 && (
        <section className="panel overflow-hidden">
          <h2 className="border-b border-border px-4 py-2 text-sm font-semibold">Lignes du lot</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-muted-foreground">
                <tr className="text-left">
                  <th className="px-3 py-1 font-medium">#</th>
                  <th className="px-3 py-1 font-medium">Nom</th>
                  <th className="px-3 py-1 font-medium">Fichier</th>
                  <th className="px-3 py-1 font-medium">Statut</th>
                  <th className="px-3 py-1 font-medium">Durée</th>
                  <th className="px-3 py-1 font-medium">Taille</th>
                </tr>
              </thead>
              <tbody>
                {status.items.map((item) => (
                  <tr key={item.position} className="border-t border-border">
                    <td className="px-3 py-1 font-mono">{item.position}</td>
                    <td className="max-w-[16rem] truncate px-3 py-1">{item.nom || "—"}</td>
                    <td className="max-w-[16rem] truncate px-3 py-1 font-mono text-[11px] text-muted-foreground">
                      {item.fichier}
                    </td>
                    <td className="px-3 py-1">
                      <span className={item.rendered ? "" : "text-muted-foreground"}>
                        {STATUT_LABEL[item.statut] ?? item.statut}
                      </span>
                    </td>
                    <td className="px-3 py-1">{formatDuration(item.duree_s || null)}</td>
                    <td className="px-3 py-1">{item.octets ? formatBytes(item.octets) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
