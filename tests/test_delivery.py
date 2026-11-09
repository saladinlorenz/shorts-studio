"""Sous-titres et miniatures du paquet de livraison.

Le contrat teste ici est double : les temps du .srt doivent etre exactement les
fenetres recues par Remotion (pas une estimation), et la miniature ne doit jamais
faire echouer une livraison — un echec remonte un avertissement.

L'export reel est execute une seule fois (2 s en 270x480) pour prouver que
l'extraction d'image tourne sur une vraie video, avec des espaces dans le chemin.
"""
from pathlib import Path

import pytest
from PIL import Image

from shortvideos import delivery, schema
from shortvideos.exporter import export_video
from shortvideos.project import default_project

TEST_WIDTH, TEST_HEIGHT, TEST_FPS = 270, 480, 15


def _project() -> dict:
    return schema.new_project("quote_cinematic")


def _scene(project: dict, scene_id: str) -> dict:
    for scene in project["content"]["scenes"]:
        if scene["id"] == scene_id:
            return scene
    raise AssertionError(f"scene {scene_id} absente du gabarit")


def _layer(project: dict, scene_id: str, layer_id: str) -> dict:
    for layer in _scene(project, scene_id)["layers"]:
        if layer["id"] == layer_id:
            return layer
    raise AssertionError(f"calque {layer_id} absent de {scene_id}")


def test_cues_suivent_les_fenetres_resolues():
    cues = delivery.srt_cues(_project())
    # Le gabarit a 6 calques de texte visibles ; la signature de marque est exclue.
    assert [c["layer_id"] for c in cues] == ["hook", "hook-caption", "quote", "author", "reveal", "reveal-note"]
    assert cues[0]["start_frame"] == 4 and cues[0]["start"] == pytest.approx(4 / 30, abs=0.001)
    assert cues[-1]["end_frame"] == 405, "le dernier cue doit finir a la derniere frame rendue"
    assert all(c["end_frame"] > c["start_frame"] for c in cues)


def test_scene_et_calque_masques_sont_ignores():
    project = _project()
    _scene(project, "s3")["hidden"] = True
    _layer(project, "s1", "hook-caption")["hidden"] = True
    _layer(project, "s2", "author")["text"] = "   "
    cues = delivery.srt_cues(project)
    assert [c["layer_id"] for c in cues] == ["hook", "quote"]


def test_sauts_de_ligne_internes_sont_gardes_et_normalises():
    project = _project()
    _layer(project, "s2", "quote")["text"] = "\r\n  premiere ligne\r\nseconde ligne\r\n\r\n"
    cue = next(c for c in delivery.srt_cues(project) if c["layer_id"] == "quote")
    assert cue["text"] == "premiere ligne\nseconde ligne"


def test_duree_minimale_garantie_quand_la_sortie_devore_l_entree():
    project = _project()
    scene = _scene(project, "s1")
    scene["duration"] = 0.5
    layer = _layer(project, "s1", "hook")
    layer["animation"].update({"start_frames": 20, "out": "fade", "out_frames": 12})
    cue = next(c for c in delivery.srt_cues(project) if c["layer_id"] == "hook")
    assert cue["end_frame"] == cue["start_frame"] + delivery.MIN_CUE_FRAMES


def test_fichier_srt_est_valide_et_indexe():
    text = delivery.srt_from_project(_project())
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", ""), "toutes les fins de ligne sont en CRLF, sans LF orphelin"
    blocks = text.strip().split("\r\n\r\n")
    assert len(blocks) == 6
    for position, block in enumerate(blocks, start=1):
        lines = block.split("\r\n")
        assert lines[0] == str(position)
        assert "-->" in lines[1]
        assert len(lines) >= 3
    assert blocks[0].split("\r\n")[1] == "00:00:00,133 --> 00:00:03,667"


def test_cue_multiligne_garde_ses_deux_lignes_en_crlf():
    project = _project()
    _layer(project, "s2", "quote")["text"] = "une\n    deux"
    text = delivery.srt_from_project(project)
    assert "une\r\ndeux" in text


def test_projet_sans_texte_visible_ne_produit_rien():
    project = _project()
    for scene in project["content"]["scenes"]:
        scene["hidden"] = True
    assert delivery.srt_cues(project) == []
    assert delivery.srt_from_project(project) == ""


def test_publish_recopie_seulement_ce_qu_le_client_a_rempli():
    """Le paquet ne redige pas une legende : il transcrit le bloc « publish » du projet.

    Les clés de calcul (frames, scene_count, source) restent dans le projet ; une
    liste de hashtags vides ne mérite pas un fichier.
    """
    from server import delivery as srv_delivery

    assert srv_delivery.publish_of({}) == {}
    assert srv_delivery.publish_of({"publish": {}}) == {}
    assert srv_delivery.publish_of({"publish": {"hashtags": [" ", ""]}}) == {}

    project = {"publish": {"title": "  Titre  ", "description": "", "hashtags": ["#un", "#deux"],
                           "start": 12.0, "end": 34.5, "scene_count": 4}}
    assert srv_delivery.publish_of(project) == {"title": "Titre", "hashtags": ["#un", "#deux"]}


@pytest.fixture(scope="module")
def video_reelle(tmp_path_factory) -> Path:
    """Deux secondes de vrai MP4, ecrit dans un chemin a espaces."""
    folder = tmp_path_factory.mktemp("livraison reels")
    fond = folder / "fond de test.png"
    Image.new("RGB", (540, 960), (24, 48, 96)).save(fond)

    project = default_project()
    project["content"]["text"] = "Une citation assez longue pour deux secondes."
    project["content"]["background_image"] = str(fond)
    project["timing"] = {"duration": 2.0, "text_start": 0.2, "fade_in": 0.4, "fade_out": 0.4}
    project["export"] = {"width": TEST_WIDTH, "height": TEST_HEIGHT, "fps": TEST_FPS, "output_dir": ""}
    out = folder / "video de test.mp4"
    export_video(project, str(out), overwrite=True)
    return out


