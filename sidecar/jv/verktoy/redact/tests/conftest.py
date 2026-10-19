import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "testdata" / "redact"

# make redact_helpers importable (tests run with --import-mode=importlib)
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def pdf_path() -> Path:
    return DATA / "personopplysninger.pdf"


@pytest.fixture
def terms_path() -> Path:
    return DATA / "termer.txt"


@pytest.fixture
def fasit() -> list[dict]:
    return json.loads((DATA / "personopplysninger_fasit.json").read_text(encoding="utf-8"))["items"]


@pytest.fixture
def scanned_pdf() -> Path:
    return ROOT / "testdata" / "ocr" / "skannet_side.pdf"


@pytest.fixture
def work(tmp_path, pdf_path, terms_path):
    """Copies of the test files in a folder with spaces and æøå in the name."""
    d = tmp_path / "sak med æøå; test"
    d.mkdir()
    pdf = d / "personopplysninger æøå.pdf"
    terms = d / "termer.txt"
    shutil.copy(pdf_path, pdf)
    shutil.copy(terms_path, terms)
    return {"dir": d, "pdf": pdf, "terms": terms, "out": tmp_path / "ut mappe"}
