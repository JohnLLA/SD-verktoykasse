"""Seventh round: table neighbour columns are not listed as candidates, and
4.2.5 account numbers that pass the fnr check are not reported as fnr, while
real numbers (with spaces, hyphen or in one piece) are still found and
redacted. PDFs are generated here (synthetic data)."""

import pymupdf
import pytest
from jv_redact.detect import find_in_string, page_text, scan_page, valid_fnr
from test_runde2 import _assert_gone, _save
from test_runde5 import _finn, _sladd

REAL = ["15068527101", "01019012480"]  # invented, valid mod 11
# 4.2.5 accounts that pass the fnr control digits
ACCOUNTS = ["1001.56.78939", "1001.31.78998", "1002.56.78929"]


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "runde7 æøå"
    d.mkdir()
    (d / "termer.txt").write_text("Kari Fiktivsen\n", encoding="utf-8")
    return d


def _table_pdf(folder, name, with_real):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    rows = [
        ("Løpenr", "Dato", "Saksnr", "Beløp", "Konto"),
        ("125", "12.03.2026", "2026/3750", "285", ACCOUNTS[0]),
        ("126", "27.01.2026", "2026/2911", "293", ACCOUNTS[1]),
        ("7", "23.04.2026", "2026/1182", "9 041", ACCOUNTS[2]),
        ("2300", "15068", "9 041 262", "9106", "4156.34.18654"),
    ]
    y = 80
    for row in rows:
        for x, cell in zip((72, 130, 220, 310, 370), row):
            page.insert_text((x, y), cell, fontsize=10)  # one text object per cell
        y += 16
    if with_real:
        page.insert_text((72, y + 20), "Kontakt Kari Fiktivsen: fnr 150685 27101", fontsize=11)
        page.insert_text((72, y + 40), "Andre: 15068527101 og 150685-27101", fontsize=11)
        page.insert_text((72, y + 60), "Sak: 010190 12480", fontsize=11)
    return _save(doc, folder / name)


@pytest.mark.parametrize("account", ACCOUNTS)
def test_accounts_pass_fnr_check_but_are_not_reported(account):
    assert valid_fnr(account.replace(".", ""))
    assert not [h for h in find_in_string(f"Konto {account} betalt", []) if h[0] != "term"]
    assert not [h for h in find_in_string(f"Konto {account.replace('.', ' ')}", []) if h[0] != "term"]


@pytest.mark.parametrize("text", ["fnr 150685 27101", "fnr 15068527101", "fnr 150685-27101",
                                  "Konto 1001.56.78939, fnr 15068527101"])
def test_real_fnr_still_found(text):
    found = [h for h in find_in_string(text, []) if h[0] == "fodselsnummer"]
    assert [h[2] for h in found] == ["15068527101"]


def test_neighbour_columns_give_no_candidates(capsys, folder):
    pdf = _table_pdf(folder, "tabell uten.pdf", with_real=False)
    with pymupdf.open(pdf) as d:
        hits, rejected = scan_page(page_text(d[0]), 1, [])
    assert hits == []
    assert all(r.quiet for r in rejected)  # none of them reach the plan
    rep, _path, plan = _finn(capsys, folder, pdf)
    assert plan["treff"] == []
    assert rep["summary"].startswith("Fant ingen treff")


def test_table_with_real_numbers_end_to_end(capsys, folder):
    pdf = _table_pdf(folder, "tabell med.pdf", with_real=True)
    _rep, plan_path, plan = _finn(capsys, folder, pdf)
    real = [t for t in plan["treff"] if t["type"] == "fodselsnummer"]
    assert sorted(t["tekst"] for t in real) == [
        "010190 12480", "150685 27101", "150685-27101", "15068527101"]
    assert all(t["sladd"] and not t.get("forkastet") for t in plan["treff"])
    assert not any(t["normalisert"].startswith("1001") for t in plan["treff"])
    code, rep, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    out = rep["outputs"][0]["path"]
    _assert_gone(out, *REAL, "Kari Fiktivsen")
    with pymupdf.open(out) as d:
        text = d[0].get_text()
    assert "12.03.2026" in text and ACCOUNTS[0] in text


# ------------------------------------------- split fnr is never invisible

FNR = "15068527101"
SPLITS = [(6, 5), (3, 3, 5), (3, 4, 4), (4, 4, 3), (3, 3, 3, 2), (1, 10), (10, 1), (2, 9), (4, 7),
          (5, 6), (2, 2, 7), (11,)]


def _split(parts):
    out, i = [], 0
    for n in parts:
        out.append(FNR[i:i + n])
        i += n
    return out


@pytest.mark.parametrize("gap", [40, 90, 200])
@pytest.mark.parametrize("parts", SPLITS, ids=lambda p: "+".join(map(str, p)))
def test_split_fnr_is_always_in_plan(capsys, folder, parts, gap):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    x = 72
    for piece in _split(parts):
        page.insert_text((x, 100), piece, fontsize=10)
        x += 6 * len(piece) + gap
    pdf = _save(doc, folder / f"delt {'-'.join(map(str, parts))} {gap}.pdf")
    _rep, plan_path, plan = _finn(capsys, folder, pdf)
    assert FNR in [t["normalisert"] for t in plan["treff"]]
    for t in plan["treff"]:
        t["sladd"] = True
    code, rep, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    _assert_gone(rep["outputs"][0]["path"], FNR)


def test_silent_candidates_warn_in_finn_and_sladd(capsys, folder):
    pdf = _table_pdf(folder, "stille.pdf", with_real=False)
    rep, _p, plan = _finn(capsys, folder, pdf)
    assert plan["treff"] == []
    assert "veiledning" in plan
    code, rep2, err = _sladd(capsys, folder, pdf, plan)
    assert code == 0, err
    if rep.get("warnings"):
        assert any("nabokolonner" in w for w in rep2["warnings"])


# ---------------------------------- separators inside cells + cell borders

SEP_CELLS = [
    ["150.685.", "27101"], ["150.", "685.27101"], ["15.068.", "527.101"],
    ["150,685", "27101"], ["150.685.271.", "01"], ["150.685", "27101"],
    ["1.506.852", "7101"], ["15,06,85", "27101"],
]


@pytest.mark.parametrize("gap", [40, 150])
@pytest.mark.parametrize("cells", SEP_CELLS, ids=lambda c: "|".join(c))
def test_separators_inside_cells_never_invisible(capsys, folder, cells, gap):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    x = 72
    for piece in cells:
        page.insert_text((x, 100), piece, fontsize=10)
        x += 6 * len(piece) + gap
    pdf = _save(doc, folder / f"sep {abs(hash(tuple(cells)))} {gap}.pdf")
    _rep, _p, plan = _finn(capsys, folder, pdf)
    assert FNR in [t["normalisert"] for t in plan["treff"]]


@pytest.mark.parametrize("cells", [["125", "12.03.2026"], ["7", "1.5.2026"], ["2026", "/2911"],
                                   ["99", "2026/2911"], ["1 5068", "527,10"], ["150", "685.271,01"]],
                         ids=lambda c: "|".join(c))
def test_dates_case_numbers_and_amounts_stay_quiet(folder, cells):
    from jv_redact.detect import scan_text  # noqa: F401
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    x = 72
    for piece in cells:
        page.insert_text((x, 100), piece, fontsize=10)
        x += 6 * len(piece) + 120
    pdf = _save(doc, folder / f"stille {abs(hash(tuple(cells)))}.pdf")
    with pymupdf.open(pdf) as d:
        hits, rejected = scan_page(page_text(d[0]), 1, [])
    assert hits == []
    assert all(r.quiet for r in rejected)
