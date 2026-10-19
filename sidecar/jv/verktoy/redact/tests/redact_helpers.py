import json
import re
import shutil
import subprocess
import unicodedata

import pymupdf

from jv_redact.cli import main


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    cap = capsys.readouterr()
    report = None
    if code == 0:
        report = json.loads(cap.out)
    return code, report, cap.err


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def texts(pdf) -> list[str]:
    """Normalised full text from PyMuPDF and (if present) pdftotext."""
    with pymupdf.open(pdf) as doc:
        out = [norm(" ".join(p.get_text() for p in doc))]
    if shutil.which("pdftotext"):
        for extra in ([], ["-layout"]):
            res = subprocess.run(
                ["pdftotext", *extra, "-enc", "UTF-8", str(pdf), "-"],
                capture_output=True,
                check=False,
            )
            assert res.returncode == 0
            out.append(norm(res.stdout.decode("utf-8")))
    return out


def contains(pdf, value: str) -> bool:
    v = norm(value)
    v_nospace = re.sub(r"\s", "", v)
    for t in texts(pdf):
        if v in t or v_nospace in re.sub(r"\s", "", t):
            return True
    return False
