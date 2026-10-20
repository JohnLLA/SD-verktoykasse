"""Fourth contract check: phone numbers with wide spacing, names in the
genitive, and tables where numbers from neighbouring cells must not be
joined (synthetic postliste and budget). PDFs are generated here."""

import json

import pymupdf
import pytest
from redact_helpers import run
from test_runde2 import _assert_gone, _new, _save

from jv_redact.detect import find_in_string, page_text, scan_page, valid_fnr

FNR = "15068527101"
FNR2 = "29029241803"


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "runde4 æøå"
    d.mkdir()
    (d / "termer.txt").write_text("Kari Fiktivsen\nÅse Prøvesen\n", encoding="utf-8")
    return d


def _finn(capsys, folder, pdf):
    code, rep, err = run(capsys, "finn", pdf, "--terms", folder / "termer.txt", "--out", folder / "ut")
    assert code == 0, err
    path = rep["outputs"][0]["path"]
    return rep, path, json.loads(open(path, encoding="utf-8").read())


def _sladd(capsys, folder, pdf, plan_path):
    return run(capsys, "sladd", pdf, "--plan", plan_path, "--out", folder / "ut")


# ------------------------------------------------ 1: wide spacing in phones

GROUPINGS = [("58", "01", "23", "45"), ("580", "12", "345"), ("5801", "2345")]
SPACINGS = [" " * n for n in range(1, 7)] + ["\t", " \t "]


@pytest.mark.parametrize("groups", GROUPINGS)
@pytest.mark.parametrize("sep", SPACINGS)
def test_phone_with_wide_spacing(groups, sep):
    text = f"Telefon:{sep}{sep.join(groups)}."
    assert "58012345" in [h[2] for h in find_in_string(text, []) if h[0] == "telefon"], repr(text)


@pytest.mark.parametrize("sep", SPACINGS)
def test_phone_with_prefix_and_wide_spacing(sep):
    text = f"Tlf +47{sep}58{sep}98{sep}76{sep}54"
    assert "+4758987654" in [h[2] for h in find_in_string(text, []) if h[0] == "telefon"]


@pytest.mark.parametrize("sep", SPACINGS)
def test_fnr_with_wide_spacing_and_tab(sep):
    assert FNR2 in [h[2] for h in find_in_string(f"Fnr:{sep}290292{sep}41803", [])]


def test_wide_phone_end_to_end(capsys, folder):
    lines = ["Navn: Kari Fiktivsen"] + [
        f"Tlf {i}: " + (" " * n).join(g) for i, (g, n) in enumerate(
            [(g, n) for g in GROUPINGS for n in (2, 4, 6)])
    ]
    doc, _page = _new(lines)
    pdf = _save(doc, folder / "brei.pdf")
    _rep, plan_path, plan = _finn(capsys, folder, pdf)
    phones = [t for t in plan["treff"] if t["type"] == "telefon"]
    assert len(phones) == 9 and not [t for t in plan["treff"] if t.get("forkastet")]
    code, rep, err = _sladd(capsys, folder, pdf, plan_path)
    assert code == 0, err
    _assert_gone(rep["outputs"][0]["path"], "58012345", "Kari Fiktivsen")


# ------------------------------------------------------------ 2: genitive

GENITIVE = [
    ("Kari Fiktivsens søknad", "Kari Fiktivsens"),
    ("Kari Fiktivsen's søknad", "Kari Fiktivsen's"),
    ("Kari Fiktivsen’s søknad", "Kari Fiktivsen’s"),
    ("Kari Fiktivsen' bil", "Kari Fiktivsen'"),
    ("Kari Fiktivsen-saken", "Kari Fiktivsen-saken"),
    ("KARI FIKTIVSENS", "KARI FIKTIVSENS"),
]


@pytest.mark.parametrize("text,shown", GENITIVE)
def test_term_in_genitive(text, shown):
    hits = [h for h in find_in_string(text, ["Kari Fiktivsen"]) if h[0] == "term"]
    assert [(h[1], h[2]) for h in hits] == [(shown, "Kari Fiktivsen")]


