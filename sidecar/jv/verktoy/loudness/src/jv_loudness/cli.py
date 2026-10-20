"""CLI: jv loudness <inngang...> --out <mappe> [--target podcast|broadcast | --lufs X]."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from jv_common import (
    build_report,
    emit,
    make_parser,
    print_report,
    require_binary,
    run_cli,
)

from . import __version__
from .core import TARGETS, check_input, normalize, resolve_target

TOOL = "loudness"


def _parser():
    parser = make_parser(
        prog="jv loudness",
        description=(
            "Setter lydnivået til standard med ffmpeg loudnorm i to pass. "
            "Originalen røres ikke; resultatet skrives som en ny fil i samme format."
        ),
    )
    parser.add_argument("inputs", nargs="+", metavar="inngang",
                        help="lyd (WAV, MP3, M4A, FLAC) eller video (MP4, MOV, M4V, MKV)")
    parser.add_argument("--out", required=True, metavar="mappe",
                        help="mappe for de normaliserte filene")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--target", choices=sorted(TARGETS), default=None,
                       help="podcast: −16 LUFS, −1 dBTP (standard). "
                            "broadcast: −23 LUFS, −1 dBTP (EBU R128)")
    group.add_argument("--lufs", type=float, default=None, metavar="LUFS",
                       help="egendefinert mål for integrert loudness, f.eks. -19 "
                            "(true peak er alltid −1 dBTP)")
    return parser


def _fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "ukjent"
    return f"{value:.1f}".replace("-", "−").replace(".", ",") + f" {unit}"


def _run(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    lufs, tp, label = resolve_target(args.target, args.lufs)
    require_binary("ffmpeg")
    require_binary("ffprobe")

    paths = [Path(p) for p in args.inputs]
    for path in paths:  # fail early, before any file is written
        check_input(path)

    outputs: list[dict] = []
    warnings: list[str] = []
    total = len(paths)
    emit(0.0)
    for n, path in enumerate(paths):
        result = normalize(
            path, args.out, lufs, tp,
            progress=lambda f, n=n: emit((n + f) / total),
        )
        outputs.append(result["entry"])
        warnings.extend(result["warnings"])

    parts = [
        f"{Path(o['source']).name}: {_fmt(o['before']['integrated_lufs'], 'LUFS')} → "
        f"{_fmt(o['after']['integrated_lufs'], 'LUFS')} "
        f"(true peak {_fmt(o['after']['true_peak_dbtp'], 'dBTP')})"
        for o in outputs
    ]
    target_text = f"{_fmt(lufs, 'LUFS')} og {_fmt(tp, 'dBTP')} ({label})"
    noun = "fil" if total == 1 else "filer"
    summary = f"Normaliserte {total} {noun} til {target_text}. " + "; ".join(parts) + "."
    report = build_report(
        tool=TOOL,
        version=__version__,
        inputs=paths,
        outputs=outputs,
        warnings=warnings,
        summary=summary,
    )
    print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)
