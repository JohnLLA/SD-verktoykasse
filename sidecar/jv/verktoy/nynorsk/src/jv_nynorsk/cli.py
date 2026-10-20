"""Command line: jv nynorsk <inngang...> --to nn|nb --out <mappe>."""

from __future__ import annotations

from collections.abc import Sequence

from jv_common import build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import MARK_TYPES_NO, TARGET_NAMES, translate_files

TOOL = "nynorsk"
DRAFT_WARNING = (
    "UTKAST: teksten er maskinomsatt med Apertium og må leses og rettes av "
    "et menneske før den brukes."
)


def _build_parser():
    parser = make_parser(
        "jv nynorsk",
        "Lag et førsteutkast på den andre målformen (bokmål ↔ nynorsk) med "
        "Apertium. Ord Apertium ikke kjenner, merkes [?ord] i utfilen og "
        "listes i rapporten. Originalfilen endres aldri.",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="inngang",
        help="tekstfil(er) å oversette: .txt, .md eller .docx",
    )
    parser.add_argument(
        "--to",
        required=True,
        choices=["nn", "nb"],
        help="målform: nn (bokmål → nynorsk) eller nb (nynorsk → bokmål)",
    )
    parser.add_argument(
        "--out", required=True, metavar="mappe", help="mappe for utfilene"
    )
    return parser


def _run(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    emit(0.0)
    results = translate_files(args.to, args.inputs, args.out, progress=emit)
    emit(1.0)

    outputs = []
    warnings = [DRAFT_WARNING]
    total_marks = 0
    for res in results:
        unknown = res.unknown_words()
        total_marks += len(res.marks)
        outputs.append(
            {
                "path": str(res.output),
                "input": str(res.input),
                "direction": res.mode,
                "draft": True,
                "paragraphs": res.paragraphs,
                "unknown_words": unknown,
            }
        )
        warnings.extend(f"{res.input.name}: {w}" for w in res.warnings)
        if unknown:
            listed = ", ".join(
                f"«{u['word']}» ({MARK_TYPES_NO[u['type']]})" for u in unknown
            )
            warnings.append(
                f"{res.input.name}: {len(unknown)} ord må sjekkes (merket [?ord]): {listed}"
            )

    target = TARGET_NAMES[args.to]
    files = "1 fil" if len(results) == 1 else f"{len(results)} filer"
    summary = (
        f"Utkast: {files} oversatt til {target} med Apertium. "
        f"{total_marks} forekomster av ukjente eller usikre ord er merket [?ord] "
        "og må sjekkes. Teksten må leses korrektur før bruk."
    )
    report = build_report(
        TOOL,
        __version__,
        inputs=[r.input for r in results],
        outputs=outputs,
        warnings=warnings,
        summary=summary,
    )
    print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)
