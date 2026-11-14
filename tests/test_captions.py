"""Alignement energie des sous-titres sur la voix off (shortvideos.captions).

Aucun moteur reel : les WAV sont synthetises (stdlib wave) avec des bouffees de
tonalite et des silences connus, pour verifier que les mots suivent la parole et
que les silences sont enjambes. Le format des cues doit rester compatible avec
moment_project.caption_timeline.
"""
from __future__ import annotations

import array
import math
import wave

import pytest

from shortvideos import captions, moment_project, resolve, schema, validation


def _write_wav(path, segments, *, rate=22050, channels=1):
    """segments : liste (duree_s, amplitude). amplitude 0 = silence, >0 = tonalite."""
    samples = array.array("h")
    for duration, amplitude in segments:
        count = int(duration * rate)
        for i in range(count):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * i / rate)) if amplitude > 0 else 0
            for _ in range(channels):
                samples.append(value)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())


def _bursts(path, *, leading=0.0, trailing=0.0, channels=1):
    # trois bouffees de 0,4 s separees par 0,3 s de silence
    segments = []
    if leading:
        segments.append((leading, 0.0))
    segments += [(0.4, 0.8), (0.3, 0.0), (0.4, 0.8), (0.3, 0.0), (0.4, 0.8)]
    if trailing:
        segments.append((trailing, 0.0))
    _write_wav(path, segments, channels=channels)


def test_align_words_trims_leading_and_trailing_silence(tmp_path):
    wav = tmp_path / "voice.wav"
    _bursts(wav, leading=0.5, trailing=0.5)
    aligned = captions.align_words(wav, "aa bb cc")
    assert [w["word"] for w in aligned] == ["aa", "bb", "cc"]
    starts = [w["start"] for w in aligned]
    ends = [w["end"] for w in aligned]
    assert starts == sorted(starts) and ends == sorted(ends)
    assert all(w["start"] <= w["end"] for w in aligned)
    # la parole commence a 0,5 s et finit a 2,3 s : les silences sont enjambes
    assert aligned[0]["start"] >= 0.4
    assert aligned[0]["start"] < 0.7
    assert aligned[-1]["end"] <= 2.4
    assert aligned[-1]["end"] > 2.0


def test_align_words_empty_text_returns_empty(tmp_path):
    wav = tmp_path / "voice.wav"
    _bursts(wav)
    assert captions.align_words(wav, "") == []
    assert captions.align_words(wav, "   ") == []


def test_align_words_silent_audio_falls_back_to_uniform(tmp_path):
    wav = tmp_path / "silent.wav"
    _write_wav(wav, [(2.0, 0.0)])
    aligned = captions.align_words(wav, "un deux trois")
    assert [w["word"] for w in aligned] == ["un", "deux", "trois"]
    assert aligned[0]["start"] == 0.0
    assert aligned[-1]["end"] == pytest.approx(2.0, abs=0.05)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(aligned, aligned[1:]))


def test_align_words_gives_longer_words_more_time(tmp_path):
    wav = tmp_path / "tone.wav"
    _write_wav(wav, [(2.0, 0.8)])
    aligned = captions.align_words(wav, "a bbbbbbbb")
    short, long = aligned
    assert (long["end"] - long["start"]) > (short["end"] - short["start"])


def test_align_words_handles_stereo(tmp_path):
    wav = tmp_path / "stereo.wav"
    _bursts(wav, channels=2)
    aligned = captions.align_words(wav, "aa bb cc")
    assert len(aligned) == 3
    assert aligned[0]["start"] >= 0.0
    assert aligned[-1]["end"] <= 1.8 + 0.05


