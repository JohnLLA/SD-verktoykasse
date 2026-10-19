"""End-to-end: finn -> plan -> sladd, the post-check, and safe failures."""

import json

import pymupdf
import pytest
from redact_helpers import contains, run, texts

from jv_common import sha256_file, skip_if_missing
from jv_redact import core

KEEP = ["15068527102", "2026/1234", "3. mars 2026", "45 000 kroner"]


def _finn(capsys, work):
    code, report, err = run(capsys, "finn", work["pdf"], "--terms", work["terms"], "--out", work["out"])
    assert code == 0, err
    return report, json.loads(open(report["outputs"][0]["path"], encoding="utf-8").read())


def _sladd(capsys, work, plan_path):
    return run(capsys, "sladd", work["pdf"], "--plan", plan_path, "--out", work["out"])


def _write_plan(work, plan, name="endret.json"):
    p = work["dir"] / name
    p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return p


def _pdfs_in(folder):
    return sorted(folder.glob("*.pdf")) if folder.exists() else []


def test_finn_matches_fasit(capsys, work, fasit):
    report, plan = _finn(capsys, work)
    assert plan["kilde"]["sha256"] == sha256_file(work["pdf"])
    found = {(t["type"], t["tekst"], t["normalisert"], t["side"]) for t in plan["treff"]}
    expected = {
        (i["type"], i["tekst"], i["normalisert"], side)
        for i in fasit
        if i["skal_sladdes"]
        for side in i["sider"]
    }
    assert found == expected
    assert len(plan["treff"]) == 9
    assert all(t["sladd"] is True for t in plan["treff"])
    texts_found = " ".join(t["tekst"] for t in plan["treff"])
    for keep in KEEP:
        assert keep not in texts_found
    assert report["outputs"][0]["treff"] == 9
    assert "Fant 9 treff" in report["summary"]


def test_sladd_removes_everything(capsys, work, fasit):
    before = sha256_file(work["pdf"])
    report, plan = _finn(capsys, work)
    code, report, err = _sladd(capsys, work, report["outputs"][0]["path"])
    assert code == 0, err
    out = report["outputs"][0]["path"]
    assert out.endswith("-sladdet.pdf")
    assert report["outputs"][0]["sladdet"] == 9
    assert report["inputs"][0]["sha256"] == before
    assert sha256_file(work["pdf"]) == before  # original untouched

    for item in fasit:
        for value in {item["tekst"], item["normalisert"]}:
            if item["skal_sladdes"]:
                assert not contains(out, value), value
            else:
                assert contains(out, value), value
    for keep in KEEP:
        assert contains(out, keep), keep
    assert len(texts(out)) == (3 if __import__("shutil").which("pdftotext") else 1)

    with pymupdf.open(out) as doc:
        meta = {k: v for k, v in doc.metadata.items() if k not in ("format", "encryption")}
        assert not any(meta.values()), meta
        assert not doc.get_xml_metadata()
        assert all(p.first_annot is None and p.first_widget is None for p in doc)
    data = open(out, "rb").read()
    assert data.count(b"%%EOF") == 1


def test_struck_hit_stays(capsys, work):
    report, plan = _finn(capsys, work)
    for t in plan["treff"]:
        if t["type"] == "epost" or (t["type"] == "term" and t["side"] == 2):
            t["sladd"] = False
    code, report, err = _sladd(capsys, work, _write_plan(work, plan))
    assert code == 0, err
    out = report["outputs"][0]["path"]
    assert report["outputs"][0]["sladdet"] == 7
    with pymupdf.open(out) as doc:
        assert "Kari Fiktivsen" not in doc[0].get_text()
        assert "Kari Fiktivsen" in doc[1].get_text()
    assert contains(out, "kari.fiktivsen@example.no")
    assert not contains(out, "010190 12480")
    joined = " ".join(report["warnings"])
    assert "strøket" in joined


def test_sladd_without_plan_fails(capsys, work):
    code, report, err = run(capsys, "sladd", work["pdf"], "--out", work["out"])
    assert code == 1
    assert "krever en plan" in err
    assert "Traceback" not in err
    assert _pdfs_in(work["out"]) == []


def _manipulations(plan):
    def sha(p):
        p["kilde"]["sha256"] = "0" * 64

    def text(p):
        p["treff"][2]["tekst"] = "58 01 23 46"

    def rect(p):
        p["treff"][0]["rektangler"] = [[0, 0, 600, 800]]

    def page(p):
        p["treff"][0]["side"] = 2

    def added(p):
        new = dict(p["treff"][0], id="t99", tekst="Saken gjelder")
        p["treff"].append(new)

    def type_(p):
        p["treff"][0]["type"] = "telefon"

    def flag(p):
        p["treff"][0]["sladd"] = "ja"

    def dup(p):
        p["treff"].append(dict(p["treff"][0]))

    def terms(p):
        p["termer"] = ["Saksdokument"]
        p["treff"].append(dict(p["treff"][0], id="t99"))

    def version(p):
        p["plan_versjon"] = 2

    def no_list(p):
        p["treff"] = {"t1": p["treff"][0]}

    return [sha, text, rect, page, added, type_, flag, dup, terms, version, no_list]


