# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lisenser/ for a Windows package: the Python runtime, the bundled programs
(with the DLLs they load) and the Python packages.

Reuses the Mac writer (mac/licenses.py) so «Kildekode og versjoner.txt» has
the same format (THIRD_PARTY_LICENSES.md is generated from it).
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..mac.licenses import Package
from . import components
from .sources import SOURCES, Source

INTRO = [
    "Programmene for Windows er offisielle eller kjente bygg, lastet ned med fast",
    "adresse og kontrollert mot SHA-256 (sidecar/build/binaries.json). De er kopiert",
    "uendret; bare filene programmet trenger er med. exiftool(-k).exe er gitt nytt",
    "navn til exiftool.exe, slik ExifTool-pakken selv sier.",
    "",
]


def python_runtime(found_dlls: set[str]) -> list[Package]:
    """Python (python-build-standalone for Windows) and what is built into it.

    `found_dlls`: lower-case names of the DLLs PyInstaller put in _internal,
    so the Microsoft runtime and OpenSSL/SQLite/libffi are listed only if they
    are there.
    """
    import pyexpat
    import sqlite3
    import ssl
    import _decimal

    base = Path(sys.base_prefix)
    ver = ".".join(map(str, sys.version_info[:3]))
    lic = [p for p in (base / "LICENSE.txt", base / "LICENSE") if p.is_file()]
    out = [Package(
        "Python", ver, "PSF-2.0",
        f"https://www.python.org/ftp/python/{ver}/Python-{ver}.tar.xz "
        "(bygget av python-build-standalone: https://github.com/astral-sh/python-build-standalone)",
        "Kjøretid", lic[:1],
    )]
    linked = "Del av Python for Windows (python-build-standalone)."

    def comp(key: str, version: str, note: str = linked) -> None:
        c = components.COMPONENTS[key]
        out.append(Package(c.name, version, c.license, c.source, "Kjøretid", components.texts(c),
                           f"{note} {c.note}".strip()))

    if any(n.startswith("libcrypto") or n.startswith("libssl") for n in found_dlls):
        comp("openssl", ssl.OPENSSL_VERSION.split()[1])
    if "sqlite3.dll" in found_dlls:
        comp("sqlite", sqlite3.sqlite_version)
    if any(n.startswith("libffi") for n in found_dlls):
        comp("libffi", "ukjent")
    comp("mpdecimal", _decimal.__libmpdec_version__)
    comp("expat", pyexpat.EXPAT_VERSION.split("_")[-1])
    comp("zlib", "ukjent")
    comp("bzip2", "ukjent")
    comp("xz", "ukjent")
    if any(components.component_of(n) is components.COMPONENTS["msvc-runtime"] for n in found_dlls):
        comp("msvc-runtime", "14.x", "Lagt med av PyInstaller.")
    return out


def program_packages(sources: list[Source], dlls: dict[str, set[str]]) -> list[Package]:
    """The downloaded programs and, for each, the components of the DLLs it loads.

    `dlls`: source key -> lower-case DLL names copied for it.
    """
    out: list[Package] = []
    seen: set[str] = set()
    for src in sources:
        texts = _source_texts(src)
        out.append(Package(src.name, src.version, src.license, src.source_code, "Windows-program", texts,
                           f"Lastet ned fra {src.url} (SHA-256 {src.sha256}). {src.note}".strip()))
        for dll in sorted(dlls.get(src.key, set())):
            c = components.component_of(dll)
            if c is None or c.key in seen or c.key == src.key:
                continue
            seen.add(c.key)
            names = sorted(d for d in dlls[src.key] if components.component_of(d) is c)
            note = f"Følger med {src.name} ({', '.join(names)}). Versjonen står ikke i bygget. {c.note}".strip()
            out.append(Package(c.name, "ukjent", c.license, c.source, "Windows-bibliotek", components.texts(c), note))
    return out


# Licence texts that come with each download (relative to the unpacked
# folder, after fetch.single_child), plus stored ones.
SOURCE_TEXTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "ffmpeg": (("LICENSE", "README.txt"), ()),
    "exiftool": (("exiftool_files/LICENSE", "exiftool_files/Licenses_Strawberry_Perl.zip",
                  "exiftool_files/readme_windows.txt", "README.txt"), ()),
    "tesseract": ((), ("tesseract",)),
    "tessdata-nor": ((), ("tessdata_fast",)),
    "tessdata-eng": ((), ("tessdata_fast",)),
    "tessdata-osd": ((), ("tessdata_fast",)),
    "poppler": ((), ("poppler",)),
}

# Set by programs.py when a source is unpacked: key -> unpacked folder.
UNPACKED: dict[str, Path] = {}


def _source_texts(src: Source) -> list[Path]:
    own, stored = SOURCE_TEXTS.get(src.key, ((), ()))
    out: list[Path] = []
    root = UNPACKED.get(src.key)
    if root is not None:
        out += [root / p for p in own if (root / p).is_file()]
    for folder in stored:
        out += components.texts(components.Component(folder, folder, "", "", (folder,)))
    return out
