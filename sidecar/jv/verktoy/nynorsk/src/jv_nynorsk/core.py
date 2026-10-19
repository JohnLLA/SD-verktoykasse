"""Core logic: translate .txt, .md and .docx between bokmål and nynorsk with Apertium.

Apertium is called through subprocess with argument lists, in the standard
mode that marks problem words in its output: ``*word`` (unknown word),
``#word`` or ``in#word`` (lemma known, but the form cannot be generated) and
``@word`` (missing in the bilingual dictionary). Real Apertium moves and
duplicates ``*``, ``#`` and ``@`` that stand in the author's text (Markdown
``**bold**``, hashtags, ``@names``), also when they are disguised, so those
characters never reach Apertium: the text is cut at every run of them, the
pieces are translated, and the author's characters are put back between the
translated pieces. Every ``*``, ``#`` and ``@`` in Apertium's output is
therefore a mark. Each marked word is wrapped as ``[?word]`` and listed; no raw
mark is ever left in the draft.

No printing, no sys.exit: errors are raised as UserError.
"""

from __future__ import annotations

import os
import re
import subprocess
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from jv_common import UserError, require_binary, safe_output_path

# --to value -> Apertium mode
MODES = {"nn": "nob-nno", "nb": "nno-nob"}
TARGET_NAMES = {"nn": "nynorsk", "nb": "bokmål"}
SUPPORTED_SUFFIXES = (".txt", ".md", ".docx")

MARK_TYPES = {"*": "unknown", "#": "generation", "@": "untranslated"}
MARK_TYPES_NO = {
    "unknown": "ukjent ord",
    "generation": "bøyingsfeil",
    "untranslated": "uten oversettelse",
}
MARKER_TEMPLATE = "[?{word}]"

SETUP_DOC = "verktoy/nynorsk/OPPSETT.md"
TIMEOUT_SECONDS = 900

_WORD = re.compile(r"\w+(?:[-'’]\w+)*")
_MISSING_MODE = re.compile(
    r"(mode\b.*\b(does not exist|not found|ikke)|no such mode|unknown mode)",
    re.IGNORECASE,
)

ProgressFn = Callable[[float], None]


# --------------------------------------------------------------------------
# Apertium wrapper
# --------------------------------------------------------------------------


def _missing_apertium_message() -> str:
    return (
        "Apertium er ikke installert eller ikke i PATH. Verktøyet trenger "
        "programmet «apertium» og språkparet apertium-nno-nob (modusene "
        "nob-nno og nno-nob). Installer begge og prøv igjen; se "
        f"{SETUP_DOC} for fremgangsmåte på macOS (Homebrew eller bygging fra kilde)."
    )


def _missing_mode_message(mode: str) -> str:
    return (
        f"Apertium er installert, men språkretningen «{mode}» finnes ikke. "
        "Installer språkparet apertium-nno-nob (gir både nob-nno og nno-nob); "
        f"se {SETUP_DOC}."
    )


