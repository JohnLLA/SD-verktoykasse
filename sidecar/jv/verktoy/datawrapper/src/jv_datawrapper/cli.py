"""Command line:

    jv datawrapper analyser <fil> [--json]
    jv datawrapper lag <fil> [--ark NAVN] [--tabell N] [--med-sum] [--bytt]
                             [--fjern-kolonne I ...] [--csv UT] [--json]

The report (JSON on stdout) is the contract with the app. `lag` puts the
cleaned table in the report as TSV (`datawrapper.tsv`). Nothing is logged:
stderr only carries progress lines and the Norwegian error message.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from jv_common import UserError, build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import analyse, make, write_csv

TOOL = "datawrapper"


def _build_parser() -> argparse.ArgumentParser:
    parser = make_parser(
        f"jv {TOOL}",
        "Klargjør en tabell fra Excel eller CSV for Datawrapper: én overskriftsrad, "
        "tall med punktum og uten tusenskille, tittel og kilde for seg.",
    )
    sub = parser.add_subparsers(dest="kommando", metavar="{analyser,lag}", required=True)
    analyser = sub.add_parser(
        "analyser",
        help="list ark og tabeller, med forslag for hver tabell",
        description="Lister synlige ark og tabellene i dem, med forslag til tabell, sumrader og bytte.",
    )
    lag = sub.add_parser(
        "lag",
        help="lag den rensede tabellen (TSV i rapporten, og eventuelt CSV)",
        description="Lager den rensede tabellen. TSV-en står i rapporten (datawrapper.tsv).",
    )
    for p in (analyser, lag):
        p.add_argument("input", metavar="fil", help=".xlsx, .xlsm, .xls, .csv eller .txt")
        p.add_argument("--json", action="store_true", help="rapport som JSON (alltid på)")
        p.add_argument("--debug", action="store_true", default=argparse.SUPPRESS, help="vis full feilsporing ved feil")
    lag.add_argument("--ark", metavar="NAVN", help="arket (standard: arket med flest tall)")
    lag.add_argument("--tabell", type=int, metavar="N", help="tabellnummer i arket, fra 1 (standard: den største)")
    lag.add_argument("--med-sum", action="store_true", help="ta med sumrader og sumkolonner")
    lag.add_argument("--bytt", action="store_true", help="bytt rader og kolonner")
    lag.add_argument(
        "--fjern-kolonne",
        type=int,
        action="extend",
        nargs="+",
        default=[],
        metavar="I",
        help="fjern kolonne nummer I (fra 1, etter de andre valgene)",
    )
    lag.add_argument("--csv", metavar="UT", help="lagre også som CSV (UTF-8, komma) i denne filen")
    return parser


def _run(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    path = Path(args.input)
    emit(0.05)
    if args.kommando == "analyser":
        data, warnings, summary = analyse(path, progress=lambda f: emit(0.05 + 0.9 * f))
        outputs: list = []
    else:
        data, warnings, summary = make(
            path,
            sheet_name=args.ark,
            table_no=args.tabell,
            with_sums=args.med_sum,
            transpose=args.bytt,
            remove_columns=tuple(args.fjern_kolonne),
            progress=lambda f: emit(0.05 + 0.85 * f),
        )
        outputs = []
        if args.csv:
            written = write_csv(path, Path(args.csv), data.pop("_rows"))
            outputs.append({"path": str(written), "type": "csv"})
            data["csv"] = str(written)
        else:
            data.pop("_rows")
    report = build_report(TOOL, __version__, [path], outputs, warnings, summary)
    report["datawrapper"] = data
    emit(1.0)
    print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)


__all__ = ["main", "UserError"]
