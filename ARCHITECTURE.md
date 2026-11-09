# Documentation complète — youtube_clipper

**Studio de motion design, production automatisée par lots et assistant IA local.**

Ce fichier est la **seule documentation du projet**. Il remplace `FEATURES.md` (fusionné
ici le 2026-11-03, sauvegarde dans `E:\youtube\_sauvegarde_docs_20261103\`) et explique,
dans l'ordre : ce que fait l'application, avec quelle technologie, comment elle démarre,
**ce que contient chaque fichier de l'arborescence**, où sont les données, **comment
fonctionne chaque onglet panneau par panneau**, puis le moteur de rendu, l'assistant IA,
l'API, la sécurité, les tests, les limites et les recettes d'extension.

État : 2026-11-06, après les tranches « couche d'effets » (§6.4 et §7.1),
« navigation groupée + assistant central » (§1.2, §8.1 et §9.8),
« livraison commerciale » — packs de marque (§6.6), sous-titres et miniatures (§6.5)
et paquet ZIP d'un lot + page Livraison (§8.10) — et « configuration guidée » :
le Cockpit affiche un parcours d'activation de l'assistant en trois étapes tant
qu'il n'est pas prêt (§8.1), sans nouvel endpoint ni dépendance.
Interface **web uniquement** (Tkinter retiré), serveur **local**, aucun cloud obligatoire.

---

## Sommaire

| Partie | Contenu |
| --- | --- |
| [1. Vue d'ensemble](#1-vue-densemble) | à quoi sert l'application, les 4 axes, navigation groupée et tableau des pages, raccourcis clavier, les 4 lois du studio, glossaire |
| [2. Stack technique](#2-stack-technique) | chaque couche, les versions réellement installées, le rôle de chaque bibliothèque, ce qui est volontairement absent |
| [3. Démarrer, construire, tester](#3-démarrer-construire-tester) | `start_web.bat` ligne à ligne, build, dev, tests, santé |
| [4. Arborescence commentée](#4-arborescence-commentée) | **fichier par fichier** : rôle, lignes, qui l'appelle, ce qu'il lit et écrit |
| [5. Données et persistance](#5-données-et-persistance) | chaque dossier, chaque format, le DDL des deux SQLite, ce qui n'est jamais persisté |
| [6. Format de projet v2](#6-format-de-projet-v2-champ-par-champ) | chaque champ, ses valeurs, qui le consomme, **dont le catalogue d'effets §6.4, les sous-titres/miniatures §6.5, les packs de marque §6.6 et la chaîne transcription → moments forts → projet §6.7** |
| [7. La chaîne de rendu](#7-la-chaîne-de-rendu-pas-à-pas) | de l'édition au MP4, étape par étape |
| [8. Les pages, une par une](#8-les-pages-une-par-une) | **Cockpit · Design · Bibliothèque · Production · Livraison · Clips · Moments forts · Podcast · Shorts v1 · Projets · Réglages** : panneaux, champs, boutons, endpoints, données |
| [9. Assistant IA du studio](#9-assistant-ia-du-studio-serveragent) | fournisseurs, modèles, contrat, 30 outils, contexte borné, intégrations |
| [10. Production par lots](#10-production-par-lots-le-moteur) | CSV, champs adressables, politique, file SQLite, manifeste |
| [11. Médias, dossiers connectés, polices, connaissances](#11-médias-dossiers-connectés-polices-et-connaissances) | médiathèque, provenance, licences, paquet Remotion |
| [12. API : toutes les routes](#12-api-référence-complète) | qui appelle quoi |
| [13. Frontend en interne](#13-frontend-en-interne) | `client.ts`, jobs, UI kit, Remotion |
| [14. Sécurité](#14-sécurité) | chaque contrôle, son code, son test |
| [15. Tests, vérifications et mesures réelles](#15-tests-vérifications-et-mesures-réelles) | |
| [16. Limites connues](#16-limites-connues) | |
| [17. Étendre le studio : recettes](#17-étendre-le-studio-recettes) | |
| [18. Dépannage](#18-dépannage) | |

---

## 1. Vue d'ensemble

### 1.1 Ce que fait l'application

`youtube_clipper` est un **studio vidéo local** qui produit des vidéos verticales
(citations, accroches, révélations), les personnalise dans un éditeur visuel, les décline
en série depuis un fichier CSV, **transcrit une source importée pour en proposer les moments
forts**, livre le résultat en paquet ZIP au client, et met à disposition un assistant IA qui
connaît ces fonctions et les utilise — sans jamais agir à la place de l'utilisateur.

Cinq axes, plus un héritage :

| Axe | Question à laquelle il répond | Où | Moteur |
| --- | --- | --- | --- |
| **DESIGN** | « comment ma vidéo doit-elle être faite ? » — scènes, calques, textes, polices, couleurs, animations, audio, cadre, **et la marque du client (pack appliqué à un projet ou à tout un lot)** | `/design` | Remotion |
| **PRODUCTION** | « comment en faire 200 sans ouvrir l'éditeur ? » — modèle + CSV + dossiers de médias → plan → file de rendu | `/production` | Remotion, en série |
| **MOMENTS FORTS** | « qu'est-ce qui vaut un clip dans cette source ? » — transcription réelle (Whisper), fenêtres scorées et expliquées, puis **au clic** un projet v2 sous-titré, marqué, miniature et métadonnées | `/moments` | Groq Whisper ou Whisper local **déjà installé**, FFmpeg, Remotion |
| **LIVRAISON** | « comment je l'envoie au client ? » — un lot rendu devient un ZIP : MP4, `.srt` calés sur les frames rendues, miniatures, **métadonnées marketing**, manifeste, `LISEZ-MOI.txt` | `/delivery` | `zipfile` + `imageio-ffmpeg`, aucun service externe |
| **ASSISTANT IA** | « dis-moi ce que tu veux, je prépare le projet ou le mapping » — tiroir **global** présent sur toutes les pages, ouvert par défaut depuis le cockpit | [`AssistantDock.tsx`](file:///E:/youtube/youtube_clipper/web/src/components/AssistantDock.tsx#L1), `Ctrl+I` | LLM local / Gemini / Groq |
| **Héritage** | outils antérieurs conservés et branchés sur le web | `/clips`, `/podcast`, `/short-videos`, `/projects` | yt-dlp + Groq + FFmpeg, chaîne Pillow v1 |

### 1.2 La navigation : quatre groupes, onze pages, un assistant

La barre latérale n'est plus une liste plate de huit entrées : elle est **regroupée par
intention** (Pilotage · Automatisation · Sources · Système) dans une seule source de vérité,
[`web/src/lib/navigation.ts`](file:///E:/youtube/youtube_clipper/web/src/lib/navigation.ts#L33-L112),
lue à la fois par le [`Sidebar`](file:///E:/youtube/youtube_clipper/web/src/App.tsx#L27) et par la
palette de commandes — donc **aucun lien n'existe dans l'une sans l'autre**. Chaque entrée porte
une `description` réelle (aide-titre dans la barre latérale, ligne descriptive dans la palette) :
`/` et toute URL inconnue (`path="*"`) mènent au **Cockpit**, plus à Design.

| Page | URL | Groupe | Rôle en une phrase | Ce qu'elle écrit sur disque |
| --- | --- | --- | --- | --- |
| **Cockpit** | `/` | Pilotage | point d'entrée : champ de demande à l'assistant, exemples, catalogue d'effets, file de production, derniers projets, modèles, points de contrôle ; **configuration guidée** de l'assistant tant qu'il n'est pas prêt | `server/settings.json` via le parcours d'activation (uniquement au clic « Activer l'assistant ») ; sinon rien — les cartes sont lectrices |
| **Design** | `/design` | Pilotage | éditer un projet v2 (scènes, calques, **effets**), lui appliquer un **pack de marque** et l'exporter en MP4 ; l'assistant est le tiroir droit | `projects/<nom>.json`, `models/<id>.json`, `brands/<id>.json`, `media/<uuid>`, `exports/<nom>.mp4` |
| **Production** | `/production` | Automatisation | fabriquer un lot : modèle + CSV + dossiers de médias → plan → file → manifeste | `batch/*`, `exports/*.mp4`, `media/<uuid>` |
| **Livraison** | `/delivery` | Automatisation | assembler et télécharger le paquet ZIP d'un lot (vidéos + `.srt` + miniatures + métadonnées + manifeste) | `batch/deliveries/<id>-<nom>.zip` |
| **Bibliothèque** | `/library` | Automatisation | lister les modèles réutilisables, en créer depuis Design, en retirer, en déposer à la main | `models/*.json` |
| **Clips** | `/clips` | Sources | télécharger une vidéo YouTube, faire découper sa transcription par Groq, extraire les clips en FFmpeg | `clips/<sid>/…` |
| **Moments forts** | `/moments` | Sources | transcrire une source **déjà importée** (Whisper), scorer des fenêtres et expliquer chaque score, puis **au clic** générer un projet v2 sous-titré, marqué, avec miniature et métadonnées | `moments/<id>.json` + `moments/work/`, puis au clic `projects/<nom>.json` + `.srt`, `media/<uuid>` |
| **Podcast** | `/podcast` | Sources | constituer une base de phrases découpées, puis assembler une vidéo qui énonce un texte | `podcast_db/…` |
| **Projets** | `/projects` | Sources | liste et ouverture des fichiers `projects/*.json` | supprime dans `projects/` |
| **Shorts v1** | `/short-videos` | Sources | l'éditeur historique à une scène, conservé parce que des projets v1 existent | `projects/*.json`, `exports/*.mp4` |
| **Réglages** | `/settings` | Système | clé Groq de Clips, **transcription des moments forts** (fournisseur, clé dédiée, modèle, langue), fournisseur LLM de l'assistant, manifeste des capacités | `server/settings.json` |

**Raccourcis globaux** (écoutés dans [`Shell`](file:///E:/youtube/youtube_clipper/web/src/App.tsx#L88-L106),
d'importe où, sauf avec `Alt`) :

| Raccourci | Effet réel |
| --- | --- |
| `Ctrl+K` | **palette de commandes** ([`CommandPalette.tsx`](file:///E:/youtube/youtube_clipper/web/src/components/CommandPalette.tsx#L1), 211 l.) : filtre les 11 pages (nom + description), l'action « Ouvrir l'assistant », les projets enregistrés (« Ouvrir le projet « … » ») et les modèles (« Nouveau projet depuis « … » ») ; flèches + `Entrée` pour choisir, `Échap` pour fermer |
| `Ctrl+I` | ouvre / ferme le **tiroir assistant** — la conversation est montée dans `App`, donc elle survit aux changements de page |
| `Ctrl+/` | retour au cockpit (`/`) |
| `Échap` | ferme le tiroir (et les dialogues, comme avant) |
| `Ctrl+Z` / `Ctrl+Maj+Z` | annuler / rétablir dans l'éditeur (`design/edit.ts`, inchangé) |

Le détail — panneau par panneau, champ par champ, bouton par bouton, endpoint par endpoint —
est au [chapitre 8](#8-les-pages-une-par-une).

### 1.3 Les quatre lois du studio

Elles sont vérifiables dans le code, pas seulement écrites ici :

1. **Le plan affiché est exactement ce qui est rendu.** `POST /api/batch/plan` et
   `POST /api/batch/start` appellent le même `shortvideos.batch.build_plan()`
   ([`server/api/batch.py:158`](file:///E:/youtube/youtube_clipper/server/api/batch.py#L158) et
   [`:185`](file:///E:/youtube/youtube_clipper/server/api/batch.py#L185)). La file ne réinvente rien.
2. **Une seule entrée de rendu.**
   [`server/render.py:render_project_to_mp4()`](file:///E:/youtube/youtube_clipper/server/render.py#L1)
   est appelée par l'export unitaire (`server/api/exports.py`) **et** par le worker du lot
   (`server/queue.py`). Il n'existe ni deuxième file, ni deuxième moteur.
3. **Rien n'est jamais rempli en silence.** Un fichier nommé dans le CSV mais introuvable
   **bloque** la ligne ; un texte trop long est **signalé**, jamais coupé ; une licence
   absente est écrite `inconnue`, jamais validée ; l'assistant IA ne déclenche **aucun**
   rendu, **aucune** suppression, **aucun** lot. Il en va de même de la livraison : un
   sous-titre n'est écrit que pour un texte **réellement affiché** (jamais estimé, jamais
   substitué à la voix), une miniature ratée devient un **avertissement** du
   paquet, et un pack de marque invalide **n'est pas enregistré**.
   **L'assistant propose, l'utilisateur applique** vaut aussi pour les moments forts :
   `POST /api/moments/analyze` n'écrit que dans `moments/` — ni `projects/`, ni la file
   SQLite ne bougent ; seul `POST /api/moments/{id}/generate`, déclenché par un clic,
   écrit un projet, et un projet généré **invalide n'est pas écrit du tout**
   ([`server/moments.py:445`](file:///E:/youtube/youtube_clipper/server/moments.py#L445)).
   Chaque score est accompagné de ses `reasons` chiffrées : aucune note sortie de nulle part.
4. **Aucun chemin Windows ne traverse le projet ni le navigateur.** Les médias sont
   référencés `media://<uuid>` et servis sous `/media-cache/<id><ext>`
   ([`server/mediacache.py`](file:///E:/youtube/youtube_clipper/server/mediacache.py#L1)).
   Un pack de marque refuse donc chemin et URL (`branding._check_ref`), et le nom du ZIP de
   livraison est **retrouvé par le serveur** (`package_path`), jamais proposé par le client.

### 1.4 Glossaire

| Terme | Définition exacte dans ce projet |
| --- | --- |
| **projet** | document JSON versionné (`projects/*.json`) décrivant une vidéo : modèle, scènes, calques, thème, audio, export. Monnaie unique entre l'éditeur, le Player, le rendu et les lots. |
| **modèle** | deux sens à ne pas confondre : (a) `model.id` du projet = la **composition Remotion** (`quote_cinematic`, `quote_vertical`) ; (b) un **projet v2 enregistré** dans `models/`, proposé par l'onglet Bibliothèque. |
| **scène** | segment temporel du projet (`duration` en secondes) avec son fond et ses calques. |
| **calque** | élément posé sur une scène : texte (avec `role` = hook / quote / author / reveal…) ou image. |
| **`resolved`** | bloc **calculé côté serveur** par `shortvideos/resolve.py` : frames absolues, fenêtres d'animation, polices, ressources, graine. Jamais édité, jamais persisté, jamais fourni par le LLM. |
| **props** | objet JSON passé à Remotion (`--props=`) : le `resolved` + les URLs locales des médias. |
| **média** | fichier importé dans `media/` sous un nom `uuid.ext`, provenance optionnelle dans `media/provenance/<uuid>.json`. |
| **dossier connecté** | chemin absolu du disque autorisé, enregistré dans `batch/folders.json`, scanné vers la médiathèque (fonds vidéo, musiques, images). |
| **lot** | une production par lots : un modèle + un CSV + un mapping, 1 à 2000 lignes, pilotée par `batch/queue.sqlite3`. |
| **manifeste** | fichier de livraison JSON ou CSV décrivant chaque ligne rendue (fichier, durée, sources, avertissements). |
| **pack de marque** | fichier `brands/<id>.json` portant ce qui se répète d'une vidéo à l'autre pour un client : `theme`, `signature` (logo), `audio` (musique) et `models` autorisés. Ne touche **jamais** les scènes ni le texte — c'est ce qui le distingue d'un modèle de la bibliothèque. |
| **paquet de livraison** | ZIP assemblé après un lot dans `batch/deliveries/` : `videos/`, `subtitles/`, `thumbnails/`, `metadata/`, `manifeste.json` / `.csv`, `LISEZ-MOI.txt`. |
| **ASR** | reconnaissance vocale automatique : `shortvideos/asr.py` transcrit une source en segments `{start, end, text}` **en secondes absolues**. Deux voies, Groq (`whisper-large-v3-turbo`, réseau, sur demande) et Whisper local (whisper.cpp ou `faster_whisper`, **détectés, jamais installés**). |
| **analyse** | instantané `moments/<id>.json` : référence `media://` de la source, transcription horodatée, paramètres de détection, moments classés. **Aucun projet, aucune file, aucune clé** n'y est écrit. |
| **moment fort** | fenêtre `[start, end]` de la source retenue par `shortvideos/moments.py:detect()`, avec un `score` **somme de critères expliqués** (`reasons`), des `keywords` et des `cues`. Bornes par défaut 10–45 s, 6 moments au plus, chevauchement toléré 0,3. |
| **cue** | réplique sous-titrée `{start, end, text}` issue **des bornes de segments ASR** (jamais d'un temps estimé), regroupée puis repliée à 46 caractères / 2 lignes par `moments.captions()` / `wrap_caption()`. |
| **`publish`** | bloc du projet généré portant les métadonnées de plateforme : `title`, `description`, `hashtags`, plus les clés de calcul (`moment_id`, `start`, `end`, `duration`, `voice`, `thumbnail`, `source`…). `server/delivery.py:publish_of()` ne recopie dans le ZIP **que** le titre, la description et les hashtags. |
| **proposition** | réponse normalisée de l'assistant (`project_patch`, `project_new`, `library_save`, `batch_plan`, `knowledge_answer`, `none`), validée serveur puis **acceptée par un clic**. |
| **candidat** | projet généré par l'assistant, gardé en mémoire vive seulement tant que l'utilisateur n'a pas cliqué « Appliquer ». |
| **job** | tâche longue suivie par `server/jobs.py` (export, clips, podcast, agent) : progression, message, annulation, TTL 1 h. |
| **worker** | thread secondaire de `server/queue.py` qui rend les lignes du lot une par une. |
| **passe** | nombre d'utilisations d'un média dans un lot : `(position-1)//len(pool)+1`. Utile quand les ressources sont moins nombreuses que les lignes. |
| **graine** | `variation.seed` : rend les variations reproductibles. Dans un lot : graine du modèle + index − 1. |
| **passe-temps (frame)** | les durées du projet sont en **secondes**, les fenêtres d'animation en **frames** ; `resolve.py` fait la conversion avec `export.fps`. |

---

## 2. Stack technique

### 2.1 Vue par couches

```
Navigateur (http://127.0.0.1:8000)
  React 18 + TypeScript + Vite + Tailwind  ──>  web/dist servi par FastAPI (même origine)
       │  Remotion Player 4.0.539 (aperçu)
       │  contrat HTTP typé : web/src/api/client.ts (1 089 lignes)
       ▼
FastAPI + uvicorn — 127.0.0.1:8000 — Python 3.12.10
  server/app.py  + 16 routeurs  +  middleware d'origine  +  bornage des chemins
       │
       ├── shortvideos/   moteur métier pur : schéma, résolution, validation, lots, sondes,
       │                  effets, sous-titres/miniatures, packs de marque,
       │                  transcription (asr), détection (moments), génération (moment_project)
       ├── server/agent/  assistant : client LLM, capacités, retrieval FTS5, contrat, outils
       ├── server/queue   file SQLite persistante + worker + manifeste
       ├── server/delivery  assemblage du paquet ZIP d'un lot (job, `.part.zip`)
       ├── server/brands  packs de marque client (`brands/*.json`) + application à un projet
       ├── server/moments analyses (`moments/*.json`), job de transcription, génération à la demande
       ├── server/folders médiathèque, dossiers connectés, scan, déduplication
       └── sous-processus : npx remotion render ──> exports/<nom>.part.mp4 ──> .mp4
                                    ▲
                        Node portable v22.23.4 (E:\youtube\_tools\node)
                        FFmpeg local (imageio-ffmpeg) — aucun ffprobe
                        Whisper local (whisper.cpp / faster_whisper) — détecté, jamais installé
```

### 2.2 Frontend — versions relevées dans `web/package.json`

| Paquet | Version | Rôle précis ici |
| --- | --- | --- |
| `react`, `react-dom` | ^18.3.1 | interface ; **aucun** state manager : `useState`/`useReducer` + un réducteur d'historique maison (`design/edit.ts`, `undo/redo`) |
| `react-router-dom` | ^6.28.0 | 11 entrées (dont `/`) + `*` → **Cockpit** ; `BrowserRouter`, servi par la même origine que l'API (fallback SPA du serveur) |
| `remotion` | 4.0.539 | runtime vidéo : `useCurrentFrame`, `interpolate`, `spring`, `<OffthreadVideo>`, `<Audio>`, `<Img>`, `staticFile` |
| `@remotion/player` | 4.0.539 | aperçu du Design et du Shorts v1 — **la même composition que le rendu** |
| `@remotion/cli` | 4.0.539 | `npx remotion render` lancé en sous-processus par `server/render.py` |
| `@radix-ui/react-label` | ^2.1.0 | labels accessibles (`components/ui/label.tsx`) |
| `@radix-ui/react-slider` | ^1.2.1 | sliders (durée, opacité, position, nombre de clips) |
| `@radix-ui/react-switch` | ^1.1.1 | interrupteurs (formats de clip, overwrite, alternance, streaming) |
| `lucide-react` | ^0.454.0 | icônes de navigation et d'action |
| `class-variance-authority` | ^0.7.0 | variantes des composants (`button.tsx`, `badge.tsx`) |
| `clsx` + `tailwind-merge` | ^2.1.1 / ^2.5.4 | `cn()` dans `web/src/lib/utils.ts` |
| `typescript` (dev) | ~5.6.3 | `tsc --noEmit` **bloquant** avant build |
| `vite` (dev) | ^6.0.3 | build + serveur de dev avec proxy `/api` → 8000 |
| `@vitejs/plugin-react` (dev) | ^4.3.3 | HMR |
| `tailwindcss` (dev) | ^3.4.14 | thème sombre, tokens (`tailwind.config.ts`, helpers `.panel` / `.panel-title` / `.input-base` dans `index.css`) |
| `postcss`, `autoprefixer` (dev) | ^8.4.49 / ^10.4.20 | chaîne Tailwind |

### 2.3 Backend — versions réellement installées (contrôlées sur ce poste)

| Paquet | Version | Rôle |
| --- | --- | --- |
| `fastapi` | 0.136.0 | 16 routeurs, middleware d'origine, service du SPA et de `/media-cache` |
| `uvicorn` | 0.44.0 | serveur ASGI (`python -m server.app`) |
| `pydantic` | 2.14.1 | schémas de requête (réglages, agent, lots) |
| `python-multipart` | 0.0.26 | uploads : médias, CSV, projets déposés |
| `httpx` | 0.28.1 | client LLM de `server/agent/llm_client.py` (streaming inclus) |
| `groq` | 1.1.2 | SDK déjà requis : `analyzer.py` (analyse texte de **Clips**) et `shortvideos/asr.py:264` (**transcription Whisper**, import paresseux — la voie Groq n'est chargée que si elle est demandée) |
| `yt-dlp` | 2026.10.26 | téléchargement vidéo + sous-titres (Clips, Podcast) |
| `Pillow` | 12.1.1 | mesure de débordement des projets v1 (`shortvideos/render.py`) ; plus moteur de production |
| `opencv-python` | 4.11.0.86 | vérification des MP4 sans ffprobe (`shortvideos/probe.py`) |
| `imageio-ffmpeg` | 0.6.0 | binaire FFmpeg local, et secours de `ffmpeg -i` pour le probe |
| `numpy` | 1.26.4 | dépendance numérique d'OpenCV |
| `requests` | 2.32.5 | modules hérités (`downloader.py`, `podcaster.py`) |
| `pytest` | 8.3.3 | 232 tests |
| `sqlite3` | stdlib, SQLite **3.49.1**, **FTS5 actif** | file de production + index de connaissances |

### 2.4 Qui fait quoi

- **`web/`** — édition, aperçu, dialogue, restitution. Zéro logique métier : l'interface
  appelle des routes et affiche ce que le serveur a calculé.
- **`shortvideos/`** — le métier pur : format v2, résolution déterministe, validation,
  politique des lots, sondes vidéo. **Aucune dépendance à FastAPI ni à React**, donc testable
  seul et réutilisable par un script.
- **`server/`** — transport, sécurité (origines, chemins bornés), persistance (JSON + SQLite),
  sous-processus Remotion, médiathèque, jobs.
- **`server/agent/`** — connaissance du studio (manifeste de capacités + index documentaire),
  conversation bornée, contrat des propositions, outils de lecture. **Aucune exécution.**
- **Remotion** — source de vérité de l'image animée : Player et rendu CLI partagent
  `web/src/remotion/registry.tsx`.

### 2.5 Volontairement absent

| Absent | Pourquoi |
| --- | --- |
| Tkinter, `main.py`, `run.bat` | retirés ; sauvegarde `E:\youtube\_sauvegarde_tkinter_20261102\` |
| LangChain, LlamaIndex, SDK OpenAI | l'assistant parle l'API OpenAI-compatible en `httpx` brut : aucune dépendance lourde |
| SQLAlchemy / ORM / migrations | 2 bases, 6 tables : SQL écrit à la main dans `server/queue.py` et `server/agent/retrieval.py` |
| CORS (`CORSMiddleware`) | le SPA est servi par le même serveur : même origine, donc rien à ouvrir — le middleware fait l'inverse, il **refuse** les origines étrangères |
| ffprobe | absent du poste → OpenCV + `ffmpeg -i` (`shortvideos/probe.py`) |
| CDN, polices ou images distantes | tout est local ; 5 familles de polices sur disque sous licence SIL OFL |
| Docker, CI, dépôt git | poste Windows local, projet non versionné — d'où la règle « sauvegarde avant toute suppression » |
| Comptes, authentification, multi-utilisateur | écoute `127.0.0.1`, mono-poste |
| Installation automatique de dépendances | `npm install` au premier build seulement ; rien n'est téléchargé au démarrage |
| Whisper local **installé par l'application** | `shortvideos/asr.py:local_backend()` **détecte** `whisper-cli` + un modèle `ggml-*.bin` (variables `WHISPER_CLI` / `WHISPER_MODEL`) ou le paquet `faster_whisper`, et répond « indisponible » **avec la raison écrite** si l'un manque. Aucun `pip install`, aucun téléchargement de modèle : la règle « aucune installation automatique » vaut aussi pour l'ASR |
| `@remotion/captions`, moteur de sous-titres tiers | le `.srt` est écrit à la main depuis `resolve()` ; la transcription, elle, vit dans `shortvideos/asr.py` et ne produit que des segments horodatés |
| Deuxième moteur de rendu (Pillow, moviepy) | interdit par la loi 2 ; `shortvideos/render.py` ne sert plus qu'à la mesure v1 |

---

## 3. Démarrer, construire, tester

### 3.1 Le lanceur unique : `start_web.bat`

[`start_web.bat`](file:///E:/youtube/youtube_clipper/start_web.bat#L1) est le **seul** point d'entrée.
Il fait, dans cet ordre :

1. `cd /d "%~dp0"` — se place à la racine du projet ;
2. `if exist "%~dp0..\_tools\node\node.exe" set "PATH=…"` — place le **Node portable v22.23.4**
   en tête de `PATH`, au même endroit que [`server/render.py`](file:///E:/youtube/youtube_clipper/server/render.py#L37)
   le cherche (`ROOT.parent/_tools/node`) : aucun chemin absolu hors projet, rien n'est supposé
   installé globalement ;
3. `where python` — absent ⇒ message explicite, `pause`, `exit /b 1` ;
4. si `web\dist\index.html` est absent → `npm install --no-audit --no-fund` (une seule fois,
   si `web\node_modules` manque) puis `npm run build` = `tsc --noEmit && vite build` ;
   échec ⇒ `popd`, message explicite, `pause`, `exit /b 1` ;
5. sinon → affiche `Frontend deja construit (web\dist).` ;
6. `python -m server.app --open` — uvicorn sur le `host`/`port` de `server/settings.json`
   (défauts `127.0.0.1` et `8000`). Le `--open` démarre un fil qui attend que
   `GET /api/health` réponde `200` **avant** d'ouvrir le navigateur sur l'URL réellement
   configurée : les imports prennent plusieurs secondes, ouvrir la page avant l'écoute
   montrerait un site inaccessible. Un hôte d'écoute `0.0.0.0`/`::` est navigué sur
   `127.0.0.1`. Sans `--open`, aucun navigateur n'est ouvert.

Le serveur reste au premier plan de la fenêtre : `Ctrl+C` arrête l'application, et un code
de sortie non nul affiche une erreur puis `pause`.

Aucun téléchargement de dépendance au démarrage, hormis le `npm install` de la toute première
construction.

### 3.2 Commandes utiles

| Objectif | Commande |
| --- | --- |
| Lancer l'application | `start_web.bat` |
| Reconstruire le frontend | `cd web && npm run build` |
| Développement à chaud | `cd web && npm run dev` (proxy `/api` → `http://127.0.0.1:8000`) |
| Types seuls | `cd web && npx tsc --noEmit` |
| Serveur sans build | `python -m server.app` (ajouter `--open` pour ouvrir le navigateur quand il répond) |
| Tests | `python -m pytest tests -q` → **232 passed** |
| Santé | `curl http://127.0.0.1:8000/api/health` |
| Un rendu hors interface | `python tests/e2e_export_remotion.py` |
| Whisper local (facultatif, **installé par vous**) | définir `WHISPER_CLI` vers `whisper-cli.exe` et `WHISPER_MODEL` vers un `ggml-*.bin`, ou installer `faster_whisper` ; `GET /api/moments/providers` affiche ce qui est réellement détecté |

### 3.3 Ce que le serveur annonce au démarrage

`GET /api/health` renvoie par exemple :

```json
{"status":"ok","groq_configured":false,"web_dist":true,
 "queue_recovered":{"items_requeued":0,"batches_paused":[]}}
```

`queue_recovered` est la trace de la reprise après arrêt : les lignes `running` repassent en
`queued`, le lot en `paused`, et **rien ne redémarre sans un clic utilisateur**.

### 3.4 Environnement réel du poste

Python 3.12.10 · Node portable 22.23.4 · Remotion 4.0.539 · Windows 10 build 17763 ·
`E:\youtube\youtube_clipper` · projet **non versionné par git**.

---

## 4. Arborescence commentée

Nombre de lignes indiqué pour chaque fichier (`.py` hors commentaires de licence, `.tsx`/`.ts`).
**« Qui l'appelle »** désigne l'entrée réelle dans le code, pas une intention.

### 4.1 Espace de travail `E:\youtube\`

```
E:\youtube\
├── _tools\node\                     Node.js + npm portables (v22.23.4) mis en PATH par start_web.bat
├── _sauvegarde_tkinter_20261102\    sauvegarde d'avant retrait de l'interface Tkinter (main.py, run.bat, shortvideos/tab.py)
├── _sauvegarde_docs_20261103\       FEATURES.md (fusionné ici) + ARCHITECTURE.md avant réécriture
├── _verif_batch\                    dossiers d'exemple (fonds vidéo, musiques) servis à la page Production
├── files (4).zip                    archive source de la bible Remotion (extraite par tools/extract_bible.py)
└── youtube_clipper\                 l'application, décrite ci-dessous
```

### 4.2 Racine du projet

| Fichier | Lig. | Rôle | Qui l'appelle |
| --- | --- | --- | --- |
| `start_web.bat` | 56 | **entrée unique** : PATH Node relatif, contrôle de Python, build conditionnel, `server.app --open` (navigateur ouvert quand `/api/health` répond) | l'utilisateur |
| `requirements.txt` | — | dépendances Python, avec commentaire de licence par paquet (Pillow MIT-CMU, OpenCV Apache-2.0, imageio-ffmpeg BSD-2, binaire FFmpeg GPLv3 usage local) | `pip install -r` (hors exécution) |
| `pytest.ini` | — | `testpaths = tests` et `--basetemp=.pytest_tmp` (le répertoire temporaire par défaut est refusé par Windows sur ce poste) | pytest |
| `ARCHITECTURE.md` | — | **ce fichier** : documentation unique | l'humain ; indexé partiellement dans l'index de l'agent (`studio-contract`) |
| `FEATURES.md` | — | **supprimé** (fusionné ici) | — |
| `analyzer.py` | — | découpe de transcription par Groq (résumé + segments candidats) | `server/api/clips.py` |
| `downloader.py` | — | wrapper yt-dlp : infos, téléchargement vidéo, récupération des sous-titres | `server/api/clips.py`, `server/api/podcast.py` |
| `processor.py` | — | découpe FFmpeg, recadrage portrait centré sur le visage | `server/api/clips.py` |
| `database.py` | — | accès à la base de phrases (CSV + dossiers de clips) | `server/api/podcast.py`, `podcaster.py` |
| `podcaster.py` | — | assemblage vidéo : `add_video`, `split_video`, `build_video`, `_find_all_matches`, `_select_with_alternation`, `_split_into_phrases`, `_assemble_clips`, `_detect_face_embedding`, `_parse_srt`, `get_stats` ; `db_dir = "podcast_db"` | `server/api/podcast.py` |

Ces cinq modules hérités ne touchent **ni au studio ni à la production** : ils sont appelés
tels quels par les routes Clips et Podcast, sans réécriture.

**Les dossiers de données à la racine** (créés à l'usage, tous dans `ALLOWED_DIRS`, détail au §5.1) :

```
youtube_clipper\
├── projects\   *.json                 éditions du Design (v1 et v2)
├── models\     *.json                 bibliothèque de modèles v2
├── brands\     *.json                 packs de marque client — vide tant qu'aucun pack n'est créé
├── moments\    *.json                 analyses de moments forts (transcription + détection)
│   └── work\<id>\                     energy.json (mesure RMS gardée) ; le WAV 16 kHz et les frames de travail sont supprimés après usage
├── media\      <uuid>.<ext>           médiathèque + media\provenance\<uuid>.json
├── exports\    <nom>.mp4              rendus unitaires (+ props-<id>.json pendant un rendu)
├── batch\
│   ├── folders.json                   dossiers de médias connectés
│   ├── csvs\*.json                    imports CSV
│   ├── queue.sqlite3                  file des lots (DDL au §5.2)
│   ├── manifests\*.json|*.csv         fiches de livraison d'un lot
│   └── deliveries\*.zip               paquets client (+ *.package.json, créé au premier paquet)
├── knowledge\  agent_index.sqlite3    index FTS5 de l'assistant (§5.3)
├── clips\ <sid>\  · downloads\ · podcast_db\   outils hérités
├── skills\     remotion\              connaissances lues par l'agent (lecture seule)
├── server\  shortvideos\  web\  tests\  tools\
```

### 4.3 `server/` — backend FastAPI (3 673 lignes hors `agent/` et `__init__.py`)

| Fichier | Lig. | Ce qu'il contient | Qui l'appelle / ce qu'il écrit |
| --- | --- | --- | --- |
| `app.py` | 170 | `FastAPI()`, inclusion des 16 routeurs sous `/api/*`, middleware `check_origin`, `GET /api/health`, montage statique de `web/dist` + `/media-cache/` + `/fonts/`, appel de `queue.recover()` au démarrage, `main()` + `--open` (fil qui attend la santé avant d'ouvrir le navigateur) | `python -m server.app [--open]` (uvicorn) ; écrit `queue.sqlite3` via recover |
| `security.py` | 140 | `ALLOWED_DIRS` (**12 racines** autorisées, dont `brands/`, `moments/` et `batch/deliveries/`), `assert_local_dir()`, `safe_name()`, `check_origin()`, `DEFAULT_ORIGINS` | toutes les routes qui touchent le disque ; **aucune écriture** |
| `settings.py` | 150 | chargement/sauvegarde de `server/settings.json`, liste blanche de clés plates, `PROVIDERS`, `CLOUD_BASE_URLS`, `PROVIDER_LABELS`, bornes `(min, défaut, max)` des paramètres LLM, et les 4 clés `asr_*` (fournisseur, clé Groq dédiée, modèle Whisper, langue) | `server/api/settings.py`, `server/agent/*`, `server/moments.py`, `app.py` ; **écrit** `server/settings.json` |
| `jobs.py` | 145 | registre en mémoire des tâches longues : `Job` (progression, message, résultat, erreur, `cancel_event`, `result_process`), `create/get/list_jobs(limit=20)`, TTL 1 h | `api/exports`, `api/clips`, `api/podcast`, `api/agent`, `queue.py` ; rien sur disque |
| `render.py` | 177 | **entrée de rendu unique** `render_project_to_mp4(job, project, out_path)` : resolve → mediacache → `npx remotion render` → parse « Rendu 340/405 » → `.part.mp4` → remplacement atomique → `probe_mp4` | `api/exports.py` (export unitaire) et `queue.py` (worker) ; écrit `exports/*.mp4` |
| `mediacache.py` | 106 | `write_props()` : copie chaque média `media://id` dans `web/public/media-cache/` **et** `web/dist/media-cache/`, réécriture des refs en `/media-cache/<id><ext>`, production du fichier de props temporaire | `render.py` ; écrit dans `web/public` et `web/dist` |
| `media.py` | 336 | médiathèque : import (`<uuid>.<ext>`), types MIME autorisés (image/vidéo, sinon 415), plafond **500 Mo par fichier** (`:74` et `:126`, même plafond dans `folders.py:43`), service borné, empreinte sha256 pour la déduplication, provenance `media/provenance/<id>.json` | `api/media_routes.py`, `api/studio.py`, `folders.py`, `agent/tools.py` ; écrit `media/` |
| `csv_source.py` | 187 | lecture tolérante : sniff des séparateurs `;` `,` tabulation `\|`, encodages `utf-8-sig` → `utf-8` → `cp1252`, en-têtes obligatoires, `MAX_ROWS = 2000`, lignes raggées signalées, aperçu 5 lignes | `api/batch.py` ; écrit `batch/csvs/<id>.json` |
| `folders.py` | 310 | dossiers connectés : enregistrement d'un chemin absolu (racine de lecteur refusée), types `video\|audio\|image\|tout`, scan avec déduplication par empreinte, inventaire par type | `api/folders.py`, `batch.py`, `agent/tools.py` ; écrit `batch/folders.json` + importe dans `media/` |
| `queue.py` | 580 | file SQLite WAL : schéma `batches`/`items`, `start_batch`, worker thread, progression, `cancel`, `retry_failed`, `recover`, `list_batches`, `get_batch(items=)`, `write_manifest` | `api/batch.py` ; écrit `batch/queue.sqlite3`, `exports/*.mp4`, `batch/manifests/*` |
| `library.py` | 211 | modèles de la bibliothèque : lecture de `models/*.json` + modèles intégrés, contrôle `version: 2` et `model.id` connu, sauvegarde d'un projet comme modèle, retrait (intégrés protégés) | `api/library.py`, `api/studio.py`, `agent/tools.py` ; écrit `models/*.json` |
| `brands.py` | 144 | **packs de marque client** : `list_brands`, `get_pack`, `save_brand`, `delete_brand`, `apply_to_project` (retourne le projet patché, **sans l'écrire**), `capture_from_project`. Normalise via `shortvideos.branding` (erreurs bloquantes, avertissements remontés) | `api/brands.py` ; écrit `brands/<id>.json` |
| `delivery.py` | 253 | **paquet ZIP d'un lot** : `status(batch_id)` (vue page Livraison), `publish_of(project)` (ne recopie que `title` / `description` / `hashtags` non vides), `build_package(batch_id, job)` (monte `videos/`, `subtitles/*.srt`, `thumbnails/*.png`, `metadata/*.json`, `manifeste.{json,csv}`, `LISEZ-MOI.txt` ; écriture `.part.zip` puis remplacement atomique, verrou « un seul paquet par lot »), `package_path` | `api/delivery.py` (dans un `Job`) ; écrit `batch/deliveries/<id>-<nom>.zip` + son `.package.json` |
| `moments.py` | 487 | **analyses de moments forts** : `providers_state()` (voies réellement ouvertes + raison écrite), `resolve_source()` (`media://` uniquement), `analyze_create_job()` (transcription → énergie → détection dans un `Job`, **rien d'écrit avant la fin**, WAV supprimé après mesure), `list_analyses` / `get_analysis` / `recompute` (détection seule, **aucun nouvel appel ASR**) / `delete_analysis`, et `generate_project()` — **le seul chemin qui écrit dans `projects/`** : extrait vocal + miniature importés en `media://`, projet validé (**invalide ⇒ 400, rien d'écrit**), `.srt` frère, **409** si le nom existe sans `overwrite` | `api/moments.py` ; écrit `moments/<id>.json`, `moments/work/<id>/energy.json`, et sur clic `projects/<nom>.json` + `.srt`, `media/*` |
| `skills.py` | 277 | paquet de connaissances : catalogue, lecture d'un document, `build_context()`, relecture de `web/package.json` pour injecter « ETAT DU PROJET » | `api/skills.py`, `agent/context.py`, `agent/retrieval.py` ; lit `skills/remotion/` |

### 4.4 `server/api/` — les 16 routeurs (2 538 lignes, hors `__init__.py`)

| Fichier | Lig. | Préfixe | Routes | Particularité |
| --- | --- | --- | --- | --- |
| `agent.py` | 209 | `/api/agent` | 10 | `status`, `capabilities`, `index`, `check`, `models`, `search`, `ask`, `proposals/{id}`, `…/accept`, `…/reject` |
| `batch.py` | 291 | `/api/batch` | 16 | `setup`, `fields`, `csv`, `csv/{id}`, `plan`, `line`, `start`, liste, détail, `start/{id}`, `cancel`, `retry`, `manifest`, `manifest/file`, `file?position=`, `DELETE` |
| `brands.py` | 72 | `/api/brands` | 6 | liste, `GET /{id}`, POST (enregistrer), `/capture` (pack depuis un projet), `POST /{id}/apply` (**renvoie le projet patché, n'écrit jamais**), `DELETE /{id}` ; ids bornés (`/ \ . :` refusés) |
| `clips.py` | 526 | `/api/clips` | 8 | sessions dans `CLIPS_DIR / sid` avec `assert_local_dir` + `safe_name` ; service `/files/{sid}/{name}` |
| `delivery.py` | 54 | `/api/delivery` | 3 | `GET /{batch_id}` (état), `POST /{batch_id}/package` (lance l'assemblage dans un job, 409 si déjà en cours, 400 si aucune vidéo), `GET /{batch_id}/package/file` (téléchargement, nom retrouvé serveur) ; id vérifié alphanumérique |
| `exports.py` | 128 | `/api/exports` | 4 | POST = job + sous-processus ; 409 si le fichier existe ; `/cancel` ; `/file` borné à `exports/` |
| `folders.py` | 100 | `/api/folders` | 6 | GET liste, `/assets`, POST, `/{id}/scan`, `/{id}`, DELETE |
| `jobs.py` | 24 | `/api/jobs` | 2 | `GET /{id}` (suivi générique), `POST /{id}/cancel` |
| `library.py` | 50 | `/api/library` | 4 | liste, `GET /{id}`, POST (enregistrer), DELETE (perso uniquement) |
| `media_routes.py` | 42 | `/api/media` | 2 | `POST /upload`, `GET /{id}` |
| `moments.py` | 124 | `/api/moments` | 7 | `GET ""` (analyses), `GET /providers`, `POST /analyze` (**renvoie un `job_id`**), `GET /{id}`, `POST /{id}/recompute`, `POST /{id}/generate` (**seul écrivain de projet**), `DELETE /{id}` ; id d'analyse alphanumérique, id de moment alphanumérique + `-`/`_` |
| `podcast.py` | 293 | `/api/podcast` | 6 | `stats`, `clips`, `videos`, `generate`, `legacy/import`, `files/{rel_path}` |
| `projects.py` | 101 | `/api/projects` | 5 | liste, POST (nom borné), `GET/{name}` (migration v1 automatique), DELETE, `POST /validate` |
| `settings.py` | 278 | `/api/settings` | 2 | `GET ""` ne renvoie **jamais** une clé (uniquement des booléens et l'état public) et porte le bloc **`asr`** (`public_asr()` : fournisseur, modèles Whisper, langue, `groq_key_configured`, voies disponibles + raison, `local_backend`) ; `POST ""` applique la liste blanche de clés, dont `AsrSettings` (clé dédiée, effacement explicite, modèle Groq vérifié) |
| `skills.py` | 45 | `/api/skills` | 4 | catalogue, `context`, `doc/{chemin}`, `/{id}` ; lecture seule bornée à `skills/remotion/` |
| `studio.py` | 201 | `/api/studio` | 9 | `effects` (**le catalogue des effets, renvoyé par `effects.manifest()` de `shortvideos/effects.py` — la même liste pour l'éditeur et pour l'assistant**), `models`, `fonts`, `default`, `prepare` (**le même objet pour le Player et le rendu**), `upgrade`, `provenance`, `provenance/{id}`, `inspect` |

### 4.5 `server/agent/` — l'assistant (3 789 lignes)

| Fichier | Lig. | Ce qu'il fait réellement | Entrées / sorties |
| --- | --- | --- | --- |
| `llm_client.py` | 456 | client **OpenAI-compatible** en `httpx` : `chat(messages, …)` avec streaming optionnel, `check_connection()`, `list_models()`, `endpoint_of()`, `_headers()` (clé + `X-PIN`), `CHARS_PER_TOKEN = 3` pour l'estimation, `ChatResult(text, model, latency_ms, tokens)` | lit les réglages serveur ; **aucun** écrit |
| `capabilities.py` | 467 | construit le **manifeste des capacités réelles** depuis le registre de compositions, la bibliothèque, `schema.py`, `effects.py` (**les 25 effets du catalogue, `_effects_brief()` / `_effects_lines()`**), `fontCatalog.json`, `web/package.json` ; `prompt_block()`, `compact_prompt_block()`, `production_prompt_block()` | lit le disque et les modules ; renvoie des chaînes bornées |
| `retrieval.py` | 563 | index FTS5 `knowledge/agent_index.sqlite3` : `split_sections()`, `_fold()` (retrait des accents pour la recherche), tables `docs`/`chunks`/`chunks_fts`/`meta`, `build()`, `search()`, 110 documents / 548 sections | **écrit** `knowledge/agent_index.sqlite3` |
| `context.py` | 421 | assemblage du **prompt borné** : rôle, interdits, manifeste, protocole JSON, contexte (projet réssumé ou colonnes CSV), documents ; troncature json → outline → compact ; `PROTOCOL` décrit le contrat de réponse | appelle `capabilities`, `retrieval` |
| `proposals.py` | 837 | **contrat** : parsing de la réponse, validation typée (`project_patch`, `project_new`, `library_save`, `batch_plan`, `knowledge_answer`, `none`), liste blanche de clés, **`set_effects` borné au catalogue `shortvideos/effects.py`**, `state` = ok/warning/error, révision, détection de conflit (le projet a bougé), `accept()` | registre en mémoire TTL 1 h |
| `tools.py` | 566 | 20 outils de lecture (`READ_TOOLS`), 6 outils de proposition, 4 outils « exécutables uniquement par l'utilisateur » ; `describe()`, `execute(name, args, ctx)` avec bornes (`MAX_SEARCH_RESULTS=8`, `MAX_ASSETS=60`, `MAX_ROWS_PREVIEW=12`, `MAX_TEMPLATE_CHARS=12 000`) | lit les modules serveur ; **n'écrit jamais** (sauf `scan_media_folder`, explicitement demandé) |
| `service.py` | 468 | orchestration en 6 étapes d'un `Job` : contexte → appel → outil ou contrat → réparation (×2) → validation → proposition ; self-heal ×0.65 du budget si le contexte était trop gros (`KIND_CONTEXT`) ; `RECORD_TTL = 3600`, `_MANIFEST_TTL = 30` | `api/agent.py` ; écrit dans `knowledge/` via retrieval |

### 4.6 `shortvideos/` — moteur métier (5 183 lignes, hors `__init__.py`)

| Fichier | Lig. | Rôle | Consommé par |
| --- | --- | --- | --- |
| `schema.py` | 547 | **format v2** : `MODELS = {"quote_cinematic": 1, "quote_vertical": 1}`, enums (`ANIM_IN`, `ANIM_OUT`, `UNITS`, `EASINGS`, `BACKGROUND_FIT`, `ALIGNMENTS`…), gabarit par modèle, `layer()` / `image_layer()` / `scene()` acceptent un argument `effects` et **créent toujours la clé `effects: []`**, `upgrade_v1_to_v2()` explicite | `resolve`, `validation`, `batch`, `library`, `agent/proposals` |
| `effects.py` | 747 | **catalogue normatif des 25 effets** : `CATEGORIES` (7), `SCOPES` (`layer` · `scene` · `overlay`), `TARGETS`, `PARAM_TYPES`, `MAX_EFFECTS_PER_TARGET = 4`, une fiche `_fx(...)` par effet (id, label, portée(s), cible(s), `params` typés et bornés, `needs_audio`, description, note), `manifest()` / `all_effects()` / `ids()` / `get()` / `default_params()`, et surtout **`normalize()`** — une seule implémentation de la norme, partagée par la validation et par la résolution (§6.4) | `resolve.py`, `validation.py`, `api/studio.py`, `agent/capabilities.py`, `agent/proposals.py`, `agent/tools.py`, `tests/test_effects.py` |
| `resolve.py` | 253 | projet édité → bloc `resolved` : frames absolues par calque (`start_frame`, `in_end_frame`, `spread_frames`, `units`, `hold_frames`, `out_start_frame`, `end_frame`), normalisation des volumes, audio (bouclage, fondus en frames), propagation de la graine, et **effets normalisés** par scène (`effects`, portée `scene` ou `overlay`) et par calque (`effects`, portée `layer`), plafonnés à 4 | `render.py`, `api/studio.py`, `batch.py`, `agent` |
| `validation.py` | 473 | **erreurs bloquantes + avertissements**, v1 et v2 : texte long, débordement, média manquant, licence inconnue, bornes de champ, **effets inconnus / hors portée / réglages hors bornes** (via `effects.normalize`) | `api/projects`, `api/studio`, `agent/proposals`, `ShortVideosPage` |
| `batch.py` | 607 | `POLICY`, `fillable_fields()` (18 champs pour Citation cinématique), `suggest_mapping()`, `build_plan()` — rotation, passes, cycle, diagnostics, noms `%03d-<slug>.mp4` | `api/batch.py`, `queue.py`, `agent/tools.py` |
| `delivery.py` | 220 | **sous-titres et miniatures sans moteur ajouté** : `srt_cues()` / `srt_from_project()` croisent les fenêtres **réellement rendues** (`resolve()`) avec le texte des calques visibles (scènes/calques masqués ignorés, signature exclue), SRT tout-CRLF ; `make_thumbnail()` extrait une frame PNG via l'ffmpeg d'`imageio_ffmpeg`, **ne lève jamais** (une miniature ratée remonte un avertissement) | `server/delivery.py`, `tests/test_delivery.py` |
| `branding.py` | 222 | **pack de marque client** : `normalize()` (mêmes disciplines que le catalogue d'effets — chemin/URL refusés, couleur/police hors catalogue = erreur, volume borné = avertissement, clef inconnue = ignorée), `from_project()` (ne prend que les clefs existantes), `apply_brand()` (écrit uniquement dans `theme` / `content.signature` / `audio`, ne touche ni scènes ni modèle, avertit sans surprendre) | `server/brands.py`, `tests/test_branding.py` |
| `asr.py` | 553 | **transcription réelle, aucune dépendance ajoutée** : `extract_audio()` (FFmpeg embarqué → WAV **16 kHz mono 16 bits**), `energy_curve()` (RMS mesuré par fenêtres de 50 ms), `split_points()` (découpe **sur les silences**, `SILENCE_RMS = 0.012`, morceaux ≤ 7 min pour rester sous la limite Groq), `cut_wav()`, `local_backend()` (**détecte** whisper.cpp / `faster_whisper`, n'installe rien), `providers()`, `transcribe_groq()` (`verbose_json`, temps **décalés de la position du morceau**), `transcribe_local()`, `transcribe(provider="auto")`, `normalize_segments()`, `parse_srt()`, `transcript_text()`. Ne renvoie que ce que le modèle a entendu : **aucun texte ni temps inventé** | `server/moments.py`, `server/api/settings.py`, `tests/test_asr.py` |
| `moments.py` | 480 | **détection déterministe** : `detect()` (fenêtres candidates ancrées sur les segments, sélection gloutonne sur le score, chevauchement refusé au-delà de `OVERLAP_TOLERANCE = 0.3`, `top` retenu puis trié par position), `score_window()` → `(score 0–100, reasons)` où **chaque point est expliqué** (densité de parole 22/8, silence de fin 20, silence de tête 12, ponctuation forte 10, marqueurs ≤ 30, énergie 14/5, durée 12/6), `captions()` / `wrap_caption()` (46 caractères, 2 lignes), `keywords()`, `title_from()`, `description_from()`, `hashtags_from()`, `metadata_from()`. Bornes : `MIN_SECONDS = 10`, `MAX_SECONDS = 45`, `TOP_DEFAULT = 6` | `server/moments.py`, `moment_project.py`, `tests/test_moments.py` |
| `moment_project.py` | 256 | **moment → projet v2 complet** : `caption_timeline()` (frame 0 = début du moment, une scène par cue, fenêtres d'animation calculées dans la place disponible), `scenes_from_specs()`, `project_name()` (`moment-<position:02d>-<slug>`, slug ≤ 42), `generate()` qui assemble `content.scenes`, `theme`, `audio.voice`, `export` (1080×1920 / 30 fps) et le bloc **`publish`** (titre, description, hashtags + clés de calcul), applique le pack via `branding.apply_brand()` puis **valide** (`validation.validate_project_v2`) et renvoie `errors` / `warnings` sans rien écrire | `server/moments.py:generate_project`, `tests/test_moment_project.py` |
| `project.py` | 108 | modèle v1 + chargement/sauvegarde + `snapshot` figé | routes projets, tests |
| `fonts.py` | 79 | lit `web/src/remotion/fontCatalog.json` (même fichier que le frontend) | `resolve`, `validation`, `api/studio`, `agent/capabilities` |
| `timing.py` | 82 | durées, fondus, glissements, zoom — fonctions pures sans I/O (héritage v1) | `render.py`, `tests/test_timing.py` |
| `render.py` | 306 | `compose_frame` / `measure_text` (Pillow) : mesure de débordement v1 et tests. **Plus moteur de production.** | `validation.py`, `tests/test_export_short.py` |
| `exporter.py` | 175 | export MP4 Pillow+FFmpeg de la chaîne v1, conservé pour les tests | `tests/test_export_short.py` |
| `probe.py` | 74 | vérification d'un MP4 **sans ffprobe** : OpenCV pour dimensions/fps/frames/1ʳᵉ image, `ffmpeg -i` en secours | `server/render.py`, `queue.py` |
| `PROJECT_FORMAT.md` | — | spécification du format de projet, **lue en dur** par `agent/retrieval.CONTRACT_FILES` (donc gardée dans un fichier séparé) | index de l'agent |

### 4.7 `web/` — frontend (14 667 lignes de `.ts`/`.tsx` + CSS, hors `fontCatalog.json` 73 l.)

Racine : `package.json` (dépendances, `build = tsc --noEmit && vite build`),
`vite.config.ts` (proxy `/api` → 8000), `tsconfig.json` (`strict`, `noUnusedLocals`),
`tailwind.config.ts`, `index.html`.

`web/public/` : `fonts/` (5 familles TTF, 10 poids, `licenses/*/OFL.txt`) et `media-cache/`
(copies locales servies sous `/media-cache/…` par Vite puis par FastAPI).
`web/dist/` : build servi à la racine par le serveur (même origine, donc pas de CORS).

| Fichier | Lig. | Rôle |
| --- | --- | --- |
| `src/main.tsx` | 13 | `createRoot`, `BrowserRouter` |
| `src/App.tsx` | 145 | **coquille de l'application** : `<AssistantProvider>` → `Shell` = `Sidebar` (layout des `NAV_GROUPS`) + `<Routes>` (11 pages, `*` → Cockpit) + **`<AssistantDock />`** + **`<CommandPalette />`** ; c'est ici que `Ctrl+K` / `Ctrl+I` / `Ctrl+/` sont écoutés |
| `src/index.css` | 58 | thème sombre + helpers `.panel`, `.panel-title`, `.input-base`, `.field-label` |
| `src/api/client.ts` | 1 089 | **contrat HTTP typé** de toutes les routes : `Project`, `PrepareResponse`, `Proposal`, `AgentStatus`, `LlmPublic`, `BatchPlan`, `Folder`, `SettingsPublic`, `EffectsManifest` / `EffectSpec` / `EffectParamSpec` + `api.studioEffects()`, **`DeliveryStatus`** (batch, `total`, `rendered`, `is_packaging`, `package` = fichier / octets / `videos` / `subtitles` / `thumbnails` / `warnings` / date, et le tableau `items` position · nom · fichier · statut · durée · octets · `rendered`) et **`BrandPackData` / `BrandPackSummary`** (thème, signature, audio, modèles autorisés) + `api.deliveryStatus()` / `deliveryPackage()` / `deliveryPackageUrl()` / `brandList()` / `brandGet()` / `brandSave()` / `brandDelete()` / `brandApply()` / `brandCapture()`… + **les types des moments forts** (`AsrProviderState`, `AsrLocalBackend`, `AsrPublic` / `AsrPayload`, `MomentsSetup`, `MomentCue`, `MomentItem`, `MomentTimelineSpec`, `AnalysisSummary` / `AnalysisRecord`, `MomentPublishBlock`, `MomentGenerateResult`) et `api.momentsSetup()` / `momentsList()` / `momentsAnalysis()` / `momentsAnalyze()` / `momentsRecompute()` / `momentsGenerate()` / `momentsDelete()` + `apiErrorMessage()` |
| `src/lib/navigation.ts` | 122 | **source de vérité de la navigation** : `NAV_GROUPS` (Pilotage / Automatisation / Sources / Système), 10 entrées `{to, label, icon, description}` — dont `/delivery` **Livraison** dans Automatisation ; lu par `App` **et** par la palette |
| `src/lib/assistant.tsx` | 172 | `AssistantProvider` : conversation **unique et persistante** (ouverture, contexte, demande en vol) + `usePublishAssistant(ctx, handlers)` — la page montée publie son contexte (`project`, `selection`, `mode`, `csvColumns`) et ses gestionnaires (`onApply`, `onLibrarySave`, `onBatchPlan`, `notify`) ; `ask(text)` ouvre le tiroir et lance la demande ; le démontage **dépublie** (`publish({}, {})`), donc plus aucun bouton « Appliquer » ne peut viser un éditeur déjà parti. Ouverture mémorisée dans `localStorage["studio.assistant.open"]`, tolérante si le stockage est indisponible |
| `src/lib/jobs.ts` | 99 | `call()` (fetch + erreur typée `HttpError`), `useJobPolling()`, `cancelJob()`, `formatBytes()`, `formatDuration()` |
| `src/lib/utils.ts` | 6 | `cn()` = clsx + tailwind-merge |
| `src/components/AssistantDock.tsx` | 134 | **tiroir global de l'assistant** : colonne de 400 px (pas un overlay) ; fermé il laisse un **rail de 26 px** cliquable ; l'`AgentPanel` y reste **monté** quand il est fermé, donc la conversation et le job en cours survivent ; intitulé de contexte (`Design · citation · scène s1 · calque hook…`, `Production · lot · …`) ; bandeau `applyHint` quand la page ouverte ne peut pas appliquer ; `Échap` ferme ; passe `visible={open}` (statut relu à chaque ouverture) et `onConfigure` (ferme le tiroir et va au Cockpit) |
| `src/components/SetupAssistant.tsx` | 391 | **configuration guidée de l'assistant** (premier lancement), affichée par le Cockpit tant que `status.ready` est faux : 3 étapes — fournisseur (local / Gemini / Groq, avertissement cloud), connexion (URL + presets locaux ou clé), modèle (`Lister les modèles` → `POST /api/agent/models`, `Tester la connexion` → `POST /api/agent/check`) puis **« Activer l'assistant »** → `POST /api/settings` avec `enabled: true`. Pré-rempli depuis `GET /api/settings` (les clés ne reviennent jamais, seul leur état) ; le bouton « Demander » du Cockpit est désactivé tant que ce n'est pas activé ; une fois prêt, le Cockpit recharge le statut et le panneau disparaît |
| `src/components/CommandPalette.tsx` | 211 | palette `Ctrl+K` : recherche sur `label + detail + group`, 4 groupes (navigation, Assistant, Projets, Bibliothèque), flèches + `Entrée`, `Échap`, remise à zéro de la requête à l'ouverture |
| `src/components/job-status.tsx` | 92 | `JobStatus` (barre + message + bouton Annuler) et `ErrorNote` (traceback replié) |
| `src/components/ui/*.tsx` | 7 fichiers, 15–37 | `button`, `badge`, `input`, `label`, `progress`, `slider`, `switch` (Radix + cva) |
| `src/components/agent/AgentPanel.tsx` | 376 | cœur de l'assistant : saisie, `mode` design/production, job pollé, tools observés, carte de proposition, accept/reject/correct, sources. Props `externalRequest` (une page peut pré-remplir et lancer une demande, utilisé par le Cockpit et la palette), `applyHint`, `visible` (statut de l'assistant relu à chaque ouverture du tiroir) et `onConfigure` (bouton « Configurer l'assistant » du bandeau non configuré) |
| `src/components/agent/ProposalCard.tsx` | 187 | rendu d'une proposition : résumé, **diff des opérations — dont `set_effects`**, warnings, état de validation, bouton d'acceptation (**label adapté au mode**) |
| `src/components/agent/SourcesPanel.tsx` | 156 | recherche dans l'index (`/api/agent/search`) et relecture des sections citées |
| `src/pages/CockpitPage.tsx` | 500 | **page d'accueil `/`** : hero de demande à l'assistant (`ask(text)`), 4 exemples cliquables, cartes *Effets* (25, 7 catégories, chaque catégorie envoie une question à l'assistant), *File de production*, *Derniers projets*, *Modèles*, *Points de contrôle*, *Aller plus vite*. **Configuration guidée** (`SetupAssistant`) affichée en tête tant que l'assistant n'est pas prêt ; « Demander » est alors désactivé. **Une carte n'affiche que des données réellement reçues** : si l'appel échoue, la carte affiche l'erreur — jamais un nombre inventé |
| `src/pages/DesignPage.tsx` | 782 | l'éditeur v2 : barre d'outils (dont les boutons **Assistant** et **Packs**), scènes, Player, **Inspecteur seul dans la 3ᵉ colonne** (l'onglet « Assistant IA » a disparu : le tiroir global s'est substitué au panneau intégré), dialogues Ouvrir / Export / Bibliothèque / **Packs de marque** ; le bouton « Appliquer » d'un pack passe par `applyEdit(patched, true)`, donc **une marque appliquée s'annule et s'autosauvegarde comme n'importe quel réglage** ; publie son contexte via `usePublishAssistant` |
| `src/pages/design/panels.tsx` | 1117 | `InspectorPanel`, `ScenesPanel`, `TimelineBar`, les `<Section>` de réglage et **`EffectsSection`** : sélecteur groupé par catégorie, compteur `n/4`, réglages bornés (slider / nombre / booléen / couleur / select / texte), badges `audio requis` / `audio réel`, bouton « appliquer à toutes les scènes », message d'erreur explicite si un id n'est plus au catalogue |
| `src/pages/design/edit.ts` | 246 | manipulation **pure** du projet + undo/redo (`updateScene`, `updateLayer`, `updateLayerPart`, `addScene`, `duplicateScene`, `moveLayer`, `toggleLayer`, `durations`…) ; les effets passent par les mêmes `update…` avec `patch = { effects: [...] }`, donc **un changement d'effet est annulable comme n'importe quel réglage** |
| `src/pages/design/measure.ts` | 121 | `host()` et `measureTextLayer()` : mesure du débordement dans le navigateur **avec la police réelle** |
| `src/pages/design/ExportDialog.tsx` | 169 | nom, progression réelle, annulation, résultat (dimensions/durée/taille), 409 → « Remplacer » |
| `src/pages/design/LibraryDialog.tsx` | 110 | nom + description d'un nouveau modèle, refus serveur si le projet est invalide |
| `src/pages/design/BrandPacksDialog.tsx` | 201 | **packs de marque client** : liste des packs (`brands/*.json`), « Créer depuis ce projet » (`api.brandCapture`), « Appliquer au projet » (`api.brandApply` → `onApply(res.project)`, **le serveur ne touche jamais le projet ouvert**), suppression, et affichage des `warnings` serveur (« la signature est désactivée », « modèle hors liste ») en `text-warning` |
| `src/pages/ProductionPage.tsx` | 1189 | les 7 sections du lot + historique ; le panneau assistant intégré est **remplacé** par le tiroir global (bouton « Aider avec l'IA » → `setOpen(true)`) et une note d'application du plan |
| `src/pages/LivraisonPage.tsx` | 242 | **page `/delivery`** : sélecteur de lot (les lots réellement en file), état du paquet (`api.deliveryStatus`), bouton **« Préparer le paquet »** → job pollé par `useJobPolling` puis relecture du statut, `<JobStatus>` avec progression et annulation, carte **« Paquet prêt »** (taille, date, nombre de vidéos / sous-titres / miniatures, avertissements) avec lien de téléchargement direct `api.deliveryPackageUrl()`, et tableau des lignes du lot (position, nom, statut, durée, taille, rendu ou non). **Aucun paquet n'est annoncé s'il n'existe pas sur disque** : `package == null` affiche l'état vide, pas une taille inventée |
| `src/pages/LibraryPage.tsx` | 158 | cartes des modèles, « Utiliser ce modèle », « Retirer », consigne d'ajout manuel |
| `src/pages/ProjectsPage.tsx` | 113 | liste `projects/*.json`, Ouvrir / Supprimer, état vide |
| `src/pages/SettingsPage.tsx` | 588 | clé Groq de Clips, panneau Assistant IA (fournisseur, modèles, paramètres, test), manifeste des capacités |
| `src/pages/ClipsPage.tsx` | 561 | étapes Source / Analyse Groq / Extraction + transcription, clips détectés, clips produits |
| `src/pages/PodcastPage.tsx` | 514 | base de phrases, ajout d'une vidéo, catalogue, génération d'une vidéo |
| `src/pages/ShortVideosPage.tsx` | 838 | éditeur v1 à une scène, export direct |
| `src/remotion/registry.tsx` | 77 | `MODEL_REGISTRY` : id de composition → composant, **partagé Player et CLI** |
| `src/remotion/QuoteCinematic.tsx` | 562 | modèle v2 : 3 scènes, fonds image/vidéo, calques animés **+ effets de calque/scene/overlay**, mix `<Audio>` musique + voix |
| `src/remotion/QuoteVertical.tsx` | 224 | composition v1 historique |
| `src/remotion/animations.ts` | 146 | implémentation des entrées/sorties (`fade`, `slide_up`, `mask_reveal`, `scale`, ressorts) |
| `src/remotion/effects/registry.ts` | 84 | **liste des ids réellement rendus** : `LAYER_EFFECT_IDS` (10), `IMAGE_EFFECT_IDS` (1), `SCENE_EFFECT_IDS` (6), `OVERLAY_EFFECT_IDS` (10), réunis sans doublon dans `IMPLEMENTED_EFFECT_IDS` — **25 identifiants distincts**, car `chromatic_aberration` et `glitch_slices` existent en calque **et** en scène. `tests/test_effects.py` compare cette liste aux 25 ids du catalogue serveur : un effet déclaré sans rendu, ou rendu sans être au catalogue, **casse les tests**. `hasEffect` / `findEffect` / `needsMeasuredAudio` |
| `src/remotion/effects/common.ts` | 142 | types `Effect` / `EffectHost`, lecture des `params` avec valeurs par défaut, helpers partagés (masques, durées en frames, graine) |
| `src/remotion/effects/layer.tsx` | 393 | `applyLayerEffects` : `spring_pop`, `kinetic_letters`, `flip_card`, `chromatic_aberration`, `glitch_slices`, `parallax_depth`, `cylinder_wrap`, `sphere_wrap`, `audio_pulse`, `shine` |
| `src/remotion/effects/scene.tsx` | 244 | `SceneEffects` : `perspective_dolly`, `liquid_contours`, `color_grade`, `depth_blur`, `glitch_slices`, `chromatic_aberration` |
| `src/remotion/effects/overlay.tsx` | 596 | `SceneOverlays` plein cadre : `scanlines`, `white_noise`, `light_leak`, `path_trace`, `path_morph` (**`@remotion/paths`** : `normalizePath`, `getLength`, `interpolatePath` — le tracé et le morphing sont calculés à la frame, pas par un paquet externe), `plasma_field` (canvas 2D + `feTurbulence`), `audio_spectrum`, `audio_waveform`, `cursor_tour`, `code_type` (rendu du code **sans `prismjs` ni `shiki`**, non installés : coloration par règles simples sur le texte du projet) |
| `src/remotion/effects/image.tsx` | 184 | `chroma_key` : **canvas 2D** (`willReadFrequently`), les pixels proches de la couleur d'accent deviennent transparents — découpe dans le média lui-même, pas un filtre CSS |
| `src/remotion/effects/audio.tsx` | 77 | accès mesuré à l'audio : `useAudioData()` + `visualizeAudio()` de **`@remotion/media-utils`** (paquet installé), mises en cache par source — les 3 effets réactifs n'ont pas de valeur inventée si la piste est absente, ils sont **signalés « audio requis »** |
| `src/remotion/effects/channels.tsx` | 132 | emballages partagés par les effets qui **dupliquent le contenu** (copies monocanales recomposées en fusion écran pour l'aberration chromatique, tranches pour le glitch) — les mêmes sur un calque de texte, d'image ou une scène entière |
| `src/remotion/fonts.ts` | 128 | `preloadAllFonts()` à partir de `fontCatalog.json` |
| `src/remotion/fontCatalog.json` | 73 | **source unique des polices**, lue aussi par Python (`shortvideos/fonts.py`) |
| `src/remotion/mediaUrl.ts` | 20 | `staticFile()` wrapper pour `/media-cache/…` |
| `src/remotion/types.ts` | 234 | types TypeScript miroirs du schéma v2, **dont `RawEffect = string \| {id, params}`** et `effectId()` — la forme courte et la forme réglée résumées au même identifiant |
| `src/remotion/index.tsx` | 40 | `registerRoot` |

### 4.8 Outillage, connaissances, tests

```
skills\remotion\               ── paquet de connaissances de l'agent (lecture disque seule)
├── PROVENANCE.md                 source, version, méthode d'extraction, état de licence
├── remotion-best-practices\      Agent Skills officiels : routeur + 12 fiches (~1,2 Mo)
├── bible\                        bible française : 7 fiches (~37 Ko)
└── effects\                      guide des effets vidéo : 1 index + 10 fiches (~29 Ko)

tools\
├── extract_bible.py              archive zip -> skills/remotion/bible/ (rejouable)
└── split_effects_guide.py        guide -> skills/remotion/effects/, compare chaque fiche à sa
                                  section d'origine (garantit le verbatim)

tests\
├── conftest.py                   fixtures (client FastAPI de test, projets temporaires)
├── test_api.py                   routes, sécurité (origine, traversal, upload, clé jamais exposée)
├── test_validation.py            16 : validation, chemins avec espaces, bornes, roundtrip JSON
├── test_timing.py                15 : durées, frames, fondus, glissement, zoom
├── test_effects.py               18 : catalogue d'effets + cohérence avec les ids rendus
├── test_export_short.py          8  : export réel + comparaison frame à frame (chaîne v1)
├── test_skills_api.py            paquet de connaissances + bornes de lecture
├── test_folders.py               enregistrement, refus racine de lecteur, scan, déduplication
├── test_batch_plan.py            rotation, passes, cycle, colonnes qui gagnent, blocages
├── test_batch_queue.py           file SQLite, annulation, retry des échecs, recover
├── test_batch_api.py             17 routes de lot, manifeste, service de fichier borné
├── test_agent_flow.py            11 : bout en bout assistant (rien n'est écrit avant acceptation)
├── test_delivery.py              10 : SRT calé sur resolve(), CRLF, signature exclue, miniature
│                                  qui ne lève jamais, assemblage complet d'un ZIP
├── test_branding.py              11 : normalisation d'un pack (chemin/URL/couleur/police/modele),
│                                  volume borné, apply_brand pur, store brands/ (écrit ou bloqué)
├── e2e_export_remotion.py        rendu complet hors interface
└── e2e_cancel_overwrite.py       annulation en cours de rendu + refus d'écrasement
```

---

## 5. Données et persistance

### 5.1 Où écrit l'application

| Chemin | Format | Producteur | Contenu exact |
| --- | --- | --- | --- |
| `projects/<nom>.json` | JSON v1 ou v2 | `api/projects.py` (autosauvegarde du Design) | le projet édité ; jamais le bloc `resolved` |
| `models/<id>.json` | JSON **v2 obligatoire** | `api/library.py` | modèle enregistré ; `version: 2` et `model.id` connu exigés |
| `brands/<id>.json` | JSON `{id, pack, created_at, updated_at}` | `server/brands.py` (bouton « Packs » du Design) | pack de marque client : `pack` porte `label`, `notes`, `theme`, `signature`, `audio` et la liste `models` autorisée ; **le dossier est editable à la main**, un pack illisible apparaît comme `unreadable` dans la liste au lieu d'être chargé |
| `media/<uuid>.<ext>` | binaire | `media.py` (upload, scan de dossier, import d'un projet v1) | média importé, nommé par uuid, empreinte sha256 en base de données mémoire |
| `media/provenance/<uuid>.json` | JSON | `api/studio.py` | `{source, licence, date}` ; licence vide ⇒ affichée `inconnue` |
| `exports/<nom>.mp4` | MP4 H.264 | `render.py`, `queue.py` | livraison ; écriture via `<nom>.mp4.part.mp4` puis remplacement atomique |
| `exports/props-<id>.json` | JSON | `mediacache.py` | fichier de props du rendu en cours ; supprimé dans le `finally` — sa présence signale un rendu actif |
| `web/public/media-cache/` et `web/dist/media-cache/` | copies | `mediacache.py` | mêmes fichiers, pour Vite et pour FastAPI |
| `batch/folders.json` | JSON | `folders.py` | registre des dossiers connectés (chemin, type, licence, nom, date de scan) |
| `batch/csvs/<id>.json` | JSON | `csv_source.py` + `api/batch.py` | colonnes, lignes, aperçu, encodage et séparateur retenus |
| `batch/queue.sqlite3` | SQLite WAL | `queue.py` | lots et lignes, statuts, résultats, tailles |
| `batch/manifests/<id>-<nom>.<json\|csv>` | JSON / CSV (BOM `utf-8-sig`) | `queue.write_manifest()` | fiche de livraison d'un lot |
| `batch/deliveries/<id>-<nom>.zip` | ZIP | `server/delivery.py` (page Livraison) | paquet client : `videos/*.mp4`, `subtitles/*.srt`, `thumbnails/*.png`, `manifeste.json`, `manifeste.csv`, `LISEZ-MOI.txt` ; écriture via `<...>.part.zip` puis remplacement atomique |
| `batch/deliveries/<id>-<nom>.package.json` | JSON | `server/delivery.py` | état du paquet : date de préparation, nombre de vidéos / sous-titres / miniatures, avertissements (miniature ratée, ligne sans média) ; **un paquet sans ce fichier est considéré comme absent** |
| `knowledge/agent_index.sqlite3` | SQLite | `agent/retrieval.py` | index FTS5 des connaissances (110 documents / 548 sections, 1,6 Mo) |
| `server/settings.json` | JSON plat | `settings.py` | `host`, `port`, `groq_api_key` et les 18 clés `llm_*` — **jamais renvoyées au navigateur** |
| `clips/<sid>/` | MP4, SRT, JSON | `api/clips.py` | session : vidéo téléchargée, transcription, clips extraits |
| `downloads/` | binaire | `downloader.py` | téléversements temporaires yt-dlp |
| `podcast_db/` | `catalog.csv` + `output/` | `database.py`, `podcaster.py` | base de phrases et vidéos assemblées |
| `.pytest_tmp/` | dossiers | pytest | forcé par `pytest.ini` (le TMP Windows est refusé sur ce poste) |

**Ce qui n'est jamais persisté** : le bloc `resolved`, les propositions de l'assistant après
TTL d'une heure, les clés d'API dans une réponse HTTP, les candidats non acceptés, l'état du
Player, les logs de réponse LLM.

### 5.2 `batch/queue.sqlite3` — DDL réel

```sql
CREATE TABLE batches (
  id TEXT PRIMARY KEY, name TEXT, model_id TEXT, csv_id TEXT,
  mapping TEXT, options TEXT, status TEXT, overwrite INTEGER,
  output_dir TEXT, total INTEGER,
  created_at TEXT, started_at TEXT, finished_at TEXT, message TEXT);

CREATE TABLE items (
  id TEXT PRIMARY KEY, batch_id TEXT REFERENCES batches(id) ON DELETE CASCADE,
  position INTEGER, name TEXT, filename TEXT,
  project TEXT,          -- projet v2 résolu pour cette ligne (JSON)
  row_preview TEXT, assets TEXT, warnings TEXT, sources TEXT,
  status TEXT,           -- queued | running | done | failed | cancelled | blocked
  error TEXT, output_path TEXT, size_bytes INTEGER,
  frames INTEGER, duration REAL, fps INTEGER,
  attempts INTEGER, started_at TEXT, finished_at TEXT,
  UNIQUE (batch_id, position));
CREATE INDEX items_batch_idx ON items(batch_id, position);
```

Accès en mode WAL, par contexte `_db()` ; un seul lot actif à la fois (second `start` ⇒ 409).

### 5.3 `knowledge/agent_index.sqlite3` — DDL réel

```sql
CREATE TABLE docs (path TEXT PRIMARY KEY, source TEXT, version TEXT, sha TEXT,
                   mtime REAL, chunks INTEGER, updated_at TEXT);
CREATE TABLE chunks (rowid INTEGER PRIMARY KEY, path TEXT, source TEXT, version TEXT,
                     title TEXT, section TEXT, body TEXT, sha TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE chunks_fts USING fts5(title, section, body,
                       tokenize='unicode61 remove_diacritics 2');
```

`meta` porte `built_at` et `fts5 = 1`. La tokenize retire les accents, donc « animasyon »
retrouve « animation ». `_fold()` fait la même Normalisation pour le tri et la recherche
manuelles. Reconstruction à la demande via `POST /api/agent/index`.

---

## 6. Format de projet v2, champ par champ

Spécification normative : `shortvideos/PROJECT_FORMAT.md` (fichier gardé séparé parce que
l'index de l'agent le lit par chemin en dur). Le projet est **l'unique monnaie** échangée
entre l'éditeur, le Player, le rendu et les lots.

```jsonc
{
  "version": 2,
  "model": { "id": "quote_cinematic", "version": 1 },
  "name": "citation-cinematique",
  "content": {
    "scenes": [
      {
        "id": "s1", "label": "Accroche", "duration": 4.0, "hidden": false,
        "effects": [],
        "background": { "media": "media://<uuid>", "fit": "cover",
                        "animation": "zoom_slow", "opacity": 0.55 },
        "layers": [
          {
            "id": "hook", "type": "text", "role": "hook", "enabled": true,
            "text": "…", "emphasis": ["mot1", "mot2"],
            "position": { "x": 0.5, "y": 0.42, "width": 0.86,
                          "align": "center", "direction": "ltr" },
            "style":  { "font_family": "archivo-black", "font_weight": 700,
                        "font_size": 128, "line_height": 1.05,
                        "letter_spacing": -0.02, "color": "#F7F5EF",
                        "accent_color": "#E2B458", "shadow": true,
                        "stroke_width": 2, "stroke_color": "#000000",
                        "opacity": 1.0 },
            "animation": { "in": "slide_up", "out": "fade", "unit": "word",
                           "start_frames": 6, "in_frames": 26, "out_frames": 12,
                           "hold_frames": 30, "distance": 0.045, "stagger": 3,
                           "easing": "spring", "damping": 20, "stiffness": 200,
                           "mass": 1 },
            "effects": [ "kinetic_letters",
                          { "id": "shine", "params": { "width": 0.3 } } ]
          }
        ]
      }
    ],
    "signature": { "text": "…", "handle": "@…", "media": "media://<uuid>",
                   "position": "bottom_right", "start_frames": 0, "in_frames": 18,
                   "font_size": 34, "logo_width": 0.14 }
  },
  "theme": { "font_family": "inter", "palette": { "background": "#0E0D12",
             "surface": "#1A1820", "text": "#F7F5EF", "accent": "#E2B458" } },
  "audio": { "enabled": false, "music": "", "voice": "", "music_volume": 0.3,
             "voice_volume": 1.0, "music_fade_in": 1.0, "music_fade_out": 1.5,
             "markers": [] },
  "variation": { "seed": 1 },
  "export":  { "width": 1080, "height": 1920, "fps": 30,
               "output_dir": "", "filename": "" }
}
```

### 6.1 Règles de format

| Règle | Conséquence vérifiable |
| --- | --- |
| Durées **en secondes**, fenêtres d'animation **en frames** | `resolve.py` multiplie par `export.fps` ; l'éditeur affiche les deux |
| Tout champ média accepte `media://<uuid>` | un chemin Windows dans un projet est une **erreur bloquante** |
| `animation.unit` ∈ `block` · `line` · `word` | le décalage (`stagger`) s'applique aux unités réellement présentes dans le texte |
| Le bloc `resolved` est calculé, jamais stocké | `save()` le retire ; une proposition LLM contenant `resolved` est **rejetée** |
| `MODELS = {"quote_cinematic": 1, "quote_vertical": 1}` | un `model.id` hors registre ⇒ erreur ; la Bibliothèque n'expose que `version: 2` |
| Bornes : scène 0,5–120 s, total 0,5–300 s, `REF_HEIGHT = 1920` | la taille de police est mise à l'échelle `hauteur / 1920` au rendu |

### 6.2 Registres d'énumérations (`shortvideos/schema.py:26-33`)

| Constante | Valeurs |
| --- | --- |
| `ANIM_IN` | `fade` · `slide_up` · `slide_left` · `scale` · `mask_reveal` · `none` |
| `ANIM_OUT` | `none` · `fade` |
| `ANIM_UNITS` | `block` · `line` · `word` |
| `EASINGS` | `linear` · `ease_out_cubic` · `ease_out_quint` · `spring` |
| `BACKGROUND_FIT` | `cover` · `contain` |
| `BACKGROUND_ANIM` | `static` · `zoom_slow` · `zoom_out` |
| `ALIGNMENTS` / `DIRECTIONS` | `left` `center` `right` / `ltr` `rtl` |

Scènes par défaut du modèle cinématique (`schema.new_project("quote_cinematic")`) :
`s1` Accroche (calques `hook`, `caption`), `s2` Citation (`quote`, `author`),
`s3` Signature (`reveal`, `caption`).

### 6.3 Ce que produit `resolve.py` — le bloc `resolved`

Par scène : `start_frame`, `duration_frames`, `end_frame`, `hidden`, `background`
(média, fit, animation, opacité). Par calque :

```
start_frame · in_end_frame · spread_frames · units · hold_frames
out_start_frame · end_frame · duration_frames
+ style résolu : font_family, font_weight, font_size_px (mis à l'échelle),
  line_height, letter_spacing_em, color, accent_color, shadow,
  stroke_width_px, stroke_color, align, direction
```

Plus globalement : `total_frames`, `fps`, `duration`, `width`, `height`, `seed`,
`fonts` (famille connue + poids disponibles), `signature`, `audio`
(`enabled`, volumes normalisés 0..1, fondus convertis en frames), **`effects` normalisés
par scène et par calque (réglages complets, jamais partiels)** et surtout
`assets[]` — la liste `{kind: background|image|music|voice|signature, ref, scene}`
que `mediacache.py` copie et que la validation parcourt pour signaler les licences.

### 6.4 La couche d'effets (`shortvideos/effects.py`)

Un projet peut poser des **effets visuels** sur un calque, sur une scène entière, ou en
**plein cadre par-dessus** la scène. Le catalogue est la **source unique de vérité** :
`shortvideos/effects.py` (747 lignes) les définit une seule fois et tout le monde boit la
même source — la route `GET /api/studio/effects`, l'`EffectsSection` de l'Inspecteur, le
manifeste de capacités de l'assistant (`capabilities._effects_brief()` / `_effects_lines()`)
et son outil de lecture `list_effects` (§9.6), la validation, la résolution et le rendu
Remotion. **Vingt-cinq effets, sept catégories, quatre maximum par cible.**

| Catégorie (`id`) | Effets (id) | Portée(s) | Cible(s) |
| --- | --- | --- | --- |
| `motion` — Motion design et physique | `spring_pop` · `kinetic_letters` · `flip_card` · `path_trace` · `path_morph` | layer (les 3 premiers), overlay (les 2 derniers) | texte et image, sauf `kinetic_letters` **texte seulement** |
| `distort` — Distorsions et glitch | `chromatic_aberration` · `glitch_slices` (layer **et** scene) · `scanlines` · `white_noise` (overlay) | layer / scene / overlay | texte et image |
| `space` — 3D, caméra et espace | `perspective_dolly` (scene) · `parallax_depth` (layer) · `cylinder_wrap` · `sphere_wrap` (layer, **texte**) | scene / layer | selon l'effet |
| `audio` — Réactif à l'audio | `audio_pulse` (layer) · `audio_spectrum` · `audio_waveform` (overlay) — **les trois marqués `needs_audio`** | layer / overlay | texte et image |
| `screen` — Screencast et interface | `cursor_tour` · `code_type` | overlay | texte et image |
| `generative` — Générateur et shaders | `liquid_contours` (scene, via filtre SVG `feTurbulence`) · `plasma_field` (overlay, canvas 2D) | scene / overlay | texte et image |
| `light` — Lumière, couleur et keying | `shine` (layer) · `light_leak` (overlay) · `color_grade` · `depth_blur` (scene) · `chroma_key` (layer, **image uniquement**) | layer / scene / overlay | selon l'effet |

**Forme stockée** (règle identique côté éditeur — `design/panels.tsx:toStoredValue` — et côté
assistant — `proposals._compact_effects`) :

| Écriture | Quand |
| --- | --- |
| `"plasma_field"` | l'effet est gardé **avec tous ses réglages par défaut** : la forme courte évite de figer des nombres dans le JSON |
| `{"id": "shine", "params": {"width": 0.3}}` | dès qu'**un seul** réglage diffère de la valeur par défaut ; les réglages absents restent implicites |

**`effects.normalize()` — la norme, une seule fois** (`shortvideos/effects.py:649`) : appelée
**à la fois** par `shortvideos/validation.py` ( ⇒ erreurs bloquantes) et par
`shortvideos/resolve.py` ( ⇒ le rendu ne reçoit que des valeurs complètes et bornées). Elle est
**tolérante à l'entrée, jamais inventrice** :

| Cas | Comportement |
| --- | --- |
| id absent du catalogue | **erreur** listant les 25 ids disponibles → message réparable pour l'assistant |
| effet posé hors de sa portée (ex. `sphere_wrap` sur une scène) | **erreur** |
| effet posé sur un calque image alors qu'il exige du texte (et inverse) | **erreur** |
| réglage inconnu | **avertissement** (jamais appliqué en silence) |
| réglage hors bornes | **ramené à la borne** + avertissement |
| plus de 4 effets sur la même cible | **erreur** (avec la consigne : retirer ou déplacer sur une autre scène) |
| doublon d'id | **erreur** |
| effet `needs_audio` sans piste audio chargée | **avertissement** « audio requis » ; l'éditeur affiche le badge et le rendu n'invente aucune mesure |

**Le contrat n'a pas été élargi pour autant** : l'assistant écrit les effets **uniquement** par
l'opération `set_effects` (§9.5), le studio n'installe **aucune** dépendance pour eux (les
effets sont rendus en CSS/SVG/canvas natif, `@remotion/paths` et `@remotion/media-utils` —
paquets déjà présents), et `tests/test_effects.py` (18 tests) **compare les ids du catalogue aux
ids réellement implémentés dans `web/src/remotion/effects/registry.ts`** : un effet annoncé sans
rendu, ou rendu hors catalogue, fait échouer les tests.

### 6.5 Ce qui est livrable sans moteur supplémentaire : sous-titres et miniatures

`shortvideos/delivery.py` (220 lignes) produit les deux pièces qu'un client attend dans un
paquet, **sans ajouter une seule dépendance** : le `.srt` est écrit à la main, la miniature
vient du FFmpeg déjà embarqué par `imageio_ffmpeg`.

**Les sous-titres viennent des frames réellement rendues** — c'est le point qui rend le
fichier crédible. `srt_cues(project)` appelle `resolve.resolve(project)` (le même que le
rendu) puis **croise** les fenêtres résolues avec les calques du projet, parce que le texte
reste dans `content` et non dans le bloc `resolved` :

| Règle | Comportement |
| --- | --- |
| scène ou calque `hidden` | **ignoré** — ce qui ne s'affiche pas ne se sous-titre pas |
| calque non `text` | ignoré (une image ou un fond n'est pas une réplique) |
| `content.signature` | **exclue** : un filigrane de marque n'est pas un sous-titre |
| calque sans fenêtre correspondante dans `resolved` | ignoré, aucune time codée au petit bonheur |
| `end_frame <= start_frame` | ramenée à `start + MIN_CUE_FRAMES` (1 frame) : deux bornes identiques font un cue invalide que la plupart des lecteurs rejettent |
| `start_frame >= total_frames` | cue supprimé |
| texte du calque | indentation retirée, lignes vides de tête et de queue retirées, **les vides du corps sont gardées** (elles portent le vers) |

Sorties : `srt_cues()` → liste `{index, scene_id, layer_id, start_frame, end_frame, start, end,
text}` triée par frame d'entrée puis re-numérotée ; `srt_from_project()` → le fichier texte
`index ␤ HH:MM:SS,mmm --> HH:MM:SS,mmm ␤ texte`, **entièrement en CRLF** (mélanger LF et CRLF
se lit mal selon le lecteur), chaîne vide si rien n'est sous-titrable — et une chaîne vide
devient un avertissement dans le paquet, jamais un fichier de 0 octet.

**La miniature** (`make_thumbnail`) est la frame à `ratio` (45 % par défaut, plafonné à
`durée − 0,04 s`) extraite par `<ffmpeg> -ss <t> -i <mp4> -frames:v 1`, écrite en
`<out>.part.png` puis remplacée. La fonction **ne lève jamais** : vidéo absente, sonde en
échec, durée inconnue, FFmpeg indisponible ou code retour non nul renvoient
`{path: "", warning: "…"}`, et le paquet est seulement amputé de cette image.

**Ce que la tranche ne fait pas** : pas de reconnaissance vocale. Les sous-titres décrivent
le texte **affiché à l'écran** par le projet v2, pas la voix d'une source externe — voir
[§16. Limites connues](#16-limites-connues).

### 6.6 Les packs de marque client

Un pack de marque répond à « ce client-là doit retrouver ses couleurs, son logo et sa
musique d'une vidéo à l'autre ». `shortvideos/branding.py` (222 lignes) n'ajoute **aucune clé
au format de projet** : il n'écrit que dans `theme`, `content.signature`, `audio` et la liste
des `models` autorisés, donc un projet passé par un pack reste validable par
`validation.validate_project`.

| Clé du pack | Contrôle | En cas de problème |
| --- | --- | --- |
| `label` / `notes` | nom de client **obligatoire** ; `label` tronqué à 80 caractères, `notes` à 600 | label vide → **erreur** ; label tronqué → **avertissement** |
| `theme.*`, `signature.*` | clés connues du schéma (`default_theme()` / `default_signature()`) | **clé inconnue → avertissement**, jamais stockée |
| valeur de couleur (`*_color`, `color`) | regex `^#[0-9A-Fa-f]{6}$` | **erreur** « couleur illisible » |
| valeur de police (`*_family`) | `fonts.known_family()` du catalogue sous licence | **erreur** « police absente du catalogue » |
| `signature.media` / `audio.music` | **`media://<id>` uniquement** (`MEDIA_REF`, 4 à 64 caractères d'identifiant) | **erreur** « un chemin ou une URL ne sont pas acceptés, choisissez un media du studio » |
| `position` | objet `{x, y}` numérique | erreur si ce n'est pas un objet |
| `audio.enabled` / `audio.music_volume` | booléen ; nombre **borné 0 à 1**, arrondi au millième | **avertissement** « volume ramené à … » quand la valeur est corrigée ; volume non numérique → erreur |
| `models` | identités connues du registre | id hors liste → **erreur** |

`apply_brand(project, pack)` est **pur** : il part de `schema.clone(project)`, retire le bloc
`resolved`, renvoie `(projet patché, avertissements)` et n'écrit dans aucun fichier. Ni les
scènes ni les calques ne bougent, et **le modèle du projet n'est jamais remplacé** : si le
projet utilise un modèle absent de la liste autorisée du pack, c'est un avertissement
(« il reste appliqué, changez de modèle si le client l'impose »), pas une surprise. Trois
incohérences sont annoncées plutôt que laissées silencieuses — un logo imposé sur un projet
dont la signature est désactivée, une musique imposée alors que `audio.enabled` reste faux,
et ce modèle hors liste. Si le pack force `signature.enabled = true`, le projet la **réactive**
(cas verrouillé par un test).

Le principe « l'assistant propose, l'utilisateur applique » vaut ici comme pour l'IA :
`POST /api/brands/{id}/apply` renvoie le projet patché au navigateur, qui le pousse dans
`applyEdit(patched, true)` — donc **undo/redo et autosauvegarde s'appliquent**, et le serveur
n'a jamais touché `projects/*.json` de son propre chef.

---

## 7. La chaîne de rendu, pas à pas

```
[1] projet édité (useState dans DesignPage)
      │  POST /api/studio/prepare
[2] shortvideos/resolve  ──> bloc `resolved`
      │  shortvideos/validation ──> erreurs bloquantes / avertissements
      │  fonts.preloadAllFonts() attendue AVANT toute mesure et tout rendu
[3] mediacache.write_props()  ──> copie des médias dans web/public ET web/dist,
      │                            refs réécrites /media-cache/<uuid><ext>,
      │                            fichier exports/props-<id>.json
[4] deux consommateurs du MÊME objet :
      ├─ Remotion Player (aperçu, web/src/remotion/registry.tsx)
      └─ sous-processus : npx remotion render <entry> <composition> <sortie>
                            --props=… --codec=h264
[5] stdout « Rendu 340/405 » ──> job.set_progress(fraction, message)
      │  job.cancel_event ──> _terminate(proc) ──> JobCancelled ──> nettoyage .part
[6] <sortie>.part.mp4 ──> remplacement atomique ──> exports/<nom>.mp4
      │  shortvideos/probe.probe_mp4() (OpenCV, secours ffmpeg -i)
[7] résultat : dimensions, fps, frames, durée, octets, première image
```

| Aspect | Implémentation exacte |
| --- | --- |
| Entrée unique | `server/render.py:render_project_to_mp4(job, project, out_path)` — n'a besoin que de `job.id`, `job.set_progress`, `job.cancel_event` |
| Composition | l'id vient du projet, résolu par `MODEL_REGISTRY` (`web/src/remotion/registry.tsx`) |
| Médias | `media://id` → copie double → `/media-cache/<id><ext>` → `staticFile()` dans le composant |
| Effets | `resolve.py` appelle `effects.normalize()` (réglages **complets et bornés**) → la composition Emballe les calques (`applyLayerEffects`), la scène (`SceneEffects`) et pose les overlays (`SceneOverlays`) — **mêmes props en aperçu et en rendu**, donc l'effet vu dans le Player est celui du MP4 |
| Progression | parsée depuis la sortie du sous-processus ; le processus vif est gardé dans `job.result_process` pour `cancel` |
| Fichier de sortie | écriture `.part.mp4` puis `os.replace` ; un MP4 existant est **refusé (409)** sauf `overwrite` explicite |
| Nettoyage | fichier de props supprimé dans un `finally` ; un `props-*.json` restant = rendu en cours |
| Échec | les 25 dernières lignes de sortie du processus sont remontées dans `job.error` |
| Audio | `resolved.audio` : musique **bouclée** si plus courte que la vidéo (jamais de `playbackRate`), surplus rogné à la dernière frame, fondu de sortie calé sur la fin |
| Polices | 5 familles OFL locales ; la chaîne de rendu n'utilise **jamais** une police Windows installée (seule la chaîne v1 Pillow de `/short-videos` en charge 8 depuis le poste, sans les servir ni les embarquer) |

**Ce que garantit l'aperçu** : `POST /api/studio/prepare` sert le Player **et** le rendu.
Mêmes frames absolues, mêmes URLs, mêmes polices — donc ce qui est vu dans `/design` est ce
qui sort dans `exports/`. Mesure réelle : 1080×1920 / 30 fps / 405 frames / 13,5 s ; pour la
piste audio `aac (LC) 48 kHz stéréo`, gain mesuré −9,1 dB pour `music_volume: 0.35`
(20·log₁₀(0.35) = −9,04 dB).

---

## 8. Les pages, une par une

Chaque sous-section décrit : **à quoi sert la page**, sa **structure d'écran**, **panneau par
panneau** les champs et boutons, **l'endpoint appelé par chaque action**, et **ce que l'action
écrit**. Les numéros de ligne renvoient aux fichiers réels.

Le tiroir d'assistant étant **global** (§9.8), il n'est plus répété dans chaque page : les pages
ci-dessous décrivent ce qu'elles **publient** dans ce tiroir et ce que leurs propres contrôles font.

---

### 8.1 Cockpit — `/`

**Sert à** démarrer n'importe quelle journée de travail sans savoir encore où l'on va : l'assistant
au centre, et autour les seules choses qui répondent à « où en suis-je ? ».
`web/src/pages/CockpitPage.tsx` (500 lignes). Les cartes sont **lectrices** ; la seule écriture
possible est le parcours de **configuration guidée** (`SetupAssistant.tsx`), affiché tant que
`GET /api/agent/status` ne renvoie pas `ready` — il enregistre les réglages de l'assistant
(`POST /api/settings`, `enabled: true`) **au clic explicite « Activer l'assistant »**, puis le
panneau disparaît et « Demander » se réactive.

| Bloc | Données réellement affichées | Endpoint |
| --- | --- | --- |
| **Configuration guidée** (si l'assistant n'est pas prêt) | la raison exacte du statut + 3 étapes : 1. fournisseur (local / Gemini / Groq, avertissement cloud), 2. connexion (URL + presets `llama.cpp` / `Local Chat`, clé et PIN optionnels en local ; clé en cloud — un champ vide conserve la clé enregistrée), 3. modèle (« Lister les modèles », « Tester la connexion » avec rapport réel) puis « Activer l'assistant ». Lien « Réglages avancés » vers `/settings` | `GET /api/settings` (pré-remplissage), `POST /api/agent/models`, `POST /api/agent/check`, `POST /api/settings` (activation) |
| **Hero assistant** | zone de demande + bouton « Demander » → `ask(text)` du contexte global : le tiroir s'ouvre et la demande part ; 4 exemples cliquables (couleur, effet mot à mot, question au catalogue, plan de lot). **« Demander » est désactivé** tant que l'assistant n'est pas configuré, avec renvoi vers le parcours ci-dessus | `POST /api/agent/ask` (au clic) |
| **Effets** | `N effets · 4 max par cible` + une puce par catégorie ; chaque puce **pose une question à l'assistant** sur cette catégorie | `GET /api/studio/effects` |
| **File de production** | lots `running` / `paused` avec barre de progression ; sinon « N lot(s) dans la file persistante, aucun en cours » + résumé du dernier (statut lisible, `3/3 rendu(s)`, date) ; sinon texte explicite « aucun lot » | `GET /api/batch` |
| **Derniers projets** | 5 projets les plus récents (tri sur `modified`), chaque ligne va à `/design?project=<nom>` | `GET /api/projects` |
| **Modèles** | modèles triés par date, chaque ligne va à `/design?model=<id>` | `GET /api/library` |
| **Points de contrôle** | polices manquantes, dossiers connectés, état de l'assistant (`ready` / pourquoi il ne l'est pas), index de connaissances | `GET /api/studio/fonts`, `GET /api/folders`, `GET /api/agent/status` |
| **Aller plus vite** | `Ctrl+K`, `Ctrl+I`, `Échap`, `Ctrl+Z` | — |

**Règle d'honnêteté, vérifiable dans le code** : chaque carte est alimentée par un appel réel ;
si l'appel échoue, **la carte affiche l'erreur** (`apiErrorMessage`) et non un nombre inventé.
Aucun indicateur n'est simulé, aucun bouton « bientôt disponible » n'existe.

---

### 8.2 Design — `/design`

**Sert à** créer et personnaliser un projet v2 et l'exporter en MP4. Écran en trois colonnes
à **plancher et plafond** ([`DesignPage.tsx:594`](file:///E:/youtube/youtube_clipper/web/src/pages/DesignPage.tsx#L594) :
`grid-cols-[minmax(215px,250px)_minmax(0,1fr)_minmax(255px,300px)]`, élargi en `xl`), pour que
l'aperçu garde de l'air quand le tiroir d'assistant s'ouvre ou que la fenêtre est étroite :
scènes à gauche, Player + timeline au centre, **Inspecteur seul** à droite — l'ancien onglet
« Assistant IA » a été **remplacé par le tiroir global** (§9.8), et la colonne droite ne contient
donc plus d'onglets.

**Barre d'outils** (`DesignPage.tsx:487-560`)

| Contrôle | Action | Endpoint / effet |
| --- | --- | --- |
| Champ « Projet » | nom du projet, `aria-label="nom du projet"` | sert à `POST /api/projects` et au nom du MP4 |
| Badge « modifications non enregistrées » | état `dirty` | — |
| **Assistant** (`:505`) | `showAssistant(true)` — ouvre le tiroir global, `Ctrl+I` | aucune requête : le tiroir lit l'état déjà publié par la page |
| **Annuler** / **Rétablir** | historique borné, `Ctrl+Z` / `Ctrl+Maj+Z` ; une suite de frappes groupée en une seule entrée (`edit.ts`, `gestureTimer`) | mémoire seule |
| **Nouveau** | projet vierge du modèle par défaut | `GET /api/studio/default` |
| **Ouvrir** | dialogue listant `projects/*.json` | `GET /api/projects`, puis `GET /api/projects/{name}` |
| ↳ un fichier v1 est sélectionné | conversion **explicite** v1→v2, bandeau « Conversion v1 → v2 » avec la liste des notes, enregistrement sous `<nom>_v2` | `POST /api/studio/upgrade` — le fichier d'origine n'est **jamais** écrasé |
| **Sauvegarder** | écriture explicite ; l'autosauvegarde se déclenche après **1 400 ms** d'inactivité (`DesignPage.tsx:222`) | `POST /api/projects` |
| **Bibliothèque** | dialogue nom + description → enregistre le projet comme modèle réutilisable ; **désactivé** si le projet a des erreurs | `POST /api/library` |
| **Packs** (`DesignPage.tsx:547`) | dialogue « Packs de marque client » : liste des `brands/*.json`, **Créer depuis ce projet**, **Appliquer au projet**, Retirer. Le projet appliqué repasse par `applyEdit(…, true)` → **annulable et autosauvegardé**, exactement comme un réglage ou une application de l'assistant | `GET /api/brands`, `POST /api/brands/capture`, `POST /api/brands/{id}/apply`, `DELETE /api/brands/{id}` |
| **Exporter** | dialogue d'export ; désactivé si erreurs, ou `prepared` absent, ou polices non chargées | `POST /api/exports` |
| Badges d'état | `n erreur(s)` (destructive), `n avertissement(s)` (warning), `polices…`, puis ligne mono `1080×1920 · 30 fps · 405 f · 13.5s` | valeurs du `resolved` serveur |

**Colonne gauche — `ScenesPanel`** (`panels.tsx:197-…`)

- `<Section title="Modèle">` : composition Remotion active, id, version, cadre, fps.
- `<Section title="Scènes · N">` : liste ordonnée des scènes ; pour chacune — durée
  (slider, 0,5–120 s), sélection au clic, **monter / descendre**, **dupliquer**, **supprimer**,
  afficher/masquer, et deux boutons **Ajouter un calque texte** / **Ajouter un calque image**.
  En bas : **Ajouter une scène**.
- `<Section title="Médias de la scène">` : emplacements `MediaSlot` (fond + calques image) ;
  chaque slot envoie un fichier → `POST /api/media/upload` → réécrit `media://<uuid>` ;
  bouton **Retirer** ; miniature de l'aperçu ; champs **provenance** (source, licence, date)
  via `POST /api/studio/provenance`.

**Colonne centrale — aperçu**

`Remotion Player` monté sur `prepared.resolved` (les props **résolues par le serveur**,
`POST /api/studio/prepare`), cadre vertical mis à l'échelle (`scale` 0.22 par défaut),
lecture/pause/boucle/seek. Le ruban `TimelineBar` ([`panels.tsx:1060`](file:///E:/youtube/youtube_clipper/web/src/pages/design/panels.tsx#L1060)) affiche marqueurs de
scènes, frame courante, durée, lecture, boucle et seek. Sous le Player, mention explicite :
« Aperçu Remotion Player avec le projet résolu par le serveur — même objet que celui du
rendu MP4 ». Les mesures de débordement (`measure.ts`) utilisent la **police réelle**,
chargée par `preloadAllFonts()` avant toute mesure.

**Colonne droite — Inspecteur** (`InspectorPanel`, [`panels.tsx:687`](file:///E:/youtube/youtube_clipper/web/src/pages/design/panels.tsx#L687))
Le contenu dépend de la sélection ; deux `<Section>` portent le nom exact **« Effets »** — l'une pour
le calque actif (`host="layer"`, cible `text` ou `image`), l'autre pour la scène (`host="scene"`) :

| Section | Champs (label exact) |
| --- | --- |
| **Contenu du calque** | texte (`textarea`), rôle (`accroche` / `citation` / `auteur` / `révélation`…), **mots mis en valeur**, activé/désactivé |
| **Typographie** | police (liste des familles **sous licence**, licence affichée), poids, taille (px), interligne, chasse (em), couleur, couleur d'accent, ombre, contour (px) + couleur du contour, opacité, sens d'écriture |
| **Position** | position X/Y (normalisées), largeur, alignement ; pour un calque image : taille et ancrage |
| **Animation & temporisation** | unité animée (bloc/ligne/mot), entrée, sortie, début (frame de la scène), entrée (frames), sortie (frames), maintien, décalage entre unités, distance du mouvement, courbe, et pour `spring` : amorti., raideur, masse |
| **Effets** (`panels.tsx:548`) | select « + ajouter un effet… » **groupé par catégorie** et filtré sur la portée et la cible du calque/la scène ; compteur `n/4` dans le titre ; pour chaque effet posé : ligne dépliable (label + `id` en mono), **réglages bornés** du catalogue (curseur, nombre entier, booléen, couleur, liste, texte), croix de retrait, badge **« audio requis »** / **« audio réel »** selon l'état réel de la piste, et bouton **« Appliquer a toutes les scenes »** sur la scène. Si un id stocké n'est plus au catalogue, la section **l'affiche en rouge** plutôt que de le masquer |
| **Fond de scène** | média, cadrage (`cover`/`contain`), mouvement (`statique`/`zoom lent`/`zoom arrière`), opacité |
| **Thème (valeurs par défaut)** | police par défaut, surface, palette enregistrée |
| **Signature de marque** | logo, nom de marque, `@pseudo`, position, taille, entrée |
| **Export** | largeur, hauteur, fps, graine de variation |
| **Validation (serveur)** | erreurs bloquantes et avertissements — calculés par `shortvideos/validation.py`, **aucune logique dupliquée côté client**, **y compris pour les effets** |
| **Projet résolu** | bloc `resolved` en JSON : frames, fenêtre par calque, **effets normalisés avec leurs réglages complets**, graine, ressources et licences |

**Tiroir droit — l'assistant global** : l'ancien onglet « Assistant IA » de Design a été retiré ;
c'est le tiroir décrit au chapitre [9.8](#98-lassistant-au-centre-provider-global--tiroir) qui s'ouvre, par le
bouton **Assistant** de la barre d'outils ou par `Ctrl+I`. Design **publie** son projet, son nom, sa
sélection et `mode: "design"` ; `onApply` passe toujours le candidat accepté par
`applyEdit(candidate, true)` — donc dans l'historique d'annulation et **jamais** dans l'autosauvegarde
avant acceptation.

**Dialogue d'export** (`design/ExportDialog.tsx`) : nom du fichier (dossier `exports/`),
progression réelle parsée (`Rendu 82/150`), **Annuler le rendu** (terminaison + nettoyage du
`.part.mp4`), résultat (chemin, dimensions, durée, frames, taille), traceback affiché en clair,
et sur **409** la proposition « Remplacer le fichier existant ».

**Ce que Design écrit** : `projects/<nom>.json`, nouveaux médias dans `media/` (+
`media/provenance/`), `models/<id>.json` via Bibliothèque, `exports/<nom>.mp4` via Exporter.

---

### 8.3 Bibliothèque — `/library`

**Sert à** voir, utiliser et gérer les modèles enregistrés (`LibraryPage.tsx`, 158 lignes).
Grille de cartes, une par modèle.

| Élément de carte | Provenance |
| --- | --- |
| Nom + description | `models/<id>.json` ou modèle intégré |
| Badge **intégré** / **perso** | `server/library.py` (les intégrés sont protégés en suppression) |
| `Composition` | `model.id` (Remotion) |
| `Scènes`, `Durée`, `Cadre`, `Médias`, `Fichier` | projet du modèle, lu serveur (`GET /api/library`) |

Actions :

| Bouton | Endpoint | Effet réel |
| --- | --- | --- |
| **Utiliser ce modèle** | navigation `/design?model=<id>` | charge le préréglage ; les réglages créent un **nouveau** projet |
| **Retirer** (perso uniquement) | `DELETE /api/library/{id}` avec confirmation | supprime le JSON du modèle, **jamais** les médias importés ni les projets |
| **Ajouter vos propres modèles** (encadré) | — | consigne : déposer un projet JSON v2 dans `models/` ; la page affiche le **dossier et le chemin absolus**. Seuls `version: 2` et un `model.id` du registre sont acceptés ; un fichier illisible est **signalé**, pas masqué |

---

### 8.4 Production — `/production`

**Sert à** produire un lot de vidéos à partir d'un CSV, sans ouvrir l'éditeur.
Sept sections numérotées **dans l'ordre réel du travail**, plus l'historique
(`ProductionPage.tsx`, 1189 lignes). Le plan affiché est calculé par le serveur avec le
**même code** que le lancement (`_plan()` → `shortvideos.batch.build_plan()`).

| # | Section | Champs et contrôles | Endpoint(s) |
| --- | --- | --- | --- |
| 1 | **Modèle** (`:516`) | liste déroulante des modèles **v2** de la bibliothèque ; récapitulatif `Composition`, `Cadre`, `fps`, `Médias du modèle` | `GET /api/batch/setup` |
| 2 | **Dossiers de médias connectés** (`:551`) | champ chemin absolu + sélecteur de type (fonds vidéo / musiques / images / tout) + champ licence (vide ⇒ `inconnue`) + nom affiché ; bouton **Enregistrer** (`:588`), **Scanner** (`:622`), corbeille (`:625`) ; liste avec badges, compteurs fonds/musiques/images et date du dernier scan | `GET/POST /api/folders`, `POST /api/folders/{id}/scan`, `DELETE /api/folders/{id}` |
| 3 | **Attribution des ressources** (`:656`) | pour les fonds **et** pour la musique : `rotation automatique` · `uniquement ce que dit le CSV` · `rien ajouter (garder le modèle)` | mémoire, transmis au plan |
| 4 | **Import CSV** (`:690`) | bouton-fichier **Choisir un fichier** (`.csv,.txt`) ; après import : nom, `n ligne(s)`, `n colonne(s)`, encodage, séparateur, badges de colonnes, avertissements, tableau des **5 premières lignes** et rappel des limites (2000) | `POST /api/batch/csv` (puis `GET /api/batch/csv/{id}`) |
| 5 | **Mapping des colonnes** (`:767`) | un sélecteur de colonne **par champ adressable** (18 pour Citation cinématique, `GET /api/batch/fields?model=`), badges `requis` et type média, compteur « `n` champ(s) câblé(s) sur `N` » ; désactivé tant qu'aucun CSV n'est importé ; bouton **Aider avec l'IA** (`:780`, `disabled={!csv || fields.length === 0}`) **qui ouvre le tiroir assistant global** — il n'y a plus de panneau IA intégré à cette page | voir [9.9](#99-intégration-dans-production) |
| 6 | **Plan du lot** (`:843`) | nom du lot, interrupteur **écraser les fichiers existants**, récapitulatif, **bandeau de cycle** quand les ressources sont moins nombreuses que les lignes, avertissements, table des lignes (`Fichier`, `Durée`, `Fond` + source + passe, `Musique` + source + passe, `Diagnostic`, lien « voir » → ligne résolue en JSON), boutons **Calculer le plan** (`:854`) puis **Lancer** (`:857`, désactivé tant que le plan n'est pas prêt) | `POST /api/batch/plan`, `POST /api/batch/line`, `POST /api/batch/start` |
| 7 | **File de production** (`:1010`) | progression live (ligne courante + frames), **Annuler le lot** (`:1042`), **Relancer les échecs** (`:1047`), **Reprendre** (`:1052`), table des lignes (`Fichier`, `Statut`, `Sortie` taille + relecture vidéo, `Détail` erreurs/avertissements), téléchargement du **manifeste CSV et JSON**, note de persistance (`batch/queue.sqlite3`) | `GET /api/batch/{id}`, `POST …/cancel`, `…/retry`, `…/start`, `GET …/manifest`, `GET …/file?position=` |
| — | **Historique des lots** (`:1131`) | statut, compteurs, boutons Lancer / Relancer les échecs / Détail / Retirer | `GET /api/batch`, `DELETE /api/batch/{id}` |

**Politique visible avant lancement** (celle du moteur, §10.4) : la colonne mappée gagne ;
un fichier nommé mais absent **bloque** la ligne ; rotation déterministe sur dossiers triés ;
le cycle reprend si les ressources manquent ; la musique est bouclée ou coupée, **jamais
accélérée** ; un texte qui déborde est un **avertissement**, jamais une coupure ; graine par
ligne = graine du modèle + index − 1 ; noms de fichiers `%03d-<slug>.mp4`.

**Après le lot, la page [Livraison `/delivery`](#810-livraison--delivery)** assemble le paquet
client à partir de ce que cette file a produit ; Production reste la seule page qui **rend**,
Livraison la seule qui **empaquette**. Aucune des deux ne propose l'autre par un lien : les deux
sont atteignables par la barre latérale et par `Ctrl+K`.

---

### 8.5 Clips — `/clips`

**Sert à** découper une vidéo YouTube en clips verticaux à l'aide de Groq. Écran en deux
colonnes (`grid-cols-[340px_minmax(0,1fr)]`) : les 3 étapes à gauche, les résultats à droite.
En-tête (`ClipsPage.tsx:176-238`) : badge d'état de la clé Groq
(« Clé Groq configurée » / « Clé Groq à saisir (Réglages) »), sélecteur **Session** (liste
`GET /api/clips/sessions`, option vide = nouvelle session, mention « (vidéo absente) »),
bouton **Nettoyage** (`DELETE /api/clips/sessions/{sid}`, confirmation explicite : supprime
la session, sa vidéo et ses clips).

| Étape | Champs | Bouton | Endpoint | Job |
| --- | --- | --- | --- | --- |
| **1 · Source** (`:245`) | champ URL YouTube | **Infos** → titre, durée, nombre de formats, badges de sous-titres (`SOUS-TITRES`, `AUTO`, ou « aucun sous-titre ») | `POST /api/clips/info` | `clips_info` |
| | | **Télécharger** → nom du fichier, taille, `n segments`, `n caractères`, avertissement éventuel | `POST /api/clips/download` | `clips_download` |
| **2 · Analyse Groq** (`:321`) | slider **Nombre de clips recherchés** (1–20) | **Analyser la transcription** — désactivé tant qu'aucune session n'a de sous-titres (infobulle explicite : « Téléchargez d'abord la vidéo » / « Téléchargez une vidéo avec des sous-titres ») | `POST /api/clips/analyze` | `clips_analyze` |
| **3 · Extraction** (`:358`) | interrupteurs **Paysage 16:9 (1920×1080)** et **Portrait 9:16 (visage centré)** ; message « Choisissez au moins un format. » | **Extraire n clip(s)** (index sélectionnés) — verrouillé si vidéo absente ou analyse manquante | `POST /api/clips/extract` | `clips_extract` |
| Panneaux droits | **Transcription** (`:409`, textarea lecture seule + compteurs + mention « aperçu tronqué »), **Clips détectés** (`:438`, cases à cocher, **Tout sélectionner** / **Tout désélectionner**, timestamps et raisons), **Clips produits** (`:486`, liens de relecture) | — | `GET /api/clips/files/{sid}/{name}` | — |

Traitement inchangé depuis l'interface Tkinter : `downloader.py` (yt-dlp), `analyzer.py`
(Groq), `processor.py` (FFmpeg + recadrage centré sur le visage). Progression et annulation
par le registre de jobs. Les fichiers vivent dans `clips/<sid>/`.

---

### 8.6 Podcast — `/podcast`

**Sert à** construire une base de phrases découpées puis assembler une vidéo qui énonce un
texte. Deux colonnes (`PodcastPage.tsx`, 514 lignes).

| Panneau | Champs / données | Bouton | Endpoint |
| --- | --- | --- | --- |
| **Base de phrases** (`:174`) | compteur `total_clips`, badges des locuteurs ; si l'**ancienne base Tkinter** est détectée et la base vide : encart avec le nombre de clips trouvés | **Importer dans le projet** | `POST /api/podcast/legacy/import` (job `podcast_legacy_import`) |
| **Ajouter une vidéo source** (`:221`) | **URL YouTube**, **Nom du locuteur (optionnel)** (placeholder « utilisé : titre de la vidéo ») | **Ajouter à la base** — télécharge, récupère les sous-titres, découpe phrase par phrase en FFmpeg | `POST /api/podcast/videos` (job `podcast_add`) ; résultat `clips_created`, `total_clips`, `speaker_count` ou `note` |
| **Catalogue de phrases** (`:283`) | **Recherche (mot ou phrase approchante)** (Entrée = chercher), sélecteur **Source**, table `Phrase`, `Source`, `Début`, `Fin`, `Durée`, bouton **clip** par ligne (lecteur vidéo inline, « Masquer l'aperçu ») | **Chercher** | `GET /api/podcast/clips?speaker=&q=` et `GET /api/podcast/files/{rel_path}` |
| **Générer une vidéo** (`:397`) | **Texte à énoncer** (une phrase par ligne ou séparée par des points ; chaque phrase doit exister dans la base), **Nom du fichier** + `.mp4`, interrupteur **Alterner les sources** | **Générer** — désactivé si texte vide, tâche occupée ou base vide (« Ajoutez d'abord une vidéo source à la base ») ; sur fichier existant, demande d'écrasement | `POST /api/podcast/generate` (job `podcast_generate`) |
| En-tête | compteurs serveur | — | `GET /api/podcast/stats` |

Moteur inchangé : `podcaster.py` (`add_video`, `split_video`, `build_video`,
`_find_all_matches`, `_select_with_alternation`, `_split_into_phrases`, `_assemble_clips`,
`_detect_face_embedding`, `_parse_srt`, `get_stats`) et `database.py`, base dans
`podcast_db/` (`catalog.csv` + `output/`).

---

### 8.7 Shorts v1 — `/short-videos`

**Sert à** éditer un projet de l'ancienne chaîne (une scène, une citation) et l'exporter.
Conservé parce que des projets v1 existent et que la mesure de débordement Pillow est encore
utilisée par `validation.py` et `tests/test_export_short.py`.

- **En haut** : nom du projet · **Ouvrir** · **Sauvegarder** · **Exporter** · statut
  (modifié / enregistré / erreurs).
- **Panneau gauche** — Contenu (citation multiligne, auteur optionnel), Médias (image de fond,
  logo ; upload → `POST /api/media/upload`, miniature, **Retirer**), Modèle (« Citation
  verticale (1080×1920) », seul modèle de cette tranche).
- **Panneau central** — Remotion Player : lecture/pause, progression, boucle, aperçu mis à
  l'échelle du 1080×1920 ; la composition `web/src/remotion/QuoteVertical.tsx` est partagée
  avec `npx remotion render`.
- **Panneau droit** — Style (police parmi les **8 polices Windows installées** — `FONTS`, `ShortVideosPage.tsx:30-38` : Arial, Arial Bold, Impact, Georgia, Times New Roman, Segoe UI, Verdana, Calibri Bold ; elles ne sont ni servies ni embarquées dans une livraison, taille 8–400 px, couleur du
  texte, couleur de l'auteur, ombre), Position (X, Y, largeur du bloc en coordonnées 0→1),
  Durée & animations (durée de scène 0,5–60 s, début du texte, fondu d'entrée, fondu de
  sortie, effet d'entrée fondu/glissement, fond statique/zoom lent), Validation (serveur).
- **En bas** : lecture/pause, instant / durée, numéro de frame, `résolution · fps · frames`,
  badge « Prêt à exporter » ou « Export bloqué ».
- Export : `POST /api/exports` + `GET /api/exports/{id}` + `POST …/cancel`, même dialogue que
  le Design, mêmes garde-fous (409, `.part.mp4`, nettoyage).

---

### 8.8 Projets — `/projects`

**Sert à** gérer les fichiers `projects/*.json` (`ProjectsPage.tsx`, 113 lignes).
Tableau : `Nom`, `Format` (version du JSON, `v1` ou `v2`), `Taille`, `Modifié`, `Actions`.

| Bouton | Endpoint | Note |
| --- | --- | --- |
| **Ouvrir** | navigation `/design?project=<nom>` (le Design charge, migre si v1) | la migration est **explicite**, jamais silencieuse |
| **Supprimer** | `DELETE /api/projects/{name}` | `window.confirm("Supprimer le projet « … » ? Cette action est définitive.")` |
| État vide | — | message explicite, pas de faux tableau |

---

### 8.9 Réglages — `/settings`

**Sert à** configurer côté serveur deux choses distinctes, sans jamais exposer une clé
(`SettingsPage.tsx`, 588 lignes, `GET/POST /api/settings`).

1. **Clé API Groq (analyse Clips)** (`:178`) — état « configurée » / « non configurée », champ
   `password` + **Enregistrer**. Mention explicite : cette clé sert **uniquement** à Clips ;
   l'assistant ne la réutilise que sur demande explicite. Écrit `groq_api_key` dans
   `server/settings.json`. Le `GET` ne renvoie qu'un booléen.
2. **Assistant IA du studio** (`:209`) — détaillé au [§9.2](#92-fournisseurs-url-et-modèles) :
   case **Activer l'assistant**, trois boutons de **fournisseur** (dont badge `cloud`),
   bandeau d'avertissement si cloud, **URL du serveur** + boutons de préréglages locaux +
   **PIN** (en-tête `X-PIN`), **Clé d'API** par fournisseur, **Modèle** avec
   `<datalist>` et bouton **Actualiser les modèles**, **Vérifier la connexion**, **Réutiliser
   la clé Clips** (Groq uniquement, copie serveur→serveur), **Effacer la clé et le PIN**, six
   `NumberField` (Température, Tokens de sortie, Budget de contexte, Timeout, Réparations
   auto, Outils de lecture / demande), sélecteur **sortie JSON (response_format)**
   `auto/on/off`, case **streaming**, **Enregistrer les réglages**, **Recharger**, et le
   voyant « prêt : <base_url> · <modèle> » ou « non configuré ».
   Sous le panneau : la carte du **test réel** (`CheckReportCard`) — latence, capabilities
   observées, réponse renvoyée, et la mention « Résultats observés sur les réponses du
   serveur, jamais déduits du nom du modèle ».
3. **« Ce que l'assistant peut toucher »** (`:471`) — manifeste lu serveur
   (`GET /api/agent/capabilities`) : modèles, modèles de bibliothèque, polices, animations
   d'entrée, nombre de médias importés, et la liste **Non proposé par l'assistant**. Les
   valeurs viennent du registre de compositions, de la bibliothèque, du schéma v2, du
   catalogue de polices et de `web/package.json` — **pas** de la documentation seule.
4. **Moteurs et points d'entrée** — rappel que `start_web.bat` est le seul lanceur et que
   Remotion est la source de vérité du rendu.

---

### 8.10 Livraison — `/delivery`

**Sert à** transformer un lot terminé en un paquet ZIP unique à envoyer au client
(`LivraisonPage.tsx`, 242 lignes, `GET/POST /api/delivery/{batch_id}[/package]`). La page
n'invente rien : elle lit l'état de la file et le fichier présent sur disque.

- **En haut** : titre + `Recharger les lots`. Sélecteur **Lot à livrer** — une option par lot
  réellement présent dans `batch/queue.sqlite3`, intitulée `{nom} — {rendered}/{total} rendues`.
- **Bouton Préparer le paquet** — désactivé si aucun lot n'est sélectionné, si
  `rendered == 0` ou si un job tourne déjà (`disabled={!batchId || rendered === 0 || job?.status === "running"}`).
  Il appelle `POST /api/delivery/{batch_id}/package`, qui refuse **409** si un paquet est déjà
  en cours pour ce lot et **400** s'il n'y a aucune vidéo rendue, puis renvoie un `job_id`.
- **Assemblage du paquet** — `<JobStatus>` pollé par `useJobPolling` (`GET /api/jobs/{id}`) :
  progression réelle « Livraison de <fichier>… », bouton **Annuler** (`raise_if_cancelled`
  entre chaque ligne, le `.part.zip` est supprimé dans le `finally`). À la fin du job, la page
  relit `GET /api/delivery/{batch_id}` — c'est le disque, pas le job, qui décide de l'affichage.
- **Carte Paquet prêt** — uniquement quand le ZIP existe : taille (`formatBytes`), date de
  préparation, compteurs `videos` / `subtitles` / `thumbnails` et les avertissements accumulation
  (miniature ratée, ligne sans texte sous-titrable, manifeste indisponible). Le téléchargement
  est un lien direct `GET /api/delivery/{batch_id}/package/file` ; le nom du fichier vient du
  serveur, jamais du client.
- **Tableau des lignes** — `position`, `nom`, `fichier` (borné par `safe_name`), `statut`,
  `durée`, `taille`, et `rendered` : « rendue » seulement si le fichier vidéo est relisible
  sous un chemin autorisé (`_video_of`). Une ligne `done` dont le MP4 a été déplacé est affichée
  comme non rendue, et n'entre pas dans le ZIP.

**Contenu du ZIP** (`server/delivery.py::build_package`, écriture `.part.zip` → `replace()`) :

| Dossier / fichier | Provenance |
| --- | --- |
| `videos/<fichier>.mp4` | le MP4 déjà rendu par la file — aucune seconde passe de Remotion |
| `subtitles/<stem>.srt` | `shortvideos.delivery.srt_from_project` sur le **projet planifié** de la ligne : mêmes fenêtres que `resolve()`, donc mêmes frames que le rendu |
| `thumbnails/<stem>.png` | frame à 45 % de la durée, extraite par `imageio-ffmpeg` ; un échec est un avertissement, pas un paquet refusé |
| `manifeste.json` / `manifeste.csv` | `queue.write_manifest()` — le même calcul que la fiche de la page Production |
| `LISEZ-MOI.txt` | nom du lot, compteurs, explication des sous-titres (« la signature de marque n'est pas sous-titrée — ce n'est pas une réplique ») et avertissements |

Tout est posé dans `batch/deliveries/`, sous-dossier de `BATCH_DIR` donc déjà couvert par
`ALLOWED_DIRS` ; le dossier temporaire `_tmp/<batch_id>` des miniatures est supprimé dans le
`finally`, que le job aille au bout ou soit annulé.

---

## 9. Assistant IA du studio (`server/agent/`)

### 9.1 Ce qu'il est, ce qu'il n'est pas

| Il fait | Il ne fait **pas** |
| --- | --- |
| Connaître le studio **en lisant son code** : registre de compositions, bibliothèque, schéma v2, **catalogue des 25 effets (`shortvideos/effects.py`)**, catalogue de polices, `web/package.json` | réciter une documentation ou inventer un paquet `@remotion/*` non installé, **un nom d'effet qui n'est pas au catalogue**, une opération qui n'existe pas |
| Lire sur demande : projet actif, modèles, polices, médias, dossiers, CSV, champs adressables, **vrai plan**, état des lots, sessions Clips, stats Podcast | écrire un fichier, lancer un rendu, démarrer un lot, supprimer quoi que ce soit, ouvrir un shell, `eval`/`exec` |
| Proposer une **proposition typée** validée par le métier existant | envoyer un projet « appliqué » ; le bloc `resolved` fourni par le modèle est **toujours retiré** |
| Se taire quand une capacité n'existe pas (`type=unavailable`) | prétendre à une capacité non vérifiée |

Tout passe par `POST /api/agent/ask`, exécuté dans un **job** (`server/jobs.py`) : le thread
de requête ne fait jamais de travail lourd. L'application reste entièrement utilisable si le
serveur LLM est éteint — l'assistant est une **aide**, pas un dépendance.

### 9.2 Fournisseurs, URL et modèles

Trois fournisseurs, **aucun basculement automatique**, réglages conservés séparément
([`server/settings.py:42-73`](file:///E:/youtube/youtube_clipper/server/settings.py#L42-L73)) :

| Clé `server/settings.json` | Défaut | Rôle |
| --- | --- | --- |
| `llm_enabled` | `False` | activer l'assistant (sinon `ask` répond `unavailable` sans appel) |
| `llm_provider` | `local` | `local` \| `gemini` \| `groq` |
| `llm_local_base_url` | `""` | **seule URL saisissable** ; les URL cloud sont fixes côté serveur |
| `llm_local_api_key` / `llm_local_pin` | `""` | clé et `X-PIN` d'un serveur local qui les exige |
| `llm_local_model` | `""` | modèle local retenu |
| `llm_gemini_api_key` / `llm_gemini_model` | `""` | API Gemini |
| `llm_groq_api_key` / `llm_groq_model` | `""` | API Groq — **distincte** de `groq_api_key` (Clips) ; reprise uniquement par le bouton explicite « Réutiliser la clé Clips » |
| `llm_temperature` | `0.4` (0–2) | échantillonnage |
| `llm_max_tokens` | `900` (64–32 000) | sortie |
| `llm_context_budget` | `3 000` (1 000–200 000) | budget de **contexte estimé**, à couvrir par la fenêtre du serveur avec la sortie |
| `llm_timeout` | `120` s (5–1 800) | délai d'appel |
| `llm_max_repairs` | `2` (0–5) | tentatives de réparation du JSON / de la proposition |
| `llm_max_tool_calls` | `3` (0–10) | outils de lecture par demande |
| `llm_stream` | `True` | SSE : permet l'arrêt pendant la génération |
| `llm_json_mode` | `auto` | `auto` \| `on` \| `off` — demande `response_format={"type":"json_object"}` |

URL cloud fixes : Gemini `https://generativelanguage.googleapis.com/v1beta/openai`,
Groq `https://api.groq.com/openai/v1`. Le panneau Réglages propose deux préréglages locaux
(`http://127.0.0.1:8900/v1` llama.cpp, `http://127.0.0.1:8080/api/agent/v1` relais) mais
**n'hypothèque aucun port** : le serveur doit exposer `/chat/completions`.

`POST /api/agent/models` renvoie la liste **réellement déclarée** par le fournisseur
(`GET /models`) ; si elle est indisponible, la saisie manuelle reste possible dans le champ
Modèle — aucune liste figée de noms inventés. `POST /api/agent/check` fait un **test réel**
(mini-prompt + mesures) et renvoie latence, capacités observées et, en cas d'échec, un
`hint` ; jamais un résultat déduit du nom du modèle.

### 9.3 Déroulé d'une demande (les 6 étapes de `service.run_request`)

| Étape | Message affiché par le job | Ce qui se passe |
| --- | --- | --- |
| 1/6 | « Recherche dans les connaissances du studio… » | `retrieval.search()` sur l'index FTS5, 4 sections au plus |
| 2/6 | « Manifeste des capacités… » | `capabilities.build()` recalculé (TTL 30 s), version Remotion lue dans `web/package.json` |
| 3/6 | « Construction du contexte… » | `context.assemble()` : rôle, interdits, protocole, contexte projet **ou** colonnes CSV, documents |
| 4/6 | « Génération par le modèle… » puis éventuellement « Outil de lecture : X… », « Réparation de la réponse (n/N)… », « Validation de la proposition (n/N)… » | appel LLM ; si la réponse est un `tool_call`, exécution de l'outil et **ré-injection de l'observation** ; sinon parsing JSON → `proposals.validate()` → en cas de rejet, la **liste d'erreurs** est renvoyée au modèle pour réparation (max `llm_max_repairs`) |
| 5/6 | (implicite, dans 4/6) | validation **métier** du candidat par `shortvideos/validation.validate_project()` |
| 6/6 | « Proposition prête. » | enregistrement en mémoire (`PROPOSAL_TTL = 3600 s`), renvoi de la proposition **sans candidat** |

Si l'échec vient de la taille du contexte (`llm_client.KIND_CONTEXT`), le budget est
**réduit de 35 %** (`×0.65`, plancher 1 400 tokens — `service.py:251`) et la demande est
retentée une fois : le prompt raccourci réessaie les niveaux de
détail plus bas plutôt que d'échouer.

### 9.4 Un contexte volontairement borné

Ordre de remplissage jusqu'à `llm_context_budget` : protocole + rôle + interdits → manifeste
des capacités → **projet en JSON complet** si possible → sinon « outline » (scènes, rôles,
longueurs, polices) → **compact** (résumé d'une dizaine de lignes) → documents. Le mode
`production` remplace le projet par `CONTEXTE PRODUCTION PAR LOTS` + les **colonnes du CSV
comme données**, avec une clause anti-injection : le contenu d'un CSV ou d'un document est du
**texte**, jamais une instruction qui autorise une action.

### 9.5 Le contrat des propositions

Types acceptés (`proposals.PROPOSAL_TYPES`) : `question` · `project_new` · `project_patch` ·
`library_save` · `batch_plan` · `unavailable`.

Clés fermées (`proposals.py:32-56`) : `THEME_KEYS`, `EXPORT_KEYS = {width,height,fps}`,
`VARIATION_KEYS = {seed}`, `SCENE_KEYS` (6 : `duration`, `label`, `hidden`,
`background.fit|animation|media`), `LAYER_KEYS` (**33 chemins pointés** : texte, hidden,
locked, opacity, emphasis, media ; `style.font_family|font_weight|font_size|line_height|
letter_spacing|color|accent_color|stroke_color|stroke_width|shadow` ; `position.x|y|width|
align|direction` ; `animation.in|out|unit|stagger_frames|start_frames|in_frames|out_frames|
easing|distance` ; `animation.spring.damping|stiffness|mass`), `SIGNATURE_KEYS` (12),
`AUDIO_KEYS` (7), `ROLE_CHOICES = {hook, caption, quote, author, reveal, body, mark}`.
`ENUM_PATHS` force les 8 énumérations **à l'opération** pour que le message de réparation
liste directement les choix possibles. `MAX_TEMPLATE_CHARS = 12 000` borne aussi la taille
d'un modèle injecté.

Opérations de `project_patch` — **14 noms, aucun autre n'existe**, 60 opérations maximum par
proposition :

| Catégorie | Opérations | Cible |
| --- | --- | --- |
| réglages globaux (5) | `set_theme`, `set_export`, `set_variation`, `set_signature`, `set_audio` | un `path` dans la liste fermée correspondante |
| scène / calque (2) | `set_scene`, `set_layer` | `scene_id` (+ `layer_id`) **et** `path` — identifiants stables, jamais la position |
| **effets (1)** | `set_effects` | `scene_id` (+ `layer_id` **optionnel**) et `effects` : liste d'ids ou `{"id", "params"}`. **Sans `layer_id`, l'opération porte sur la scène** (portée `scene`/`overlay`). La liste passe par `effects.normalize()` **avant** acceptation : un id hors catalogue, un effet posé sur la mauvaise portée ou le mauvais type de calque, un doublon ou plus de 4 effets ⇒ `ProposalError` **réparable** (le message cite les 25 ids disponibles). `effects: []` **retire** tous les effets — c'est le seul moyen propre de les enlever par proposition |
| construction (6) | `add_text_layer`, `add_image_layer`, `add_scene`, `duplicate_scene`, `remove_scene`, `remove_layer` | passent par les aides de `schema.py`, jamais par du JSON libre (`CONSTRUCT_OPS`) |

Il n'existe **pas** d'opération `set_style` : une couleur se change par
`{"op":"set_layer","scene_id":"s2","layer_id":"quote","path":"style.color","value":"#0E7C86"}` —
la liste blanche `LAYER_KEYS` est explicite, c'est ce qui rend le message de réparation précis.

Un média est accepté **seulement** en `media://<uuid>` (`_check_media_ref`) ; une référence
inventeuse ou un chemin disque est rejeté avant validation métier.

`batch_plan` attend `model`, `mapping` (champ → colonne), `options` (`background`, `music` ∈
`auto|column|none`), `notes`. Le validateur vérifie le modèle dans la bibliothèque, chaque
champ contre les 18 `fillable_fields()`, chaque colonne contre le CSV importé ; un champ
inventé lève `ProposalError` **réparable**. Le candidat ne contient **jamais** de `job_id` :
la proposition ne lance rien.

`accept(id, rebase)` : si le projet a changé depuis `base_revision`, conflit signalé et
`rebase` obligatoire — **on n'écrase pas des modifications récentes**. `reject(id)` purgé le
registre. TTL 1 h, registre en mémoire, aucune donnée persistée.

### 9.6 Les 31 outils (`server/agent/tools.py:34-77`)

| Famille | Outils de lecture (21, utilisables par le modèle) |
| --- | --- |
| connaissances & capacités | `get_capabilities`, `search_knowledge`, `read_knowledge` |
| design & bibliothèque | `get_current_project`, `list_templates`, `get_template`, `list_projects`, `list_fonts`, **`list_effects`** |
| médias | `list_assets`, `search_assets`, `get_asset_provenance`, `list_media_folders`, `scan_media_folder` *(uniquement sur demande explicite de l'utilisateur)* |
| production | `get_batch_fields`, `get_csv_preview`, `compute_batch_plan`, `get_batch_status`, `get_queue_status` |
| clips & podcast | `get_clips_sessions`, `get_podcast_stats` |

`list_effects` renvoie le **catalogue serveur filtré et borné** — filtres `id`, `scope`,
`target`, `category`, plafond `MAX_EFFECT_SPECS = 40`, chaque effet avec **ses réglages et leurs
bornes** pour que le modèle écrive des `params` valides du premier coup. Une portée, une catégorie
ou un id inconnu lève `ToolError` **avec la liste des choix**. L'assistant répond donc à
« quels effets tiennent sur un calque de texte ? » en lisant la même liste que l'éditeur et que le
validateur, pas en inventant des noms (`tests/test_effects.py::test_list_effects_tool_filters_and_bounds`).

| Outils de **proposition** (6, produisent une `Proposal`) | Outils **d'exécution** (4, déclenchés **seulement** par un clic utilisateur sur les routes du studio) |
| --- | --- |
| `propose_project`, `propose_project_changes`, `validate_candidate`, `propose_library_save`, `propose_batch_mapping`, `prepare_batch_plan` | `apply_candidate`, `save_library_model`, `start_export`, `start_batch` |

Bornes d'exécution : `MAX_SEARCH_RESULTS = 8`, `MAX_ASSETS = 60`, `MAX_ROWS_PREVIEW = 12`,
`MAX_TEMPLATE_CHARS = 12 000`, `MAX_EFFECT_SPECS = 40`. `tools.describe()` publie la liste et les
**interdits** : accès shell ou système, `exec`/`eval` du contenu généré, chemin disque choisi
par le modèle, installation de dépendances, suppression de fichiers, lancement d'un lot ou
d'un export sans clic utilisateur.

### 9.7 D'où vient sa connaissance du Remotion

`server/skills.py` sert le paquet `skills/remotion/`, **lu uniquement depuis le disque**
(aucun appel réseau, aucune dépendance) : les Agent Skills officiels (routeur + 12 fiches,
≈ 1,2 Mo), la bible française (`bible/`, 7 fiches, extraite par `tools/extract_bible.py`) et
le guide des effets (`effects/`, 1 index + 10 fiches, découpé **verbatim** par
`tools/split_effects_guide.py`, qui compare chaque fiche à sa section d'origine).
`retrieval.py` en tire l'index FTS5 `knowledge/agent_index.sqlite3` — **110 documents,
548 sections** à la construction du 2026-11-03, 1,6 Mo. Le guide cite beaucoup de paquets
`@remotion/*` non installés : `context.py` réinjecte donc un bloc **ETAT DU PROJET** relu dans
`web/package.json` à chaque demande, pour que l'assistant ne propose pas un paquet absent.
`skills/remotion/PROVENANCE.md` consigne source, version, méthode et état de licence.

### 9.8 L'assistant au centre : provider global + tiroir

Depuis la refonte de navigation, l'assistant **n'appartient plus à une page**. Trois modules se
partagent le travail :

| Module | Rôle | Ce qui garantit |
| --- | --- | --- |
| `lib/assistant.tsx` (172 l.) | `AssistantProvider` monté **dans `App`** : état `open` persisté (`localStorage`), `request` (une demande lancée depuis une autre page), `data` de la dernière réponse, et `usePublishAssistant(ctx, handlers)` | **une seule conversation** ; elle survit à `navigate()` ; `useEffect(() => () => publish({}, {}), [publish])` **dépublie au démontage** — donc pas de bouton « Appliquer » orphelin sur une page sans éditeur |
| `components/AssistantDock.tsx` (134 l.) | colonne de 400 px à droite de `<main>`, jamais un overlay ; fermé → **rail de 26 px** cliquable ; l'`AgentPanel` y reste monté ; entête affichant le contexte publié ; bandeau `applyHint` quand la page ne peut pas appliquer ; `Échap` ferme ; `onConfigure` ferme le tiroir et mène au Cockpit | le job en cours **n'est pas interrompu** parce qu'on a fermé le tiroir ou changé de page |
| `components/agent/AgentPanel.tsx` (376 l.) | le panneau lui-même, identique à avant — il reçoit simplement `externalRequest`, `applyHint`, `visible` et `onConfigure` en plus ; le statut est **relu à chaque ouverture** (`visible`), donc une activation faite tiroir fermé est visible sans rechargement ; le bandeau « non configuré » propose **« Configurer l'assistant »** | le contrat serveur (§9.5) est le seul chemin d'écriture ; **rien n'applique sans clic** |

**Design** publie `{project, projectName, selection, mode:"design", source:"Design"}` et quatre
gestionnaires :

1. la demande part avec `{message, project, mode:"design", selection, csv_columns: []}` ;
2. le job est pollé (`useJobPolling`) et chaque étape du §9.3 est affichée, outils inclus ;
3. la `ProposalCard` montre résumé, **diff** des opérations (dont `set_effects`), avertissements,
   état de validation serveur ;
4. **Appliquer** → `onApply(candidate)` → `applyEdit(candidate, true)` : le candidat entre
   dans l'état de l'éditeur **et dans l'historique d'annulation**, donc `Ctrl+Z` suffit à
   revenir en arrière. Tant que le clic n'a pas eu lieu, l'autosauvegarde ne voit jamais le
   candidat ;
5. **Enregistrer le modèle** (`library_save`) → `api.saveLibraryModel` ;
6. **Demander une correction** renvoie la proposition précédente + l'observation au modèle ;
7. `SourcesPanel` (156 lignes) permet de relire les sections de connaissances citées
   (`POST /api/agent/search`).

Le **Cockpit** (`/`) utilise le même tiroir par `ask(text)` — son champ de demande et ses puces
de catégories d'effets **pré-remplissent et lancent** la conversation (`externalRequest`), sans
que la page ait besoin d'un éditeur : si la proposition est un `project_patch`, le bandeau
`applyHint` dit explicitement « Aucun éditeur sur cette page : ouvrez Design, relancez la demande
avec le projet affiché, puis appliquez. »

### 9.9 Intégration dans Production

Le bouton **« Aider avec l'IA »** de la section 5 (`ProductionPage.tsx:780`) ne monte plus de
panneau : il appelle `showAssistant(true)`, et la page **publie** sa propre entrée dans le tiroir
commun — `{project: null, projectName: lotName, mode:"production", csvColumns: csv?.columns ?? []}`
— avec `onBatchPlan` et `notify`. L'étiquette d'acceptation reste **« Reprendre le mapping »**.
Sans CSV importé, le bouton est désactivé et le contexte publié indique « aucun CSV importé », ce
qui évite une demande hors sol.

`applyAgentPlan()` revalide **indépendamment côté page** avant toute écriture d'état :
`plan.model` doit exister dans `setup.models` (sinon les champs sont relecture via
`api.batchFields`), chaque champ du mapping doit appartenir aux clés adressables du modèle
**cible**, chaque colonne doit exister dans le CSV importé, chaque option doit être dans
`{auto, column, none}`. Les éléments refusés sont listés dans une note ; ceux qui passent
remplissent `model`, `mapping`, `options`. Message final explicite :
**« Recalculez le plan (bouton 6) ; le lancement reste votre clic. »** L'assistant ne crée
aucun lot, ne télécharge aucun fichier et n'appelle aucune route de rendu.

### 9.10 Transparence

- `GET /api/agent/status` expose l'état EFFECTIF (fournisseur actif, base URL, modèle,
  ready, nombre de clés configurées) et le manifeste de capacités ;
- chaque réponse de l'assistant porte un `meta` : `prompt_mode`,
  `estimated_input_tokens` (`CHARS_PER_TOKEN = 3`), `context_budget_tokens`, `attempts`,
  modèles et latences observées ;
- les réponses LLM **ne sont pas journalisées** ; les clés ne sortent jamais du serveur ;
- une erreur de contrat est renvoyée **telle quelle** au modèle pour réparation, puis à
  l'utilisateur en clair si elle persiste — jamais masquée par une réponse approximative.

---

## 10. Production par lots, le moteur

### 10.1 Lecture CSV — `server/csv_source.py`

- séparateur sniffé parmi `;` `,` tabulation `|` ;
- encodages testés dans l'ordre `utf-8-sig` → `utf-8` → `cp1252` ;
- en-têtes obligatoires sur la première ligne, `MAX_ROWS = 2000` au-delà desquels le fichier
  est **refusé** avec invitation à le découper ;
- lignes raggées signalées (jamais ignorées), aperçu des 5 premières lignes renvoyé au
  frontend, contenu stocké dans `batch/csvs/<id>.json` pour que le plan soit recalculable.

### 10.2 Champs adressables — `shortvideos.batch.fillable_fields(template)`

Les champs sont **découverts dans le modèle**, dans l'ordre visuel — rien n'est codé en dur
pour un modèle donné. `citation-cinematique` en expose **18** :

| Clé | Type | Libellé |
| --- | --- | --- |
| `title` | text | Titre (sert aussi de nom de fichier) |
| `scene.s1.hook.text` · `scene.s1.caption.text` | text | Accroche → hook / caption |
| `scene.s1.duration` | number | Accroche → durée (s) |
| `scene.s1.background` | media | Accroche → fond |
| `scene.s2.quote.text` · `scene.s2.quote.emphasis` | text · list | Citation → quote / mots mis en valeur |
| `scene.s2.author.text` | text | Citation → author |
| `scene.s2.duration` · `scene.s2.background` | number · media | Citation → durée / fond |
| `scene.s3.reveal.text` · `scene.s3.caption.text` | text | Signature → reveal / caption |
| `scene.s3.duration` · `scene.s3.background` | number · media | Signature → durée / fond |
| `signature.handle` | text | Signature → @pseudo |
| `signature.media` | media | Signature → logo |
| `audio.music` · `audio.voice` | media | Musique de fond / voix (voix-off) |

`suggest_mapping()` pré-câble une colonne quand son en-tête ressemble au nom du champ.

### 10.3 Politique — `shortvideos/batch.py:POLICY`

```python
POLICY = {
  "column_wins": True,
  "missing_named_file": "erreur bloquante pour la ligne",
  "rotation": "ordre trié des dossiers connectés, déterministe",
  "cycling": "le cycle reprend quand les ressources sont moins nombreuses que les lignes",
  "never": "aucun raccourcissement de texte, aucun chemin Windows dans un projet",
}
```

- **La colonne mappée gagne toujours** sur l'automatisme ; si elle nomme un fichier absent
  des dossiers connectés, la ligne est `blocked` avec une erreur explicite — **rien n'est
  substitué en silence**.
- **Rotation déterministe** : `_rotation(pool, position)` trie les assets, prend
  `position % len(pool)` et note la passe `(position-1)//len(pool)+1`. Les trois scènes
  partagent le même choix de fond pour la cohérence visuelle de la ligne.
- **Bouclage assumé** : le plan **avertit** quand les ressources sont moins nombreuses que
  les lignes (« chaque fichier sert au plus N fois »).
- **Musique** : bouclée ou coupée à la durée du projet, **jamais** accélérée
  (`playbackRate` interdit).
- **Texte trop long** : avertissement au-delà de `OVERFLOW_RATIO = 1.6` × la longueur du
  modèle ; le texte n'est jamais tronqué.
- **Graine** : `seed du modèle + index − 1` par ligne → variations reproductibles mais
  distinctes.
- **Noms de fichiers** : `%03d-<slug>.mp4` (slug sans accents, sans espaces, 60 caractères).

### 10.4 File — `server/queue.py`

| Point | Comportement |
| --- | --- |
| Fichier | `batch/queue.sqlite3`, mode WAL, accès par contexte `_db()` |
| Un seul lot actif | un second `start` renvoie **409** |
| Worker | thread secondaire, une ligne après l'autre, `render_project_to_mp4()` — la **même** fonction que l'export unitaire |
| Statuts ligne | `queued` · `running` · `done` · `failed` · `cancelled` · `blocked` |
| Progression | compteur de lignes rendues + progression de frame de la ligne courante |
| Sortie | `.part.mp4` puis remplacement atomique ; refus d'écraser sans `overwrite` |
| Annulation | `POST /api/batch/{id}/cancel` : ligne en cours interrompue, reste en file |
| Reprise | au démarrage, `recover()` remet les `running` en `queued` et le lot en `paused` ; **rien ne redémarre sans l'utilisateur** |
| Relance | `POST /api/batch/{id}/retry` ne re-queue que `failed` / `cancelled`, jamais les lignes déjà rendues |
| Suppression | `DELETE` refuse si le lot tourne et **ne supprime aucun MP4** |
| Historique | `GET /api/batch` (léger, compteurs) et `GET /api/batch/{id}?items=true` (lourd, à la demande) |

### 10.5 Manifeste de livraison

`write_manifest(batch_id, "json" | "csv")` écrit `batch/manifests/<id>-<nom>.<ext>` et renvoie
le chemin **produit par le serveur** — le frontend ne le construit jamais.

```
position, nom, fichier, statut, chemin, octets, frames, duree_s, fps,
fond, fond_source, fond_pass, musique, musique_source, musique_pass,
titres, avertissements, erreurs
```

CSV en `utf-8-sig` (BOM) pour Excel ; le JSON ajoute `batch` (mapping, options, horodatages),
`summary` (compteurs) et `policy` (règles appliquées). Les `titres` permettent de contrôler
une livraison sans ouvrir les vidéos.

**Le paquet client ne duplique pas ce calcul** : `server/delivery.py` appelle
`queue.write_manifest()` et **emballe les fichiers produits** dans le ZIP (`manifeste.json`,
`manifeste.csv`) — il n'existe pas un second format de manifeste (§8.10).

---

## 11. Médias, dossiers connectés, polices et connaissances

### 11.1 Médiathèque (`server/media.py`)

`POST /api/media/upload` vérifie le type MIME (images et vidéos, sinon **415**), 500 Mo
maximum, fichier vide refusé, puis stocke `media/<uuid>.<ext>`. `GET /api/media/{id}` sert le
fichier avec un identifiant validé (mauvais format ⇒ **400**, inconnu ⇒ **404**). Une
empreinte sha256 sert à la déduplication. Un ancien projet v1 qui référence des fichiers
absolus est **réimporté automatiquement** à l'ouverture, et cela est signalé dans le message
d'ouverture — jamais fait en silence.

### 11.2 Dossiers connectés (`server/folders.py`)

Enregistrement d'un chemin absolu dans `batch/folders.json` — une **racine de lecteur est
refusée** — avec type (`vidéos de fond` / `musiques` / `images` / `tout`), licence (vide ⇒
`inconnue`) et nom affiché. `POST /api/folders/{id}/scan` liste, déduplique par empreinte et
importe dans la médiathèque ; les compteurs et la date du dernier scan sont relus serveur.
Retirer un dossier du registre ne touche **pas** aux médias déjà importés.

### 11.3 Polices

5 familles **SIL Open Font License** dans `web/public/fonts/` (10 poids), cataloguées dans
`web/src/remotion/fontCatalog.json` — **un seul fichier lu à la fois par Python
(`shortvideos/fonts.py`) et par TypeScript (`web/src/remotion/fonts.ts`)**.
`preloadAllFonts()` est **attendue** avant toute mesure et tout rendu. Les polices Windows
installées ne sont jamais utilisées : leur licence ne permet ni de les servir ni de les
embarquer dans une livraison client.

### 11.4 Provenance et licence

`media/provenance/<uuid>.json` conserve `{source, licence, date}` saisis à l'import. Une
licence absente est affichée **`inconnue`** — un avertissement, jamais une validation — et
listée dans la préparation du rendu comme dans le bloc « Projet résolu ».

### 11.5 Paquet de connaissances Remotion

Voir §9.7. Accès borné à `skills/remotion/` par `server/skills.py` : ni traversée, ni lecture
hors du dossier ; lecture seule.

---

## 12. API, référence complète

Préfixe `/api` pour tout : **88 routes** (méthode + chemin, vérifié sur l'app FastAPI réel)
réparties dans les 15 routeurs, plus `GET /` et le SPA. « Client » = l'appelant réel dans
`web/src/api/client.ts` ou la route du serveur.

| Méthode + chemin | Rôle | Client |
| --- | --- | --- |
| `GET /api/health` | statut, clé Groq, `web_dist`, `queue_recovered` | monitoring, `start_web.bat` |
| `GET /api/projects` | liste des projets | Design (dialogue Ouvrir), Projets |
| `POST /api/projects` | enregistrer (nom borné, pas de traversée) | Design (Sauvegarder + autosave) |
| `GET /api/projects/{name}` | charger + valider + migrer les médias v1 | Design, Shorts v1 |
| `DELETE /api/projects/{name}` | supprimer | Projets |
| `POST /api/projects/validate` | erreurs / avertissements calculés en Python | Shorts v1, Design |
| `GET /api/studio/effects` | **catalogue des 25 effets** (`effects.manifest()` : catégories, portées, `max_per_target`, réglages typés et bornés) | Cockpit, Inspecteur (`EffectsSection`), Réglages ; l'assistant lit le même module en interne |
| `GET /api/studio/models` · `/fonts` · `/default` | catalogue des compositions, polices sous licence, projet neuf | Design |
| `POST /api/studio/prepare` | **résout + valide + sert les props du Player et du rendu** | Design |
| `POST /api/studio/upgrade` | conversion explicite v1 → v2 avec notes | Design |
| `POST /api/studio/inspect` | bloc `resolved` seul (frames, graine, ressources) | Design (Projet résolu) |
| `POST /api/studio/provenance` · `GET /api/studio/provenance/{id}` | source / licence / date d'un média | Design |
| `POST /api/media/upload` | import d'un média → `media/<uuid>.<ext>` | Design, Shorts v1, panneaux |
| `GET /api/media/{id}` | service limité | — |
| `POST /api/exports` | lance `remotion render` en sous-processus → `job_id` | ExportDialog |
| `GET /api/exports/{id}` | progression / statut / résultat | ExportDialog |
| `POST /api/exports/{id}/cancel` | terminaison + nettoyage du `.part.mp4` | ExportDialog |
| `GET /api/exports/{id}/file` | relecture du MP4 (chemin borné à `exports/`) | ExportDialog |
| `GET /api/jobs/{id}` · `POST /api/jobs/{id}/cancel` | suivi générique (export, clips, podcast, agent) | `lib/jobs.ts` |
| `GET /api/library` · `GET /api/library/{id}` | modèles + projet d'un modèle | Bibliothèque, Production, agent |
| `POST /api/library` · `DELETE /api/library/{id}` | enregistrer un projet comme modèle / retirer un modèle perso (intégrés protégés) | LibraryDialog, Bibliothèque |
| `GET /api/skills` · `/api/skills/{id}` · `/api/skills/doc/{chemin}` · `/api/skills/context` | paquet de connaissances en lecture seule | agent, Réglages |
| `GET/POST /api/folders` · `GET /api/folders/assets` · `POST /api/folders/{id}/scan` · `GET/DELETE /api/folders/{id}` | dossiers connectés, scan, inventaire | Production, agent |
| `GET /api/batch/setup` · `GET /api/batch/fields` · `POST /api/batch/csv` · `GET /api/batch/csv/{id}` | modèles v2, politique, champs adressables, import/lecture CSV | Production |
| `POST /api/batch/plan` · `POST /api/batch/line` | plan complet du lot, ligne résolue en JSON | Production |
| `POST /api/batch/start` · `GET /api/batch` · `GET/DELETE /api/batch/{id}` · `POST /api/batch/{id}/start` · `/cancel` · `/retry` | file persistante : création, historique, détail, reprise, annulation, relance des échecs, retrait | Production |
| `GET /api/batch/{id}/manifest` · `/manifest/file` · `GET /api/batch/{id}/file?position=N` | manifeste JSON/CSV (`attachment`) et relecture d'une ligne rendue | Production |
| `GET /api/delivery/{batch_id}` | état du lot vu de la livraison : compteurs, `is_packaging`, paquet existant (taille, date, vidéos/sous-titres/miniatures, avertissements), lignes | Livraison |
| `POST /api/delivery/{batch_id}/package` | lance l'assemblage du ZIP **dans un job** ; **409** si un paquet est déjà en cours pour ce lot, **400** si `rendered == 0` ; renvoie `{job_id, items}` | Livraison (« Préparer le paquet ») |
| `GET /api/delivery/{batch_id}/package/file` | `FileResponse` du ZIP, `application/zip` ; le nom vient du serveur (`package_path`), **404** si le paquet n'existe pas | Livraison (lien de téléchargement) |
| `GET /api/brands` · `GET /api/brands/{id}` | liste des packs (`brands/*.json`, un illisible ressort en `unreadable`) et détail d'un pack | Design (« Packs ») |
| `POST /api/brands` | enregistre un pack après `branding.normalize()` ; **les erreurs bloquent l'écriture** ; id passé par `slugify` | Design |
| `POST /api/brands/capture` | construit le pack **avec ce que le projet v2 affiche déjà** (`from_project`) puis l'enregistre ; refusé sur un projet v1 ou sans nom de client | Design (« Créer depuis ce projet ») |
| `POST /api/brands/{id}/apply` | renvoie `{project, warnings}` : **aucune route n'écrit dans un projet de travail** | Design (« Appliquer au projet ») |
| `DELETE /api/brands/{id}` | retire le fichier du pack | Design |
| `GET /api/settings` · `POST /api/settings` | réglages ; la clé n'est **jamais** renvoyée | Réglages, Clips |
| `POST /api/clips/info` · `/download` · `/analyze` · `/extract` | téléchargement, analyse Groq, extraction FFmpeg | Clips |
| `GET /api/clips/sessions` · `/sessions/{sid}` · `DELETE /sessions/{sid}` · `GET /files/{sid}/{name}` | sessions, relecture, nettoyage | Clips |
| `GET /api/podcast/stats` · `/clips` · `POST /videos` · `/generate` · `/legacy/import` · `GET /files/{rel_path}` | base de phrases, recherche, assemblage, import de l'ancienne base | Podcast |
| `GET /api/agent/status` · `/capabilities` | état effectif + manifeste des capacités | Réglages, `AgentPanel` |
| `POST /api/agent/index` | reconstruction de l'index FTS5 | Réglages / SourcesPanel |
| `POST /api/agent/check` · `POST /api/agent/models` | test réel du fournisseur, modèles réellement accessibles | Réglages |
| `POST /api/agent/search` | recherche dans les connaissances | `SourcesPanel` |
| `POST /api/agent/ask` | lance une demande (job 6 étapes) | `AgentPanel` |
| `GET /api/agent/proposals/{id}` (candidat seulement avec `?preview=true`) · `POST …/accept` · `POST …/reject` | contrat des propositions | `AgentPanel` |
| `GET /` + SPA | sert `web/dist`, `/fonts/…` et `/media-cache/…` | navigateur |

---

## 13. Frontend en interne

| Module | Ce qu'il impose |
| --- | --- |
| `api/client.ts` (892 l.) | **contrat typé unique** : aucune route appelée en dehors ; `apiErrorMessage()` normalise les erreurs — **y compris un `detail` texte simple**, un objet `{message, errors}` ou une liste ; `Proposal`, `AgentStatus`, `PrepareResponse`, `BatchPlan`, `LlmPublic`, `SettingsPublic`, `EffectsManifest`, `DeliveryStatus`, `BrandPackData` / `BrandPackSummary` |
| `lib/navigation.ts` (122 l.) | la navigation est **des données**, pas du JSX dupliqué : `NAV_GROUPS` porte `to / label / icon / description`, et la barre latérale comme la palette en découlent |
| `lib/assistant.tsx` (172 l.) | l'assistant est un **contexte**, pas un composant de page : `useAssistant()` (open / toggle / `ask` / data) + `usePublishAssistant(ctx, handlers)` ; aucune page ne monte son propre `AgentPanel` |
| `lib/jobs.ts` (99 l.) | `call()` (fetch, `HttpError` typé), `useJobPolling()` (borné, arrêt au démontage), `cancelJob()`, `formatBytes()`, `formatDuration()` |
| `components/AssistantDock.tsx` (134 l.) | colonne **dans le flux** (jamais par-dessus l'inspecteur), rail de 26 px fermé, contenu monté en permanence, `Échap` ferme |
| `components/CommandPalette.tsx` (211 l.) | `Ctrl+K` : recherche sur les mêmes données de navigation + projets + modèles, clavier complet, aucune commande qui n'existe pas ailleurs |
| `components/job-status.tsx` | `JobStatus` = barre + message d'étape + **Annuler** ; `ErrorNote` = traceback replié |
| `components/ui/*` | 7 primitives (button, badge, input, label, progress, slider, switch) — Radix + cva, aucune autre dépendance d'UI |
| `index.css` | helpers partagés `.panel`, `.panel-title`, `.input-base`, `.field-label` ; thème sombre sobre, états actif / désactivé / chargement / erreur / succès |
| `pages/design/edit.ts` (246 l.) | manipulations **pures** du projet + historique borné (undo/redo, geste de frappe groupé) |
| `pages/design/measure.ts` | mesure du débordement dans le navigateur avec la police réelle |
| `pages/design/BrandPacksDialog.tsx` (201 l.) | un pack de marque **s'applique par l'éditeur** : le dialogue demande `{project, warnings}` au serveur puis appelle le `onApply` de la page ; aucune écriture serveur dans `projects/` |
| `pages/LivraisonPage.tsx` (242 l.) | la page ne devine pas : elle lit `deliveryStatus`, suit le job d'assemblage avec `useJobPolling`, relit l'état à la fin, et ne propose un téléchargement que si le ZIP est retourné par le serveur |
| `remotion/registry.tsx` | `MODEL_REGISTRY` : un id de composition → un composant, **utilisé par le Player et par `remotion render`** |
| `remotion/effects/registry.ts` | les ids **réellement rendus** ; testé contre le catalogue serveur (§6.4) |
| `remotion/QuoteCinematic.tsx` | 3 scènes, fonds image/vidéo (`OffthreadVideo`), calques animés, **chaîne d'effets calque → scène → overlay**, deux pistes `<Audio>` (musique en boucle + voix) |

Un seul build, une seule origine. Mesuré après la tranche « Livraison commerciale »
(`tsc --noEmit` sans sortie, `vite build` : **1 714 modules transformés en 22,14 s**) :
`dist/assets/index-*.js` **910,6 kB — 889,2 KiB — (277,5 kB gzip)** et `index-*.css`
**27,6 kB — 27,0 KiB — (5,7 kB gzip)** ; Vite et `wc -c` ne divisent pas pareil, les deux sont
donnés. Vite remonte seulement un avertissement de taille de chunk (> 500 kB), aucune erreur.

---

## 14. Sécurité

| Contrôle | Comportement vérifié | Où |
| --- | --- | --- |
| Écoute | `127.0.0.1` par défaut, rien publié sur Internet | `server/settings.py`, `app.py` |
| Origine | `POST`/`PUT`/`DELETE`/`PATCH` d'une origine étrangère ⇒ **403** | `security.check_origin`, middleware |
| Chemins | **11 racines** autorisées (`ALLOWED_DIRS`, dont `brands/` et `batch/deliveries/`) ; hors de ces racines ⇒ **400** ; aucun chemin Windows en URL, médias = `/api/media/<uuid>` | `security.assert_local_dir` |
| Traversée | `../`, chemins encodés, identifiants invalides ⇒ **400/404** ; un id de pack refuse `/ \ . :`, un id de lot doit être alphanumérique | `security.safe_name`, `api/brands._check_id`, `api/delivery._check_id`, tests |
| Média de marque | un pack ne peut porter **ni chemin ni URL** : seule la forme `media://<id>` est acceptée pour un logo ou une musique | `branding._check_ref`, `tests/test_branding.py` |
| Paquet de livraison | assemblé dans un **job** (jamais dans le thread de requête), **un seul paquet à la fois par lot** (verrou + **409**), écriture `.part.zip` puis remplacement atomique, dossier temporaire de miniatures supprimé dans le `finally` même en cas d'annulation ; le nom du ZIP est retrouvé serveur, le client ne propose jamais un chemin | `server/delivery.py`, `api/delivery.py` |
| Upload | types MIME image/vidéo uniquement (sinon **415**), 500 Mo max, fichier vide refusé | `media.py` |
| Threads | aucun traitement lourd dans le thread de requête : exports et agent = jobs / sous-processus | `jobs.py`, `queue.py` |
| Clés API | restent côté serveur ; `GET /api/settings` ne renvoie que des booléens ; rien dans les logs | `settings.py`, `api/settings.py` |
| Dossiers disque | une **racine de lecteur** est refusée à l'enregistrement | `folders.py` |
| LLM | ni shell, ni `eval`/`exec`, ni chemin disque choisi par le modèle, ni écriture de fichier, ni suppression, ni lancement sans clic | `tools.describe()["forbidden"]`, `proposals.py` |
| CSV / documents | traités comme des **données**, avec clause anti-injection dans le prompt | `context.py` |
| `resolved` | un bloc fourni par le LLM est **toujours retiré** | `proposals._forced_resolved` |
| Écrasement | MP4 ou projet existant non remplacé sans règle explicite (**409** puis confirmation) | `render.py`, `api/exports.py` |

Les 16 tests de `tests/test_api.py` couvrent ensemble routes et sécurité : origine étrangère
**et origine distante qui se déclare locale**, traversée, upload, identifiants invalides,
clé jamais renvoyée.

---

## 15. Tests, vérifications et mesures réelles

```bat
cd /d E:\youtube\youtube_clipper
python -m pytest tests -q        →  152 passed, 2 warnings
```

| Fichier | Tests | Couvre |
| --- | --- | --- |
| `tests/test_effects.py` | 18 | catalogue : unicité des 25 ids, bien-fondé des params, `normalize()` (formes courte et réglée, id inconnu, doublon, portée, cible, cap de 4, écrêtage, audio absent), cohérence **catalogue ↔ ids rendus dans `registry.ts`**, route `/api/studio/effects`, prompt et capacités, outil `list_effects`, opérateur `set_effects` |
| `tests/test_validation.py` | 16 | validation, chemins avec espaces, bornes, versions, roundtrip JSON |
| `tests/test_api.py` | 16 | routes + sécurité (origine locale acceptée / étrangère et auto-déclarée refusées, traversée, upload, clé jamais exposée) |
| `tests/test_timing.py` | 15 | durées, frames, fondus, glissements, zoom |
| `tests/test_batch_plan.py` | 14 | rotation, passes, cycle, colonnes qui gagnent, lignes bloquées, graines, noms |
| `tests/test_agent_flow.py` | 11 | bout en bout avec un LLM maquillé : proposition puis application à l'acceptation, **rien n'est écrit avant l'acceptation**, effet inventé refusé avec message réparable, conflit pendant la génération puis rebase, `library_save`, `batch_plan` (et refus d'une colonne absente du CSV), `question`, réponse mal formée réparée, refus quand le serveur LLM n'est pas configuré, rejet qui laisse le projet intact |
| `tests/test_skills_api.py` | 10 | paquet de connaissances, bornes de lecture |
| `tests/test_folders.py` | 10 | enregistrement, refus racine de lecteur, scan, déduplication |
| `tests/test_batch_queue.py` | 10 | file SQLite, annulation, retry des échecs, `recover` |
| `tests/test_export_short.py` | 8 | export réel + comparaison frame à frame |
| `tests/test_delivery.py` | 10 | **les cues suivent `resolve()`** (mêmes frames que le rendu), scènes et calques masqués ignorés, durée minimale garantie quand la sortie dévore l'entrée, fichier SRT indexé et tout-CRLF (cue multiligne compris), projet sans texte visible ⇒ chaîne vide, miniature extraite **sur une vraie vidéo**, miniature absente ou déjà présente ⇒ avertissement et non échec, **assemblage complet d'un ZIP** (vidéo + `.srt` + manifestes + `LISEZ-MOI`, aucun `.part.zip` résiduel) |
| `tests/test_branding.py` | 11 | pack sain accepté avec le superflu signalé, **chemin / URL / couleur / police hors catalogue refusés** (4 cas paramétrés), modèle hors liste refusé, `apply_brand` n'écrit que dans `theme` / `signature` / `audio`, avertissement si la signature est désactivée, réactivation quand le pack force `enabled`, aller-retour du store `brands/` et **aucun écrit pour un pack invalide** |
| `tests/test_batch_api.py` | 3 | routes de lot, manifeste, service de fichier borné |

**Mesures déjà obtenues sur ce poste** (exécutées, pas déduites) :

- export unitaire 1080×1920 / 30 fps / **405 frames** / 13,5 s, 832 Ko, terminé ;
- `verif-audio.mp4` : piste `aac (LC) 48 kHz stéréo`, gain mesuré **−9,1 dB** pour
  `music_volume: 0.35` ;
- lot de 3 lignes rendu de bout en bout depuis `/production` (`001-discipline.mp4`,
  `002-curiosite.mp4`, `003-patience.mp4`), manifestes CSV et JSON téléchargés ;
- **rendu réel avec effets** : `exports/_smoke-effects.mp4`, **540×960 / 30 fps /
  228 frames / 7,6 s / 1 690 947 octets**, sonde avec `shortvideos.probe.probe_mp4()`.
  Le projet de fumée faisait porter à chaque cible le maximum autorisé (4 effets) et
  **chacun des 25 ids du catalogue apparaissait au moins une fois** ; aucun échec de
  composition, aucun filtre SVG malformé, aucun arrêt de rendu. Le MP4 reste dans `exports/`
  comme preuve mesurée ; le script de fumée et ses captures intermédiaires sont rangés hors du
  projet, dans `E:\youtube\_sauvegarde_smoke_20261104\` ;
- frontend construit sans erreur TypeScript, page `/design`, `/production`, `/library`,
  `/clips`, `/podcast`, `/short-videos`, `/projects`, `/settings` testées dans le navigateur
  avec **0 erreur console** ; la page `/` (cockpit) et le tiroir assistant global (`Ctrl+I`)
  également ouverts et inspectés dans le navigateur local ;
- index de connaissances : **110 documents / 548 sections**, FTS5 actif.

**Vérifications de l'assistant — ce qui est simulé et ce qui est réel** :

| Vérification | Nature |
| --- | --- |
| Contrat `batch_plan` : colonnes injectées comme données, bloc `CONTEXTE PRODUCTION PAR LOTS` présent, `PROJET ACTIF` absent en mode production, champ inventé rejeté, `accept()` renvoie `{model, mapping, options, notes, fields}` **sans `job_id`** | **simulée** — `llm_client.chat` maquillé, aucun appel réseau ; couvert en permanence par `tests/test_agent_flow.py` (le script ponctuel `_verif_prod.py` est retiré) |
| Pipeline `ask` → `validate` → `accept` / `reject`, bornes d'outils, retrait d'un bloc `resolved`, effet inventé refusé, conflit pendant la génération | **simulée** (mock `llm_client.chat`) — **11 tests** dans `tests/test_agent_flow.py` |
| « accept → application dans l'éditeur » cliquée dans le navigateur | **non exécutée** sur ce poste : `GET /api/agent/status` renvoie `ready: false` (« L'assistant IA est désactivé ») et `server/settings.py` n'a **aucune variable d'environnement** de secours — activer un LLM imposerait de modifier le `settings.json` de l'utilisateur. Le contrat est donc garanti par les tests, pas par une capture de clic. |
| Un appel **réel** au serveur local configuré, réponse JSON contractuelle acceptée | **réel**, exécuté une seule fois (pas de répétition d'appels identiques) |
| Gemini / Groq | **aucun appel réel effectué** : seule la construction d'URL, du catalogue et du test a été vérifiée en local |

---

## 16. Limites connues

1. **Mono-poste, mono-utilisateur** : pas de comptes, pas de file partagée.
2. **Un seul lot actif** à la fois (second lancement ⇒ 409).
3. **2 000 lignes CSV maximum** (`MAX_ROWS`) ; au-delà, découper le fichier.
4. **Un seul modèle cinématique v2** en production (`citation-cinematique`) ; `quote_vertical`
   reste v1.
5. **Sortie verticale uniquement** en pratique : les cadres non 9:16 ne sont pas testés.
6. **L'arabe et l'écriture `rtl`** sont décrits dans le format (`DIRECTIONS`) mais **pas testés**
   : ils ne sont donc pas annoncés comme pris en charge.
7. **Les 25 effets sont rendus sans paquet supplémentaire** : tout est écrit avec ce qui est
   déjà installé (Transform / `filter` CSS, filtres SVG, masques, canvas 2D,
   `@remotion/paths`, `@remotion/media-utils`) parce que la règle du projet est
   « aucune installation automatique de dépendances ». Ce que cela exclut, noir sur blanc :
   - **pas de vraie 3D** : `@remotion/three` et `three` ne sont pas installés —
     `perspective_dolly`, `parallax_depth`, `cylinder_wrap` et `sphere_wrap` sont des
     transformations CSS 3D (`perspective`, `rotateY`, `translateZ`) sur des plans, pas de la
     géométrie ;
   - **pas de morphing vectoriel libre** : `flubber` n'est pas installé — `path_morph`
     n'interpole que deux tracés **de même nombre de segments**, via `interpolatePath()` de
     `@remotion/paths`. Le serveur ne compare pas les segments : si les deux tracés sont
     incompatibles, le composant **n'affiche rien** (`try/catch` autour de
     `interpolatePath`, `overlay.tsx:191`) au lieu d'inventer une forme ou de casser le
     rendu ; la règle est donc une contrainte d'auteur, pas une validation ;
   - **pas de coloration syntaxique installée** : `prismjs` et `shiki` ne sont pas installés —
     `code_type` utilise un **tokenizer maison** (`overlay.tsx:489`) qui reconnaît chaînes,
     commentaires, nombres et une liste de mots-clés Python/JS, avec deux thèmes (`sombre`,
     `clair`). Ce n'est pas une analyse grammaticale complète : un langage absent de la liste
     n'est coloré que sur ses chaînes et ses commentaires ;
   - **pas de LUT externe** : aucun fichier `.cube` n'est lu — `color_grade` est une chaîne de
     filtres SVG (`feColorMatrix` saturation, `feComponentTransfer` linéaire pour exposition et
     contraste, puis `feFunc*` `type="table"`) alimentée par les tables **embarquées** dans
     `LOOK_TABLES` (`scene.tsx:17`) et chaînées dans `GradeDefs` (`scene.tsx:85`) ;
   - **pas de WebGL ni de shader** : les distorsions passent par des **filtres SVG**
     (`liquid_contours` = `feTurbulence type="fractalNoise"` + `feDisplacementMap`, `scene.tsx:51`,
     animé par la frame et non par un timer) ou par du **canvas 2D** (`plasma_field`,
     `overlay.tsx:231` ; `chroma_key`, `image.tsx:43`). Tout reste sur le CPU : cumuler plusieurs
     overlays coûte du temps de rendu ;
   - **les 3 effets `needs_audio`** (`audio_pulse`, `audio_spectrum`, `audio_waveform`) ne
     bougent que si un fichier audio réel est présent et audible ; sans audio, `normalize()`
     avertit et le rendu reste statique.
   Le bloc ETAT DU PROJET rappelle ces bornes à l'agent, qui ne peut proposer que ce qui
   existe.
8. **Le montage audio automatique n'existe pas** : pas de beat-matching, pas de
   transcription-forcée, pas de ducking dynamique — seulement bouclage, rognage et fondus.
9. **Groq de Clips ≠ assistant** : deux configurations séparées, la reprise est explicite.
10. **Pas de basculement local ↔ cloud automatique.**
11. **`server/settings.json` est en clair sur le disque local** (poste mono-utilisateur) ;
    il ne sort jamais par HTTP.
12. **Projet non versionné** : la règle « sauvegarde avant suppression » est le seul filet.
13. **`recover()` ne relance rien** : un lot interrompu reste `paused` jusqu'à un clic.
14. **Pillow n'est plus un moteur** : il ne sert qu'à la mesure v1 et à un test.
15. **OpenCV/`ffmpeg -i` remplacent ffprobe** : la probe lit conteneur et flux, pas la
    bibliographie technique complète.
16. **La mesure de débordement est approchée** : elle avertit, elle ne garantit pas le
    typographique exact d'une fonte non mesurée.
17. **L'assistant ne voit pas l'image** : il raisonne sur le JSON, les capacités et les
    documents, jamais sur les frames rendues.
18. **Les sous-titres livrés ne sont pas une transcription de la voix** : `srt_from_project`
    reprend le **texte des calques réellement affichés**, avec les fenêtres de `resolve()`. Il
    n'y a **aucune reconnaissance vocale** dans la chaîne de livraison — ni Whisper ni un autre
    moteur ASR, parce qu'installer une dépendance sort du cadre décidé (« aucune installation
    automatique de dépendances »). Une vidéo dont la parole n'est pas écrite dans les calques
    reçoit donc un `.srt` partiel, ou aucun — la page Livraison affiche alors l'avertissement
    « aucun texte sous-titrable » au lieu de produire un fichier vide.
19. **Le paquet ZIP ne porte pas de copywriting** : il contient les vidéos, les `.srt`, les
    miniatures, le manifeste (dont les `titres` déjà saisis dans le CSV) et un `LISEZ-MOI`
    technique. Les descriptions et hashtags pour les plateformes ne sont **pas générés** — le
    manifeste ne fait que restituer les colonnes du CSV, il n'invente pas de texte.
20. **Un pack de marque n'est pas un gabarit de mise en page** : il porte `theme`, `signature`,
    `audio` et une liste de modèles autorisés, **pas** les scènes, les calques ni le texte —
    c'est ce qui le distingue d'un modèle de la bibliothèque (`models/`). Un projet v1 ne peut
    ni servir de pack ni en recevoir (**400**).
21. **Un seul paquet par lot** : le nom du ZIP est dérivé de `(id, nom du lot)`, préparer à
    nouveau écrase le paquet précédent (après `.part.zip`), et une préparation déjà en cours est
    refusée par **409**. Il n'existe pas d'historique des paquets d'un même lot.

---

## 17. Étendre le studio, recettes

| Objectif | Étapes exactes |
| --- | --- |
| **Nouveau modèle v2** | ajouter l'id dans `shortvideos/schema.py:MODELS` + son gabarit (`new_project`) ; écrire le composant dans `web/src/remotion/` ; l'enregistrer dans `registry.tsx` ; exposer les scènes/rôles pour que `fillable_fields()` le découvre ; `npm run build` ; `POST /api/agent/index` si le manifeste doit changer |
| **Nouvelle police** | déposer le TTF + `OFL.txt` dans `web/public/fonts/…` ; l'ajouter à `fontCatalog.json` (lu par Python et TS) ; vérifier `preloadAllFonts()` |
| **Nouveau champ adressable par le CSV** | le rendre lisible par `fillable_fields()` (il est découvert dans le modèle : inutile de modifier `batch.py`) ; le consommer dans la composition |
| **Nouvel outil de lecture pour l'assistant** | l'ajouter à `tools.READ_TOOLS` + une branche dans `tools.execute()` avec ses bornes ; le décrire dans `TOOL_DESCRIPTION` ; le rendre visible par `capabilities.build()` |
| **Nouveau type de proposition** | `proposals.PROPOSAL_TYPES` + un validateur dédié (liste blanche de clés, rejet réparable) ; `accept()` dans le panneau concerné ; **jamais** d'exécution sans clic |
| **Nouvelle route** | `server/api/<module>.py`, inclus dans `app.py` ; bornage `assert_local_dir` si disque ; ajout du type dans `web/src/api/client.ts` ; appel depuis la page |
| **Nouvel effet** | 1. fiche `_fx(id, label, catégorie, scopes, description, params, targets=…, needs_audio=…, note=…)` ajoutée à `EFFECTS` dans `shortvideos/effects.py` — c'est elle qui fixe les bornes, et `manifest()`, `list_effects`, le prompt de l'agent et la section Effets de l'Inspecteur en découlent **sans autre modification** ; 2. l'id dans la liste de portée correspondante de `web/src/remotion/effects/registry.ts` (`LAYER_EFFECT_IDS`, `IMAGE_EFFECT_IDS`, `SCENE_EFFECT_IDS`, `OVERLAY_EFFECT_IDS`) ; 3. le composant : une branche dans `LAYER_HANDLERS` (`layer.tsx:317`), `OVERLAY_COMPONENTS` (`overlay.tsx:569`), `image.tsx` ou un `pickFirst` dans `SceneEffects` (`scene.tsx:156`) — les `Record<EffectId, …>` **empêchent la compilation** si l'implémentation manque ; 4. rien à écrire dans `tests/test_effects.py` : `test_registry_ts_implements_exactly_the_catalog()` compare déjà les deux listes. Puis `npm run build` et `python -m pytest tests -q` |
| **Nouvelle page** | une entrée `{to, label, icon, description}` dans le bon groupe de `NAV_GROUPS` (`web/src/lib/navigation.ts:33`) + une `<Route>` dans `App.tsx` : la barre latérale **et** la palette `Ctrl+K` la découvrent seules, il n'existe aucune liste de liens à maintenir deux fois. Si la page doit parler à l'assistant, `usePublishAssistant(ctx, handlers)` ; sinon le tiroir affiche son `applyHint` au lieu de promettre une application. Pas de bouton simulé : soit fonctionnel, soit absent |
| **Nouveau paquet de connaissances** | déposer dans `skills/remotion/<paquet>/`, enregistrer dans `PROVENANCE.md`, éventuellement un extracteur rejouable dans `tools/`, puis `POST /api/agent/index` |
| **Nouvelle pièce dans le paquet de livraison** | l'ajouter dans la boucle de `server/delivery.py::build_package` (un fichier par ligne rendue) et le compteur correspondant dans `counts` + l'état écrit dans `.package.json` ; **ne pas recalculer une donnée déjà produite** : les `.srt` viennent de `shortvideos/delivery.srt_from_project` (donc de `resolve()`), les manifestes de `queue.write_manifest()`. Une pièce facultative (miniature) doit **avertir, pas échouer** |
| **Nouveau champ dans un pack de marque** | il doit **exister dans le format de projet** : l'ajouter aux clés de `schema.default_theme()` / `default_signature()` ou à `AUDIO_KEYS`, puis à `_check_section` (type + borne + message d'erreur en français) et à `apply_brand` ; un projet passé par le pack doit rester validable par `validation.validate_project` |

Règles à ne pas casser en étendant : une seule entrée de rendu ; pas de chemin Windows dans
un projet ; pas de `resolved` persisté ; licence inconnue affichée comme inconnue ; rien
d'automatique côté agent sans clic ; `tsc --noEmit` et `pytest` passent avant toute
livraison.

---

## 18. Dépannage

| Symptôme | Cause probable | Vérification |
| --- | --- | --- |
| Le navigateur s'ouvre sur une page morte | uvicorn n'a pas démarré (build ou Python) ; le lanceur n'ouvre plus la page avant que `/api/health` réponde | relire la console de `start_web.bat` ; `curl http://127.0.0.1:8000/api/health` ; sans `--open`, ouvrir l'URL à la main |
| « Frontend non construit » | `web/dist/index.html` absent ou build interrompu | `cd web && npm run build` (le PATH Node est celui de `_tools\node`) |
| Erreurs TypeScript bloquantes | `noUnusedLocals` / `strict` dans `tsconfig.json` | `npx tsc --noEmit` |
| Export qui échoue sans détail | sortie du sous-processus tronquée | les 25 dernières lignes sont dans `job.error` ; un `exports/props-*.json` restant = rendu en cours |
| Fichier existant refusé | **409** voulu par la règle d'écrasement | cocher « écraser les fichiers existants » ou confirmer « Remplacer » |
| Texte coupé / débordant | mesure faite avant chargement des polices | vérifier `fontsReady` ; le badge « polices… » doit avoir disparu |
| « Aucun média » dans un lot | dossier non scanné ou fichier nommé absent du CSV | re-scan (`POST /api/folders/{id}/scan`) ; la ligne est `blocked` avec le nom manquant |
| Lot interrompu reste `paused` | `recover()` volontairement passif | bouton **Reprendre** ou **Relancer les échecs** |
| « Préparer le paquet » grisé | `rendered == 0` dans le lot — rien à empaqueter | lancer le lot depuis Production ; la page affiche « Aucune vidéo rendue dans ce lot : rien à livrer. » |
| **409** à la préparation | un paquet est déjà en cours pour ce **même lot** (verrou serveur) | attendre la fin du job ; un second clic est refusé par conception |
| « Paquet introuvable : préparez le livrable. » (404 au téléchargement) | le ZIP n'existe pas (préparation jamais lancée, échouée, ou lot renommé depuis) | relire `GET /api/delivery/{batch_id}` ; le nom du paquet dépend de `(id, nom du lot)` |
| ZIP sans `.srt` pour une ligne | la ligne n'a aucun **calque texte visible** (pas de transcription automatique de la voix — limite 18) | l'avertissement « aucun texte sous-titrable » est dans `LISEZ-MOI.txt` et sur la carte du paquet |
| Miniatures absentes | FFmpeg local en échec sur ce MP4 (une miniature ratée **ne bloque pas** le paquet) | lire les avertissements du paquet ; vérifier que le MP4 est relisible (`shortvideos.probe`) |
| Pack de marque refusé à l'enregistrement | `branding.normalize()` pose une **erreur** : chemin ou URL à la place d'un `media://`, couleur hors `#RRGGBB`, police absente du catalogue, modèle inconnu | la liste des erreurs s'affiche dans le dialogue ; corriger, pas forcer — un pack invalide n'est **jamais** écrit dans `brands/` |
| « le logo du pack ne s'affichera pas » | le projet a `signature.enabled = false` et le pack impose un logo sans réactiver la signature | réactiver la signature dans l'Inspecteur, ou enregistrer un pack avec `signature.enabled = true` |
| pytest : `PermissionError WinError 5` | TMP Windows refusé | `pytest.ini` force `--basetemp=.pytest_tmp` |
| Assistant « non configuré » | `llm_enabled` faux, ou base URL vide, ou modèle absent | panneau Assistant de Réglages : **Vérifier la connexion**, puis **Actualiser les modèles** |
| `unavailable` en réponse | l'assistant n'a pas la capacité demandée | lire « Ce que l'assistant peut toucher » ; **ne pas** étendre le contrat pour forcer une réponse |
| Échec du test de fournisseur en local | serveur LLM arrêté ou route `/chat/completions` absente | l'application reste utilisable sans l'assistant : c'est le comportement attendu |
| Clé perdue / à remplacer | — | « Effacer la clé » (demande explicite), puis resaisie ; jamais de renvoi de clé au navigateur |

