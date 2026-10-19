"""Command line for `jv keyframes`."""

from __future__ import annotations

from collections.abc import Sequence

from jv_common import build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import extract, format_timecode, parse_interval, parse_threshold

TOOL = "keyframes"


def _parser():
    parser = make_parser(
        f"jv {TOOL}",
        "Trekker ut stillbilder fra video med tidskode i filnavnet, pluss et "
        "kontaktark med alle bildene. Rotasjonsmetadata respekteres, så stående "
        "mobilvideo gir stående bilder.",
    )
    parser.add_argument("inputs", nargs="+", metavar="VIDEO", help="videofil(er): MP4, MOV, MKV og alt ffmpeg leser")
    parser.add_argument("--out", required=True, metavar="MAPPE", help="mappe for bildene og kontaktarket")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--every", metavar="INTERVALL", help="ett bilde med fast intervall, for eksempel «2s»")
    mode.add_argument("--scenes", metavar="TERSKEL", help="ett bilde ved hvert klipp, terskel 0–1, for eksempel «0.3»")
    return parser


def _run(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    every = parse_interval(args.every) if args.every is not None else None
    scenes = parse_threshold(args.scenes) if args.scenes is not None else None

    total = len(args.inputs)
    results = []
    for index, path in enumerate(args.inputs):
        def progress(fraction: float, index: int = index) -> None:
            emit((index + fraction) / total)

        results.append(extract(path, args.out, every=every, scenes=scenes, progress=progress))

    outputs = []
    warnings = []
    for res in results:
        outputs.extend(
            {"path": str(f.path), "type": "bilde", "time": round(f.time, 3), "timecode": format_timecode(f.time)}
            for f in res.frames
        )
        outputs.append({"path": str(res.contact_sheet), "type": "kontaktark", "frames": len(res.frames)})
        warnings.extend(res.warnings)
        if res.info.fps is None:
            warnings.append(f"{res.input.name}: klarte ikke å lese bildefrekvensen.")

    n_frames = sum(len(r.frames) for r in results)
    mode = f"hvert {every:g}. sekund" if every is not None else f"ved klipp (terskel {scenes:g})"
    videos = "1 video" if total == 1 else f"{total} videoer"
    summary = f"Trakk ut {n_frames} bilder fra {videos} {mode}, og laget kontaktark."

    report = build_report(TOOL, __version__, [r.input for r in results], outputs, warnings, summary)
    report["videos"] = [r.info_dict() for r in results]
    print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)
