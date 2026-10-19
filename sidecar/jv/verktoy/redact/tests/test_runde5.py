"""Fifth contract check: a rejected (table cell) value must not cover the
same number elsewhere; rejected candidates set to "sladd": true are
redacted even when they are the only hits; justified text; and documents
without hits. PDFs are generated here (synthetic data)."""

import json

import pymupdf
import pytest
from redact_helpers import run
from test_runde2 import _add_object, _append_content, _assert_gone, _save

FNR = "15068527101"


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "runde5 æøå"
    d.mkdir()
    (d / "termer.txt").write_text("Kari Fiktivsen\n", encoding="utf-8")
    return d


def _finn(capsys, folder, pdf):
    code, rep, err = run(capsys, "finn", pdf, "--terms", folder / "termer.txt", "--out", folder / "ut")
    assert code == 0, err
    path = rep["outputs"][0]["path"]
    return rep, path, json.loads(open(path, encoding="utf-8").read())


def _sladd(capsys, folder, pdf, plan):
    p = folder / "plan.json"
    p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return run(capsys, "sladd", pdf, "--plan", p, "--out", folder / "ut")


def _cells(page, y=100):
    """«150685» and «27101» as two cells far apart: a rejected candidate."""
    page.insert_text((72, y), "150685", fontsize=11)
    page.insert_text((300, y), "27101", fontsize=11)


def _hidden(doc, page, text=FNR):
    """The number in one piece, with horizontal scaling 0 (not extracted by
    PyMuPDF, but in the content stream)."""
    page.insert_text((72, 60), "Vedlegg", fontsize=11)  # gives the page /helv
    _append_content(doc, page, f"q BT /helv 11 Tf 0 Tz 72 700 Td ({text}) Tj ET Q".encode())


# ----------------------------------------- 1: decoy value + hidden number


@pytest.fixture
def decoy_other_page(folder):
    doc = pymupdf.open()
    _cells(doc.new_page())
    _hidden(doc, doc.new_page())
    return _save(doc, folder / "lokke s1 skjult s2.pdf")


@pytest.fixture
def decoy_same_page(folder):
    doc = pymupdf.open()
    page = doc.new_page()
    _cells(page)
    _hidden(doc, page)
    return _save(doc, folder / "lokke og skjult.pdf")


@pytest.mark.parametrize("which", ["decoy_other_page", "decoy_same_page"])
def test_rejected_value_does_not_cover_hidden_copy(capsys, folder, which, request):
    pdf = request.getfixturevalue(which)
    rep, _path, plan = _finn(capsys, folder, pdf)
    # the value also stands as one text object (the hidden copy), so the
    # cells are a normal hit, and finn warns about the hidden text
    cells = [t for t in plan["treff"] if t["normalisert"] == FNR]
    assert cells and not any(t.get("forkastet") for t in cells)
    assert all(t["sladd"] for t in cells)
    assert any("ett tekststykke" in w for w in rep["warnings"])
    code, _r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 1, err
    assert "Gjenkjenningen finner fødselsnummer" in err and "strøm" in err
    assert list((folder / "ut").glob("*.pdf")) == []


def test_rejected_value_alone_passes(capsys, folder):
    doc = pymupdf.open()
    _cells(doc.new_page())
    pdf = _save(doc, folder / "bare lokke.pdf")
    rep, _path, plan = _finn(capsys, folder, pdf)
    code, r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    assert "IKKE sladdet" in r["summary"]


def test_hidden_alone_still_stops(capsys, folder):
    doc = pymupdf.open()
    _hidden(doc, doc.new_page())
    pdf = _save(doc, folder / "kun skjult.pdf")
    _rep, _path, plan = _finn(capsys, folder, pdf)
    code, _r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 1 and "strøm" in err


# --------------------------- 2: only rejected candidates, set to sladd true


