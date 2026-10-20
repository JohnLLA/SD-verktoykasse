"""Second contract check: separators in fødselsnummer, invisible characters,
disguised streams and unknown catalog keys, ToUnicode CMaps with ligatures
(no false hits), rotated pages, and plan edits (placement, terms).

All PDFs are generated here with synthetic data, mirroring the contract
checker's files in vokter-redact/runde2/.
"""

import json
import re
import unicodedata

import pymupdf
import pytest
from redact_helpers import run

from jv_redact.detect import find_in_string, normalize_text
from jv_redact.verify import verify

FNR = "15068527101"
FNR2 = "29029241803"


# ------------------------------------------------------------------ helpers


def _new(lines=("Navn: Kari Fiktivsen",)):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 18 * i), line, fontsize=11)
    return doc, page


def _add_object(doc, source: str, stream: bytes | None = None) -> int:
    xref = doc.get_new_xref()
    doc.update_object(xref, source)
    if stream is not None:
        doc.update_stream(xref, stream, compress=False)
    return xref


def _append_content(doc, page, content: bytes) -> None:
    xref = _add_object(doc, "<<>>", content)
    refs = " ".join(f"{x} 0 R" for x in page.get_contents() + [xref])
    doc.xref_set_key(page.xref, "Contents", f"[{refs}]")


def _resources_xref(doc, page) -> int:
    kind, value = doc.xref_get_key(page.xref, "Resources")
    if kind == "xref":
        return int(value.split()[0])
    xref = _add_object(doc, value if kind == "dict" else "<<>>")
    doc.xref_set_key(page.xref, "Resources", f"{xref} 0 R")
    return xref


def _font_with_cmap(doc, page, name: str, cmap_entries: str) -> None:
    cmap = (
        "/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /X def\n"
        "1 begincodespacerange <00> <FF> endcodespacerange\n"
        "1 beginbfrange <20> <7E> <0020> endbfrange\n"
        f"{cmap_entries}\nendcmap CMapName currentdict /CMap defineresource pop end end"
    ).encode()
    cm = _add_object(doc, "<<>>", cmap)
    font = _add_object(
        doc,
        f"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding/ToUnicode {cm} 0 R>>",
    )
    doc.xref_set_key(_resources_xref(doc, page), f"Font/{name}", f"{font} 0 R")


def _save(doc, path):
    doc.save(path)
    doc.close()
    return path


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if c != "\xad" and unicodedata.category(c) != "Cf")
    return re.sub(r"[\W_]", "", text).casefold()


def _everything(path) -> str:
    """All text a reader could get at, normalised and without separators."""
    from jv_redact.pdfstrings import text_pieces

    doc = pymupdf.open(path)
    parts = [" ".join(p.get_text(clip=pymupdf.INFINITE_RECT()) for p in doc)]
    for xref in range(1, doc.xref_length()):
        parts += text_pieces(doc.xref_object(xref).encode("utf-8"))
        if doc.xref_is_stream(xref):
            data = doc.xref_stream(xref) or b""
            parts += text_pieces(data, content=True)
            parts.append(data.decode("latin-1"))
    doc.close()
    return _norm(" ".join(parts))


def _assert_gone(path, *values):
    hay = _everything(path)
    for v in values:
        assert _norm(v) not in hay, v


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "runde2 æøå"
    d.mkdir()
    (d / "termer.txt").write_text("Kari Fiktivsen\nÅse Prøvesen\n", encoding="utf-8")
    return d


def _finn(capsys, folder, pdf):
    code, rep, err = run(capsys, "finn", pdf, "--terms", folder / "termer.txt", "--out", folder / "ut")
    assert code == 0, err
    path = rep["outputs"][0]["path"]
    return path, json.loads(open(path, encoding="utf-8").read())


def _sladd(capsys, folder, pdf, plan_path):
    return run(capsys, "sladd", pdf, "--plan", plan_path, "--out", folder / "ut")


def _edited(folder, plan):
    p = folder / "endret.json"
    p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return p


# ------------------------------------------------------- 1: separators


SEPARATED = [
    "150685-27101",
    "29.02.92 41803",
    "150685.27101",
    "150685/27101",
    "150685–27101",  # en dash
    "150685—27101",  # em dash
    "150685·27101",  # middle dot
    "150685 - 27101",
    "290292 418 03",
]


