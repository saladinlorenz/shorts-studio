"""Alignement de sous-titres sur la voix off, sans dependance externe.

Le moteur TTS produit un WAV PCM mono (voir ``tts.py``). Ce module lit ce WAV
avec la seule bibliotheque standard (``wave`` + ``array``), en extrait une
enveloppe d'energie, puis repartit les mots connus du texte sur la timeline
audio : les mots longs occupent plus de temps, les silences ne comptent pas.
C'est un alignement force « leger » (pas d'ASR) : le texte est deja connu, on ne
cherche que le quand.

Les cues produites ont le format attendu par ``moment_project.caption_timeline``
(``start`` / ``end`` en secondes, ``text``), donc les sous-titres cinetiques
carrelent la voix a la frame pres, en apercu comme a l'export.

Deterministe : aucune horloge, aucun alea. Deux lectures du meme WAV donnent les
memes bornes.
"""
from __future__ import annotations

import array
import bisect
import math
import sys
import wave
from pathlib import Path

# Fenetre d'analyse (ms) : assez fine pour suivre les mots, assez large pour
# lisser le bruit. 30 ms ~ une syllabe.
DEFAULT_WINDOW_MS = 30
# Seuil de parole relatif au crete de l'enveloppe : en dessous, c'est du silence.
DEFAULT_THRESHOLD_RATIO = 0.12
# Regroupement des mots en lignes de sous-titre lisibles.
DEFAULT_MAX_WORDS = 6
DEFAULT_MAX_CHARS = 42
# Silence entre deux mots qui justifie une nouvelle ligne de sous-titre.
DEFAULT_PAUSE_SECONDS = 0.30


class CaptionError(RuntimeError):
    """WAV illisible ou format non supporte : raison humaine, jamais un stacktrace."""


def _read_mono(path: str | Path) -> tuple[list[float], int]:
    """Lit un WAV PCM et le rend en mono normalise (-1..1) + cadence reelle.

    Supporte 8/16/32 bits, mono ou stereo (moyenne des canaux). Le WAV est
    little-endian : on corrige si la machine ne l'est pas.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())
    except (wave.Error, OSError, EOFError) as exc:
        raise CaptionError(f"WAV illisible ({path}) : {exc}") from exc

    if width == 2:
        data = array.array("h", raw)
        scale = 32768.0
    elif width == 4:
        data = array.array("i", raw)
        scale = 2147483648.0
    elif width == 1:
        data = array.array("B", raw)
        scale = 128.0
    else:
        raise CaptionError(f"Format WAV non supporte : echantillon {width * 8} bits.")
    if sys.byteorder != "little":
        data.byteswap()

    if width == 1:
        values = [(s - 128) / scale for s in data]
    else:
        values = [s / scale for s in data]
    if channels > 1:
        values = [
            sum(values[i : i + channels]) / channels
            for i in range(0, len(values) - channels + 1, channels)
        ]
    return values, rate


def _envelope(samples: list[float], rate: int, window_ms: int) -> tuple[list[float], float]:
    """RMS par fenetre glissante : l'energie de parole au fil du temps."""
    window = max(1, int(rate * window_ms / 1000))
    win_seconds = window / rate if rate else 0.0
    env: list[float] = []
    for start in range(0, len(samples), window):
        chunk = samples[start : start + window]
        if not chunk:
            break
        env.append(math.sqrt(sum(x * x for x in chunk) / len(chunk)))
    return env, win_seconds


def _uniform(words: list[str], start: float, end: float) -> list[dict]:
    """Repli sans energie : repartition proportionnelle a la longueur des mots."""
    weights = [len(w) + 1 for w in words]
    total = sum(weights) or 1
    span = max(0.0, end - start)
    out: list[dict] = []
    cursor = start
    acc = 0
    for index, word in enumerate(words):
        acc += weights[index]
        nxt = start + (acc / total) * span if index < len(words) - 1 else end
        out.append({"word": word, "start": round(cursor, 3), "end": round(nxt, 3)})
        cursor = nxt
    return out