def test_term_not_inside_other_words():
    assert not [h for h in find_in_string("Kari Fiktivsenius", ["Kari Fiktivsen"]) if h[0] == "term"]


def test_genitive_end_to_end(capsys, folder):
    doc, _page = _new(["Kari Fiktivsens søknad er mottatt.", "Åse Prøvesens advokat svarer.",
                       "Fiktivsen-saken behandles nå av Kari Fiktivsen."])
    pdf = _save(doc, folder / "genitiv.pdf")
    _rep, plan_path, plan = _finn(capsys, folder, pdf)
    shown = sorted(t["tekst"] for t in plan["treff"] if t["type"] == "term")
    assert shown == ["Kari Fiktivsen", "Kari Fiktivsens", "Åse Prøvesens"]
    code, rep, err = _sladd(capsys, folder, pdf, plan_path)
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, "Kari Fiktivsen", "Åse Prøvesen")
    with pymupdf.open(out) as d:
        text = d[0].get_text()
    assert "søknad er mottatt" in text and "advokat svarer" in text


# -------------------------------------------------------------- 3: tables

POSTLISTE = [
    ("Løpenr", "Dato", "Saksnr", "Beløp", "Konto"),
    ("125", "12.03.2026", "2026/3750", "285", "1425.31.00827"),
    ("126", "27.01.2026", "2026/2911", "293", "0799.46.69596"),
    ("127", "05.11.2026", "2026/8807", "906", "4156.34.18654"),
    ("7", "23.04.2026", "2026/1182", "783", "9931.52.47000"),
]
COLS = (72, 130, 220, 310, 370)


def _table(rows, cols, folder, name, extra=(), split=False):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 80
    for row in rows:
        for x, cell in zip(cols, row):
            page.insert_text((x, y), cell, fontsize=10)  # one text object per cell
        y += 16
    for line in extra:
        page.insert_text((72, y + 20), line, fontsize=11)
        y += 18
    if split:  # a real number in two cells far apart: still a rejected candidate
        page.insert_text((72, y + 20), "Fnr: 150685", fontsize=11)
        page.insert_text((300, y + 20), "27101", fontsize=11)
    return _save(doc, folder / name)


BUDGET = [("Post", "Regnskap", "Budsjett", "Avvik", "Endring")] + [
    (f"Post {i}", f"{9_041_262 + i * 7919:,}".replace(",", " "), f"{9_106 + i}",
     f"{707 + i}", f"{65_445 + i:,}".replace(",", " "))
    for i in range(30)
]
BUDGET_COLS = (72, 160, 260, 340, 400)


def test_account_numbers_are_not_fnr():
    assert valid_fnr("14253100827")  # passes mod 11 ...
    assert not [h for h in find_in_string("Konto 1425.31.00827", []) if h[0] != "term"]
    assert not [h for h in find_in_string("Konto 1425 31 00827", []) if h[0] != "term"]


@pytest.mark.parametrize("which", ["postliste", "budsjett"])
def test_tables_without_personal_data_give_no_hits(capsys, folder, which):
    if which == "postliste":
        pdf = _table(POSTLISTE, COLS, folder, "postliste.pdf")
    else:
        pdf = _table(BUDGET, BUDGET_COLS, folder, "budsjett.pdf")
    rep, _path, plan = _finn(capsys, folder, pdf)
    assert [t for t in plan["treff"] if not t.get("forkastet")] == []
    for f in plan["treff"]:
        assert f["forkastet"] is True and f["sladd"] is False
        assert f["grunn"] and f["type"] in ("fodselsnummer", "d_nummer", "telefon")


def test_postliste_cells_are_not_joined(folder):
    pdf = _table(POSTLISTE, COLS, folder, "postliste.pdf")
    with pymupdf.open(pdf) as doc:
        pt = page_text(doc[0])
        hits, rejected = scan_page(pt, 1, [])
    assert hits == []
    # "125" + "12.03.2026" would pass mod 11 when joined across the cells
    assert valid_fnr("12512032026")
    assert any(r.normalized == "12512032026" for r in rejected)