@pytest.mark.parametrize("text", SEPARATED)
def test_fnr_with_separators_detected(text):
    hits = [h for h in find_in_string(f"Fnr: {text}.", []) if h[0] == "fodselsnummer"]
    assert len(hits) == 1
    assert hits[0][2] in (FNR, FNR2)


@pytest.mark.parametrize(
    "text",
    ["150685-27102", "1-150685-27101", "150685-27101-3", "150685-27101.5", "29.02.92.41803.1"],
)
def test_separators_not_in_longer_runs_or_wrong(text):
    assert not [h for h in find_in_string(f"Nr {text} her", []) if h[0] == "fodselsnummer"]


@pytest.mark.parametrize("text", ["58-01-23-45", "58.01.23.45", "580-12-345"])
def test_phone_with_hyphen_or_dot(text):
    assert ("telefon", text, "58012345") in [h[:3] for h in find_in_string(f"Tlf {text}.", [])]


@pytest.mark.parametrize("text", ["saksnr 2026-1234", "dato 20.10.2026", "sak 2026/1234"])
def test_no_phone_false_positives(text):
    assert not [h for h in find_in_string(text, []) if h[0] == "telefon"]


@pytest.fixture
def separators_pdf(folder):
    lines = ["Navn: Kari Fiktivsen"] + [f"Fnr {i}: {t}" for i, t in enumerate(SEPARATED)] + [
        "Tlf: 58-01-23-45 og 58.01.23.45",
        "Saksnr 2026-1234 og ref 150685-27102",
    ]
    doc, _page = _new(lines)
    return _save(doc, folder / "skilletegn.pdf")


def test_separators_end_to_end(capsys, folder, separators_pdf):
    plan_path, plan = _finn(capsys, folder, separators_pdf)
    fnr = [t for t in plan["treff"] if t["type"] == "fodselsnummer"]
    assert len(fnr) == len(SEPARATED)
    assert len([t for t in plan["treff"] if t["type"] == "telefon"]) == 2
    code, rep, err = _sladd(capsys, folder, separators_pdf, plan_path)
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR, FNR2, "58012345", "Kari Fiktivsen")
    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert "2026-1234" in text and "150685-27102" in text


def test_verify_detects_separated_fnr(separators_pdf):
    findings, _ = verify(open(separators_pdf, "rb").read(), {}, [], set())
    assert any("Gjenkjenningen finner fødselsnummer" in f for f in findings)


# ---------------------------------------------------- 2: invisible characters

INVISIBLE_CMAP = (
    "6 beginbfchar <80> <200B> <82> <00AD> <83> <2060> <84> <FEFF> <85> <200C> <86> <200D> endbfchar"
)


@pytest.fixture
def invisible_pdf(folder):
    doc, page = _new()
    _font_with_cmap(doc, page, "TU1", INVISIBLE_CMAP)
    _append_content(
        doc,
        page,
        b"q BT /TU1 11 Tf 72 700 Td (ZW 290292\\20041803) Tj 0 -20 Td "
        b"(SHY 1\\2025\\2020\\2026\\2028\\2025\\2022\\2027\\2021\\2020\\2021) Tj 0 -20 Td "
        b"(WJ 58\\20301\\2042345) Tj 0 -20 Td (ZWNJ 0101\\2059012\\206480) Tj ET Q",
    )
    return _save(doc, folder / "nullbredde.pdf")


def test_normalize_removes_invisible():
    assert normalize_text("290292​41803") == FNR2
    assert normalize_text("1\xad5⁠0﻿6‌8‍5") == "150685"
    assert normalize_text("１５") == "15"  # fullwidth digits (NFKC)
    hits = find_in_string("WJ 58⁠01﻿2345 og 290292​41803", [])
    assert ("telefon", "58012345") in [(h[0], h[2]) for h in hits]
    assert ("fodselsnummer", FNR2) in [(h[0], h[2]) for h in hits]


