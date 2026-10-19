"""jv redact: finn and sladd."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf

from jv_common import UserError, build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import (
    NO_HITS,
    NOTHING_MARKED,
    REJECT_LEFT,
    REJECT_SUMMARY,
    count_by_type,
    find_to_plan,
    redact_with_plan,
)

TOOL = "redact"


def _parser():
    parser = make_parser(
        "jv redact",
        "Ekte sladding av PDF: «finn» lager en plan med treff (fødselsnummer, "
        "D-nummer, telefon, e-post og egne termer), «sladd» fjerner dem fra filen.",
    )
    sub = parser.add_subparsers(dest="kommando", metavar="{finn,sladd}")

    finn = sub.add_parser(
        "finn",
        help="finn personopplysninger og lag en plan (JSON) du kan gå gjennom",
        description="Finn personopplysninger i en PDF og skriv en plan (JSON).",
    )
    finn.add_argument("pdf", help="PDF-fil med tekstlag")
    finn.add_argument("--out", help="mappe for planfilen")
    finn.add_argument(
        "--terms", help="tekstfil med egne ord og navn som skal sladdes, ett per linje"
    )
    finn.add_argument("--debug", action="store_true", help="vis full feilsporing ved feil")

    sladd = sub.add_parser(
        "sladd",
        help="sladd PDF-en etter en plan fra «finn»",
        description="Sladd treffene i planen. Filen leveres bare hvis etterkontrollen er ren.",
    )
    sladd.add_argument("pdf", help="den samme PDF-en som planen ble laget for")
    sladd.add_argument("--plan", help="planfilen (JSON) fra «jv redact finn»")
    sladd.add_argument("--out", help="mappe for den sladdede PDF-en")
    sladd.add_argument("--debug", action="store_true", help="vis full feilsporing ved feil")
    return parser


def _run(argv: list[str]) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.kommando is None:
        raise UserError("Velg «finn» eller «sladd». Se «jv redact --help».")
    if not args.out:
        raise UserError("Oppgi utmappe med --out <mappe>.")
    pdf = Path(args.pdf)
    out = Path(args.out)

    if args.kommando == "finn":
        terms = Path(args.terms) if args.terms else None
        res = find_to_plan(pdf, out, terms, progress=emit)
        inputs = [pdf] + ([terms] if terms else [])
        real = [h for h in res.hits if not h.rejected]
        rejected = [h for h in res.hits if h.rejected]
        summary = f"Fant {len(real)} treff ({count_by_type(real)})." if real else NO_HITS
        if rejected:
            summary += " " + REJECT_SUMMARY.format(n=len(rejected))
        summary += (
            f" Gå gjennom «{res.plan_path.name}», stryk treff som skal stå, og kjør "
            f"«jv redact sladd {pdf.name} --plan {res.plan_path.name} --out <mappe>»."
        )
        report = build_report(
            TOOL,
            __version__,
            inputs,
            outputs=[{"path": str(res.plan_path), "treff": len(real), "forkastet": len(rejected)}],
            warnings=res.warnings,
            summary=summary,
        )
        print_report(report)
        return 0

    if not args.plan:
        raise UserError(
            "«sladd» krever en plan: --plan <fil>.json. Lag den først med "
            f"«jv redact finn {pdf.name} --out <mappe>»."
        )
    plan = Path(args.plan)
    res = redact_with_plan(pdf, plan, out, progress=emit)
    if res.redacted:
        summary = (
            f"Sladdet {len(res.redacted)} treff ({count_by_type(res.redacted)}). "
            "Etterkontrollen fant ingen av de sladdede verdiene igjen."
        )
    else:
        summary = (
            NOTHING_MARKED + " Utfilen er en vasket kopi (metadata, bokmerker, lenker "
            "og lignende er fjernet), men ingen tekst er sladdet."
        )
    if res.left_rejected:
        summary += " " + REJECT_LEFT.format(n=len(res.left_rejected))
    report = build_report(
        TOOL,
        __version__,
        [pdf, plan],
        outputs=[{"path": str(res.output_path), "sladdet": len(res.redacted)}],
        warnings=res.warnings,
        summary=summary,
    )
    print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    # MuPDF's own (English) warnings and errors are not shown to the user;
    # problems surface as Norwegian messages instead
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    return run_cli(_run, argv)
