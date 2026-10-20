"""The command line against the synthetic files in testdata/datawrapper.

Every fasit is the expected TSV, byte for byte (scripts/lag_testdata_datawrapper.py).
These tests also run against the packed binary (sidecar/build/pytest_packaged.py).
"""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from jv_datawrapper.cli import main

DATA = Path(__file__).resolve().parents[3] / "testdata" / "datawrapper"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(capsys, *args):
    code = main([str(a) for a in args])
    captured = capsys.readouterr()
    report = json.loads(captured.out) if code == 0 else None
    return code, report, captured


def fasit(name):
    return (DATA / name).read_bytes().decode("utf-8")


CASES = [
    ("ssb_befolkning.xlsx", [], "ssb_befolkning.fasit.tsv"),
    ("ssb_befolkning.xlsx", ["--med-sum"], "ssb_befolkning.med-sum.fasit.tsv"),
    ("to_overskriftsrader.xlsx", [], "to_overskriftsrader.fasit.tsv"),
    ("sumrader.xlsx", [], "sumrader.fasit.tsv"),
    ("sumrader.xlsx", ["--med-sum"], "sumrader.med-sum.fasit.tsv"),
    ("to_tabeller.xlsx", [], "to_tabeller.fasit.tsv"),
    ("to_tabeller.xlsx", ["--tabell", "1"], "to_tabeller.tabell1.fasit.tsv"),
    ("to_tabeller.xlsx", ["--ark", "Ark1", "--tabell", "2"], "to_tabeller.fasit.tsv"),
    ("skjult_rad.xlsx", [], "skjult_rad.fasit.tsv"),
    ("tall_som_tekst.xlsx", [], "tall_som_tekst.fasit.tsv"),
    ("semikolon_cp1252.csv", [], "semikolon_cp1252.fasit.tsv"),
    ("bytt.csv", [], "bytt.fasit.tsv"),
    ("bytt.csv", ["--bytt"], "bytt.bytt.fasit.tsv"),
    ("omsetning.xls", [], "omsetning.fasit.tsv"),
]


@pytest.mark.parametrize("name, extra, expected", CASES, ids=[f"{c[0]}{''.join(c[1])}" for c in CASES])
def test_tsv_matches_fasit_byte_for_byte(capsys, name, extra, expected):
    before = sha(DATA / name)
    code, report, captured = run(capsys, "lag", DATA / name, *extra, "--json")
    assert code == 0, captured.err
    assert report["tool"] == "datawrapper"
    assert report["datawrapper"]["tsv"].encode("utf-8") == fasit(expected).encode("utf-8")
    assert report["outputs"] == []
    assert sha(DATA / name) == before  # the original is never changed


def test_ssb_title_source_notes_symbols_and_sum(capsys):
    code, report, _ = run(capsys, "lag", DATA / "ssb_befolkning.xlsx")
    assert code == 0
    d = report["datawrapper"]
    assert d["title"] == "Tabell 1. Folkemengde etter kommune. 1. januar"
    assert d["description"] == "Fiktive tall til test"
    assert d["source"] == "Statistisk sentralbyrå (fiktive tall)"
    assert d["notes"][:2] == ["¹ Ny kommune fra 2024.", "* Foreløpige tall."]
    assert d["notes"][2].startswith("Tegnforklaring")
    assert d["symbols"] == {".": 1, "..": 1, ":": 1, "-": 1, "x": 1}
    assert d["removed"]["sum_rows"] == ["Hele landet"]
    assert d["header_rows"] == 1
    assert [c["name"] for c in d["columns"]][:2] == ["Kommune", "2022"]
    assert [c["numeric"] for c in d["columns"]] == [False, True, True, True, True]
    assert d["rows"] == 5
    assert any("sumrad" in w for w in report["warnings"])
    assert any("«..»" in w for w in report["warnings"])
    assert report["summary"].startswith("Tabellen har 5 rader og 5 kolonner")


def test_two_header_rows_are_joined(capsys):
    code, report, _ = run(capsys, "lag", DATA / "to_overskriftsrader.xlsx")
    d = report["datawrapper"]
    assert d["header_rows"] == 2
    assert d["title"] == "Sysselsatte etter fylke og kjønn"
    assert d["source"] == "SSB (fiktive tall)"


