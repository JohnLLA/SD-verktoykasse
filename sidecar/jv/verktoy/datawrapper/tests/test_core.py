"""Unit tests of the rules (run in process)."""

from datetime import date, datetime

import pytest

from jv_datawrapper.analysis import (
    _header_row_count,
    convert_value,
    find_blocks,
    find_tables,
    format_number,
    is_year,
)
from jv_datawrapper.reading import Sheet, _build_sheet, col_letter, decode_text, detect_delimiter


@pytest.mark.parametrize(
    "value, text",
    [
        (1234567.5, "1234567.5"),
        (12.0, "12"),
        (0.1 + 0.2, "0.3"),
        (-0.0, "0"),
        (1e16, "10000000000000000"),
        (1.5e-7, "0.00000015"),
        (42, "42"),
    ],
)
def test_format_number(value, text):
    assert format_number(value) == text


@pytest.mark.parametrize(
    "value, text, kind",
    [
        ("1 234 567,50", "1234567.5", "num"),
        ("1 234", "1234", "num"),
        ("−12", "-12", "num"),
        ("(12)", "-12", "num"),
        ("12,5 %", "12.5", "num"),
        ("..", "", "symbol"),
        ("x", "", "symbol"),
        ("0301", "0301", "text"),
        ("12,5 kr", "12,5 kr", "text"),
        (date(2024, 1, 15), "2024-01-15", "date"),
        (datetime(2024, 1, 15, 13, 5), "2024-01-15 13:05", "date"),
        (None, "", "empty"),
    ],
)
def test_convert_value(value, text, kind):
    c = convert_value(value)
    assert (c.text, c.kind) == (text, kind)


def test_ambiguous_numbers_are_flagged():
    assert convert_value("1.234").uncertain
    assert convert_value("1.234").text == "1234"
    assert convert_value("12.5").uncertain
    assert not convert_value("1 234,5").uncertain


def test_years():
    assert is_year(2023) and is_year(2023.0) and is_year("2023")
    assert not is_year(1850) and not is_year("20234") and not is_year(True)


def test_delimiter_detection():
    assert detect_delimiter("a;b;c\n1,5;2;3\n4;5,5;6\n") == ";"
    assert detect_delimiter("a,b,c\n1,2,3\n") == ","
    assert detect_delimiter("a\tb\n1\t2\n") == "\t"
    assert detect_delimiter('"a;b",c\n"1;2",3\n') == ","


def test_decode_text():
    assert decode_text("Ø;1".encode("utf-8")) == ("Ø;1", "UTF-8")
    assert decode_text("Ø;1".encode("cp1252")) == ("Ø;1", "Windows-1252")
    assert decode_text(b"\xef\xbb\xbfA") == ("A", "UTF-8 med BOM")
    assert decode_text("Å".encode("utf-16")) == ("Å", "UTF-16")


def test_col_letter():
    assert [col_letter(i) for i in (0, 25, 26, 701, 702)] == ["A", "Z", "AA", "ZZ", "AAA"]


def test_blocks_split_on_empty_rows_and_columns():
    occ = [
        [True, True, False, True],
        [True, True, False, True],
        [False, False, False, False],
        [True, False, False, False],
    ]
    assert find_blocks(occ) == [(0, 2, 0, 2), (0, 2, 3, 4), (3, 4, 0, 1)]


def test_header_rows_with_years():
    assert _header_row_count([["Region", 2022, 2023], ["Aby", 5, 6]]) == 1
    assert _header_row_count([["", 2022, 2022], ["Region", "M", "K"], ["Aby", 5, 6]]) == 2
    assert _header_row_count([["År", "Antall"], [2019, 5]]) == 1
    assert _header_row_count([[1, 2], [3, 4]]) == 0
    assert _header_row_count([["a", "b"], ["c", "d"]]) == 1


def _sheet(rows):
    cells = {(r, c): v for r, row in enumerate(rows) for c, v in enumerate(row) if v is not None}
    return _build_sheet("Ark", cells, set(), set(), [], set())


def test_title_rows_and_notes_inside_one_block():
    s = _sheet(
        [
            ["Tittel"],
            ["Navn", "Tall"],
            ["a", 1],
            ["b", 2],
            ["Kilde: Oppdiktet"],
            ["1) En fotnote"],
        ]
    )
    (t,) = find_tables(s)
    assert t.title_lines == ["Tittel"]
    assert t.note_lines == ["Kilde: Oppdiktet", "1) En fotnote"]
    assert (t.r0, t.r1) == (1, 4)


def test_one_column_lists_are_not_tables():
    s = _sheet([["bare"], ["en"], ["kolonne"]])
    assert find_tables(s) == []


def test_empty_sheet():
    assert isinstance(_sheet([]), Sheet)
    assert find_tables(_sheet([])) == []
