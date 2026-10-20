"""Core logic: Whisper JSON -> subtitle cues -> SRT/VTT text.

All times are integer milliseconds internally. No printing, no sys.exit.
"""

from __future__ import annotations

import json
import math
import os
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from jv_common import UserError

SENTENCE_END = (".", "?", "!", "…")
CLAUSE_END = (",", ";", ":", "–", "—")
# Words a break may come before (a soft clause boundary in Norwegian).
CONJUNCTIONS = frozenset(
    "og men så eller fordi at som der når hvis mens før etter da selv om enn".split()
)
# Largest delay (ms) a cue may cause for the next one when it is stretched to
# the minimum display time. Fixed, so delay can never build up along a chain.
MAX_PUSH_MS = 150
_CLOSING = "\"'»”)]"


@dataclass(frozen=True)
class Rules:
    max_chars: int = 42
    max_lines: int = 2
    min_ms: int = 1000
    max_ms: int = 7000
    gap_ms: int = 80

    def check(self) -> None:
        if self.max_chars < 10:
            raise UserError("--max-chars må være minst 10.")
        if self.max_lines < 1:
            raise UserError("--max-lines må være minst 1.")
        if self.min_ms <= 0 or self.max_ms <= 0:
            raise UserError("Varighetene må være større enn null.")
        if self.min_ms > self.max_ms:
            raise UserError("--min-duration kan ikke være større enn --max-duration.")
        if self.gap_ms < 0:
            raise UserError("--gap kan ikke være negativ.")


@dataclass
class Word:
    text: str
    start: int
    end: int


@dataclass
class Cue:
    start: int
    end: int
    words: list[Word]
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Transcript:
    segments: list[list[Word]]
    segments_with_words: int
    segments_total: int


# ------------------------------------------------------------------ input


