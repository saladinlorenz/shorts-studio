import React from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Clock,
  Gauge,
  Layers,
  Library,
  Loader2,
  PenTool,
  ShieldAlert,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import SetupAssistant from "../components/SetupAssistant";
import { api, apiErrorMessage, type AgentStatus, type Batch, type LibraryModel, type EffectsManifest } from "../api/client";
import { useAssistant } from "../lib/assistant";

/**
 * Cockpit : la page d'accueil du studio, construite autour de l'assistant.
 *
 * Tout ce qui s'affiche ici vient d'un endpoint réel ; une carte dont la donnée
 * manque affiche son erreur au lieu d'inventer un chiffre. Les exemples de
 * demande remplissent la question, ils ne lancent rien : c'est le clic sur
 * « Demander » qui envoie, et l'assistant répond par une proposition qu'on
 * applique soi-même dans Design.
 */

const EXAMPLES = [
  "Mets l'accent en bleu pétrole sur toute la vidéo et rallonge la dernière scène de 2 s.",
  "Ajoute un effet de texte mot par mot sur la scène 1 et du glitch léger sur la scène 2.",
  "Quels effets du catalogue tiennent sur un calque de texte, et quels sont leurs réglages ?",
  "Prépare un plan de lot pour mon CSV : colonne Titre vers l'accroche, Citation vers la scène 2.",
];

const BATCH_STATUS: Record<string, string> = {
  ready: "prêt",
  running: "en cours",
  paused: "en pause",
  done: "terminé",
  cancelled: "annulé",
};

