"""Third contract check: a single digit next to a fødselsnummer (numbered
lists, table rows), NFC/NFD differences between PDF and term file, and plans
whose term list was edited. PDFs are generated here (synthetic data)."""

import json
import unicodedata

import pymupdf
import pytest
from redact_helpers import run
from test_runde2 import _append_content, _assert_gone, _font_with_cmap, _new, _save

from jv_redact.core import read_terms, terms_digest
from jv_redact.detect import find_in_string, normalize_text
from jv_redact.verify import verify

FNR = "15068527101"
FNR2 = "29029241803"
DNR = "41038815278"
NFC_NAME = "Åse Prøvesen"
NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "runde3 æøå"
    d.mkdir()
    return d


def _terms(folder, *terms):
    p = folder / "termer.txt"
    p.write_text("\n".join(terms) + "\n", encoding="utf-8")
    return p


def _finn_sladd(capsys, folder, pdf, terms):
    out = folder / "ut"
    code, rep, err = run(capsys, "finn", pdf, "--terms", terms, "--out", out)
    assert code == 0, err
    plan_path = rep["outputs"][0]["path"]
    plan = json.loads(open(plan_path, encoding="utf-8").read())
    code, rep2, err2 = run(capsys, "sladd", pdf, "--plan", plan_path, "--out", out)
    return plan, code, rep2, err2


# ------------------------------------------------- 1: digit next to the number

NEXT_TO = [
    (f"Rad 1 {FNR} Kari", FNR),
    (f"{FNR2} 2 vedlegg", FNR2),
    (f"Nr 7 {DNR}", DNR),
    (f"1 {FNR} Kari Fiktivsen", FNR),
    (f"Tlf 58012345 {FNR2}", FNR2),
    (f"1. {FNR}", FNR),
    (f"{FNR}, 2 stk", FNR),
    (f"Sum {FNR}. 3 sider", FNR),
    (f"12 34 {FNR} 5 6", FNR),
]


@pytest.mark.parametrize("text,number", NEXT_TO)
def test_single_digit_next_to_fnr(text, number):
    found = [h[2] for h in find_in_string(text, []) if h[0] in ("fodselsnummer", "d_nummer")]
    assert found == [number]


@pytest.mark.parametrize("text", [f"1-{FNR}", f"{FNR}-2", f"1.{FNR}", f"{FNR}/7", f"9{FNR}"])
def test_bound_digit_still_blocks(text):
    assert not [h for h in find_in_string(text, []) if h[0] in ("fodselsnummer", "d_nummer")]


@pytest.mark.parametrize(
    "text", ["1 58012345 x", "58012345 2 ganger", "Tlf 58 01 23 45 3 ganger", f"Tlf 58012345 {FNR2}"]
)
def test_single_digit_next_to_phone(text):
    assert "58012345" in [h[2] for h in find_in_string(text, []) if h[0] == "telefon"]


def test_digit_next_to_fnr_end_to_end(capsys, folder):
    lines = ["Liste:"] + [t for t, _ in NEXT_TO]
    doc, _page = _new(lines)
    pdf = _save(doc, folder / "liste.pdf")
    plan, code, rep, err = _finn_sladd(capsys, folder, pdf, _terms(folder, "Kari Fiktivsen"))
    numbers = [t["normalisert"] for t in plan["treff"] if t["type"] in ("fodselsnummer", "d_nummer")]
    assert len(numbers) == len(NEXT_TO)
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR, FNR2, DNR, "58012345")
    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert "Rad 1" in text and "2 vedlegg" in text and "Nr 7" in text


def test_verify_finds_fnr_next_to_digit(folder):
    doc, _page = _new([f"Rad 1 {FNR} Kari"])
    doc.set_metadata({})
    data = doc.tobytes(garbage=4, clean=True)
    doc.close()
    findings, _ = verify(data, {}, [], set())
    assert any("Gjenkjenningen finner fødselsnummer" in f for f in findings)


# ------------------------------------------------------------ 2: NFC and NFD


def test_normalize_whole_string():
    assert normalize_text(NFD_NAME) == NFC_NAME
    assert normalize_text("A​̊se") == "Åse"  # invisible char between base and mark
    assert ("term", NFC_NAME) in [(h[0], h[1]) for h in find_in_string(f"Til {NFD_NAME}.", [NFC_NAME])]
    assert ("term", NFC_NAME) in [(h[0], h[1]) for h in find_in_string(f"Til {NFC_NAME}.", [NFD_NAME])]


