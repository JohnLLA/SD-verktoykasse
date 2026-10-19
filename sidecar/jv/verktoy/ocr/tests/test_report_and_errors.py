"""Fast tests: report details, bad input and missing programs (no OCR run)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from jv_common import skip_if_missing

from jv_ocr import cli, core

from ocr_testhelpers import DATA, page_image, report_of, run_cli


def _assert_user_error(code, err, needle):
    assert code == 1
    assert "Traceback" not in err
    lines = [ln for ln in err.splitlines() if not ln.startswith('{"progress"')]
    assert lines and lines[0].startswith("Feil: "), err
    assert needle in err


def test_missing_file(tmp_path, capsys):
    code, _, err = run_cli([tmp_path / "finnes ikke.pdf", "--out", tmp_path], capsys)
    _assert_user_error(code, err, "Finner ikke")


def test_empty_file(tmp_path, capsys):
    empty = tmp_path / "tom.pdf"
    empty.write_bytes(b"")
    code, _, err = run_cli([empty, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "er tom")


def test_wrong_format(tmp_path, capsys):
    doc = tmp_path / "notat.docx"
    doc.write_bytes(b"PK\x03\x04 ikke relevant")
    code, _, err = run_cli([doc, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "ikke støttes")


def test_fake_pdf(tmp_path, capsys):
    fake = tmp_path / "falsk.pdf"
    fake.write_text("dette er ikke en pdf", encoding="utf-8")
    code, _, err = run_cli([fake, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "ikke en gyldig PDF")


def test_fake_image(tmp_path, capsys):
    fake = tmp_path / "bilde.png"
    fake.write_text("ikke et bilde", encoding="utf-8")
    code, _, err = run_cli([fake, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "ikke et gyldig bilde")


def test_empty_folder(tmp_path, capsys):
    folder = tmp_path / "tom mappe"
    folder.mkdir()
    code, _, err = run_cli([folder, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "ingen PDF- eller bildefiler")


def test_missing_out_argument(capsys):
    code, _, err = run_cli([DATA / "skannet_side.pdf"], capsys)
    _assert_user_error(code, err, "Ugyldige argumenter")


@skip_if_missing("tesseract")
def test_ghostscript_is_not_required(monkeypatch):
    import shutil

    real = shutil.which
    monkeypatch.delenv("JV_GS", raising=False)
    monkeypatch.setattr(shutil, "which", lambda n, *a, **k: None if n == "gs" else real(n))
    core.check_dependencies()  # no UserError: ocrmypdf writes plain PDF without Ghostscript


def test_missing_tesseract(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda n, *a, **k: None)
    with pytest.raises(core.UserError, match="brew install tesseract"):
        core.check_dependencies()


def test_missing_norwegian(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda n, *a, **k: f"/usr/bin/{n}")

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="List of languages:\neng\nosd\n", stderr="")

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    with pytest.raises(core.UserError, match="«nor».*brew install tesseract-lang"):
        core.check_dependencies()


def test_low_confidence_is_warned(tmp_path, monkeypatch, capsys):
    src = tmp_path / "skann.pdf"
    src.write_bytes((DATA / "blandet.pdf").read_bytes())

    def fake_many(files, out_dir, **kwargs):
        return [
            core.FileResult(
                source=files[0],
                output=Path(out_dir) / "skann-ocr.pdf",
                text_output=None,
                pages=[
                    core.PageResult(1, ocr=False),
                    core.PageResult(2, ocr=True, confidence=42.4, words=10),
                    core.PageResult(3, ocr=True, confidence=88.0, words=50),
                    core.PageResult(4, ocr=True, confidence=None, words=0),
                ],
            )
        ]

    monkeypatch.setattr(cli, "ocr_many", fake_many)
    monkeypatch.setattr(cli, "check_dependencies", lambda: None)
    code, out, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    assert code == 0, err
    rep = report_of(out)
    entry = rep["outputs"][0]
    assert entry["ocr_pages"] == [2, 3, 4]
    assert entry["low_confidence_pages"] == [2, 4]
    assert any("side 2" in w and "42" in w for w in rep["warnings"])
    assert any("side 4" in w and "ingen ord" in w for w in rep["warnings"])
    assert not any("side 3" in w for w in rep["warnings"])
    assert "2 side(r) har lav sikkerhet" in rep["summary"]


def test_ocrmypdf_error_becomes_norwegian(tmp_path, monkeypatch):
    from ocrmypdf import exceptions as ocr_exc

    def boom(*args, **kwargs):
        raise ocr_exc.EncryptedPdfError()

    import ocrmypdf

    monkeypatch.setattr(ocrmypdf, "ocr", boom)
    monkeypatch.setattr(core, "_pages_with_text", lambda p: [False])
    with pytest.raises(core.UserError, match="kryptert"):
        core.ocr_file(DATA / "skannet_side.pdf", tmp_path)


def _no_pdf_outputs(folder):
    return not folder.exists() or not any(folder.glob("*.pdf"))


def test_garbage_pdf(tmp_path, capsys):
    bad = tmp_path / "søppel fil.pdf"
    bad.write_bytes(b"%PDF-1.7\n" + "søppel søppel".encode() + b"\x00\x01\x02")
    out = tmp_path / "ut"
    code, stdout, err = run_cli([bad, "--out", out], capsys)
    _assert_user_error(code, err, "skadet eller avkuttet")
    assert stdout == ""
    assert _no_pdf_outputs(out)


@skip_if_missing("tesseract")
@pytest.mark.parametrize("size", [20000, 60000])
def test_truncated_pdf(tmp_path, capsys, size):
    bad = tmp_path / "avkuttet.pdf"
    bad.write_bytes((DATA / "skannet_side.pdf").read_bytes()[:size])
    out = tmp_path / "ut"
    code, stdout, err = run_cli([bad, "--out", out], capsys)
    _assert_user_error(code, err, "skadet eller avkuttet")
    assert stdout == ""
    assert _no_pdf_outputs(out)


def test_pikepdf_error_inside_ocrmypdf_is_user_error(tmp_path, monkeypatch):
    import ocrmypdf
    import pikepdf

    def boom(*args, **kwargs):
        raise pikepdf.PdfError("unable to find /Root dictionary")

    monkeypatch.setattr(ocrmypdf, "ocr", boom)
    monkeypatch.setattr(core, "_pages_with_text", lambda p: [False])
    with pytest.raises(core.UserError, match="skadet eller avkuttet"):
        core.ocr_file(DATA / "skannet_side.pdf", tmp_path)
    assert not any(tmp_path.glob("*.pdf"))


@pytest.mark.parametrize("fmt,ext", [("TIFF", "tif"), ("PNG", "png"), ("JPEG", "jpg")])
def test_truncated_image(tmp_path, capsys, fmt, ext):
    full = page_image(200, fmt, tmp_path / f"hel.{ext}")
    data = full.read_bytes()
    bad = tmp_path / f"avkuttet æ.{ext}"
    bad.write_bytes(data[: len(data) // 2])
    out = tmp_path / "ut"
    code, stdout, err = run_cli([bad, "--out", out], capsys)
    _assert_user_error(code, err, "skadet eller avkuttet")
    assert "Warning" not in err  # no PIL warnings leak to the user
    assert stdout == ""
    assert _no_pdf_outputs(out)


def test_all_files_validated_before_ocr(tmp_path, capsys, monkeypatch):
    good = tmp_path / "a god.pdf"
    good.write_bytes((DATA / "skannet_side.pdf").read_bytes())
    full = page_image(200, "TIFF", tmp_path / "hel.tif").read_bytes()
    bad = tmp_path / "b avkuttet.tif"
    bad.write_bytes(full[: len(full) // 2])

    called = []
    monkeypatch.setattr(cli, "ocr_many", lambda *a, **k: called.append(1) or [])
    code, stdout, err = run_cli([good, bad, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "b avkuttet.tif")
    assert called == []


def test_oserror_inside_ocrmypdf_is_user_error(tmp_path, monkeypatch):
    import ocrmypdf

    def boom(*args, **kwargs):
        raise OSError("image file is truncated (2385 bytes not processed)")

    monkeypatch.setattr(ocrmypdf, "ocr", boom)
    img = page_image(200, "PNG", tmp_path / "side.png")
    with pytest.raises(core.UserError, match="skadet eller avkuttet"):
        core.ocr_file(img, tmp_path / "ut")
    assert not any((tmp_path / "ut").glob("*.pdf"))


def test_later_failure_names_finished_files(tmp_path, monkeypatch):
    done = core.FileResult(
        source=tmp_path / "a.pdf", output=tmp_path / "a-ocr.pdf", text_output=None, pages=[]
    )
    calls = []

    def fake_ocr_file(src, out_dir, **kwargs):
        calls.append(src)
        if len(calls) == 1:
            return done
        raise core.UserError("«b.pdf» er skadet eller avkuttet.")

    monkeypatch.setattr(core, "ocr_file", fake_ocr_file)
    with pytest.raises(core.UserError, match="ble ferdige.*a-ocr.pdf"):
        core.ocr_many([tmp_path / "a.pdf", tmp_path / "b.pdf"], tmp_path)
