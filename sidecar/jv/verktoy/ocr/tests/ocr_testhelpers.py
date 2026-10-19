"""Shared helpers for the ocr tests."""

from __future__ import annotations

import io
import json
import math
import statistics
from pathlib import Path

from jv_ocr import core

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "testdata" / "ocr"


def run_cli(argv, capsys):
    from jv_ocr.cli import main

    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def report_of(out: str) -> dict:
    return json.loads(out)


def line_angle(pdf: Path, index: int = 0) -> float:
    """Median text-line angle in degrees, measured with tesseract on the image."""
    rows = core.tesseract_tsv(core.render_page_png(pdf, index, 150))
    lines: dict[tuple, list] = {}
    for r in rows:
        lines.setdefault((r["block_num"], r["par_num"], r["line_num"]), []).append(r)
    angles = []
    for words in lines.values():
        if len(words) < 4:
            continue
        first, last = words[0], words[-1]

        def cx(w):
            return int(w["left"]) + int(w["width"]) / 2

        def cy(w):
            return int(w["top"]) + int(w["height"]) / 2

        angles.append(math.degrees(math.atan2(cy(last) - cy(first), cx(last) - cx(first))))
    assert angles, "fant ingen tekstlinjer å måle"
    return statistics.median(angles)


def page_image(dpi_meta: int | None, fmt: str, path: Path) -> Path:
    """Write the scanned test page as an image file (with or without DPI)."""
    import pymupdf
    from PIL import Image

    with pymupdf.open(DATA / "skannet_side.pdf") as doc:
        pix = doc[0].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        img.load()
    kwargs = {}
    if dpi_meta:
        kwargs["dpi"] = (dpi_meta, dpi_meta)
    img.save(path, format=fmt, **kwargs)
    return path


def pdf_text(pdf: Path) -> list[str]:
    import pymupdf

    with pymupdf.open(pdf) as doc:
        return [page.get_text("text") for page in doc]
