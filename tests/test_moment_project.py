"""Moment detect -> projet v2 : le clip EST le moment, a la frame pres.

Le contrat qui justifie ce module entier est verifie ici :

- la frame 0 de la composition = l instant de depart du moment, donc la piste vocale
  decoupee dans la source se retrouve calee sur l'image sans decalage ;
- les scenes carrelent la timeline sans trou ni recouvrement ;
- le .sRT re-derive par ``delivery.srt_cues`` (qui lit ``resolve()``, donc les frames
  reellement recues par Remotion) retrouve les bornes de l'ASR a une frame pres ;
- le branding n'entre que si un pack est passe explicitement ;
- rien n'invente de texte : pas de cue, pas de projet.
"""
from __future__ import annotations

import pytest

from shortvideos import branding, delivery, moment_project, moments, schema, validation

TRANSCRIPT = {
    "provider": "groq",
    "model": "whisper-large-v3-turbo",
    "language": "fr",
    "duration": 90.0,
    "segments": [
        {"start": 12.0, "end": 15.6, "text": "Ce que personne ne te dit, c'est que la discipline s'entraine."},
        {"start": 15.9, "end": 19.4, "text": "Ton cerveau cherche la recompense immediate, encore et encore."},
        {"start": 19.6, "end": 23.8, "text": "En realite, le probleme n'est pas la paresse."},
        {"start": 24.2, "end": 28.0, "text": "Deux minutes de clarte valent dix heures d'agitation."},
        {"start": 40.0, "end": 44.0, "text": "Et pourtant, une seule regle change tout."},
    ],
}


