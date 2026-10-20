"""`analyser` and `lag`: the report data, warnings and the CSV file."""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from jv_common import UserError

from .analysis import Result, Table, build, count_numbers, find_tables, to_tsv
from .reading import Sheet, Workbook, read_file

# The TSV goes in the report; the app reads at most 32 MB of it.
MAX_TSV_BYTES = 24 * 1024 * 1024

_DELIMITER_NAMES = {";": "semikolon", ",": "komma", "\t": "tabulator"}


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _quote_list(items: list[str]) -> str:
    return ", ".join(f"«{i}»" for i in items)


def _sheet_tables(wb: Workbook) -> list[tuple[Sheet, list[Table], int]]:
    return [(s, find_tables(s), count_numbers(s)) for s in wb.sheets]


def _suggested_sheet(found: list[tuple[Sheet, list[Table], int]]) -> int | None:
    best = None
    for i, (_, tables, numbers) in enumerate(found):
        if tables and (best is None or numbers > found[best][2]):
            best = i
    return best


def _suggested_table(tables: list[Table]) -> int | None:
    if not tables:
        return None
    return max(range(len(tables)), key=lambda i: (tables[i].size, -i))


def _table_summary(n: int, t: Table, r: Result, suggested: bool) -> dict:
    return {
        "index": n,
        "range": t.range_ref(),
        "suggested": suggested,
        "rows": len(r.rows),
        "columns": len(r.header),
        "headers": r.header,
        "title": r.title,
        "description": r.description,
        "source": r.source,
        "notes": r.notes,
        "sum_rows": r.sum_rows,
        "sum_columns": r.sum_columns,
        "hidden_rows": r.hidden_rows,
        "hidden_columns": r.hidden_columns,
        "symbols": r.symbols,
        "transpose_suggested": r.transpose_suggested,
    }


def _format_info(wb: Workbook) -> dict:
    info: dict = {"format": wb.kind, "hidden_sheets": wb.hidden_sheets}
    if wb.kind == "csv":
        info["encoding"] = wb.encoding
        info["delimiter"] = _DELIMITER_NAMES.get(wb.delimiter or "", wb.delimiter)
    return info


def analyse(path: Path, progress: Callable[[float], None] = lambda f: None):
    wb = read_file(str(path))
    progress(0.5)
    found = _sheet_tables(wb)
    best_sheet = _suggested_sheet(found)
    sheets = []
    total = 0
    for i, (sheet, tables, numbers) in enumerate(found):
        best_table = _suggested_table(tables)
        summaries = [
            _table_summary(n + 1, t, build(t), suggested=(i == best_sheet and n == best_table))
            for n, t in enumerate(tables)
        ]
        total += len(tables)
        sheets.append(
            {
                "name": sheet.name,
                "numbers": numbers,
                "suggested": i == best_sheet,
                "suggested_table": None if best_table is None else best_table + 1,
                "tables": summaries,
            }
        )
    progress(1.0)
    if total == 0:
        raise UserError("Fant ingen tabell i filen. En tabell trenger minst to kolonner med data.")
    warnings = []
    if wb.hidden_sheets:
        warnings.append(f"Hoppet over {_plural(wb.hidden_sheets, 'skjult ark', 'skjulte ark')}.")
    data = _format_info(wb)
    data["sheets"] = sheets
    data["suggested_sheet"] = None if best_sheet is None else found[best_sheet][0].name
    n_sheets = sum(1 for s in sheets if s["tables"])
    summary = f"Fant {_plural(total, 'tabell', 'tabeller')} i {_plural(n_sheets, 'ark', 'ark')}."
    return data, warnings, summary


