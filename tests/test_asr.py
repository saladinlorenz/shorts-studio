"""Real ASR checks: decoding and splitting run on a WAV made here, the network is faked.

Nothing is installed by these tests: local_backend() only reports what the machine
already has.
"""
from __future__ import annotations

import array
import math
import wave

import pytest

from shortvideos import asr

RATE = 16_000


def _tone(seconds, amplitude=12000, frequency=220.0):
    count = int(seconds * RATE)
    return [int(amplitude * math.sin(2 * math.pi * frequency * i / RATE)) for i in range(count)]


def _silence(seconds):
    return [0] * int(seconds * RATE)


@pytest.fixture()
def wav_with_gaps(tmp_path):
    path = tmp_path / "episode.wav"
    samples = []
    for index in range(8):
        samples += _tone(4.0, amplitude=9000 + index * 400, frequency=180.0 + index * 30)
        samples += _silence(1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(array.array("h", samples).tobytes())
    return path


def test_extract_audio_from_real_wav(wav_with_gaps, tmp_path):
    out = tmp_path / "extrait.wav"
    info = asr.extract_audio(wav_with_gaps, out)
    assert out.is_file()
    assert info["sample_rate"] == asr.SAMPLE_RATE
    assert info["channels"] == 1
    assert info["duration"] == pytest.approx(40.0, abs=0.2)


def test_extract_audio_missing_source_is_a_clear_error(tmp_path):
    with pytest.raises(asr.AsrError) as excinfo:
        asr.extract_audio(tmp_path / "absent.wav", tmp_path / "out.wav")
    assert "introuvable" in str(excinfo.value)


def test_energy_curve_follows_the_signal(wav_with_gaps):
    curve = asr.energy_curve(wav_with_gaps)
    assert curve["window_s"] == pytest.approx(asr.ENERGY_WINDOW_S)
    assert curve["duration"] == pytest.approx(40.0, abs=0.2)
    assert all(0.0 <= value <= 1.0 for value in curve["rms"])
    window = curve["window_s"]
    silent = curve["rms"][int(4.5 / window)]
    speech = curve["rms"][int(1.0 / window)]
    assert silent < speech / 4, (silent, speech)


def test_energy_curve_on_silence(tmp_path):
    path = tmp_path / "muet.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(array.array("h", _silence(1.0)).tobytes())
    curve = asr.energy_curve(path)
    assert curve["rms"] and max(curve["rms"]) == pytest.approx(0.0)


def test_split_points_cut_inside_silence_and_cover_everything(wav_with_gaps):
    ranges = asr.split_points(wav_with_gaps, max_seconds=10.0)
    assert ranges
    assert ranges[0][0] == 0.0
    for (_start_a, end_a), (start_b, _end_b) in zip(ranges, ranges[1:]):
        assert end_a == pytest.approx(start_b, abs=0.01)
    for start, end in ranges[:-1]:
        assert end - start <= 10.0 + 0.4
    curve = asr.energy_curve(wav_with_gaps)
    for _start, end in ranges[:-1]:
        index = int(end / curve["window_s"])
        assert curve["rms"][index] < 0.3, "coupe en pleine energie a " + str(end)


def test_split_points_keeps_a_short_audio_whole(wav_with_gaps):
    ranges = asr.split_points(wav_with_gaps, max_seconds=60.0)
    assert len(ranges) == 1
    assert ranges[0][0] == 0.0
    assert ranges[0][1] == pytest.approx(40.0, abs=0.2)


def test_cut_wav_is_real(wav_with_gaps, tmp_path):
    out = tmp_path / "morceau.wav"
    asr.cut_wav(wav_with_gaps, out, 5.0, 9.0)
    assert asr.wav_duration(out) == pytest.approx(4.0, abs=0.1)


def test_normalize_segments_drops_nonsense():
    raw = [
        {"start": 3.0, "end": 1.0, "text": "a l envers"},
        {"start": float("nan"), "end": 4.0, "text": "nan"},
        {"start": 2.0, "end": 3.0, "text": "   "},
        "pas un dictionnaire",
        {"start": 5.0, "end": 6.5, "text": "  deux   espaces  "},
        {"start": 0.5, "end": 1.2, "text": "premier"},
    ]
    assert asr.normalize_segments(raw) == [
        {"start": 0.5, "end": 1.2, "text": "premier"},
        {"start": 5.0, "end": 6.5, "text": "deux espaces"},
    ]


def test_parse_srt_recovers_times():
    text = (
        "1\n00:00:01,500 --> 00:00:03,250\nBonjour tout\nle monde\n\n"
        "2\n00:00:04,000 --> 00:00:05,000\nSecond cue\n"
    )
    assert asr.parse_srt(text) == [
        {"start": 1.5, "end": 3.25, "text": "Bonjour tout le monde"},
        {"start": 4.0, "end": 5.0, "text": "Second cue"},
    ]


def _real_wav(tmp_path, name):
    """Un WAV minuscule mais reel : _groq_chunk ouvre le fichier avant d'appeler le client."""
    path = tmp_path / name
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(array.array("h", _silence(0.2)).tobytes())
    return str(path)


class _FakeResult:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class _FakeTranscriptions:
    def __init__(self, pieces):
        self.pieces = pieces
        self.calls = []

    def create(self, file=None, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.pieces) - 1)
        return _FakeResult(self.pieces[index])