def test_read_terms_normalises(folder):
    assert read_terms(_terms(folder, NFD_NAME)) == [NFC_NAME]


def _nfd_pdf(folder):
    """Page text with A + U+030A (combining ring) instead of Å. The mark's
    advance is cancelled with a kerning value, as in a real NFD text run."""
    doc, page = _new(["Saksdokument"])
    _font_with_cmap(doc, page, "TU1", "1 beginbfchar <90> <030A> endbfchar")
    _append_content(doc, page, b"q BT /TU1 11 Tf 72 700 Td [(Kontakt: A\\220) 556 (se Pr\\370vesen)] TJ ET Q")
    return _save(doc, folder / "nfd.pdf")


def test_nfd_term_matches_nfc_pdf(capsys, folder):
    doc, _page = _new([f"Kontakt: {NFC_NAME}"])
    pdf = _save(doc, folder / "nfc.pdf")
    plan, code, rep, err = _finn_sladd(capsys, folder, pdf, _terms(folder, NFD_NAME))
    assert [t["tekst"] for t in plan["treff"] if t["type"] == "term"] == [NFC_NAME]
    assert code == 0, err
    _assert_gone(rep["outputs"][0]["path"], NFC_NAME)


def test_nfc_term_matches_nfd_pdf(capsys, folder):
    pdf = _nfd_pdf(folder)
    with pymupdf.open(pdf) as doc:
        assert "Åse" in doc[0].get_text()  # really decomposed
    plan, code, rep, err = _finn_sladd(capsys, folder, pdf, _terms(folder, NFC_NAME))
    hits = [t for t in plan["treff"] if t["type"] == "term"]
    assert [t["tekst"] for t in hits] == [NFC_NAME]
    with pymupdf.open(pdf) as doc:
        label = doc[0].search_for("Kontakt:")[-1]
    assert hits[0]["rektangler"][0][0] > label.x1  # box starts at the name
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, NFC_NAME)
    with pymupdf.open(out) as doc:
        assert "Kontakt:" in doc[0].get_text()


def test_verify_finds_nfd_name(folder):
    data = open(_nfd_pdf(folder), "rb").read()
    findings, _ = verify(data, {}, [], set(), terms=[NFC_NAME])
    assert any("Gjenkjenningen finner term" in f for f in findings)


# ------------------------------------------------------- 3: edited term list


def _plan_for(capsys, folder, terms):
    doc, _page = _new(["Navn: Kari Fiktivsen", f"Kontakt: {NFC_NAME}"])
    pdf = _save(doc, folder / "termer.pdf")
    code, rep, err = run(capsys, "finn", pdf, "--terms", _terms(folder, *terms), "--out", folder / "ut")
    assert code == 0, err
    plan = json.loads(open(rep["outputs"][0]["path"], encoding="utf-8").read())
    return pdf, plan


def _sladd_edited(capsys, folder, pdf, plan):
    p = folder / "endret.json"
    p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return run(capsys, "sladd", pdf, "--plan", p, "--out", folder / "ut")


def test_extra_term_with_recomputed_digest_is_rejected(capsys, folder):
    pdf, plan = _plan_for(capsys, folder, [NFC_NAME])
    plan["termer"].append("Kari Fiktivsen")
    plan["kilde"]["termer_sha256"] = terms_digest(plan["termer"])
    code, _rep, err = _sladd_edited(capsys, folder, pdf, plan)
    assert code == 1
    assert "mangler i planen" in err and "termer" in err
    assert list((folder / "ut").glob("*.pdf")) == []


def test_extra_term_without_digest_is_rejected(capsys, folder):
    pdf, plan = _plan_for(capsys, folder, [NFC_NAME])
    plan["termer"].append("Kari Fiktivsen")
    code, _rep, err = _sladd_edited(capsys, folder, pdf, plan)
    assert code == 1 and "termer" in err


def test_invalid_json_message_is_norwegian(capsys, folder):
    pdf, _plan = _plan_for(capsys, folder, [NFC_NAME])
    p = folder / "tull.json"
    p.write_text("{ikke json", encoding="utf-8")
    code, _rep, err = run(capsys, "sladd", pdf, "--plan", p, "--out", folder / "ut")
    assert code == 1
    assert "linje 1" in err and "Expecting" not in err
