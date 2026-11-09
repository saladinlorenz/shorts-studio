# Provenance du paquet de connaissances Remotion

## Source 1 — « Agent Skills » de remotion-dev

| Champ | Valeur |
| --- | --- |
| Source | https://github.com/remotion-dev/skills (dépôt « Agent Skills » de Remotion) |
| Version déclarée | 4.0.540 (frontmatter `version:` de chaque fiche) |
| Date d'obtention | 2026-11-02 |
| Méthode | `npx -y skills@latest add remotion-dev/skills -g -y`, puis copie du dossier `remotion-best-practices/` dans `skills/remotion/` |
| Licence | **inconnue** |
| Vérification licence | Aucun fichier `LICENSE` dans le dépôt (chemin `main/LICENSE` → 404) ; API GitHub `repos/remotion-dev/skills` → `license: null`. La licence n'est donc pas établie, et elle n'est pas validée ici. |
| Usage dans le projet | Contexte interne de l'agent de l'éditeur : les fiches sont injectées dans le prompt système côté serveur. Elles ne sont pas livrées au client, pas redistribuées, pas intégrées au code des vidéos. |
| Modification du contenu | Aucune. Les fichiers sont copiés tels quels, y compris les liens relatifs et les copies internes (`remotion-markup/remotion-maps/`), pour que la navigation entre fiches fonctionne. |

## Source 2 — bible Remotion en français (`bible/`)

| Champ | Valeur |
| --- | --- |
| Fichiers | `00_INDEX_LISEZ_MOI.md`, `01_COEUR_API_REMOTION.md`, `02_EFFETS_ET_RECETTES.md`, `03_PAQUETS_OFFICIELS.md`, `04_RENDU_CLI_NODE_LAMBDA_PLAYER.md`, `05_AUDIO_VIDEO_SOUSTITRES_IA.md`, `06_IDEES_PROJETS_ET_SERVICES.md` (≈ 37 Ko) |
| Source | Archive `files (4).zip` fournie par l'utilisateur le 2026-11-02. L'archive contenait aussi `remotion-bible.zip`, doublon de ces 7 mêmes fichiers : non recopié. |
| Extraction | `python tools/extract_bible.py "E:\youtube\files (4).zip"` (relançable, n'écrit que dans `bible/`) |
| Licence | **non précisée** — mémoire rédigé pour le projet, pas un paquet tiers ; aucun fichier licence joint |
| Vérification technique | Les noms d'API du paquet `remotion` cités (`useCurrentScale`, `Html5Video`, `Html5Audio`, `Artifact`, `useDelayRender`, `prefetch`, `watchStaticFile`, `interpolateColors`, `Easing`, `measureSpring`, `Freeze`, `Series`, `Loop`) sont présents dans `web/node_modules/remotion` 4.0.539. En revanche `03_PAQUETS_OFFICIELS.md` décrit tout l'écosystème alors que le projet n'installe que `remotion`, `@remotion/cli` et `@remotion/player` : `server/skills.py` (`project_state()`) réinjecte la liste réelle dans le contexte pour que l'agent ne propose pas un paquet absent. |
| Usage | contexte interne de l'agent, comme la source 1 ; non redistribué au client |

## Source 3 — guide des effets vidéo en français (`effects/`)

| Champ | Valeur |
| --- | --- |
| Fichiers | `00_INDEX_LISEZ_MOI.md` + 10 fiches numérotées (règles de rendu, animation, médias, effets texte/tracés/caméra, filtres/transitions/3D/audio, paquets `@remotion/*`, rendu CLI/Node/Lambda/Player, sous-titres Whisper, performance, compatibilité des versions) — ≈ 29 Ko |
| Source | « Les meilleurs effets vidéo avec Remotion.md », document fourni par l'utilisateur le 2026-11-03 (téléchargement hors projet, original non modifié et non supprimé) |
| Extraction | `python tools/split_effects_guide.py` (relançable, n'écrit que dans `effects/`) |
| Modification du contenu | Découpage sur les titres `##` hors blocs de code, titres remontés d'un niveau (`##` → `#`). Aucun texte changé : le script compare chaque fiche à sa section d'origine et échoue en cas d'écart. L'en-tête ajouté dans l'index (frontmatter + note de licence) est le seul contenu rédactionnel. |
| Licence | **non précisée** — document de travail sans mention de licence ; traité comme les sources 1 et 2 : contexte interne, non redistribué au client |
| Vérification technique | Le guide décrit Remotion 4.x et cite des paquets non installés (`@remotion/captions`, `noise`, `paths`, `shapes`, `motion-blur`, `three`, `skia`, `transitions`, `layout-utils`, `lambda`, `cloudrun`…). Seuls `remotion`, `@remotion/cli` et `@remotion/player` sont présents : `project_state()` le rappelle à l'agent, et la fiche `10_COMPATIBILITE_VERSIONS.md` prévient des changements de nom (`startFrom`/`endAt` → `trimBefore`/`trimAfter`). |
| Usage | contexte interne de l'agent, comme les sources 1 et 2 ; non redistribué au client |

## Contenu

`skills/remotion/remotion-best-practices/` — 147 fichiers, ≈ 1,2 Mo :

- `SKILL.md` : routeur, oriente l'agent vers la bonne fiche ;
- 12 fiches (`remotion-create`, `remotion-markup`, `remotion-captions`, `remotion-render`, `remotion-studio`, `remotion-interactivity`, `remotion-multimedia`, `remotion-saas`, `remotion-maps`, `remotion-license`, `remotion-docs`, `remotion-upgrade`), chacune avec `REFERENCE.md` + documents thématiques ;
- `agents/*.yaml`, `assets/*.svg` : métadonnées d'installation et icônes, inutilisées par l'app ;
- exemples `.tsx` / `.json` / `.geojson` dans les fiches cartes et 3D.

À côté de ce paquet : `bible/` (source 2, 7 fiches ≈ 37 Ko) et `effects/`
(source 3, 11 fiches ≈ 29 Ko). Les trois sources sont vues par l'agent à travers
le même catalogue ; `server/skills.py` ne lit que l'intérieur de `skills/remotion/`.

## Point de lecture côté app

`server/skills.py` (catalogue, lecture de document, bloc de contexte) et les routes
`GET /api/skills`, `GET /api/skills/{id}`, `GET /api/skills/doc/{chemin}`,
`GET /api/skills/context?names=…`. L'accès est borné à ce dossier par
`server/security.py` (`SKILLS_DIR`) : ni traversée de chemin, ni lecture en dehors.

## Retirer / mettre à jour

Supprimer `skills/remotion/` suffit à désactiver la source de connaissances
(l'API renvoie alors un catalogue vide). Pour mettre à jour, relancer la commande
d'installation puis recopier le dossier, et actualiser ce fichier.
