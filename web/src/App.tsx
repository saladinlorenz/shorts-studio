import React from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import AssistantDock from "./components/AssistantDock";
import CommandPalette from "./components/CommandPalette";
import { AssistantProvider, useAssistant } from "./lib/assistant";
import { NAV_GROUPS } from "./lib/navigation";
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

/**
 * Coquille du studio.
 *
 * Trois surfaces, une seule de chaque : la barre latérale (groupée par
 * intention — piloter, automatiser, alimenter, régler), le tiroir d'assistant
 * qui suit la page courante, et la palette de commandes. Les raccourcis globaux
 * sont déclarés ici pour rester disponibles quelle que soit la page ouverte.
 */

function Sidebar({ onOpenPalette }: { onOpenPalette: () => void }) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card/60">
      <div className="border-b border-border px-4 py-4">
        <div className="text-sm font-semibold tracking-tight">Studio Vidéo</div>
        <div className="text-[11px] text-muted-foreground">youtube_clipper · local</div>
      </div>

      <nav className="flex flex-1 flex-col gap-3 overflow-y-auto p-2" aria-label="Navigation du studio">
        {NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <div className="px-2.5 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground/70">
              {group.label}
            </div>
            <div className="flex flex-col gap-0.5">
              {group.items.map(({ to, label, icon: Icon, description }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    [
                      "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                      isActive
                        ? "bg-accent text-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    ].join(" ")
                  }
                  title={description}
                >
                  <Icon size={15} className="shrink-0" />
                  <span className="flex-1">{label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-1.5 border-t border-border px-3 py-3">
        <button
          className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
          onClick={onOpenPalette}
          title="Rechercher une page, un projet ou un modèle"
        >
          <Search size={13} className="shrink-0" />
          <span className="flex-1">Rechercher</span>
          <kbd className="text-[10px]">Ctrl+K</kbd>
        </button>
        <div className="text-[11px] leading-snug text-muted-foreground">
          Interface web locale — 127.0.0.1
        </div>
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
          <Route path="/" element={<CockpitPage />} />
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
          <Route path="*" element={<CockpitPage />} />
        </Routes>
      </main>
      <AssistantDock />
      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} />
    </div>
  );
}

/**
 * Point d'entrée : tout le studio est sous le même fournisseur d'assistant, donc
 * la conversation et le contexte publié survivent aux changements de page.
 */
export default function App() {
  return (
    <AssistantProvider>
      <Shell />
    </AssistantProvider>
  );
}
