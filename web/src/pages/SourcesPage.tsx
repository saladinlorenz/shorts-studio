import React from "react";
import {
  Aperture,
  AudioLines,
  Camera,
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  Globe,
  Image as ImageIcon,
  KeyRound,
  Landmark,
  Loader2,
  Music,
  RefreshCw,
  Rocket,
  Search,
  SearchX,
  ShieldCheck,
  Telescope,
  Trash2,
  XCircle,
  Zap,
} from "lucide-react";
import {
  api,
  apiErrorMessage,
  type ContentSource,
  type SourceTestResult,
} from "../api/client";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Switch } from "../components/ui/switch";
import { cn } from "../lib/utils";

/**
 * Banques de contenu — le terrain de la récupération.
 *
 * Chaque fournisseur du catalogue serveur a sa carte : clé en écriture seule
 * (jamais renvoyée, seul un indice des 4 derniers caractères est affiché),
 * test de connexion réel exécuté par le serveur, activation pour la future
 * récupération. Aucun contenu n'est téléchargé ici : la recherche et l'import
 * se brancheront sur ces accès.
 */

const SOURCE_STYLE: Record<string, { icon: React.ComponentType<{ size?: number | string; className?: string }>; accent: string }> = {
  pexels: { icon: Camera, accent: "#05A081" },
  pixabay: { icon: ImageIcon, accent: "#2EC66D" },
  unsplash: { icon: Aperture, accent: "#A7B4C4" },
  nasa: { icon: Rocket, accent: "#5B8DEF" },
  freesound: { icon: AudioLines, accent: "#FF8A3D" },
  jamendo: { icon: Music, accent: "#E85D9E" },
  archive: { icon: Landmark, accent: "#C9A227" },
};

const KIND_META: Record<string, { label: string; color: string }> = {
  video: { label: "Vidéo", color: "#5B8DEF" },
  photo: { label: "Photo", color: "#2EC66D" },
  audio: { label: "Audio", color: "#FF8A3D" },
  music: { label: "Musique", color: "#E85D9E" },
  space: { label: "Espace", color: "#8B7CF6" },
  archive: { label: "Archives", color: "#C9A227" },
};

const KIND_FILTERS = ["all", "video", "photo", "audio", "music", "space", "archive"] as const;
type KindFilter = (typeof KIND_FILTERS)[number];
type StatusFilter = "all" | "ready" | "todo";

function statusBadge(p: ContentSource) {
  if (!p.enabled) return <Badge variant="outline">En pause</Badge>;
  if (p.ready) return <Badge variant="success">Prête</Badge>;
  if (p.key_required) return <Badge variant="warning">Clé requise</Badge>;
  return <Badge variant="secondary">Public</Badge>;
}

interface Flash {
  kind: "ok" | "error";
  msg: string;
}