class _FakeClient:
    def __init__(self, pieces):
        self.audio = type("Audio", (), {"transcriptions": _FakeTranscriptions(pieces)})()


def test_groq_offsets_are_turned_into_absolute_times(tmp_path):
    pieces = [
        {"language": "fr", "segments": [{"start": 0.2, "end": 1.8, "text": " premier "},
                                         {"start": 2.0, "end": 3.0, "text": "deuxieme"}]},
        {"language": "fr", "segments": [{"start": 0.5, "end": 2.0, "text": "suite"}]},
    ]
    chunks = [
        {"path": _real_wav(tmp_path, "a.wav"), "start": 0.0, "end": 7.0},
        {"path": _real_wav(tmp_path, "b.wav"), "start": 7.0, "end": 14.0},
    ]
    result = asr.transcribe_groq(chunks, api_key="k", client_factory=lambda key: _FakeClient(pieces))
    assert result["provider"] == "groq"
    assert [s["start"] for s in result["segments"]] == [0.2, 2.0, 7.5]
    assert [s["end"] for s in result["segments"]] == [1.8, 3.0, 9.0]
    assert result["language"] == "fr"
    assert result["warnings"] == []


def test_groq_reports_a_chunk_it_heard_nothing(tmp_path):
    pieces = [{"language": "fr", "segments": []}]
    result = asr.transcribe_groq([{"path": _real_wav(tmp_path, "a.wav"), "start": 0.0, "end": 7.0}],
                                api_key="k", client_factory=lambda key: _FakeClient(pieces))
    assert result["segments"] == []
    assert len(result["warnings"]) == 1


def test_groq_refuses_without_a_key(tmp_path):
    with pytest.raises(asr.AsrError) as excinfo:
        asr.transcribe_groq([{"path": _real_wav(tmp_path, "a.wav"), "start": 0.0, "end": 1.0}], api_key="")
    assert "Cle Groq absente" in str(excinfo.value)


def test_groq_refuses_an_unknown_model(tmp_path):
    with pytest.raises(asr.AsrError) as excinfo:
        asr.transcribe_groq([{"path": _real_wav(tmp_path, "a.wav"), "start": 0.0, "end": 1.0}],
                            api_key="k", model="gpt")
    assert "whisper-large-v3-turbo" in str(excinfo.value)


def test_groq_network_refusal_becomes_a_readable_error(tmp_path):
    client = _FakeClient([{"segments": [{"start": 0, "end": 1, "text": "x"}]}])

    def explode(**kwargs):
        raise RuntimeError("429 rate limit")

    client.audio.transcriptions.create = explode
    with pytest.raises(asr.AsrError) as excinfo:
        asr.transcribe_groq([{"path": _real_wav(tmp_path, "a.wav"), "start": 0.0, "end": 1.0}],
                            api_key="k", client_factory=lambda key: client)
    assert "429" in str(excinfo.value)


def test_providers_report_what_this_machine_can_do():
    listing = asr.providers(groq_key_present=False)
    groq = next(p for p in listing if p["id"] == "groq")
    local = next(p for p in listing if p["id"] == "local")
    assert groq["available"] is False and groq["cloud"] is True and groq["reason"]
    assert local["cloud"] is False
    assert local["available"] is asr.local_backend()["available"]
    assert next(p for p in asr.providers(groq_key_present=True) if p["id"] == "groq")["available"] is True


def test_local_backend_installs_nothing():
    state = asr.local_backend()
    assert set(state) == {"kind", "available", "cli", "model", "reason"}
    if not state["available"]:
        assert state["reason"], "une voie fermee doit dire pourquoi"


def test_full_transcribe_entry_point_on_a_real_file(wav_with_gaps, tmp_path):
    pieces = [{"language": "fr", "segments": [
        {"start": 0.1, "end": 3.9, "text": "Premiere phrase."},
        {"start": 5.0, "end": 8.0, "text": "Seconde phrase."},
    ]}]
    seen = []

    def factory(key):
        seen.append(key)
        return _FakeClient(pieces)

    result = asr.transcribe(
        wav_with_gaps, provider="groq", api_key="cle-test", work_dir=tmp_path,
        client_factory=factory, max_chunk_seconds=10.0, audio_out=tmp_path / "garde.wav",
    )
    assert seen == ["cle-test"]
    assert result["provider"] == "groq"
    assert result["duration"] == pytest.approx(40.0, abs=0.3)
    assert result["audio_path"] == str(tmp_path / "garde.wav")
    assert (tmp_path / "garde.wav").is_file(), "audio_out doit garder la piste pour l'energie"
    assert max(s["start"] for s in result["segments"]) >= 10.0, "les morceaux suivants sont decales"
    assert not list(tmp_path.glob("*chunk*.wav")), "les morceaux de travail sont nettoyes"