def _pick(found, sheet_name: str | None, table_no: int | None) -> tuple[Sheet, list[Table], int]:
    if sheet_name is None:
        idx = _suggested_sheet(found)
        if idx is None:
            raise UserError("Fant ingen tabell i filen. En tabell trenger minst to kolonner med data.")
    else:
        idx = next((i for i, (s, _, _) in enumerate(found) if s.name == sheet_name), None)
        if idx is None:
            raise UserError(f"Fant ikke arket «{sheet_name}» blant de synlige arkene i filen.")
    sheet, tables, _ = found[idx]
    if not tables:
        raise UserError(f"Arket «{sheet.name}» har ingen tabell.")
    if table_no is None:
        n = _suggested_table(tables)
    else:
        if not 1 <= table_no <= len(tables):
            raise UserError(
                f"Arket «{sheet.name}» har {_plural(len(tables), 'tabell', 'tabeller')}. "
                f"Velg et tall fra 1 til {len(tables)}."
            )
        n = table_no - 1
    return sheet, tables, n


def _warnings(r: Result, tables_in_sheet: int, table_no: int, wb: Workbook) -> list[str]:
    w: list[str] = []
    if wb.hidden_sheets:
        w.append(f"Hoppet over {_plural(wb.hidden_sheets, 'skjult ark', 'skjulte ark')}.")
    if tables_in_sheet > 1:
        w.append(f"Arket har {tables_in_sheet} tabeller. Tabell {table_no} er valgt.")
    if r.hidden_rows or r.hidden_columns:
        parts = []
        if r.hidden_rows:
            parts.append(_plural(r.hidden_rows, "skjult rad", "skjulte rader"))
        if r.hidden_columns:
            parts.append(_plural(r.hidden_columns, "skjult kolonne", "skjulte kolonner"))
        w.append(f"Fjernet {' og '.join(parts)}.")
    if r.sum_rows_removed and (r.sum_rows or r.sum_columns):
        parts = []
        if r.sum_rows:
            parts.append(_plural(len(r.sum_rows), "sumrad", "sumrader"))
        if r.sum_columns:
            parts.append(_plural(len(r.sum_columns), "sumkolonne", "sumkolonner"))
        w.append(f"Fjernet {' og '.join(parts)}. Velg «Ta med sumrader» for å beholde dem.")
    if r.symbols:
        n = sum(r.symbols.values())
        w.append(
            f"Symbolene {_quote_list(sorted(r.symbols))} ble tomme celler "
            f"({_plural(n, 'celle', 'celler')})."
        )
    if r.uncertain:
        refs = ", ".join(r.uncertain[:10]) + (" …" if len(r.uncertain) > 10 else "")
        w.append(
            f"{_plural(len(r.uncertain), 'tall', 'tall')} kan leses på to måter, som «1.234». "
            "Punktum med tre sifre etter er lest som tusenskille, ellers som desimaltegn. "
            f"Sjekk {refs}."
        )
    if r.filled_labels:
        w.append(
            f"Fylte ut {_plural(r.filled_labels, 'tom etikett', 'tomme etiketter')} "
            "med etiketten over."
        )
    if r.percent_text:
        w.append(f"Fjernet prosenttegnet i {_plural(r.percent_text, 'celle', 'celler')}. Tallene er beholdt.")
    if r.percent_format:
        w.append(
            f"{_plural(r.percent_format, 'celle', 'celler')} er formatert som prosent i Excel "
            "og står som desimaltall (0.125 betyr 12,5 %)."
        )
    if r.excel_errors:
        w.append(
            f"{_plural(r.excel_errors, 'celle', 'celler')} hadde en feilverdi fra Excel "
            "(som #DIV/0!) og ble tomme."
        )
    if r.generated_header:
        w.append("Fant ingen overskriftsrad. Kolonnene har fått navnene «Kolonne 1», «Kolonne 2» og så videre.")
    if r.transpose_suggested and not r.transposed:
        w.append("Første kolonne har tall og første rad har tekst. Vurder å bytte rader og kolonner.")
    return w


