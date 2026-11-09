# 10. Compatibilité entre versions

Remotion 4.x évolue vite. Vérifiez la documentation de votre version sur remotion.dev/docs pour ces points :

- `<Video>` et `<Audio>` existent aussi sous `<Html5Video>` et `<Html5Audio>`.
- `startFrom` et `endAt` deviennent `trimBefore` et `trimAfter`.
- `useDelayRender()` complète ou remplace `delayRender()` / `continueRender()`.
- Un paquet `@remotion/media` propose des composants vidéo et audio basés sur WebCodecs.
- Des paquets récents (`light-leaks`, `sfx`, `vercel`) n'existent pas dans les anciennes versions.
