"""Rule-based analysis: tables, title/source/notes, headers, sums and numbers.

The rules (docs/spesifikasjon-datawrapper.md, «Analyse»), in order:

1. Visible sheets only; the sheet with the most numbers is suggested.
2. Tables are the blocks left when the sheet is cut at empty rows and
   columns (recursively). Each block with at least two filled cells in one
   row is a table; the largest is suggested.
3. One-cell text lines above a table are its title. Lines below that start
   with «Kilde», «Note», «Merknad», «*», «¹» or «1)» are source and notes.
4. Rows above the first row with numbers are headers. Merged cells are
   filled, and headers over several rows are joined with « – ».
5. Hidden rows and columns are gone already (reading.py).
6. Rows and columns labelled «I alt», «Sum», «Totalt», «Total» or «Hele
   landet» are marked.
7. Numbers: Norwegian formats via jv_common.numbers; SSB symbols become
   empty cells; numbers stored as text become numbers.
8. Excel dates as YYYY-MM-DD; years in headers stay text.
9. The first column holds the labels. If it holds numbers and the first
   row is text, swapping rows and columns is suggested.
10. Empty cells under a label in hierarchical tables are filled from above.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal

from jv_common.numbers import parse_number

from .reading import Sheet, cell_ref, format_datetime, is_empty

SSB_SYMBOLS = (".", "..", ":", "-", "x")

_TOTAL_RE = re.compile(r"^(i alt|sum|totalt|total|hele landet)\b|\b(i alt|totalt)$", re.IGNORECASE)
_NOTE_RE = re.compile(
    r"^(kilde|kjelde|note|noter|merknad|merknader|fotnote|fotnoter|tegnforklaring)\b"
    r"|^[*¹²³⁴⁵⁶⁷⁸⁹⁰]"
    r"|^\d{1,2}\s*\)",
    re.IGNORECASE,
)
_SOURCE_RE = re.compile(r"^(kilde|kjelde)\s*[:.\-–]?\s*", re.IGNORECASE)
_PERCENT_RE = re.compile(r"^(.*?\d)\s*%$")


def is_year(value: object) -> bool:
    """1900-2099 as an integer number or as text («2023»)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return 1900 <= value <= 2099
    if isinstance(value, str):
        s = value.strip()
        return len(s) == 4 and s.isdigit() and 1900 <= int(s) <= 2099
    return False


def clean_text(value: str) -> str:
    """One line, single spaces (tabs and line breaks would break the TSV)."""
    return " ".join(value.split())


