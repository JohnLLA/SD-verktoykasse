"""Detection of personal data in the text layer of a PDF.

Text is read character by character (rawdict) so every hit gets exact
rectangles. All lines of a page are joined with "\n", which lets a number
that wraps over a line break (e.g. "010190" / "12480") still be found.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

import pymupdf

# Extraction flags: expand ligatures, keep whitespace, no images, no clipping
# to the mediabox. On its own the flag is not enough in PyMuPDF 1.28, so text
# is also read with clip=INFINITE_RECT, and the page boxes are widened first
# (see prepare.py), so text outside the visible page is found too.
TEXT_FLAGS = (
    pymupdf.TEXTFLAGS_RAWDICT
    & ~pymupdf.TEXT_PRESERVE_LIGATURES
    & ~pymupdf.TEXT_PRESERVE_IMAGES
    & ~pymupdf.TEXT_MEDIABOX_CLIP
)

# Horizontal spaces that may appear inside numbers and names.
_HSPACE_CH = "\t\u0020\u00a0\u2009\u202f"
_HSPACE = f"[{_HSPACE_CH}]"
# One separator inside a phone number or name: 1-6 spaces or tabs (maybe with
# a line break) or a bare line break. Whether a wide gap really joins two
# groups is decided from the positions on the page (see gap_checker).
_WS = rf"(?:{_HSPACE}{{1,6}}\n?{_HSPACE}{{0,3}}|\n{_HSPACE}{{0,3}})"
_SEP = _WS

_NOT_DIGIT_AFTER = r"(?!\d)(?![.,]\d)"

# Digit groups and what lies between them.
#
# A "binding" separator joins two digit groups into one number token:
# punctuation directly between digits ("150685-27101", "29.02.92",
# "1,5") or a dash with spaces around it ("150685 - 27101").
# A "loose" separator is whitespace (optionally after . , ; :), as between
# words: "Rad 1 15068527101", "290292 418 03", "fnr 010190\n12480".
# A fødselsnummer is any sequence of whole tokens with exactly 11 digits and
# valid mod 11, so a single digit in front or behind never hides it, while a
# number that is part of a longer token ("1-15068527101") is not a hit.
_DASHES = "\\-\u2010\u2011\u2012\u2013\u2014\u2212"
_BIND = rf"(?:[{_DASHES}./\u00b7,]|{_HSPACE}{{1,2}}[{_DASHES}]{_HSPACE}{{1,2}})"
_LOOSE = rf"(?:[.,;:]?{_WS})"
_BIND_RE = re.compile(rf"{_BIND}\Z")
DIGIT_RUN_RE = re.compile(rf"(?<!\d)\d+(?:(?:{_BIND}|{_LOOSE})\d+)*")
_GROUP_RE = re.compile(r"\d+")


GapCheck = Callable[[int, int], bool] | None


def number_tokens(text: str, gap_ok: GapCheck = None) -> list[list[tuple[int, int, str, tuple[int, ...]]]]:
    """Per digit run: its tokens as (start, end, digits, group lengths).

    gap_ok(a, b) is asked about every loose separator text[a:b]; when it
    says no (digits far apart on the page), the run is split there.
    """
    runs = []
    for run in DIGIT_RUN_RE.finditer(text):
        tokens: list[tuple[int, int, str, tuple[int, ...]]] = []
        prev_end = None
        for g in _GROUP_RE.finditer(text, run.start(), run.end()):
            glen = len(g.group(0))
            if prev_end is not None and _BIND_RE.match(text, prev_end, g.start()):
                s0, _e0, d0, gl = tokens[-1]
                tokens[-1] = (s0, g.end(), d0 + g.group(0), gl + (glen,))
            else:
                if prev_end is not None and gap_ok is not None and not gap_ok(prev_end, g.start()):
                    runs.append(tokens)
                    tokens = []
                tokens.append((g.start(), g.end(), g.group(0), (glen,)))
            prev_end = g.end()
        runs.append(tokens)
    return runs


# 8 digits in the usual Norwegian groupings, optional +47 / 0047 in front.
# 2-2-2-2 and 3-2-3 may also use hyphen or full stop ("58-01-23-45"); 4-4 only
# spaces, so case numbers like "2026-1234" are not phone numbers.
_PSEP = rf"(?:[.\-\u2010\u2011\u2013]|{_WS})"
_PHONE_CORE = (
    r"\d{8}"
    rf"|\d{{2}}{_PSEP}\d{{2}}{_PSEP}\d{{2}}{_PSEP}\d{{2}}"
    rf"|\d{{3}}{_PSEP}\d{{2}}{_PSEP}\d{{3}}"
    rf"|\d{{4}}{_SEP}\d{{4}}"
)
PHONE_RE = re.compile(
    rf"(?<![\d+])(?<!\d[.,\-/])(?:(?:\+|00)47{_SEP}?)?(?:{_PHONE_CORE})"
    rf"{_NOT_DIGIT_AFTER}(?![\-/]\d)"
)

# Invisible characters that must not hide a number: format characters
# (category Cf: zero width space/joiners, word joiner, BOM, ...) and soft hyphen.
def _is_invisible(c: str) -> bool:
    return c == "­" or unicodedata.category(c) == "Cf"


def normalize_with_map(chars: Sequence[str]) -> list[tuple[str, list[int]]]:
    """Normalise a character sequence as a whole and keep track of where
    every output character came from.

    Invisible characters are dropped, then every base character together
    with the combining marks that follow it ("A" + U+030A) is normalised
    with NFC and NFKC as one cluster ("Å"). Returns (character, source
    indices) for each output character.
    """
    visible = [(i, c) for i, c in enumerate(chars) if c and not all(_is_invisible(x) for x in c)]
    clusters: list[tuple[str, list[int]]] = []
    for i, c in visible:
        c = "".join(x for x in c if not _is_invisible(x))
        if clusters and all(unicodedata.combining(x) for x in c):
            text, idx = clusters[-1]
            clusters[-1] = (text + c, idx + [i])
        else:
            clusters.append((c, [i]))
    out: list[tuple[str, list[int]]] = []
    for text, idx in clusters:
        norm = unicodedata.normalize("NFKC", unicodedata.normalize("NFC", text))
        for x in norm:
            if not _is_invisible(x):
                out.append((x, idx))
    return out


def normalize_chars(c: str) -> str:
    """NFKC of a single character, invisible characters removed."""
    return "".join(x for x, _ in normalize_with_map(list(c)))


def normalize_text(text: str) -> str:
    """NFC + NFKC of the whole string, invisible characters removed."""
    return "".join(x for x, _ in normalize_with_map(list(text)))


EMAIL_RE = re.compile(
    r"(?<![\w.%+-])[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}(?![\w-])"
)

_K1_WEIGHTS = (3, 7, 6, 1, 8, 9, 4, 5, 2)
_K2_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

TYPE_LABELS = {
    "fodselsnummer": "fødselsnummer",
    "d_nummer": "D-nummer",
    "telefon": "telefonnummer",
    "epost": "e-postadresse",
    "term": "term",
}


def _control_digit(digits: Sequence[int], weights: Sequence[int]) -> int | None:
    rest = sum(d * w for d, w in zip(digits, weights)) % 11
    k = 11 - rest
    if k == 11:
        return 0
    if k == 10:
        return None
    return k


def valid_fnr(number: str) -> bool:
    """True if both mod 11 control digits of an 11-digit number are valid.

    The date is not checked (so D-, H- and synthetic numbers are caught),
    except that day 00 or month 00 is never a real number (all zeros would
    otherwise pass mod 11).
    """
    if len(number) != 11 or not number.isdigit():
        return False
    if number[0:2] == "00" or number[2:4] == "00":
        return False
    digits = [int(c) for c in number]
    k1 = _control_digit(digits[:9], _K1_WEIGHTS)
    if k1 is None or k1 != digits[9]:
        return False
    k2 = _control_digit(digits[:10], _K2_WEIGHTS)
    return k2 is not None and k2 == digits[10]


def fnr_type(number: str) -> str:
    """D-nummer has 40 added to the day, so the first digit is 4-7."""
    return "d_nummer" if number[0] in "4567" else "fodselsnummer"


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Hit:
    type: str
    text: str  # as in the PDF, whitespace collapsed to single spaces
    normalized: str
    page: int | None  # 1-based; None for hits that belong to no page
    excerpt: str
    rects: list[list[float]] = field(default_factory=list)
    placement: str = "side"
    # top-left of the original visible page in working-copy coordinates;
    # the plan shows rectangles relative to it (normal page coordinates)
    offset: tuple[float, float] = (0.0, 0.0)
    # a number candidate whose digit groups are far apart on the page
    # (likely table cells): listed in the plan with "sladd": false
    rejected: bool = False
    reason: str = ""
    # a rejected candidate that does not look like a number split over cells
    # (table columns): kept out of the plan, but still known to the post-check
    quiet: bool = False

    def plan_rects(self) -> list[list[float]]:
        dx, dy = self.offset
        return [
            [round(r[0] - dx, 2), round(r[1] - dy, 2), round(r[2] - dx, 2), round(r[3] - dy, 2)]
            for r in self.rects
        ]

    def key_rects(self) -> list[tuple[float, ...]]:
        return [tuple(r) for r in self.rects]


@dataclass
class PageText:
    """The characters of one page as a string, plus a bbox per character
    (None for the synthetic line breaks)."""

    text: str
    boxes: list[tuple[float, float, float, float] | None]
    line_of: list[int]
    block_of_line: dict[int, int] = field(default_factory=dict)


def page_text(page: pymupdf.Page) -> PageText:
    raw_chars: list[str] = []
    raw_boxes: list[tuple[float, float, float, float] | None] = []
    raw_lines: list[int] = []
    raw = page.get_text("rawdict", flags=TEXT_FLAGS, clip=pymupdf.INFINITE_RECT())
    line_no = 0
    block_of_line: dict[int, int] = {}
    for block_no, block in enumerate(raw.get("blocks", [])):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            block_of_line[line_no] = block_no
            if raw_chars:
                raw_chars.append("\n")
                raw_boxes.append(None)
                raw_lines.append(-1)
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    raw_chars.append(ch.get("c", ""))
                    raw_boxes.append(tuple(ch["bbox"]))
                    raw_lines.append(line_no)
            line_no += 1
    # Normalise the page text as a whole (NFC/NFKC, no invisible characters);
    # every output character gets the union box of its source characters.
    chars: list[str] = []
    boxes: list[tuple[float, float, float, float] | None] = []
    line_of: list[int] = []
    for c, idx in normalize_with_map(raw_chars):
        src = [raw_boxes[i] for i in idx if raw_boxes[i] is not None]
        chars.append(c)
        if src:
            boxes.append((min(b[0] for b in src), min(b[1] for b in src),
                          max(b[2] for b in src), max(b[3] for b in src)))
            line_of.append(raw_lines[idx[0]])
        else:
            boxes.append(None)
            line_of.append(-1)
    return PageText("".join(chars), boxes, line_of, block_of_line)


def gap_checker(pt: PageText) -> Callable[[int, int], bool]:
    """Decide from the page geometry whether whitespace text[a:b] between
    two digit groups really joins them.

    Same line: the gap may be at most about 2 normal spaces, or as wide as
    the typed spaces/tabs (with some slack), so "58    01" typed with four
    spaces still joins, while two table columns that only got one
    synthetic space between them do not. A "normal space" is also measured
    from the line itself: in justified text (block alignment) every word gap
    on the line is stretched, and twice the median gap between words with
    letters is allowed.
    Different lines: the first group must end its line, the second must
    start the next line, directly below. Lines MuPDF put in the same block
    join (wrapped text, digits stacked vertically). Lines in separate blocks
    join only when the next line starts at the left edge of the previous one
    and one of them has letters (a wrapped paragraph written line by line),
    not for two number cells of a table.
    """
    text = pt.text

    # "Visual lines": MuPDF splits a line with wide word gaps (justified
    # text) into several lines on the same baseline. Consecutive lines in the
    # same block, on the same baseline and moving right, form one visual line.
    vline: dict[int, int] = {}
    last: tuple[int, float, float, float] | None = None  # (block, y1, x1, height)
    vid = -1
    line_box: dict[int, list[float]] = {}
    for i, ln in enumerate(pt.line_of):
        box = pt.boxes[i]
        if ln < 0 or box is None:
            continue
        if ln not in line_box:
            line_box[ln] = list(box)
        else:
            lb = line_box[ln]
            lb[2] = max(lb[2], box[2])
    for ln in sorted(line_box):
        x0, _y0, x1, y1 = line_box[ln]
        h = line_box[ln][3] - line_box[ln][1]
        block = pt.block_of_line.get(ln)
        if not (last and last[0] == block and abs(last[1] - y1) < 0.3 * max(h, 1.0)
                and x0 >= last[2] - 0.5):
            vid += 1
        vline[ln] = vid
        last = (block, y1, x1, h)

    def vline_of(i: int) -> int:
        return vline.get(pt.line_of[i], -1 - i)

    def line_bounds(i: int) -> tuple[int, int]:
        ln = pt.line_of[i]
        a = i
        while a > 0 and pt.line_of[a - 1] == ln:
            a -= 1
        b = i
        while b + 1 < len(text) and pt.line_of[b + 1] == ln:
            b += 1
        return a, b

    def vline_bounds(i: int) -> tuple[int, int]:
        v = vline_of(i)
        a = i
        while a > 0 and (pt.line_of[a - 1] < 0 or vline_of(a - 1) == v):
            a -= 1
        while pt.line_of[a] < 0:
            a += 1
        b = i
        while b + 1 < len(text) and (pt.line_of[b + 1] < 0 or vline_of(b + 1) == v):
            b += 1
        while pt.line_of[b] < 0:
            b -= 1
        return a, b

    word_gap_cache: dict[int, list[tuple[int, float]]] = {}

    def word_gaps(i: int) -> list[tuple[int, float]]:
        """(position, width) of the gaps between words with letters on the
        line of character i: in justified text these are all stretched
        alike, so they tell what a normal space is on this line."""
        ln = vline_of(i)
        if ln in word_gap_cache:
            return word_gap_cache[ln]
        a0, a1 = vline_bounds(i)
        words: list[tuple[int, int]] = []
        j = a0
        while j <= a1:
            if text[j].isspace() or pt.boxes[j] is None:
                j += 1
                continue
            k = j
            while k + 1 <= a1 and not text[k + 1].isspace() and pt.boxes[k + 1] is not None:
                k += 1
            words.append((j, k))
            j = k + 1
        gaps = []
        for (s1, e1), (s2, e2) in zip(words, words[1:]):
            if any(c.isalpha() for c in text[s1:e1 + 1]) and any(c.isalpha() for c in text[s2:e2 + 1]):
                gaps.append((e1 + 1, pt.boxes[s2][0] - pt.boxes[e1][2]))
        word_gap_cache[ln] = gaps
        return gaps

    def ok(a: int, b: int) -> bool:
        if a < 1 or b >= len(text):
            return True
        pa, pb = pt.boxes[a - 1], pt.boxes[b]
        if pa is None or pb is None:
            return True
        la, lb = pt.line_of[a - 1], pt.line_of[b]
        height = max(pa[3] - pa[1], pb[3] - pb[1], 1.0)
        space = 0.3 * height
        if la == lb or vline_of(a - 1) == vline_of(b):
            sep = text[a:b]
            typed = sep.count(" ") + sep.count("\u00a0") + sep.count("\u2009") * 0.5 + sep.count("\t") * 6
            allowed = max(2.0, typed * 1.6) * space
            # justified text: compare with the other word gaps on the line
            others = sorted(w for pos, w in word_gaps(a - 1) if pos != a)
            if len(others) >= 2:
                median = others[len(others) // 2]
                allowed = max(allowed, 2.0 * median * max(1.0, typed))
            return (pb[0] - pa[2]) <= allowed
        if pb[1] < pa[3] - 0.3 * height:
            return False  # next line is not below
        a0, a1 = line_bounds(a - 1)
        b0, b1 = line_bounds(b)
        if text[a:a1 + 1].strip() or text[b0:b].strip():
            return False  # not at the end / start of the lines
        if pb[1] - pa[3] > height:
            return False  # not the next line
        if pt.block_of_line.get(la) == pt.block_of_line.get(lb):
            return True  # MuPDF grouped the lines: running text or stacked digits
        # separate blocks (e.g. one text object per line): still a wrap if
        # the next line starts at the left edge of the previous one and one
        # of the lines has letters (a paragraph, not two number cells)
        start_a = pt.boxes[a0]
        if start_a is None or pb[0] > start_a[0] + 2 * space:
            return False
        return any(c.isalpha() for c in text[a0:a1 + 1] + text[b0:b1 + 1])

    return ok


def _rects_for_span(pt: PageText, start: int, end: int) -> list[list[float]]:
    """One rectangle per text line covered by text[start:end]."""
    per_line: dict[int, list[float]] = {}
    order: list[int] = []
    for i in range(start, end):
        box = pt.boxes[i]
        if box is None or pt.text[i].isspace():
            continue
        ln = pt.line_of[i]
        if ln not in per_line:
            per_line[ln] = list(box)
            order.append(ln)
        else:
            r = per_line[ln]
            r[0] = min(r[0], box[0])
            r[1] = min(r[1], box[1])
            r[2] = max(r[2], box[2])
            r[3] = max(r[3], box[3])
    return [[round(v, 2) for v in per_line[ln]] for ln in order]


def _excerpt(text: str, start: int, end: int, width: int = 30) -> str:
    a = max(0, start - width)
    b = min(len(text), end + width)
    pre = ("…" if a > 0 else "") + text[a:start]
    post = text[end:b] + ("…" if b < len(text) else "")
    return collapse_ws(pre + "[" + text[start:end] + "]" + post)


def term_pattern(term: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in normalize_text(term).split()]
    body = r"(?:\s+)".join(words)
    # also the genitive ("Fiktivsens", "Fiktivsen's", "Fiktivsen’") and
    # hyphen compounds ("Fiktivsen-saken"): the whole word is redacted
    suffix = r"(?:s|['\u2019\u02bc]s?|-\w+)?"
    return re.compile(rf"(?<!\w){body}{suffix}(?!\w)", re.IGNORECASE)


@dataclass
class Span:
    type: str
    start: int
    end: int
    normalized: str


def _account_shaped(groups: tuple[int, ...]) -> bool:
    """Norwegian account numbers are written 4.2.5 (1425.31.00827); their
    check digit uses the same weights, so they would pass as fnr."""
    return groups == (4, 2, 5)


def scan_text(text: str, terms: Iterable[str], gap_ok: GapCheck = None) -> list[Span]:
    """All detections in a string, as character spans. gap_ok, if given,
    vetoes digit groups that are far apart on the page."""
    spans: list[Span] = []
    fnr_spans: set[tuple[int, int]] = set()

    runs = number_tokens(text, gap_ok)
    starts = {t[0] for run in runs for t in run}
    ends = {t[1] for run in runs for t in run}
    for tokens in runs:
        i = 0
        while i < len(tokens):
            digits = ""
            groups: tuple[int, ...] = ()
            found = None
            for j in range(i, len(tokens)):
                digits += tokens[j][2]
                groups += tokens[j][3]
                if len(digits) >= 11:
                    if len(digits) == 11 and valid_fnr(digits) and not _account_shaped(groups):
                        found = j
                    break
            if found is None:
                i += 1
                continue
            s0, e0 = tokens[i][0], tokens[found][1]
            spans.append(Span(fnr_type(digits), s0, e0, digits))
            fnr_spans.add((s0, e0))
            i = found + 1

    for m in PHONE_RE.finditer(text):
        s, e = m.span()
        if any(s < b and a < e for a, b in fnr_spans):
            continue  # part of a fødselsnummer
        first = next(i for i in range(s, e) if text[i].isdigit())
        if first not in starts or e not in ends:
            continue  # inside a longer number token ("1-58-01-23-45")
        if gap_ok is not None and any(
            not gap_ok(s + w.start(), s + w.end()) for w in re.finditer(r"\s+", m.group(0))
        ):
            continue  # groups far apart on the page (table columns)
        digits = re.sub(r"\D", "", m.group(0))
        core = digits[-8:]
        has_prefix = len(digits) > 8
        spans.append(Span("telefon", s, e, ("+47" + core) if has_prefix else core))

    for m in EMAIL_RE.finditer(text):
        spans.append(Span("epost", m.start(), m.end(), m.group(0).lower()))

    for term in terms:
        for m in term_pattern(term).finditer(text):
            spans.append(Span("term", m.start(), m.end(), collapse_ws(normalize_text(term))))
    return spans


def find_in_string(text: str, terms: Iterable[str]) -> list[tuple[str, str, str, str]]:
    """(type, text, normalized, excerpt) for every detection in a string
    (after NFKC and removal of invisible characters)."""
    text = normalize_text(text)
    return [
        (sp.type, collapse_ws(text[sp.start:sp.end]), sp.normalized,
         _excerpt(text, sp.start, sp.end))
        for sp in scan_text(text, terms)
    ]


REJECT_REASON = (
    "sifrene står langt fra hverandre på siden (trolig ulike tabellceller), så "
    "dette er ikke merket for sladding. Sett \"sladd\" til true hvis det er et "
    "ekte nummer som skal bort."
)


def _word_rects(pt: PageText, start: int, end: int) -> list[list[float]]:
    """One rectangle per word (run without whitespace) in text[start:end]:
    for a rejected candidate the digit groups stand far apart, so each group
    gets its own box instead of one box over the gap."""
    out: list[list[float]] = []
    for m in re.finditer(r"\S+", pt.text[start:end]):
        out.extend(_rects_for_span(pt, start + m.start(), start + m.end()))
    return out


def _hits_from_spans(pt: PageText, page_no: int, spans: list[Span], per_word: bool = False) -> list[Hit]:
    text = pt.text
    hits: list[Hit] = []
    for sp in spans:
        rects = (_word_rects if per_word else _rects_for_span)(pt, sp.start, sp.end)
        if not rects:
            continue
        hits.append(
            Hit(
                type=sp.type,
                text=collapse_ws(text[sp.start:sp.end]),
                normalized=sp.normalized,
                page=page_no,
                excerpt=_excerpt(text, sp.start, sp.end),
                rects=rects,
            )
        )
    hits.sort(key=lambda h: (h.rects[0][1], h.rects[0][0]))
    return hits


# Rejected candidates always pass the fnr control digits (only valid numbers
# are candidates). One is "quiet" (left out of the plan) only when at least
# one word it is made of is clearly something else than a fnr: a date with a
# 4-digit year (a fnr has a 2-digit year), a case number "2026/2911", or an
# amount with exactly two decimals after a decimal comma. Everything else
# stays in the plan, however it is split. A thousands separator alone
# ("150.685") is not enough: that may be a fnr.
_NOT_FNR_WORD_RES = [
    re.compile(r"(?:0?[1-9]|[12]\d|3[01])([./-])(?:0?[1-9]|1[0-2])\1(?:19|20)\d{2}[.,;:]?"),
    re.compile(r"(?:19|20)\d{2}/\d+[.,;:]?"),
    re.compile(r"\d+(?:[.\u00a0]\d{3})*,\d{2}"),
]


def _clearly_not_fnr(text: str) -> bool:
    return any(r.fullmatch(w) for w in text.split() for r in _NOT_FNR_WORD_RES)


def scan_page(pt: PageText, page_no: int, terms: Iterable[str]) -> tuple[list[Hit], list[Hit]]:
    """(hits, rejected): rejected are number candidates that only appear
    when digit groups far apart on the page are joined."""
    terms = list(terms)
    gated = scan_text(pt.text, terms, gap_checker(pt))
    strict = scan_text(pt.text, terms)
    kept_spans = [(sp.start, sp.end) for sp in gated]
    rejected_spans = [
        sp for sp in strict
        if sp.type in ("fodselsnummer", "d_nummer", "telefon")
        and not any(sp.start < b and a < sp.end for a, b in kept_spans)
    ]
    rejected = _hits_from_spans(pt, page_no, rejected_spans, per_word=True)
    for h in rejected:
        h.rejected = True
        h.reason = REJECT_REASON
        h.quiet = h.type != "telefon" and _clearly_not_fnr(h.text)
    return _hits_from_spans(pt, page_no, gated), rejected


def find_in_page(pt: PageText, page_no: int, terms: Iterable[str]) -> list[Hit]:
    return scan_page(pt, page_no, terms)[0]


def find_rejected(doc: pymupdf.Document, terms: Sequence[str]) -> list[Hit]:
    out: list[Hit] = []
    for i, page in enumerate(doc):
        out.extend(scan_page(page_text(page), i + 1, terms)[1])
    return out


def find_hits(doc: pymupdf.Document, terms: Sequence[str], progress=None) -> list[Hit]:
    hits: list[Hit] = []
    n = doc.page_count
    for i, page in enumerate(doc):
        hits.extend(find_in_page(page_text(page), i + 1, terms))
        if progress:
            progress((i + 1) / max(n, 1))
    return hits
