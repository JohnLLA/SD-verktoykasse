"""Places outside the normal page text (from the contract check):
bookmarks with æøå, data only in a bookmark, switched-off layers, text
outside the page, data only in a mailto link, and page labels.

The PDFs are generated here (synthetic data) and mirror the contract
checker's files in vokter-redact/vanskelig/.
"""

import json
import re

import pymupdf
import pytest
from redact_helpers import run

from jv_redact import core
from jv_redact.pdfstrings import decode_pdf_string, text_pieces
from jv_redact.verify import verify

FNR = "15068527101"
FNR2 = "29029241803"
EMAIL = "kari.fiktivsen@example.no"


def _base(text_lines=("Saksdokument (oppdiktet)",)):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    for line in text_lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 20
    return doc


def _save(doc, path):
    doc.save(path, garbage=3)
    doc.close()
    return path


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "vanskelig æøå"
    d.mkdir()
    (d / "termer.txt").write_text("Kari Fiktivsen\nÅse Prøvesen\n", encoding="utf-8")
    return d


def _finn_sladd(capsys, folder, pdf, edit=None):
    out = folder / "ut"
    code, rep, err = run(capsys, "finn", pdf, "--terms", folder / "termer.txt", "--out", out)
    assert code == 0, err
    plan_path = rep["outputs"][0]["path"]
    plan = json.loads(open(plan_path, encoding="utf-8").read())
    if edit:
        edit(plan)
        plan_path = folder / "endret.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    code, rep2, err2 = run(capsys, "sladd", pdf, "--plan", plan_path, "--out", out)
    return plan, code, rep2, err2


def _all_decoded(path) -> str:
    """Every decoded string/name/comment in every object and stream."""
    doc = pymupdf.open(path)
    parts = []
    for xref in range(1, doc.xref_length()):
        parts += text_pieces(doc.xref_object(xref).encode("utf-8"))
        if doc.xref_is_stream(xref):
            data = doc.xref_stream(xref) or b""
            parts += text_pieces(data, content=True)
            parts.append(data.decode("latin-1"))
    doc.close()
    return re.sub(r"\s+", "", " ".join(parts)).casefold()


def _assert_gone(path, *values):
    hay = _all_decoded(path)
    with pymupdf.open(path) as doc:
        text = re.sub(r"\s+", "", " ".join(p.get_text(clip=pymupdf.INFINITE_RECT()) for p in doc)).casefold()
    for v in values:
        v = re.sub(r"\s+", "", v).casefold()
        assert v not in hay, v
        assert v not in text, v


# ------------------------------------------------------------ 1: bookmark æøå


@pytest.fixture
def bookmark_aeoa(folder):
    doc = _base(["Kontaktperson: Åse Prøvesen"])
    doc.set_toc([[1, "Notat om Åse Prøvesen", 1]])
    return _save(doc, folder / "bokmerke æøå.pdf")


def test_decoding_of_pdf_strings():
    assert decode_pdf_string(b"Notat om \xc5se Pr\xf8vesen") == "Notat om Åse Prøvesen"
    assert decode_pdf_string(b"\xfe\xff" + "Åse".encode("utf-16-be")) == "Åse"
    assert text_pieces(rb"(Notat om \305se Pr\370vesen)") == ["Notat om Åse Prøvesen"]
    assert text_pieces(b"<FEFF00C500730065>") == ["Åse"]
    assert text_pieces(b"<feff00c500730065>") == ["Åse"]
    assert text_pieces(rb"[(0101)-20(90 1)(2480)] TJ") == ["010190 12480"]
    assert text_pieces(b"(a\\(b\\)c (nested))") == ["a(b)c (nested)"]


def test_bookmark_with_aeoa_is_found_and_removed(capsys, folder, bookmark_aeoa):
    plan, code, rep, err = _finn_sladd(capsys, folder, bookmark_aeoa)
    assert {"bokmerke", "side"} <= {t["plassering"] for t in plan["treff"]}
    bm = [t for t in plan["treff"] if t["plassering"] == "bokmerke"]
    assert bm[0]["tekst"] == "Åse Prøvesen" and bm[0]["rektangler"] == []
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    with pymupdf.open(out) as doc:
        assert doc.get_toc() == []
    _assert_gone(out, "Åse Prøvesen")


