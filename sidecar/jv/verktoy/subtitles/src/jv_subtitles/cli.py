"""CLI: jv subtitles <transkripsjon.json...> --out <mappe> [regler]."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from jv_common import UserError, build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import Rules, convert, load_transcript

TOOL = "subtitles"
MAX_SECONDS = 86_400.0


def _parser():
    parser = make_parser(
        prog="jv subtitles",
        description=(
            "Gjør en Whisper-transkripsjon (JSON med tidskoder) om til undertekster "
            "i SRT og VTT. Ordtidskoder brukes til delingen når de finnes. "
            "Originalen røres ikke."
        ),
    )
    parser.add_argument("inputs", nargs="+", metavar="inngang",
                        help="Whisper-JSON med segmenter (start, end, text, eventuelt words)")
    parser.add_argument("--out", required=True, metavar="mappe",
                        help="mappe for .srt- og .vtt-filene")
    parser.add_argument("--max-chars", type=int, default=42, metavar="N",
                        help="høyst så mange tegn per linje (standard 42)")
    parser.add_argument("--max-lines", type=int, default=2, metavar="N",
                        help="høyst så mange linjer per tekst (standard 2)")
    parser.add_argument("--min-duration", type=float, default=1.0, metavar="SEK",
                        help="minste visningstid i sekunder (standard 1)")
    parser.add_argument("--max-duration", type=float, default=7.0, metavar="SEK",
                        help="lengste visningstid i sekunder (standard 7)")
    parser.add_argument("--gap", type=float, default=0.08, metavar="SEK",
                        help="minste mellomrom mellom tekster i sekunder (standard 0,08 = 2 bilder)")
    return parser


def _run(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    for flag, value in (("--min-duration", args.min_duration),
                        ("--max-duration", args.max_duration),
                        ("--gap", args.gap)):
        if not math.isfinite(value) or value < 0 or value > MAX_SECONDS:
            raise UserError(
                f"{flag} må være et vanlig tall mellom 0 og {MAX_SECONDS:g} sekunder."
            )
    rules = Rules(
        max_chars=args.max_chars,
        max_lines=args.max_lines,
        min_ms=round(args.min_duration * 1000),
        max_ms=round(args.max_duration * 1000),
        gap_ms=round(args.gap * 1000),
    )
    rules.check()

    paths = [Path(p) for p in args.inputs]
    for path in paths:  # fail early, before any file is written
        load_transcript(path)

    outputs: list[dict] = []
    warnings: list[str] = []
    parts: list[str] = []
    violations = 0
    total = len(paths)
    if total > 1:
        emit(0.0)
    for n, path in enumerate(paths, start=1):
        result = convert(path, args.out, rules)
        outputs.extend(result["outputs"])
        warnings.extend(result["warnings"])
        violations += result["violations"]
        how = "ordtidskoder" if result["word_timestamps"] else "tegnfordeling"
        parts.append(f"{path.name}: {result['cues']} tekster fra {result['segments']} segmenter ({how})")
        if total > 1:
            emit(n / total)

    status = (
        "Alle tekstene følger reglene."
        if violations == 0
        else f"{violations} regelbrudd, se advarslene."
    )
    summary = "Lagde SRT og VTT. " + "; ".join(parts) + ". " + status
    print_report(build_report(
        tool=TOOL,
        version=__version__,
        inputs=paths,
        outputs=outputs,
        warnings=warnings,
        summary=summary,
    ))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)
