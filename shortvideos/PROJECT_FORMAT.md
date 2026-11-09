# Format de projet Short Videos (version 1)

Fichier JSON UTF-8, champ obligatoire `version` (schema version actuelle : **1**).
Chemins acceptés : absolus ou relatifs, espaces et accents autorisés.

```json
{
  "version": 1,
  "template": "quote_vertical",

  "content": {
    "text": "La citation affichee.",
    "author": "Nom de l'auteur (optionnel)",
    "background_image": "C:/mes medias/fond.png",
    "logo": "C:/mes medias/logo.png"
  },

  "theme": {
    "font_family": "arialbd.ttf",
    "font_size": 72,
    "text_color": "#FFFFFF",
    "author_color": "#F2C14E",
    "accent_color": "#F2C14E",
    "shadow": true
  },

  "position": {
    "x": 0.5,
    "y": 0.45,
    "width": 0.85
  },

  "timing": {
    "duration": 8.0,
    "text_start": 0.5,
    "fade_in": 0.8,
    "fade_out": 0.8
  },

  "animation": {
    "text_in": "fade",
    "background": "zoom_slow"
  },

  "export": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "output_dir": ""
  }
}
```

## Sections

| Section | Rôle |
|---|---|
| `content` | **Le contenu** : textes, image de fond, logo |
| `theme` | **Le thème** : police, tailles, couleurs |
| `position` | Position/taille du bloc de texte (coordonnées normalisées 0..1) |
| `timing` | **La chronologie** : durée de la scène, début et fondus du texte |
| `animation` | **Les animations** : `text_in` (`fade`/`slide`), `background` (`static`/`zoom_slow`) |
| `export` | Résolution, FPS, dossier de sortie |

## Bornes (validées, erreurs bloquantes sauf mention contraire)

- `font_size` : 8..400 · `position.x/y/width` : 0..1
- `duration` : 0.5..300 s · `text_start` : 0..300 s · `fade_in/out` : 0..60 s
- `width`/`height` : 16..7680, **paires** (exigence H.264) · `fps` : 1..120
- Couleurs : format `#RRGGBB`
- `text_start >= duration` → erreur · fondus dépassant la fin → avertissement
- Texte > 220 caractères ou débordant le cadre → avertissement (non bloquant)

## Version 2 (implémentée — studio `web/src/pages/DesignPage.tsx`)

`version: 2`, modèle identifié par `model: {"id": "quote_cinematic", "version": 1}`.
Un projet v1 reste lisible : `/api/projects/{name}` migre ses médias hérités et
`/api/studio/upgrade` produit une conversion v1 → v2 **explicite**, enregistrée
sous `<nom>_v2` (le fichier d'origine n'est jamais écrasé).

```jsonc
{
  "version": 2,
  "model": { "id": "quote_cinematic", "version": 1 },
  "name": "citation-cinematique",
  "content": {
    "scenes": [
      {
        "id": "s1", "label": "Accroche", "duration": 4.0, "hidden": false,
        "background": { "media": "media://<id>", "fit": "cover", "animation": "static" },
        "layers": [
          {
            "id": "hook", "type": "text", "role": "hook",
            "text": "Ce que personne ne te dit",
            "emphasis": ["personne"], "hidden": false, "locked": false,
            "position": { "x": 0.5, "y": 0.42, "width": 0.86, "align": "center", "direction": "ltr" },
            "style": { "font_family": "anton", "font_weight": 400, "font_size": 132,
                        "line_height": 1.02, "letter_spacing": 0.01, "color": "#F7F5EF" },
            "animation": { "in": "mask_reveal", "out": "fade", "unit": "line",
                            "stagger_frames": 5, "start_frames": 4,
                            "in_frames": 26, "out_frames": 10, "easing": "spring",
                            "spring": { "damping": 16, "stiffness": 140, "mass": 1 },
                            "distance": 0.06 }
          }
        ]
      }
    ],
    "signature": { "enabled": true, "media": "media://<id>", "handle": "@votre.marque",
                    "font_family": "space-grotesk", "font_weight": 500, "font_size": 34,
                    "color": "#9A9AA8", "logo_width": 0.14, "position": { "x": 0.5, "y": 0.945 },
                    "start_frames": 0, "in_frames": 24 }
  },
  "theme": { "palette_id": "noir_or", "background_color": "#0B0B10", "surface_color": "#15151F",
              "text_color": "#F7F5EF", "accent_color": "#E2B458", "author_color": "#E2B458",
              "muted_color": "#9A9AA8", "font_family": "playfair-display", "font_weight": 700,
              "font_size": 84, "line_height": 1.18, "letter_spacing": -0.015, "shadow": true },
  "audio": { "music": "", "voice": "", "music_volume": 0.3, "voice_volume": 1.0,
              "music_fade_in": 1.0, "music_fade_out": 1.5, "markers": [], "enabled": false },
  "variation": { "seed": 1 },
  "export": { "width": 1080, "height": 1920, "fps": 30, "output_dir": "", "filename": "" }
}
```

