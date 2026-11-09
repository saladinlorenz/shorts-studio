import { staticFile } from "remotion";

/**
 * URL d'un media local pour les deux contextes de rendu.
 *
 * Le serveur du Player (web/dist) sert sa racine sur `/` ; le navigateur de
 * rendu Remotion sert le bundle, ou le contenu de web/public se retrouve sous
 * `/public`. staticFile() applique ce préfixe seulement quand il connait la
 * base statique du bundle, donc la meme chaine fonctionne a l'aperçu et a
 * l'export, sans chemin Windows et sans re-embarquement en data-URI.
 */
export function renderMediaUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  if (value.startsWith("data:") || value.startsWith("http://") || value.startsWith("https://")) {
    return value;
  }
  if (value.startsWith("/media-cache/")) return staticFile(value);
  if (value.startsWith("media://")) return `/api/media/${value.slice("media://".length)}`;
  return null; // chemin herite : non servable par le web, la validation le signale
}