def _ms(value: object, what: str, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UserError(f"{where}: «{what}» mangler eller er ikke et tall.")
    if not math.isfinite(value) or value < 0:
        raise UserError(f"{where}: «{what}» har en ugyldig verdi ({value}).")
    return int(round(value * 1000))


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _is_punct_only(token: str) -> bool:
    return bool(token) and all(unicodedata.category(c).startswith("P") for c in token)


def _words_from_whisper(raw: list, seg_start: int, seg_end: int, where: str) -> list[Word]:
    words: list[Word] = []
    last = seg_start
    for item in raw:
        if not isinstance(item, dict):
            raise UserError(f"{where}: ordlisten har et ugyldig element.")
        token = _norm(str(item.get("word", ""))).strip()
        if not token:
            continue
        start = _ms(item.get("start"), "start", where + " (ord)")
        end = _ms(item.get("end"), "end", where + " (ord)")
        start = min(max(start, last, seg_start), seg_end)
        end = min(max(end, start), seg_end)
        last = end
        for piece in token.split():
            if words and _is_punct_only(piece):
                words[-1].text += piece
                words[-1].end = max(words[-1].end, end)
            else:
                words.append(Word(piece, start, end))
    return words


def _words_by_chars(text: str, seg_start: int, seg_end: int) -> list[Word]:
    tokens = _norm(text).split()
    merged: list[str] = []
    for tok in tokens:
        if merged and _is_punct_only(tok):
            merged[-1] += tok
        else:
            merged.append(tok)
    if not merged:
        return []
    weights = [len(t) + 1 for t in merged]
    total = sum(weights)
    span = seg_end - seg_start
    words: list[Word] = []
    acc = 0
    for tok, w in zip(merged, weights):
        start = seg_start + round(span * acc / total)
        acc += w
        end = seg_start + round(span * acc / total)
        words.append(Word(tok, start, end))
    return words


def load_transcript(path: str | os.PathLike[str]) -> Transcript:
    """Read Whisper JSON (a dict with "segments", or a bare list of segments)."""
    p = Path(path)
    if not p.exists():
        raise UserError(f"Filen «{p}» finnes ikke.")
    if not p.is_file():
        raise UserError(f"«{p}» er ikke en fil.")
    data = p.read_bytes()
    if not data.strip():
        raise UserError(f"Filen «{p.name}» er tom.")
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise UserError(f"«{p.name}» er ikke UTF-8-tekst. Forventet Whisper-JSON.") from None
    except json.JSONDecodeError as exc:
        raise UserError(
            f"«{p.name}» er ikke gyldig JSON (linje {exc.lineno}). Forventet Whisper-JSON."
        ) from None

    segs = doc.get("segments") if isinstance(doc, dict) else doc
    if not isinstance(segs, list):
        raise UserError(
            f"«{p.name}» ser ikke ut som Whisper-JSON: fant ingen liste «segments»."
        )
    segments: list[list[Word]] = []
    with_words = 0
    for n, seg in enumerate(segs):
        where = f"«{p.name}», segment {n}"
        if not isinstance(seg, dict):
            raise UserError(f"{where} er ikke et objekt med start, end og text.")
        text = seg.get("text")
        if not isinstance(text, str):
            raise UserError(f"{where}: «text» mangler eller er ikke tekst.")
        start = _ms(seg.get("start"), "start", where)
        end = _ms(seg.get("end"), "end", where)
        if end < start:
            raise UserError(f"{where}: «end» er før «start».")
        raw_words = seg.get("words")
        words: list[Word] = []
        if isinstance(raw_words, list) and raw_words:
            words = _words_from_whisper(raw_words, start, end, where)
            if words:
                with_words += 1
        if not words:
            words = _words_by_chars(text, start, end)
        if words:
            segments.append(words)
    if not segments:
        raise UserError(f"«{p.name}» inneholder ingen tekst å lage undertekster av.")
    return Transcript(segments, with_words, len(segments))


# ------------------------------------------------------------- line wrap


def _break_cost(left: str, right: str) -> float:
    """Cost of breaking between two words (lower is better)."""
    tail = left.rstrip(_CLOSING)
    if tail.endswith(SENTENCE_END):
        return 0.0
    if tail.endswith(CLAUSE_END):
        return 0.3
    if right.lower() in CONJUNCTIONS:
        return 0.8
    return 1.5


def wrap(words: tuple[str, ...], max_chars: int, max_lines: int) -> list[str] | None:
    """Split words into at most max_lines lines of at most max_chars characters,
    breaking only between words. Returns None if impossible."""
    result = _wrap(words, max_chars, max_lines)
    return None if result is None else list(result[1])


@lru_cache(maxsize=4096)
def _wrap(words: tuple[str, ...], max_chars: int, max_lines: int):
    text = " ".join(words)
    if len(text) <= max_chars:
        return (0.0, (text,))
    if max_lines <= 1 or len(words) < 2:
        return None
    best = None
    total = len(text)
    for k in range(1, len(words)):
        first = " ".join(words[:k])
        if len(first) > max_chars:
            break
        rest = _wrap(words[k:], max_chars, max_lines - 1)
        if rest is None:
            continue
        # prefer clause breaks and balanced lines
        balance = abs(len(first) - (total - len(first) - 1) / (max_lines - 1)) / max_chars
        cost = _break_cost(words[k - 1], words[k]) + balance + rest[0]
        if best is None or cost < best[0]:
            best = (cost, (first, *rest[1]))
    return best


# --------------------------------------------------------------- cueing


def _split_segment(words: list[Word], rules: Rules) -> list[list[Word]]:
    """Partition one segment into cues with dynamic programming.

    Each cue must fit (wrap succeeds, duration <= max). A single word is
    always allowed as a last resort. Cost: 1 per cue, plus break cost,
    plus a penalty for cues shorter than the minimum display time.
    """
    n = len(words)
    texts = tuple(w.text for w in words)
    inf = float("inf")
    best = [inf] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for i in range(1, n + 1):
        for j in range(i - 1, -1, -1):
            if best[j] == inf:
                continue
            span = words[i - 1].end - words[j].start
            chars = len(" ".join(texts[j:i]))
            if chars > rules.max_chars * rules.max_lines + rules.max_lines and i - j > 1:
                break
            fits = span <= rules.max_ms and wrap(texts[j:i], rules.max_chars, rules.max_lines) is not None
            if not fits and i - j > 1:
                continue
            cost = 1.0
            if not fits:
                cost += 100.0
            if span < rules.min_ms:
                cost += 1.0
            if j > 0:
                cost += _break_cost(texts[j - 1], texts[j])
            total = best[j] + cost
            if total < best[i]:
                best[i] = total
                back[i] = j
    parts: list[list[Word]] = []
    i = n
    while i > 0:
        j = back[i]
        parts.append(words[j:i])
        i = j
    parts.reverse()
    return parts


def _try_merge(cue: Cue, nxt: Cue, rules: Rules) -> Cue | None:
    """Merge two neighbouring cues if the result still follows the rules."""
    if nxt.end - cue.start > rules.max_ms:
        return None
    words = cue.words + nxt.words
    lines = wrap(tuple(w.text for w in words), rules.max_chars, rules.max_lines)
    if lines is None:
        return None
    return Cue(cue.start, max(cue.end, nxt.end), words, lines)


def _fix_timing(cues: list[Cue], rules: Rules, notes: dict[str, int] | None = None) -> None:
    """Enforce min/max display time and the gap between cues, in order.

    A cue is never extended past the start of the next one, so delay cannot
    build up along a chain of short cues. A too-short cue that cannot be
    extended is merged with the next cue when the result follows the rules,
    otherwise it stays short. Counts go into notes ("merged", "short").
    """
    if notes is None:
        notes = {}
    notes.setdefault("merged", 0)
    notes.setdefault("short", 0)
    gap, lo, hi = rules.gap_ms, rules.min_ms, rules.max_ms
    i = 0
    while i < len(cues):
        cue = cues[i]
        floor = 0 if i == 0 else cues[i - 1].end + gap
        if cue.start < floor:
            cue.start = floor
        if cue.end < cue.start:
            cue.end = cue.start
        nxt = cues[i + 1] if i + 1 < len(cues) else None
        limit = None if nxt is None else nxt.start - gap
        need = lo - (cue.end - cue.start)
        if need > 0 and nxt is not None:
            room = max(0, limit - cue.end) + max(0, cue.start - floor)
            if room < need:
                merged = _try_merge(cue, nxt, rules)
                if merged is not None:
                    cues[i : i + 2] = [merged]
                    notes["merged"] += 1
                    continue
        # Too short: extend the end up to the next cue, then pull the start
        # earlier. Anything still missing is left short (never pushes the next cue).
        if need > 0:
            room = need if limit is None else max(0, min(need, limit - cue.end))
            cue.end += room
            need -= room
        if need > 0:
            back = min(need, cue.start - floor)
            cue.start -= back
            need -= back
        if need > 0 and limit is not None:
            # Last resort: push the next cue later, but only a small fixed amount.
            push = min(need, MAX_PUSH_MS)
            cue.end += push
            need -= push
        elif need > 0:
            cue.end += need
            need = 0
        if need > 0:
            notes["short"] += 1
        if cue.end - cue.start > hi:
            cue.end = cue.start + hi
        if limit is not None and cue.end > limit + MAX_PUSH_MS:
            cue.end = max(limit + MAX_PUSH_MS, cue.start)
        i += 1


def make_cues(
    transcript: Transcript, rules: Rules, notes: dict[str, int] | None = None
) -> list[Cue]:
    cues: list[Cue] = []
    for seg in transcript.segments:
        for part in _split_segment(seg, rules):
            cue = Cue(part[0].start, part[-1].end, part)
            texts = tuple(w.text for w in part)
            cue.lines = wrap(texts, rules.max_chars, rules.max_lines) or [" ".join(texts)]
            cues.append(cue)
    _fix_timing(cues, rules, notes)
    return cues


def check_cues(cues: list[Cue], rules: Rules) -> list[str]:
    """Return Norwegian descriptions of every rule violation (empty if none)."""
    problems: list[str] = []
    for n, cue in enumerate(cues, start=1):
        dur = cue.end - cue.start
        if not cue.lines or not any(line.strip() for line in cue.lines):
            problems.append(f"Tekst {n} er tom.")
        if len(cue.lines) > rules.max_lines:
            problems.append(f"Tekst {n} har {len(cue.lines)} linjer (maks {rules.max_lines}).")
        for line in cue.lines:
            if len(line) > rules.max_chars:
                problems.append(
                    f"Tekst {n} har en linje på {len(line)} tegn (maks {rules.max_chars}): «{line}»."
                )
        if dur < rules.min_ms:
            problems.append(f"Tekst {n} vises i {dur / 1000:.3f} s (minst {rules.min_ms / 1000:g} s).")
        if dur > rules.max_ms:
            problems.append(f"Tekst {n} vises i {dur / 1000:.3f} s (høyst {rules.max_ms / 1000:g} s).")
        if n < len(cues):
            gap = cues[n].start - cue.end
            if gap < rules.gap_ms:
                problems.append(
                    f"Bare {gap} ms mellom tekst {n} og {n + 1} (minst {rules.gap_ms} ms)."
                )
    return problems


# ---------------------------------------------------------------- output


def _ts(ms: int, sep: str) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, msec = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{msec:03d}"


def to_srt(cues: list[Cue]) -> str:
    """SRT with CRLF line endings."""
    blocks = []
    for n, cue in enumerate(cues, start=1):
        lines = [str(n), f"{_ts(cue.start, ',')} --> {_ts(cue.end, ',')}", *cue.lines]
        blocks.append("\r\n".join(lines) + "\r\n")
    return "\r\n".join(blocks)


def _vtt_escape(line: str) -> str:
    return line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_vtt(cues: list[Cue]) -> str:
    """WebVTT with LF line endings."""
    out = ["WEBVTT", ""]
    for cue in cues:
        out.append(f"{_ts(cue.start, '.')} --> {_ts(cue.end, '.')}")
        out.extend(_vtt_escape(line) for line in cue.lines)
        out.append("")
    return "\n".join(out)


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 without BOM, keeping line endings exactly as given."""
    with open(path, "xb") as handle:
        handle.write(text.encode("utf-8"))


def convert(
    path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    rules: Rules,
) -> dict:
    """Convert one transcript. Returns outputs, warnings and stats."""
    from jv_common import safe_output_path

    transcript = load_transcript(path)
    notes: dict[str, int] = {}
    cues = make_cues(transcript, rules, notes)
    problems = check_cues(cues, rules)

    srt_path = safe_output_path(path, out_dir, ".srt")
    write_text(srt_path, to_srt(cues))
    vtt_path = safe_output_path(path, out_dir, ".vtt")
    write_text(vtt_path, to_vtt(cues))

    name = Path(path).name
    warnings = [f"{name}: {p}" for p in problems]
    if notes.get("merged"):
        warnings.append(
            f"{name}: {notes['merged']} tette korte tekster er slått sammen med neste "
            "tekst, så ingen tekst kommer senere enn tidskoden."
        )
    if notes.get("short"):
        warnings.append(
            f"{name}: {notes['short']} tekster er kortere enn minste visningstid, fordi de "
            "ligger tett inntil neste tekst. De er avkortet i stedet for å forsinke resten."
        )
    if transcript.segments_with_words == 0:
        warnings.append(
            f"{name}: ingen ordtidskoder – tiden i lange segmenter er fordelt etter antall tegn."
        )
    elif transcript.segments_with_words < transcript.segments_total:
        missing = transcript.segments_total - transcript.segments_with_words
        warnings.append(
            f"{name}: {missing} segmenter manglet ordtidskoder – der er tiden fordelt etter antall tegn."
        )
    return {
        "outputs": [
            {"path": str(srt_path), "format": "srt", "cues": len(cues), "source": str(path)},
            {"path": str(vtt_path), "format": "vtt", "cues": len(cues), "source": str(path)},
        ],
        "warnings": warnings,
        "cues": len(cues),
        "segments": transcript.segments_total,
        "word_timestamps": transcript.segments_with_words > 0,
        "violations": len(problems),
    }
