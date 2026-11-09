"""Detection des moments forts : les bornes viennent de l'ASR, rien n'est invente.

Contrats verifies ici :

- les moments respectent les bornes de duree, ne se chevauchent pas, et sont
  deterministes (mêmes donnees, meme resultat) ;
- un sous-titre = un segment ASR : temps relatifs et bornes brutes retrouvent
  l'horodatage de la transcription ;
- l'energie mesuree entre dans le score, les silences mesures sont reels ;
- titre, description et hashtags ne contiennent que des mots du moment.
"""
from __future__ import annotations

import math
import re

import pytest

from shortvideos import moments

SEGMENTS = [
    (12.0, 15.6, "Ce que personne ne te dit, c'est que la discipline s'entraine."),
    (15.9, 19.4, "Ton cerveau cherche la recompense immediate, encore et encore."),
    (19.6, 23.8, "En realite, le probleme n'est pas la paresse, c'est l'absence de signal."),
    (24.1, 25.4, "Deux minutes."),
    (24.9, 28.0, "de clarte valent dix heures d'agitation."),
    (28.3, 31.0, "Voila pourquoi tu abandonnes au bout de trois jours."),
    (40.0, 44.0, "Et pourtant, une seule regle change tout : commence avant d'etre pret."),
    (60.5, 63.2, "Le secret est simple, mais personne ne le pratique."),
]


@pytest.fixture()
def transcript():
    return {
        "provider": "fake",
        "model": "whisper-large-v3-turbo",
        "language": "fr",
        "duration": 90.0,
        "segments": [{"start": s, "end": e, "text": t} for s, e, t in SEGMENTS],
    }


@pytest.fixture()
def energy(transcript):
    """Enveloppe mesuree sur un signal synthetique : crete pendant la parole, creux entre."""
    window = 0.05
    rms = []
    for index in range(int(transcript["duration"] / window)):
        at = index * window
        speaking = any(s - 0.4 <= at <= e for s, e, _ in SEGMENTS)
        rms.append(0.72 if speaking else 0.01)
    return {"window_s": window, "duration": transcript["duration"], "rms": rms}


# --- detection ----------------------------------------------------------------


def test_detect_respecte_les_bornes_de_duree_et_l_ordre_temporel(transcript, energy):
    found = moments.detect(transcript, energy=energy, min_seconds=10.0, max_seconds=20.0, top=5)
    assert found, "un transcript a silences doit produire des moments"
    for moment in found:
        assert moment["duration"] <= 20.0 + 0.01, moment
        assert 0 <= moment["score"] <= 100
        assert moment["reasons"], "un moment sans critere explique ne se montre pas"
        assert moment["start"] >= 0.0 and moment["end"] <= transcript["duration"]
    starts = [m["start"] for m in found]
    assert starts == sorted(starts), "les moments sont presentes dans l ordre de la video"
    assert [m["id"] for m in found] == ["m" + str(i) for i in range(1, len(found) + 1)]


def test_detect_ne_chevauche_pas_deux_moments(transcript, energy):
    found = moments.detect(transcript, energy=energy, min_seconds=8.0, max_seconds=45.0, top=8)
    assert len(found) > 1, "plusieurs moments attendus sur 90 s"
    for left, right in zip(found, found[1:]):
        overlap = min(left["end"], right["end"]) - max(left["start"], right["start"])
        size = min(left["duration"], right["duration"])
        assert overlap <= moments.OVERLAP_TOLERANCE * size + 0.01, (left, right)


def test_detect_est_deterministe(transcript, energy):
    first = moments.detect(transcript, energy=energy, top=3)
    second = moments.detect(transcript, energy=energy, top=3)
    assert [(m["start"], m["end"], m["score"]) for m in first] == [
        (m["start"], m["end"], m["score"]) for m in second
    ]


def test_detect_survit_a_des_segments_incoherents(transcript):
    transcript["segments"].extend([
        {"start": float("nan"), "end": 70.0, "text": "borne invalide"},
        {"start": 70.0, "end": 60.0, "text": "a l envers"},
        {"start": 71.0, "end": 74.0, "text": ""},
        "pas un dictionnaire",
        {"end": 78.0, "text": "sans debut"},
    ])
    found = moments.detect(transcript, top=3)
    assert found
    for moment in found:
        assert math.isfinite(moment["start"]) and math.isfinite(moment["end"])


