"""CSV de production et plan de lot : mapping, attribution intelligente, determinisme."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from server import csv_source
from shortvideos import batch
from shortvideos import schema


TEMPLATE = schema.new_project("quote_cinematic")


def _asset(media_id: str, name: str, kind: str = "video") -> dict:
    return {"media_id": media_id, "name": name, "kind": kind, "ref": f"media://{media_id}", "folder": "fonds"}


VIDEOS = [_asset(f"{i:032x}", f"fond-{i}.mp4") for i in (1, 2)]
AUDIOS = [_asset("a" * 32, "boucle-unique.mp3", "audio")]
ASSETS = {"video": VIDEOS, "audio": AUDIOS, "image": []}


def test_fillable_fields_couvrent_le_modele_integre():
    keys = [f["key"] for f in batch.fillable_fields(TEMPLATE)]
    assert "title" in keys
    assert "scene.s2.quote.text" in keys
    assert "scene.s2.author.text" in keys
    assert "scene.s1.duration" in keys
    assert "scene.s1.background" in keys
    assert "audio.music" in keys
    assert "signature.handle" in keys
    required = {f["key"] for f in batch.fillable_fields(TEMPLATE) if f.get("required")}
    assert required == {"scene.s1.hook.text", "scene.s2.quote.text"}


def test_fillable_fields_refuse_un_projet_v1():
    with pytest.raises(ValueError):
        batch.fillable_fields({"version": 1})


def test_suggest_mapping_detecte_les_entetes_usuelles():
    fields = batch.fillable_fields(TEMPLATE)
    mapping = batch.suggest_mapping(
        ["Titre", "Citation", "Auteur", "Durée", "Musique", "inutile"], fields
    )
    assert mapping["title"] == "Titre"
    assert mapping["scene.s2.quote.text"] == "Citation"
    assert mapping["scene.s2.author.text"] == "Auteur"
    assert mapping["audio.music"] == "Musique"
    assert "inutile" not in mapping.values()


def test_apply_row_remplit_textes_duree_et_media():
    row = {
        "titre": "Courage",
        "citation": "Avancer malgre tout.",
        "auteur": "— Amelia Runa",
        "accroche": "Une seule phrase",
        "duree": "5,5",
        "mots": "courage,  avancer",
        "fond": "fond-1.mp4",
    }
    mapping = {
        "title": "titre",
        "scene.s2.quote.text": "citation",
        "scene.s2.author.text": "auteur",
        "scene.s1.hook.text": "accroche",
        "scene.s1.duration": "duree",
        "scene.s2.quote.emphasis": "mots",
        "scene.s1.background": "fond",
    }
    item = batch.apply_row(TEMPLATE, row, mapping, assets=ASSETS, index=3)

    assert item["errors"] == []
    scenes = {s["id"]: s for s in item["project"]["content"]["scenes"]}
    assert scenes["s1"]["duration"] == 5.5
    assert scenes["s1"]["background"]["media"] == f"media://{VIDEOS[0]['media_id']}"
    texts = {
        layer["role"]: layer["text"]
        for scene in scenes.values()
        for layer in scene["layers"]
        if layer["type"] == "text"
    }
    assert texts["quote"] == "Avancer malgre tout."
    assert texts["hook"] == "Une seule phrase"
    emphasis = [
        layer["emphasis"] for scene in scenes.values() for layer in scene["layers"] if layer["role"] == "quote"
    ][0]
    assert emphasis == ["courage", "avancer"]
    assert item["index"] == 3
    assert item["filename"].startswith("003-courage")


def test_apply_row_chemin_windows_et_fichier_inconnu_sont_bloquants():
    row = {"citation": "Texte", "accroche": "Accroche", "fond": "E:\\videos\\fond.mp4"}
    mapping = {
        "scene.s2.quote.text": "citation",
        "scene.s1.hook.text": "accroche",
        "scene.s1.background": "fond",
    }
    item = batch.apply_row(TEMPLATE, row, mapping, assets=ASSETS, index=1)
    assert any("chemin Windows" in e for e in item["errors"])

    row2 = dict(row, fond="jamais-vu.mp4")
    item2 = batch.apply_row(TEMPLATE, row2, mapping, assets=ASSETS, index=2)
    assert any("introuvable" in e for e in item2["errors"])
    assert "media://jamais" not in str(item2["project"])


def test_apply_row_ne_raccourcit_pas_un_texte_long():
    row = {"citation": "« " + "mot " * 40 + "»"}
    item = batch.apply_row(
        TEMPLATE,
        dict(row, accroche="Accroche"),
        {"scene.s2.quote.text": "citation", "scene.s1.hook.text": "accroche"},
        assets=ASSETS,
        index=1,
    )
    assert item["project"]["content"]["scenes"][1]["layers"][0]["text"] == row["citation"]
    assert any("débordement" in w for w in item["warnings"])


def test_build_plan_boucle_quand_les_ressources_sont_moins_nombreuses():
    rows = [{"citation": f"Citation {i}", "accroche": f"A {i}"} for i in range(5)]
    mapping = {"scene.s2.quote.text": "citation", "scene.s1.hook.text": "accroche"}

    plan = batch.build_plan(TEMPLATE, rows, mapping, ASSETS, {"background": "auto", "music": "auto"})

    assert plan["summary"]["rows"] == 5
    assert plan["summary"]["video_assets"] == 2
    assert plan["summary"]["cycled_background"] is True
    assert plan["summary"]["background_passes"] == 3
    assert [i["background_pass"] for i in plan["items"]] == [1, 1, 2, 2, 3]
    assert [i["assets_used"][0]["name"] for i in plan["items"]] == [
        "fond-1.mp4",
        "fond-2.mp4",
        "fond-1.mp4",
        "fond-2.mp4",
        "fond-1.mp4",
    ]
    assert all(i["music_source"] == "rotation" for i in plan["items"])
    assert any("cycle reprend" in w for w in plan["warnings"])


def test_build_plan_la_colonne_gagne_sur_l_attribution():
    rows = [{"fond": "fond-2.mp4"} for _ in range(3)]
    plan = batch.build_plan(
        TEMPLATE, rows, {"scene.s1.background": "fond"}, ASSETS, {"background": "auto", "music": "none"}
    )
    first = plan["items"][0]
    filled = {
        s["id"]: s["background"]["media"]
        for s in first["project"]["content"]["scenes"]
    }
    assert filled["s1"] == f"media://{VIDEOS[1]['media_id']}"  # colonne respectee
    assert filled["s2"] == f"media://{VIDEOS[0]['media_id']}"  # rotation pour les autres scenes
    assert first["background_source"] == "colonne CSV + rotation"  # s1 nommé, les autres en rotation
    assert any("musiques" in w or "désactivée" in w for w in plan["warnings"])


def test_build_plan_sans_dossier_connecte_preventit():
    rows = [{"citation": "Une", "accroche": "Deux"}]
    plan = batch.build_plan(
        TEMPLATE,
        rows,
        {"scene.s2.quote.text": "citation", "scene.s1.hook.text": "accroche"},
        {"video": [], "audio": [], "image": []},
        {"background": "auto", "music": "auto"},
    )
    assert plan["summary"]["auto_background"] is False
    assert plan["summary"]["cycled_background"] is False
    assert any("Aucun dossier de vidéos" in w for w in plan["warnings"])
    assert any("silencieuses" in w for w in plan["warnings"])
    assert all(not s["background"]["media"] for s in plan["items"][0]["project"]["content"]["scenes"])


def test_build_plan_est_reproductible():
    rows = [{"citation": f"C{i}", "accroche": f"A{i}"} for i in range(4)]
    mapping = {"scene.s2.quote.text": "citation", "scene.s1.hook.text": "accroche"}
    a = batch.build_plan(TEMPLATE, rows, mapping, ASSETS, {})
    b = batch.build_plan(TEMPLATE, rows, mapping, ASSETS, {})
    assert [i["filename"] for i in a["items"]] == [i["filename"] for i in b["items"]]
    assert [i["project"]["variation"]["seed"] for i in a["items"]] == [
        i["project"]["variation"]["seed"] for i in b["items"]
    ]
    assert [i["assets_used"] for i in a["items"]] == [i["assets_used"] for i in b["items"]]


def test_build_plan_signale_les_lignes_invalides_sans_supprimer_les_autres():
    rows = [{"citation": "OK", "accroche": "A", "duree": "4"}, {"citation": "", "accroche": "B", "duree": "999"}]
    mapping = {
        "scene.s2.quote.text": "citation",
        "scene.s1.hook.text": "accroche",
        "scene.s1.duration": "duree",
    }
    plan = batch.build_plan(TEMPLATE, rows, mapping, ASSETS, {})
    assert plan["summary"]["invalid_rows"] == [2]
    assert plan["summary"]["ready"] == 1
    assert any("durée" in e for e in plan["items"][1]["errors"])


# --- CSV -------------------------------------------------------------------


def test_parse_detecte_ponto_virgule_et_cp1252():
    payload = "titre;citation;auteur\nCœur;« avis »;Amélie\n".encode("cp1252")
    parsed = csv_source.parse(payload)
    assert parsed["delimiter"] == ";"
    assert parsed["encoding"] == "cp1252"
    assert parsed["columns"] == ["titre", "citation", "auteur"]
    assert parsed["rows"][0]["titre"] == "Cœur"
    assert parsed["rows"][0]["citation"] == "« avis »"


def test_parse_garde_le_bom_et_refuse_un_fichier_vide():
    parsed = csv_source.parse("titre,citation\n1,deux\n".encode("utf-8-sig"))
    assert parsed["columns"][0] == "titre"
    assert parsed["rows"] == [{"titre": "1", "citation": "deux"}]

    with pytest.raises(HTTPException):
        csv_source.parse(b"")


def test_parse_signale_lignes_decalées_et_plafonne_le_nombre_de_lignes():
    parsed = csv_source.parse("a,b,c\n1,2\n3,4,5,6\n".encode("utf-8"))
    assert len(parsed["warnings"]) == 2
    assert parsed["rows"][0]["c"] == ""

    big = "a,b\n" + "1,2\n" * (csv_source.MAX_ROWS + 5)
    with pytest.raises(HTTPException) as exc:
        csv_source.parse(big.encode("utf-8"))
    assert "maximum" in str(exc.value.detail)
