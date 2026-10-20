"""CLI: jv ocr <inngang...> --out <mappe> [--text]"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from jv_common import build_report, emit, make_parser, print_report, run_cli

from . import __version__
from .core import LOW_CONFIDENCE, check_dependencies, collect_inputs, ocr_many

TOOL = "ocr"


def _parser():
    parser = make_parser(
        "jv ocr",
        "Gjør skannede PDF-er og bilder (JPEG, PNG, TIFF) søkbare med OCR "
        "(norsk og engelsk). Sider som har tekst fra før, hoppes over. "
        "Skjeve og snudde sider rettes opp.",
    )
    parser.add_argument(
        "inputs", nargs="+", metavar="inngang", help="PDF, bilde eller mappe"
    )
    parser.add_argument(
        "--out", required=True, metavar="mappe", help="mappe for nye filer"
    )
    parser.add_argument(
        "--text", action="store_true", help="lag også en .txt-fil med all teksten"
    )
    return parser


def _fmt(value: float) -> str:
    return f"{value:.0f}"


def _run(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    files = collect_inputs(args.inputs)
    check_dependencies()
    out_dir = Path(args.out)

    last: list[float] = []

    def progress(fraction: float) -> None:
        value = round(fraction, 4)
        if last and value <= last[0]:
            return  # no repeated or backwards lines
        last[:] = [value]
        emit(value)

    progress(0.0)
    results = ocr_many(files, out_dir, text=args.text, progress=progress)

    outputs: list[dict] = []
    warnings: list[str] = []
    pages_total = 0
    ocr_total = 0
    for res in results:
        pages_total += res.page_count
        ocr_total += len(res.ocr_pages)
        low = res.low_confidence
        outputs.append(
            {
                "path": str(res.output),
                "type": "pdf",
                "source": str(res.source),
                "pages": res.page_count,
                "ocr_pages": res.ocr_pages,
                "skipped_pages": [p.number for p in res.pages if not p.ocr],
                "confidence": {
                    str(p.number): (
                        None if p.confidence is None else round(p.confidence, 1)
                    )
                    for p in res.pages
                    if p.ocr
                },
                "low_confidence_pages": [p.number for p in low],
            }
        )
        if res.text_output is not None:
            outputs.append(
                {"path": str(res.text_output), "type": "txt", "source": str(res.source)}
            )
        if res.repaired:
            warnings.append(
                f"{res.source.name}: PDF-en var skadet (for eksempel uten "
                "kryssreferansetabell) og ble reparert før OCR. Kontroller at "
                "alle sider og hele innholdet er med."
            )
        if res.image_dpi_assumed:
            warnings.append(
                f"{res.source.name}: bildet oppgir ingen oppløsning, så "
                f"{res.image_dpi_assumed} dpi er brukt. Sidestørrelsen i PDF-en "
                "kan derfor avvike fra originalen."
            )
        for page in low:
            if page.confidence is None:
                warnings.append(
                    f"{res.source.name} side {page.number}: OCR fant ingen ord."
                )
            else:
                warnings.append(
                    f"{res.source.name} side {page.number}: lav sikkerhet i OCR "
                    f"(gjennomsnittlig ordsikkerhet {_fmt(page.confidence)}, "
                    f"under {_fmt(LOW_CONFIDENCE)}). Kontroller teksten."
                )

    n_low = sum(len(r.low_confidence) for r in results)
    files_word = "fil" if len(results) == 1 else "filer"
    summary = (
        f"{len(results)} {files_word} behandlet: {pages_total} sider, "
        f"{ocr_total} fikk OCR og {pages_total - ocr_total} hadde tekst fra før."
    )
    if n_low:
        summary += f" {n_low} side(r) har lav sikkerhet."
    report = build_report(
        TOOL,
        __version__,
        inputs=files,
        outputs=outputs,
        warnings=warnings,
        summary=summary,
    )
    print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_run, argv)
