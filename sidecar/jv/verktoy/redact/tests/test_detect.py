"""Detection rules: mod 11, D-nummer, phone groupings, boundaries."""

import pytest

from jv_redact.detect import PageText, find_in_page, fnr_type, valid_fnr


def _hits(text, terms=()):
    pt = PageText(text, [(0.0, 0.0, 1.0, 1.0) if c != "\n" else None for c in text],
                  [0 if c != "\n" else -1 for c in text])
    return [(h.type, h.text, h.normalized) for h in find_in_page(pt, 1, terms)]


def test_fasit_control_digits(fasit):
    for item in fasit:
        if item["type"] in ("fodselsnummer", "d_nummer"):
            assert valid_fnr(item["normalisert"]), item
            assert fnr_type(item["normalisert"]) == item["type"]
        if item["type"] == "ugyldig_11_siffer":
            assert not valid_fnr(item["normalisert"])


@pytest.mark.parametrize("number", ["01019012481", "01019012490", "1234567890", "0101901248a"])
def test_invalid_numbers(number):
    assert not valid_fnr(number)


def test_d_nummer_type():
    assert fnr_type("41038815278") == "d_nummer"
    assert fnr_type("01019012480") == "fodselsnummer"


@pytest.mark.parametrize(
    "text",
    ["fnr 01019012480.", "fnr 010190 12480.", "fnr 010190\n12480 her", "fnr 010190 12480"],
)
def test_fnr_with_and_without_space(text):
    assert ("fodselsnummer", "010190 12480" if not text.startswith("fnr 01019012480") else "01019012480",
            "01019012480") in _hits(text)


@pytest.mark.parametrize(
    "text",
    [
        "nr 0101901248012",  # longer digit run
        "nr 9901019012480",
        "nr 01019012480,5",
        "nr 1-01019012480",  # bound to a longer number token
        "nr 01019012480-7",
        "nr 00000000000",  # passes mod 11, but day/month 00
        "nr 15068527102",  # wrong control digit
    ],
)
def test_no_fnr_in_longer_or_wrong(text):
    assert not [h for h in _hits(text) if h[0] in ("fodselsnummer", "d_nummer")]


@pytest.mark.parametrize(
    "text,shown",
    [
        ("fnr 2 902 924 180 3 her", "2 902 924 180 3"),
        ("fnr 0101 9012480.", "0101 9012480"),
        ("fnr 01 01 90 124 80", "01 01 90 124 80"),
    ],
)
def test_fnr_with_unusual_grouping(text, shown):
    hits = [h for h in _hits(text) if h[0] in ("fodselsnummer", "d_nummer")]
    assert [h[1] for h in hits] == [shown]
    assert not [h for h in _hits(text) if h[0] == "telefon"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("tlf 58012345.", ("58012345", "58012345")),
        ("tlf 58 01 23 45.", ("58 01 23 45", "58012345")),
        ("tlf 580 12 345.", ("580 12 345", "58012345")),
        ("tlf 5801 2345.", ("5801 2345", "58012345")),
        ("tlf +47 58 98 76 54.", ("+47 58 98 76 54", "+4758987654")),
        ("tlf +4758987654.", ("+4758987654", "+4758987654")),
        ("tlf 0047 58987654.", ("0047 58987654", "+4758987654")),
        ("tlf 0047 58 98 76 54", ("0047 58 98 76 54", "+4758987654")),
    ],
)
def test_phone_formats(text, expected):
    assert ("telefon",) + expected in _hits(text)


@pytest.mark.parametrize(
    "text",
    [
        "fnr 01019012480",
        "fnr 010190 12480",
        "ref 15068527102",
        "tall 123456789",
        "tall 5801234567",
        "beløp 45 000 kroner",
        "beløp 12 345 678 kroner",
        "sak 2026/1234 og 3. mars 2026",
        "desimal 1,58012345",
    ],
)
def test_no_phone_inside_other_numbers(text):
    assert not [h for h in _hits(text) if h[0] == "telefon"]


def test_email_and_terms():
    hits = _hits("Skriv til Kari.Fiktivsen@example.no eller KARI\nFIKTIVSEN, ikke Karine.", ["Kari Fiktivsen"])
    assert ("epost", "Kari.Fiktivsen@example.no", "kari.fiktivsen@example.no") in hits
    assert ("term", "KARI FIKTIVSEN", "Kari Fiktivsen") in hits
    assert len([h for h in hits if h[0] == "term"]) == 1
