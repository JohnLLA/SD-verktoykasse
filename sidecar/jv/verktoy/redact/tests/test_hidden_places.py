"""Data hidden outside the page text: metadata, XMP, comments, form fields,
embedded files, links, images, vector graphics and earlier revisions."""

import io
import json
import shutil

import pymupdf
import pytest
from redact_helpers import contains, run

from jv_redact import core
from jv_redact.verify import Value, verify

FNR = "01019012480"
XMP = (
    '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Kari Fiktivsen '
    + FNR
    + "</dc:creator></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end=\"w\"?>"
)


def _red_png() -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 20), False)
    pix.set_rect(pix.irect, (255, 0, 0))
    return pix.tobytes("png")


@pytest.fixture
def rich_pdf(tmp_path, pdf_path, terms_path):
    """The test PDF with personal data hidden in many places, saved with an
    incremental update so an older revision is in the file."""
    d = tmp_path / "rik æøå"
    d.mkdir()
    shutil.copy(terms_path, d / "termer.txt")
    doc = pymupdf.open(pdf_path)
    p1, p2 = doc[0], doc[1]

    phone_rect = p1.search_for("58 01 23 45")[0]
    p1.insert_image(phone_rect + (-4, -2, 4, 2), stream=_red_png(), overlay=False)
    fnr_rect = p2.search_for("15068527101")[0]
    p2.draw_rect(fnr_rect + (-2, -1, 2, 1), color=None, fill=(0, 0.8, 0), overlay=False)

    p1.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(300, 148, 500, 160),
                    "uri": "mailto:kari.fiktivsen@example.no"})
    p1.add_text_annot((400, 400), f"Notat: fnr {FNR}, ring 58 01 23 45")
    fa = p2.add_freetext_annot(pymupdf.Rect(60, 300, 400, 330), "Kopi: kari.fiktivsen@example.no", fontsize=11)
    fa.update()
    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_name = "telefon"
    w.field_value = "+47 58 98 76 54"
    w.rect = pymupdf.Rect(60, 350, 300, 370)
    w.text_fontsize = 11
    p2.add_widget(w)
    doc.embfile_add("vedlegg.txt", f"Skjult vedlegg {FNR} kari.fiktivsen@example.no".encode())
    doc.set_metadata({"author": "Kari Fiktivsen", "title": f"Sak om {FNR}",
                      "subject": "58 01 23 45", "keywords": "kari.fiktivsen@example.no"})
    doc.set_xml_metadata(XMP)
    first = d / "rik.pdf"
    doc.save(first)
    doc.close()

    # incremental revision on top: the old revision keeps the old title
    doc = pymupdf.open(first)
    doc.set_metadata(dict(doc.metadata, title="Ny tittel"))
    doc.saveIncr()
    doc.close()
    assert open(first, "rb").read().count(b"%%EOF") == 2
    return d, first


def test_everything_hidden_is_removed(capsys, rich_pdf):
    d, pdf = rich_pdf
    out_dir = d / "ut"
    code, rep, err = run(capsys, "finn", pdf, "--terms", d / "termer.txt", "--out", out_dir)
    assert code == 0, err
    plan = json.loads(open(rep["outputs"][0]["path"], encoding="utf-8").read())
    found = {(t["type"], t["side"]) for t in plan["treff"]}
    # flattened free text and form field values are found as well
    assert ("epost", 2) in found
    assert ("telefon", 2) in found
    assert len([t for t in plan["treff"] if t["type"] == "telefon" and t["side"] == 2]) == 2

    code, rep, err = run(capsys, "sladd", pdf, "--plan", rep["outputs"][0]["path"], "--out", out_dir)
    assert code == 0, err
    out = rep["outputs"][0]["path"]

    for value in (FNR, "010190 12480", "58 01 23 45", "+47 58 98 76 54", "58987654",
                  "kari.fiktivsen@example.no", "Kari Fiktivsen", "15068527101"):
        assert not contains(out, value), value
    assert contains(out, "15068527102")

    raw = open(out, "rb").read()
    assert raw.count(b"%%EOF") == 1
    doc = pymupdf.open(out)
    try:
        meta = {k: v for k, v in doc.metadata.items() if k not in ("format", "encryption")}
        assert not any(meta.values()), meta
        assert not doc.get_xml_metadata()
        assert doc.embfile_count() == 0
        assert not doc.is_form_pdf
        for page in doc:
            assert page.first_annot is None
            assert page.first_widget is None
            assert not [l for l in page.get_links() if "kari" in str(l.get("uri", ""))]
        # every object, decompressed, is free of the values
        for xref in range(1, doc.xref_length()):
            src = doc.xref_object(xref).lower()
            stream = (doc.xref_stream(xref) or b"").lower() if doc.xref_is_stream(xref) else b""
            for needle in ("kari", FNR, "fiktivsen", "58 01 23 45"):
                assert needle not in src, (xref, needle)
                assert needle.encode() not in stream, (xref, needle)
        # vector graphics under the redaction are gone (green box)
        greens = [g for g in doc[1].get_drawings() if g.get("fill") and
                  tuple(round(c, 1) for c in g["fill"]) == (0.0, 0.8, 0.0)]
        assert greens == []
        # image pixels under the box are blanked: the image is no longer all red
        imgs = doc[0].get_images(full=True)
        for img in imgs:
            pix = pymupdf.Pixmap(doc, img[0])
            if pix.n >= 3:
                samples = pix.samples
                reds = sum(
                    1 for i in range(0, len(samples), pix.n)
                    if samples[i:i + 3] == b"\xff\x00\x00"
                )
                assert reds < pix.width * pix.height
    finally:
        doc.close()


def test_verify_rejects_multiple_revisions(pdf_path, tmp_path):
    doc = pymupdf.open(pdf_path)
    doc.set_metadata({})
    doc.del_xml_metadata()
    p = tmp_path / "a.pdf"
    doc.save(p)
    doc.close()
    doc = pymupdf.open(p)
    doc.set_metadata({"title": ""})
    doc.saveIncr()
    doc.close()
    data = p.read_bytes()
    assert data.count(b"%%EOF") == 2
    findings, _ = verify(data, {}, [], set())
    assert any("revisjon" in f for f in findings)


def test_verify_rejects_metadata(pdf_path):
    doc = pymupdf.open(pdf_path)
    doc.set_metadata({"author": "Kari Fiktivsen"})
    data = doc.tobytes(garbage=4, clean=True)
    doc.close()
    v = Value("term", "kari fiktivsen")
    findings, _ = verify(data, {}, [(v, 1)], {v})
    assert any("metadata" in f.lower() for f in findings)
    assert any("teksten fra PyMuPDF" in f for f in findings)


def test_verify_finds_value_in_objects(pdf_path):
    doc = pymupdf.open(pdf_path)
    doc.set_metadata({})
    doc.del_xml_metadata()
    doc.embfile_add("x.txt", b"hemmelig 58012345")
    data = doc.tobytes(garbage=4, clean=True)
    doc.close()
    v = Value("telefon", "58 01 23 45")
    findings, _ = verify(data, {}, [(v, 1)], {v})
    assert any("PDF-objekt" in f for f in findings)
    assert any("innebygde filer" in f for f in findings)


def test_redaction_options_are_the_strong_ones():
    assert core.REDACT_OPTIONS["text"] == pymupdf.PDF_REDACT_TEXT_REMOVE
    assert core.REDACT_OPTIONS["images"] == pymupdf.PDF_REDACT_IMAGE_PIXELS
    assert core.REDACT_OPTIONS["graphics"] == pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