def test_postcheck_catches_bookmark_left_behind(capsys, folder, bookmark_aeoa, monkeypatch):
    monkeypatch.setattr(pymupdf.Document, "set_toc", lambda self, *a, **k: None)
    monkeypatch.setattr(core, "CATALOG_KEEP", core.CATALOG_KEEP | {"Outlines"})
    _plan, code, _rep, err = _finn_sladd(capsys, folder, bookmark_aeoa)
    assert code == 1
    assert "bokmerker" in err
    assert "Gjenkjenningen finner term «Ås********en»" in err
    assert list((folder / "ut").glob("*.pdf")) == []


def test_verify_runs_detector_on_decoded_strings(folder, bookmark_aeoa):
    """Without any known redacted value, the detector alone must find the
    æøå name in the PDFDocEncoded bookmark title."""
    doc = pymupdf.open(bookmark_aeoa)
    doc.set_metadata({})
    doc[0].add_redact_annot(doc[0].search_for("Åse Prøvesen")[0])
    doc[0].apply_redactions()
    data = doc.tobytes(garbage=4, clean=True)
    doc.close()
    findings, _ = verify(data, {}, [], set(), terms=["Åse Prøvesen"])
    assert any("bokmerker" in f for f in findings)
    assert any("Gjenkjenningen" in f and "PDF-objekt" in f for f in findings)


# ------------------------------------------------- 2: switched-off layer (OCG)


@pytest.fixture
def hidden_layer(folder):
    doc = _base(["Synlig tekst uten personopplysninger"])
    ocg = doc.add_ocg("skjult", on=False)
    doc[0].insert_text((72, 150), f"Skjult lag {FNR}", fontsize=11, oc=ocg)
    return _save(doc, folder / "lag.pdf")


def test_hidden_layer_is_found_and_removed(capsys, folder, hidden_layer):
    with pymupdf.open(hidden_layer) as doc:
        assert FNR not in doc[0].get_text()  # really hidden
    plan, code, rep, err = _finn_sladd(capsys, folder, hidden_layer)
    hits = [t for t in plan["treff"] if t["normalisert"] == FNR]
    assert [t["plassering"] for t in hits] == ["skjult lag"]
    assert code == 0, err
    assert any("innholdslag" in w for w in rep["warnings"])
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR)
    with pymupdf.open(out) as doc:
        assert doc.xref_get_key(doc.pdf_catalog(), "OCProperties")[0] == "null"
        assert "Skjult lag" in doc[0].get_text()  # layer flattened, rest kept


def test_verify_sees_hidden_layer(hidden_layer):
    data = open(hidden_layer, "rb").read()
    findings, _ = verify(data, {}, [], set())
    assert any("Gjenkjenningen finner fødselsnummer" in f and "PyMuPDF" in f for f in findings)
    assert any("innholdslag" in f for f in findings)


# ------------------------------------------------------ 3: outside the page


@pytest.fixture
def outside(folder):
    doc = _base(["Synlig tekst"])
    doc[0].insert_text((700, 300), f"Utenfor {FNR2}", fontsize=11)  # page is 595 wide
    return _save(doc, folder / "utenfor.pdf")


def test_text_outside_page_is_found_and_removed(capsys, folder, outside):
    plan, code, rep, err = _finn_sladd(capsys, folder, outside)
    hits = [t for t in plan["treff"] if t["normalisert"] == FNR2]
    assert len(hits) == 1
    assert hits[0]["plassering"] == "utenfor sideflaten"
    assert hits[0]["rektangler"][0][0] > 595  # normal page coordinates
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR2)
    with pymupdf.open(out) as doc:
        assert doc[0].mediabox == pymupdf.Rect(0, 0, 595, 842)
        assert doc[0].cropbox == pymupdf.Rect(0, 0, 595, 842)
        assert "Synlig tekst" in doc[0].get_text()


def test_verify_sees_text_outside_page(outside):
    findings, _ = verify(open(outside, "rb").read(), {}, [], set())
    assert any("Gjenkjenningen finner fødselsnummer" in f for f in findings)


# ------------------------------------------------- 4: e-mail only in a link


@pytest.fixture
def mailto(folder):
    doc = _base(["Send svar til saksbehandler"])
    doc[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 60, 300, 76),
                        "uri": f"mailto:{EMAIL}"})
    return _save(doc, folder / "lenke.pdf")


def test_mailto_only_link_is_found_and_removed(capsys, folder, mailto):
    plan, code, rep, err = _finn_sladd(capsys, folder, mailto)
    hits = [t for t in plan["treff"] if t["type"] == "epost"]
    assert [(t["plassering"], t["side"]) for t in hits] == [("lenke", 1)]
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    with pymupdf.open(out) as doc:
        assert doc[0].get_links() == []
    _assert_gone(out, EMAIL)


