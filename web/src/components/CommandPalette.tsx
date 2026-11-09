import React from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, FileText, Search, Sparkles } from "lucide-react";
import { api } from "../api/client";
import { useAssistant } from "../lib/assistant";
import { NAV_GROUPS } from "../lib/navigation";

/**
 * Palette de commandes (Ctrl+K).
 *
 * Elle ne fait que ce que le studio sait déjà faire : aller à une page, ouvrir
 * un projet enregistré, démarrer depuis un modèle de bibliothèque, ouvrir le
 * tiroir d'assistant. Aucun raccourci d'export ou de lancement de lot ici :
 * ces actions exigent le contexte d'une page et le clic de validation de
 * l'utilisateur.
 */

type Command = {
  id: string;
  label: string;
  detail: string;
  group: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  run: () => void;
};

interface Props {
  open: boolean;
  setOpen: (value: boolean) => void;
}

export default function CommandPalette({ open, setOpen }: Props) {
  const navigate = useNavigate();
  const { setOpen: setAssistantOpen } = useAssistant();
  const [query, setQuery] = React.useState("");
  const [index, setIndex] = React.useState(0);
  const [projects, setProjects] = React.useState<Array<{ name: string }>>([]);
  const [models, setModels] = React.useState<Array<{ id: string; label: string }>>([]);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!open) return;
    setQuery("");
    setIndex(0);
    // Chargement a la demande : la palette reste ouverte sur ce qui a repondu,
    // un serveur arrete ne doit pas vider la liste des pages.
    api.listProjects().then(setProjects).catch(() => setProjects([]));
    api
      .libraryModels()
      .then((res) => setModels(res.models.map((m) => ({ id: m.id, label: m.label }))))
      .catch(() => setModels([]));
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const commands = React.useMemo<Command[]>(() => {
    const go = (to: string) => () => {
      navigate(to);
      setOpen(false);
    };
    const list: Command[] = NAV_GROUPS.flatMap((group) =>
      group.items.map((item) => ({
        id: `nav:${item.to}`,
        label: item.label,
        detail: item.description,
        group: group.label,
        icon: item.icon,
        run: go(item.to),
      })),
    );
    list.push({
      id: "assistant:open",
      label: "Ouvrir l'assistant",
      detail: "Le tiroir lit la page courante — Ctrl+I",
      group: "Assistant",
      icon: Sparkles,
      run: () => {
        setAssistantOpen(true);
        setOpen(false);
      },
    });
    for (const project of projects.slice(0, 30)) {
      list.push({
        id: `project:${project.name}`,
        label: `Ouvrir le projet « ${project.name} »`,
        detail: "Dans Design, avec l'aperçu Remotion",
        group: "Projets",
        icon: FileText,
        run: () => {
          navigate(`/design?project=${encodeURIComponent(project.name)}`);
          setOpen(false);
        },
      });
    }
    for (const model of models.slice(0, 30)) {
      list.push({
        id: `model:${model.id}`,
        label: `Nouveau projet depuis « ${model.label} »`,
        detail: "Charge un modèle de la bibliothèque dans Design",
        group: "Bibliothèque",
        icon: Sparkles,
        run: () => {
          navigate(`/design?model=${encodeURIComponent(model.id)}`);
          setOpen(false);
        },
      });
    }
    return list;
  }, [navigate, setOpen, setAssistantOpen, projects, models]);

  const filtered = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) =>
      `${command.label} ${command.detail} ${command.group}`.toLowerCase().includes(needle),
    );
  }, [commands, query]);

  React.useEffect(() => {
    setIndex((current) => Math.min(current, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  if (!open) return null;

  const runAt = (position: number) => {
    const command = filtered[position];
    if (command) command.run();
  };

  let lastGroup = "";

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/60 p-4 pt-[12vh]"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Palette de commandes"
    >
      <div
        className="panel flex max-h-[70vh] w-full max-w-xl flex-col overflow-hidden"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setIndex((current) => Math.min(current + 1, filtered.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setIndex((current) => Math.max(current - 1, 0));
          } else if (event.key === "Enter") {
            event.preventDefault();
            runAt(index);
          } else if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
          }
        }}
      >
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Search size={14} className="text-muted-foreground" />
          <input
            ref={inputRef}
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            placeholder="Page, projet, modèle, assistant…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setIndex(0);
            }}
          />
          <kbd className="rounded border border-border px-1 text-[10px] text-muted-foreground">Échap</kbd>
        </div>
        <div className="min-h-0 flex-1 overflow-auto py-1">
          {filtered.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              Aucun élément ne correspond. La palette navigue et ouvre des fichiers existants : elle ne
              lance aucun rendu.
            </p>
          )}
          {filtered.map((command, position) => {
            const header = command.group !== lastGroup ? command.group : null;
            lastGroup = command.group;
            const Icon = command.icon;
            return (
              <React.Fragment key={command.id}>
                {header && (
                  <div className="px-3 pb-1 pt-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                    {header}
                  </div>
                )}
                <button
                  className={
                    "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm " +
                    (position === index ? "bg-accent text-foreground" : "hover:bg-accent/60")
                  }
                  onMouseEnter={() => setIndex(position)}
                  onClick={command.run}
                >
                  <Icon size={14} className="shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{command.label}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{command.detail}</span>
                  </span>
                  {position === index && <CornerDownLeft size={12} className="shrink-0 text-muted-foreground" />}
                </button>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}