"""Production par lots : champs adressables, ligne de CSV -> projet, plan de lot.

Le lot n'invente aucun format : chaque ligne produit un projet version 2
complet, qui passe les memes validations et le meme rendu qu'un projet
unitaire. Les ressources sont adressees par reference ``media://<id>`` — un
chemin Windows ne rentre jamais dans un projet.

Politique d'attribution des ressources (fonds vidéo, musiques) :

1. une colonne CSV explicitement mappee gagne, et un fichier introuvable est
   une erreur pour la ligne (rien n'est remplacé en silence) ;
2. sinon, rotation sur les médias importés des dossiers connectés ;
3. s'il y a moins de ressources que de lignes, le cycle reprend au début :
   c'est un bouclage, annonce dans le plan ;
4. sans dossier connecté, le modèle garde son apparence (fond du thème, pas de
   musique) et le plan porte un avertissement.

Tout est deterministe : l'ordre des lignes, l'ordre des médias (trié au scan)
et la graine par ligne, donc un même CSV produit le même plan deux fois.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import schema
from .schema import SCHEMA_VERSION_V2

# Champs de type média : la valeur d'une colonne doit devenir une reference.
MEDIA_SUFFIX = ".background"
KIND_OF_SUFFIX = {"background": "video", "music": "audio", "voice": "audio"}

# Un texte nettement plus long que celui du modele risque de deborder :
# on avertit, on ne raccourcit jamais.
OVERFLOW_RATIO = 1.6

# Règles d'attribution exposées dans le plan : l'utilisateur les lit avant de
# lancer le lot, pas après dans un manifeste.
POLICY = {
    "column_wins": True,
    "missing_named_file": "erreur bloquante pour la ligne",
    "rotation": "ordre trié des dossiers connectés, déterministe",
    "cycling": "le cycle reprend quand les ressources sont moins nombreuses que les lignes",
    "never": "aucun raccourcissement de texte, aucun chemin Windows dans un projet",
}


def _slug(value: str, fallback: str = "video") -> str:
    """Nom de fichier lisible, sans accents ni separateurs de chemin."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    text = re.sub(r"[\s_]+", "-", text).strip("-").lower()
    return text[:60] or fallback


def _layer_field_name(layer: dict, scene: dict) -> str:
    return str(layer.get("role") or layer.get("id") or "text")


def fillable_fields(template: dict) -> list[dict]:
    """Champs d'un modele que le CSV peut remplir, dans l'ordre visuel.

    Une clef est un chemin logique (pas un chemin de fichier) : elle suffit a
    ``apply_row`` pour retrouver l'endroit a editer dans le projet.
    """
    if template.get("version") != SCHEMA_VERSION_V2:
        raise ValueError("fillable_fields attend un projet version 2.")

    fields: list[dict] = [
        {
            "key": "title",
            "label": "Titre (sert aussi de nom de fichier)",
            "type": "text",
            "scene": "",
            "required": False,
        }
    ]

    for scene in template.get("content", {}).get("scenes", []):
        scene_id = str(scene.get("id", ""))
        scene_label = str(scene.get("label") or scene_id)
        for layer in scene.get("layers", []):
            if layer.get("type") != "text":
                continue
            role = _layer_field_name(layer, scene)
            key = f"scene.{scene_id}.{role}.text"
            fields.append(
                {
                    "key": key,
                    "label": f"{scene_label} · {role}",
                    "type": "text",
                    "scene": scene_id,
                    "required": role in ("hook", "quote"),
                    "sample": str(layer.get("text", ""))[:80],
                }
            )
            if layer.get("emphasis"):
                fields.append(
                    {
                        "key": f"scene.{scene_id}.{role}.emphasis",
                        "label": f"{scene_label} · {role} — mots mis en valeur",
                        "type": "list",
                        "scene": scene_id,
                        "required": False,
                        "sample": ", ".join(str(e) for e in layer.get("emphasis", [])),
                    }
                )
        fields.append(
            {
                "key": f"scene.{scene_id}.duration",
                "label": f"{scene_label} — durée (s)",
                "type": "number",
                "scene": scene_id,
                "required": False,
                "min": 0.5,
                "max": 60.0,
                "sample": scene.get("duration"),
            }
        )
        fields.append(
            {
                "key": f"scene.{scene_id}{MEDIA_SUFFIX}",
                "label": f"{scene_label} — fond",
                "type": "media",
                "kind": "video",
                "scene": scene_id,
                "required": False,
                "sample": str(scene.get("background", {}).get("media", "")),
            }
        )

    signature = template.get("content", {}).get("signature", {})
    fields.append(
        {
            "key": "signature.handle",
            "label": "Signature — @pseudo",
            "type": "text",
            "scene": "",
            "required": False,
            "sample": str(signature.get("handle", "")),
        }
    )
    fields.append(
        {
            "key": "signature.media",
            "label": "Signature — logo",
            "type": "media",
            "kind": "image",
            "scene": "",
            "required": False,
            "sample": str(signature.get("media", "")),
        }
    )
    for key, label, kind in (("music", "Musique de fond", "audio"), ("voice", "Voix (voix-off)", "audio")):
        fields.append(
            {
                "key": f"audio.{key}",
                "label": label,
                "type": "media",
                "kind": kind,
                "scene": "",
                "required": False,
                "sample": str(template.get("audio", {}).get(key, "")),
            }
        )
    return fields