def test_link_removed_even_when_struck(capsys, folder, mailto):
    def strike(plan):
        for t in plan["treff"]:
            if t["plassering"] == "lenke":
                t["sladd"] = False
    # only hit is struck -> nothing to redact, but a cleaned copy without the link
    _plan, code, rep, err = _finn_sladd(capsys, folder, mailto, strike)
    assert code == 0, err
    assert rep["summary"].startswith("Ingen treff ble merket for sladding")
    out = rep["outputs"][0]["path"]
    with pymupdf.open(out) as doc:
        assert doc[0].get_links() == []
    _assert_gone(out, EMAIL)


def test_verify_sees_link(mailto):
    doc = pymupdf.open(mailto)
    doc.set_metadata({})
    data = doc.tobytes(garbage=4, clean=True)
    doc.close()
    findings, _ = verify(data, {}, [], set())
    assert any("lenker" in f for f in findings)
    assert any("Gjenkjenningen finner e-postadresse" in f for f in findings)


# --------------------------------------------- 5: fnr only in a bookmark


@pytest.fixture
def bookmark_only(folder):
    doc = _base(["Kari Fiktivsen er part i saken"])
    doc.set_toc([[1, f"Fnr {FNR2}", 1]])
    return _save(doc, folder / "bokmerke bare.pdf")


def test_fnr_only_in_bookmark(capsys, folder, bookmark_only):
    plan, code, rep, err = _finn_sladd(capsys, folder, bookmark_only)
    hits = [t for t in plan["treff"] if t["normalisert"] == FNR2]
    assert [(t["plassering"], t["side"]) for t in hits] == [("bokmerke", 1)]
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    with pymupdf.open(out) as doc:
        assert doc.get_toc() == []
    _assert_gone(out, FNR2, "Kari Fiktivsen")


def test_struck_bookmark_hit_is_removed_anyway(capsys, folder, bookmark_only):
    def strike(plan):
        for t in plan["treff"]:
            if t["plassering"] == "bokmerke":
                t["sladd"] = False
    _plan, code, rep, err = _finn_sladd(capsys, folder, bookmark_only, strike)
    assert code == 0, err
    assert any("fjernes alltid" in w or "fjernet likevel" in w for w in rep["warnings"])
    _assert_gone(rep["outputs"][0]["path"], FNR2)


# ------------------------------------------------------------- page labels


@pytest.fixture
def page_labels(folder):
    doc = _base([f"Saken gjelder {FNR}"])
    doc.set_page_labels([{"startpage": 0, "prefix": f"{FNR2}-", "style": "D", "firstpagenum": 1}])
    return _save(doc, folder / "sidelabel.pdf")


def test_page_labels_are_found_and_removed(capsys, folder, page_labels):
    plan, code, rep, err = _finn_sladd(capsys, folder, page_labels)
    hits = [t for t in plan["treff"] if t["normalisert"] == FNR2]
    assert [(t["plassering"], t["side"]) for t in hits] == [("sidelabel", 1)]
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    with pymupdf.open(out) as doc:
        assert doc.get_page_labels() == []
        assert doc.xref_get_key(doc.pdf_catalog(), "PageLabels")[0] == "null"
    _assert_gone(out, FNR, FNR2)


def test_verify_sees_page_labels(page_labels):
    doc = pymupdf.open(page_labels)
    doc.set_metadata({})
    data = doc.tobytes(garbage=4, clean=True)
    doc.close()
    findings, _ = verify(data, {}, [], set())
    assert any("sidelabels" in f for f in findings)
    assert any("Gjenkjenningen finner fødselsnummer «29*******03»" in f for f in findings)


# ------------------------------------------------------- plan manipulation


@pytest.mark.parametrize("change", ["placement", "rects_on_bookmark", "page_hit_as_bookmark", "side_none"])
def test_manipulated_placement_fails(capsys, folder, bookmark_only, change):
    def edit(plan):
        bm = next(t for t in plan["treff"] if t["plassering"] == "bokmerke")
        pg = next(t for t in plan["treff"] if t["plassering"] == "side")
        if change == "placement":
            bm["plassering"] = "lenke"
        elif change == "rects_on_bookmark":
            bm["rektangler"] = [[0, 0, 600, 800]]
        elif change == "page_hit_as_bookmark":
            pg["plassering"] = "bokmerke"
            pg["rektangler"] = []
        else:
            pg["side"] = None
    _plan, code, _rep, err = _finn_sladd(capsys, folder, bookmark_only, edit)
    assert code == 1, err
    assert "Traceback" not in err
    assert list((folder / "ut").glob("*.pdf")) == []
