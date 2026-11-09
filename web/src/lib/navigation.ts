import {
  AudioLines,
  Clapperboard,
  FolderOpen,
  Gauge,
  Layers,
  Library,
  Mic,
  Package,
  PenTool,
  Settings as SettingsIcon,
  Sparkles,
  Volume2,
} from "lucide-react";
import type { ComponentType } from "react";

/**
 * Modèle de navigation du studio.
 *
 * Les pages sont regroupées par intention (créer, automatiser, alimenter,
 * régler) plutôt que par module technique : la barre latérale et la palette de
 * commandes lisent la même liste, donc aucun lien n'existe dans l'une sans
 * l'autre.
 */

export type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number | string; className?: string }>;
  /** Ce que la page fait réellement — sert d'aide-titre et de description dans la palette. */
  description: string;
};

export type NavGroup = { id: string; label: string; items: NavItem[] };

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "pilotage",
    label: "Pilotage",
    items: [
      {
        to: "/",
        label: "Cockpit",
        icon: Gauge,
        description: "Assistant, files en cours, derniers projets et points de contrôle",
      },
      {
        to: "/design",
        label: "Design",
        icon: PenTool,
        description: "Éditeur : scènes, calques, effets, aperçu Remotion, export MP4",
      },
    ],
  },
  {
    id: "creation",
    label: "Création",
    items: [
      {
        to: "/tts",
        label: "Voix off",
        icon: Volume2,
        description: "Synthèse vocale locale : texte → WAV, catalogue multilingue Piper et Kokoro",
      },
    ],
  },
  {
    id: "automatisation",
    label: "Automatisation",
    items: [
      {
        to: "/production",
        label: "Production",
        icon: Layers,
        description: "Lots par CSV, file de rendu persistante, manifeste de livraison",
      },
      {
        to: "/delivery",
        label: "Livraison",
        icon: Package,
        description: "Paquet ZIP d'un lot : vidéos, sous-titres, miniatures, métadonnées et manifeste",
      },
      {
        to: "/library",
        label: "Bibliothèque",
        icon: Library,
        description: "Modèles enregistrés, prêts à réutiliser",
      },
    ],
  },
  {
    id: "sources",
    label: "Sources",
    items: [
      {
        to: "/clips",
        label: "Clips",
        icon: Clapperboard,
        description: "Téléchargement et repérage de moments dans les vidéos",
      },
      {
        to: "/moments",
        label: "Moments forts",
        icon: AudioLines,
        description:
          "Transcription Whisper d'une source importée, moments scorés, projets générés au clic",
      },
      {
        to: "/podcast",
        label: "Podcast",
        icon: Mic,
        description: "Base des extraits de podcast, intervenants et statistiques",
      },
      {
        to: "/projects",
        label: "Projets",
        icon: FolderOpen,
        description: "Fichiers de projet enregistrés dans projects/",
      },
      {
        to: "/short-videos",
        label: "Shorts v1",
        icon: Sparkles,
        description: "Ancien format v1 : conversion explicite vers v2 dans Design",
      },
    ],
  },
  {
    id: "systeme",
    label: "Système",
    items: [
      {
        to: "/settings",
        label: "Réglages",
        icon: SettingsIcon,
        description: "Serveur LLM de l'assistant, clés, dossiers de médias, licence",
      },
    ],
  },
];

/** Routes réelles de l'application. */
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);