function SourceCard({
  provider,
  index,
  onUpdated,
}: {
  provider: ContentSource;
  index: number;
  onUpdated: (next: ContentSource) => void;
}) {
  const style = SOURCE_STYLE[provider.id] ?? { icon: Globe, accent: "#5B8DEF" };
  const Icon = style.icon;
  const [draft, setDraft] = React.useState("");
  const [showKey, setShowKey] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [toggling, setToggling] = React.useState(false);
  const [clearing, setClearing] = React.useState(false);
  const [confirmClear, setConfirmClear] = React.useState(false);
  const [result, setResult] = React.useState<SourceTestResult | null>(null);
  const [flash, setFlash] = React.useState<Flash | null>(null);
  const flashTimer = React.useRef<number | undefined>(undefined);
  const clearTimer = React.useRef<number | undefined>(undefined);

  React.useEffect(() => () => {
    window.clearTimeout(flashTimer.current);
    window.clearTimeout(clearTimer.current);
  }, []);

  const say = (next: Flash) => {
    setFlash(next);
    window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => setFlash(null), 5000);
  };

  const saveKey = async () => {
    const typed = draft.trim();
    if (!typed || saving) return;
    setSaving(true);
    try {
      const r = await api.setSource(provider.id, { key: typed });
      onUpdated(r.provider);
      setDraft("");
      setShowKey(false);
      setResult(null);
      say({ kind: "ok", msg: "Clé enregistrée côté serveur — jamais renvoyée au navigateur." });
    } catch (e) {
      say({ kind: "error", msg: apiErrorMessage(e) });
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (enabled: boolean) => {
    if (toggling) return;
    setToggling(true);
    const optimistic: ContentSource = {
      ...provider,
      enabled,
      ready: enabled && (provider.key_configured || !provider.key_required),
    };
    onUpdated(optimistic);
    try {
      const r = await api.setSource(provider.id, { enabled });
      onUpdated(r.provider);
    } catch (e) {
      onUpdated(provider);
      say({ kind: "error", msg: apiErrorMessage(e) });
    } finally {
      setToggling(false);
    }
  };

  const askClear = () => {
    if (clearing) return;
    if (!confirmClear) {
      setConfirmClear(true);
      window.clearTimeout(clearTimer.current);
      clearTimer.current = window.setTimeout(() => setConfirmClear(false), 3500);
      return;
    }
    window.clearTimeout(clearTimer.current);
    setConfirmClear(false);
    void doClear();
  };

  const doClear = async () => {
    setClearing(true);
    try {
      const r = await api.setSource(provider.id, { clear_key: true });
      onUpdated(r.provider);
      setResult(null);
      say({ kind: "ok", msg: "Clé effacée du serveur." });
    } catch (e) {
      say({ kind: "error", msg: apiErrorMessage(e) });
    } finally {
      setClearing(false);
    }
  };

  const test = async () => {
    if (testing) return;
    setTesting(true);
    setResult(null);
    try {
      setResult(await api.testSource(provider.id));
    } catch (e) {
      setResult({ ok: false, message: apiErrorMessage(e), latency_ms: 0 });
    } finally {
      setTesting(false);
    }
  };

  const testDisabled = testing || (provider.key_required && !provider.key_configured);

  return (
    <article
      className="sources-card panel group relative flex flex-col gap-2.5 overflow-hidden p-3.5 transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5"
      style={{
        "--src": style.accent,
        "--src-soft": `${style.accent}24`,
        "--src-line": `${style.accent}59`,
        animationDelay: `${Math.min(index, 8) * 55}ms`,
      } as React.CSSProperties}
      aria-label={`Source ${provider.label}`}
    >
      <span
        aria-hidden
        className="absolute inset-x-0 top-0 h-[2px]"
        style={{ background: `linear-gradient(90deg, transparent, ${style.accent}, transparent)` }}
      />
      <div className="flex items-start gap-2.5">
        <span
          className="grid h-10 w-10 shrink-0 place-items-center rounded-lg transition-shadow duration-200"
          style={{ background: "var(--src-soft)", color: style.accent, boxShadow: `inset 0 0 0 1px ${style.accent}40` }}
        >
          <Icon size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h2 className="truncate text-sm font-semibold tracking-tight">{provider.label}</h2>
            {statusBadge(provider)}
          </div>
          <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted-foreground">{provider.tagline}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {provider.kinds.map((kind) => {
          const meta = KIND_META[kind];
          if (!meta) return null;
          return (
            <span
              key={kind}
              className="inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[10px]"
              style={{ borderColor: `${meta.color}55`, color: meta.color }}
            >
              <span className="h-1 w-1 rounded-full" style={{ background: meta.color }} />
              {meta.label}
            </span>
          );
        })}
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="field-label inline-flex items-center gap-1">
            <KeyRound size={11} /> {provider.key_label}
          </span>
          {provider.key_configured && (
            <span className="font-mono text-[10px] text-muted-foreground" title="Indice de la clé enregistrée">
              {provider.key_hint}
            </span>
          )}
        </div>
        <div className="relative">
          <input
            type={showKey ? "text" : "password"}
            className="input-base pr-8 font-mono text-xs"
            value={draft}
            maxLength={200}
            autoComplete="off"
            spellCheck={false}
            placeholder={provider.key_configured ? "Nouvelle clé (vide = conserver l'actuelle)" : "Collez votre clé ici"}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void saveKey(); }}
            aria-label={`Clé API ${provider.label}`}
          />
          <button
            type="button"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
            onClick={() => setShowKey((v) => !v)}
            aria-label={showKey ? "Masquer la clé saisie" : "Afficher la clé saisie"}
            title={showKey ? "Masquer" : "Afficher"}
          >
            {showKey ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Button size="sm" onClick={() => void saveKey()} disabled={!draft.trim() || saving}>
          {saving ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={12} />}
          Enregistrer
        </Button>
        <Button size="sm" variant="outline" onClick={() => void test()} disabled={testDisabled}
          title={testDisabled && provider.key_required && !provider.key_configured ? "Enregistrez d'abord une clé" : "Tester la connexion depuis le serveur"}>
          {testing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
          Tester
        </Button>
        {provider.key_configured && (
          <Button size="sm" variant="ghost" className={cn("text-destructive hover:text-destructive", confirmClear && "bg-destructive/15")}
            onClick={askClear} disabled={clearing}>
            {clearing ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
            {confirmClear ? "Confirmer l'effacement" : "Effacer"}
          </Button>
        )}
        <label className="ml-auto inline-flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground">
          <Switch checked={provider.enabled} disabled={toggling} onCheckedChange={(v) => void toggle(v)}
            aria-label={`Activer ${provider.label} pour la récupération`} />
          Active
        </label>
      </div>

      {flash && (
        <p className={cn("sources-result text-[11px]", flash.kind === "ok" ? "text-success" : "text-destructive")} role="status">
          {flash.msg}
        </p>
      )}

      {result && (
        <div
          className={cn(
            "sources-result rounded-md border p-2 text-[11px]",
            result.ok ? "border-success/40 bg-success/10" : "border-destructive/40 bg-destructive/10",
          )}
          role="status"
        >
          <div className="flex items-start gap-1.5">
            {result.ok
              ? <CheckCircle2 size={13} className="mt-px shrink-0 text-success" />
              : <XCircle size={13} className="mt-px shrink-0 text-destructive" />}
            <div className="min-w-0">
              <p className={result.ok ? "text-success" : "text-destructive"}>
                {result.message}{result.latency_ms > 0 ? ` · ${result.latency_ms} ms` : ""}
              </p>
              {result.ok && result.sample && (
                <p className="mt-0.5 break-words text-muted-foreground">Aperçu : « {result.sample} »</p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-3 border-t border-border/60 pt-2 text-[11px]">
        {provider.signup_url && (
          <a href={provider.signup_url} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-primary hover:underline">
            Obtenir une clé <ExternalLink size={10} />
          </a>
        )}
        {provider.docs_url && (
          <a href={provider.docs_url} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground hover:underline">
            Documentation <ExternalLink size={10} />
          </a>
        )}
        <span className="ml-auto inline-flex items-center gap-1 text-muted-foreground/80" title="La clé reste sur le serveur">
          <ShieldCheck size={11} /> serveur uniquement
        </span>
      </div>
    </article>
  );
}

export default function SourcesPage() {
  const [providers, setProviders] = React.useState<ContentSource[]>([]);
  const [note, setNote] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [kind, setKind] = React.useState<KindFilter>("all");
  const [status, setStatus] = React.useState<StatusFilter>("all");

  const load = React.useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const r = await api.getSources();
      setProviders(r.providers);
      setNote(r.note);
    } catch (e) {
      setLoadError(apiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { void load(); }, [load]);

  const onUpdated = React.useCallback((next: ContentSource) => {
    setProviders((current) => current.map((p) => (p.id === next.id ? next : p)));
  }, []);

  const configured = providers.filter((p) => p.key_configured).length;
  const ready = providers.filter((p) => p.ready).length;

  const visible = providers.filter((p) => {
    if (kind !== "all" && !p.kinds.includes(kind)) return false;
    if (status === "ready" && !p.ready) return false;
    if (status === "todo" && p.ready) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const kinds = p.kinds.map((k) => KIND_META[k]?.label.toLowerCase() ?? k).join(" ");
    return `${p.label} ${p.tagline} ${p.id} ${kinds}`.toLowerCase().includes(q);
  });

  const resetFilters = () => { setQuery(""); setKind("all"); setStatus("all"); };

  return (
    <div className="flex-1 space-y-3 overflow-auto p-4 md:p-6">
      <header className="relative overflow-hidden rounded-lg border border-border bg-card">
        <div className="sources-aurora pointer-events-none absolute inset-0" aria-hidden />
        <div className="relative flex flex-wrap items-start justify-between gap-4 p-4 md:p-5">
          <div className="min-w-0 max-w-xl">
            <div className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-md bg-primary/15 text-primary">
                <Telescope size={16} />
              </span>
              <h1 className="text-xl font-semibold tracking-tight md:text-2xl">Banques de contenu</h1>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground md:text-sm">
              Préparez le terrain de la récupération : enregistrez vos clés API pour puiser vidéos,
              photos, sons et musiques libres — Pexels, NASA, Pixabay, Unsplash, Freesound, Jamendo,
              Internet Archive. Chaque clé est testée en conditions réelles, puis activée pour la suite.
            </p>
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary">
              <KeyRound size={11} /> Étape 1 — les accès. La recherche et l'import se brancheront sur ces clés.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              { value: providers.length, label: "Sources", color: "text-foreground" },
              { value: configured, label: "Clés", color: "text-primary" },
              { value: ready, label: "Prêtes", color: "text-success" },
            ].map((stat) => (
              <div key={stat.label} className="rounded-md border border-border/80 bg-background/70 px-3 py-2 text-center backdrop-blur-sm">
                <div className={cn("text-lg font-semibold tabular-nums", stat.color)}>{stat.value}</div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </header>

      <div className="panel flex flex-wrap items-center gap-2 p-2.5">
        <div className="relative min-w-0 max-w-full">
          <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            className="input-base w-52 max-w-full pl-7 text-xs"
            placeholder="Rechercher une source…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Rechercher une source"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Filtrer par type de contenu">
          {KIND_FILTERS.map((k) => {
            const meta = k === "all" ? null : KIND_META[k];
            const count = k === "all" ? providers.length : providers.filter((p) => p.kinds.includes(k)).length;
            const active = kind === k;
            return (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                  active ? "border-primary/50 bg-accent text-foreground" : "border-border text-muted-foreground hover:text-foreground",
                )}
                aria-pressed={active}
              >
                {meta && <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />}
                {meta ? meta.label : "Toutes"}
                <span className="tabular-nums opacity-60">{count}</span>
              </button>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-1" role="group" aria-label="Filtrer par état">
          {([
            ["all", "Toutes"],
            ["ready", "Prêtes"],
            ["todo", "À configurer"],
          ] as Array<[StatusFilter, string]>).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setStatus(value)}
              className={cn(
                "rounded-md px-2 py-1 text-[11px] transition-colors",
                status === value ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
              aria-pressed={status === value}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="panel flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
          <Loader2 size={16} className="animate-spin" /> Chargement du catalogue…
        </div>
      )}

      {!loading && loadError && (
        <div className="panel space-y-2 border-destructive/40 p-4 text-sm">
          <p className="flex items-center gap-2 text-destructive"><XCircle size={15} /> {loadError}</p>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            <RefreshCw size={12} /> Réessayer
          </Button>
        </div>
      )}

      {!loading && !loadError && visible.length === 0 && (
        <div className="panel flex flex-col items-center gap-2 p-10 text-center">
          <SearchX size={22} className="text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Aucune source ne correspond à ces filtres.</p>
          <Button size="sm" variant="outline" onClick={resetFilters}>Réinitialiser les filtres</Button>
        </div>
      )}

      {!loading && !loadError && visible.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {visible.map((p, index) => (
            <SourceCard key={p.id} provider={p} index={index} onUpdated={onUpdated} />
          ))}
        </div>
      )}

      <footer className="panel flex items-start gap-2.5 p-3.5 text-[11px] leading-relaxed text-muted-foreground">
        <ShieldCheck size={15} className="mt-0.5 shrink-0 text-success" />
        <div className="space-y-1">
          <p>
            <span className="font-medium text-foreground">Vos clés restent sur cette machine.</span>{" "}
            Stockées côté serveur (<span className="font-mono">server/sources.json</span>, hors dépôt),
            jamais renvoyées au navigateur ni journalisées — seul l'indice des 4 derniers caractères est affiché.
            Le test interroge l'API officielle du fournisseur depuis le serveur, avec votre clé.
          </p>
          {note && <p>{note}</p>}
        </div>
      </footer>
    </div>
  );
}