Règles :

- **Scènes** : `content.scenes` est une liste ordonnée ; la chronologie (frames
  absolues de début/fin de chaque scène et calque) est calculée par `resolve.py`,
  jamais saisie dans le fichier.
- **Calques** : `type` = `text` ou `image` (un calque image porte `media` à la place
  de `text`) ; `role` est une chaîne libre — le modèle par défaut emploie `hook`,
  `caption`, `quote`, `author`, `reveal` ; `emphasis` = mots mis en valeur (colorés
  avec `theme.accent_color`).
- **Sens d'écriture** : `position.direction` = `ltr` ou `rtl` (validé ; le rendu RTL
  n'est pas encore validé visuellement).
- **Animation** : `unit` = `block` | `line` | `word`, `in` = `none` | `fade` |
  `slide_up` | `slide_left` | `scale` | `mask_reveal`, `out` = `none` | `fade`,
  `easing` = `linear` | `ease_out_cubic` | `ease_out_quint` | `spring`.
  Tout est piloté par la **frame**, aucun timer indépendant.
- **Médias** : uniquement `media://<id>`. Un chemin Windows dans un projet v2 est
  une **erreur bloquante** (« chemin Windows interdit ») → réimport du média.
- **Polices** : `font_family` doit exister dans `fonts.py` /
  `web/src/remotion/fontCatalog.json` (familles SIL OFL). Une police hors catalogue
  est une erreur ; un poids non déclaré est un avertissement.
- **Rien d'calculé n'est persisté** : le bloc `resolved` (frames, fenêtres, graine,
  ressources, URLs de rendu) est produit à chaque préparation par
  `/api/studio/prepare` et n'entre **pas** dans le fichier de projet.
- **Audio** : `audio` porte `enabled`, `music`, `voice` (mêmes références
  `media://` que les images et vidéos), `music_volume` / `voice_volume` (0 à 1)
  et `music_fade_in` / `music_fade_out` (secondes). `resolve()` en fait un bloc
  `resolved.audio` borné et en frames ; la composition mélange la piste, **boucle
  une musique plus courte que la vidéo et ne la ralentit jamais**, et rogne le
  surplus à la durée de la vidéo. Un `media://` manquant ou un chemin Windows
  dans `audio.music` / `audio.voice` est une **erreur bloquante**.

## Déjà en place

- **Bibliothèque de modèles** (`models/`, `/api/library`, enregistrement depuis Design).
- **Mixage audio** (`resolved.audio`) : musique en boucle jamais ralentie, voix, rognage
  à la durée de la vidéo, `media://` manquant = erreur bloquante.
- **Production par lots** : `shortvideos/batch.py` transforme chaque ligne de CSV en un
  **projet version 2 complet** (rien de nouveau dans le format : les colonnes remplissent
  les champs adressables découverts dans le modèle), puis `server/queue.py` rend chaque
  projet par la chaîne d'export unitaire. Les champs utilisés par le lot sont exactement
  ceux du format : `content.scenes[].layers[].text` / `.emphasis`, `.duration`,
  `.background`, `content.signature.handle` / `.media`, `audio.music` / `audio.voice`,
  `variation.seed` (graine du modèle + index − 1) et `export.*`. Un projet de lot refuse
  toute autre version que 2, et aucun chemin Windows n'est jamais injecté dans un champ
  média : la valeur d'une colonne devient une référence `media://` résolue dans les
  dossiers connectés.

## Avenirs

Timeline de montage (séquence d'images, pistes, réglages finement éditables). Le format
n'a pas encore de champ pour ça : il faudra l'ajouter sous une nouvelle `version`, avec
migration explicite, pour ne jamais réinterpréter silencieusement un projet enregistré.