_AUTONAMES: dict[str, tuple[str, ...]] = {
    "title": ("title", "titre", "name", "nom", "video", "fichier"),
    "scene.s1.hook.text": ("hook", "accroche", "teaser"),
    "scene.s2.quote.text": ("quote", "citation", "texte", "text", "content", "contenu"),
    "scene.s2.author.text": ("author", "auteur", "source", "by"),
    "scene.s3.reveal.text": ("reveal", "signature", "cta"),
    "audio.music": ("music", "musique", "audio", "background music", "bgm"),
    "audio.voice": ("voice", "voix", "voiceover", "vo"),
    "scene.s1.duration": ("duration", "duree", "temps", "seconds", "secondes"),
    "signature.handle": ("handle", "pseudo", "marque", "brand"),
}


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def suggest_mapping(columns: list[str], fields: list[dict]) -> dict[str, str]:
    """Deduit un mapping colonne -> champ a partir des entetes.

    Regles simples, dans l'ordre : nom de colonne identique a un nom courant
    du champ, puis equality avec le libelle du champ. Une colonne qui ne
    correspond a rien n'est pas mappee — l'utilisateur la voit reste.
    """
    by_column = {_norm(c): c for c in columns if str(c).strip()}
    mapping: dict[str, str] = {}
    for field in fields:
        key = field["key"]
        candidates = [_norm(name) for name in _AUTONAMES.get(key, ())]
        if key in ("scene.s2.quote.text",):
            candidates += ["quote text", "citation texte"]
        candidates.append(_norm(field["label"]))
        for name in candidates:
            column = by_column.get(name)
            if column and column not in mapping.values():
                mapping[key] = column
                break
    return mapping


def _as_number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def resolve_media_value(value: Any, assets: list[dict], *, field: str) -> tuple[str, dict | None, str]:
    """Valeur de colonne -> reference ``media://<id>``.

    Accepte une reference deja complete, un identifiant brut, ou un nom de
    fichier tel qu'il apparait dans le dossier connecte. Retourne
    ``(ref, media_utilise, message_derreur)``.
    """
    text = str(value if value is not None else "").strip()
    if not text:
        return "", None, ""

    if text.startswith("media://"):
        media_id = text[len("media://") :]
        match = next((a for a in assets if a.get("media_id") == media_id), None)
        if match:
            return text, match, ""
        if re.fullmatch(r"[0-9a-fA-F-]{8,64}", media_id):
            # la reference n'est pas dans les dossiers connectes : le projet
            # vient peut-etre de la mediathedique, la validation verifiera
            return text, None, ""
        return "", None, f"{field} : reference media invalide {text!r}"

    if re.fullmatch(r"[0-9a-fA-F]{16,64}", text):
        by_id = next((a for a in assets if a.get("media_id") == text), None)
        return f"media://{text}", by_id, ""

    wanted = _norm(text)
    wanted_stem = _norm(Path_stem(text))
    matches = [
        a
        for a in assets
        if _norm(str(a.get("name", ""))) == wanted or _norm(Path_stem(str(a.get("name", "")))) == wanted_stem
    ]
    if len(matches) == 1:
        ref = f"media://{matches[0]['media_id']}"
        return ref, matches[0], ""
    if len(matches) > 1:
        folders = ", ".join(sorted({str(m.get("folder", "")) for m in matches}))
        return (
            f"media://{matches[0]['media_id']}",
            matches[0],
            f"{field} : « {text} » correspond a plusieurs fichiers (dossiers {folders}), "
            f"le premier « {matches[0]['name']} » est utilise.",
        )
    return "", None, f"{field} : fichier « {text} » introuvable dans les dossiers connectés."