def _speech_segments(env: list[float], win_seconds: float, threshold: float,
                     duration: float) -> list[list[float]]:
    """Plages de parole continues : ``[debut_s, fin_s, energie]``.

    Les micro-coupures (moins de deux fenetres) sont fusionnees : une hesitation
    ne doit pas fragmenter un mot. Le silence entre deux plages reste un vrai
    vide, c'est lui que le regroupement en lignes de sous-titre detecte.
    """
    segments: list[list[float]] = []
    start = None
    energy = 0.0
    for index, value in enumerate(env):
        if value >= threshold:
            if start is None:
                start = index
            energy += value
        elif start is not None:
            segments.append([start * win_seconds, min(duration, index * win_seconds), energy])
            start = None
            energy = 0.0
    if start is not None:
        segments.append([start * win_seconds, min(duration, len(env) * win_seconds), energy])

    merged: list[list[float]] = []
    for segment in segments:
        if merged and segment[0] - merged[-1][1] < 2 * win_seconds:
            merged[-1][1] = segment[1]
            merged[-1][2] += segment[2]
        else:
            merged.append(segment)
    return merged


def align_words(path: str | Path, text: str, *, window_ms: int = DEFAULT_WINDOW_MS,
                threshold_ratio: float = DEFAULT_THRESHOLD_RATIO) -> list[dict]:
    """Aligne chaque mot du texte sur le WAV : ``[{word, start, end}]`` en secondes.

    L'enveloppe d'energie decoupe la parole en plages continues ; chaque plage
    recoit des mots proportionnellement a son energie, et les mots y sont repartis
    selon leur longueur. Un mot ne chevauche jamais un silence : les vides entre
    plages sont les pauses reellement mesurees, que ``caption_cues`` utilise pour
    passer a la ligne. Audio muet ou texte vide : repli propre, jamais d'erreur.
    """
    words = (text or "").split()
    if not words:
        return []
    samples, rate = _read_mono(path)
    duration = len(samples) / rate if rate else 0.0
    if not samples or duration <= 0:
        return _uniform(words, 0.0, 0.0)

    env, win_seconds = _envelope(samples, rate, window_ms)
    peak = max(env) if env else 0.0
    if peak <= 0 or win_seconds <= 0:
        return _uniform(words, 0.0, duration)

    segments = _speech_segments(env, win_seconds, peak * threshold_ratio, duration)
    if not segments:
        return _uniform(words, 0.0, duration)
    total_energy = sum(segment[2] for segment in segments)
    if total_energy <= 0:
        return _uniform(words, segments[0][0], segments[-1][1])

    weights = [len(w) + 1 for w in words]
    weight_total = sum(weights)
    # Part cumulative d'energie a la fin de chaque plage : sert de carte temps.
    cumulative_energy: list[float] = []
    acc_energy = 0.0
    for segment in segments:
        acc_energy += segment[2]
        cumulative_energy.append(acc_energy / total_energy)

    # Chaque mot va a la plage qui contient le centre de sa part de longueur :
    # repartition proportionnelle a l'energie, robuste aux micro-ecarts.
    allocation: list[list[tuple[str, int]]] = [[] for _ in segments]
    acc_weight = 0
    for word, weight in zip(words, weights):
        center = (acc_weight + weight / 2) / weight_total
        acc_weight += weight
        index = min(bisect.bisect_left(cumulative_energy, center), len(segments) - 1)
        allocation[index].append((word, weight))

    out: list[dict] = []
    for (seg_start, seg_end, _energy), items in zip(segments, allocation):
        if not items:
            continue
        seg_weight = sum(weight for _word, weight in items)
        span = max(0.0, seg_end - seg_start)
        cursor = seg_start
        acc = 0
        for index, (word, weight) in enumerate(items):
            acc += weight
            nxt = seg_start + (acc / seg_weight) * span if index < len(items) - 1 else seg_end
            out.append({"word": word, "start": round(cursor, 3), "end": round(nxt, 3)})
            cursor = nxt
    return out


