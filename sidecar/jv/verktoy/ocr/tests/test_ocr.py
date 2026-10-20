"""OCR end-to-end tests. Run sequentially; each OCR takes a few seconds."""

from __future__ import annotations

import shutil

import pytest
from jv_common import sha256_file, skip_if_missing

from jv_ocr import core

from ocr_testhelpers import DATA, line_angle, page_image, pdf_text, report_of, run_cli

pytestmark = [skip_if_missing("tesseract")]


def test_scanned_page_becomes_searchable_cli(tmp_path, capsys):
    src_dir = tmp_path / "inn; mappe"
    src_dir.mkdir()
    src = src_dir / "skannet side æøå.pdf"
    shutil.copy(DATA / "skannet_side.pdf", src)
    before = sha256_file(src)

    code, out, err = run_cli([src, "--out", tmp_path / "ut æ", "--text"], capsys)
    assert code == 0, err
    rep = report_of(out)
    assert rep["tool"] == "ocr"
    assert rep["inputs"][0]["sha256"] == before
    assert sha256_file(src) == before

    pdf_entry = next(o for o in rep["outputs"] if o["type"] == "pdf")
    txt_entry = next(o for o in rep["outputs"] if o["type"] == "txt")
    assert pdf_entry["pages"] == 1
    assert pdf_entry["ocr_pages"] == [1]
    assert pdf_entry["low_confidence_pages"] == []
    assert pdf_entry["confidence"]["1"] >= 60

    import pymupdf

    with pymupdf.open(pdf_entry["path"]) as doc:
        assert len(doc[0].search_for("Bergen kommune")) >= 2
        text = doc[0].get_text("text")
    for word in ("Særlige vilkår", "søknaden", "sjøen", "Høyden", "Åse Prøvesen"):
        assert word in text, word

    txt = open(txt_entry["path"], encoding="utf-8").read()
    assert "Bergen kommune" in txt and "Åse Prøvesen" in txt

    # progress lines on stderr are JSON
    import json

    progress = [json.loads(line)["progress"] for line in err.splitlines() if line.strip()]
    assert progress and progress[-1] == 1.0
    assert progress == sorted(progress)
    assert len(progress) == len(set(progress))  # no repeated lines


def test_skewed_page_is_straightened(tmp_path):
    src = DATA / "skjev_side.pdf"
    assert abs(line_angle(src)) > 2.0  # the test file really is skewed
    res = core.ocr_file(src, tmp_path, jobs=1)
    assert res.ocr_pages == [1]
    assert abs(line_angle(res.output)) < 0.5
    assert "Bergen kommune" in pdf_text(res.output)[0]


def test_mixed_pdf_skips_page_with_text(tmp_path, capsys):
    code, out, err = run_cli([DATA / "blandet.pdf", "--out", tmp_path], capsys)
    assert code == 0, err
    rep = report_of(out)
    entry = rep["outputs"][0]
    assert entry["pages"] == 2
    assert entry["ocr_pages"] == [2]
    assert entry["skipped_pages"] == [1]
    assert "2 sider, 1 fikk OCR" in rep["summary"]
    pages = pdf_text(entry["path"])
    assert "Ærlig, søt og åpen." in pages[0]
    assert "Bergen kommune" in pages[1]


def test_folder_of_images_gives_pdfs(tmp_path, capsys):
    folder = tmp_path / "bilder"
    folder.mkdir()
    page_image(None, "PNG", folder / "uten dpi.png")
    page_image(200, "JPEG", folder / "med_dpi.jpg")
    (folder / "notat.txt").write_text("ignoreres", encoding="utf-8")

    code, out, err = run_cli([folder, "--out", tmp_path / "ut"], capsys)
    assert code == 0, err
    rep = report_of(out)
    pdfs = [o for o in rep["outputs"] if o["type"] == "pdf"]
    assert len(pdfs) == 2
    assert len(rep["inputs"]) == 2
    for entry in pdfs:
        assert entry["path"].endswith("-ocr.pdf")
        assert entry["ocr_pages"] == [1]
        assert "Bergen kommune" in pdf_text(entry["path"])[0]
    dpi_warnings = [w for w in rep["warnings"] if "dpi" in w]
    assert len(dpi_warnings) == 1 and "uten dpi.png" in dpi_warnings[0]


def test_never_overwrites_existing_output(tmp_path):
    first = core.ocr_file(DATA / "blandet.pdf", tmp_path, jobs=1)
    second = core.ocr_file(DATA / "blandet.pdf", tmp_path, jobs=1)
    assert first.output != second.output
    assert second.output.name == "blandet-ocr-2.pdf"


def test_pdf_without_xref_is_repaired_with_warning(tmp_path, capsys):
    data = (DATA / "skannet_side.pdf").read_bytes()
    src = tmp_path / "uten trailer.pdf"
    src.write_bytes(data[:-200])  # xref table and trailer gone
    code, out, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    assert code == 0, err
    rep = report_of(out)
    assert any("ble reparert" in w for w in rep["warnings"])
    entry = rep["outputs"][0]
    assert entry["ocr_pages"] == [1]
    assert "Bergen kommune" in pdf_text(entry["path"])[0]
    assert "MuPDF" not in err
