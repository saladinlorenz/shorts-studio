"""Detection des moments forts : transcription + audio + duree, rien d'invente.

Un moment est une fenetre de la video source qui tient debout toute seule. Le module
ne devine aucun contenu : il ne travaille que sur des segments horodates produits par
``shortvideos.asr`` (ou un ``.srt`` existant) et, si on lui fournit l'enveloppe
d'energie reellement mesuree, sur le signal audio lui-meme.

Chaque critere est ajoute aux ``reasons`` du moment avec sa valeur : la page Moments
affiche **pourquoi** ce passage est propose, jamais une note sortie de nulle part.
Le score est une somme normalisee de ces criteres — reproductible, donc testable.
"""
from __future__ import annotations

import math
import re
import unicodedata


MIN_SECONDS = 10.0
MAX_SECONDS = 45.0
TOP_DEFAULT = 6
OVERLAP_TOLERANCE = 0.3      # fraction de chevauchement toleree entre deux moments
GAP_EDGE_S = 0.30            # silence attendu avant/apres une pensee complete
GAP_REPORT_MAX = 2.0         # au dela, le chiffre affiche ne veut plus rien dire
DENSITY_IDEAL = (2.0, 3.6)   # mots par seconde : en dessous c'est creux, au-dessus ca bavarde
CAPTION_MAX_CHARS = 46
CAPTION_MAX_LINES = 2

# Marqueurs de « ca vaut un clip » : amorce, question, chiffre, inversion, chute.
# Liste volontairement courte et assumee : ce qui n'y est pas ne penalise pas, ca ne
# remonte pas le score.
MARKERS = {
    "amorce": (
        "ce que personne", "la verite", "on ne te dit pas", "personne ne t'explique",
        "le secret", "erreur", "piege", "voila pourquoi", "la raison", "un jour",
        "j'ai compris", "le probleme", "ce qui compte",
    ),
    "question": ("pourquoi", "comment", "qu'est-ce qui", "et si", "tu savais", "saviez-vous"),
    "chiffre": ("%", "pourcent", "fois", "secondes", "minutes", "ans", "euros", "dollars", "01", "100"),
    "bascule": ("mais", "or ", "alors que", "en realite", "en fait", "pourtant", "sauf que",
                "au debut", "au bout de"),
    "chute": ("c'est ca", "voila", "retiens", "donc", "la lecon", "et voila", "exactement"),
    "english": ("nobody", "the truth", "here's why", "what if", "instead", "actually",
                "the real", "stop", "remember"),
}

STOPWORDS = frozenset(
    """le la les un une des du de d' au aux et ou mais donc or ni car que qui quoi dont
    ce cet cette ces mon ton son notre votre leur je tu il elle on nous vous ils elles
    me te se lui y en dont a à dans sur pour par avec sans sous tres trop plus moins
    est sont etait etaient etre ete avoir eu fais faire fait peut peuvent vont va
    the a an and or but so if of to in on for with that this it is was were be been
    have has had you your we they them his her its our not do does did so as at by
    """.split()
)


def _is_finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _clean_segments(transcript: dict) -> list[dict]:
    """Segments exploitables : bornes numeriques finies, tries par temps croissants."""
    return sorted(
        (s for s in (transcript.get("segments") or [])
         if isinstance(s, dict) and _is_finite(s.get("start")) and _is_finite(s.get("end"))),
        key=lambda s: (float(s["start"]), float(s["end"])),
    )


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^\w'’]+", str(text or "").lower()) if w]


def keywords(text: str, *, limit: int = 8) -> list[str]:
    """Mots les plus frequents du texte, hors vidanges : jamais un mot invente.

    L'elision francaise est eclatee (« d'agitation » donne « agitation ») : un hashtag
    « #dagitation » n'est searche par personne, et « c'est » ne porte aucun sens.
    """
    counts: dict[str, int] = {}
    for raw in re.split(r"[^\w]+", str(text or "").lower()):
        word = raw.strip("'’")
        if len(word) < 4 or word in STOPWORDS or word.isdigit():
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:limit]]


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