def caption_cues(path: str | Path, text: str, *, fps: int = 30,
                 max_words: int = DEFAULT_MAX_WORDS, max_chars: int = DEFAULT_MAX_CHARS,
                 pause_seconds: float = DEFAULT_PAUSE_SECONDS,
                 window_ms: int = DEFAULT_WINDOW_MS,
                 threshold_ratio: float = DEFAULT_THRESHOLD_RATIO) -> list[dict]:
    """Mots alignes -> cues de sous-titres lisibles (``start``/``end``/``text``).

    Une ligne casse sur un silence franc, ou quand elle depasse le nombre de mots
    ou de caracteres confortable. Le format est celui de ``caption_timeline``.
    """
    aligned = align_words(path, text, window_ms=window_ms, threshold_ratio=threshold_ratio)
    if not aligned:
        return []
    cues: list[dict] = []
    current: list[dict] = []

    def flush() -> None:
        if current:
            cues.append({
                "start": current[0]["start"],
                "end": current[-1]["end"],
                "text": " ".join(item["word"] for item in current),
            })

    for item in aligned:
        if current:
            gap = item["start"] - current[-1]["end"]
            chars = sum(len(x["word"]) + 1 for x in current) + len(item["word"])
            if len(current) >= max_words or chars > max_chars or gap >= pause_seconds:
                flush()
                current = []
        current.append(item)
    flush()
    return cues


