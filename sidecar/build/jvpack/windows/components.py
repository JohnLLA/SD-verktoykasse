# SPDX-License-Identifier: AGPL-3.0-or-later
"""Licence facts for every DLL that may go into a Windows package.

Each DLL a bundled program loads (pe.closure) must match a pattern here. A DLL
without a match stops the build: then its licence is unknown and must be
checked by hand before it is added (spesifikasjon-journalistverktoy.md, «Åpen
kildekode og lisenser»).

Licence texts are kept in lisenstekster/<folder>/ with a KILDE.txt that says
where each text came from (Homebrew on John Inge's Mac, or the project's own
repository at a fixed tag). Nothing is fetched during the build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STORED = Path(__file__).resolve().parent / "lisenstekster"


@dataclass(frozen=True)
class Component:
    key: str
    name: str
    license: str
    source: str
    texts: tuple[str, ...]  # folders under lisenstekster/
    free: bool = True  # False: not a free licence (reported, see NOT_FREE_NOTE)
    note: str = ""


C = Component
COMPONENTS: dict[str, Component] = {
    c.key: c
    for c in [
        # poppler-windows (conda-forge, MSVC)
        C("poppler", "poppler", "GPL-2.0-only OR GPL-3.0-only", "https://poppler.freedesktop.org/", ("poppler",)),
        C("freetype", "FreeType", "FTL OR GPL-2.0-or-later", "https://download.savannah.gnu.org/releases/freetype/", ("freetype",)),
        C("icu", "ICU", "Unicode-3.0", "https://github.com/unicode-org/icu/releases", ("icu",)),
        C("libjpeg-turbo", "libjpeg-turbo", "IJG AND BSD-3-Clause AND Zlib", "https://github.com/libjpeg-turbo/libjpeg-turbo/releases", ("libjpeg-turbo",)),
        C("lcms2", "Little CMS", "MIT", "https://github.com/mm2/Little-CMS/releases", ("lcms2",)),
        C("lerc", "LERC", "Apache-2.0", "https://github.com/Esri/lerc/releases", ("lerc",)),
        C("openssl", "OpenSSL", "Apache-2.0", "https://github.com/openssl/openssl/releases", ("openssl",)),
        C("curl", "libcurl", "curl", "https://curl.se/download.html", ("curl",),
          note="Lenket inn av programmet (adresser som inndata). Verktøyene gir det bare lokale filer."),
        C("xz", "xz (liblzma)", "0BSD", "https://github.com/tukaani-project/xz/releases", ("xz",)),
        C("libpng", "libpng", "libpng-2.0", "https://github.com/pnggroup/libpng/releases", ("libpng",)),
        C("libssh2", "libssh2", "BSD-3-Clause", "https://libssh2.org/download/", ("libssh2",)),
        C("openjpeg", "OpenJPEG", "BSD-2-Clause", "https://github.com/uclouvain/openjpeg/releases", ("openjpeg",)),
        C("libpsl", "libpsl", "MIT", "https://github.com/rockdaboot/libpsl/releases", ("libpsl",)),
        C("libtiff", "libtiff", "libtiff", "https://download.osgeo.org/libtiff/", ("libtiff",)),
        C("zlib", "zlib", "Zlib", "https://zlib.net/", ("zlib",)),
        C("zstd", "Zstandard", "BSD-3-Clause OR GPL-2.0-only", "https://github.com/facebook/zstd/releases", ("zstd",)),
        C("libdeflate", "libdeflate", "MIT", "https://github.com/ebiggers/libdeflate/releases", ("libdeflate",)),
        # UB Mannheim's Tesseract (MSYS2, mingw-w64)
        C("tesseract", "Tesseract", "Apache-2.0", "https://github.com/tesseract-ocr/tesseract/releases", ("tesseract",)),
        C("leptonica", "Leptonica", "BSD-2-Clause", "https://github.com/DanBloomberg/leptonica/releases", ("leptonica",)),
        C("libarchive", "libarchive", "BSD-2-Clause", "https://github.com/libarchive/libarchive/releases", ("libarchive",)),
        C("gcc-runtime", "GCC-kjøretid (libgcc, libstdc++, libgomp)", "GPL-3.0-or-later WITH GCC-exception-3.1",
          "https://gcc.gnu.org/", ("gcc-runtime",),
          note="Unntaket (GCC Runtime Library Exception) tillater å distribuere bibliotekene med programmer under andre lisenser."),
        C("winpthreads", "winpthreads (mingw-w64)", "MIT AND BSD-3-Clause", "https://github.com/mingw-w64/mingw-w64", ("winpthreads",)),
        C("webp", "libwebp", "BSD-3-Clause", "https://github.com/webmproject/libwebp/releases", ("webp",)),
        C("giflib", "giflib", "MIT", "https://sourceforge.net/projects/giflib/files/", ("giflib",)),
        C("bzip2", "bzip2", "bzip2-1.0.6", "https://sourceware.org/bzip2/downloads.html", ("bzip2",)),
        C("jbigkit", "JBIG-KIT", "GPL-2.0-or-later", "https://www.cl.cam.ac.uk/~mgk25/jbigkit/", ("jbigkit",)),
        C("libiconv", "GNU libiconv", "LGPL-2.1-or-later", "https://ftp.gnu.org/gnu/libiconv/", ("lgpl-2.1",)),
        C("gettext", "gettext (libintl)", "LGPL-2.1-or-later", "https://ftp.gnu.org/gnu/gettext/", ("lgpl-2.1",)),
        C("libb2", "libb2 (BLAKE2)", "CC0-1.0", "https://github.com/BLAKE2/libb2/releases", ("libb2",)),
        C("lz4", "LZ4", "BSD-2-Clause", "https://github.com/lz4/lz4/releases", ("lz4",)),
        C("expat", "Expat", "MIT", "https://github.com/libexpat/libexpat/releases", ("expat",)),
        C("libxml2", "libxml2", "MIT", "https://gitlab.gnome.org/GNOME/libxml2/-/releases", ("libxml2",)),
        C("brotli", "Brotli", "MIT", "https://github.com/google/brotli/releases", ("brotli",)),
        C("libidn2", "libidn2", "LGPL-3.0-or-later OR GPL-2.0-or-later", "https://ftp.gnu.org/gnu/libidn/", ("libidn2",)),
        C("libunistring", "libunistring", "LGPL-3.0-or-later OR GPL-2.0-or-later", "https://ftp.gnu.org/gnu/libunistring/", ("libunistring",)),
        C("nghttp2", "nghttp2", "MIT", "https://github.com/nghttp2/nghttp2/releases", ("nghttp2",)),
        C("nghttp3", "nghttp3", "MIT", "https://github.com/ngtcp2/nghttp3/releases", ("nghttp3",)),
        C("ngtcp2", "ngtcp2", "MIT", "https://github.com/ngtcp2/ngtcp2/releases", ("ngtcp2",)),
        C("libffi", "libffi", "MIT", "https://github.com/libffi/libffi/releases", ("libffi",)),
        C("sqlite", "SQLite", "blessing (public domain)", "https://www.sqlite.org/download.html", ("sqlite",)),
        C("mpdecimal", "mpdecimal", "BSD-2-Clause", "https://www.bytereef.org/mpdecimal/download.html", ("mpdecimal",)),
        # Apertium's Windows build (MinGW-w64, nynorsk)
        C("lttoolbox", "lttoolbox (liblttoolbox)", "GPL-2.0-or-later", "https://github.com/apertium/lttoolbox", ("lttoolbox",)),
        C("cg3", "VISL CG-3 (libcg3)", "GPL-3.0-or-later", "https://github.com/GrammarSoft/cg3", ("cg3",)),
        # Not free: Microsoft's C/C++ runtime (redistributable). See NOT_FREE_NOTE.
        C("msvc-runtime", "Microsoft Visual C++ Redistributable (vcruntime140, msvcp140)",
          "LicenseRef-Microsoft-Visual-C-Redistributable", "https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files",
          (), free=False,
          note="Microsofts kjøretid for programmer bygget med Visual C++. Ikke fri lisens; Microsoft tillater "
               "å distribuere filene sammen med programmer. Python for Windows og MSVC-byggene trenger den."),
    ]
}

# (regex on the lower-case DLL name, component). First match wins.
DLL_PATTERNS: list[tuple[str, str]] = [
    (r"poppler.*\.dll", "poppler"),
    (r"(lib)?freetype(-\d+)?\.dll", "freetype"),
    (r"(lib)?icu(dt|uc|in|io|tu|test)\d*\.dll", "icu"),
    (r"(lib)?(jpeg|turbojpeg)(-?\d+)?\.dll", "libjpeg-turbo"),
    (r"(lib)?lcms2(-\d+)?\.dll", "lcms2"),
    (r"(lib)?lerc\.dll", "lerc"),
    (r"lib(crypto|ssl)-3(-x64)?\.dll", "openssl"),
    (r"libcurl(-\d+)?\.dll", "curl"),
    (r"liblzma(-\d+)?\.dll", "xz"),
    (r"libpng16(-\d+)?\.dll", "libpng"),
    (r"libssh2(-\d+)?\.dll", "libssh2"),
    (r"(lib)?openjp2(-\d+)?\.dll", "openjpeg"),
    (r"(lib)?psl-\d+\.dll", "libpsl"),
    (r"(lib)?tiff(-\d+)?\.dll", "libtiff"),
    (r"zlib1?\.dll", "zlib"),
    (r"(lib)?zstd\.dll", "zstd"),
    (r"(lib)?deflate\.dll", "libdeflate"),
    (r"libtesseract-[\d.]+\.dll", "tesseract"),
    (r"lib(leptonica|lept)-\d+\.dll", "leptonica"),
    (r"libarchive-\d+\.dll", "libarchive"),
    (r"lib(gcc_s_seh|stdc\+\+|gomp|quadmath)-\d+\.dll", "gcc-runtime"),
    (r"libwinpthread-\d+\.dll", "winpthreads"),
    (r"lib(webp|webpmux|webpdemux|sharpyuv)-\d+\.dll", "webp"),
    (r"libgif-\d+\.dll", "giflib"),
    (r"libbz2-\d+\.dll", "bzip2"),
    (r"libjbig-\d+\.dll", "jbigkit"),
    (r"libiconv-\d+\.dll", "libiconv"),
    (r"libintl-\d+\.dll", "gettext"),
    (r"libb2-\d+\.dll", "libb2"),
    (r"liblz4(-\d+)?\.dll", "lz4"),
    (r"libexpat-\d+\.dll", "expat"),
    (r"libxml2-\d+\.dll", "libxml2"),
    (r"libbrotli(common|dec|enc)\.dll", "brotli"),
    (r"libidn2-\d+\.dll", "libidn2"),
    (r"libunistring-\d+\.dll", "libunistring"),
    (r"libnghttp2-\d+\.dll", "nghttp2"),
    (r"libnghttp3-\d+\.dll", "nghttp3"),
    (r"libngtcp2(_crypto_\w+)?-\d+\.dll", "ngtcp2"),
    (r"libsqlite3(-\d+)?\.dll", "sqlite"),
    (r"liblttoolbox(-\d+)?\.dll", "lttoolbox"),
    (r"libcg3(-\d+)?\.dll", "cg3"),
    (r"(vcruntime140(_1)?|msvcp140(_\w+)?|concrt140|vcomp140)\.dll", "msvc-runtime"),
]


def component_of(dll: str) -> Component | None:
    name = dll.lower()
    for pattern, key in DLL_PATTERNS:
        if re.fullmatch(pattern, name):
            return COMPONENTS[key]
    return None


def texts(c: Component) -> list[Path]:
    out: list[Path] = []
    for folder in c.texts:
        out += sorted(p for p in (STORED / folder).iterdir() if p.is_file() and p.name != "KILDE.txt")
        kilde = STORED / folder / "KILDE.txt"
        if kilde.exists():
            out.append(kilde)
    return out


NOT_FREE_NOTE = (
    "Microsofts Visual C++-kjøretid (vcruntime140.dll, vcruntime140_1.dll, msvcp140.dll) har ikke fri "
    "lisens. Python for Windows (python-build-standalone) og MSVC-byggene (poppler) trenger den, og "
    "PyInstaller legger den alltid med. Den er listet som unntak i binaries.json og må godkjennes av John Inge."
)
