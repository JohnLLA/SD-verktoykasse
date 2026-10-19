"""Command line: jv metadata vis <fil...> | jv metadata vask <fil...> --out <mappe>."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from jv_common import UserError, build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import clean_file, collect_inputs, read_metadata

TOOL = "metadata"


def _files(n: int) -> str:
    return "1 fil" if n == 1 else f"{n} filer"


def _build_parser() -> argparse.ArgumentParser:
    parser = make_parser(
        "jv metadata",
        "Vis skjult metadata i bilder, PDF og Office-filer, eller lag vaskede kopier.",
    )
    sub = parser.add_subparsers(dest="kommando", metavar="{vis,vask}", required=True)

    vis = sub.add_parser(
        "vis",
        help="vis metadata gruppert i Sted, Person, Utstyr, Tid og Annet",
        description="Vis metadata. GPS- og personfelt merkes som følsomme.",
    )
    vask = sub.add_parser(
        "vask",
        help="lag en kopi uten metadata og kontroller resultatet",
        description=(
            "Lag en vasket kopi av hver fil i utmappen. Originalen røres ikke. "
            "Den vaskede filen leses på nytt for å bekrefte at følsomme felt er borte."
        ),
    )
    for p in (vis, vask):
        p.add_argument(
            "inputs",
            nargs="+",
            metavar="fil",
            help="JPEG, PNG, HEIC, PDF, DOCX, XLSX eller PPTX, eller en mappe",
        )
        p.add_argument(
            "--debug",
            action="store_true",
            default=argparse.SUPPRESS,
            help="vis full feilsporing ved feil",
        )
    vask.add_argument("--out", required=True, metavar="mappe", help="mappe for de vaskede kopiene")
    return parser


def _run(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    files, warnings = collect_inputs(args.inputs)
    out_dir = Path(args.out) if args.kommando == "vask" else None

    outputs = []
    failed = 0
    many = len(files) > 1
    for i, path in enumerate(files):
        try:
            if out_dir is None:
                result, notes = read_metadata(path)
            else:
                result, notes = clean_file(path, out_dir)
        except UserError as exc:
            if not many:
                raise
            failed += 1
            warnings.append(str(exc))
        else:
            outputs.append(result)
            warnings.extend(notes)
        if many:
            emit((i + 1) / len(files))

    done = [f for f in files if str(f) in {o.get("source", o["path"]) for o in outputs}]
    if out_dir is None:
        total = sum(o["field_count"] for o in outputs)
        sensitive = sum(o["sensitive_count"] for o in outputs)
        summary = (
            f"Leste metadata fra {_files(len(outputs))}: {total} felt, "
            f"{sensitive} følsomme (sted eller person)."
        )
    else:
        left = [o for o in outputs if not o["verified"]]
        summary = f"Lagde vasket kopi av {_files(len(outputs))}. " + (
            "Kontrollen fant ingen følsomme felt igjen."
            if not left
            else f"{_files(len(left))} har fortsatt felt igjen, se advarslene."
        )
    if failed:
        summary += f" {_files(failed)} kunne ikke behandles."

    print_report(
        build_report(TOOL, __version__, inputs=done, outputs=outputs, warnings=warnings, summary=summary)
    )
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)