function Card({
  title,
  icon: Icon,
  action,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel flex flex-col p-4">
      <header className="mb-2.5 flex items-center gap-2">
        <Icon size={14} className="text-muted-foreground" />
        <h2 className="text-sm font-medium">{title}</h2>
        <div className="ml-auto flex items-center gap-1.5">{action}</div>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

function CardError({ msg }: { msg: string }) {
  return <p className="text-[11px] leading-snug text-destructive">{msg}</p>;
}

function relativeTime(epochSeconds: number): string {
  const days = Math.floor((Date.now() / 1000 - epochSeconds) / 86400);
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "hier";
  if (days < 30) return `il y a ${days} j`;
  return new Date(epochSeconds * 1000).toLocaleDateString("fr-FR");
}

export default function CockpitPage() {
  const navigate = useNavigate();
  const { ask, open, data } = useAssistant();
  const [text, setText] = React.useState("");
  const [status, setStatus] = React.useState<AgentStatus | null>(null);
  const [statusError, setStatusError] = React.useState("");
  const [projects, setProjects] = React.useState<{ name: string; version: number | null; modified: number }[]>([]);
  const [models, setModels] = React.useState<LibraryModel[]>([]);
  const [batches, setBatches] = React.useState<Batch[]>([]);
  const [effects, setEffects] = React.useState<EffectsManifest | null>(null);
  const [checks, setChecks] = React.useState<{ missingFonts: number; folders: number } | null>(null);
  const [checksError, setChecksError] = React.useState("");

  React.useEffect(() => {
    let stopped = false;
    const guard = <T,>(p: Promise<T>, set: (v: T) => void, fail: (msg: string) => void) =>
      p
        .then((v) => {
          if (!stopped) set(v);
        })
        .catch((e) => {
          if (!stopped) fail(apiErrorMessage(e));
        });

    void guard(api.agentStatus(), setStatus, setStatusError);
    void guard(
      api.listProjects(),
      (r) => setProjects([...r].sort((a, b) => b.modified - a.modified)),
      () => {},
    );
    void guard(
      api.libraryModels(),
      (r) => setModels([...r.models].sort((a, b) => b.modified - a.modified)),
      () => {},
    );
    void guard(api.batchList(), (r) => setBatches(r.batches), () => {});
    void guard(api.studioEffects(), setEffects, () => {});
    void guard(
      Promise.all([api.studioFonts(), api.folders()]).then(([fonts, folders]) => ({
        missingFonts: fonts.missing_files.length,
        folders: folders.folders.length,
      })),
      setChecks,
      setChecksError,
    );
    return () => {
      stopped = true;
    };
  }, []);

  const refreshStatus = React.useCallback(() => {
    api
      .agentStatus()
      .then((s) => {
        setStatus(s);
        setStatusError("");
      })
      .catch((e) => setStatusError(apiErrorMessage(e)));
  }, []);

  const notReady = status !== null && !status.ready;

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || notReady) return;
    ask(trimmed);
    setText("");
  };

  const running = batches.filter((b) => b.is_running || b.status === "running" || b.status === "paused");
  const recent = projects.slice(0, 5);
  const contextLabel =
    data.mode === "production"
      ? "Contexte lu par l'assistant : Production"
      : data.project
        ? `Contexte lu par l'assistant : ${data.projectName || "projet"} (${data.source || "Design"})`
        : "Aucun projet ouvert : l'assistant répond sur la documentation et les réglages.";

  return (
    <div className="flex-1 overflow-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-6">
        <div className="flex items-center gap-2">
          <Gauge size={17} className="text-primary" />
          <h1 className="text-lg font-semibold tracking-tight">Cockpit</h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          L'assistant est le point d'entrée du studio : vous décrivez ce que vous voulez, il lit le
          projet affiché et propose des opérations bornées. Vous décidez si la proposition s'applique,
          et un rendu ne se lance que de votre clic.
        </p>

        {/* ------------------------- configuration guidée ------------------------- */}
        {notReady && <SetupAssistant status={status} onReady={refreshStatus} />}

        {/* -------------------------------- demande -------------------------------- */}
        <section className="panel mt-4 p-4">
          <div className="mb-2 flex items-center gap-2">
            <Sparkles size={14} className="text-primary" />
            <h2 className="text-sm font-medium">Demander à l'assistant</h2>
            {status?.ready ? (
              <Badge variant="success" className="ml-auto">
                {status.provider === "local" ? "serveur local" : status.provider} · {status.model}
              </Badge>
            ) : (
              <Badge variant="warning" className="ml-auto">
                Non configuré
              </Badge>
            )}
          </div>
          <textarea
            className="input-base min-h-[92px] w-full resize-none text-sm"
            placeholder="Ex. : ajoute un effet de texte mot par mot sur la scène 1, puis raccourcis la scène 2 à 4 s."
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
            }}
            aria-label="Demande à l'assistant"
          />
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <button
              className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              onClick={submit}
              disabled={!text.trim() || notReady}
            >
              <ArrowRight size={13} />
              Demander
            </button>
            <button
              className="h-8 rounded-md border border-border px-3 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => navigate("/design")}
            >
              Ouvrir un projet dans Design
            </button>
            {notReady && (
              <span className="text-[11px] text-warning">
                Configurez l'assistant ci-dessus pour envoyer une demande.
              </span>
            )}
            {!open && (
              <span className="text-[11px] text-muted-foreground">
                Ctrl+I rouvre le tiroir de l'assistant, Ctrl+K la palette de commandes.
              </span>
            )}
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                className="rounded-full border border-border/60 px-2.5 py-1 text-left text-[11px] text-muted-foreground hover:border-primary/50 hover:text-foreground"
                onClick={() => setText(example)}
              >
                {example}
              </button>
            ))}
          </div>
          <p className="mt-2.5 text-[11px] text-muted-foreground">{contextLabel}</p>
          {statusError && <CardError msg={statusError} />}
        </section>

        {/* --------------------------------- cartes --------------------------------- */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card
            title="Effets disponibles"
            icon={WandSparkles}
            action={
              effects && (
                <span className="text-xs tabular-nums text-muted-foreground">
                  {effects.effects.length} effets
                </span>
              )
            }
          >
            {effects ? (
              <>
                <p className="text-[11px] leading-snug text-muted-foreground">
                  {effects.effects.length} effets applicables par l'assistant et par l'Inspecteur,{" "}
                  {effects.max_per_target} au maximum sur un même calque ou une même scène. Une demande
                  d'effet passe par le catalogue : un nom hors catalogue est refusé, pas deviné.
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {effects.categories.map((category) => (
                    <button
                      key={category.id}
                      className="rounded-full border border-border/60 px-2.5 py-0.5 text-[11px] text-muted-foreground hover:border-primary/50 hover:text-foreground"
                      onClick={() => ask(`Quels effets de la catégorie « ${category.label} » existent, et quels sont leurs réglages ?`)}
                      title="Demander le détail à l'assistant"
                    >
                      {category.label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-[11px] text-muted-foreground">Chargement du catalogue…</p>
            )}
          </Card>

          <Card
            title="File de production"
            icon={Layers}
            action={
              <button
                className="text-[11px] text-muted-foreground hover:text-foreground"
                onClick={() => navigate("/production")}
              >
                Production
              </button>
            }
          >
            {running.length === 0 && batches.length === 0 ? (
              <p className="text-[11px] leading-snug text-muted-foreground">
                Aucun lot enregistré. Un lot se prépare depuis un CSV importé : l'assistant propose le
                mapping, le planificateur recalcule le plan, et le lancement reste votre clic.
              </p>
            ) : running.length === 0 ? (
              <p className="text-[11px] leading-snug text-muted-foreground">
                {batches.length} lot(s) dans la file persistante, aucun en cours. Dernier :{" "}
                <span className="text-foreground">{batches[0].name}</span> —{" "}
                {BATCH_STATUS[batches[0].status] ?? batches[0].status} ·{" "}
                {batches[0].counters.rendered}/{batches[0].counters.total} rendu(s)
                {batches[0].counters.failed > 0
                  ? ` · ${batches[0].counters.failed} échec(s)`
                  : ""}
                {batches[0].finished_at ? ` · ${new Date(batches[0].finished_at).toLocaleString("fr-FR")}` : ""}
              </p>
            ) : (
              <ul className="space-y-2.5">
                {running.slice(0, 3).map((batch) => (
                  <li key={batch.id}>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="truncate font-medium">{batch.name}</span>
                      <Badge variant={batch.status === "running" ? "default" : "outline"}>
                        {BATCH_STATUS[batch.status] ?? batch.status}
                      </Badge>
                      <span className="ml-auto tabular-nums text-muted-foreground">
                        {batch.counters.rendered}/{batch.counters.total}
                      </span>
                    </div>
                    <Progress value={batch.counters.progress} className="mt-1.5 h-1.5" />
                    {batch.message && (
                      <p className="mt-1 truncate text-[11px] text-muted-foreground">{batch.message}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Derniers projets"
            icon={Clock}
            action={
              <button
                className="text-[11px] text-muted-foreground hover:text-foreground"
                onClick={() => navigate("/projects")}
              >
                Tous
              </button>
            }
          >
            {recent.length === 0 ? (
              <p className="text-[11px] leading-snug text-muted-foreground">
                Aucun projet enregistré. Ouvrez un modèle de la bibliothèque dans Design, puis enregistrez
                pour repartir de là.
              </p>
            ) : (
              <ul className="space-y-1">
                {recent.map((item) => (
                  <li key={item.name}>
                    <button
                      className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs hover:bg-accent/60"
                      onClick={() => navigate(`/design?project=${encodeURIComponent(item.name)}`)}
                      title="Ouvrir dans Design"
                    >
                      <PenTool size={12} className="shrink-0 text-muted-foreground" />
                      <span className="truncate">{item.name}</span>
                      <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">
                        {relativeTime(item.modified)}
                      </span>
                      {item.version !== 2 && (
                        <Badge variant={item.version === 1 ? "warning" : "outline"}>
                          v{item.version ?? "?"}
                        </Badge>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Modèles de la bibliothèque"
            icon={Library}
            action={
              <button
                className="text-[11px] text-muted-foreground hover:text-foreground"
                onClick={() => navigate("/library")}
              >
                Bibliothèque
              </button>
            }
          >
            {models.length === 0 ? (
              <p className="text-[11px] leading-snug text-muted-foreground">
                Aucun modèle. Depuis Design, « Enregistrer dans la bibliothèque » transforme le projet
                affiché en point de départ réutilisable.
              </p>
            ) : (
              <>
                <p className="text-[11px] text-muted-foreground">{models.length} modèle(s) prêt(s) à réutiliser.</p>
                <ul className="mt-1.5 space-y-1">
                  {models.slice(0, 4).map((model) => (
                    <li key={model.id}>
                      <button
                        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs hover:bg-accent/60"
                        onClick={() => navigate(`/design?model=${encodeURIComponent(model.id)}`)}
                        title="Ouvrir dans Design"
                      >
                        <span className="truncate">{model.label}</span>
                        <span className="ml-auto shrink-0 tabular-nums text-[11px] text-muted-foreground">
                          {model.scenes} scène(s) · {model.duration.toFixed(1)} s
                        </span>
                        {model.unreadable && <Badge variant="destructive">illisible</Badge>}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>

          <Card
            title="Points de contrôle"
            icon={ShieldAlert}
            action={
              <button
                className="text-[11px] text-muted-foreground hover:text-foreground"
                onClick={() => navigate("/settings")}
              >
                Réglages
              </button>
            }
          >
            {checksError ? (
              <CardError msg={checksError} />
            ) : !checks ? (
              <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <Loader2 size={12} className="animate-spin" /> Vérification des polices et des dossiers…
              </p>
            ) : (
              <ul className="space-y-1.5 text-[11px] leading-snug">
                <li className="flex items-start gap-2">
                  <Badge variant={checks.missingFonts === 0 ? "success" : "warning"}>
                    {checks.missingFonts === 0 ? "ok" : `${checks.missingFonts} manquant(s)`}
                  </Badge>
                  <span className="text-muted-foreground">
                    Polices du catalogue présentes sur la machine — sans elles l'aperçu et le rendu
                    tombent en police de secours.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <Badge variant={checks.folders > 0 ? "success" : "outline"}>
                    {checks.folders} dossier(s)
                  </Badge>
                  <span className="text-muted-foreground">
                    Dossiers de médias connectés ; un média n'entre dans un projet que par sa référence
                    locale.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <Badge variant={status?.ready ? "success" : "warning"}>
                    {status?.ready ? "prêt" : "à régler"}
                  </Badge>
                  <span className="text-muted-foreground">
                    {status?.ready
                      ? `Assistant sur ${status.provider === "local" ? "serveur local" : status.provider}, modèle ${status.model}.`
                      : status?.reason || "Assistant non configuré : Réglages → Assistant IA."}
                  </span>
                </li>
                {status?.knowledge && (
                  <li className="flex items-start gap-2">
                    <Badge variant={status.knowledge.built ? "success" : "outline"}>
                      {status.knowledge.docs} doc(s)
                    </Badge>
                    <span className="text-muted-foreground">
                      Documentation locale indexée que l'assistant peut citer ; sans elle il reste
                      limité au projet et au catalogue.
                    </span>
                  </li>
                )}
              </ul>
            )}
          </Card>

          <Card title="Aller plus vite" icon={ArrowRight}>
            <ul className="space-y-1.5 text-[11px] leading-snug text-muted-foreground">
              <li>
                <span className="text-foreground">Ctrl+K</span> — palette : pages, projets enregistrés et
                modèles, par nom.
              </li>
              <li>
                <span className="text-foreground">Ctrl+I</span> — ouvrir ou fermer le tiroir de
                l'assistant ; il garde la conversation quand vous changez de page.
              </li>
              <li>
                <span className="text-foreground">Échap</span> — fermer le tiroir ou la palette.
              </li>
              <li>
                Dans Design, <span className="text-foreground">Ctrl+Z</span> annule une application : une
                proposition acceptée passe par l'historique, jamais par un écrasement du fichier.
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
