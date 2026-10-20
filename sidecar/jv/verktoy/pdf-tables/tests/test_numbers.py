import pytest

from jv_pdf_tables.numbers import parse_number


@pytest.mark.parametrize(
    "text, value",
    [
        ("1 234 567,50", 1234567.5),
        ("1 234 567,50", 1234567.5),
        ("1 234 567,50", 1234567.5),
        ("1 234,5", 1234.5),
        ("1234,25", 1234.25),
        ("−145 320,40", -145320.4),
        ("-410 000,00", -410000.0),
        ("– 12", -12),
        ("(51 499,75)", -51499.75),
        ("( 12 )", -12),
        ("0,00", 0.0),
        ("1000", 1000),
        ("12", 12),
    ],
)
def test_certain_numbers(text, value):
    parsed = parse_number(text)
    assert parsed is not None
    assert parsed.value == pytest.approx(value)
    assert not parsed.uncertain


def test_integer_stays_int_and_decimal_is_float():
    assert isinstance(parse_number("1 000").value, int)
    assert isinstance(parse_number("1 000,00").value, float)


@pytest.mark.parametrize(
    "text, value",
    [("1.234.567,50", 1234567.5), ("12.5", 12.5), ("12-", -12)],
)
def test_uncertain_numbers(text, value):
    parsed = parse_number(text)
    assert parsed is not None
    assert parsed.value == pytest.approx(value)
    assert parsed.uncertain


@pytest.mark.parametrize(
    "text",
    ["", None, "Oppvekst", "0301", "12 34", "1 2345,00", "(−12)", "abc 12", "12,5 kr", "-"],
)
def test_not_numbers(text):
    assert parse_number(text) is None