def make(
    path: Path,
    sheet_name: str | None = None,
    table_no: int | None = None,
    with_sums: bool = False,
    transpose: bool = False,
    remove_columns: tuple[int, ...] = (),
    progress: Callable[[float], None] = lambda f: None,
):
    wb = read_file(str(path))
    progress(0.5)
    found = _sheet_tables(wb)
    sheet, tables, n = _pick(found, sheet_name, table_no)
    t = tables[n]
    width = len(build(t, with_sums=with_sums, transpose=transpose).header)
    bad = [i for i in remove_columns if not 1 <= i <= width]
    if bad:
        raise UserError(f"Tabellen har {_plural(width, 'kolonne', 'kolonner')}. Kolonne {bad[0]} finnes ikke.")
    if len(set(remove_columns)) >= width:
        raise UserError("Minst én kolonne må være igjen.")
    r = build(t, with_sums=with_sums, transpose=transpose, remove_columns=tuple(sorted(set(remove_columns))))
    tsv = to_tsv(r.header, r.rows)
    if len(tsv.encode("utf-8")) > MAX_TSV_BYTES:
        raise UserError("Tabellen er for stor til å kopieres til Datawrapper (mer enn 24 MB).")
    progress(1.0)
    data = _format_info(wb)
    data.update(
        {
            "sheet": sheet.name,
            "table": n + 1,
            "tables_in_sheet": len(tables),
            "range": t.range_ref(),
            "title": r.title,
            "description": r.description,
            "source": r.source,
            "notes": r.notes,
            "header_rows": r.header_rows,
            "columns": [
                {"index": c.index, "name": c.name, "numeric": c.numeric, "sum": c.is_sum, "removed": c.removed}
                for c in r.columns
            ],
            "rows": len(r.rows),
            "with_sums": with_sums,
            "transposed": r.transposed,
            "transpose_suggested": r.transpose_suggested,
            "removed": {
                "sum_rows": r.sum_rows if not with_sums else [],
                "sum_columns": r.sum_columns if not with_sums else [],
                "sum_rows_found": r.sum_rows,
                "sum_columns_found": r.sum_columns,
                "hidden_rows": r.hidden_rows,
                "hidden_columns": r.hidden_columns,
                "columns": r.removed_columns,
                "notes": r.notes,
            },
            "symbols": r.symbols,
            "filled_labels": r.filled_labels,
            "uncertain_cells": r.uncertain,
            "tsv": tsv,
            "_rows": (r.header, r.rows),
        }
    )
    warnings = _warnings(r, len(tables), n + 1, wb)
    summary = (
        f"Tabellen har {_plural(len(r.rows), 'rad', 'rader')} og "
        f"{_plural(len(r.header), 'kolonne', 'kolonner')} og er klar for Datawrapper."
    )
    return data, warnings, summary


def _free_path(target: Path, original: Path) -> Path:
    """target, or target-2.csv, -3 … if it exists or is the original."""
    orig = original.resolve()
    candidate = target
    n = 2
    while candidate.exists() or candidate.resolve() == orig:
        candidate = target.with_name(f"{target.stem}-{n}{target.suffix}")
        n += 1
    return candidate


def write_csv(original: Path, target: Path, table: tuple[list[str], list[list[str]]]) -> Path:
    """UTF-8 (no BOM), comma, minimal quoting. Never overwrites the original or an existing file."""
    if target.suffix.lower() != ".csv":
        raise UserError("CSV-filen må ha endelsen .csv.")
    parent = target.parent
    if not parent.is_dir():
        raise UserError(f"Mappen «{parent.name}» finnes ikke. Velg en annen mappe.")
    if not os.access(parent, os.W_OK | os.X_OK):
        raise UserError(f"Mangler skrivetilgang til mappen «{parent.name}». Velg en annen mappe.")
    out = _free_path(target, original)
    header, rows = table
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".jv-datawrapper-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter=",", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(header)
            writer.writerows(rows)
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return out
