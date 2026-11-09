# 9. Performance, qualité et pièges fréquents

| Problème | Cause | Solution |
| --- | --- | --- |
| Vidéo saccadée ou image manquante au rendu | `<Video>` natif | Utiliser `<OffthreadVideo>` |
| Le rendu se fige ou expire | `delayRender` jamais libéré | Appeler `continueRender` dans tous les cas, y compris en cas d'erreur |
| Résultat différent à chaque rendu | `Math.random()` ou `Date.now()` | Utiliser `random(seed)` et la frame |
| Animation CSS ignorée | `transition` ou `@keyframes` | Tout piloter par `interpolate` et `spring` |
| Rendu lent | `blur` ou `box-shadow` énormes sur beaucoup d'éléments | Réduire les rayons, regrouper, utiliser `useMemo` |
| 3D vide ou erreur WebGL en cloud | Moteur graphique absent | `--gl=angle` |
| Scène qui apparaît en retard | Composant monté trop tard | `<Sequence premountFor={30}>` |
| Police qui change en cours de rendu | Chargement asynchrone | `loadFont` ou `delayRender` autour du chargement |
| Erreur de version | Paquets Remotion désalignés | `npx remotion upgrade` |
| Durée totale fausse avec transitions | Somme des séquences sans retrancher les transitions | Durée = séquences moins transitions |

**Bonnes pratiques de production**

- Un thème centralisé (couleurs, polices) et un `Root.tsx` rangé avec `<Folder>`.
- Des props typées et un `schema` zod pour que le client modifie textes et couleurs dans le Studio.
- H.264 avec CRF 16 à 18 pour une qualité élevée ; produire 9:16, 1:1 et 16:9 depuis le même composant en changeant `width` et `height`.
- Pour le volume : API Express ou Next.js avec `renderMedia`, ou Lambda pour le parallélisme.
- Licence : gratuite pour particuliers et petites équipes ; une licence entreprise est requise pour les grandes structures (voir remotion.pro).
