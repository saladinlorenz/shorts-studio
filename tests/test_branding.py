"""Packs de marque client : normalisation, application et persistance.

Le contrat protege ici est double, comme pour le catalogue d'effets :
``normalize()`` refuse ce qui est faux et ne remplace jamais une valeur par une
hypothese, et ``apply_brand()`` n'ecrit que dans des cles qui existent deja dans le
projet. Le test de persistance verifie que ``save`` puis ``get`` puis ``apply``
retrouvent exactement le pack normalise — un pack enregistre a la main doit pouvoir
etre recharge.
"""
from __future__ import annotations

import pytest

from shortvideos import branding, schema
from shortvideos.schema import SCHEMA_VERSION_V2

from server import brands as brands_mod
from server import security


def _raw() -> dict:
    return {
        "label": "Client Cinemoche",
        "notes": "palette chaude, signature en bas",
        "theme": {
            "font_size": 96,
            "text_color": "#FFF2D6",
            "accent_color": "#E2B458",
            "font_family": "anton",
            "reglage_inconnu": 1,
        },
        "signature": {"media": "media://logo_ab12", "handle": "@cinemoche", "enabled": True},
        "audio": {"music": "media://song_cd34", "music_volume": 1.8, "enabled": True},
        "models": ["quote_cinematic"],
    }


def test_normalize_accepte_un_pack_sain_et_signale_le_superflu():
    pack, errors, warnings = branding.normalize(_raw())
    assert errors == []
    assert pack["theme"]["font_size"] == 96 and pack["theme"]["text_color"] == "#FFF2D6"
    assert pack["signature"]["media"] == "media://logo_ab12"
    assert pack["audio"]["music_volume"] == 1.0, "le volume est ramene a la borne 1, pas conserve tel quel"
    assert "reglage_inconnu" not in pack["theme"]
    assert any("reglage" in w for w in warnings), "une cle inconnue est ignoree, jamais stockee"


@pytest.mark.parametrize(
    ("section", "value", "fragment"),
    [
        ("signature", {"media": "C:/x/logo.png"}, "chemin"),
        ("signature", {"media": "https://e.com/l.png"}, "chemin"),
        ("theme", {"text_color": "rouge"}, "couleur"),
        ("theme", {"font_family": "comic-sans"}, "police"),
    ],
)
def test_normalize_refuse_chemins_couleurs_et_polices_hors_catalogue(section, value, fragment):
    raw = _raw()
    raw[section] = dict(value)
    _, errors, _ = branding.normalize(raw)
    assert any(fragment in e for e in errors), errors


def test_normalize_refuse_un_modele_hors_catalogue():
    raw = _raw()
    raw["models"] = ["quote_cinematic", "modele-fantome"]
    _, errors, _ = branding.normalize(raw)
    assert any("modele-fantome" in e for e in errors)
    assert any("nom de client" in e for e in branding.normalize({"theme": {}})[1])


def _project() -> dict:
    return schema.new_project("quote_cinematic")


def test_apply_brand_n_touche_que_theme_signature_audio():
    pack, errors, _ = branding.normalize(_raw())
    assert errors == []
    project = _project()
    scenes_before = project["content"]["scenes"]

    patched, warnings = branding.apply_brand(project, pack)

    assert patched.get("version") == SCHEMA_VERSION_V2
    assert patched["content"]["scenes"] == scenes_before, "les scenes ne sont pas modifiees"
    assert patched["theme"]["font_size"] == 96 and patched["theme"]["text_color"] == "#FFF2D6"
    assert patched["content"]["signature"]["media"] == "media://logo_ab12"
    assert patched["audio"]["music"] == "media://song_cd34"
    assert warnings == []


def test_apply_brand_a_vertit_sur_une_signature_desactivee():
    # le pack impose un logo mais ne re-active pas la signature : si le projet a
    # desactive sa signature, le logo ne s'affichera pas — il faut le signaler.
    pack, errors, _ = branding.normalize({"label": "Client", "signature": {"media": "media://logo_ab12"}})
    assert errors == []
    project = _project()
    project["content"]["signature"]["enabled"] = False

    patched, warnings = branding.apply_brand(project, pack)
    assert any("Signature d" in w for w in warnings), warnings
    assert patched["content"]["signature"]["media"] == "media://logo_ab12"


def test_apply_brand_reactive_quand_le_pack_force_enabled_true():
    pack, _, _ = branding.normalize(_raw())  # _raw porte signature.enabled = True
    project = _project()
    project["content"]["signature"]["enabled"] = False

    patched, warnings = branding.apply_brand(project, pack)
    assert patched["content"]["signature"]["enabled"] is True
    assert not any("Signature d" in w for w in warnings), warnings


@pytest.fixture()
def brands_dir(tmp_path, monkeypatch):
    folder = tmp_path / "brands"
    folder.mkdir()
    monkeypatch.setattr(brands_mod, "BRANDS_DIR", folder)
    monkeypatch.setattr(security, "ALLOWED_DIRS", (folder,))
    return folder


def test_store_roundtrip_et_application(brands_dir):
    saved = brands_mod.save_brand(_raw())
    brand_id = saved["brand"]["id"]
    assert saved["warnings"], "le reglage inconnu doit remonter comme avertissement"

    listed = [b["id"] for b in brands_mod.list_brands()]
    assert brand_id in listed

    pack = brands_mod.get_pack(brand_id)
    assert pack["theme"]["font_size"] == 96 and pack["audio"]["music_volume"] == 1.0

    applied = brands_mod.apply_to_project(brand_id, _project())
    assert applied["project"]["theme"]["text_color"] == "#FFF2D6"

    assert brands_mod.delete_brand(brand_id) == {"deleted": brand_id}
    assert brands_mod.list_brands() == []


def test_store_bloque_un_pack_invalide(brands_dir):
    from fastapi import HTTPException

    raw = _raw()
    raw["signature"] = {"media": "C:/interdit.png"}
    with pytest.raises(HTTPException) as exc:
        brands_mod.save_brand(raw)
    assert exc.value.status_code == 400
    assert list(brands_dir.glob("*.json")) == [], "un pack refuse n'est jamais ecrit"
