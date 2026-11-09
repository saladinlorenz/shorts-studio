"""Tests de validation des projets Short Videos.

Couvre : projet par defaut, texte long, fichiers manquants,
chemins avec espaces, bornes numeriques, versions inconnues.
"""
from pathlib import Path

from shortvideos import project as project_mod
from shortvideos.validation import LONG_TEXT_CHARS, validate_project


def make_valid_project(tmp_path: Path) -> dict:
    """Projet valide, avec fond et logo dans un dossier contenant des espaces."""
    media = tmp_path / "mes medias" / "fond d'image.png"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"\x89PNG\r\n\x1a\n fake")  # le contenu n'est pas lu par la validation
    logo = media.parent / "le logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n fake")

    proj = project_mod.default_project()
    proj["content"]["background_image"] = str(media)
    proj["content"]["logo"] = str(logo)
    return proj


def test_default_project_has_no_errors(tmp_path):
    proj = make_valid_project(tmp_path)
    errors, warnings = validate_project(proj)
    assert errors == [], f"Le projet valide ne doit pas avoir d'erreurs : {errors}"
    assert warnings == [], f"Le projet court ne doit pas avoir d'avertissements : {warnings}"


def test_missing_background_is_clear_error(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["content"]["background_image"] = str(tmp_path / "n'existe pas.png")
    errors, _ = validate_project(proj)
    assert any("fond" in e.lower() and "introuvable" in e.lower() for e in errors), errors


def test_missing_logo_is_clear_error(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["content"]["logo"] = str(tmp_path / "logo absent.png")
    errors, _ = validate_project(proj)
    assert any("logo" in e.lower() and "introuvable" in e.lower() for e in errors), errors


def test_empty_background_is_error(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["content"]["background_image"] = ""
    errors, _ = validate_project(proj)
    assert any("fond" in e.lower() for e in errors), errors


def test_empty_text_is_error(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["content"]["text"] = "   "
    errors, _ = validate_project(proj)
    assert any("citation" in e.lower() for e in errors), errors


def test_long_text_is_signaled(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["content"]["text"] = "Ce texte est volontairement tres long. " * (
        LONG_TEXT_CHARS // 38 + 2
    )
    _errors, warnings = validate_project(proj)
    assert any("texte long" in w.lower() for w in warnings), warnings


def test_path_with_spaces_and_accents_accepted(tmp_path):
    proj = make_valid_project(tmp_path)  # dossier "mes medias" + "fond d'image.png"
    errors, _ = validate_project(proj)
    assert errors == [], errors


def test_out_of_range_position_is_error(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["position"]["x"] = 2.5
    errors, _ = validate_project(proj)
    assert any("position.x" in e for e in errors), errors


def test_text_start_after_duration_is_error(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["timing"]["text_start"] = 20.0
    proj["timing"]["duration"] = 5.0
    errors, _ = validate_project(proj)
    assert any("apres la fin" in e.lower() for e in errors), errors


def test_odd_dimensions_are_error(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["export"]["width"] = 1081
    errors, _ = validate_project(proj)
    assert any("paires" in e.lower() for e in errors), errors


def test_unknown_version_rejected(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["version"] = 999
    errors, _ = validate_project(proj)
    assert any("version" in e.lower() for e in errors), errors


def test_unknown_template_rejected(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["template"] = "intro_dance"
    errors, _ = validate_project(proj)
    assert any("template" in e.lower() for e in errors), errors


def test_bad_color_format_rejected(tmp_path):
    proj = make_valid_project(tmp_path)
    proj["theme"]["text_color"] = "blanc"
    errors, _ = validate_project(proj)
    assert any("RRGGBB" in e for e in errors), errors


def test_save_load_roundtrip_with_spaces(tmp_path):
    """Sauvegarde et reouverture d'un projet dont le chemin contient des espaces."""
    proj = make_valid_project(tmp_path)
    path = tmp_path / "mes projets" / "projet d'exemple.json"
    project_mod.save_project(proj, path)
    assert path.exists()
    loaded = project_mod.load_project(path)
    assert loaded["content"]["text"] == proj["content"]["text"]
    assert loaded["content"]["background_image"] == proj["content"]["background_image"]
    assert loaded["timing"]["duration"] == proj["timing"]["duration"]
    errors, _ = validate_project(loaded)
    assert errors == [], errors


def test_load_missing_file_error_message(tmp_path):
    try:
        project_mod.load_project(tmp_path / "absent.json")
    except RuntimeError as e:
        assert "introuvable" in str(e)
    else:
        raise AssertionError("load_project aurait du lever une erreur")


def test_snapshot_is_isolated():
    proj = project_mod.default_project()
    snap = project_mod.snapshot(proj)
    proj["content"]["text"] = "modifie apres snapshot"
    assert snap["content"]["text"] != "modifie apres snapshot"