def Path_stem(value: str) -> str:
    """Nom sans extension, pour tolerer « fond » au lieu de « fond.mp4 »."""
    text = str(value or "").replace("\\", "/").split("/")[-1]
    return text.rsplit(".", 1)[0] if "." in text else text


def _set_scene_field(project: dict, scene_id: str, role: str, sub: str, value: Any) -> bool:
    for scene in project.get("content", {}).get("scenes", []):
        if str(scene.get("id", "")) != scene_id:
            continue
        for layer in scene.get("layers", []):
            if _layer_field_name(layer, scene) != role:
                continue
            if sub == "text":
                layer["text"] = str(value)
                return True
            if sub == "emphasis":
                layer["emphasis"] = [
                    part.strip() for part in str(value).split(",") if part.strip()
                ]
                return True
    return False


def apply_row(
    template: dict,
    row: dict[str, Any],
    mapping: dict[str, str],
    *,
    assets: dict[str, list[dict]] | None = None,
    index: int = 1,
    auto_background: list[dict] | None = None,
    auto_music: list[dict] | None = None,
) -> dict:
    """Projet d'une ligne, plus son nom de fichier et son diagnostic.

    ``auto_background`` / ``auto_music`` : media choisi par rotation pour cette
    ligne, applique seulement si la ligne ne nomme rien explicitement.
    """
    assets = assets or {}
    video_assets = assets.get("video", [])
    audio_assets = assets.get("audio", [])
    image_assets = assets.get("image", [])

    project = schema.clone(template)
    if project.get("version") != SCHEMA_VERSION_V2:
        raise ValueError("apply_row attend un modèle version 2.")

    errors: list[str] = []
    warnings: list[str] = []
    used: dict[str, dict] = {}
    title = ""

    def column(key: str) -> Any:
        column_name = mapping.get(key)
        if not column_name:
            return None
        return row.get(column_name)

    def media_field(key: str, kind: str) -> tuple[str, dict | None]:
        value = column(key)
        text = str(value if value is not None else "").strip()
        if text and not text.startswith("media://") and not re.fullmatch(r"[0-9a-fA-F]{16,64}", text):
            if re.search(r"^[A-Za-z]:\\|^\\\\", text):
                errors.append(
                    f"ligne {index} : {key} contient un chemin Windows ({text!r}) ; "
                    "indiquez un nom de fichier du dossier connecté."
                )
                return "", None
        pool = {"video": video_assets, "audio": audio_assets, "image": image_assets}[kind]
        ref, match, message = resolve_media_value(value, pool, field=key)
        if message:
            (errors if "introuvable" in message or "invalide" in message else warnings).append(
                f"ligne {index} : {message}"
            )
        return ref, match

    # 1. titre / nom
    if "title" in mapping:
        raw_title = column("title")
        if str(raw_title or "").strip() == "":
            errors.append(f"ligne {index} : colonne « {mapping['title']} » vide pour le titre.")
            title = ""
        else:
            title = str(raw_title).strip()
    project["name"] = _slug(title, fallback=f"lot-{index:03d}")

    # 2. champs texte, durees, emphasis
    fields_by_key = {f["key"]: f for f in fillable_fields(template)}
    for key, column_name in mapping.items():
        if key == "title" or column_name not in row:
            continue
        field = fields_by_key.get(key)
        if field is None:
            warnings.append(f"ligne {index} : champ inconnu ignoré — {key} ← « {column_name} ».")
            continue
        value = row[column_name]
        text = str(value if value is not None else "")

        if field["type"] == "media":
            continue  # traite a l'etape 3, avec les regles d'attribution
        if text.strip() == "":
            if field.get("required"):
                errors.append(
                    f"ligne {index} : « {field['label']} » est vide (colonne « {column_name} »)."
                )
            continue

        if key.endswith(".duration"):
            scene_id = key.split(".")[1]
            number = _as_number(text)
            if number is None:
                errors.append(f"ligne {index} : durée illisible pour la scène {scene_id} — {text!r}.")
                continue
            lo, hi = field.get("min", 0.5), field.get("max", 60.0)
            if not lo <= number <= hi:
                errors.append(f"ligne {index} : durée {number} s hors bornes [{lo}, {hi}] (scène {scene_id}).")
                continue
            for scene in project["content"]["scenes"]:
                if str(scene.get("id")) == scene_id:
                    scene["duration"] = number
            continue

        parts = key.split(".")
        if parts[0] == "scene" and len(parts) == 4:
            scene_id, role, sub = parts[1], parts[2], parts[3]
            if not _set_scene_field(project, scene_id, role, sub, text):
                errors.append(f"ligne {index} : cible introuvable dans le modèle — {key}.")
                continue
            if sub == "text":
                sample = fields_by_key.get(key, {}).get("sample", "")
                if sample and len(text) > len(sample) * OVERFLOW_RATIO:
                    warnings.append(
                        f"ligne {index} : « {field['label']} » est {len(text)} caractères "
                        f"pour {len(sample)} dans le modèle — risque de débordement, à contrôler à l'aperçu."
                    )
            continue

        if key == "signature.handle":
            project["content"]["signature"]["handle"] = text.strip()[:80]
            continue

    # 3. medias : colonne explicite, sinon attribution automatique
    for scene in project["content"]["scenes"]:
        scene_id = str(scene.get("id", ""))
        key = f"scene.{scene_id}.background"
        if key in mapping:
            ref, match = media_field(key, "video")
            if ref:
                scene.setdefault("background", {})["media"] = ref
                used[f"scene.{scene_id}.background"] = match or {"media_id": ref[len('media://'):], "name": ref}
            continue
        if str(scene.get("background", {}).get("media", "") or ""):
            continue  # le modele a deja son fond : on n'y touche pas
        if auto_background:
            pick = auto_background[0]
            scene.setdefault("background", {})["media"] = pick["ref"]
            used[f"scene.{scene_id}.background"] = pick

    if "signature.media" in mapping:
        ref, match = media_field("signature.media", "image")
        if ref:
            project["content"]["signature"]["media"] = ref
            used["signature.media"] = match or {"media_id": ref[len('media://'):], "name": ref}

    for key, kind, auto_pool in (("audio.music", "audio", auto_music), ("audio.voice", "audio", None)):
        if key in mapping:
            ref, match = media_field(key, kind)
            if ref:
                project.setdefault("audio", {})[key.split(".", 1)[1]] = ref
                used[key] = match or {"media_id": ref[len('media://'):], "name": ref}
        elif auto_pool:
            project.setdefault("audio", {})[key.split(".", 1)[1]] = auto_pool[0]["ref"]
            used[key] = auto_pool[0]

    audio = project.setdefault("audio", {})
    if isinstance(audio, dict):
        audio["enabled"] = bool(str(audio.get("music", "") or "") or str(audio.get("voice", "") or ""))

    # 4. graine et nom de fichier : deterministes
    project.setdefault("variation", {})["seed"] = int(template.get("variation", {}).get("seed", 1) or 1) + index - 1
    filename = title if title else f"lot-{index:03d}"
    if "filename" in mapping:
        filename = str(column("filename") or filename)
    export = project.setdefault("export", {})
    export["filename"] = _slug(filename, fallback=f"lot-{index:03d}")
    if title:
        export["filename"] = f"{index:03d}-{export['filename']}"

    return {
        "index": index,
        "project": project,
        "name": project["name"],
        "filename": f"{export['filename']}.mp4",
        "assets_used": [
            {"field": field, **(media or {})} for field, media in used.items() if media
        ],
        "errors": errors,
        "warnings": warnings,
    }


