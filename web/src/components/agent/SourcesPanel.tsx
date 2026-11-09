import React from "react";
import { BookOpen, ChevronDown, ChevronRight, Cpu, Loader2, RefreshCw } from "lucide-react";
import { api, apiErrorMessage, type ProposalSource } from "../../api/client";

interface Props {
  sources: ProposalSource[];
  meta: Record<string, any> | null;
  knowledge: { engine?: string; docs?: number; chunks?: number; built?: boolean } | null;
}

/**
 * Sources et technique : ce que l'assistant a lu, et ce qu'il a réellement
 * envoyé au modèle. Les chiffres de contexte sont des ESTIMATIONS, jamais une
 * mesure du tokenizer du serveur.
 */
export default function SourcesPanel({ sources, meta, knowledge }: Props) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<Array<Record<string, any>> | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const search = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.agentSearch(query.trim(), 5);
      setResults(r.passages);
    } catch (e) {
      setError(apiErrorMessage(e));
      setResults(null);
    } finally {
      setBusy(false);
    }
  };

  const rebuild = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api.agentIndex(true);
      setResults(null);
      setError(r.built ? "" : `Index non reconstruit : ${String(r.error || "cause inconnue")}`);
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const sections = meta?.context_sections as Record<string, number> | undefined;

  return (
    <div className="mt-2 rounded-md border border-border/70 bg-muted/20">
      <button
        className="flex w-full items-center gap-1.5 px-2 py-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <BookOpen size={12} />
        Sources ({sources.length}) · technique
      </button>

      {open && (
        <div className="space-y-2 px-2 pb-2 text-[11px]">
          <div className="flex gap-1">
            <input
              className="input-base h-7 flex-1 text-[11px]"
              placeholder="Chercher dans la documentation du studio…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void search();
              }}
            />
            <button className="rounded-md border border-border px-2 text-[11px] hover:bg-muted" onClick={search} disabled={busy}>
              {busy ? <Loader2 size={12} className="animate-spin" /> : "Chercher"}
            </button>
            <button
              className="rounded-md border border-border px-2 text-[11px] hover:bg-muted"
              onClick={rebuild}
              disabled={busy}
              title="Reconstruire l'index (FTS5) à partir des documents actuels"
            >
              <RefreshCw size={11} />
            </button>
          </div>
          {error && <p className="text-destructive">{error}</p>}

          {results && results.length === 0 && <p className="text-muted-foreground">Aucun passage trouvé.</p>}
          {(results || sources).slice(0, 8).map((item: any, index) => (
            <div key={`${item.id ?? "r"}-${index}`} className="rounded border border-border/60 bg-background/60 px-2 py-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-medium">{item.title}</span>
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {item.source} · v{item.version} {typeof item.score === "number" ? `· ${item.score.toFixed(1)}` : ""}
                </span>
              </div>
              <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">{item.path}</p>
              {item.excerpt && <p className="mt-1 line-clamp-3 text-muted-foreground">{item.excerpt}</p>}
              {item.truncated && <p className="text-[10px] text-warning">passage coupé (budget de sections)</p>}
            </div>
          ))}

          {meta && (
            <div className="rounded border border-border/60 bg-background/60 px-2 py-1.5">
              <div className="mb-1 flex items-center gap-1 font-medium">
                <Cpu size={11} /> Ce qui a été envoyé au modèle
              </div>
              <ul className="space-y-0.5 text-muted-foreground">
                <li>
                  fournisseur {String(meta.provider || "?")} · modèle {String(meta.model || "?")} ·{" "}
                  {Number(meta.latency_ms || 0)} ms
                </li>
                <li>
                  contexte estimé {Number(meta.estimated_input_tokens || 0)} tokens / budget{" "}
                  {Number(meta.context_budget_tokens || 0)} · projet en {String(meta.project_detail)} ·{" "}
                  {String(meta.prompt_mode)}
                  {meta.context_shrunk ? " · réduit après refus du serveur" : ""}
                </li>
                <li>
                  tentatives de réparation {Number(meta.attempts || 0)} · outils de lecture{" "}
                  {Number(meta.tool_calls || 0)} · sortie {Number(meta.raw_length || 0)} caractères
                </li>
                <li>json_mode {String(meta.json_mode)} · index {String(meta.knowledge_engine || knowledge?.engine || "?")}</li>
                {(meta.rejected_errors as string[] | undefined)?.length ? (
                  <li className="text-warning">rejeté puis corrigé : {String(meta.rejected_errors[0]).slice(0, 120)}</li>
                ) : null}
                {((meta.context_dropped as string[]) || []).length ? (
                  <li>sections supprimées pour tenir : {(meta.context_dropped as string[]).join(", ")}</li>
                ) : null}
                {((meta.context_trimmed as string[]) || []).length ? (
                  <li>sections tronquées : {(meta.context_trimmed as string[]).join(", ")}</li>
                ) : null}
              </ul>
              {sections && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {Object.entries(sections).map(([name, size]) => (
                    <span key={name} className="rounded bg-muted px-1 text-[10px]">
                      {name} {size}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-1 text-[10px] italic">
                Estimations (3 caractères ≈ 1 token) : la fenêtre réelle est celle du serveur.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
