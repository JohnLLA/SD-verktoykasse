"""Command line: jv pdf-tables <pdf...> --out <mappe> [--pages 3-7] [--merge] [--csv]."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from jv_common.errors import os_error_message
from jv_common import UserError, build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import run, validate_inputs

TOOL = "pdf-tables"


def _build_parser():
    parser = make_parser(
        prog=f"jv {TOOL}",
        description=(
            "Henter tabeller fra PDF-er med tekstlag til ett XLSX-regneark per PDF, "
            "med ett ark per tabell (arknavn s<side>_t<nr>). Norske tall som "
            "«1 234 567,50», «−12» og «(12)» lagres som tall."
        ),
    )
    parser.add_argument("inputs", nargs="+", metavar="PDF", help="PDF-fil(er) med tekstlag")
    parser.add_argument("--out", required=True, metavar="MAPPE", help="mappe for utfilene")
    parser.add_argument(
        "--pages", metavar="SIDER", help="bare disse sidene, f.eks. 3-7 eller 1,4-5"
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="slå sammen tabeller som fortsetter på neste side med samme kolonner",
    )
    parser.add_argument("--csv", action="store_true", help="skriv også én CSV-fil per tabell")
    return parser


def _message(exc: Exception) -> str:
    if isinstance(exc, UserError):
        return str(exc)
    return os_error_message(exc) or f"Kunne ikke skrive filen ({exc.__class__.__name__})."


def _main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    outputs: list[dict] = []
    warnings: list[str] = []
    total_tables = 0
    count = len(args.inputs)
    validate_inputs(args.inputs, args.out, args.pages)
    failure: Exception | None = None
    done: list[str] = []
    for i, path in enumerate(args.inputs):
        try:
            result = run(
                path,
                args.out,
                pages=args.pages,
                merge=args.merge,
                write_csv_files=args.csv,
                progress=lambda f, i=i: emit((i + f) / count),
            )
        except (UserError, OSError) as exc:
            failure = exc
            break
        done.append(path)
        warnings.extend(result.warnings)
        total_tables += len(result.tables)
        if result.xlsx is not None:
            outputs.append(
                {
                    "path": str(result.xlsx),
                    "type": "xlsx",
                    "sheets": [
                        {
                            "name": t.name,
                            "pages": t.pages,
                            "rows": len(t.rows),
                            "columns": t.col_count,
                        }
                        for t in result.tables
                    ],
                }
            )
        outputs.extend({"path": str(p), "type": "csv"} for p in result.csv_files)

    if total_tables:
        files = sum(1 for o in outputs if o["type"] == "xlsx")
        summary = (
            f"Fant {total_tables} {'tabell' if total_tables == 1 else 'tabeller'} "
            f"og skrev {files} regneark."
        )
    else:
        summary = "Fant ingen tabeller. Ingen regneark ble skrevet."
    if failure is not None:
        remaining = args.inputs[len(done) :]
        warnings.append(
            f"Behandlingen stoppet ved «{Path(remaining[0]).name}»: {_message(failure)} "
            f"Rapporten viser bare de {len(done)} filene som ble fullført."
        )
        summary = f"Stoppet etter {len(done)} av {count} filer. {summary}"
    print_report(
        build_report(TOOL, __version__, done if failure else args.inputs, outputs, warnings, summary)
    )
    if failure is not None:
        print(f"Feil: {_message(failure)}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_main, argv)