_FORM_IS_WORD = re.compile(r"[a-z]+")


def marker_hits(text: str) -> dict[str, list[str]]:
    """Categories de marqueurs presentes, avec les formes trouvees.

    Un marqueur d'un seul mot se matching en mot entier : « trans » contient « ans »
    et n'a rien d'un chiffre. Les expressions et les symboles restent en sous-chaine.
    """
    haystack = _strip_accents(str(text or "").lower())
    words = set(_words(haystack))
    hits: dict[str, list[str]] = {}
    for kind, forms in MARKERS.items():
        found = []
        for form in forms:
            needle = _strip_accents(str(form).lower())
            matched = needle in words if _FORM_IS_WORD.fullmatch(needle) else needle in haystack
            if matched:
                found.append(needle)
        if found:
            hits[kind] = found
    return hits


def segments_in(transcript: dict, start: float, end: float) -> list[dict]:
    """Segments dont le centre tombe dans la fenetre — le texte reel du moment."""
    out = []
    for seg in _clean_segments(transcript):
        middle = (float(seg["start"]) + float(seg["end"])) / 2.0
        if start - 0.001 <= middle <= end + 0.001:
            out.append(seg)
    return out


def speech_density(segments, start: float, end: float) -> float:
    window = max(0.001, end - start)
    return round(sum(len(_words(s.get("text"))) for s in segments) / window, 3)


def edge_gaps(transcript: dict, start: float, end: float) -> tuple[float, float]:
    """Silence reellement present avant ``start`` et apres ``end`` (en secondes)."""
    before = start
    after = max(0.0, float(transcript.get("duration") or end) - end)
    for seg in _clean_segments(transcript):
        if float(seg["end"]) <= start:
            before = min(before, start - float(seg["end"]))
        if float(seg["start"]) >= end:
            after = min(after, float(seg["start"]) - end)
    return round(before, 3), round(after, 3)


def energy_stats(energy: dict | None, start: float, end: float) -> dict:
    """Moyenne et crete de l'enveloppe d'energie sur la fenetre, en valeur absolue."""
    if not energy or not energy.get("rms"):
        return {"mean": None, "peak": None, "global_mean": None}
    window = float(energy.get("window_s") or 0.05) or 0.05
    rms = energy["rms"]
    lo, hi = max(0, int(start / window)), min(len(rms), int(end / window))
    inside = rms[lo:hi] or [0.0]
    return {"mean": round(sum(inside) / len(inside), 4),
            "peak": round(max(inside), 4),
            "global_mean": round(sum(rms) / len(rms), 4)}


def _anchor_indices(segments: list[dict]) -> tuple[list[int], list[int]]:
    """Indices qui ouvrent une pensee (silence avant) et qui la ferment (silence apres).

    Un segment isol au milieu d'un flux n'est pas une frontiere exploitable : couper
    la ou le locuteur ne s'est jamais arrête hache les phrases.
    """
    starts: list[int] = []
    ends: list[int] = []
    for index, seg in enumerate(segments):
        if index == 0 or float(seg["start"]) - float(segments[index - 1]["end"]) >= GAP_EDGE_S:
            starts.append(index)
        if index == len(segments) - 1 or float(segments[index + 1]["start"]) - float(seg["end"]) >= GAP_EDGE_S:
            ends.append(index)
    return starts, ends


def _candidate_windows(transcript: dict, *, min_seconds: float, max_seconds: float,
                       anchored: bool = True) -> list[tuple[float, float]]:
    """Fenetres ouvertes sur un debut de pensee et fermees sur une fin de pensee.

    Ancrer sur les frontieres reelles de l'ASR garantit deux choses : le moment
    commence sur un mot et il finit sur un mot. Aucune coupe arbitraire en secondes
    rondes, donc aucune phrase hachee.
    """
    segments = _clean_segments(transcript)
    start_indices, end_indices = _anchor_indices(segments)
    allowed_ends = set(end_indices) if anchored else set(range(len(segments)))
    windows: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for i in (start_indices if anchored else range(len(segments))):
        start = float(segments[i]["start"])
        for j in range(i, len(segments)):
            end = float(segments[j]["end"])
            duration = end - start
            if duration > max_seconds:
                # les segments sont tries : la premiere fenetre trop longue fermee
                # l'ancre, les suivantes le seront encore.
                break
            if duration >= min_seconds and j in allowed_ends and (start, end) not in seen:
                seen.add((start, end))
                windows.append((round(start, 3), round(end, 3)))
    return windows