def _rotation(pool: list[dict], position: int) -> list[dict]:
    """Media de la ``position``-ieme ligne, en cycle complet sur le pool."""
    if not pool:
        return []
    index = (max(1, position) - 1) % len(pool)
    pick = pool[index]
    return [{**pick, "pass": (max(1, position) - 1) // len(pool) + 1, "rank": index + 1}]


def _passes(rows: int, pool: list[dict]) -> int:
    if not pool:
        return 0
    return -(-rows // len(pool))  # division ceiling


def build_plan(
    template: dict,
    rows: list[dict[str, Any]],
    mapping: dict[str, str],
    assets: dict[str, list[dict]] | None = None,
    options: dict[str, Any] | None = None,
) -> dict:
    """Plan inspectable avant lancement : un projet par ligne, plus la
    justification de chaque attribution de ressource.

    ``options`` : ``background`` et ``music`` valent ``"auto"`` (rotation sur
    les dossiers connectes), ``"none"`` (rien n'est ajoute) ou ``"column"``
    (seule la colonne CSV decide).
    """
    options = options or {}
    assets = assets or {}
    video_pool = assets.get("video", [])
    audio_pool = assets.get("audio", [])

    mode_background = str(options.get("background", "auto")).lower()
    mode_music = str(options.get("music", "auto")).lower()

    scenes = template.get("content", {}).get("scenes", [])
    scenes_needing_background = [
        str(scene.get("id", ""))
        for scene in scenes
        if not str(scene.get("background", {}).get("media", "") or "")
    ]

    auto_background_ok = bool(mode_background == "auto" and video_pool and scenes_needing_background)
    auto_music_ok = bool(mode_music == "auto" and audio_pool and "audio.music" not in mapping)

    warnings: list[str] = []
    if mode_background == "auto":
        if not video_pool:
            if scenes_needing_background:
                warnings.append(
                    "Aucun dossier de vidéos de fond connecté (ou scan non lancé) : "
                    "les scènes gardent le fond du thème."
                )
        elif len(video_pool) < len(rows):
            warnings.append(
                f"{len(video_pool)} fonds pour {len(rows)} lignes : le cycle reprend au début, "
                f"chaque fichier sert au plus {_passes(len(rows), video_pool)} fois."
            )
    if mode_music == "auto":
        if not audio_pool:
            warnings.append("Aucune musique de fond disponible : les vidéos seront silencieuses.")
        elif len(audio_pool) < len(rows):
            warnings.append(
                f"{len(audio_pool)} musiques pour {len(rows)} lignes : bouclage, "
                f"{_passes(len(rows), audio_pool)} passes au plus."
            )
    if mode_background == "none" and scenes_needing_background:
        warnings.append("Attribution automatique des fonds désactivée : les scènes restent sur le fond du thème.")
    if mode_music == "none":
        warnings.append("Attribution automatique des musiques désactivée : aucune musique sauf colonne mappée.")

    items: list[dict] = []
    for position, row in enumerate(rows, start=1):
        auto_bg = _rotation(video_pool, position) if auto_background_ok else []
        auto_mu = _rotation(audio_pool, position) if auto_music_ok else []
        item = apply_row(
            template,
            row,
            mapping,
            assets=assets,
            index=position,
            auto_background=auto_bg or None,
            auto_music=auto_mu or None,
        )
        explicit_background = [
            a for a in item["assets_used"] if a["field"].endswith(".background") and "pass" not in a
        ]
        sources = []
        if explicit_background:
            sources.append("colonne CSV")
        if auto_bg:
            item["background_pass"] = auto_bg[0]["pass"]
            sources.append("rotation")
        item["background_source"] = " + ".join(sources) or "modèle (fond du thème)"
        if auto_mu:
            item["music_source"] = "rotation"
            item["music_pass"] = auto_mu[0]["pass"]
        elif any(a["field"] == "audio.music" for a in item["assets_used"]):
            item["music_source"] = "colonne CSV"
        else:
            item["music_source"] = "aucune"
        item["row_preview"] = {str(k): str(v) for k, v in list(row.items())[:6]}
        items.append(item)

    invalid = [item["index"] for item in items if item["errors"]]
    filenames = [item["filename"] for item in items]
    duplicates = sorted({name for name in filenames if filenames.count(name) > 1})
    if duplicates:
        warnings.append(
            "Noms de fichier en double dans le lot (" + ", ".join(duplicates[:5]) + ") : "
            "deux titres identiques produiraient le même fichier."
        )

    return {
        "items": items,
        "warnings": warnings,
        "summary": {
            "rows": len(rows),
            "ready": len(rows) - len(invalid),
            "invalid_rows": invalid,
            "video_assets": len(video_pool),
            "audio_assets": len(audio_pool),
            "background_passes": _passes(len(rows), video_pool) if auto_background_ok else 0,
            "music_passes": _passes(len(rows), audio_pool) if auto_music_ok else 0,
            "cycled_background": bool(auto_background_ok and len(video_pool) < len(rows)),
            "cycled_music": bool(auto_music_ok and len(audio_pool) < len(rows)),
            "auto_background": auto_background_ok,
            "auto_music": auto_music_ok,
        },
        "policy": POLICY,
    }
