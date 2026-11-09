import React from "react";
import type { TtsVoice } from "../api/client";

/**
 * Sélecteur de voix pour un catalogue complet.
 *
 * Le catalogue Piper + Kokoro compte des centaines de voix : une liste plate
 * serait illisible. On filtre à la saisie (langue, nom, locale, moteur) et on
 * regroupe par langue, les voix déjà téléchargées en tête pour aller vite.
 * Ce composant n'affiche rien de métier : il ne fait que trier et filtrer.
 */
export function VoiceSelect({
  voices,
  value,
  onChange,
  disabled = false,
}: {
  voices: TtsVoice[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const [filter, setFilter] = React.useState("");
  const needle = filter.trim().toLowerCase();

  const groups = React.useMemo(() => {
    const match = (v: TtsVoice) =>
      !needle ||
      v.label.toLowerCase().includes(needle) ||
      (v.language_name || "").toLowerCase().includes(needle) ||
      v.language.toLowerCase().includes(needle) ||
      (v.locale || "").toLowerCase().includes(needle) ||
      (v.quality || "").toLowerCase().includes(needle) ||
      v.engine.includes(needle);

    const byLanguage = new Map<string, TtsVoice[]>();
    for (const voice of voices) {
      if (!match(voice)) continue;
      const key = voice.language_name || voice.language;
      const bucket = byLanguage.get(key);
      if (bucket) bucket.push(voice);
      else byLanguage.set(key, [voice]);
    }
    for (const bucket of byLanguage.values()) {
      bucket.sort(
        (a, b) =>
          Number(b.downloaded) - Number(a.downloaded) ||
          a.label.localeCompare(b.label, "fr"),
      );
    }
    return [...byLanguage.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], "fr"))
      .map(([lang, list]) => ({ lang, list }));
  }, [voices, needle]);

  const shown = groups.reduce((total, group) => total + group.list.length, 0);
  const languages = new Set(voices.map((v) => v.language)).size;
  // La voix choisie peut être masquée par le filtre : on la réaffiche en tête
  // pour que le <select> ne retombe jamais silencieusement sur une autre voix.
  const selected = voices.find((v) => v.id === value) ?? null;
  const selectedVisible = groups.some((g) => g.list.some((v) => v.id === value));

  return (
    <div className="flex flex-col gap-1.5">
      <input
        className="input-base"
        value={filter}
        placeholder="Filtrer : arabe, anglais, kareem, medium…"
        onChange={(e) => setFilter(e.target.value)}
        disabled={disabled}
        aria-label="Filtrer les voix"
      />
      <select
        className="input-base"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        {selected && !selectedVisible && (
          <option value={selected.id}>{selected.label} (masquée par le filtre)</option>
        )}
        {groups.map((group) => (
          <optgroup key={group.lang} label={`${group.lang} — ${group.list.length} voix`}>
            {group.list.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.label}
                {voice.downloaded ? "" : ` · à télécharger (~${voice.approx_mb} Mo)`}
              </option>
            ))}
          </optgroup>
        ))}
        {shown === 0 && <option value="">Aucune voix ne correspond au filtre</option>}
      </select>
      <span className="text-[11px] text-muted-foreground">
        {shown} voix affichée{shown > 1 ? "s" : ""} sur {voices.length} · {languages} langues
      </span>
    </div>
  );
}