def test_invisible_characters_end_to_end(capsys, folder, invisible_pdf):
    with pymupdf.open(invisible_pdf) as doc:
        raw = doc[0].get_text()
    assert "​" in raw and "\xad" in raw  # the trick is really there
    plan_path, plan = _finn(capsys, folder, invisible_pdf)
    found = {(t["type"], t["normalisert"]) for t in plan["treff"]}
    assert {("fodselsnummer", FNR2), ("fodselsnummer", FNR), ("telefon", "58012345"),
            ("fodselsnummer", "01019012480")} <= found
    # the rectangle covers the digits, not the label in front
    zw = next(t for t in plan["treff"] if t["normalisert"] == FNR2)
    with pymupdf.open(invisible_pdf) as doc:
        label = doc[0].search_for("ZW")[0]
    assert zw["rektangler"][0][0] > label.x1
    code, rep, err = _sladd(capsys, folder, invisible_pdf, plan_path)
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR, FNR2, "58012345", "01019012480")
    with pymupdf.open(out) as doc:
        assert "ZW" in doc[0].get_text() and "WJ" in doc[0].get_text()


def test_verify_detects_invisible_characters(invisible_pdf):
    findings, _ = verify(open(invisible_pdf, "rb").read(), {}, [], set())
    joined = " ".join(findings)
    assert "fødselsnummer «29*******03»" in joined
    assert "telefonnummer «58****45»" in joined


# ------------------------------------- 3: disguised streams, unknown catalog keys


@pytest.fixture
def disguised_pdf(folder):
    doc, page = _new()
    a = _add_object(doc, "<</Length1 40>>", "Notat om Åse Prøvesen, fnr 29029241803".encode())
    b = _add_object(
        doc,
        "<</Type/XObject/Subtype/Image/Width 16/Height 1/ColorSpace/DeviceGray/BitsPerComponent 8>>",
        b"Notat 15068527101",
    )
    doc.xref_set_key(doc.pdf_catalog(), "Ekstra", f"<</A {a} 0 R /B {b} 0 R>>")
    doc.xref_set_key(page.xref, "Privat", f"{a} 0 R")
    return _save(doc, folder / "forkledd.pdf")


def test_disguised_streams_removed(capsys, folder, disguised_pdf):
    plan_path, _plan = _finn(capsys, folder, disguised_pdf)
    code, rep, err = _sladd(capsys, folder, disguised_pdf, plan_path)
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR, FNR2, "Åse Prøvesen", "Kari Fiktivsen")
    with pymupdf.open(out) as doc:
        assert set(doc.xref_get_keys(doc.pdf_catalog())) <= {"Type", "Pages", "Lang", "Version"}
        assert "Privat" not in doc.xref_get_keys(doc[0].xref)


def _doc_with_fake_resources(kind: str) -> bytes:
    doc, page = _new(["Ingen personopplysninger her"])
    res = _resources_xref(doc, page)
    if kind == "image":
        img = _add_object(
            doc,
            "<</Type/XObject/Subtype/Image/Width 16/Height 1/ColorSpace/DeviceGray/BitsPerComponent 8>>",
            b"Notat 15068527101",
        )
        doc.xref_set_key(res, "XObject/Im9", f"{img} 0 R")
    else:
        ff = _add_object(doc, "<</Length1 30>>", b"Skjult i fontfil 15068527101 her")
        fd = _add_object(doc, f"<</Type/FontDescriptor/FontName/Fake/Flags 32/FontFile2 {ff} 0 R>>")
        font = _add_object(doc, f"<</Type/Font/Subtype/TrueType/BaseFont/Fake/FontDescriptor {fd} 0 R>>")
        doc.xref_set_key(res, "Font/F9", f"{font} 0 R")
    doc.set_metadata({})
    # not clean=True: that would already drop the unused resources
    data = doc.tobytes(garbage=1)
    doc.close()
    return data


@pytest.mark.parametrize("kind", ["image", "font"])
def test_verify_scans_streams_that_only_claim_to_be_images_or_fonts(kind):
    findings, _ = verify(_doc_with_fake_resources(kind), {}, [], set())
    assert any("Gjenkjenningen finner fødselsnummer" in f and "strøm" in f for f in findings)


def test_real_image_with_digit_like_pixels_is_no_false_hit(capsys, folder):
    """Gray value 0x35 is the byte '5': raw pixels read '55555555...'."""
    doc, page = _new()
    pix = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 40, 10), False)
    pix.set_rect(pix.irect, (0x35,))
    page.insert_image(pymupdf.Rect(300, 300, 400, 325), pixmap=pix)
    pdf = _save(doc, folder / "bilde.pdf")
    plan_path, _ = _finn(capsys, folder, pdf)
    code, _rep, err = _sladd(capsys, folder, pdf, plan_path)
    assert code == 0, err


