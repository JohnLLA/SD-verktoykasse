"""Tests for compare, based on «Godkjent når» in docs/verktoy.md and testdata/FASIT.md."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from jv_compare import cli
from jv_compare.core import (
    SCANNED_WARNING,
    Options,
    compare_files,
    read_document,
    render_html,
    split_sentences,
)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "testdata" / "compare"
FORMATS = ["txt", "docx", "pdf"]
MOVED = "Tilskuddet utbetales i to like deler."
DELETED = "Ubrukte midler skal betales tilbake til kommunen."


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, capsys):
    code = cli.main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def html_text(fragment: str) -> str:
    return re.sub(r"\s+", " ", fragment)


# ---------------------------------------------------------------- reading


@pytest.mark.parametrize("fmt", FORMATS)
def test_reads_paragraphs(fmt):
    v1 = read_document(DATA / f"vedtak_v1.{fmt}")
    v2 = read_document(DATA / f"vedtak_v2.{fmt}")
    # FASIT: v1 has 6 paragraphs and v2 has 5, the title not counted
    assert len(v1.paragraphs) == 7
    assert len(v2.paragraphs) == 6
    assert v1.paragraphs[0] == "Vedtak i sak 42/26 – Tilskudd til Fiktivhavn kulturhus"
    assert not v1.warnings and not v2.warnings


@pytest.mark.parametrize(
    "a,b", [("txt", "docx"), ("txt", "pdf"), ("docx", "pdf"), ("pdf", "pdf")]
)
def test_same_content_in_different_formats_is_equal(a, b):
    c = compare_files(DATA / f"vedtak_v1.{a}", DATA / f"vedtak_v1.{b}")
    assert c.total_changed == 0
    assert c.words_added == c.words_removed == 0
    assert not c.moved


def test_sentence_split_keeps_dates_together():
    text = "Møtet var 12. februar 2026. Første del utbetales nå. Ferdig!"
    spans = [text[s:e] for s, e in split_sentences(text)]
    assert spans == ["Møtet var 12. februar 2026.", "Første del utbetales nå.", "Ferdig!"]


# ---------------------------------------------------------------- the three changes


@pytest.mark.parametrize("old_fmt", FORMATS)
@pytest.mark.parametrize("new_fmt", FORMATS)
def test_godkjent_changes(old_fmt, new_fmt):
    c = compare_files(DATA / f"vedtak_v1.{old_fmt}", DATA / f"vedtak_v2.{new_fmt}")

    # changed paragraph 2 (number), changed paragraph 4 (sentence moved in),
    # deleted paragraph 5
    assert c.changed_paragraphs == 2
    assert c.deleted_paragraphs == 1
    assert c.inserted_paragraphs == 0
    assert c.total_changed == 3

    # moved sentence: from paragraph 2 to paragraph 4 (3 -> 5 with the title)
    assert len(c.moved) == 1
    assert c.moved[0].text == MOVED
    assert (c.moved[0].old_paragraph, c.moved[0].new_paragraph) == (3, 5)

    # the amount is one token: 1 200 000 removed, 1 250 000 added
    assert c.words_added == 1
    deleted_row = [r for r in c.rows if r.kind == "deleted"]
    assert len(deleted_row) == 1 and deleted_row[0].old_no == 6
    # removed = the amount + the 16 words of the deleted paragraph
    assert c.words_removed == 1 + 16

    page = html_text(render_html(c))
    assert "<del>1 200 000</del>" in page
    assert "<ins>1 250 000</ins>" in page
    assert f'<del class="moved" title="flyttet til avsnitt 5">{MOVED}</del>' in page
    assert f'<ins class="moved" title="flyttet fra avsnitt 3">{MOVED}</ins>' in page
    assert f"<del>{DELETED}" in page
    assert "(avsnittet er slettet)" in page


def test_unchanged_paragraphs_are_equal_rows():
    c = compare_files(DATA / "vedtak_v1.txt", DATA / "vedtak_v2.txt")
    kinds = [(r.kind, r.old_no, r.new_no) for r in c.rows]
    assert kinds == [
        ("equal", 1, 1),
        ("equal", 2, 2),
        ("changed", 3, 3),
        ("equal", 4, 4),
        ("changed", 5, 5),
        ("deleted", 6, None),
        ("equal", 7, 6),
    ]


def test_reverse_direction_shows_inserted_paragraph():
    c = compare_files(DATA / "vedtak_v2.txt", DATA / "vedtak_v1.txt")
    assert c.inserted_paragraphs == 1 and c.deleted_paragraphs == 0
    assert len(c.moved) == 1
    page = render_html(c)
    assert "(nytt avsnitt)" in page
    assert f"<ins>{DELETED}" in page


# ---------------------------------------------------------------- options


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_ignore_whitespace_default_and_off(tmp_path):
    a = write(tmp_path / "a.txt", "Første linje med tekst.\n\nAndre avsnitt her.")
    b = write(tmp_path / "b.txt", "Første  linje\nmed tekst.\n\nAndre avsnitt her.")
    assert compare_files(a, b).total_changed == 0
    c = compare_files(a, b, Options(ignore_whitespace=False))
    assert c.changed_paragraphs == 1


def test_ignore_case(tmp_path):
    a = write(tmp_path / "a.txt", "Kommunen innvilger tilskudd.")
    b = write(tmp_path / "b.txt", "kommunen INNVILGER tilskudd.")
    assert compare_files(a, b).changed_paragraphs == 1
    assert compare_files(a, b, Options(ignore_case=True)).total_changed == 0


def test_cli_options(tmp_path, capsys):
    a = write(tmp_path / "a.txt", "Kommunen innvilger tilskudd.")
    b = write(tmp_path / "b.txt", "KOMMUNEN  innvilger tilskudd.")
    code, out, _ = run([a, b, "--out", tmp_path / "u1", "--ignore-case"], capsys)
    assert code == 0 and json.loads(out)["outputs"][0]["changed_paragraphs"] == 0
    code, out, _ = run(
        [a, b, "--out", tmp_path / "u2", "--ignore-case", "--no-ignore-whitespace"],
        capsys,
    )
    assert code == 0 and json.loads(out)["outputs"][0]["changed_paragraphs"] == 1


# ---------------------------------------------------------------- HTML


def test_html_is_self_contained_and_escaped(tmp_path):
    danger = "<script>alert(1)</script> <img src=x onerror=alert(2)> & «sitat»"
    a = write(tmp_path / "a<b>.md", f"# Tittel\n\nGammel tekst med {danger}.\n\nSlettet <b>avsnitt</b>.")
    b = write(tmp_path / "b.md", f"# Tittel\n\nNy tekst med {danger}.\n\nNytt <i>avsnitt</i> helt annet.")
    page = render_html(compare_files(a, b))
    lower = page.lower()
    assert "<script" not in lower
    assert "<img" not in lower
    assert "<link" not in lower
    assert "http://" not in lower and "https://" not in lower
    assert "@import" not in lower and "url(" not in lower
    assert "&lt;script&gt;" in page
    assert "&lt;img src=x onerror=alert(2)&gt;" in page
    assert "<b>avsnitt" not in page and "<i>" not in page
    assert "a&lt;b&gt;.md" in page
    assert "&amp;" in page
    assert page.startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in page


def test_html_header_counts(tmp_path, capsys):
    code, out, _ = run(
        [DATA / "vedtak_v1.docx", DATA / "vedtak_v2.pdf", "--out", tmp_path], capsys
    )
    assert code == 0
    report = json.loads(out)
    page = Path(report["outputs"][0]["path"]).read_text(encoding="utf-8")
    assert "<b>3</b><span>endrede avsnitt" in page
    assert "<b>1</b><span>ord lagt til" in page
    assert "<b>17</b><span>ord fjernet" in page
    assert "<b>1</b><span>flyttede setninger" in page


# ---------------------------------------------------------------- report and files


def test_cli_report_contract(tmp_path, capsys):
    old, new = DATA / "vedtak_v1.txt", DATA / "vedtak_v2.txt"
    code, out, err = run([old, new, "--out", tmp_path], capsys)
    assert code == 0
    report = json.loads(out)
    assert set(report) == {"tool", "version", "inputs", "outputs", "warnings", "summary"}
    assert report["tool"] == "compare"
    assert [i["sha256"] for i in report["inputs"]] == [sha(old), sha(new)]
    output = report["outputs"][0]
    assert Path(output["path"]).name == "vedtak_v1-mot-vedtak_v2.html"
    assert Path(output["path"]).parent == tmp_path
    assert output["changed_paragraphs"] == 3
    assert output["moved_sentences"] == 1
    assert report["warnings"] == []
    assert "3 avsnitt er endret" in report["summary"]
    assert "1 setning flyttet" in report["summary"]


def test_does_not_overwrite_existing_report(tmp_path, capsys):
    args = [DATA / "vedtak_v1.txt", DATA / "vedtak_v2.txt", "--out", tmp_path]
    _, out1, _ = run(args, capsys)
    _, out2, _ = run(args, capsys)
    p1 = json.loads(out1)["outputs"][0]["path"]
    p2 = json.loads(out2)["outputs"][0]["path"]
    assert p1 != p2 and Path(p1).exists() and Path(p2).exists()


def test_names_with_spaces_and_norwegian_letters(tmp_path, capsys):
    src = tmp_path / "inn mappe; æøå"
    src.mkdir()
    old = src / "vedtak første versjon; æøå.docx"
    new = src / "vedtak andre versjon (ÆØÅ).pdf"
    shutil.copy(DATA / "vedtak_v1.docx", old)
    shutil.copy(DATA / "vedtak_v2.pdf", new)
    before = (sha(old), sha(new))
    code, out, _ = run([old, new, "--out", tmp_path / "ut mappe æøå"], capsys)
    assert code == 0
    report = json.loads(out)
    path = Path(report["outputs"][0]["path"])
    assert path.exists()
    assert path.name == "vedtak første versjon; æøå-mot-vedtak andre versjon (ÆØÅ).html"
    assert "vedtak første versjon; æøå.docx" in path.read_text(encoding="utf-8")
    assert (sha(old), sha(new)) == before


@pytest.mark.parametrize("fmt", FORMATS)
def test_inputs_unchanged(tmp_path, capsys, fmt):
    old, new = DATA / f"vedtak_v1.{fmt}", DATA / f"vedtak_v2.{fmt}"
    before = (sha(old), sha(new))
    code, _, _ = run([old, new, "--out", tmp_path], capsys)
    assert code == 0
    assert (sha(old), sha(new)) == before


def test_out_in_input_folder_does_not_touch_input(tmp_path, capsys):
    old = shutil.copy(DATA / "vedtak_v1.txt", tmp_path / "v1.txt")
    new = shutil.copy(DATA / "vedtak_v2.txt", tmp_path / "v2.txt")
    before = sha(Path(old))
    code, out, _ = run([old, new, "--out", tmp_path], capsys)
    assert code == 0
    assert sha(Path(old)) == before
    assert Path(json.loads(out)["outputs"][0]["path"]).suffix == ".html"


# ---------------------------------------------------------------- scanned PDF


def _scanned_pdf(path: Path) -> Path:
    import pymupdf

    src = pymupdf.open(DATA / "vedtak_v1.pdf")
    pix = src[0].get_pixmap(dpi=72)
    out = pymupdf.open()
    page = out.new_page(width=src[0].rect.width, height=src[0].rect.height)
    page.insert_image(page.rect, pixmap=pix)
    out.save(path)
    return path


def test_scanned_pdf_warns(tmp_path, capsys):
    scanned = _scanned_pdf(tmp_path / "skannet.pdf")
    code, out, _ = run([scanned, DATA / "vedtak_v2.txt", "--out", tmp_path / "ut"], capsys)
    assert code == 0
    report = json.loads(out)
    assert len(report["warnings"]) == 1
    assert SCANNED_WARNING in report["warnings"][0]
    assert "PDF-en ser ut til å være skannet. Kjør `ocr` først." in report["warnings"][0]
    page = Path(report["outputs"][0]["path"]).read_text(encoding="utf-8")
    assert "Kjør `ocr` først." in page


# ---------------------------------------------------------------- bad input


@pytest.mark.parametrize(
    "make,expected",
    [
        (lambda d: d / "finnes_ikke.txt", "Finner ikke filen"),
        (lambda d: write(d / "tom.txt", ""), "er tom"),
        (lambda d: write(d / "bilde.jpg", "ikke tekst"), "støttes ikke"),
        (lambda d: write(d / "feil.docx", "dette er ikke en zip"), "DOCX"),
        (lambda d: write(d / "feil.pdf", "dette er ikke en pdf"), "PDF"),
        (lambda d: write(d / "blank.txt", "  \n\n  \n"), "Fant ingen tekst"),
        (lambda d: (d / "binær.txt").write_bytes(b"\x00\x01\x02") and d / "binær.txt", "tekstfil"),
        (lambda d: d, "er ikke en fil"),
    ],
)
def test_bad_input_gives_norwegian_error(tmp_path, capsys, make, expected):
    bad = make(tmp_path)
    code, out, err = run([bad, DATA / "vedtak_v2.txt", "--out", tmp_path / "ut"], capsys)
    assert code == 1
    assert out == ""
    assert err.startswith("Feil: ")
    assert expected in err
    assert "Traceback" not in err


def test_missing_arguments(tmp_path, capsys):
    code, _, err = run([DATA / "vedtak_v1.txt"], capsys)
    assert code == 1
    assert "Ugyldige argumenter" in err
    assert "Traceback" not in err


def test_jv_dispatch(tmp_path, capsys):
    from jv_common.cli import discover_tools, main as jv_main

    assert "compare" in discover_tools()
    code = jv_main(
        ["compare", str(DATA / "vedtak_v1.txt"), str(DATA / "vedtak_v2.pdf"), "--out", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["tool"] == "compare"
