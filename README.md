<div align="center">

# shorts-studio

**Le studio vidéo local qui transforme une phrase en vidéo prête à publier.**
Motion design, production par lots, montage footage, voix off, sous-titres et assistant IA —
le tout sur votre machine, sans cloud obligatoire, sans rien faire dans votre dos.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-467%20passed-brightgreen.svg)](#tests--vérifications)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](#stack-technique)
[![Node](https://img.shields.io/badge/node-22-green.svg)](#stack-technique)
[![Remotion](https://img.shields.io/badge/Remotion-4.0.539-ff69b4.svg)](#stack-technique)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688.svg)](#stack-technique)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](#stack-technique)
[![Local first](https://img.shields.io/badge/local--first-aucun%20cloud%20obligatoire-orange.svg)](#les-4-lois-du-studio)

*Interface web · serveur `127.0.0.1` · un seul lanceur : `start_web.bat`*

</div>

---

## En une phrase

> Vous décrivez la vidéo que vous voulez. L'assistant prépare le projet, l'autopilote le rend
> en MP4, le studio le décline en 200 exemplaires depuis un CSV, l'assemble en montage footage
> réel, le sous-titre, le décline aux formats sociaux et le livre en ZIP au client.
> **Vous gardez la main sur chaque clic sensible.**

`shorts-studio` (dossier `youtube_clipper`) est un **studio de production vidéo complet, local
et autonome**. Il réunit dans une seule application web ce qu'on disperse habituellement entre
After Effects, un outil de sous-titres, un moteur TTS, un script de batch et un assistant IA :
un éditeur visuel, un moteur de rendu déterministe, une file de production, un assistant qui
connaît le studio par cœur, et une chaîne de livraison commerciale.

---

## Un projet original, entièrement remodelé

`shorts-studio` est **mon projet : mon architecture, mon code, ma direction**. Remotion et
OpenMontage ont servi de point de départ — l'un comme moteur de rendu, l'autre comme grammaire
de production — mais **tout a été remodelé, réarchitecturé et réécrit** pour former un studio
cohérent qui m'appartient en propre :

- le **format de projet v2** et sa résolution déterministe sont conçus pour ce studio ;
- les **25 effets**, le moteur de sous-titres, la voix off, le B-roll et les formats sociaux sont
  des implémentations maison ;
- l'**assistant IA**, son contrat de propositions, ses 32 outils et son autopilote sont écrits
  sur mesure, sans framework IA lourd ;
- le **moteur de montage footage** (contrat EDL + assemblage FFmpeg en trois passes) est une
  implémentation originale : aucun code exécutable d'OpenMontage n'est copié.

Remotion reste une bibliothèque tierce utilisée sous sa propre licence ; la grammaire OpenMontage
n'est conservée qu'en **lecture seule, en local**, comme simple référence documentaire
(voir [Licence](#licence)). Le studio, lui, est une œuvre originale et propriétaire — pas un
wrapper, pas une copie.

---

## Sommaire

- [Un projet original, entièrement remodelé](#un-projet-original-entièrement-remodelé)
- [Pourquoi ce studio ?](#pourquoi-ce-studio-)
- [Ce que vous pouvez faire](#ce-que-vous-pouvez-faire)
- [L'autopilote : une demande → un MP4](#lautopilote--une-demande--un-mp4)
- [L'assistant IA : il propose, vous appliquez](#lassistant-ia--il-propose-vous-appliquez)
- [Le montage footage : EDL → FFmpeg](#le-montage-footage--edl--ffmpeg)
- [Les 4 lois du studio](#les-4-lois-du-studio)
- [Stack technique](#stack-technique)
- [Démarrage rapide](#démarrage-rapide)
- [Architecture](#architecture)
- [Sécurité](#sécurité)
- [Tests & vérifications](#tests--vérifications)
- [Structure du projet](#structure-du-projet)
- [Limites connues](#limites-connues)
- [Licence](#licence)
- [Documentation complète](#documentation-complète)

---

## Pourquoi ce studio ?

Ce qui distingue `shorts-studio` d'un énième « générateur de vidéos IA » :

| Point fort | Ce que ça change concrètement |
| --- | --- |
| **Œuvre originale et propriétaire** | Architecture, format v2, effets, assistant, moteur EDL/FFmpeg : tout est conçu et réécrit pour ce studio. Remotion et OpenMontage ne sont que des fondations remodelées — pas le produit. |
| **Local-first, sans cloud obligatoire** | Tout tourne sur `127.0.0.1`. Vos rushes, vos textes, vos clés API ne quittent pas la machine. Aucun compte, aucun abonnement, aucune télémétrie. Le studio reste **entièrement utilisable même si le serveur LLM est éteint**. |
| **Le plan affiché est exactement ce qui est rendu** | L'aperçu Remotion Player et le rendu CLI partagent **la même composition**. Pas de surprise « ce n'était pas ça à l'écran ». Une seule entrée de rendu, un seul moteur. |
| **L'IA propose, l'humain applique** | L'assistant ne déclenche **jamais** un rendu, une suppression, un lot ou un téléchargement sans un clic. Chaque action sensible passe par un jeton de confirmation et une re-vérification de fraîcheur. |
| **Déterministe et reproductible** | Le bloc `resolved` (frames, fenêtres d'animation, polices, graine) est calculé côté serveur, jamais par le LLM. Même projet + même graine = même vidéo, à la frame près. |
| **Zéro dépendance lourde installée en douce** | Pas de LangChain, pas de SDK OpenAI, pas d'ORM, pas de Docker. L'assistant parle l'API OpenAI-compatible en `httpx` brut. Whisper local est **détecté, jamais installé**. |
| **Un vrai pont footage, pas un gadget** | Le montage réel (rushes, transitions, musique, étalonnage) passe par un contrat EDL fermé puis FFmpeg. Remotion reste le moteur du motion design. Chaque moteur fait ce qu'il fait de mieux. |
| **Pensé pour la livraison commerciale** | Packs de marque client, sous-titres calés sur les frames rendues, miniatures, métadonnées, manifeste, ZIP prêt à envoyer. Le studio produit un **livrable**, pas juste un MP4. |
| **467 tests, des mesures réelles** | Chaque garde-fou est couvert par un test. Les performances annoncées sont **mesurées sur ce poste**, pas déduites d'un nom de modèle. |

---

## Ce que vous pouvez faire

Le studio s'organise en **cinq axes** (plus un héritage d'outils conservés), accessibles depuis
une navigation groupée de **11 pages** et une palette de commandes (`Ctrl+K`).

| Axe | La question à laquelle il répond | Page | Moteur |
| --- | --- | --- | --- |
| **DESIGN** | « Comment ma vidéo doit-elle être faite ? » — scènes, calques, textes, polices, couleurs, animations, audio, cadre, marque du client. | `/design` | Remotion |
| **PRODUCTION** | « Comment en faire 200 sans ouvrir l'éditeur ? » — modèle + CSV + dossiers de médias → plan → file de rendu. | `/production` | Remotion, en série |
| **MOMENTS FORTS** | « Qu'est-ce qui vaut un clip dans cette source ? » — transcription Whisper, fenêtres scorées et **expliquées**, puis au clic un projet sous-titré. | `/moments` | Whisper + FFmpeg + Remotion |
| **LIVRAISON** | « Comment je l'envoie au client ? » — un lot rendu devient un ZIP : MP4, `.srt`, miniatures, métadonnées, manifeste, `LISEZ-MOI.txt`. | `/delivery` | `zipfile` + FFmpeg |
| **ASSISTANT IA** | « Dis-moi ce que tu veux, je prépare le projet ou le mapping. » — tiroir global présent sur toutes les pages (`Ctrl+I`). | partout | LLM local / Gemini / Groq |
| *Héritage* | Outils antérieurs conservés et branchés sur le web : Clips YouTube, Podcast, Shorts v1, Projets. | `/clips` `/podcast` `/short-videos` `/projects` | yt-dlp + Groq + FFmpeg |

### Les capacités qui font la différence

- **25 effets de motion design** rendus sans paquet supplémentaire (Transform/CSS, filtres SVG,
  masques, canvas 2D, `@remotion/paths`) : transitions, étalonnage, parallaxe, plasma, chroma key,
  audio-réactif… Chaque effet a ses réglages et ses bornes, connus de l'éditeur **et** de l'assistant.
- **5 familles de polices** sur disque sous licence SIL OFL (Anton, Archivo Black, Inter,
  Playfair Display, Space Grotesk), mesurées avant rendu pour signaler tout débordement.
- **Voix off locale** : catalogue de **234 voix, 53 langues** (Piper + Kokoro), synthèse hors ligne.
  Les voix sont vérifiées et leur licence consignées — rien n'est téléchargé sans votre clic.
- **Sous-titres cinétiques alignés sur la voix** : un alignement forcé « léger » lit le WAV de la
  voix off (bibliothèque standard seule, aucun ASR) et cale chaque mot à la frame près. Déterministe.
- **B-roll automatique** : le moteur rapproche les mots d'une scène des médias déjà importés et
  pose un visuel pertinent — **sans aucun LLM**, best-effort, jamais par-dessus un fond choisi.
- **Génération d'images** via Pollinations (API publique **sans clé**) : l'image revient en local
  et devient un média normal `media://<id>`, assignable par les opérations déjà validées.
- **Formats sociaux dérivés** : du master 9:16, le studio dérive le 1:1 et le 16:9 par recadrage
  centré FFmpeg, **sans re-rendu Remotion**.
- **Packs de marque client** : ce qui se répète d'une vidéo à l'autre (thème, logo, musique,
  modèles autorisés) appliqué à un projet ou à tout un lot — sans jamais toucher aux scènes ni au texte.

---

## L'autopilote : une demande → un MP4

L'autopilote est le mode « réalisateur autonome ». **Un seul appel LLM** produit un plan complet
et validé ; ensuite, **tout est déterministe, sans nouvel appel** :

```
une demande
    │
    ▼  1 appel LLM → plan validé (autopilot_plan)
┌─────────────────────────────────────────────────────────┐
│  SCRIPT     textes appliqués (opérations validées)        │
│  DESIGN     mise en scène + effets + B-roll automatique   │
│  VOIX OFF   synthèse TTS + alignement des sous-titres     │
│  EXPORT     rendu MP4 + audit technique optionnel         │
└─────────────────────────────────────────────────────────┘
    │
    ▼  un MP4, des sous-titres calés, une miniature
```

Ce qui rend l'autopilote robuste :

- **Auto-reprise** : chaque transition est persistée sur disque (`projects/autopilot/<job>.json`).
  Après un arrêt du serveur, le plan reprend à la première étape non terminée via `start(job_id=…)`.
  Les échecs transitoires (moteur vocal, rendu, disque) sont rejoués une fois — sans clic ni coût LLM.
- **Auto-correction bornée** : un audit sonde le DOM et les mesures sur quelques frames ; si des
  défauts sont **mesurés**, 0 à 2 appels LLM corrigent et re-rendent. Jamais de boucle infinie.
- **Annulation propre** : la synthèse vocale et le rendu respectent le `cancel_event` du job ;
  aucun fichier provisoire ne reste.
- **Honnêteté de l'audit** : le LLM texte ne voit pas les images. Il ne prétend jamais avoir vérifié
  le contraste sur fond média, le mouvement intégral ou l'esthétique. Le succès visuel reste à
  confirmer par une personne.

---

## L'assistant IA : il propose, vous appliquez

L'assistant n'est pas un chatbot générique : il **connaît le studio en lisant son code** (registre
de compositions, schéma v2, catalogue des 25 effets, polices, `web/package.json`). Il ne récite pas
une documentation et n'invente ni paquet `@remotion/*` absent, ni effet hors catalogue.

**Trois fournisseurs, aucun basculement automatique** : LLM local (OpenAI-compatible), Gemini, Groq.
Les réglages sont séparés ; les clés ne sortent jamais du serveur.

### Le contrat des propositions

L'assistant produit une **proposition typée** (`project_new`, `project_patch`, `library_save`,
`batch_plan`, `autopilot_plan`, `question`, `unavailable`), validée côté serveur par le métier
existant, puis **acceptée par un clic**. Tant que vous n'avez pas cliqué :

- le candidat vit en mémoire vive seulement, jamais dans l'autosauvegarde ;
- le bloc `resolved` fourni par le modèle est **toujours retiré** ;
- un média n'est accepté qu'en `media://<uuid>` — tout chemin disque est rejeté.

### 32 outils, une frontière nette

| Famille | Rôle | Exécution |
| --- | --- | --- |
| **22 outils de lecture** | projet, modèles, polices, médias, CSV, plan, lots, effets, pipelines montage, validation EDL… | libres, bornés |
| **6 outils de proposition** | produire une `Proposal` validée | sans effet de bord |
| **4 outils d'exécution** | appliquer, enregistrer, exporter, lancer un lot | **seulement sur clic utilisateur** |

`tools.describe()` publie la liste **et les interdits** : pas de shell, pas d'`eval`/`exec`, pas de
chemin disque choisi par le modèle, pas d'installation de dépendances, pas de suppression, pas de
rendu ni de lot sans clic. Les CSV et documents sont traités comme des **données** (clause
anti-injection dans le prompt).

### Transparence

Chaque réponse porte un `meta` : mode de prompt, tokens d'entrée estimés, budget de contexte,
tentatives, modèles et latences observés. Les réponses LLM ne sont pas journalisées ; une erreur de
contrat est renvoyée telle quelle au modèle pour réparation, puis à l'utilisateur en clair — jamais
masquée par une réponse approximative.

---

## Le montage footage : EDL → FFmpeg

Le studio ne se limite pas au motion design : il assemble aussi du **footage réel** (rushes,
transitions, musique, étalonnage). La répartition des moteurs est assumée :

- **Remotion** rend les compositions animées v2 (motion design, titres, sous-titres) ;
- **FFmpeg** assemble le footage réel via un contrat **EDL** (edit decision list).

Le contrat EDL et le moteur d'assemblage en trois passes sont une **implémentation maison** :
la grammaire OpenMontage n'a servi que de référence documentaire, aucun de ses exécutables n'est
utilisé. Le pont, branché de bout en bout :

```
l'assistant produit edit_decisions (EDL)
    │  cuts media:// déjà ingérés, transitions, musique, étalonnage
    ▼
validate_montage          ← outil de lecture : erreurs indexées + contrat EDL, sans écriture
    ▼
montage_render {edl,name} ← action confirmée : EDL normalisé figé, anti-écrasement,
    │                        photographie des médias (taille + mtime) → toute dérive refuse l'exécution
    ▼
POST /api/montage         ← job annulable, rendu FFmpeg en trois passes
    ▼
MP4 + probe (durée réelle vs planifiée, audio, taille) + « Ouvrir le montage »
```

Le contrat EDL est **fermé** : rôles, transitions et étalonnages hors listes sont refusés ; les
erreurs sont indexées (`cuts[2].out`) pour que le modèle corrige sans deviner. Bornes : 80 plans max,
coupes de 0,4 à 120 s, total de 2 à 3600 s, transitions ≤ 40 % du plan le plus court. Le rendu
FFmpeg en trois passes (normalisation → assemblage → finition) est volontairement robuste : codecs,
résolutions et fps hétérogènes, rushs muets, fichiers plus courts que prévu.

> Un plan sans rendu reste un plan : l'assistant ne présente jamais un `edit_decisions` comme une vidéo.

---

## Les 4 lois du studio

Elles sont **vérifiables dans le code**, pas seulement écrites ici :

1. **Le plan affiché est exactement ce qui est rendu.** `POST /api/batch/plan` et
   `POST /api/batch/start` appellent le même `build_plan()`. La file ne réinvente rien.
2. **Une seule entrée de rendu.** `render_project_to_mp4()` est appelée par l'export unitaire **et**
   par le worker du lot. Ni deuxième file, ni deuxième moteur.
3. **Rien n'est jamais rempli en silence.** Un média introuvable **bloque** la ligne ; un texte trop
   long est **signalé**, jamais coupé ; une licence absente est écrite `inconnue`, jamais validée ;
   l'assistant ne déclenche aucun rendu, aucune suppression, aucun lot sans clic.
4. **Aucun chemin Windows ne traverse le projet ni le navigateur.** Les médias sont référencés
   `media://<uuid>` et servis sous `/media-cache/<id><ext>`. Un pack de marque refuse chemin et URL ;
   le nom du ZIP de livraison est retrouvé par le serveur, jamais proposé par le client.

---

## Stack technique

| Couche | Technologies | Rôle |
| --- | --- | --- |
| **Frontend** | React 18 · TypeScript 5.6 · Vite 6 · Tailwind 3 · Remotion 4.0.539 · Radix UI | édition, aperçu (`@remotion/player`), dialogue, restitution. Zéro logique métier. |
| **Backend** | Python 3.12 · FastAPI 0.136 · uvicorn · Pydantic 2 · httpx | 16 routeurs, middleware d'origine, bornage des chemins, jobs, sous-processus. |
| **Moteur métier** | `shortvideos/` (pur, sans FastAPI ni React) | schéma v2, résolution déterministe, validation, lots, effets, EDL, sous-titres, voix, probe. |
| **Rendu** | Remotion CLI (motion design) · FFmpeg via `imageio-ffmpeg` (footage) | une seule entrée par moteur, Node portable v22. |
| **Assistant** | `server/agent/` · httpx brut · SQLite FTS5 | client LLM, capacités, retrieval, contrat, 32 outils. Aucune exécution. |
| **Persistance** | JSON + 2 bases SQLite (file de production, index de connaissances) | SQL écrit à la main, pas d'ORM. |
| **Voix / ASR** | Piper + Kokoro (TTS local) · Whisper Groq ou local (détecté, jamais installé) | synthèse hors ligne, transcription à la demande. |

**Volontairement absent** : LangChain, LlamaIndex, SDK OpenAI, SQLAlchemy, CORS (même origine),
ffprobe (OpenCV + `ffmpeg -i`), CDN/polices distantes, Docker, comptes/auth, installation automatique
de dépendances, deuxième moteur de rendu.

---

## Démarrage rapide

### Prérequis

- **Python 3.12** dans le `PATH`.
- **Node portable v22** attendu dans `../_tools/node` (le lanceur le place en tête du `PATH`,
  rien n'est supposé installé globalement).
- Windows (poste local mono-utilisateur).

### Lancer

```bat
start_web.bat
```

Le lanceur unique fait, dans l'ordre : se place à la racine · prépare le Node portable · vérifie
Python · construit le frontend si `web/dist` est absent (`npm install` une seule fois, puis
`tsc --noEmit && vite build`) · démarre uvicorn sur `127.0.0.1:8000` · attend que `/api/health`
réponde avant d'ouvrir le navigateur. `Ctrl+C` arrête l'application.

### Commandes utiles

| Objectif | Commande |
| --- | --- |
| Lancer l'application | `start_web.bat` |
| Reconstruire le frontend | `cd web && npm run build` |
| Développement à chaud | `cd web && npm run dev` (proxy `/api` → `:8000`) |
| Types seuls | `cd web && npx tsc --noEmit` |
| Serveur sans build | `python -m server.app` (`--open` pour ouvrir le navigateur) |
| Tests | `python -m pytest tests -q` → **467 passed** |
| Santé | `curl http://127.0.0.1:8000/api/health` |
| Rendu hors interface | `python tests/e2e_export_remotion.py` |

### Activer l'assistant (facultatif)

Le studio fonctionne sans LLM. Pour activer l'assistant, le **Cockpit** affiche un parcours guidé
en trois étapes (fournisseur, URL/clé, modèle) tant qu'il n'est pas prêt. Un test réel
(`POST /api/agent/check`) mesure latence et capacités observées — jamais un résultat déduit du nom
du modèle. Les clés restent dans `server/settings.json`, jamais renvoyées par HTTP.

---

## Architecture

```
Navigateur (http://127.0.0.1:8000)
  React 18 + TypeScript + Vite + Tailwind  ──>  web/dist servi par FastAPI (même origine)
       │  Remotion Player 4.0.539 (aperçu = rendu)
       │  contrat HTTP typé : web/src/api/client.ts
       ▼
FastAPI + uvicorn — 127.0.0.1:8000 — Python 3.12
  server/app.py + 16 routeurs + middleware d'origine + bornage des chemins
       │
       ├── shortvideos/   moteur métier pur : schéma, résolution, validation, lots,
       │                  effets, EDL, timeline, sous-titres, voix, b-roll, probe
       ├── server/agent/  assistant : client LLM, capacités, retrieval FTS5, contrat, outils
       ├── server/queue   file SQLite persistante + worker + manifeste
       ├── server/delivery  paquet ZIP d'un lot (job, .part.zip atomique)
       ├── server/brands    packs de marque client
       ├── server/moments   transcription, scoring, génération à la demande
       └── sous-processus : Remotion render (motion design) · FFmpeg (footage EDL)
                                    ▲
                        Node portable v22 · FFmpeg local (imageio-ffmpeg)
                        Whisper local détecté, jamais installé
```

**Qui fait quoi** : `web/` édite et affiche (zéro métier) · `shortvideos/` porte le métier pur
(testable seul) · `server/` transporte, sécurise, persiste et lance les sous-processus ·
`server/agent/` connaît le studio et propose (aucune exécution) · Remotion est la source de vérité
de l'image animée.

---

## Sécurité

| Contrôle | Comportement vérifié |
| --- | --- |
| **Écoute** | `127.0.0.1` par défaut, rien publié sur Internet. |
| **Origine** | `POST`/`PUT`/`DELETE`/`PATCH` d'une origine étrangère ⇒ **403** (y compris une origine distante qui se déclare locale). |
| **Chemins** | 11 racines autorisées ; hors de ces racines ⇒ **400** ; aucun chemin Windows en URL, médias = `/api/media/<uuid>`. |
| **Traversée** | `../`, chemins encodés, identifiants invalides ⇒ **400/404**. |
| **Upload** | types MIME image/vidéo uniquement (sinon **415**), 500 Mo max, fichier vide refusé. |
| **Clés API** | restent côté serveur ; `GET /api/settings` ne renvoie que des booléens ; rien dans les logs. |
| **LLM** | ni shell, ni `eval`/`exec`, ni chemin disque choisi par le modèle, ni écriture, ni suppression, ni lancement sans clic. |
| **CSV / documents** | traités comme des données, clause anti-injection dans le prompt. |
| **`resolved`** | un bloc fourni par le LLM est toujours retiré. |
| **Écrasement** | MP4 ou projet existant non remplacé sans règle explicite (**409** puis confirmation). |
| **Action sensible** | jeton de confirmation (`hmac.compare_digest`) + re-vérification de fraîcheur (médias, EDL) avant exécution. |

---

## Tests & vérifications

```bat
python -m pytest tests -q        →  467 passed
```

Les tests couvrent le métier **et** les garde-fous : catalogue des 25 effets (unicité, bornes,
cohérence catalogue ↔ rendu), validation, timing, plan de lot, file SQLite, livraison (cues calées
sur `resolve()`, ZIP complet), packs de marque, bout en bout de l'assistant avec un LLM maquillé
(rien n'est écrit avant acceptation, effet inventé refusé, conflit puis rebase), sécurité des routes,
contrat EDL et rendu montage.

**Mesures réelles obtenues sur ce poste** (exécutées, pas déduites) :

- export unitaire 1080×1920 / 30 fps / 405 frames / 13,5 s, terminé ;
- rendu réel avec effets : 540×960 / 30 fps / 228 frames / 7,6 s, **chacun des 25 effets** présent,
  aucun échec de composition ;
- lot de 3 lignes rendu de bout en bout depuis `/production`, manifestes CSV et JSON téléchargés ;
- frontend construit sans erreur TypeScript, pages testées dans le navigateur avec **0 erreur console** ;
- index de connaissances : ~290 documents / ~2 300 sections, FTS5 actif.

> Le contrat de l'assistant est garanti par les tests, pas par une capture de clic : activer un LLM
> imposerait de modifier le `settings.json` de l'utilisateur, ce que le studio ne fait pas sans clic.

---

## Structure du projet

```
youtube_clipper/
├── start_web.bat            lanceur unique (build + serveur + navigateur)
├── ARCHITECTURE.md          documentation complète (18 chapitres)
├── requirements.txt         dépendances Python
├── server/                  backend FastAPI
│   ├── app.py               application + 16 routeurs
│   ├── api/                 les routeurs (montage, batch, delivery, agent…)
│   ├── agent/               assistant : autopilot, tools, proposals, retrieval…
│   ├── render.py            entrée de rendu Remotion
│   ├── queue.py             file SQLite + worker
│   ├── delivery.py          paquet ZIP d'un lot
│   ├── imagegen.py          génération d'images (Pollinations, sans clé)
│   └── security.py          origines, chemins bornés, racines autorisées
├── shortvideos/             moteur métier pur
│   ├── schema.py            format de projet v2
│   ├── resolve.py           bloc resolved déterministe
│   ├── effects.py           catalogue des 25 effets
│   ├── edl.py               contrat EDL du montage footage
│   ├── timeline.py          rendu FFmpeg en trois passes
│   ├── captions.py          alignement des sous-titres sur la voix
│   ├── broll.py             B-roll automatique sans LLM
│   ├── tts.py               voix off locale (Piper + Kokoro)
│   └── delivery.py          sous-titres, miniatures, formats sociaux
├── web/                     frontend React + Remotion
│   ├── src/remotion/        compositions (source de vérité de l'image)
│   ├── src/components/      pages, assistant, UI kit
│   └── public/fonts/        5 familles SIL OFL
├── skills/                  paquets de connaissances (Remotion ; montage en local)
├── tests/                   467 tests
└── brands/ models/ projects/ media/ exports/ batch/   (données, hors dépôt)
```

---

## Limites connues

Le studio est honnête sur ce qu'il ne fait pas :

- **Mono-poste, mono-utilisateur** : pas de comptes, pas de file partagée ; un seul lot actif à la fois.
- **2 000 lignes CSV maximum** ; sortie verticale 9:16 en pratique (autres cadres non testés).
- **Pas de vraie 3D, ni morphing vectoriel libre, ni LUT externe, ni WebGL** : les 25 effets sont
  rendus avec ce qui est déjà installé (CSS 3D sur plans, filtres SVG, canvas 2D). Les 3 effets
  audio-réactifs ne bougent que si un audio réel est présent.
- **L'assistant ne voit pas l'image** : il raisonne sur le JSON, les capacités et les documents,
  jamais sur les frames rendues. L'audit technique ne garantit pas l'esthétique.
- **Les sous-titres livrés ne sont pas une transcription de la voix** : ils reprennent le texte des
  calques réellement affichés. Pas d'ASR dans la chaîne de livraison (aucune installation automatique).
- **Pas de montage audio automatique** (beat-matching, ducking dynamique) : bouclage, rognage, fondus.
- **Whisper local détecté, jamais installé** ; aucun basculement local ↔ cloud automatique.
- `server/settings.json` est en clair sur le disque local (poste mono-utilisateur) ; il ne sort
  jamais par HTTP.

La liste exhaustive et les recettes d'extension sont dans [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Licence

Le code de `shorts-studio` — l'architecture, le format v2, les effets, l'assistant, l'autopilote,
le moteur EDL/FFmpeg et toute la chaîne de livraison — est une **œuvre originale** sous licence
**Apache 2.0** — voir [`LICENSE`](LICENSE).

**Bibliothèques tierces.** Remotion est utilisé comme moteur de rendu, sous **sa propre licence**
(éditeur Remotion) ; il n'est ni modifié ni redistribué comme partie prenante du projet. FFmpeg,
Piper, Kokoro et les autres dépendances restent sous leurs licences respectives.

**Note sur le paquet montage.** La grammaire de production importée d'OpenMontage
(`skills/montage/`, licence **AGPL-3.0**) n'est qu'une **référence documentaire lue en local** :
elle est **exclue du dépôt public** (gitignorée) et aucun code exécutable d'OpenMontage n'est
copié dans le studio — seuls des manifestes et fiches sont lus, en lecture seule, par l'assistant.
Le moteur de montage, lui, est entièrement réécrit (voir plus haut). Les tests restent verts sans
ce paquet. Sa provenance (source, commit, licence) est consignée dans `skills/montage/PROVENANCE.md`
(local).

Les polices livrées sont sous licence **SIL OFL** ; les voix TTS portent leurs licences respectives
(Piper GPL-3.0 pour le code, Kokoro MIT / modèle Apache-2.0), consignées dans le catalogue.

---

## Documentation complète

Ce README est la vitrine. La référence exhaustive — chaque fichier, chaque champ du format v2,
chaque page panneau par panneau, chaque route, chaque garde-fou et son test, les limites et les
recettes d'extension — vit dans un seul document :

**[`ARCHITECTURE.md`](ARCHITECTURE.md)** — 18 chapitres, la seule documentation de référence du projet.

<div align="center">

---

*Conçu pour rester local, déterministe et honnête : le studio propose, vous décidez.*

</div>