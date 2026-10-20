"""Command line for compare: two files in, one HTML report and a JSON report out."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from jv_common import (
    UserError,
    build_report,
    make_parser,
    print_report,
    run_cli,
    safe_output_path,
)

from . import __version__
from .core import Options, compare_files, render_html, summary_text

TOOL = "compare"


def build_parser() -> argparse.ArgumentParser:
    parser = make_parser(
        f"jv {TOOL}",
        "Viser hva som er endret mellom to versjoner av et dokument "
        "(.txt, .md, .docx eller .pdf med tekstlag). Lager én selvstendig "
        "HTML-rapport med to kolonner.",
    )
    parser.add_argument("gammel", help="den gamle versjonen")
    parser.add_argument("ny", help="den nye versjonen")
    parser.add_argument(
        "--out", required=True, help="mappe der HTML-rapporten skal lagres"
    )
    parser.add_argument(
        "--ignore-whitespace",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="se bort fra forskjeller i mellomrom og linjeskift (standard: på; "
        "slå av med --no-ignore-whitespace)",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="regn store og små bokstaver som like",
    )
    return parser


def _run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    old_path, new_path = Path(args.gammel), Path(args.ny)
    opts = Options(
        ignore_whitespace=args.ignore_whitespace, ignore_case=args.ignore_case
    )
    comparison = compare_files(old_path, new_path, opts)
    out_path = safe_output_path(old_path, args.out, f"-mot-{new_path.stem}.html")
    for src in (old_path, new_path):
        if out_path.resolve() == src.resolve():
            raise UserError("Rapporten ville overskrevet en av inngangsfilene.")
    try:
        out_path.write_text(render_html(comparison), encoding="utf-8")
    except OSError as exc:
        raise UserError(f"Kunne ikke skrive rapporten til «{out_path}»: {exc}") from exc

    report = build_report(
        TOOL,
        __version__,
        inputs=[old_path, new_path],
        outputs=[
            {
                "path": str(out_path),
                "format": "html",
                "changed_paragraphs": comparison.total_changed,
                "paragraphs_changed": comparison.changed_paragraphs,
                "paragraphs_deleted": comparison.deleted_paragraphs,
                "paragraphs_inserted": comparison.inserted_paragraphs,
                "words_added": comparison.words_added,
                "words_removed": comparison.words_removed,
                "moved_sentences": len(comparison.moved),
            }
        ],
        warnings=comparison.warnings,
        summary=summary_text(comparison),
    )
    print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)