def test_align_words_unreadable_wav_raises_caption_error(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wav file")
    with pytest.raises(captions.CaptionError):
        captions.align_words(bad, "un deux")


def test_caption_cues_text_is_preserved_and_ordered(tmp_path):
    wav = tmp_path / "voice.wav"
    _bursts(wav)
    text = "un deux trois quatre cinq six"
    cues = captions.caption_cues(wav, text, fps=30)
    assert cues
    assert " ".join(c["text"] for c in cues) == text
    assert all(c["start"] <= c["end"] for c in cues)
    assert [c["start"] for c in cues] == sorted(c["start"] for c in cues)


def test_caption_cues_breaks_on_a_long_pause(tmp_path):
    wav = tmp_path / "pause.wav"
    # deux blocs de parole separes par un silence franc (> 0,3 s)
    _write_wav(wav, [(0.8, 0.8), (0.6, 0.0), (0.8, 0.8)])
    cues = captions.caption_cues(wav, "un deux trois quatre cinq six sept huit", fps=30, max_words=8)
    assert len(cues) >= 2, "un silence franc doit separer les lignes"


def test_caption_cues_respects_max_words(tmp_path):
    wav = tmp_path / "tone.wav"
    _write_wav(wav, [(3.0, 0.8)])
    text = " ".join(f"mot{i}" for i in range(12))
    cues = captions.caption_cues(wav, text, fps=30, max_words=4, max_chars=200)
    assert all(len(c["text"].split()) <= 4 for c in cues)


def test_caption_cues_feed_caption_timeline(tmp_path):
    wav = tmp_path / "voice.wav"
    _bursts(wav, leading=0.2)
    cues = captions.caption_cues(wav, "un deux trois quatre cinq six", fps=30)
    specs, total = moment_project.caption_timeline(cues, 30)
    assert specs and total > 0
    assert specs[0]["scene_start"] == 0
    assert all(s["scene_end"] > s["scene_start"] for s in specs)


def test_caption_scenes_builds_caption_layers(tmp_path):
    wav = tmp_path / "voice.wav"
    _bursts(wav, leading=0.2, trailing=0.2)
    scenes, total = captions.caption_scenes(wav, "un deux trois quatre cinq six", 30)
    assert scenes and total > 0
    for scene in scenes:
        assert scene["duration"] >= schema.SCENE_DURATION_MIN
        captions_layers = [l for l in scene["layers"] if l["role"] == "caption"]
        assert captions_layers, "chaque scene porte un calque de sous-titre"
        assert all(l["text"].strip() for l in captions_layers)


# --------------------------------------------------------------------------- #
# Overlay sur un projet designe (autopilote) : le design est conserve, les
# sous-titres se calent sur la chronologie absolue de la voix.
# --------------------------------------------------------------------------- #

def _two_scene_project() -> dict:
    project = schema.new_project("quote_cinematic")
    project["content"]["scenes"] = [
        schema.scene("s1", "Un", 2.0, [schema.text_layer("title", "Titre un")]),
        schema.scene("s2", "Deux", 2.0, [schema.text_layer("title", "Titre deux")]),
    ]
    return project


def _caption_layers(project: dict, scene_id: str) -> list[dict]:
    scene = next(s for s in project["content"]["scenes"] if s["id"] == scene_id)
    return [l for l in scene["layers"] if l["role"] == "caption"]


def test_overlay_places_cue_in_the_right_scene_with_local_timing():
    project = _two_scene_project()  # s1 [0,60), s2 [60,120) a 30 fps
    cues = [{"start": 2.5, "end": 3.5, "text": "bonjour le monde"}]  # frames [75,105]
    out = captions.overlay_captions(project, cues, fps=30)
    assert _caption_layers(out, "s1") == [], "le cue ne commence qu'en scene 2"
    layer = _caption_layers(out, "s2")[0]
    assert layer["animation"]["start_frames"] == 15  # 75 - 60
    assert layer["animation"]["out_frames"] == 15  # 120 - 105
    assert "bonjour" in layer["text"]
    # le calque de design est conserve
    assert any(l["id"] == "title" for l in out["content"]["scenes"][1]["layers"])


def test_overlay_splits_a_cue_spanning_two_scenes():
    project = _two_scene_project()
    cues = [{"start": 1.5, "end": 2.5, "text": "a cheval"}]  # frames [45,75]
    out = captions.overlay_captions(project, cues, fps=30)
    assert len(_caption_layers(out, "s1")) == 1
    assert len(_caption_layers(out, "s2")) == 1
    assert _caption_layers(out, "s1")[0]["animation"]["start_frames"] == 45
    assert _caption_layers(out, "s2")[0]["animation"]["start_frames"] == 0


def test_overlay_preserves_timeline_and_passes_validation():
    project = _two_scene_project()
    cues = [{"start": 0.2, "end": 1.0, "text": "un deux"},
            {"start": 2.2, "end": 3.8, "text": "trois quatre cinq"}]
    out = captions.overlay_captions(project, cues, fps=30)
    errors, _ = validation.validate_project_v2(out)
    assert errors == []
    before = resolve.resolve(project)["resolved"]["total_frames"]
    after = resolve.resolve(out)["resolved"]["total_frames"]
    assert before == after, "l'overlay n'allonge pas la video"


def test_overlay_is_idempotent_and_does_not_mutate_source():
    project = _two_scene_project()
    snapshot = schema.clone(project)
    cues = [{"start": 0.5, "end": 3.5, "text": "un deux trois quatre"}]
    once = captions.overlay_captions(project, cues, fps=30)
    twice = captions.overlay_captions(once, cues, fps=30)
    assert project == snapshot, "le projet source n'est pas mute"
    for scene_id in ("s1", "s2"):
        assert len(_caption_layers(once, scene_id)) == len(_caption_layers(twice, scene_id))


def test_overlay_empty_cues_returns_unchanged_clone():
    project = _two_scene_project()
    out = captions.overlay_captions(project, [], fps=30)
    assert out == project
    assert out is not project


# --------------------------------------------------------------------------- #
# Rythme cale sur la voix (G2) : la duree totale des scenes suit la narration,
# le rythme relatif est preserve, chaque duree reste dans les bornes du schema.
# --------------------------------------------------------------------------- #

def test_pace_to_voice_matches_total_and_preserves_ratio():
    project = _two_scene_project()  # 2 s + 2 s = 4 s
    snapshot = schema.clone(project)
    out = captions.pace_to_voice(project, 8.0, fps=30)
    assert schema.total_duration(out) == pytest.approx(8.0, abs=0.01)
    durations = [sc["duration"] for sc in out["content"]["scenes"]]
    assert durations[0] == pytest.approx(durations[1])  # rythme relatif preserve
    assert any(l["id"] == "title" for l in out["content"]["scenes"][0]["layers"])
    assert project == snapshot, "le projet source n'est pas mute"


def test_pace_to_voice_clamps_to_schema_bounds():
    project = _two_scene_project()
    low = captions.pace_to_voice(project, 0.2, fps=30)  # 0.1 s/scene -> borne min
    for scene in low["content"]["scenes"]:
        assert scene["duration"] >= schema.SCENE_DURATION_MIN
    high = captions.pace_to_voice(project, 1000.0, fps=30)  # 500 s/scene -> borne max
    for scene in high["content"]["scenes"]:
        assert scene["duration"] <= schema.SCENE_DURATION_MAX
    assert validation.validate_project_v2(low)[0] == []
    assert validation.validate_project_v2(high)[0] == []


def test_pace_to_voice_no_voice_returns_unchanged_clone():
    project = _two_scene_project()
    for seconds in (0.0, -1.0):
        out = captions.pace_to_voice(project, seconds, fps=30)
        assert out == project
        assert out is not project


def test_pace_to_voice_includes_hidden_scenes():
    project = _two_scene_project()
    project["content"]["scenes"][1]["hidden"] = True
    out = captions.pace_to_voice(project, 8.0, fps=30)
    # La scene cachee compte dans la timeline : les deux sont remises a l'echelle.
    assert schema.total_duration(out) == pytest.approx(8.0, abs=0.01)
    assert out["content"]["scenes"][1]["hidden"] is True


def test_pace_to_voice_empty_scenes_returns_clone():
    project = schema.new_project("quote_cinematic")
    project["content"]["scenes"] = []
    out = captions.pace_to_voice(project, 5.0, fps=30)
    assert out == project


def test_pace_to_voice_rescales_layer_windows_to_stay_valid():
    project = schema.new_project("quote_cinematic")
    layer = schema.text_layer("title", "Titre", start_frames=48, in_frames=24)
    project["content"]["scenes"] = [schema.scene("s1", "Un", 6.0, [layer])]
    out = captions.pace_to_voice(project, 2.0, fps=30)  # 6 s -> 2 s, facteur 1/3
    scene = out["content"]["scenes"][0]
    new_frames = int(round(scene["duration"] * 30))
    anim = scene["layers"][0]["animation"]
    assert anim["start_frames"] < new_frames, "le calque ne deborde plus de la scene"
    assert anim["start_frames"] == pytest.approx(16, abs=1)  # 48 * 1/3
    assert validation.validate_project_v2(out)[0] == []