"""Regression: OCR must work without TMPDIR and with a symlinked TMPDIR."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from jv_common import skip_if_missing

from jv_ocr import core

from ocr_testhelpers import DATA, pdf_text

pytestmark = [skip_if_missing("tesseract"), skip_if_missing("gs")]


def _run(tmp_path: Path) -> Path:
    result = core.ocr_file(DATA / "skannet_side.pdf", tmp_path / "ut")
    assert result.ocr_pages == [1]
    assert any(t.strip() for t in pdf_text(result.output))
    return result.output


def _leftovers(base: Path) -> list[str]:
    return [p.name for p in base.iterdir() if p.name.startswith(("jv-ocr-", "ocrmypdf"))]


def test_ocr_without_tmpdir(tmp_path, monkeypatch):
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", None)
    _run(tmp_path)
    assert "TMPDIR" not in os.environ
    assert tempfile.tempdir is None


def test_ocr_with_symlinked_tmpdir(tmp_path, monkeypatch):
    real = tmp_path / "ekte"
    real.mkdir()
    link = tmp_path / "lenke"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("TMPDIR", str(link))
    monkeypatch.setattr(tempfile, "tempdir", None)
    _run(tmp_path)
    assert os.environ["TMPDIR"] == str(link)
    assert _leftovers(real) == []


def test_work_dir_removed_and_env_restored_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", None)
    seen = []
    try:
        with core._work_dir() as tmp:
            seen.append(tmp)
            assert tmp.is_dir()
            assert os.environ["TMPDIR"] == str(tmp)
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert not seen[0].exists()
    assert os.environ["TMPDIR"] == str(tmp_path)