def test_detect_sans_transcription_n_invente_rien():
    assert moments.detect({}, top=3) == []
    assert moments.detect({"segments": []}, top=3) == []
    assert moments.detect({"segments": [{"start": 1.0, "end": 2.0, "text": "un"}]}, top=3) == []


def test_detect_sur_un_flux_continu_sans_vraies_pauses():
    """Pas de silence de 0,3 s : on retombe sur les frontieres ASR plutot que de rien proposer."""
    segments = []
    cursor = 0.0
    for index in range(14):
        segments.append({"start": round(cursor, 3), "end": round(cursor + 4.6, 3),
                         "text": "Phrase numero " + str(index) + " avec un chiffre et une erreur possible"})
        cursor += 4.7
    found = moments.detect({"duration": cursor, "segments": segments}, top=2)
    assert found, "un flux continu doit malgre tout produire un moment"


def test_detect_ancre_les_fenetres_sur_des_pensees_completes(transcript, energy):
    found = moments.detect(transcript, energy=energy, min_seconds=10.0, max_seconds=20.0, top=1)[0]
    starts = [s for s, _e, _t in SEGMENTS]
    ends = [e for _s, e, _t in SEGMENTS]
    assert any(abs(found["start"] - s) < 0.01 for s in starts), found
    assert any(abs(found["end"] - e) < 0.01 for e in ends), found


def test_l_energie_renseigne_le_score(transcript):
    """L'enveloppe entre dans le score : la crete est relative a la moyenne du fichier."""
    window = 0.05
    frames = int(transcript["duration"] / window)
    hot, flat = [], []
    for index in range(frames):
        at = index * window
        hot.append(0.9 if 12.0 <= at < 24.0 else 0.05)
        flat.append(0.05)
    loud = {"window_s": window, "duration": transcript["duration"], "rms": hot}
    plane = {"window_s": window, "duration": transcript["duration"], "rms": flat}
    score_loud, reasons_loud = moments.score_window(transcript, 12.0, 24.0, energy=loud)
    score_flat, reasons_flat = moments.score_window(transcript, 12.0, 24.0, energy=plane)
    assert score_loud > score_flat, (score_loud, score_flat)
    assert any("nergie" in r for r in reasons_loud), reasons_loud
    assert not any("nergie" in r and "moyenne du fichier" in r for r in reasons_flat), reasons_flat
    # une enveloppe absente ne doit pas etre comptee comme un silence
    score_sans, reasons_sans = moments.score_window(transcript, 12.0, 24.0)
    assert all("nergie" not in r for r in reasons_sans), reasons_sans
    stats = moments.energy_stats(loud, 12.0, 24.0)
    assert stats["mean"] > stats["global_mean"] and stats["peak"] >= stats["mean"]


def test_segments_in_et_edge_gaps_mesurent_le_reel(transcript):
    inside = moments.segments_in(transcript, 12.0, 19.5)
    assert [round(s["start"], 1) for s in inside] == [12.0, 15.9]
    before, after = moments.edge_gaps(transcript, 12.0, 23.8)
    assert before == pytest.approx(12.0)
    assert after == pytest.approx(24.1 - 23.8, abs=0.01), \
        "le silence apres la fenetre se mesure au premier mot ASR suivant"
    _, longue = moments.edge_gaps(transcript, 12.0, 31.0)
    assert longue == pytest.approx(40.0 - 31.0, abs=0.01), "le blanc reel de 9 s est mesure"
    assert moments.speech_density(inside, 12.0, 19.5) > 0


# --- sous-titres ----------------------------------------------------------------


def test_captions_un_cue_par_segment_et_temps_relatifs(transcript):
    segments = moments.segments_in(transcript, 12.0, 23.8)
    cues = moments.captions(segments, 12.0)
    assert len(cues) == len(segments)
    assert cues[0]["start"] == pytest.approx(0.0)
    for cue, segment in zip(cues, segments):
        assert cue["raw_start"] == pytest.approx(segment["start"], abs=0.01)
        assert cue["raw_end"] == pytest.approx(segment["end"], abs=0.01)
        assert cue["end"] > cue["start"]
        assert cue["text"].strip()