@pytest.fixture
def kerning_pdf(folder):
    """As d02: phone groups pushed apart with TJ kerning, in one TJ array."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Notat", fontsize=11)
    _append_content(doc, page, b"q BT /helv 11 Tf 72 700 Td (Telefon: ) Tj "
                    b"[(58) -1500 (01) -1500 (23) -1500 (45)] TJ ET Q")
    return _save(doc, folder / "kerning.pdf")


def test_kerning_in_one_text_object_is_a_hit(capsys, folder, kerning_pdf):
    rep, _path, plan = _finn(capsys, folder, kerning_pdf)
    assert [(t["normalisert"], t.get("forkastet", False), t["sladd"]) for t in plan["treff"]] == [
        ("58012345", False, True)]
    code, r, err = _sladd(capsys, folder, kerning_pdf, plan)
    assert code == 0, err
    _assert_gone(r["outputs"][0]["path"], "58012345")


@pytest.fixture
def cells_pdf(folder):
    doc = pymupdf.open()
    _cells(doc.new_page())
    return _save(doc, folder / "celler.pdf")


def test_only_rejected_set_to_true_is_redacted(capsys, folder, cells_pdf):
    rep, _path, plan = _finn(capsys, folder, cells_pdf)
    assert [t["normalisert"] for t in plan["treff"]] == [FNR]
    assert plan["treff"][0]["forkastet"] is True
    assert rep["summary"].startswith("Fant ingen treff")
    assert "1 mulige fødselsnumre/telefonnumre ble IKKE merket" in rep["summary"]
    plan["treff"][0]["sladd"] = True
    code, r, err = _sladd(capsys, folder, cells_pdf, plan)
    assert code == 0, err
    assert r["outputs"][0]["sladdet"] == 1
    _assert_gone(r["outputs"][0]["path"], FNR, "150685", "27101")


def test_only_rejected_left_false_warns(capsys, folder, cells_pdf):
    _rep, _path, plan = _finn(capsys, folder, cells_pdf)
    code, r, err = _sladd(capsys, folder, cells_pdf, plan)
    assert code == 0, err
    assert r["summary"].startswith("Ingen treff ble merket for sladding. Les gjennom dokumentet selv.")
    assert "IKKE sladdet" in r["summary"]


def test_table_all_rejected_set_to_true(capsys, folder):
    doc = pymupdf.open()
    page = doc.new_page()
    for row, (a, b) in enumerate([("150685", "27101"), ("010190", "12480")]):
        page.insert_text((72, 80 + 16 * row), a, fontsize=10)
        page.insert_text((140, 80 + 16 * row), b, fontsize=10)
    pdf = _save(doc, folder / "tabell.pdf")
    _rep, _path, plan = _finn(capsys, folder, pdf)
    assert plan["treff"] and all(t["forkastet"] for t in plan["treff"])
    for t in plan["treff"]:
        t["sladd"] = True
    code, r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    assert r["outputs"][0]["sladdet"] == len(plan["treff"])


# --------------------------------------------------- 3: justified text


def _justified_pdf(folder, tw: float):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Vedtak", fontsize=11)
    line = b"(Ring saksbehandler Kari Fiktivsen pa telefon 58 01 23 45 eller oppgi fnr 150685 27101 i svaret) Tj"
    _append_content(doc, page, b"q BT /helv 10 Tf " + f"{tw} Tw".encode() + b" 40 700 Td " + line + b" ET Q")
    return _save(doc, folder / f"justert {tw}.pdf")


@pytest.mark.parametrize("tw", [0, 4, 8])
def test_justified_text_numbers_are_hits(capsys, folder, tw):
    pdf = _justified_pdf(folder, tw)
    _rep, _path, plan = _finn(capsys, folder, pdf)
    real = {t["normalisert"] for t in plan["treff"] if not t.get("forkastet")}
    assert {"58012345", FNR} <= real
    assert not [t for t in plan["treff"] if t.get("forkastet")]
    code, r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    _assert_gone(r["outputs"][0]["path"], "58012345", FNR, "Kari Fiktivsen")


def test_number_cells_in_a_row_still_rejected(capsys, folder):
    """No letter words on the line: no stretched word gaps to measure, so
    wide gaps between number cells are not joined."""
    doc = pymupdf.open()
    page = doc.new_page()
    for x, cell in zip((72, 160, 250, 340), ("150685", "27101", "58 01", "23 45")):
        page.insert_text((x, 100), cell, fontsize=10)
    pdf = _save(doc, folder / "tallrad.pdf")
    _rep, _path, plan = _finn(capsys, folder, pdf)
    assert all(t.get("forkastet") for t in plan["treff"])


# ------------------------------------------------------ 4: no hits at all


def test_no_hits_gives_cleaned_copy(capsys, folder):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Et notat uten tall eller navn.", fontsize=11)
    doc.set_metadata({"author": "Noen", "title": "Notat"})
    doc.set_toc([[1, "Notat", 1]])
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 60, 200, 76),
                      "uri": "https://example.org/"})
    pdf = _save(doc, folder / "uten treff.pdf")
    rep, _path, plan = _finn(capsys, folder, pdf)
    assert plan["treff"] == [] and rep["summary"].startswith("Fant ingen treff")
    code, r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    assert r["summary"].startswith("Ingen treff ble merket for sladding. Les gjennom dokumentet selv.")
    assert r["outputs"][0]["sladdet"] == 0
    with pymupdf.open(r["outputs"][0]["path"]) as d:
        assert d.get_toc() == [] and d[0].get_links() == []
        assert not d.metadata.get("author")
        assert "Et notat uten tall" in d[0].get_text()


def test_all_struck_gives_cleaned_copy(capsys, folder):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), f"Kari Fiktivsen, fnr {FNR}", fontsize=11)
    pdf = _save(doc, folder / "alt strøket.pdf")
    _rep, _path, plan = _finn(capsys, folder, pdf)
    for t in plan["treff"]:
        t["sladd"] = False
    code, r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    assert r["summary"].startswith("Ingen treff ble merket for sladding")
    with pymupdf.open(r["outputs"][0]["path"]) as d:
        assert FNR in d[0].get_text()  # the user chose to keep it


def test_hidden_only_is_warned_in_finn(capsys, folder):
    doc = pymupdf.open()
    _hidden(doc, doc.new_page(), text="150685 27101")
    pdf = _save(doc, folder / "kun skjult delt.pdf")
    rep, _path, plan = _finn(capsys, folder, pdf)
    assert any("skjult eller usynlig tekst" in w for w in rep["warnings"])
    code, _r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 1


# --------------------------- runde 6: hidden copies written with gaps / TJ


@pytest.mark.parametrize("hidden", [
    b"BT /helv 11 Tf 72 300 Td 0 Tz (150685 27101) Tj ET",
    b"q BT /helv 11 Tf 72 300 Td 0 Tz [(150685) -300 (27101)] TJ ET Q",
])
@pytest.mark.parametrize("own_stream", [False, True])
def test_decoy_and_hidden_split_copy_stops(capsys, folder, hidden, own_stream):
    """e01/e02/e02c: decoy cells plus a hidden copy with a gap or TJ
    adjustment on the same page. Must never be delivered."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Til Kari Fiktivsen", fontsize=11)
    _cells(page)
    if own_stream:
        _append_content(doc, page, hidden)
    else:
        xref = page.get_contents()[-1]
        doc.update_stream(xref, (doc.xref_stream(xref) or b"") + b"\n" + hidden)
    pdf = _save(doc, folder / "lokke delt.pdf")
    rep, _path, plan = _finn(capsys, folder, pdf)
    assert not [t for t in plan["treff"] if t.get("forkastet")]  # promoted
    code, r, err = _sladd(capsys, folder, pdf, plan)
    assert code == 1, (r or {}).get("summary")
    assert list((folder / "ut").glob("*.pdf")) == []