class Apertium:
    """Thin wrapper around the ``apertium`` command for one mode."""

    def __init__(self, mode: str, binary: str | None = None) -> None:
        if binary is None:
            try:
                binary = require_binary("apertium")
            except UserError:
                raise UserError(_missing_apertium_message()) from None
        self.binary = binary
        self.mode = mode

    def available_modes(self) -> list[str] | None:
        """Modes reported by ``apertium -l``, or None if that is not supported."""
        try:
            proc = subprocess.run(
                [self.binary, "-l"],
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        modes = proc.stdout.decode("utf-8", errors="replace").split()
        return modes or None

    def check_mode(self) -> None:
        modes = self.available_modes()
        if modes is not None and self.mode not in modes:
            raise UserError(_missing_mode_message(self.mode))

    def run(self, text: str) -> str:
        """Translate text; problem words come back with *, # or @ marks."""
        args = [self.binary, "-f", "txt", self.mode]
        try:
            proc = subprocess.run(
                args,
                input=text.encode("utf-8"),
                capture_output=True,
                check=False,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise UserError(
                f"Apertium brukte mer enn {TIMEOUT_SECONDS} sekunder og ble stoppet."
            ) from None
        except OSError as exc:
            raise UserError(f"Klarte ikke å starte Apertium: {exc}") from None
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            if _MISSING_MODE.search(stderr):
                raise UserError(_missing_mode_message(self.mode))
            detail = stderr.splitlines()[-1] if stderr else "ingen feilmelding"
            raise UserError(
                f"Apertium feilet med kode {proc.returncode}: {detail}"
            )
        return proc.stdout.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# Marks: Apertium's own *, # and @
# --------------------------------------------------------------------------

MARK_CHARS = "*#@"
# A word with marks: a leading mark, a mark inside (på#drage) or a trailing one.
_MARKED = re.compile(
    r"[*#@]*\w+(?:[-'’#*@]+\w+)*[*#@]*|[*#@]+"
)
# Apertium handles roughly this many tokens before cg-proc forces a break
BATCH_TOKENS = 300
_TOKEN = re.compile(r"\w+|[^\w\s]")


@dataclass
class Translated:
    text: str  # draft with [?word] markers
    marks: list[tuple[str, str]] = field(default_factory=list)  # (word, type)
    offsets: list[int] = field(default_factory=list)  # marker start in text
    warnings: list[str] = field(default_factory=list)


def parse_marks(output: str) -> Translated:
    """Turn Apertium output with raw marks into a draft with [?word] markers.

    Marks from the author must already be protected (see translate_text), so
    every ``*``, ``#`` and ``@`` here comes from Apertium. When a word has
    several marks the first one decides the type.
    """
    pieces: list[str] = []
    marks: list[tuple[str, str]] = []
    offsets: list[int] = []
    length = 0
    cursor = 0
    for match in _MARKED.finditer(output):
        chunk = match.group(0)
        found = [c for c in chunk if c in MARK_CHARS]
        if not found:
            continue
        before = output[cursor:match.start()]
        word = "".join(c for c in chunk if c not in MARK_CHARS)
        cursor = match.end()
        if not word:
            pieces.append(before)  # a lone mark with no word: drop it
            length += len(before)
            continue
        marker = MARKER_TEMPLATE.format(word=word)
        pieces += [before, marker]
        length += len(before)
        offsets.append(length)
        length += len(marker)
        marks.append((word, MARK_TYPES[found[0]]))
    pieces.append(output[cursor:])
    return Translated("".join(pieces), marks, offsets)


_SYMBOL_RUNS = re.compile(r"([*#@]+)")
_PADDING = re.compile(r"(\s*)(.*?)(\s*)\Z", re.DOTALL)


def _translate_cores(engine: Apertium, cores: list[str]) -> tuple[list[str], int]:
    """Translate pieces of text, one output per input (joined by blank lines).

    Returns (raw outputs, number of pieces left untranslated). A piece whose
    line count changes is retried alone, then line by line; if a line still changes, the original
    line is kept so nothing is silently damaged.
    """
    counts = [c.count("\n") + 1 for c in cores]
    # A blank line between pieces: with a single newline real Apertium
    # sometimes adds an extra one after words like "var".
    lines = engine.run("\n\n".join(cores)).rstrip("\n").split("\n")
    if len(lines) == sum(counts) + len(cores) - 1:
        out, pos, intact = [], 0, True
        for n in counts:
            out.append("\n".join(lines[pos:pos + n]))
            intact = intact and (pos + n >= len(lines) or lines[pos + n] == "")
            pos += n + 1
        if intact:
            return out, 0
    out, skipped = [], 0
    for core, n in zip(cores, counts):
        single = engine.run(core).rstrip("\n").split("\n")
        if len(single) == n:
            out.append("\n".join(single))
            continue
        done = []  # still wrong: one call per line
        for line in core.split("\n"):
            if not line.strip():
                done.append(line)
                continue
            result = engine.run(line).rstrip("\n").split("\n")
            if len(result) == 1:
                done.append(result[0])
            else:
                done.append(line)
                skipped += 1
        out.append("\n".join(done))
    return out, skipped


def translate_text(engine: Apertium, text: str) -> Translated:
    """Translate text; the author's own *, # and @ stay exactly where they are."""
    parts = _SYMBOL_RUNS.split(text)  # even index: text, odd index: symbols
    padded: dict[int, tuple[str, str, str]] = {}
    for i in range(0, len(parts), 2):
        lead, core, trail = _PADDING.match(parts[i]).groups()
        padded[i] = (lead, core, trail)
    indexes = [i for i, (_l, core, _t) in padded.items() if core]
    outputs: dict[int, str] = {}
    skipped = 0
    if indexes:
        raws, skipped = _translate_cores(engine, [padded[i][1] for i in indexes])
        outputs = dict(zip(indexes, raws))

    pieces: list[str] = []
    marks: list[tuple[str, str]] = []
    offsets: list[int] = []
    length = 0

    def add(piece: str) -> None:
        nonlocal length
        pieces.append(piece)
        length += len(piece)

    for i, part in enumerate(parts):
        if i % 2:
            add(part)
            continue
        lead, core, trail = padded[i]
        add(lead)
        if core:
            res = parse_marks(outputs[i])
            offsets.extend(length + o for o in res.offsets)
            marks.extend(res.marks)
            add(res.text)
        add(trail)
    warnings = []
    if skipped:
        warnings.append(
            f"{skipped} linjer ble ikke oversatt fordi Apertium endret "
            "linjestrukturen. De står uendret i utkastet."
        )
    return Translated("".join(pieces), marks, offsets, warnings)


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT_RUNS_XPATH = (
    "./w:r | ./w:hyperlink/w:r | ./w:ins/w:r | ./w:smartTag/w:r "
    "| ./w:fldSimple/w:r"
)


def _is_line_break(el) -> bool:
    return el.tag in (f"{_W}br", f"{_W}cr") and el.get(f"{_W}type") in (
        None,
        "textWrapping",
    )


def _run_text(r) -> str:
    parts: list[str] = []
    for child in r:
        if child.tag == f"{_W}t":
            parts.append(child.text or "")
        elif child.tag == f"{_W}tab":
            parts.append("\t")
        elif _is_line_break(child):
            parts.append("\n")
    return "".join(parts)


def _text_children(r) -> list:
    return [
        c
        for c in r
        if c.tag in (f"{_W}t", f"{_W}tab") or _is_line_break(c)
    ]


class _DocxParagraph:
    """A paragraph whose text lives in a list of w:r elements."""

    def __init__(self, paragraph) -> None:
        self.paragraph = paragraph
        self.runs = [r for r in paragraph._p.xpath(_TEXT_RUNS_XPATH)]
        self.text = "".join(_run_text(r) for r in self.runs)

    def mixed_formatting(self) -> bool:
        from lxml import etree  # dependency of python-docx

        formats = set()
        for r in self.runs:
            if not _run_text(r).strip():
                continue
            rpr = r.find(f"{_W}rPr")
            formats.add(b"" if rpr is None else etree.tostring(rpr))
        return len(formats) > 1

    def set_text(self, text: str) -> None:
        from docx.text.run import Run

        first = next((r for r in self.runs if _run_text(r)), None)
        if first is None:
            return
        for r in self.runs:
            if r is first:
                continue
            for child in _text_children(r):
                r.remove(child)
        # Run.text replaces w:t/w:tab/w:br children and turns \t and \n into
        # w:tab and w:br; keep non-text children such as drawings.
        for child in _text_children(first):
            first.remove(child)
        Run(first, self.paragraph).text = text


def _iter_table_paragraphs(tables, seen: set[int]):
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                if id(cell._tc) in seen:
                    continue  # merged cells are returned more than once
                seen.add(id(cell._tc))
                yield from cell.paragraphs
                yield from _iter_table_paragraphs(cell.tables, seen)


def _iter_docx_paragraphs(document):
    yield from document.paragraphs
    yield from _iter_table_paragraphs(document.tables, set())


def _open_docx(path: Path):
    import docx

    if not zipfile.is_zipfile(path):
        raise UserError(
            f"«{path.name}» er ikke en gyldig DOCX-fil (ikke et Word-dokument)."
        )
    try:
        return docx.Document(str(path))
    except Exception:  # noqa: BLE001 - python-docx raises many types
        raise UserError(
            f"Klarte ikke å lese «{path.name}» som Word-dokument (DOCX)."
        ) from None


def _batches(paragraphs: list[_DocxParagraph]) -> list[list[_DocxParagraph]]:
    """Group paragraphs so each Apertium call stays below the cohort limit."""
    batches: list[list[_DocxParagraph]] = []
    current: list[_DocxParagraph] = []
    size = 0
    for p in paragraphs:
        tokens = len(_TOKEN.findall(p.text)) + 1
        if current and size + tokens > BATCH_TOKENS:
            batches.append(current)
            current, size = [], 0
        current.append(p)
        size += tokens
    if current:
        batches.append(current)
    return batches


def _translate_batch(
    engine: Apertium, paragraphs: list[_DocxParagraph]
) -> list[Translated] | None:
    """Translate paragraphs in one call (joined by blank lines).

    Returns None if Apertium did not keep the line structure, so the caller
    can fall back to one call per paragraph.
    """
    line_counts = [p.text.count("\n") + 1 for p in paragraphs]
    joined = "\n\n".join(p.text for p in paragraphs)  # blank line = safe separator
    result = translate_text(engine, joined)
    lines = result.text.split("\n")
    if len(lines) != sum(line_counts) + len(paragraphs) - 1:
        return None
    mark_lines = [result.text.count("\n", 0, off) for off in result.offsets]
    out: list[Translated] = []
    first_line = 0
    for count in line_counts:
        last_line = first_line + count
        if last_line < len(lines) and lines[last_line] != "":
            return None
        chunk = "\n".join(lines[first_line:last_line])
        para_marks = [
            m
            for m, line in zip(result.marks, mark_lines)
            if first_line <= line < last_line
        ]
        out.append(Translated(chunk, para_marks))
        first_line = last_line + 1
    if out:
        out[0].warnings = result.warnings
    return out


def _translate_lines(
    engine: Apertium,
    paragraphs: list[_DocxParagraph],
    progress: ProgressFn | None = None,
) -> list[Translated]:
    """Translate in batches; a batch that loses its structure goes paragraph by paragraph."""
    results: list[Translated] = []
    done = 0
    for batch in _batches(paragraphs):
        part = _translate_batch(engine, batch)
        if part is None:
            part = [translate_text(engine, p.text) for p in batch]
        results.extend(part)
        done += len(batch)
        if progress:
            progress(0.9 * done / len(paragraphs))
    return results


def translate_docx(
    engine: Apertium, src: Path, dst: Path, progress: ProgressFn | None = None
) -> tuple[list[tuple[str, str]], list[str], int]:
    """Translate paragraph by paragraph. Returns (marks, warnings, paragraphs)."""
    document = _open_docx(src)
    paragraphs = [
        p
        for p in (_DocxParagraph(par) for par in _iter_docx_paragraphs(document))
        if p.text.strip()
    ]
    if not paragraphs:
        raise UserError(f"«{src.name}» inneholder ingen tekst å oversette.")

    warnings: list[str] = []
    results = _translate_lines(engine, paragraphs, progress)

    mixed = 0
    marks: list[tuple[str, str]] = []
    for p, res in zip(paragraphs, results):
        if p.mixed_formatting():
            mixed += 1
        p.set_text(res.text)
        marks.extend(res.marks)
        warnings.extend(res.warnings)
    if mixed:
        warnings.append(
            f"{mixed} avsnitt hadde blandet tegnformatering (for eksempel fet "
            "eller kursiv i deler av avsnittet). Den er ikke beholdt: hele "
            "avsnittet har fått formateringen til den første teksten i avsnittet."
        )
    document.save(str(dst))
    return marks, warnings, len(paragraphs)


# --------------------------------------------------------------------------
# Plain text and Markdown
# --------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UserError(
            f"«{path.name}» er ikke UTF-8-tekst. Lagre filen som UTF-8 og prøv igjen."
        ) from None


# --------------------------------------------------------------------------
# Public entry
# --------------------------------------------------------------------------


@dataclass
class FileResult:
    input: Path
    output: Path
    mode: str
    paragraphs: int
    marks: list[tuple[str, str]]
    warnings: list[str]

    def unknown_words(self) -> list[dict]:
        counts: dict[tuple[str, str], int] = {}
        for key in self.marks:
            counts[key] = counts.get(key, 0) + 1
        return [
            {"word": w, "type": t, "count": c} for (w, t), c in counts.items()
        ]


def validate_input(path: Path) -> Path:
    if not path.exists():
        raise UserError(f"Filen «{path}» finnes ikke.")
    if not path.is_file():
        raise UserError(f"«{path}» er ikke en fil.")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise UserError(
            f"«{path.name}» har et format som ikke støttes. "
            "Bruk .txt, .md eller .docx."
        )
    if path.stat().st_size == 0:
        raise UserError(f"«{path.name}» er tom.")
    return path


def make_engine(to: str, binary: str | None = None) -> Apertium:
    if to not in MODES:
        raise UserError("Retningen må være «nn» (til nynorsk) eller «nb» (til bokmål).")
    engine = Apertium(MODES[to], binary)
    engine.check_mode()
    return engine


def translate_file(
    engine: Apertium,
    to: str,
    path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    progress: ProgressFn | None = None,
) -> FileResult:
    src = validate_input(Path(path))
    suffix = src.suffix.lower()
    if suffix == ".docx":
        _open_docx(src)  # fail early, before an output path is reserved
        dst = safe_output_path(src, out_dir, f"-{to}.docx")
        marks, warnings, paragraphs = translate_docx(engine, src, dst, progress)
    else:
        text = _read_text(src)
        if not text.strip():
            raise UserError(f"«{src.name}» inneholder ingen tekst å oversette.")
        result = translate_text(engine, text)
        dst = safe_output_path(src, out_dir, f"-{to}{suffix}")
        dst.write_text(result.text, encoding="utf-8")
        marks, warnings = result.marks, result.warnings
        paragraphs = len([b for b in re.split(r"\n\s*\n", text) if b.strip()])
    return FileResult(src, dst, engine.mode, paragraphs, marks, warnings)


def translate_files(
    to: str,
    paths: Iterable[str | os.PathLike[str]],
    out_dir: str | os.PathLike[str],
    progress: ProgressFn | None = None,
    binary: str | None = None,
) -> list[FileResult]:
    paths = [Path(p) for p in paths]
    for p in paths:
        validate_input(p)  # all inputs are checked before any work starts
        if p.suffix.lower() == ".docx":
            _open_docx(p)  # a bad file is reported before Apertium is checked
    engine = make_engine(to, binary)
    results: list[FileResult] = []
    for n, p in enumerate(paths):
        def part(fraction: float, n: int = n) -> None:
            if progress:
                progress((n + fraction) / len(paths))

        results.append(translate_file(engine, to, p, out_dir, part))
        part(1.0)
    return results
