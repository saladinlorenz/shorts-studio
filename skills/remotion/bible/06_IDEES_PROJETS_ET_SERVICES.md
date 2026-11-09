# 06 — QUOI CONSTRUIRE / VENDRE AVEC REMOTION

## Services freelance (Fiverr / Upwork)
| Service | Briques Remotion |
|---|---|
| Sous-titres animés TikTok/Reels | `@remotion/captions`, Whisper, `spring` |
| Vidéos personnalisées en masse (prénom, logo, prix) | `inputProps`, `renderMedia`, Lambda |
| Pubs produit / e-commerce depuis un flux (CSV/API) | `calculateMetadata`, `TransitionSeries`, `Img` |
| Logo reveal / intro YouTube | `spring`, `evolvePath`, particules, `noise2D` |
| Vidéos de données / rapports animés | SVG + `interpolate`, bar chart race |
| Clips podcast (audiogram) | `visualizeAudio`, captions |
| Annonces immobilières / voitures auto-générées | `Series`, `Img`, `Audio` TTS |
| Vidéos d'événements / invitations personnalisées | props, `Still`, `Lambda` |
| Miniatures YouTube / images OG dynamiques | `<Still>` + `renderStill` |
| Vidéos pédagogiques (code animé, formules, schémas) | `evolvePath`, `interpolate`, texte |

## Produits SaaS possibles
- **API « JSON → vidéo »** (Express + `renderMedia` ou Lambda) avec facturation à la minute
- **Éditeur vidéo en ligne** (`@remotion/player` + formulaire + rendu cloud)
- **Générateur de sous-titres** (upload → Whisper → rendu → téléchargement)
- **Outil de pubs dynamiques** pour boutiques en ligne
- **Générateur de vidéos « wrapped » / rapport annuel** pour clients
- **Chaîne YouTube/TikTok 100 % automatisée** (script IA + voix + images + Remotion)

## Pour votre activité
- Pubs/démos animées pour **DTECFEU** (sécurité incendie, ATEX) : schémas animés, chiffres clés, certificats, avant/après.
- Vidéos automatiques pour le **blog** (résumé d'article → vidéo courte).
- Packs de **templates vendus** (Gumroad, Fiverr « gig » avec modèle personnalisable).
- Combiner avec vos **agents WhatsApp / RAG** : le bot génère une vidéo personnalisée et la renvoie.

## Checklist qualité pro
1. Un `Root.tsx` propre avec dossiers (`<Folder>`) par client/série
2. Props typées + `schema` zod (le client change textes/couleurs dans le Studio)
3. Thème centralisé (couleurs, polices)
4. Animations avec `spring`/`Easing` (jamais linéaire par défaut)
5. Sons : musique à -18 dB, voix claire, ducking
6. Export : H.264 CRF 16-18 ; 9:16, 1:1 et 16:9 depuis le même composant
7. Rendu serveur/Lambda pour la production en volume
