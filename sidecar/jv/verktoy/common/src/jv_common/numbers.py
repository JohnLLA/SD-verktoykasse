"""Parsing of Norwegian number formats (shared by pdf-tables and datawrapper).

Certain formats (stored without comment):
  1 234 567,50   thousands separated by space, U+00A0, U+202F or U+2009
  1234567,5      no separator
  −12 / -12      minus as U+2212, hyphen or en dash
  (12)           parentheses mean negative
Uncertain formats (stored as number, original text kept in a comment):
  1.234.567,50   dot as thousands separator
  12.5           dot as decimal sign
  12-            trailing minus
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_SPACES = "     "
_MINUS = "-−–"

_SPACE_RE = f"[{_SPACES}]"
# 1 234 567 (space-grouped) or plain digits
_INT_GROUPED = rf"\d{{1,3}}(?:{_SPACE_RE}\d{{3}})+"
_INT_PLAIN = r"\d+"
_CERTAIN_RE = re.compile(rf"^(?:{_INT_GROUPED}|{_INT_PLAIN})(?:,\d+)?$")
_DOT_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$")
_DOT_DECIMAL_RE = re.compile(r"^\d+\.\d+$")


@dataclass(frozen=True)
class ParsedNumber:
    value: int | float
    uncertain: bool


def _to_number(text: str) -> int | float:
    dec = Decimal(text)
    if dec == dec.to_integral_value() and "." not in text:
        return int(dec)
    return float(dec)


def parse_number(text: str | None) -> ParsedNumber | None:
    """Return the number in a cell text, or None if it is not a number.

    Integers with a leading zero (e.g. "0301") are treated as codes and
    left as text.
    """
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None

    negative = False
    uncertain = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    if s and s[0] in _MINUS:
        if negative:
            return None
        negative = True
        s = s[1:].strip(_SPACES)
    elif s and s[-1] in _MINUS and len(s) > 1:
        if negative:
            return None
        negative = True
        uncertain = True
        s = s[:-1].strip(_SPACES)
    if not s:
        return None

    if _CERTAIN_RE.match(s):
        int_part = s.split(",")[0]
        digits = re.sub(_SPACE_RE, "", int_part)
        if len(digits) > 1 and digits.startswith("0") and "," not in s:
            return None  # a code like "0301", keep as text
        canonical = re.sub(_SPACE_RE, "", s).replace(",", ".")
    elif _DOT_THOUSANDS_RE.match(s):
        uncertain = True
        canonical = s.replace(".", "").replace(",", ".")
    elif _DOT_DECIMAL_RE.match(s):
        uncertain = True
        canonical = s
    else:
        return None

    try:
        value = _to_number(canonical)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    return ParsedNumber(value=value, uncertain=uncertain)
