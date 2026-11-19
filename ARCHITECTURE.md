# Documentation d'architecture — Studio Vidéo (Node.js 22 + React + Remotion)

**Studio de motion design, montage vidéo EDL, production automatisée par lots et assistant IA avec garde-fous.**

L'application fonctionne intégralement sur un runtime **Node.js 22** mono-processus (`server.ts`, Express + middleware Vite en développement, build statique `web/dist` en production) sur le port `3000`. Tous les calculs métier, validations, rendus vidéo (`@remotion/cli` / `ffmpeg`), synthèses vocales et garde-fous de l'assistant résident côté serveur dans `server-node/`.

---

## Sommaire

1. [Vue d'ensemble et lois du studio](#1-vue-densemble-et-lois-du-studio)
2. [Stack technique et démarrage](#2-stack-technique-et-démarrage)
3. [Arborescence du projet](#3-arborescence-du-projet)
4. [Format de projet v2, modèles 9:16 et 16:9 (P6), polices & arabe RTL (P3)](#4-format-de-projet-v2-modèles-916-et-169-p6-polices--arabe-rtl-p3)
5. [Voix off & sous-titres multilingues (P3)](#5-voix-off--sous-titres-multilingues-p3)
6. [Montage footage — EDL fermé (P5)](#6-montage-footage--edl-fermé-p5)
7. [Autopilote conditionnel (P2), QC vidéo (P4) et `check_render` (P8)](#7-autopilote-conditionnel-p2-qc-vidéo-p4-et-check_render-p8)
8. [Copywriting structuré (P7)](#8-copywriting-structuré-p7)
9. [Garde-fous, budgets, arrêt global et journal d'audit (P9)](#9-garde-fous-budgets-arrêt-global-et-journal-daudit-p9)
10. [Référence complète des routes HTTP](#10-référence-complète-des-routes-http)
11. [Sécurité et vérifications](#11-sécurité-et-vérifications)

---

## 1. Vue d'ensemble et lois du studio

Studio Vidéo réunit cinq pôles complémentaires dans une interface React unique (`web/`) :

| Pôle | Route UI | Rôle | Moteur |
| --- | --- | --- | --- |
| **Studio & Design** | `/`, `/design`, `/cockpit` | Édition de scènes/calques, aperçu temps réel, assistant IA | Remotion Player + `@remotion/cli` |
| **Voix off** | `/tts` | Synthèse vocale Piper/Kokoro, alignement de répliques | `tts.ts` + `captions.ts` |
| **Montage** | `/montage` | Montage footage par EDL fermé (`speed`, `subtitles`, `loudnorm`, `grade`) | `edl.ts` + `montage.ts` (FFmpeg) |
| **Production & Livraison** | `/production`, `/delivery`, `/library` | Lots CSV → file persistante → paquet ZIP (`videos/`, `.srt`, `metadata/`) | `batch.ts` + `queue.ts` + `delivery.ts` |
| **Sources & Outils** | `/moments`, `/clips`, `/podcast`, `/sources`, `/projects`, `/settings` | Transcription ASR, moments forts, banques médias, réglages clés API | `asr.ts`, `moments.ts`, `stock.ts`, `settings.ts` |

### Lois invariantes
1. **Validation serveur stricte** : aucune opération de projet, EDL, copywriting ou pack de marque n'est acceptée sans passer par les validateurs `server-node/`.
2. **Chemins et secrets bornés** : les médias utilisent exclusivement `media://<uuid>` (`/api/media/<uuid>`), aucun chemin système ni clé API ne fuite vers le navigateur ou dans les logs.
3. **Budget et révocabilité** : les actions auto-confirmées sont bornées par heure, excluent la génération d'image / suppressions / réglages / écrasements, et peuvent être coupées instantanément par l'**arrêt global**.

---

## 2. Stack technique et démarrage

- **Serveur HTTP & orchestration** : Node.js 22 TypeScript natif (`tsx server.ts` en dev, `node server.ts` en production), Express 4, Multer, `@google/genai`, `yazl`/`adm-zip`/FFmpeg CLI.
- **Frontend** : React 18, TypeScript, Vite 6 (`hmr: false`), Tailwind CSS, Radix UI, Lucide Icons, Remotion 4 (`remotion`, `@remotion/player`, `@remotion/cli`, `@remotion/paths`).
- **Port** : `0.0.0.0:3000` (`DEFAULT_APP_PORT` ou `3000`).

Commandes principales :
```bash
npm install
npm run dev      # Lance server.ts avec middleware Vite (dev SPA + API sur :3000)
npm run build    # Build frontend Vite -> web/dist + vérifications TypeScript
npm start        # Lance server.ts en production (sert web/dist + API sur :3000)
npm run lint     # tsc --noEmit + vérifications syntaxiques serveur & client
```

---

## 3. Arborescence du projet

```text
server.ts                     Point d'entrée unique Express + Vite (dev) / web/dist (prod)
package.json                  Dépendances unifiées serveur + client + scripts
tsconfig.server.json          Configuration TypeScript stricte du serveur (noEmit)
metadata.json                 Métadonnées de l'application
.env.example                  Variables d'environnement documentées (sans secrets)

server-node/
  schema.ts                   Schéma projet v2, modèles quote_cinematic / quote_horizontal / quote_vertical
  resolve.ts                  Résolution déterministe (frames, échelle côté court, RTL, polices, ressources)
  validation.ts               Validation des scènes, calques, thèmes, exports, durées
  fonts.ts                    Catalogue polices OFL + détection arabe (`containsArabic`) + RTL
  effects.ts                  Catalogue des effets Remotion (4 effets max par cible)
  render.ts                   Préparation props, export MP4 (`@remotion/cli` + fallback FFmpeg) & `checkRender` (P8)
  edl.ts                      Contrat EDL fermé (P5 : `speed`, `subtitles`, `loudnorm`, transitions, grades)
  montage.ts                  Pipeline FFmpeg de montage EDL (trim, setpts/atempo, xfade, drawtext/subtitles, loudnorm)
  tts.ts                      Catalogue multilingue Piper/Kokoro + `pickVoiceForLanguage` (P3)
  captions.ts                 Alignement mot-à-mot WAV + wrapping RTL/LTR (P3)
  asr.ts                      Fournisseurs ASR (Groq Whisper optionnel + mode énergie local) (P3)
  budgets.ts                  Budgets horaires glissants, allowlist/blocklist auto-confirm, arrêt global (P9)
  logger.ts                   Journal JSONL sanitizé dans `logs/agent-actions.jsonl` (P9)
  batch.ts, queue.ts, csv_source.ts, delivery.ts
  brands.ts, branding.ts, library.ts, folders.ts, media.ts, mediacache.ts
  moments.ts, clips.ts, podcast.ts, probe.ts, retrieval.ts, security.ts, settings.ts, skills.ts, sources.ts, stock.ts
  agent/
    llm.ts                    Client unifié Gemini / Groq / OpenAI-compatible + tracking budget LLM
    proposals.ts              Validation opérations projet + `validateCopywriting` (P7) + étapes autopilote (P2)
    tools.ts                  12 outils lecture seule dont `check_render` (P8)
    review.ts                 QC vidéo DOM + passe vision optionnelle (OFF par défaut, `vision_review: false`) (P4)
    actions.ts                Exécution des actions studio avec contrôle budget & journalisation
    autopilot.ts              Orchestrateur 8 étapes conditionnelles (P2) avec reprise et annulation
    service.ts                Routeur requêtes agent (`copywriting`, `check_render`, `16:9`, `autopilot`, LLM)

web/
  public/fonts/               Polices OFL embarquées dont NotoSansArabic-{400,700}.ttf (P3)
  src/api/client.ts           Client HTTP typé (projets, montage EDL, copywriting, budgets, logs)
  src/remotion/               Compositions Remotion (`quote-cinematic`, `quote-horizontal`, `quote-vertical`)
  src/pages/                  Pages UI dont `MontagePage.tsx` (P5), `DesignPage.tsx`, `MomentsPage.tsx`, etc.
  src/components/agent/       `AgentPanel.tsx` (P7/P9), `AutopilotTracker.tsx` (P2), `ActionTracker.tsx` (P8)
```

---

## 4. Format de projet v2, modèles 9:16 et 16:9 (P6), polices & arabe RTL (P3)

- Trois compositions officielles enregistrées dans `server-node/schema.ts` et `web/src/remotion/registry.tsx` :
  - `quote_cinematic` (`compositionId: "quote-cinematic"`, `1080x1920`, ratio 9:16)
  - `quote_horizontal` (`compositionId: "quote-horizontal"`, `1920x1080`, ratio 16:9 — **P6**, modèle paysage natif YouTube / LinkedIn avec disposition adaptée et `label: "Citation horizontale (16:9)"`)
  - `quote_vertical` (`compositionId: "quote-vertical"`, `1080x1920`, ratio 9:16)
- **Mise à l'échelle côté court (`resolve.ts`)** : `scale = Math.min(width, height) / 1080`, garantissant des tailles typographiques identiques en `1080x1920` et `1920x1080` (pas d'écrasement ni d'étirement).
- **Polices et arabe RTL** :
  - Polices `NotoSansArabic-400.ttf` et `NotoSansArabic-700.ttf` sous licence **SIL OFL 1.1** (`web/public/fonts/licenses/noto-sans-arabic/OFL.txt`), déclarées dans `web/src/remotion/fontCatalog.json` sous l'id `noto-sans-arabic`.
  - Si un calque texte contient des caractères arabes (`containsArabic`), `resolve.ts` bascule automatiquement `direction: "rtl"` et sélectionne `noto-sans-arabic` si la police courante ne couvre pas le script arabe. `QuoteCinematic.tsx` applique `dir={resolved.direction}`.

---

## 5. Voix off & sous-titres multilingues (P3)

- `tts.pickVoiceForLanguage(lang, TTS_MODELS_DIR)` sélectionne automatiquement une voix adaptée à la langue demandée (`fr`, `en`, `ar`, `es`, `de`, …), y compris en mode autopilote.
- `captions.alignScriptToWav()` aligne le script mot-à-mot sur la durée WAV mesurée et `captions.wrapWords(..., { rtl })` formate les sous-titres avec gestion RTL pour l'arabe (`max_chars: 46`, max 2 lignes).
- L'ASR (`server-node/asr.ts`) est optionnel : Groq Whisper n'est appelé que s'il est configuré et demandé ; sinon le studio s'appuie sur la détection énergétique locale + alignement script déterministe.

---

## 6. Montage footage — EDL fermé (P5)

`server-node/edl.ts` et `server-node/montage.ts` exposent un contrat **strictement fermé** (aucune expression libre transmise à FFmpeg) :
- **Plans (`cuts[]`)** : `media` (`media://<id>`), `in`, `out`, **`speed`** (`0.25` à `4.0` — applique `setpts=PTS/<speed>` vidéo et chaîne `atempo` audio), `role`, `transition` (`cut | fade | dissolve | wipeleft | slideup`, `0..2s`).
- **Audio** : musique optionnelle (`gain_db`, `duck`, `fade_in`, `fade_out`) + **`loudnorm`** (booléen, `true` par défaut → filtre FFmpeg `loudnorm=I=-14:TP=-1.5:LRA=11`).
- **Sous-titres (`subtitles`)** : `enabled`, `burn_in`, `style` (`font_size`, `color`, `position: "bottom" | "center"`), `cues[]` (`{ start, end, text }`), incrustés via filtres `drawtext` échappés côté serveur.
- **Étalonnage (`grade`)** : `look` (`none | warm | cool | sepia | mono | teal_orange`), `saturation`, `contrast`.

---

## 7. Autopilote conditionnel (P2), QC vidéo (P4) et `check_render` (P8)

### P2 — Pipeline autopilote à 8 étapes conditionnelles
`server-node/agent/autopilot.ts` exécute séquentiellement :
1. `script` — Génération/validation du texte (accroche, corps, auteur, langue)
2. `design` — Création du projet 9:16 ou 16:9, thème, police (arabe auto si besoin)
3. `media` *(conditionnelle)* — Fond vidéo/image si disponible en médiathèque locale, sinon `skipped` explicite
4. `voice` *(conditionnelle)* — Synthèse vocale + sous-titres si voix demandée et binaire Piper prêt, sinon `skipped` avec raison
5. `export` — Rendu MP4 final (et variantes multi-ratios si demandées)
6. `qc` *(conditionnelle)* — Exécution de `reviewProject` + `checkRender` (`skipped` si désactivé dans la spec)
7. `metadata` *(conditionnelle)* — Génération copywriting structuré `publish` (`skipped` si non demandé)
8. `delivery` *(conditionnelle)* — Préparation du résumé de livraison (`skipped` si aucun export produit)

Chaque étape non exécutée porte explicitement `status: "skipped"` et un `message` explicatif dans `AutopilotTracker.tsx`.

### P4 — Contrôle qualité (`reviewProject`)
- Passe 1 (toujours active) : audit déterministe du graphe résolu (débordements de texte, contrastes, médias manquants, durées, police arabe manquante).
- Passe 2 (**vision optionnelle, désactivée par défaut**) : `cfg.vision_review === false` par défaut dans `settings.ts`. Une analyse visuelle par LLM multimodale n'est déclenchée que si l'utilisateur active explicitement `vision_review` ET passe `allow_vision: true`.

### P8 — Outil de vérification `check_render`
- Accessible en outil lecture seule `check_render` (`server-node/agent/tools.ts`) et en action studio `project_check_render` (`server-node/agent/actions.ts`).
- Vérifie la géométrie DOM des calques du projet actif (débordement horizontal/vertical, durées nulles, contraste, polices manquantes) ainsi que l'intégrité du MP4 exporté via `probe.ts` / FFmpeg (flux vidéo, présence audio, niveau moyen pour détecter les frames entièrement noires ou pistes silencieuses).

---

## 8. Copywriting structuré (P7)

- Le type de proposition `copywriting` (`server-node/agent/proposals.ts:validateCopywriting`) valide un objet strict :
  `{ title, description, hashtags, hook_lines, cta, language }`.
- Lorsqu'un projet est ouvert, accepter la proposition applique l'opération `set_publish` sur `project.publish` (sans modifier scènes ni calques).
- `AgentPanel.tsx` affiche une carte structurée (titre, description, CTA, badges hashtags, langue).

---

## 9. Garde-fous, budgets, arrêt global et journal d'audit (P9)

Implémentés dans `server-node/budgets.ts` et `server-node/logger.ts` :
- **Budgets horaires glissants (fenêtre 3600 s)** :
  - `auto_confirms_per_hour`: `15`
  - `llm_calls_per_hour`: `60`
  - `exports_per_hour`: `10`
  - `autopilot_runs_per_hour`: `5`
- **Allowlist / Blocklist d'auto-confirmation** :
  - Autorisées sous budget : `project_patch`, `project_new`, `project_review`, `project_check_render`, `project_export`, `montage_render`, `brand_apply`, `brand_capture`, `tts_generate`, `copywriting_generate`, `autopilot_start`.
  - Toujours manuelles / bloquées en auto-confirmation : `image_generate`, `settings_update`, `delete_project`, `delete_media`, ainsi que tout export/montage avec `overwrite: true`.
- **Arrêt global (`POST /api/agent/stop` / `POST /api/agent/resume`)** :
  - Coupe immédiatement toutes les tâches actives (`cancelAllJobs`), tous les lots en cours et les autopilotes, et bloque toute nouvelle consommation de budget jusqu'à reprise explicite.
- **Journal sanitizé (`logs/agent-actions.jsonl`, `GET /api/agent/logs`)** :
  - Chaque proposition, exécution d'action, dépassement de budget ou arrêt global est enregistré en JSONL append-only après masquage récursif des clés contenant `key`, `secret`, `token`, `pin`, `password` ou `authorization`.

---

## 10. Référence complète des routes HTTP

- **Santé & Réglages** : `GET /api/health`, `GET/POST /api/settings`, `GET /api/sources`, `POST /api/sources/:id`, `POST /api/sources/:id/test`
- **Projets & Studio** : `GET/POST/DELETE /api/projects`, `POST /api/projects/validate`, `GET /api/studio/models`, `GET /api/studio/effects`, `GET /api/studio/fonts`, `GET /api/studio/default`, `POST /api/studio/prepare`, `POST /api/studio/upgrade`, `POST /api/studio/inspect`, `GET/POST /api/studio/provenance`
- **Exports & Montage EDL** : `POST /api/exports`, `GET /api/exports/:jobId`, `POST /api/exports/:jobId/cancel`, `GET /api/exports/:jobId/file`, `POST /api/montage/validate`, `POST /api/montage`, `GET /api/montage/:jobId`, `GET /api/montage/:jobId/file`
- **Bibliothèque, Marques, Dossiers & Médias** : `/api/library*`, `/api/brands*`, `/api/folders*`, `POST /api/media/upload`, `GET /api/media/:mediaId`
- **Production & Livraison** : `/api/batch*`, `/api/delivery/:batchId*`
- **Voix, Moments, Clips, Podcast & Connaissances** : `/api/tts*`, `/api/moments*`, `/api/clips`, `/api/podcast/stats`, `/api/skills*`
- **Assistant, Autopilote & Garde-fous P9** :
  - `GET /api/agent/status`, `GET /api/agent/capabilities`, `POST /api/agent/index`, `POST /api/agent/check`, `POST /api/agent/models`, `POST /api/agent/search`
  - `POST /api/agent/ask`, `GET /api/agent/proposals/:id`, `POST /api/agent/proposals/:id/accept|execute|reject`
  - `POST /api/agent/autopilot/plan`, `POST /api/agent/autopilot/start`, `GET /api/agent/autopilot/:jobId`, `POST /api/agent/autopilot/:jobId/cancel`, `GET /api/agent/autopilot/:jobId/file`, `GET /api/agent/autopilot/:jobId/format/:name`
  - `POST /api/agent/stop`, `POST /api/agent/resume`, `GET /api/agent/budget`, `GET /api/agent/logs`

---

## 11. Sécurité et vérifications

- `server-node/security.ts` impose `safeName()` et le bornage strict des répertoires pour prévenir toute traversée de répertoire (`../`).
- `checkOrigin()` bloque les requêtes cross-origin non autorisées sur l'API.
- Les clés API (`Gemini`, `Groq`, banques stock) ne quittent jamais `server-node/settings.json` / `sources.json` et sont automatiquement caviardées par `logger.ts`.
- La vérification complète du build repose sur `npm run build` (`vite build`) et `npm run lint` (`tsc --noEmit` client + serveur).