@pytest.mark.parametrize("which", ["postliste", "budsjett"])
def test_tables_with_personal_data_end_to_end(capsys, folder, which):
    extra = [f"Kontakt: Kari Fiktivsen, fnr {FNR}, tlf 58 01 23 45"]
    if which == "postliste":
        pdf = _table(POSTLISTE, COLS, folder, "postliste pii.pdf", extra)
    else:
        pdf = _table(BUDGET, BUDGET_COLS, folder, "budsjett pii.pdf", extra)
    rep, plan_path, plan = _finn(capsys, folder, pdf)
    assert sorted(t["type"] for t in plan["treff"] if not t.get("forkastet")) == [
        "fodselsnummer", "telefon", "term"]
    code, rep2, err = _sladd(capsys, folder, pdf, plan_path)
    assert code == 0, err  # pdftotext joins the cells, but forkastet is allowed
    out = rep2["outputs"][0]["path"]
    _assert_gone(out, FNR, "58012345", "Kari Fiktivsen")
    with pymupdf.open(out) as d:
        text = d[0].get_text()
    if which == "postliste":
        assert "12.03.2026" in text and "2026/3750" in text and "1425.31.00827" in text
    else:
        assert "9 041 262" in text


def test_rejected_candidates_are_reported(capsys, folder):
    pdf = _table(POSTLISTE, COLS, folder, "postliste.pdf", ["Kari Fiktivsen"], split=True)
    rep, _path, plan = _finn(capsys, folder, pdf)
    rejected = [t for t in plan["treff"] if t.get("forkastet")]
    assert rejected
    assert rep["summary"].startswith("Fant 1 treff")
    assert f"{len(rejected)} mulige fødselsnumre/telefonnumre ble IKKE merket" in rep["summary"]
    assert any("IKKE merket" in w for w in rep["warnings"])
    assert rep["outputs"][0]["forkastet"] == len(rejected)
    assert {"type", "tekst", "normalisert", "side", "utdrag", "grunn", "rektangler"} <= set(rejected[0])
    assert rejected[0]["rektangler"]


def test_wrapped_number_in_paragraph_still_found(folder):
    doc, page = _new(["Saken gjelder Kari Fiktivsen, med fødselsnummer 010190", "12480 og mer tekst."])
    pdf = _save(doc, folder / "brudd.pdf")
    with pymupdf.open(pdf) as d:
        hits, rejected = scan_page(page_text(d[0]), 1, [])
    assert "01019012480" in [h.normalized for h in hits]


def test_far_apart_on_same_line_is_rejected(folder):
    doc, page = _new(["Fnr: 150685"])
    page.insert_text((300, 72), "27101", fontsize=11)
    pdf = _save(doc, folder / "langt.pdf")
    with pymupdf.open(pdf) as d:
        hits, rejected = scan_page(page_text(d[0]), 1, [])
    assert FNR not in [h.normalized for h in hits]
    assert FNR in [r.normalized for r in rejected]


def test_no_personal_data_message(capsys, folder):
    doc, _page = _new(["Ingen personopplysninger her, bare tekst."])
    pdf = _save(doc, folder / "tom.pdf")
    rep, plan_path, plan = _finn(capsys, folder, pdf)
    assert plan["treff"] == []
    assert rep["summary"].startswith("Fant ingen treff")
    assert "Les gjennom dokumentet selv" in rep["summary"]
    code, r, err = _sladd(capsys, folder, pdf, plan_path)
    assert code == 0, err
    assert r["summary"].startswith("Ingen treff ble merket for sladding. Les gjennom dokumentet selv.")
    assert "personopplysninger" not in r["summary"]  # never "no personal data"
    with pymupdf.open(r["outputs"][0]["path"]) as d:
        assert "Ingen personopplysninger her" in d[0].get_text()
        assert not any(v for k, v in d.metadata.items() if k not in ("format", "encryption"))


