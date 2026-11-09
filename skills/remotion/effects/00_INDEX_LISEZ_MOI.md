---
name: remotion-effects-fr
description: Guide des effets video Remotion (10 fiches) : regles de rendu, animation, medias, effets codes, paquets @remotion/*, rendu CLI/Node/Lambda/Player, sous-titres Whisper, performance, compatibilite des versions.
version: fourni par l'utilisateur (2026-11-03)
---

# EFFETS VIDEO REMOTION — INDEX (lisez ce fichier en premier)

*Guide des effets à fort impact, avec les fonctions à utiliser*

Source : « Les meilleurs effets vidéo avec Remotion », memoire de travail en francais fournie par l'utilisateur. Licence non precisee : contexte interne de l'agent, non redistribue au client.

Le guide decrit Remotion 4.x et enumere beaucoup de paquets `@remotion/*` que ce projet n'a pas installes : se fier au bloc « ETAT DU PROJET » du contexte avant de proposer un paquet.

## Fiches

- 01_MODELE_RENDU_REGLES.md — 1. Modèle de rendu et règles techniques
- 02_FONCTIONS_ANIMATION.md — 2. Fonctions d'animation (référence détaillée)
- 03_MEDIAS_METADONNEES_ENVIRONNEMENT.md — 3. Médias, métadonnées et environnement
- 04_EFFETS_TEXTE_TRACES_CAMERA.md — 4. Code des effets : texte, tracés, caméra
- 05_EFFETS_FILTRES_TRANSITIONS_3D_AUDIO.md — 5. Code des effets : filtres, transitions, 3D, audio
- 06_PAQUETS_REMOTION.md — 6. Paquets officiels `@remotion/*` et leurs fonctions
- 07_RENDU_AUTOMATISATION_DEPLOIEMENT.md — 7. Rendu, automatisation et déploiement
- 08_SOUS_TITRES_WHISPER.md — 8. Pipeline sous-titres automatiques (Whisper)
- 09_PERFORMANCE_PIEGES.md — 9. Performance, qualité et pièges fréquents
- 10_COMPATIBILITE_VERSIONS.md — 10. Compatibilité entre versions

## Les effets « waouh »

Voici les effets qui donnent le plus d'impact visuel avec Remotion, du plus spectaculaire au plus simple à mettre en place.

1. **Sous-titres dynamiques mot par mot (style TikTok)** : c'est l'effet le plus demandé en freelance. Il utilise `@remotion/captions` (`createTikTokStyleCaptions`), Whisper pour la transcription, `spring` pour l'effet de pop, et `interpolateColors` pour le surlignage.
2. **Flou de mouvement cinéma** : `<CameraMotionBlur>` de `@remotion/motion-blur` donne un rendu très pro à toute animation rapide, pour presque aucun effort.
3. **Dessin de traits qui se tracent (line drawing)** : `evolvePath` de `@remotion/paths` fait apparaître un contour comme s'il était dessiné à la main. C'est idéal pour les logos, les schémas techniques et les cartes.
4. **Morphing de formes** : `interpolatePath` transforme une forme en une autre (cercle → étoile → logo), et `@remotion/shapes` fournit des formes de base.
5. **Scènes 3D avec lumières et reflets** : `@remotion/three` avec `<ThreeCanvas>`, des matériaux métalliques et des lumières colorées. Avec `@react-three/postprocessing`, on ajoute un effet de lueur (bloom) et de profondeur de champ.
6. **Fonds organiques « aurora »** : `noise2D` et `noise3D` de `@remotion/noise` pilotent des dégradés flous qui se déplacent naturellement. Cela remplace avantageusement un fond fixe.
7. **Glitch RGB** : trois copies décalées en rouge, vert et bleu avec `mixBlendMode: 'screen'`, et un décalage calculé par `random()`. Il s'utilise beaucoup pour les intros et les transitions « tech ».
8. **Distorsion liquide ou chaleur** : un filtre SVG `feTurbulence` + `feDisplacementMap` dont la fréquence est animée par la frame.
9. **Visualiseur audio réactif** : `useAudioData` + `visualizeAudio`. Les formes pulsent sur les basses, la caméra tremble sur les kicks, les couleurs suivent la musique.
10. **Transitions fluides entre scènes** : `TransitionSeries` avec `slide`, `wipe`, `flip`, `clockWipe`, `fade`. On peut aussi créer ses propres transitions.
11. **Particules déterministes** : une boucle avec `random(i)` et `noise2D`. Elles peuvent converger vers un logo ou exploser à l'écran.
12. **Texte néon ou dégradé animé** : `textShadow` multiple, ou `background-clip: text` avec `interpolateColors`.
13. **Balayage lumineux (shine)** : un dégradé incliné qui traverse un titre ou un bouton. Il rend un logo ou un prix immédiatement plus premium.
14. **Ken Burns + parallaxe** : un zoom lent sur des images, avec plusieurs calques qui bougent à des vitesses différentes. Cela donne de la profondeur à de simples photos.
15. **Shaders GPU** : `@remotion/skia` permet d'écrire du GLSL pour des effets impossibles en CSS (eau, feu, plasma, distorsion).

## Les plus rentables en freelance

Pour Fiverr et Upwork, les effets qui se vendent le mieux sont :

- les sous-titres animés (effet 1) ;
- le logo reveal avec traits et particules (effets 3, 11 et 13) ;
- les pubs produit avec transitions (effet 10).

Ils sont rapides à produire et très demandés.

## Pour aller plus loin

Le prochain pas possible est un projet avec ces effets sous forme de compositions prêtes à lancer : glitch RGB, morphing, line drawing, shader aurora, sous-titres Whisper, etc. Le code de chaque effet et la référence technique complète se trouvent dans les sections 1 à 10 ci-dessus.
