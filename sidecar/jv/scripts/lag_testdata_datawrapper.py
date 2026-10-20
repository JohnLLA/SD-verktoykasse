"""Generate the synthetic test files for `datawrapper` in testdata/datawrapper/.

All places, numbers and texts are made up. Every file gets a fasit: the TSV
the tool must produce, byte for byte (`<file>.fasit.tsv`, and for other
choices `<file>.<valg>.fasit.tsv`). The fasit is written here from the
expected values, not from the tool. Run from sidecar/jv:

    uv run --frozen --all-packages python scripts/lag_testdata_datawrapper.py

Needs only openpyxl (already in the workspace). The .xls file is written by
a small BIFF8/OLE2 writer below, so no extra package is needed. No network.
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "testdata" / "datawrapper"
FIXED = datetime(2026, 1, 15, 10, 30, 0)
NBSP = " "
NNBSP = " "
MINUS = "−"


def tsv(rows: list[list[str]]) -> str:
    return "".join("\t".join(r) + "\n" for r in rows)


def write_fasit(name: str, rows: list[list[str]]) -> None:
    (OUT / name).write_bytes(tsv(rows).encode("utf-8"))


def save_xlsx(wb: Workbook, name: str) -> None:
    """Save with fixed dates in the document properties and in the zip, so the bytes are stable."""
    wb.properties.created = FIXED
    wb.properties.modified = FIXED
    wb.properties.creator = "lag_testdata_datawrapper.py"
    buf = io.BytesIO()
    wb.save(buf)
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl always writes «modified» as now.
                data = re.sub(
                    rb"<dcterms:modified([^>]*)>[^<]*</dcterms:modified>",
                    rb"<dcterms:modified\1>2026-01-15T10:30:00Z</dcterms:modified>",
                    data,
                )
            zi = zipfile.ZipInfo(info.filename, date_time=FIXED.timetuple()[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(zi, data)
    (OUT / name).write_bytes(out.getvalue())


# --------------------------------------------------------------------- 1. SSB-like table


def make_ssb() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Tabell"
    ws["A1"] = "Tabell 1. Folkemengde etter kommune. 1. januar"
    ws.merge_cells("A1:F1")
    ws["A2"] = "Fiktive tall til test"
    ws.append([])  # row 3 stays empty
    rows = [
        ["Kommune", 2022, 2023, 2024, "Endring 2023–2024 (%)"],
        ["Hele landet", 5425270, 5488984, 5550203, 1.1],
        ["3101 Nordby", 12345, f"12{NBSP}401", f"12{NNBSP}502", "0,8"],
        ["3102 Sørvik¹", 8210, 8199, "..", ":"],
        ["3103 Austhamn", ".", 2044, 2101, 2.8],
        ["3104 Vestmo", 655, 640, "-", "x"],
        ["3105 Fjellrud*", 23456, 23890, 24012, f"{MINUS}0,5"],
    ]
    for i, row in enumerate(rows, start=4):
        for j, v in enumerate(row, start=1):
            ws.cell(i, j, v)
    ws["A12"] = "Kilde: Statistisk sentralbyrå (fiktive tall)"
    ws["A13"] = "¹ Ny kommune fra 2024."
    ws["A14"] = "* Foreløpige tall."
    ws["A15"] = "Tegnforklaring: .. = kan ikke offentliggjøres, : = vises ikke, . = ikke mulig å oppgi, - = null, x = ikke aktuelt"
    save_xlsx(wb, "ssb_befolkning.xlsx")
    header = ["Kommune", "2022", "2023", "2024", "Endring 2023–2024 (%)"]
    data = [
        ["3101 Nordby", "12345", "12401", "12502", "0.8"],
        ["3102 Sørvik¹", "8210", "8199", "", ""],
        ["3103 Austhamn", "", "2044", "2101", "2.8"],
        ["3104 Vestmo", "655", "640", "", ""],
        ["3105 Fjellrud*", "23456", "23890", "24012", "-0.5"],
    ]
    write_fasit("ssb_befolkning.fasit.tsv", [header, *data])
    write_fasit(
        "ssb_befolkning.med-sum.fasit.tsv",
        [header, ["Hele landet", "5425270", "5488984", "5550203", "1.1"], *data],
    )


# --------------------------------------------------------------------- 2. two header rows, merged


def make_two_header_rows() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sysselsatte"
    ws["A1"] = "Sysselsatte etter fylke og kjønn"
    ws["A2"] = "Fylke"
    ws.merge_cells("A2:A3")
    ws["B2"] = 2023
    ws.merge_cells("B2:C2")
    ws["D2"] = 2024
    ws.merge_cells("D2:E2")
    for j, v in enumerate(["Menn", "Kvinner", "Menn", "Kvinner"], start=2):
        ws.cell(3, j, v)
    data = [
        ["Nordfylke", 51200, 48900, 51800, 49350],
        ["Sørfylke", 33010, 31870, 33420, 32100],
        ["Vestfylke", 27455, 26990, 27610, 27200],
    ]
    for i, row in enumerate(data, start=4):
        for j, v in enumerate(row, start=1):
            ws.cell(i, j, v)
    ws["A7"] = "Kilde: SSB (fiktive tall)"
    save_xlsx(wb, "to_overskriftsrader.xlsx")
    write_fasit(
        "to_overskriftsrader.fasit.tsv",
        [
            ["Fylke", "2023 – Menn", "2023 – Kvinner", "2024 – Menn", "2024 – Kvinner"],
            *[[r[0], *map(str, r[1:])] for r in data],
        ],
    )


# --------------------------------------------------------------------- 3. sum rows, sum column, hierarchy


def make_sums() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Tilbud"
    rows = [
        ["Fylke", "Kommune", "Barnehager", "Skoler", "Totalt"],
        ["Nordfylke", "Aby", 12, 5, 17],
        [None, "Bey", 8, 3, 11],
        [None, "Sum", 20, 8, 28],
        ["Sørfylke", "Cey", 4, 2, 6],
        [None, "Dey", 7, 1, 8],
        [None, "Sum", 11, 3, 14],
        ["I alt", None, 31, 11, 42],
    ]
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row, start=1):
            if v is not None:
                ws.cell(i, j, v)
    save_xlsx(wb, "sumrader.xlsx")
    write_fasit(
        "sumrader.fasit.tsv",
        [
            ["Fylke", "Kommune", "Barnehager", "Skoler"],
            ["Nordfylke", "Aby", "12", "5"],
            ["Nordfylke", "Bey", "8", "3"],
            ["Sørfylke", "Cey", "4", "2"],
            ["Sørfylke", "Dey", "7", "1"],
        ],
    )
    write_fasit(
        "sumrader.med-sum.fasit.tsv",
        [
            ["Fylke", "Kommune", "Barnehager", "Skoler", "Totalt"],
            ["Nordfylke", "Aby", "12", "5", "17"],
            ["Nordfylke", "Bey", "8", "3", "11"],
            ["Nordfylke", "Sum", "20", "8", "28"],
            ["Sørfylke", "Cey", "4", "2", "6"],
            ["Sørfylke", "Dey", "7", "1", "8"],
            ["Sørfylke", "Sum", "11", "3", "14"],
            ["I alt", "", "31", "11", "42"],
        ],
    )


# --------------------------------------------------------------------- 4. two tables in one sheet


def make_two_tables() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ark1"
    cells = {
        1: ["Tabell 1. Besøkende per måned"],
        2: ["Måned", "Museum", "Bibliotek"],
        3: ["Januar", 1200, 3400],
        4: ["Februar", 1350, 3100],
        5: ["Mars", 1500, 3550],
        8: ["Tabell 2. Utlån etter type"],
        9: ["Type", "Antall", "Andel"],
        10: ["Bøker", 5400, "54 %"],
        11: ["Lydbøker", 2100, "21 %"],
        12: ["Filmer", 1500, "15 %"],
        13: ["Tidsskrifter", 1000, "10 %"],
        14: ["Kilde: Fiktive tall"],
    }
    for r, row in cells.items():
        for j, v in enumerate(row, start=1):
            ws.cell(r, j, v)
    save_xlsx(wb, "to_tabeller.xlsx")
    write_fasit(
        "to_tabeller.tabell1.fasit.tsv",
        [
            ["Måned", "Museum", "Bibliotek"],
            ["Januar", "1200", "3400"],
            ["Februar", "1350", "3100"],
            ["Mars", "1500", "3550"],
        ],
    )
    write_fasit(
        "to_tabeller.fasit.tsv",  # default: the larger table 2
        [
            ["Type", "Antall", "Andel"],
            ["Bøker", "5400", "54"],
            ["Lydbøker", "2100", "21"],
            ["Filmer", "1500", "15"],
            ["Tidsskrifter", "1000", "10"],
        ],
    )


# --------------------------------------------------------------------- 5. hidden row, column and sheet


def make_hidden() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Oversikt"
    for row in (["Nøkkeltall", "Verdi"], ["Kommuner", 3], ["Innbyggere", 3600]):
        ws.append(row)
    data = wb.create_sheet("Data")
    for row in (
        ["Kommune", "Innbyggere", "Intern merknad", "Areal (km²)"],
        ["Aby", 1200, "kontroll", 45.5],
        ["Bey", 900, "sjekket", 30.25],
        ["Cey (gammel)", 1, "slett", 1],
        ["Dey", 1500, None, 60],
    ):
        data.append(row)
    data.row_dimensions[4].hidden = True
    data.column_dimensions["C"].hidden = True
    hidden = wb.create_sheet("Hjelpeark")
    for i in range(1, 21):
        hidden.append([f"Rad {i}", i, i * 2, i * 3, i * 4, i * 5])
    hidden.sheet_state = "hidden"
    save_xlsx(wb, "skjult_rad.xlsx")
    write_fasit(
        "skjult_rad.fasit.tsv",
        [
            ["Kommune", "Innbyggere", "Areal (km²)"],
            ["Aby", "1200", "45.5"],
            ["Bey", "900", "30.25"],
            ["Dey", "1500", "60"],
        ],
    )


# --------------------------------------------------------------------- 6. numbers stored as text, dates


def make_numbers_as_text() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Budsjett"
    rows = [
        ["Post", "Dato", "Regnskap", "Budsjett", "Andel", "Kode"],
        ["Lønn", date(2025, 1, 31), f"1{NBSP}234{NBSP}567,50", f"1{NNBSP}300{NNBSP}000", "12,5 %", "0301"],
        ["Husleie", date(2025, 2, 28), f"{MINUS}145 320,40", "(51 499,75)", "3 %", "0402"],
        ["Inventar", date(2025, 3, 31), "1.234", "12.5", 0.125, "1100"],
        ["Reise", datetime(2025, 4, 30), 2500, "2 500,00", "#DIV/0!", "0503"],
    ]
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row, start=1):
            c = ws.cell(i, j, v)
            if isinstance(v, (date, datetime)):
                c.number_format = "dd.mm.yyyy"
    ws["E4"].number_format = "0.0%"
    save_xlsx(wb, "tall_som_tekst.xlsx")
    write_fasit(
        "tall_som_tekst.fasit.tsv",
        [
            # E4 is formatted as percent in Excel: 0.125 becomes 12.5 and the header gets « (%)».
            ["Post", "Dato", "Regnskap", "Budsjett", "Andel (%)", "Kode"],
            ["Lønn", "2025-01-31", "1234567.5", "1300000", "12.5", "0301"],
            ["Husleie", "2025-02-28", "-145320.4", "-51499.75", "3", "0402"],
            ["Inventar", "2025-03-31", "1234", "12.5", "12.5", "1100"],
            ["Reise", "2025-04-30", "2500", "2500", "", "0503"],
        ],
    )


# --------------------------------------------------------------------- 7. semicolon CSV, Windows-1252


def make_csv_cp1252() -> None:
    text = (
        "Kommune;Innbyggere;Andel over 67 år;Endring\r\n"
        f"Øyvik;12{NBSP}345;18,5;-3\r\n"
        'Ærnes;"1 204";21,0;12\r\n'
        "Åsheim;987;..;0\r\n"
        "Sum;14 536;;9\r\n"
    )
    (OUT / "semikolon_cp1252.csv").write_bytes(text.encode("cp1252"))
    write_fasit(
        "semikolon_cp1252.fasit.tsv",
        [
            ["Kommune", "Innbyggere", "Andel over 67 år", "Endring"],
            ["Øyvik", "12345", "18.5", "-3"],
            ["Ærnes", "1204", "21", "12"],
            ["Åsheim", "987", "", "0"],
        ],
    )


def make_csv_transpose() -> None:
    text = "Nordby,Sørvik,Austhamn\n120,80,45\n130,85,50\n"
    (OUT / "bytt.csv").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    write_fasit("bytt.fasit.tsv", [["Nordby", "Sørvik", "Austhamn"], ["120", "80", "45"], ["130", "85", "50"]])
    write_fasit("bytt.bytt.fasit.tsv", [["Nordby", "120", "130"], ["Sørvik", "80", "85"], ["Austhamn", "45", "50"]])


# --------------------------------------------------------------------- 8. .xls (BIFF8 in an OLE2 file)

ENDOFCHAIN = 0xFFFFFFFE
FREESECT = 0xFFFFFFFF
FATSECT = 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF


def cfb(streams: list[tuple[str, bytes]]) -> bytes:
    """A minimal OLE2 compound file (version 3, 512-byte sectors, no mini stream).

    Each stream is padded to at least 4096 bytes so it lives in regular sectors.
    """
    padded = [(name, data + b"\0" * max(0, 4096 - len(data))) for name, data in streams]
    sectors: list[bytes] = []
    fat = [FATSECT, ENDOFCHAIN]  # sector 0: FAT, sector 1: directory
    starts = []
    next_sector = 2
    for _, data in padded:
        n = -(-len(data) // 512)
        starts.append(next_sector)
        for k in range(n):
            fat.append(next_sector + k + 1 if k < n - 1 else ENDOFCHAIN)
        sectors.append(data + b"\0" * (n * 512 - len(data)))
        next_sector += n
    assert len(fat) <= 128 and len(padded) <= 3
    fat += [FREESECT] * (128 - len(fat))

    def entry(name: str, kind: int, left: int, right: int, child: int, start: int, size: int) -> bytes:
        raw = name.encode("utf-16-le") + b"\0\0"
        return (
            raw.ljust(64, b"\0")
            + struct.pack("<HBB", len(raw), kind, 1)
            + struct.pack("<III", left, right, child)
            + b"\0" * 16
            + struct.pack("<I", 0)
            + b"\0" * 16
            + struct.pack("<II", start, size)
            + struct.pack("<I", 0)
        )

    # Siblings sorted by (length, upper case) as a right-leaning chain.
    order = sorted(range(len(padded)), key=lambda i: (len(padded[i][0]), padded[i][0].upper()))
    ids = {i: k + 1 for k, i in enumerate(order)}
    entries = [entry("Root Entry", 5, NOSTREAM, NOSTREAM, ids[order[0]], ENDOFCHAIN, 0)]
    for k, i in enumerate(order):
        right = ids[order[k + 1]] if k + 1 < len(order) else NOSTREAM
        entries.append(entry(padded[i][0], 2, NOSTREAM, right, NOSTREAM, starts[i], len(padded[i][1])))
    while len(entries) < 4:
        entries.append(b"\0" * 64 + struct.pack("<HBB", 0, 0, 0) + struct.pack("<III", NOSTREAM, NOSTREAM, NOSTREAM) + b"\0" * 48)
    header = (
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        + b"\0" * 16
        + struct.pack("<HHHHH", 0x003E, 0x0003, 0xFFFE, 9, 6)
        + b"\0" * 6
        + struct.pack("<IIIIIIIII", 0, 1, 1, 0, 4096, ENDOFCHAIN, 0, ENDOFCHAIN, 0)
        + struct.pack("<I", 0)
        + struct.pack("<I", FREESECT) * 108
    )
    assert len(header) == 512
    return header + struct.pack("<128I", *fat) + b"".join(entries) + b"".join(sectors)


def _rec(rtype: int, data: bytes = b"") -> bytes:
    return struct.pack("<HH", rtype, len(data)) + data


def _ustr(text: str, lenlen: int) -> bytes:
    raw = text.encode("utf-16-le")
    return struct.pack("<B" if lenlen == 1 else "<H", len(text)) + b"\x01" + raw


XF_GENERAL = 1
XF_DATE = 2


def biff_sheet(cells: dict[tuple[int, int], object], merges=(), hidden_rows=(), hidden_cols=()) -> bytes:
    nrows = max(r for r, _ in cells) + 1
    ncols = max(c for _, c in cells) + 1
    out = _rec(0x0809, struct.pack("<HHHHII", 0x0600, 0x0010, 0x0DBB, 0x07CC, 0, 6))
    out += _rec(0x0200, struct.pack("<IIHHH", 0, nrows, 0, ncols, 0))
    for c in hidden_cols:
        out += _rec(0x007D, struct.pack("<HHHHHH", c, c, 2560, XF_GENERAL, 0x0001, 0))
    for r in hidden_rows:
        out += _rec(0x0208, struct.pack("<HHHHHHI", r, 0, ncols, 0x00FF, 0, 0, 0x0100 | 0x20 | (15 << 16)))
    for (r, c), v in sorted(cells.items()):
        if isinstance(v, str):
            out += _rec(0x0204, struct.pack("<HHH", r, c, XF_GENERAL) + _ustr(v, 2))
        elif isinstance(v, date):
            serial = (v - date(1899, 12, 30)).days
            out += _rec(0x0203, struct.pack("<HHHd", r, c, XF_DATE, float(serial)))
        else:
            out += _rec(0x0203, struct.pack("<HHHd", r, c, XF_GENERAL, float(v)))
    if merges:
        out += _rec(0x00E5, struct.pack("<H", len(merges)) + b"".join(struct.pack("<HHHH", *m) for m in merges))
    out += _rec(0x000A)
    return out


def biff_workbook(sheets: list[tuple[str, bytes, int]]) -> bytes:
    """sheets: (name, substream, visibility 0/1)."""
    font = struct.pack("<HHHHHBBBB", 200, 0, 0x7FFF, 400, 0, 0, 0, 0, 0) + _ustr("Arial", 1)
    xf_style = struct.pack("<HHHBBBBIIH", 0, 0, 0xFFF5, 0x20, 0, 0, 0, 0, 0, 0x20C0)
    xf_cell = struct.pack("<HHHBBBBIIH", 0, 0, 0x0001, 0x20, 0, 0, 0, 0, 0, 0x20C0)
    xf_date = struct.pack("<HHHBBBBIIH", 0, 14, 0x0001, 0x20, 0, 0, 0, 0, 0, 0x20C0)
    head = _rec(0x0809, struct.pack("<HHHHII", 0x0600, 0x0005, 0x0DBB, 0x07CC, 0, 6))
    head += _rec(0x0042, struct.pack("<H", 1200)) + _rec(0x0022, struct.pack("<H", 0))
    head += b"".join(_rec(0x0031, font) for _ in range(5))
    head += _rec(0x00E0, xf_style) + _rec(0x00E0, xf_cell) + _rec(0x00E0, xf_date)
    bound_sizes = [4 + 6 + len(_ustr(name, 1)) for name, _, _ in sheets]
    offset = len(head) + sum(bound_sizes) + 4  # + EOF
    bounds = b""
    for (name, sub, vis), _ in zip(sheets, bound_sizes):
        bounds += _rec(0x0085, struct.pack("<IBB", offset, vis, 0) + _ustr(name, 1))
        offset += len(sub)
    return head + bounds + _rec(0x000A) + b"".join(sub for _, sub, _ in sheets)


def make_xls() -> None:
    cells: dict[tuple[int, int], object] = {(0, 0): "Tabell 3. Omsetning etter næring (mill. kr)"}
    rows = [
        ["Næring", 2022, 2023, "Endring", "Oppdatert"],
        ["Jordbruk", 1200.5, 1300, 99.5, date(2024, 1, 15)],
        ["Fiske", 800, "..", None, date(2024, 1, 15)],
        ["Skjult", 1, 2, 3, date(2024, 1, 15)],
        ["Industri", 5000, 5100, 100, date(2024, 1, 15)],
        ["I alt", 7000.5, 6400, 199.5, date(2024, 1, 15)],
    ]
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row):
            if v is not None:
                cells[(i, j)] = v
    cells[(8, 0)] = "Kilde: Fiktive tall"
    sheet = biff_sheet(cells, merges=[(0, 0, 0, 4)], hidden_rows=[4])
    other = biff_sheet({(0, 0): "Skjult", (0, 1): "Ark", (1, 0): "a", (1, 1): 1})
    data = biff_workbook([("Tabell", sheet, 0), ("Skjult ark", other, 1)])
    (OUT / "omsetning.xls").write_bytes(cfb([("Workbook", data)]))
    write_fasit(
        "omsetning.fasit.tsv",
        [
            ["Næring", "2022", "2023", "Endring", "Oppdatert"],
            ["Jordbruk", "1200.5", "1300", "99.5", "2024-01-15"],
            ["Fiske", "800", "", "", "2024-01-15"],
            ["Industri", "5000", "5100", "100", "2024-01-15"],
        ],
    )


# --------------------------------------------------------------------- 9. empty, broken, protected


def make_bad_files() -> None:
    wb = Workbook()
    wb.active.title = "Ark1"
    save_xlsx(wb, "tom.xlsx")
    (OUT / "tom.csv").write_bytes(b"")
    good = (OUT / "sumrader.xlsx").read_bytes()
    (OUT / "odelagt.xlsx").write_bytes(good[: len(good) // 3])
    (OUT / "passord.xlsx").write_bytes(
        cfb([("EncryptionInfo", b"\x04\x00\x04\x00\x40\x00\x00\x00"), ("EncryptedPackage", b"\x00" * 64)])
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.iterdir():
        p.unlink()
    make_ssb()
    make_two_header_rows()
    make_sums()
    make_two_tables()
    make_hidden()
    make_numbers_as_text()
    make_csv_cp1252()
    make_csv_transpose()
    make_xls()
    make_bad_files()
    print(f"Laget {sum(1 for _ in OUT.iterdir())} filer i {OUT.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