def test_hierarchy_and_sums_are_reported(capsys):
    code, report, _ = run(capsys, "lag", DATA / "sumrader.xlsx")
    d = report["datawrapper"]
    assert d["filled_labels"] == 4
    assert d["removed"]["sum_rows"] == ["Nordfylke – Sum", "Sørfylke – Sum", "I alt"]
    assert d["removed"]["sum_columns"] == ["Totalt"]
    code, report, _ = run(capsys, "lag", DATA / "sumrader.xlsx", "--med-sum")
    d = report["datawrapper"]
    assert d["removed"]["sum_rows"] == [] and d["removed"]["sum_rows_found"]
    assert [c["sum"] for c in d["columns"]] == [False, False, False, False, True]


def test_hidden_rows_columns_and_sheets(capsys):
    code, report, _ = run(capsys, "lag", DATA / "skjult_rad.xlsx")
    d = report["datawrapper"]
    assert d["sheet"] == "Data"
    assert d["hidden_sheets"] == 1
    assert d["removed"]["hidden_rows"] == 1
    assert d["removed"]["hidden_columns"] == 1
    code, report, _ = run(capsys, "lag", DATA / "skjult_rad.xlsx", "--ark", "Oversikt")
    assert report["datawrapper"]["tsv"] == "Nøkkeltall\tVerdi\nKommuner\t3\nInnbyggere\t3600\n"
    code, _, captured = run(capsys, "lag", DATA / "skjult_rad.xlsx", "--ark", "Hjelpeark")
    assert code == 1 and "Fant ikke arket" in captured.err


def test_numbers_as_text_warnings(capsys):
    code, report, _ = run(capsys, "lag", DATA / "tall_som_tekst.xlsx")
    d = report["datawrapper"]
    assert d["uncertain_cells"] == ["C4", "D4"]
    text = " ".join(report["warnings"])
    assert "to måter" in text and "C4, D4" in text
    assert "prosenttegnet i 2 celler" in text
    assert "formatert som prosent" in text
    assert "feilverdi fra Excel" in text


def test_csv_detection_is_reported(capsys):
    code, report, _ = run(capsys, "analyser", DATA / "semikolon_cp1252.csv")
    d = report["datawrapper"]
    assert d["format"] == "csv"
    assert d["encoding"] == "Windows-1252"
    assert d["delimiter"] == "semikolon"
    code, report, _ = run(capsys, "analyser", DATA / "bytt.csv")
    assert report["datawrapper"]["encoding"] == "UTF-8 med BOM"
    assert report["datawrapper"]["delimiter"] == "komma"


def test_analyser_lists_sheets_tables_and_suggestions(capsys):
    code, report, _ = run(capsys, "analyser", DATA / "to_tabeller.xlsx", "--json")
    assert code == 0
    d = report["datawrapper"]
    assert d["suggested_sheet"] == "Ark1"
    (sheet,) = d["sheets"]
    assert sheet["suggested_table"] == 2
    t1, t2 = sheet["tables"]
    assert (t1["index"], t1["range"], t1["suggested"]) == (1, "A2:C5", False)
    assert (t2["index"], t2["range"], t2["suggested"]) == (2, "A9:C13", True)
    assert t1["title"] == "Tabell 1. Besøkende per måned"
    assert t2["headers"] == ["Type", "Antall", "Andel"]
    assert t2["source"] == "Fiktive tall"
    assert report["summary"] == "Fant 2 tabeller i 1 ark."


def test_analyser_picks_sheet_with_most_numbers_and_skips_hidden(capsys):
    code, report, _ = run(capsys, "analyser", DATA / "skjult_rad.xlsx")
    d = report["datawrapper"]
    assert [s["name"] for s in d["sheets"]] == ["Oversikt", "Data"]
    assert d["suggested_sheet"] == "Data"
    assert d["hidden_sheets"] == 1
    assert any("skjult ark" in w for w in report["warnings"])


def test_transpose_is_suggested(capsys):
    code, report, _ = run(capsys, "analyser", DATA / "bytt.csv")
    assert report["datawrapper"]["sheets"][0]["tables"][0]["transpose_suggested"] is True
    code, report, _ = run(capsys, "lag", DATA / "bytt.csv")
    assert report["datawrapper"]["transpose_suggested"] is True
    assert any("bytte rader og kolonner" in w for w in report["warnings"])
    code, report, _ = run(capsys, "analyser", DATA / "ssb_befolkning.xlsx")
    assert report["datawrapper"]["sheets"][0]["tables"][0]["transpose_suggested"] is False