def format_number(value: int | float) -> str:
    """Point as decimal sign, no thousands separator, no exponent.

    Floats are rounded to 15 significant digits first, like Excel shows them,
    so 0.1 + 0.2 becomes 0.3.
    """
    if isinstance(value, int):
        return str(value)
    if value != value or value in (float("inf"), float("-inf")):
        return ""
    d = Decimal(f"{value:.15g}").normalize()
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def format_plain(value: object) -> str:
    """A value as text, without number interpretation (labels and headers)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "SANN" if value else "USANN"
    if isinstance(value, (int, float)):
        return format_number(value)
    if isinstance(value, datetime):
        return format_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M" if not value.second else "%H:%M:%S")
    return clean_text(str(value))


def text_number(text: str):
    """(value, uncertain, had_percent) for a number stored as text, or None."""
    s = clean_text(text)
    percent = False
    m = _PERCENT_RE.match(s)
    if m:
        s = m.group(1)
        percent = True
    parsed = parse_number(s)
    if parsed is None:
        return None
    return parsed.value, parsed.uncertain, percent


def is_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return text_number(value) is not None
    return False


@dataclass
class Converted:
    text: str
    kind: str  # "num", "text", "empty", "symbol", "date"
    uncertain: bool = False
    percent_text: bool = False


def convert_value(value: object) -> Converted:
    """A data cell for Datawrapper."""
    if is_empty(value):
        return Converted("", "empty")
    if isinstance(value, bool):
        return Converted(format_plain(value), "text")
    if isinstance(value, (int, float)):
        return Converted(format_number(value), "num")
    if isinstance(value, (datetime, date, time)):
        return Converted(format_plain(value), "date")
    s = clean_text(str(value))
    if s in SSB_SYMBOLS:
        return Converted("", "symbol")
    tn = text_number(s)
    if tn is not None:
        v, uncertain, pct = tn
        return Converted(format_number(v), "num", uncertain, pct)
    return Converted(s, "text")


# ---------------------------------------------------------------- blocks


def _occupancy(sheet: Sheet) -> list[list[bool]]:
    occ = [[not is_empty(v) for v in row] for row in sheet.rows]
    for r0, c0, r1, c1 in sheet.merges:
        if occ[r0][c0]:
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    occ[r][c] = True
    return occ


def _runs(flags: list[bool], offset: int) -> list[tuple[int, int]]:
    """Runs of True as half-open (start, end), shifted by offset."""
    runs = []
    start = None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            runs.append((offset + start, offset + i))
            start = None
    if start is not None:
        runs.append((offset + start, offset + len(flags)))
    return runs


def find_blocks(occ: list[list[bool]]) -> list[tuple[int, int, int, int]]:
    """Recursive cut at empty rows and columns. Blocks as half-open (r0, r1, c0, c1)."""
    if not occ:
        return []
    out: list[tuple[int, int, int, int]] = []
    stack = [(0, len(occ), 0, len(occ[0]))]
    while stack:
        r0, r1, c0, c1 = stack.pop()
        row_flags = [any(occ[r][c0:c1]) for r in range(r0, r1)]
        row_runs = _runs(row_flags, r0)
        if not row_runs:
            continue
        if len(row_runs) > 1:
            stack.extend((a, b, c0, c1) for a, b in reversed(row_runs))
            continue
        r0, r1 = row_runs[0]
        col_flags = [any(occ[r][c] for r in range(r0, r1)) for c in range(c0, c1)]
        col_runs = _runs(col_flags, c0)
        if len(col_runs) > 1:
            stack.extend((r0, r1, a, b) for a, b in reversed(col_runs))
            continue
        c0, c1 = col_runs[0]
        out.append((r0, r1, c0, c1))
    out.sort(key=lambda b: (b[0], b[2]))
    return out


# ---------------------------------------------------------------- tables


@dataclass
class Table:
    sheet: Sheet
    r0: int
    r1: int
    c0: int
    c1: int  # core area (half-open), grid coordinates, without title and notes
    title_lines: list[str] = field(default_factory=list)
    note_lines: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return (self.r1 - self.r0) * (self.c1 - self.c0)

    def range_ref(self) -> str:
        s = self.sheet
        top = cell_ref(s.row_ids[self.r0], s.col_ids[self.c0])
        bottom = cell_ref(s.row_ids[self.r1 - 1], s.col_ids[self.c1 - 1])
        return f"{top}:{bottom}"


def _row_cells(sheet: Sheet, r: int, c0: int, c1: int) -> list[int]:
    return [c for c in range(c0, c1) if not is_empty(sheet.rows[r][c])]


def _single_text(sheet: Sheet, r: int, c0: int, c1: int) -> str | None:
    """The text if the row has exactly one filled cell, a text in the first column."""
    cells = _row_cells(sheet, r, c0, c1)
    if len(cells) != 1 or cells[0] != c0:
        return None
    v = sheet.rows[r][c0]
    if not isinstance(v, str) or is_number(v):
        return None
    return clean_text(v)


def _is_note_block(sheet: Sheet, b: tuple[int, int, int, int]) -> bool:
    r0, r1, c0, c1 = b
    return all(len(_row_cells(sheet, r, c0, c1)) <= 1 for r in range(r0, r1))


def find_tables(sheet: Sheet) -> list[Table]:
    blocks = find_blocks(_occupancy(sheet))
    tables: list[Table] = []
    loose: list[tuple[int, str]] = []  # one-cell lines outside tables
    for b in blocks:
        r0, r1, c0, c1 = b
        if _is_note_block(sheet, b):
            for r in range(r0, r1):
                cells = _row_cells(sheet, r, c0, c1)
                if cells:
                    loose.append((r, format_plain(sheet.rows[r][cells[0]])))
            continue
        t = Table(sheet, r0, r1, c0, c1)
        # Leading one-cell text lines: title.
        while t.r1 - t.r0 > 2:
            line = _single_text(sheet, t.r0, t.c0, t.c1)
            if line is None:
                break
            t.title_lines.append(line)
            t.r0 += 1
        # Trailing lines that look like source or notes.
        tail: list[str] = []
        while t.r1 - t.r0 > 2:
            line = _single_text(sheet, t.r1 - 1, t.c0, t.c1)
            if line is None or not _NOTE_RE.match(line):
                break
            tail.append(line)
            t.r1 -= 1
        t.note_lines = list(reversed(tail))
        _trim_columns(t)
        tables.append(t)
    _attach_loose_lines(tables, loose)
    return tables


def _trim_columns(t: Table) -> None:
    s = t.sheet

    def empty_col(c: int) -> bool:
        return all(is_empty(s.rows[r][c]) for r in range(t.r0, t.r1))

    while t.c1 - t.c0 > 1 and empty_col(t.c0):
        t.c0 += 1
    while t.c1 - t.c0 > 1 and empty_col(t.c1 - 1):
        t.c1 -= 1


def _attach_loose_lines(tables: list[Table], loose: list[tuple[int, str]]) -> None:
    """Lines in their own blocks: notes of the table above, or title of the table below."""
    titles: dict[int, list[str]] = {}
    for r, line in loose:
        above = [t for t in tables if t.r1 <= r]
        below = [t for t in tables if t.r0 > r]
        t_above = max(above, key=lambda t: t.r1) if above else None
        t_below = min(below, key=lambda t: t.r0) if below else None
        if t_above is not None and (_NOTE_RE.match(line) or t_below is None):
            t_above.note_lines.append(line)
        elif t_below is not None:
            titles.setdefault(id(t_below), []).append(line)
    for t in tables:
        t.title_lines = titles.get(id(t), []) + t.title_lines


# ---------------------------------------------------------------- one table, cleaned


@dataclass
class Column:
    index: int  # 1-based position in the result before columns are removed
    name: str
    numeric: bool
    is_sum: bool = False
    removed: bool = False


@dataclass
class Result:
    header: list[str]
    rows: list[list[str]]
    columns: list[Column]
    title: str
    description: str
    source: str
    notes: list[str]
    header_rows: int
    sum_rows: list[str]
    sum_columns: list[str]
    sum_rows_removed: bool
    hidden_rows: int
    hidden_columns: int
    symbols: dict[str, int]
    filled_labels: int
    uncertain: list[str]  # cell refs
    percent_text: int
    percent_format: int
    excel_errors: int
    transpose_suggested: bool
    transposed: bool
    generated_header: bool
    removed_columns: list[str]


def _total_label(text: str) -> bool:
    return bool(_TOTAL_RE.search(text.strip().rstrip(":").strip()))


def _fill_merges(t: Table) -> list[list[object]]:
    s = t.sheet
    grid = [list(s.rows[r][t.c0 : t.c1]) for r in range(t.r0, t.r1)]
    for r0, c0, r1, c1 in s.merges:
        if not (t.r0 <= r0 < t.r1 and t.c0 <= c0 < t.c1):
            continue
        v = s.rows[r0][c0]
        for r in range(r0, min(r1 + 1, t.r1)):
            for c in range(c0, min(c1 + 1, t.c1)):
                grid[r - t.r0][c - t.c0] = v
    return grid


def _header_row_count(grid: list[list[object]]) -> int:
    """Rows above the first row with data numbers.

    Years (1900-2099) count as header text: «Region | 2022 | 2023» is a header
    when a row with other numbers follows within a few rows. Without such a
    row, the first row with any number is the first data row.
    """
    first_any = first_data = None
    for i, row in enumerate(grid):
        nums = [v for v in row if not is_empty(v) and is_number(v)]
        if nums and first_any is None:
            first_any = i
        if any(not is_year(v) for v in nums):
            first_data = i
            break
    if first_any is None:
        return min(1, len(grid))
    if first_data is not None and first_data - first_any <= 2 and first_data <= 8:
        return first_data
    return first_any


def _label_columns(data: list[list[object]], width: int) -> int:
    """Leading columns without data numbers (column 0 may hold years or dates)."""
    n = 0
    for c in range(width - 1):
        values = [row[c] for row in data if not is_empty(row[c])]
        if not values:
            n += 1
            continue
        if c == 0 and all(is_year(v) or isinstance(v, (datetime, date)) for v in values):
            n += 1
            continue
        if any(is_number(v) for v in values):
            break
        n += 1
    return n


def build(
    t: Table,
    with_sums: bool = False,
    transpose: bool = False,
    remove_columns: tuple[int, ...] = (),
) -> Result:
    s = t.sheet
    grid = _fill_merges(t)
    width = t.c1 - t.c0
    h = _header_row_count(grid)
    header_grid = grid[:h]
    # Data rows with their grid row (for cell references in warnings).
    pairs = [(row, t.r0 + i) for i, row in enumerate(grid) if i >= h and any(not is_empty(v) for v in row)]
    data = [row for row, _ in pairs]
    data_r = [r for _, r in pairs]

    # Headers: one per column, parts from top to bottom joined with « – ».
    generated_header = False
    if header_grid:
        header = []
        header_parts = []
        for c in range(width):
            parts: list[str] = []
            for row in header_grid:
                p = format_plain(row[c])
                if p and (not parts or parts[-1] != p):
                    parts.append(p)
            header_parts.append(parts)
            header.append(" – ".join(parts))
    else:
        generated_header = True
        header = [f"Kolonne {c + 1}" for c in range(width)]
        header_parts = [[] for _ in range(width)]

    n_labels = _label_columns(data, width)

    # Hierarchical tables: fill empty labels from above (all label columns but the last).
    filled = 0
    if n_labels >= 2:
        for c in range(n_labels - 1):
            last: object = None
            for row in data:
                if is_empty(row[c]):
                    if last is not None and any(not is_empty(v) for v in row[c + 1 :]):
                        row[c] = last
                        filled += 1
                else:
                    last = row[c]

    # Sums.
    label_cols = range(n_labels)
    sum_row_flags = [
        any(isinstance(row[c], str) and _total_label(row[c]) for c in label_cols) for row in data
    ]
    sum_col_flags = [
        c >= n_labels and any(_total_label(p) for p in header_parts[c]) for c in range(width)
    ]

    # Cells.
    symbols: dict[str, int] = {}
    uncertain: list[str] = []
    percent_text = 0
    percent_format = 0
    excel_errors = 0
    out_rows: list[list[str]] = []
    kinds: list[list[str]] = []
    for row, gr in zip(data, data_r):
        texts, ks = [], []
        for c, v in enumerate(row):
            gc = t.c0 + c
            if c < n_labels:
                texts.append(format_plain(v))
                ks.append("text" if not is_empty(v) else "empty")
                continue
            conv = convert_value(v)
            if conv.kind == "symbol":
                sym = clean_text(str(v))
                symbols[sym] = symbols.get(sym, 0) + 1
            if conv.uncertain:
                uncertain.append(cell_ref(s.row_ids[gr], s.col_ids[gc]))
            if conv.percent_text:
                percent_text += 1
            if conv.kind == "num" and (gr, gc) in s.percent:
                percent_format += 1
            if (gr, gc) in s.errors:
                excel_errors += 1
            texts.append(conv.text)
            ks.append(conv.kind)
        out_rows.append(texts)
        kinds.append(ks)

    # Transposing is suggested when column 0 holds numbers and the header is text.
    transpose_suggested = (
        n_labels == 0
        and not generated_header
        and any(k == "num" for k in (ks[0] for ks in kinds))
        and all(not is_number(v) for v in (header_grid[-1] if header_grid else []) if not is_empty(v))
    )

    sum_rows = []
    for i, flag in enumerate(sum_row_flags):
        if flag:
            c = next(c for c in label_cols if isinstance(data[i][c], str) and _total_label(data[i][c]))
            sum_rows.append(" – ".join(out_rows[i][k] for k in range(c + 1) if out_rows[i][k]))
    sum_columns = [header[c] for c, f in enumerate(sum_col_flags) if f]
    if not with_sums:
        keep_r = [i for i, f in enumerate(sum_row_flags) if not f]
        out_rows = [out_rows[i] for i in keep_r]
        kinds = [kinds[i] for i in keep_r]
        keep_c = [c for c, f in enumerate(sum_col_flags) if not f]
        header = [header[c] for c in keep_c]
        out_rows = [[row[c] for c in keep_c] for row in out_rows]
        kinds = [[k[c] for c in keep_c] for k in kinds]

    if transpose:
        matrix = [header] + out_rows
        kmatrix = [["text"] * len(header)] + kinds
        tm = [list(col) for col in zip(*matrix)] if matrix and header else []
        tk = [list(col) for col in zip(*kmatrix)] if kmatrix and header else []
        header, out_rows = (tm[0], tm[1:]) if tm else ([], [])
        kinds = [k for k in tk[1:]] if tk else []

    columns = [
        Column(i + 1, name, numeric=_numeric_column([k[i] for k in kinds]))
        for i, name in enumerate(header)
    ]
    if not transpose:
        sum_names = set(sum_columns)
        for col in columns:
            col.is_sum = with_sums and col.name in sum_names

    removed_names: list[str] = []
    if remove_columns:
        drop = {i - 1 for i in remove_columns}
        for i in sorted(drop):
            columns[i].removed = True
            removed_names.append(header[i])
        keep = [i for i in range(len(header)) if i not in drop]
        header = [header[i] for i in keep]
        out_rows = [[row[i] for i in keep] for row in out_rows]

    source_parts, notes = [], []
    for line in t.note_lines:
        m = _SOURCE_RE.match(line)
        if m:
            source_parts.append(line[m.end() :].strip())
        else:
            notes.append(line)

    return Result(
        header=header,
        rows=out_rows,
        columns=columns,
        title=t.title_lines[0] if t.title_lines else "",
        description=" ".join(t.title_lines[1:]),
        source="; ".join(p for p in source_parts if p),
        notes=notes,
        header_rows=h,
        sum_rows=sum_rows,
        sum_columns=sum_columns,
        sum_rows_removed=not with_sums,
        hidden_rows=sum(1 for r in s.hidden_rows if s.row_ids and _within(r, s.row_ids[t.r0], s.row_ids[t.r1 - 1])),
        hidden_columns=sum(1 for c in s.hidden_cols if s.col_ids and _within(c, s.col_ids[t.c0], s.col_ids[t.c1 - 1])),
        symbols=symbols,
        filled_labels=filled,
        uncertain=uncertain,
        percent_text=percent_text,
        percent_format=percent_format,
        excel_errors=excel_errors,
        transpose_suggested=transpose_suggested,
        transposed=transpose,
        generated_header=generated_header,
        removed_columns=removed_names,
    )


def _within(x: int, lo: int, hi: int) -> bool:
    return lo < x < hi


def _numeric_column(kinds: list[str]) -> bool:
    filled = [k for k in kinds if k != "empty" and k != "symbol"]
    return bool(filled) and all(k == "num" for k in filled)


def count_numbers(sheet: Sheet) -> int:
    return sum(1 for row in sheet.rows for v in row if not is_empty(v) and is_number(v))


def to_tsv(header: list[str], rows: list[list[str]]) -> str:
    return "".join("\t".join(r) + "\n" for r in [header, *rows])