@pytest.fixture(autouse=True)
def media_store(tmp_path, monkeypatch):
    """Les references « media:// » sont verifiees sur disque : on simule le dossier media."""
    store = tmp_path / "media"
    store.mkdir()
    (store / "voice01.wav").write_bytes(b"RIFF")
    (store / "voice02.wav").write_bytes(b"RIFF")
    (store / "fond01.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(validation, "MEDIA_STORE", store)
    return store


@pytest.fixture()
def moment():
    found = moments.detect(TRANSCRIPT, min_seconds=10.0, max_seconds=20.0, top=1)
    assert found, "un transcript a silences doit produire au moins un moment"
    return found[0]


@pytest.fixture()
def pack():
    normalized, errors, _warnings = branding.normalize({
        "label": "Atelier Runa",
        "theme": {"accent_color": "#C4F1BE", "font_family": "inter"},
        "signature": {"handle": "@atelier.runa"},
    })
    assert errors == []
    return normalized


def _voice_ref(suffix: str = "01") -> str:
    return f"media://voice{suffix}"


# --- timeline ------------------------------------------------------------------


def test_les_scenes_carrellent_la_timeline_sans_trou(moment):
    fps = 30
    specs, total = moment_project.caption_timeline(moment["cues"], fps,
                                                   end_seconds=moment["duration"])
    assert specs and total > 0
    assert specs[0]["scene_start"] == 0, "frame 0 = instant de depart du moment"
    for left, right in zip(specs, specs[1:]):
        assert left["scene_end"] == right["scene_start"], (left, right)
    assert specs[-1]["scene_end"] == total
    for spec in specs:
        assert spec["scene_end"] > spec["scene_start"]
        assert spec["scene_start"] <= spec["cue_start"] < spec["cue_end"] <= spec["scene_end"]


def test_les_frames_des_cues_sont_ceelles_de_l_asr(moment):
    """Les bornes resolues viennent des segments ASR, arrondies a la frame — pas estimees."""
    fps = 30
    specs, _total = moment_project.caption_timeline(moment["cues"], fps,
                                                   end_seconds=moment["duration"])
    starts = [round(c["start"] * fps) for c in moment["cues"]]
    ends = [round(c["end"] * fps) for c in moment["cues"]]
    assert specs[0]["cue_start"] == starts[0]
    assert specs[-1]["cue_end"] == ends[-1]
    for spec in specs:
        assert spec["cue_start"] in starts, spec
        assert spec["cue_end"] in ends, spec
    frames = [(s["cue_start"], s["cue_end"]) for s in specs]
    assert frames == sorted(frames)


def test_un_segment_long_reste_un_seul_cue(moment):
    """Couper un segment ASR inventerait un temps intermediaire : un segment = un cue."""
    specs, _ = moment_project.caption_timeline(moment["cues"], 30, end_seconds=moment["duration"])
    longest = max(moment["cues"], key=lambda c: c["end"] - c["start"])
    assert any(s["raw_start"] == longest["raw_start"] for s in specs)
    assert len(specs) <= len(moment["cues"])


def test_un_cue_trop_proche_du_precedent_est_fondu():
    """Deux segments qui démarrent à moins d'une demi-seconde donneraient une scène
       refusée par le format : ils ne font qu'un bloc, les bornes extérieures restent."""
    cues = [
        {"start": 0.0, "end": 0.3, "text": "Deux minutes.", "raw_start": 10.0, "raw_end": 10.3},
        {"start": 0.4, "end": 2.0, "text": "de clarte valent dix heures d agitation.",
         "raw_start": 10.4, "raw_end": 12.0},
        {"start": 9.0, "end": 11.0, "text": "Troisieme pensee.", "raw_start": 19.0, "raw_end": 21.0},
    ]
    specs, total = moment_project.caption_timeline(cues, 30, end_seconds=11.0, min_scene_seconds=0.5)
    assert len(specs) == 2, [s["text"] for s in specs]
    assert specs[0]["text"].startswith("Deux minutes.") and "clarte" in specs[0]["text"]
    assert specs[0]["cue_start"] == 0 and specs[0]["cue_end"] == 60
    assert specs[-1]["cue_end"] == total == 330


def test_deux_segments_chevauchants_ne_se_devorent_pas():
    """Whisper arrive parfois a fermer un segment apres l ouverture du suivant : le
       second cue demarre a la fin du premier, jamais avant. Deux sous-titres superposes
       rendraient le clip illegible."""
    cues = [
        {"start": 0.0, "end": 4.0, "text": "Premiere pensee.", "raw_start": 10.0, "raw_end": 14.0},
        {"start": 3.0, "end": 7.0, "text": "Deuxieme pensee.", "raw_start": 13.0, "raw_end": 17.0},
    ]
    specs, total = moment_project.caption_timeline(cues, 30, end_seconds=7.0)
    assert [s["cue_start"] for s in specs] == [0, 120]
    assert specs[1]["cue_end"] == total == 210


def test_sans_cue_il_n_y_a_pas_de_timeline():
    assert moment_project.caption_timeline([], 30, end_seconds=10.0) == ([], 0)
    assert moment_project.caption_timeline([{"text": "   "}], 30)[0] == []


# --- projet genere -------------------------------------------------------------


def test_projet_genere_est_valide_et_dans_le_format_v2(moment):
    built = moment_project.generate(moment, voice_ref=_voice_ref())
    assert built["errors"] == [], built["errors"]
    project = built["project"]
    assert project["version"] == schema.SCHEMA_VERSION_V2
    assert project["model"]["id"] == "quote_cinematic"
    errors, _warnings = validation.validate_project_v2(schema.clone(project))
    assert errors == []
    assert len(project["content"]["scenes"]) == built["cues"] == len(built["timeline"])
    assert project["audio"]["voice"] == _voice_ref() and project["audio"]["enabled"] is True


def test_la_composition_couvre_exactement_le_moment(moment):
    built = moment_project.generate(moment, voice_ref=_voice_ref())
    project = built["project"]
    fps = project["export"]["fps"]
    assert built["start"] == pytest.approx(moment["start"], abs=0.01)
    assert built["duration"] == pytest.approx(sum(s["duration"] for s in project["content"]["scenes"]), abs=0.01)
    assert built["end"] == pytest.approx(built["start"] + built["duration"], abs=0.01)
    resolved = built["project"]
    assert schema.total_frames(resolved) == built["timeline"][-1]["scene_end"]


def test_le_srt_rederive_retrouve_l_asr_a_la_frame(moment):
    """Le .sRT livrable est re-tire du projet : c'est la preuve que le sous-titre colle a la voix."""
    built = moment_project.generate(moment, voice_ref=_voice_ref())
    cues = delivery.srt_cues(built["project"])
    specs = built["timeline"]
    assert len(cues) == len(specs)
    for cue, spec in zip(cues, specs):
        assert cue["layer_id"] == f"cue-{specs.index(spec) + 1}"
        assert abs(cue["start_frame"] - spec["cue_start"]) <= 1, (cue, spec)
        assert abs(cue["end_frame"] - spec["cue_end"]) <= 1, (cue, spec)
        assert cue["text"] == spec["text"]
    assert cues[0]["start_frame"] == 0, "le premier mot doit etre legendee des la frame 0"
    srt = delivery.srt_from_project(built["project"])
    assert srt.startswith("1\r\n00:00:00,000 -->") and "-->" in srt
    assert srt.count("-->") == len(specs), "un bloc SRT par scene, pas un de plus"


def test_la_signature_de_marque_n_est_pas_un_sous_titre(moment):
    built = moment_project.generate(moment, handle="@atelier", voice_ref=_voice_ref())
    cues = delivery.srt_cues(built["project"])
    assert all("cue-" in c["layer_id"] for c in cues), cues
    assert built["project"]["content"]["signature"]["handle"] == "@atelier"


@pytest.mark.parametrize("fps", [24, 30, 60])
def test_le_temps_en_secondes_ne_depend_pas_du_fps(moment, fps):
    built = moment_project.generate(moment, voice_ref=_voice_ref(), fps=fps)
    assert built["project"]["export"]["fps"] == fps
    assert built["duration"] == pytest.approx(moment["duration"], abs=0.6)
    specs = built["timeline"]
    assert specs[-1]["scene_end"] == pytest.approx(built["duration"] * fps, abs=1)
    for spec in specs:
        assert spec["cue_start"] % 1 == 0 and spec["cue_end"] > spec["cue_start"]


def test_la_generation_est_deterministe(moment, pack):
    first = moment_project.generate(moment, pack=pack, voice_ref=_voice_ref(), handle="@r")
    second = moment_project.generate(moment, pack=pack, voice_ref=_voice_ref(), handle="@r")
    assert first["project"] == second["project"]
    assert first["timeline"] == second["timeline"]


def test_sans_pack_le_theme_reste_celui_du_gabarit(moment):
    built = moment_project.generate(moment, voice_ref=_voice_ref())
    assert built["project"]["theme"] == schema.default_theme()


def test_le_pack_ne_touche_pas_au_texte_des_scenes(moment, pack):
    sans = moment_project.generate(moment, voice_ref=_voice_ref())
    avec = moment_project.generate(moment, pack=pack, voice_ref=_voice_ref(),
                                   handle="@atelier.runa", brand_label=pack["label"])
    assert avec["project"]["theme"]["accent_color"] == "#C4F1BE"
    assert avec["project"]["content"]["signature"]["handle"] == "@atelier.runa"
    assert [s["layers"][0]["text"] for s in avec["project"]["content"]["scenes"]] == \
           [s["layers"][0]["text"] for s in sans["project"]["content"]["scenes"]]
    assert avec["name"].startswith("moment-") and " " not in avec["name"]
    assert "Atelier Runa" in avec["project"]["publish"]["title"]
    assert "Atelier Runa" not in sans["project"]["publish"]["title"], \
        "sans pack demande, la marque du client n apparait nulle part"


def test_fond_de_scene_non_applique_par_defaut(moment):
    """La composition rejoue le media d arriere-plan a chaque scene : mieux vaut une
       scene sans fond qu un montage saccade. L'utilisateur I ajoute de lui-meme."""
    built = moment_project.generate(moment, voice_ref=_voice_ref())
    for scene in built["project"]["content"]["scenes"]:
        assert scene["background"]["media"] == ""
    avec_fond = moment_project.generate(moment, voice_ref=_voice_ref(), background_media="media://fond01")
    assert avec_fond["project"]["content"]["scenes"][0]["background"]["media"] == "media://fond01"


def test_sans_piste_vocale_le_projet_le_die_haut(moment):
    built = moment_project.generate(moment)
    assert built["project"]["audio"]["enabled"] is False
    assert any("muet" in w for w in built["warnings"]), built["warnings"]


# --- refus ---------------------------------------------------------------------


def test_un_moment_sans_texte_ne_devient_pas_un_projet():
    with pytest.raises(moment_project.MomentProjectError):
        moment_project.generate({"start": 1.0, "end": 5.0, "cues": []})
    with pytest.raises(moment_project.MomentProjectError):
        moment_project.generate({"start": 1.0, "end": 5.0, "cues": [{"text": "  "}]})
    with pytest.raises(moment_project.MomentProjectError):
        moment_project.generate("pas un moment")


def test_un_modele_inconnu_est_refuse(moment):
    with pytest.raises(moment_project.MomentProjectError):
        moment_project.generate(moment, model_id="clip_magique")


def test_le_nom_du_projet_vient_du_moment_pas_de_l_exterieur(moment):
    built = moment_project.generate(moment, voice_ref=_voice_ref())
    assert built["name"] == built["project"]["name"]
    assert built["name"].startswith("moment-")
    assert all(c.isalnum() or c in "-." for c in built["name"]), built["name"]