def test_remove_columns(capsys):
    code, report, _ = run(capsys, "lag", DATA / "sumrader.xlsx", "--fjern-kolonne", "2", "--fjern-kolonne", "4")
    d = report["datawrapper"]
    assert d["tsv"].splitlines()[:2] == ["Fylke\tBarnehager", "Nordfylke\t12"]
    assert d["removed"]["columns"] == ["Kommune", "Skoler"]
    assert [c["removed"] for c in d["columns"]] == [False, True, False, True]
    code, _, captured = run(capsys, "lag", DATA / "sumrader.xlsx", "--fjern-kolonne", "9")
    assert code == 1 and "Kolonne 9 finnes ikke" in captured.err
    code, _, captured = run(capsys, "lag", DATA / "bytt.csv", "--fjern-kolonne", "1", "2", "3")
    assert code == 1 and "Minst én kolonne" in captured.err


def test_wrong_table_number(capsys):
    code, _, captured = run(capsys, "lag", DATA / "to_tabeller.xlsx", "--tabell", "3")
    assert code == 1
    assert "har 2 tabeller" in captured.err


def test_csv_file_utf8_comma_and_original_untouched(capsys, tmp_path):
    target = tmp_path / "ut.csv"
    code, report, _ = run(capsys, "lag", DATA / "ssb_befolkning.xlsx", "--csv", target)
    assert code == 0
    assert report["outputs"] == [{"path": str(target), "type": "csv"}]
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8").splitlines()
    assert lines[0] == "Kommune,2022,2023,2024,Endring 2023–2024 (%)"
    assert lines[1] == "3101 Nordby,12345,12401,12502,0.8"
    assert lines[2] == "3102 Sørvik¹,8210,8199,,"
    # An existing file is never overwritten.
    code, report, _ = run(capsys, "lag", DATA / "sumrader.xlsx", "--csv", target)
    assert report["outputs"][0]["path"] == str(tmp_path / "ut-2.csv")
    assert target.read_bytes() == raw


def test_csv_next_to_a_csv_original_never_replaces_it(capsys, tmp_path):
    src = tmp_path / "data.csv"
    shutil.copy(DATA / "semikolon_cp1252.csv", src)
    before = sha(src)
    code, report, _ = run(capsys, "lag", src, "--csv", src)
    assert code == 0
    assert report["outputs"][0]["path"] == str(tmp_path / "data-2.csv")
    assert sha(src) == before
    assert (tmp_path / "data-2.csv").read_text(encoding="utf-8").startswith("Kommune,Innbyggere,Andel over 67 år,Endring\n")


def test_csv_must_end_in_csv_and_folder_must_exist(capsys, tmp_path):
    code, _, captured = run(capsys, "lag", DATA / "bytt.csv", "--csv", tmp_path / "ut.txt")
    assert code == 1 and ".csv" in captured.err
    code, _, captured = run(capsys, "lag", DATA / "bytt.csv", "--csv", tmp_path / "finnes-ikke" / "ut.csv")
    assert code == 1 and "finnes ikke" in captured.err


@pytest.mark.parametrize(
    "name, message",
    [
        ("tom.xlsx", "Filen er tom"),
        ("tom.csv", "Filen er tom"),
        ("odelagt.xlsx", "ødelagt"),
        ("passord.xlsx", "passordbeskyttet"),
    ],
)
def test_empty_broken_and_protected_files(capsys, name, message):
    for cmd in ("analyser", "lag"):
        code, report, captured = run(capsys, cmd, DATA / name)
        assert code == 1
        assert message in captured.err
        assert "Traceback" not in captured.err


def test_too_large_and_wrong_type(capsys, tmp_path):
    big = tmp_path / "stor.csv"
    with open(big, "wb") as fh:
        fh.truncate(50 * 1024 * 1024 + 1)
    code, _, captured = run(capsys, "analyser", big)
    assert code == 1 and "50 MB" in captured.err
    ods = tmp_path / "regneark.ods"
    ods.write_bytes(b"PK\x03\x04")
    code, _, captured = run(capsys, "analyser", ods)
    assert code == 1 and "støttes ikke" in captured.err
    code, _, captured = run(capsys, "analyser", tmp_path / "finnes-ikke.xlsx")
    assert code == 1 and "Finner ikke" in captured.err


def test_stderr_has_only_progress_no_cell_content(capsys):
    code, report, captured = run(capsys, "lag", DATA / "ssb_befolkning.xlsx")
    assert code == 0
    lines = [ln for ln in captured.err.splitlines() if ln.strip()]
    assert lines and all(json.loads(ln).keys() == {"progress"} for ln in lines)
    assert json.loads(lines[-1])["progress"] == 1.0
    for content in ("Nordby", "Folkemengde", "Statistisk"):
        assert content not in captured.err


def test_bad_arguments_are_user_errors(capsys):
    code, _, captured = run(capsys, "lag", DATA / "bytt.csv", "--tabell", "en")
    assert code == 1
    code, _, captured = run(capsys, "finn", DATA / "bytt.csv")
    assert code == 1