def test_miniature_extraite_sur_une_vraie_video(video_reelle: Path, tmp_path: Path):
    png = tmp_path / "miniatures" / "video de test.png"
    result = delivery.make_thumbnail(video_reelle, png)

    assert result["warning"] == "", result["warning"]
    assert Path(result["path"]) == png and png.is_file()
    assert 0.0 < result["at_seconds"] < 2.0
    with Image.open(png) as image:
        image.verify()
    with Image.open(png) as image:
        assert image.size == (TEST_WIDTH, TEST_HEIGHT)


def test_miniature_manquante_ou_existante_ne_trame_pas_la_livraison(video_reelle: Path, tmp_path: Path):
    manquant = delivery.make_thumbnail(tmp_path / "introuvable.mp4", tmp_path / "mini.png")
    assert manquant["path"] == "" and "Video absente" in manquant["warning"]

    existante = tmp_path / "video de test.png"
    existante.write_bytes(b"\x89PNG\r\n\x1a\n deja la")
    garde = delivery.make_thumbnail(video_reelle, existante, overwrite=False)
    assert existante.read_bytes().startswith(b"\x89PNG\r\n\x1a\n deja la"), "le fichier du client n'est pas touche"
    assert garde["path"] == str(existante)
    assert "Miniature deja presente" in garde["warning"]


def test_build_package_assemble_un_zip_sans_rendu_reel(tmp_path, monkeypatch):
    """L'assemblage du paquet est verifie sans re-exporter une video.

    On fabrique un faux lot de deux lignes dont la « video » est un octet ecrit sur
    disque : la miniature echoue proprement (ffmpeg ne lit pas ce fichier) mais le
    sous-titre vient du projet et le manifeste vient d'un stub. Le test porte la
    logique neuve — ecriture atomique, inventaire, LISEZ-MOI — sans couter un rendu.

    Les deux lignes sont volontairement differentes : la premiere porte un bloc
    « publish » rempli par la page Moments, la seconde sort du seul gabarit. Le
    paquet ne redige rien — il ne livre des metadonnees que la ou le client en a.
    """
    import json
    import zipfile

    from server import delivery as srv
    from server import security

    folder = tmp_path / "deliveries"
    exports = tmp_path / "exports"
    exports.mkdir()
    monkeypatch.setattr(security, "ALLOWED_DIRS", (folder, exports))
    monkeypatch.setattr(srv, "DELIVERIES_DIR", folder)

    with_publish = schema.new_project("quote_cinematic")
    with_publish["publish"] = {
        "title": "La discipline s'entraine",
        "description": "Deux minutes de clarte valent dix heures d'agitation.\n\n@atelier.runa #discipline #citation",
        "hashtags": ["#discipline", "#citation", "  "],
        "moment_id": "m0123abcd",
        "scene_count": 3,
    }
    plain = schema.new_project("quote_cinematic")

    def item(position: int, project: dict) -> dict:
        video = exports / f"ligne {position:02d}.mp4"
        video.write_bytes(b"\x00fake-mp4")
        return {
            "position": position,
            "name": f"ligne {position:02d}",
            "filename": video.name,
            "status": "done",
            "output_path": str(video),
            "duration": 13.5,
            "size_bytes": 999,
            "project": project,
        }

    fake_batch = {
        "id": "abcd1234",
        "name": "lot client",
        "model_id": "quote_cinematic",
        "status": "done",
        "counters": {"total": 2, "rendered": 2},
        "items": [item(1, with_publish), item(2, plain)],
    }
    monkeypatch.setattr(srv.queue_mod, "get_batch", lambda batch_id, items=True: fake_batch)

    def fake_manifest(batch_id, fmt):
        stub = exports / f"manifeste.{fmt}"
        stub.write_text("{}", encoding="utf-8")
        return {"manifest": str(stub)}

    monkeypatch.setattr(srv.queue_mod, "write_manifest", fake_manifest)

    result = srv.build_package("abcd1234")
    pack = Path(result["package"])
    assert pack.is_file() and pack.name.endswith(".zip")
    assert result["videos"] == 2 and result["subtitles"] == 2
    assert result["metadata"] == 1, "seule la ligne qui porte un bloc publish est livrée en métadonnées"
    assert any("miniature" in w for w in result["warnings"]), "la miniature ratee est un avertissement, pas un echec"

    with zipfile.ZipFile(pack) as archive:
        names = archive.namelist()
        assert "videos/ligne 01.mp4" in names
        assert "subtitles/ligne 01.srt" in names
        assert "manifeste.json" in names and "manifeste.csv" in names
        assert "LISEZ-MOI.txt" in names
        assert b" --> " in archive.read("subtitles/ligne 01.srt")
        assert "metadata/ligne 02.json" not in names

        marketing = json.loads(archive.read("metadata/ligne 01.json").decode("utf-8"))
        notice = archive.read("LISEZ-MOI.txt").decode("utf-8")

    assert marketing == {
        "title": "La discipline s'entraine",
        "description": "Deux minutes de clarte valent dix heures d'agitation.\n\n@atelier.runa #discipline #citation",
        "hashtags": ["#discipline", "#citation"],
        "fichier": "videos/ligne 01.mp4",
    }, "les hashtags vides tombent, le reste du bloc publish (frames, scene_count) ne sort pas du projet"
    assert "metadata/" in notice and "1 fichier(s) .json dans metadata/" in notice

    # ecriture atomique : le .part.zip transitoire ne reste jamais sur disque
    assert list(folder.glob("*.part.zip")) == []