def test_stacked_digits_are_found(capsys, folder):
    """One digit per line in a column (vertical text) is one number."""
    doc, page = _new(["Kari Fiktivsen"])
    for i, c in enumerate(FNR):
        page.insert_text((300, 140 + 12 * i), c, fontsize=11)
    pdf = _save(doc, folder / "loddrett.pdf")
    _rep, plan_path, plan = _finn(capsys, folder, pdf)
    assert FNR in [t["normalisert"] for t in plan["treff"]]
    code, rep, err = _sladd(capsys, folder, pdf, plan_path)
    assert code == 0, err
    _assert_gone(rep["outputs"][0]["path"], FNR)


def test_sladd_warns_about_rejected(capsys, folder):
    pdf = _table(POSTLISTE, COLS, folder, "postliste pii.pdf", ["Kari Fiktivsen"], split=True)
    _rep, plan_path, plan = _finn(capsys, folder, pdf)
    assert [t for t in plan["treff"] if t.get("forkastet")]
    code, rep, err = _sladd(capsys, folder, pdf, plan_path)
    assert code == 0, err
    assert any("står igjen i dokumentet" in w and "forkastet" in w for w in rep["warnings"])
    assert "IKKE sladdet" in rep["summary"]


# ------------------------------------- rejected candidates as plan entries


@pytest.fixture
def split_pdf(folder):
    """As c08g: fnr and phone split in two text pieces far apart on a line."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Til Kari Fiktivsen", fontsize=11)
    page.insert_text((72, 94), "Fnr: 150685", fontsize=11)
    page.insert_text((200, 94), "27101", fontsize=11)
    page.insert_text((72, 116), "Tlf: 58 01", fontsize=11)
    page.insert_text((200, 116), "23 45", fontsize=11)
    return _save(doc, folder / "to tekstbiter.pdf")


def _edit(folder, plan):
    p = folder / "endret.json"
    p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return p


def test_split_rejected_left_gives_warning(capsys, folder, split_pdf):
    rep, plan_path, plan = _finn(capsys, folder, split_pdf)
    rejected = [t for t in plan["treff"] if t.get("forkastet")]
    assert sorted(t["normalisert"] for t in rejected) == ["15068527101", "58012345"]
    assert all(t["sladd"] is False for t in rejected)
    assert rep["summary"].startswith("Fant 1 treff")
    assert "2 mulige fødselsnumre/telefonnumre ble IKKE merket for sladding" in rep["summary"]
    code, rep2, err = _sladd(capsys, folder, split_pdf, plan_path)
    assert code == 0, err
    assert "2 mulige fødselsnumre/telefonnumre ble IKKE sladdet" in rep2["summary"]
    assert any("IKKE sladdet" in w for w in rep2["warnings"])
    with pymupdf.open(rep2["outputs"][0]["path"]) as d:
        text = d[0].get_text()
    assert "150685" in text and "27101" in text  # left as the user chose


def test_split_rejected_set_to_true_is_redacted(capsys, folder, split_pdf):
    _rep, _path, plan = _finn(capsys, folder, split_pdf)
    for t in plan["treff"]:
        if t.get("forkastet"):
            t["sladd"] = True
    code, rep, err = _sladd(capsys, folder, split_pdf, _edit(folder, plan))
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, FNR, "58012345", "150685", "27101", "Kari Fiktivsen")
    assert "IKKE sladdet" not in rep["summary"]
    assert rep["outputs"][0]["sladdet"] == 3


@pytest.mark.parametrize("change", ["unflag", "flag_real", "move", "text"])
def test_rejected_entries_only_allow_sladd_to_change(capsys, folder, split_pdf, change):
    _rep, _path, plan = _finn(capsys, folder, split_pdf)
    rej = next(t for t in plan["treff"] if t.get("forkastet"))
    real = next(t for t in plan["treff"] if not t.get("forkastet"))
    if change == "unflag":
        rej["forkastet"] = False
        rej["sladd"] = True
    elif change == "flag_real":
        real["forkastet"] = True
    elif change == "move":
        rej["rektangler"] = [[0, 0, 600, 800]]
    else:
        rej["tekst"] = "150685 27102"
    code, _rep2, err = _sladd(capsys, folder, split_pdf, _edit(folder, plan))
    assert code == 1, change
    assert "ugyldig eller endret" in err
    assert list((folder / "ut").glob("*.pdf")) == []