def score_window(transcript: dict, start: float, end: float, *, energy: dict | None = None) -> tuple[int, list[str]]:
    """Score 0–100 d'une fenetre, et la liste des criteres qui y contribuent."""
    reasons: list[str] = []
    segments = segments_in(transcript, start, end)
    if not segments:
        return 0, []
    score = 0

    density = speech_density(segments, start, end)
    if DENSITY_IDEAL[0] <= density <= DENSITY_IDEAL[1]:
        score += 22
        reasons.append(f"densite de parole {density} mots/s (bande {DENSITY_IDEAL[0]}–{DENSITY_IDEAL[1]})")
    elif density > 0:
        score += 8
        reasons.append(f"{density} mots/s, hors bande {DENSITY_IDEAL[0]}–{DENSITY_IDEAL[1]}")

    before, after = edge_gaps(transcript, start, end)
    # Le silence est une condition, pas un concours : au dela de GAP_REPORT_MAX le
    # chiffre affiche ne veut plus rien dire (fin de transcription, blanc publicitaire).
    if after >= GAP_EDGE_S:
        score += 20
        reasons.append(f"pensee fermee : {min(after, GAP_REPORT_MAX)} s de silence apres")
    if before >= GAP_EDGE_S:
        score += 12
        reasons.append(f"demarre sur un silence ({min(before, GAP_REPORT_MAX)} s avant)")

    text = " ".join(s.get("text", "") for s in segments)
    tail = text.rstrip()[-1:]
    if tail in {".", "!", "?", "”", '"'}:
        score += 10
        reasons.append(f"fin sur une ponctuation forte ({tail})")

    hits = marker_hits(text)
    if hits:
        bonus = min(30, 6 * sum(len(v) for v in hits.values()))
        score += bonus
        labels = ", ".join(f"{kind} ({', '.join(v[:2])})" for kind, v in sorted(hits.items()))
        reasons.append(f"marqueurs : {labels}")

    stats = energy_stats(energy, start, end)
    if stats["mean"] is not None and stats["global_mean"]:
        ratio = round(stats["mean"] / stats["global_mean"], 2)
        if ratio >= 1.08:
            score += 14
            reasons.append(f"energie {ratio}× la moyenne du fichier")
        elif ratio >= 0.92:
            score += 5
            reasons.append(f"energie dans la moyenne ({ratio}×)")

    duration = end - start
    if 12.0 <= duration <= 30.0:
        score += 12
        reasons.append(f"{round(duration, 1)} s : format court tenu")
    elif duration <= max(MAX_SECONDS, 40.0):
        score += 6
        reasons.append(f"{round(duration, 1)} s")

    return min(100, score), reasons


