import React from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import AssistantDock from "./components/AssistantDock";
import CommandPalette from "./components/CommandPalette";
import { AssistantProvider, useAssistant } from "./lib/assistant";
import { ProjectProvider } from "./lib/project";
import { NAV_GROUPS } from "./lib/navigation";
import StudioPage from "./pages/StudioPage";
import CockpitPage from "./pages/CockpitPage";
import DesignPage from "./pages/DesignPage";
import LibraryPage from "./pages/LibraryPage";
import ProductionPage from "./pages/ProductionPage";
import LivraisonPage from "./pages/LivraisonPage";
import MomentsPage from "./pages/MomentsPage";
import ShortVideosPage from "./pages/ShortVideosPage";
import ClipsPage from "./pages/ClipsPage";
import PodcastPage from "./pages/PodcastPage";
import ProjectsPage from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";
import TtsPage from "./pages/TtsPage";

/**
 * Coquille du studio.
 *
 * L'accueil est la conversation + l'aperçu vidéo ; les pages avancées restent
 * accessibles par la barre latérale (repliable en rail d'icônes) et la palette
 * de commandes. Le tiroir d'assistant suit la page courante et reste ouvert sur
 * l'accueil. Les raccourcis globaux sont déclarés ici pour rester disponibles
 * quelle que soit la page ouverte.
 */

const COLLAPSE_KEY = "studio.sidebar.collapsed";

function Sidebar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const [collapsed, setCollapsed] = React.useState(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) !== "0";
    } catch {
      return true;
    }
  });
  const toggle = () => {
    setCollapsed((value) => {
      const next = !value;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* stockage indisponible */
      }
      return next;
    });
  };

  return (
    <aside
      className={
        "flex shrink-0 flex-col border-r border-border bg-card/60 transition-[width] " +
        (collapsed ? "w-14" : "w-56")
      }
    >
      <div className={"flex items-center border-b border-border py-3 " + (collapsed ? "justify-center px-2" : "gap-2 px-3")}>
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold tracking-tight">Studio Vidéo</div>
            <div className="truncate text-[11px] text-muted-foreground">youtube_clipper · local</div>
          </div>
        )}
        <button
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/60 hover:text-foreground"
          onClick={toggle}
          title={collapsed ? "Déplier le menu" : "Replier le menu"}
          aria-label={collapsed ? "Déplier le menu" : "Replier le menu"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className="flex flex-1 flex-col gap-2 overflow-y-auto p-2" aria-label="Navigation du studio">
        {NAV_GROUPS.map((group) => (
          <div key={group.id}>
            {!collapsed && (
              <div className="px-2.5 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground/70">
                {group.label}
              </div>
            )}
            <div className="flex flex-col gap-0.5">
              {group.items.map(({ to, label, icon: Icon, description }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    [
                      "flex items-center rounded-md py-1.5 text-sm transition-colors",
                      collapsed ? "justify-center px-2" : "gap-2 px-2.5",
                      isActive
                        ? "bg-accent text-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    ].join(" ")
                  }
                  title={`${label} — ${description}`}
                  aria-label={label}
                >
                  <Icon size={16} className="shrink-0" />
                  {!collapsed && <span className="flex-1 truncate">{label}</span>}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-2">
        <button
          className={
            "flex items-center rounded-md border border-border py-1.5 text-xs text-muted-foreground hover:text-foreground " +
            (collapsed ? "justify-center px-2" : "gap-2 px-2")
          }
          onClick={onOpenPalette}
          title="Rechercher une page, un projet ou un modèle (Ctrl+K)"
          aria-label="Rechercher"
        >
          <Search size={14} className="shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1 text-left">Rechercher</span>
              <kbd className="text-[10px]">Ctrl+K</kbd>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

function Shell() {
  const navigate = useNavigate();
  const { toggle: toggleAssistant } = useAssistant();
  const [paletteOpen, setPaletteOpen] = React.useState(false);

  React.useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
      } else if (key === "i") {
        event.preventDefault();
        toggleAssistant();
      } else if (key === "/") {
        event.preventDefault();
        navigate("/");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleAssistant, navigate]);

  return (
    <div className="flex h-full">
      <Sidebar onOpenPalette={() => setPaletteOpen(true)} />
      <main className="flex min-w-0 flex-1 flex-col">
        <Routes>
          <Route path="/" element={<StudioPage />} />
          <Route path="/cockpit" element={<CockpitPage />} />
          <Route path="/design" element={<DesignPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/production" element={<ProductionPage />} />
          <Route path="/delivery" element={<LivraisonPage />} />
          <Route path="/moments" element={<MomentsPage />} />
          <Route path="/clips" element={<ClipsPage />} />
          <Route path="/podcast" element={<PodcastPage />} />
          <Route path="/short-videos" element={<ShortVideosPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/tts" element={<TtsPage />} />
          <Route path="*" element={<StudioPage />} />
        </Routes>
      </main>
      <AssistantDock />
      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} />
    </div>
  );
}

/**
 * Point d'entrée : le projet actif et la conversation sont partagés par tout le
 * studio, donc une modification demandée dans le chat survit aux changements de
 * page et reste visible dans l'aperçu comme dans l'éditeur.
 */
export default function App() {
  return (
    <ProjectProvider>
      <AssistantProvider>
        <Shell />
      </AssistantProvider>
    </ProjectProvider>
  );
}