@pytest.mark.parametrize("index", range(11))
def test_manipulated_plan_fails_safely(capsys, work, index):
    report, plan = _finn(capsys, work)
    change = _manipulations(plan)[index]
    change(plan)
    code, report, err = _sladd(capsys, work, _write_plan(work, plan))
    assert code == 1, change.__name__
    assert err.startswith("Feil: ")
    assert "Traceback" not in err
    assert _pdfs_in(work["out"]) == []


def test_plan_not_json(capsys, work):
    p = work["dir"] / "tull.json"
    p.write_text("{ikke json", encoding="utf-8")
    code, _, err = _sladd(capsys, work, p)
    assert code == 1 and "ikke gyldig JSON" in err


def test_plan_for_other_pdf(capsys, work):
    report, _plan = _finn(capsys, work)
    other = work["dir"] / "annen.pdf"
    other.write_bytes(work["pdf"].read_bytes() + b"\n% endret\n")
    code, _, err = run(capsys, "sladd", other, "--plan", report["outputs"][0]["path"], "--out", work["out"])
    assert code == 1
    assert "SHA-256 stemmer ikke" in err
    assert _pdfs_in(work["out"]) == []


def test_postcheck_blocks_output(capsys, work, monkeypatch):
    """If redaction did not remove the text, no file may be delivered."""
    report, _ = _finn(capsys, work)
    weak = dict(core.REDACT_OPTIONS, text=pymupdf.PDF_REDACT_TEXT_NONE)
    monkeypatch.setattr(core, "REDACT_OPTIONS", weak)
    code, _, err = _sladd(capsys, work, report["outputs"][0]["path"])
    assert code == 1
    assert "Etterkontrollen" in err and "ingen fil" in err
    assert "PyMuPDF" in err
    if __import__("shutil").which("pdftotext"):
        assert "pdftotext" in err
    # the values are masked in the message
    assert "01019012480" not in err and "kari.fiktivsen@example.no" not in err
    assert _pdfs_in(work["out"]) == []


def test_scanned_pdf_gives_ocr_hint(capsys, tmp_path, scanned_pdf):
    code, _, err = run(capsys, "finn", scanned_pdf, "--out", tmp_path)
    assert code == 1
    assert "jv ocr" in err


@pytest.mark.parametrize("kind", ["missing", "empty", "text", "fake"])
def test_bad_input(capsys, tmp_path, kind):
    p = tmp_path / f"fil {kind}.pdf"
    if kind == "empty":
        p.write_bytes(b"")
    elif kind == "text":
        p.write_text("Dette er ikke en PDF 01019012480", encoding="utf-8")
    elif kind == "fake":
        p.write_bytes(b"%PDF-1.4\n tull og toys \n")
    code, _, err = run(capsys, "finn", p, "--out", tmp_path / "ut")
    assert code == 1, err
    assert err.startswith("Feil: ")
    assert "Traceback" not in err


def test_missing_out_and_subcommand(capsys, work):
    code, _, err = run(capsys, "finn", work["pdf"])
    assert code == 1 and "--out" in err
    code, _, err = run(capsys)
    assert code == 1 and "finn" in err


def test_missing_terms_file(capsys, work):
    code, _, err = run(capsys, "finn", work["pdf"], "--terms", work["dir"] / "finnes ikke.txt", "--out", work["out"])
    assert code == 1 and "termfilen" in err


@skip_if_missing("pdftotext")
def test_pdftotext_is_used(capsys, work, monkeypatch):
    calls = []
    import subprocess

    from jv_redact import verify

    real = subprocess.run

    def spy(args, **kw):
        calls.append(args)
        return real(args, **kw)

    monkeypatch.setattr(verify.subprocess, "run", spy)
    report, _ = _finn(capsys, work)
    code, report, err = _sladd(capsys, work, report["outputs"][0]["path"])
    assert code == 0, err
    assert any("-layout" in a for a in calls)
    assert all(isinstance(a, list) for a in calls)


def test_warns_without_pdftotext(capsys, work, monkeypatch):
    from jv_redact import verify

    monkeypatch.setattr(verify, "_which", lambda name: None)
    report, _ = _finn(capsys, work)
    code, report, err = _sladd(capsys, work, report["outputs"][0]["path"])
    assert code == 0, err
    assert any("pdftotext er ikke installert" in w for w in report["warnings"])


def test_jv_dispatch_finds_tool(capsys, work):
    from jv_common.cli import main as jv_main

    code = jv_main(["redact", "finn", str(work["pdf"]), "--out", str(work["out"])])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "redact"


def test_deleted_hit_is_rejected(capsys, work):
    """Striking is done with "sladd": false; a deleted item means the plan
    no longer matches the PDF (it could also hide an added term)."""
    report, plan = _finn(capsys, work)
    plan["treff"] = plan["treff"][1:]
    code, _, err = _sladd(capsys, work, _write_plan(work, plan))
    assert code == 1
    assert "mangler i planen" in err and "sladd" in err
    assert _pdfs_in(work["out"]) == []