def caption_scenes(path: str | Path, text: str, fps: int, *, background_media: str = "",
                   max_words: int = DEFAULT_MAX_WORDS, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[list[dict], int]:
    """WAV + texte -> scenes de sous-titres cinetiques, pretes pour le projet v2.

    Reutilise ``moment_project.caption_timeline`` / ``scenes_from_specs`` : une
    scene par ligne, le calque porte le fondu de sortie egal au silence mesure.
    Retourne ``(scenes, total_frames)``.
    """
    from . import moment_project

    cues = caption_cues(path, text, fps=fps, max_words=max_words, max_chars=max_chars)
    specs, total = moment_project.caption_timeline(cues, fps)
    scenes = moment_project.scenes_from_specs(specs, fps, background_media=background_media)
    return scenes, total


def overlay_captions(project: dict, cues: list[dict], *, fps: int | None = None,
                     min_overlap_frames: int = 3) -> dict:
    """Pose des sous-titres synchronises sur les scenes existantes, sans toucher au design.

    Chaque cue (``start``/``end`` en secondes, ``text``) devient un calque
    ``role=caption`` dans la ou les scenes qu'il chevauche : la fenetre locale du
    calque est calee sur les bornes du cue (entree au debut du cue, fondu de sortie
    egal au silence mesure jusqu'au cue suivant ou a la fin de la scene). Titres,
    B-roll et effets sont conserves ; les anciens calques ``caption`` sont remplaces.
    Renvoie une copie : le projet d'origine n'est pas mute.
    """
    from . import moment_project, moments, schema

    out = schema.clone(project)
    if not cues:
        return out
    rate = int(fps if fps is not None else (out.get("export") or {}).get("fps", 30) or 30)
    windows: list[tuple[int, int, str]] = []
    for cue in cues:
        text = moments.wrap_caption(str(cue.get("text") or "").strip())
        if not text:
            continue
        start = max(0, int(round(float(cue.get("start") or 0.0) * rate)))
        end = max(start + 1, int(round(float(cue.get("end") or 0.0) * rate)))
        windows.append((start, end, text))
    if not windows:
        return out

    cursor = 0
    for scene in out.get("content", {}).get("scenes", []):
        scene_frames = max(1, int(round(float(scene.get("duration", 0.0)) * rate)))
        scene_start, scene_end = cursor, cursor + scene_frames
        cursor = scene_end
        if scene.get("hidden"):
            continue
        layers = [layer for layer in scene.get("layers", []) if layer.get("role") != "caption"]
        for index, (cue_start, cue_end, text) in enumerate(windows, start=1):
            overlap_start = max(cue_start, scene_start)
            overlap_end = min(cue_end, scene_end)
            if overlap_end - overlap_start < min_overlap_frames:
                continue
            start_frames = overlap_start - scene_start
            out_frames = scene_end - overlap_end
            animation = moment_project._caption_animation(
                scene_frames - start_frames, out_frames, len(text.split())
            )
            layers.append(schema.text_layer(
                f"caption-{index}", text, role="caption", start_frames=start_frames,
                position={"x": 0.5, "y": moment_project.CAPTION_Y,
                          "width": moment_project.CAPTION_WIDTH, "align": "center"},
                style={"font_size": moment_project.CAPTION_FONT_SIZE,
                       "line_height": moment_project.CAPTION_LINE_HEIGHT,
                       "letter_spacing": 0.005},
                animation=animation,
            ))
        scene["layers"] = layers
    return out


def _rescale_scene_timing(scene: dict, local: float, new_frames: int) -> None:
    """Remet a l'echelle les fenetres d'animation et la transition d'une scene.

    Quand la duree d'une scene change, les calques doivent suivre : un
    ``start_frames`` pense pour 6 s deborderait d'une scene ramenee a 1 s.
    Chaque fenetre est multipliee par le facteur local puis bornee a la
    nouvelle duree, pour que le design reste valide et proportionnel.
    """
    from . import schema

    transition = scene.get("transition")
    if isinstance(transition, dict) and transition.get("frames"):
        scaled = int(round(int(transition["frames"]) * local))
        transition["frames"] = max(0, min(new_frames, schema.TRANSITION_FRAMES_MAX, scaled))
    for layer in scene.get("layers", []):
        anim = layer.get("animation")
        if not isinstance(anim, dict):
            continue
        start = int(anim.get("start_frames", 0) or 0)
        anim["start_frames"] = max(0, min(new_frames - 1, int(round(start * local))))
        for key in ("in_frames", "out_frames"):
            if key in anim:
                anim[key] = max(0, int(round(int(anim[key] or 0) * local)))


def pace_to_voice(project: dict, voice_seconds: float, *, fps: int | None = None) -> dict:
    """Cale la duree totale des scenes sur la narration, sans toucher au design.

    Chaque scene est remise a l'echelle proportionnellement : le rythme relatif
    choisi par le realisateur est preserve, mais la video dure exactement le
    temps de la voix off — ni blanc en fin, ni narration coupee. Chaque duree
    est bornee aux limites du schema, et les fenetres d'animation + transitions
    suivent la nouvelle duree (le design reste valide). Les scenes cachees
    comptent dans la timeline (resolve les accumule toutes), elles sont donc
    remises a l'echelle aussi. Sans voix (<=0) ou sans scene, le projet est rendu
    tel quel (copie). Renvoie une copie : le projet d'origine n'est pas mute.
    """
    from . import schema

    out = schema.clone(project)
    scenes = out.get("content", {}).get("scenes", [])
    if voice_seconds <= 0 or not scenes:
        return out
    rate = int(fps if fps is not None else (out.get("export") or {}).get("fps", 30) or 30)
    durations = [max(0.0, float(sc.get("duration", 0.0))) for sc in scenes]
    total = sum(durations)
    if total <= 0:
        return out
    scale = voice_seconds / total
    for scene, old_duration in zip(scenes, durations):
        new_duration = min(schema.SCENE_DURATION_MAX, max(schema.SCENE_DURATION_MIN, old_duration * scale))
        new_duration = round(new_duration, 3)
        scene["duration"] = new_duration
        if old_duration <= 0:
            continue
        new_frames = max(1, int(round(new_duration * rate)))
        _rescale_scene_timing(scene, new_duration / old_duration, new_frames)
    return out