def detect(transcript: dict, *, energy: dict | None = None, min_seconds: float = MIN_SECONDS,
           max_seconds: float = MAX_SECONDS, top: int = TOP_DEFAULT,
           max_candidates: int = 4000) -> list[dict]:
    """Les ``top`` meilleurs moments, non chevauchants, tries par position dans la video.

    La selection est gloutonne sur le score : un moment n'est garde que s'il ne
    recouvre pas deja retenu de plus de ``OVERLAP_TOLERANCE``. Deterministe : meme
    transcript, meme energie, meme resultat.
    """
    if not isinstance(transcript, dict) or not (transcript.get("segments") or []):
        return []
    windows = _candidate_windows(transcript, min_seconds=min_seconds, max_seconds=max_seconds)
    if not windows:
        # Flux continu sans vraie pause de 0,3 s : les frontieres strictes n'existent
        # pas. On retombe sur les frontieres ASR seules plutot que de ne rien proposer.
        windows = _candidate_windows(transcript, min_seconds=min_seconds,
                                     max_seconds=max_seconds, anchored=False)
    if len(windows) > max_candidates:
        # sur une longue interview, on echantillonne les ancres plute que d'exploser :
        # la difference de score entre deux fenetres voisines est minuscule.
        step = max(1, len(windows) // max_candidates)
        windows = windows[::step]
    scored = []
    for start, end in windows:
        score, reasons = score_window(transcript, start, end, energy=energy)
        if reasons:
            scored.append({"start": start, "end": end, "score": score, "reasons": reasons})
    # a score egal, la fenetre la plus courte gagne : une pensee serree vaut mieux
    # qu'un bloc de 45 s qui avale trois pensees pour cumuler les marqueurs.
    scored.sort(key=lambda w: (-w["score"], round(w["end"] - w["start"], 3), w["start"]))

    chosen: list[dict] = []
    for window in scored:
        if len(chosen) >= max(1, int(top)):
            break
        if _overlaps_chosen(window, chosen) > OVERLAP_TOLERANCE:
            continue
        chosen.append(window)

    moments: list[dict] = []
    for index, window in enumerate(sorted(chosen, key=lambda w: w["start"]), start=1):
        segments = segments_in(transcript, window["start"], window["end"])
        text = " ".join(s.get("text", "") for s in segments).strip()
        moments.append({
            "id": f"m{index}",
            "position": index,
            "start": window["start"],
            "end": window["end"],
            "duration": round(window["end"] - window["start"], 3),
            "score": window["score"],
            "reasons": window["reasons"],
            "text": re.sub(r"\s+", " ", text),
            "cues": captions(segments, window["start"]),
            "keywords": keywords(text),
        })
    return moments


def _overlaps_chosen(window: dict, chosen: list[dict]) -> float:
    """Chevauchement rapporte a la plus petite des deux fenetres.

    Rapportee a la fenetre entrante, une pensee de 12 s avalee par un bloc de 45 s ne
    « chevaucherait » jamais assez pour etre refusee : deux clips quasi identiques
    seraient livres. La plus petite mesure est celle qui compte.
    """
    worst = 0.0
    for other in chosen:
        overlap = min(window["end"], other["end"]) - max(window["start"], other["start"])
        if overlap > 0:
            smaller = min(window["end"] - window["start"], other["end"] - other["start"])
            worst = max(worst, overlap / max(0.001, smaller))
    return round(worst, 3)


def captions(segments, window_start: float) -> list[dict]:
    """Les sous-titres du moment, en temps relatifs a la fenetre.

    Une seule source de verite : les frontieres de l'ASR. Un segment long reste
    **un seul** cue — le couper en deux inventerait des temps intermediaires. On
    replie seulement le texte en lignes, ce qui ne change aucun horodatage.
    """
    cues: list[dict] = []
    for seg in segments:
        text = re.sub(r"\s+", " ", str(seg.get("text") or "")).strip()
        if not text:
            continue
        start = max(0.0, round(float(seg["start"]) - window_start, 3))
        end = max(start + 0.2, round(float(seg["end"]) - window_start, 3))
        cues.append({"start": start, "end": end, "text": wrap_caption(text),
                     "words": len(_words(text)),
                     "raw_start": round(float(seg["start"]), 3),
                     "raw_end": round(float(seg["end"]), 3)})
    return cues


def wrap_caption(text: str, *, max_chars: int = CAPTION_MAX_CHARS,
                 max_lines: int = CAPTION_MAX_LINES) -> str:
    """Replie le texte en ``max_lines`` lignes au plus, sans jamais couper un mot.

    Ce qui deborde est signale par « … » sur la derniere ligne : l'horodatage du cue
    reste celui du segment ASR, seul le texte visible est replie.
    """
    words = str(text or "").split()
    lines: list[str] = []
    index = 0
    while index < len(words) and len(lines) < max_lines:
        line = words[index]
        index += 1
        while index < len(words) and len(line) + 1 + len(words[index]) <= max_chars:
            line = f"{line} {words[index]}"
            index += 1
        lines.append(line)
    if index < len(words) and lines:
        last = lines[-1]
        while " " in last and len(last) + 2 > max_chars:
            last = last.rsplit(" ", 1)[0]
        lines[-1] = f"{last} …"
    return "\n".join(lines)


def _cut_words(text: str, limit: int) -> str:
    """Coupe au dernier mot entier avant ``limit`` caracteres, avec point de suspension."""
    if len(text) <= limit:
        return text
    head = text[: max(1, limit - 1)]
    if " " not in head:
        return head.rstrip()
    return head[: head.rfind(" ")].rstrip() + "…"


def title_from(moment: dict, *, brand_label: str = "", max_chars: int = 80) -> str:
    """Titre : la premiere phrase forte du moment, raccourcie sur un mot entier.

    Aucun mot exterieur a la transcription n'apparait : le titre est une citation
    du moment, pas une reformulation. La marque n'est ajoutee que si l'utilisateur
    l'a fournie ; quand elle ne laisse plus assez de place a la citation, elle saute
    et le titre tient dans ``max_chars``.
    """
    text = re.sub(r"\s+", " ", str(moment.get("text") or "")).strip()
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    pick = sentences[0] if sentences else text
    pick = pick.rstrip(".!?,;:")
    suffix = f" · {brand_label}" if brand_label else ""
    if max_chars - len(suffix) < 12:
        suffix = ""
    return _cut_words(pick, max_chars - len(suffix)) + suffix


def hashtags_from(moment: dict, *, handle: str = "", limit: int = 8) -> list[str]:
    """Hashtags construits uniquement sur les mots presents dans le moment."""
    tags: list[str] = []
    if handle:
        slug = ascii_slug(str(handle).lstrip("@"))
        if slug:
            tags.append(f"#{slug}")
    words = list(moment.get("keywords") or []) or keywords(moment.get("text", ""))
    for word in words:
        slug = ascii_slug(word)
        if slug and f"#{slug}" not in tags:
            tags.append(f"#{slug}")
        if len(tags) >= limit:
            break
    return tags[:limit]


def ascii_slug(word: str) -> str:
    clean = _strip_accents(str(word or "").lower())
    return re.sub(r"[^a-z0-9]+", "", clean)[:24]


def description_from(moment: dict, *, source_title: str = "", handle: str = "",
                     brand_label: str = "", max_chars: int = 320) -> str:
    """Description : l'extrait reel du moment, puis credit, identite et hashtags.

    Le corps est coupe sur un mot entier pour laisser la ligne de hashtags intacte :
    un hashtag tronque ne marche plus sur aucune plateforme.
    """
    text = re.sub(r"\s+", " ", str(moment.get("text") or "")).strip()
    if not text:
        return ""
    lines: list[str] = []
    credit = " · ".join(p for p in (brand_label, source_title) if p)
    if credit:
        lines.append(f"Extrait de {credit} ({moment.get('duration', 0)} s)")
    if handle:
        lines.append(str(handle) if str(handle).startswith("@") else f"@{handle}")
    tags = hashtags_from(moment, handle="")
    if tags:
        lines.append(" ".join(tags[:5]))
    suffix = "\n" + "\n".join(lines) if lines else ""
    budget = max_chars - len(suffix)
    if budget < 1:
        # les hashtags passent avant la citation : c'est elle qui se sacrifie.
        return suffix.lstrip("\n")[:max_chars]
    return _cut_words(text, budget) + suffix


def metadata_from(moment: dict, *, source_title: str = "", handle: str = "",
                  brand_label: str = "") -> dict:
    """Les trois champs de publies d'un moment, tous derives de sa transcription."""
    return {
        "title": title_from(moment, brand_label=brand_label),
        "description": description_from(moment, source_title=source_title,
                                        handle=handle, brand_label=brand_label),
        "hashtags": hashtags_from(moment, handle=handle),
        "moment_id": moment.get("id", ""),
        "start": moment.get("start", 0.0),
        "end": moment.get("end", 0.0),
        "duration": moment.get("duration", 0.0),
        "score": moment.get("score", 0),
        "reasons": list(moment.get("reasons") or []),
        "keywords": list(moment.get("keywords") or []),
    }