def test_wrap_caption_ne_coupe_jamais_un_mot():
    long_text = " ".join("mot" + str(i) for i in range(30))
    wrapped = moments.wrap_caption(long_text, max_chars=46, max_lines=2)
    lines = wrapped.split("\n")
    assert len(lines) == 2
    assert all(len(line) <= 47 for line in lines), lines
    assert all(len(word) <= 46 for line in lines for word in line.split()), lines
    assert wrapped.endswith("…"), "ce qui deborde doit etre signale"
    assert "mot0" in lines[0]


def test_wrap_caption_ne_deborde_pas_de_la_largeur():
    """Le « … » qui signale le debordement compte dans la ligne : 47 caracteres sur un
       bloc de 46 debordent du calque et le rendu coupe le mot."""
    long_text = " ".join("mot" + str(i) for i in range(30))
    lines = moments.wrap_caption(long_text, max_chars=28, max_lines=2).split("\n")
    assert len(lines) == 2
    assert all(len(line) <= 28 for line in lines), [len(line) for line in lines]
    assert lines[-1].endswith("…")


def test_wrap_caption_garde_un_texte_court_intact():
    assert moments.wrap_caption("Deux minutes.") == "Deux minutes."


# --- criteres lexicaux ----------------------------------------------------------


def test_marker_hits_ne_matche_pas_un_mot_interieur_a_un_autre():
    hits = moments.marker_hits("La transaction traverse un panier de données.")
    assert "chiffre" not in hits, hits
    assert moments.marker_hits("Deux ans de travail pour une seule ligne.")["chiffre"] == ["ans"]
    autres = moments.marker_hits("Le secret est simple : voila pourquoi tu abandonnes.")
    assert "amorce" in autres and "chute" in autres, autres


def test_keywords_eclate_les_elisions_et_jette_les_vidanges():
    mots = moments.keywords("c'est l'absence de signal, le signal de l'agitation du public")
    assert "signal" in mots
    assert "agitation" in mots, "l apostrophe doit etre eclatee"
    assert "dagitation" not in mots
    assert all(w not in mots for w in ("cest", "c", "est", "l"))
    assert all(m not in moments.STOPWORDS for m in mots)
    assert all(not m.isdigit() for m in mots), "un chiffre seul n est pas un sujet"


# --- publies ---------------------------------------------------------------------


def test_title_from_reste_une_citation_du_moment(transcript, energy):
    moment = moments.detect(transcript, energy=energy, top=1)[0]
    titre = moments.title_from(moment)
    assert titre
    assert len(titre) <= 80
    for word in moment["text"].split()[:2]:
        assert word.strip(".,;:!?").lower() in titre.lower() or len(word) < 4
    with_brand = moments.title_from(moment, brand_label="Atelier Runa")
    assert "Atelier Runa" in with_brand and len(with_brand) <= 80


def test_hashtags_uniquement_des_mots_du_moment(transcript, energy):
    moment = moments.detect(transcript, energy=energy, top=1)[0]
    tags = moments.hashtags_from(moment, handle="@atelier")
    assert tags[0] == "#atelier"
    # le vocabulaire est celui du moment, tel que le decoupe l'extracteur de mots-cles
    vocabulary = {moments.ascii_slug(t) for t in re.split(r"[^\w]+", moment["text"].lower()) if t}
    for tag in tags[1:]:
        assert tag.startswith("#") and " " not in tag
        assert tag[1:] in vocabulary, tag
    assert len(set(tags)) == len(tags)


def test_description_from_tient_l_extrait_et_les_credites(transcript, energy):
    moment = moments.detect(transcript, energy=energy, top=1)[0]
    description = moments.description_from(moment, source_title="Episode 12",
                                           handle="@atelier", brand_label="Atelier Runa")
    assert len(description) <= 320
    assert "Episode 12" in description
    assert "@atelier" in description
    assert moment["text"][:18].strip() in description, "le corps est l extrait reel"


def test_metadata_from_porte_les_trois_champs_et_les_temps(transcript, energy):
    moment = moments.detect(transcript, energy=energy, top=1)[0]
    meta = moments.metadata_from(moment, source_title="Episode 12", handle="@a")
    assert set(meta) >= {"title", "description", "hashtags", "start", "end", "duration", "score"}
    assert meta["start"] == moment["start"] and meta["end"] == moment["end"]
    assert meta["title"] and meta["hashtags"]