# ------------------------------------------ 4: ToUnicode CMap with ligatures


LIGATURE_CMAP = "3 beginbfchar <81> <00660069> <87> <00660066> <88> <00660074> endbfchar"


@pytest.fixture
def ligature_pdf(folder):
    doc, page = _new()
    _font_with_cmap(doc, page, "LG1", LIGATURE_CMAP)
    _append_content(
        doc,
        page,
        b"q BT /LG1 11 Tf 72 700 Td (O\\207isiell \\201l fra kontoret, e\\207ekt, \\210) Tj "
        b"0 -20 Td (Fnr 150685 27101, telefon 58 01 23 45.) Tj ET Q",
    )
    return _save(doc, folder / "ligatur.pdf")


def test_ligature_cmap_gives_no_false_hits(capsys, folder, ligature_pdf):
    with pymupdf.open(ligature_pdf) as doc:
        assert "Offisiell fil" in doc[0].get_text()
    plan_path, plan = _finn(capsys, folder, ligature_pdf)
    code, rep, err = _sladd(capsys, folder, ligature_pdf, plan_path)
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR, "58012345", "Kari Fiktivsen")
    with pymupdf.open(out) as doc:
        assert "Offisiell fil" in doc[0].get_text()


def test_cmap_targets_are_still_checked(folder):
    """A CMap is read structurally, so data hidden as one target is found."""
    doc, page = _new(["Ingen personopplysninger"])
    target = FNR.encode("utf-16-be").hex().upper()
    _font_with_cmap(doc, page, "X1", f"1 beginbfchar <90> <{target}> endbfchar")
    doc.set_metadata({})
    data = doc.tobytes(garbage=1)
    doc.close()
    findings, _ = verify(data, {}, [], set())
    assert any("Gjenkjenningen finner fødselsnummer" in f for f in findings)


# ------------------------------------------------------------- rotated page


def test_rotated_page_text_is_on_page(capsys, folder):
    doc, page = _new([f"Fnr {FNR}"])
    page.set_rotation(90)
    pdf = _save(doc, folder / "rotert.pdf")
    _plan_path, plan = _finn(capsys, folder, pdf)
    assert {t["plassering"] for t in plan["treff"]} == {"side"}


# ------------------------------------------------------- 5: plan edits


@pytest.mark.parametrize("new", ["utenfor sideflaten", "skjult lag"])
def test_changed_page_placement_rejected(capsys, folder, separators_pdf, new):
    plan_path, plan = _finn(capsys, folder, separators_pdf)
    plan["treff"][0]["plassering"] = new
    code, _rep, err = _sladd(capsys, folder, separators_pdf, _edited(folder, plan))
    assert code == 1 and "ugyldig eller endret" in err
    assert list((folder / "ut").glob("*.pdf")) == []


def test_hidden_layer_placement_cannot_be_changed_to_side(capsys, folder):
    doc, page = _new(["Synlig"])
    ocg = doc.add_ocg("skjult", on=False)
    page.insert_text((72, 200), f"Skjult {FNR}", oc=ocg)
    pdf = _save(doc, folder / "lag.pdf")
    plan_path, plan = _finn(capsys, folder, pdf)
    hit = next(t for t in plan["treff"] if t["normalisert"] == FNR)
    assert hit["plassering"] == "skjult lag"
    hit["plassering"] = "side"
    code, _rep, err = _sladd(capsys, folder, pdf, _edited(folder, plan))
    assert code == 1


@pytest.mark.parametrize("change", ["extra", "changed", "removed"])
def test_changed_terms_rejected(capsys, folder, separators_pdf, change):
    plan_path, plan = _finn(capsys, folder, separators_pdf)
    if change == "extra":
        plan["termer"].append("Fiktivhavn")
    elif change == "changed":
        plan["termer"][0] = "Kari"
    else:
        plan["termer"] = plan["termer"][1:]
    code, _rep, err = _sladd(capsys, folder, separators_pdf, _edited(folder, plan))
    assert code == 1
    assert "termer" in err
    assert list((folder / "ut").glob("*.pdf")) == []


def test_missing_terms_digest_rejected(capsys, folder, separators_pdf):
    plan_path, plan = _finn(capsys, folder, separators_pdf)
    del plan["kilde"]["termer_sha256"]
    code, _rep, err = _sladd(capsys, folder, separators_pdf, _edited(folder, plan))
    assert code == 1
