"""Decode the strings stored in PDF objects and content streams.

Used by the post-check to run the detector on everything in the file, not
only on the extracted page text. Literal strings (with octal and other
escapes), hex strings (any case), names (#xx escapes) and comments are
decoded; text strings are read as UTF-16BE/LE or UTF-8 when they start
with a byte order mark, and as PDFDocEncoding otherwise.
"""

from __future__ import annotations

import re

_PDFDOC_HIGH = {
    0x80: "•", 0x81: "†", 0x82: "‡", 0x83: "…", 0x84: "—",
    0x85: "–", 0x86: "ƒ", 0x87: "⁄", 0x88: "‹", 0x89: "›",
    0x8A: "−", 0x8B: "‰", 0x8C: "„", 0x8D: "“", 0x8E: "”",
    0x8F: "‘", 0x90: "’", 0x91: "‚", 0x92: "™", 0x93: "ﬁ",
    0x94: "ﬂ", 0x95: "Ł", 0x96: "Œ", 0x97: "Š", 0x98: "Ÿ",
    0x99: "Ž", 0x9A: "ı", 0x9B: "ł", 0x9C: "œ", 0x9D: "š",
    0x9E: "ž", 0xA0: "€",
}

_WS = b" \t\r\n\f\x00"
_DELIM = b"()<>[]{}/%"
_ESCAPES = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
_NUM_RE = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
_EI_RE = re.compile(rb"[ \t\r\n\f\x00]EI(?=[ \t\r\n\f\x00]|$)")


def decode_pdf_string(raw: bytes) -> str:
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", "replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace")
    return "".join(_PDFDOC_HIGH.get(b, chr(b)) for b in raw)


def _literal(data: bytes, i: int) -> tuple[bytes, int]:
    """Parse a literal string starting after '('. Returns (bytes, next index)."""
    out = bytearray()
    depth = 1
    n = len(data)
    while i < n:
        c = data[i]
        if c == 0x5C:  # backslash
            i += 1
            if i >= n:
                break
            e = data[i]
            if e in _ESCAPES:
                out.append(_ESCAPES[e])
                i += 1
            elif 0x30 <= e <= 0x37:
                j = i
                while j < n and j < i + 3 and 0x30 <= data[j] <= 0x37:
                    j += 1
                out.append(int(data[i:j], 8) & 0xFF)
                i = j
            elif e == 0x0D:  # line continuation
                i += 1
                if i < n and data[i] == 0x0A:
                    i += 1
            elif e == 0x0A:
                i += 1
            else:
                out.append(e)
                i += 1
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
            if depth == 0:
                return bytes(out), i + 1
        out.append(c)
        i += 1
    return bytes(out), i


def _hex(data: bytes, i: int) -> tuple[bytes, int]:
    j = data.find(b">", i)
    if j < 0:
        j = len(data)
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", data[i:j])
    if len(digits) % 2:
        digits += b"0"
    return bytes.fromhex(digits.decode("ascii")), j + 1


def _name(data: bytes, i: int) -> tuple[str, int]:
    j = i
    n = len(data)
    while j < n and data[j] not in _WS and data[j] not in _DELIM:
        j += 1
    raw = re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), data[i:j])
    try:
        return raw.decode("utf-8"), j
    except UnicodeDecodeError:
        return raw.decode("latin-1"), j


def text_pieces(data: bytes, content: bool = False) -> list[str]:
    """Decoded strings, names and comments in PDF syntax, in order.

    Strings inside one array (e.g. a TJ array with kerning) are joined
    without separator, because they are one piece of text, except where a
    large adjustment (>= 250/1000 em) makes a visible gap: there a space.
    content=True skips inline image data (BI ... ID <binary> EI).
    """
    pieces: list[str] = []
    stack: list[list[str]] = []
    i = 0
    n = len(data)

    def add(text: str) -> None:
        if stack:
            stack[-1].append(text)
        elif text:
            pieces.append(text)

    while i < n:
        c = data[i]
        if c == 0x28:  # (
            raw, i = _literal(data, i + 1)
            add(decode_pdf_string(raw))
        elif c == 0x3C:  # <
            if i + 1 < n and data[i + 1] == 0x3C:
                i += 2
            else:
                raw, i = _hex(data, i + 1)
                add(decode_pdf_string(raw))
        elif c == 0x5B:  # [
            stack.append([])
            i += 1
        elif c == 0x5D:  # ]
            joined = "".join(stack.pop()) if stack else ""
            add(joined)
            i += 1
        elif stack and (c in b"+-." or 0x30 <= c <= 0x39):
            # a number inside an array: in a TJ array a large adjustment
            # (a quarter em or more) is a visible gap, kept as a space
            m = _NUM_RE.match(data, i)
            if m:
                try:
                    if abs(float(m.group(0))) >= 250:
                        stack[-1].append(" ")
                except ValueError:
                    pass
                i = m.end()
            else:
                i += 1
        elif c == 0x2F:  # /
            name, i = _name(data, i + 1)
            if name and not stack:
                pieces.append(name)
        elif c == 0x25:  # % comment
            j = i + 1
            while j < n and data[j] not in b"\r\n":
                j += 1
            pieces.append(data[i + 1 : j].decode("latin-1"))
            i = j
        elif (
            content
            and c == 0x49  # I
            and data[i : i + 2] == b"ID"
            and (i == 0 or data[i - 1] in _WS)
            and (i + 2 >= n or data[i + 2] in _WS)
        ):
            m = _EI_RE.search(data, i + 2)
            i = m.end() if m else n
        else:
            i += 1
    while stack:
        pieces.append("".join(stack.pop()))
    return pieces
