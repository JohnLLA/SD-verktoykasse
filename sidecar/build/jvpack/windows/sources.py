# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pinned downloads for the Windows packages: URL, SHA-256, version and licence.

Nothing else is downloaded for the system programs. The build refuses a file
whose SHA-256 differs. `python -m jvpack windows kilder` writes this list to
binaries.json (section x86_64-pc-windows-msvc), so the file in git always
matches what the build uses (the CI workflow checks it).

Choice of builds (docs/spike-sidecar.md, runde B):

- ffmpeg: Gyan Doshi's «essentials» build of the release 9.0.2 (same version
  as on Mac), from his GitHub mirror where the files are permanent. GPL-3.0,
  built without «nonfree» (the build checks `ffmpeg -version`).
- exiftool: Phil Harvey's 64-bit Windows package (exiftool + a portable
  Strawberry Perl and Oliver Betz' launcher), from the project's SourceForge
  area where old versions stay.
- Tesseract: the UB Mannheim installer of 5.5.3 (same version as on Mac),
  published by the Tesseract project. Unpacked with 7-Zip; the installer is
  never run.
- Language data: tessdata_fast 4.1.0 (the same files as Homebrew's
  tesseract-lang on Mac, byte for byte).
- poppler: Owen Schwartz' poppler-windows 26.09.0-0 (conda-forge build).
  Only pdftotext and the DLLs it loads are copied.
- Apertium (nynorsk): Apertium's own nightly Windows build (MinGW-w64, by Tino
  Didriksen), with the same commits as the Mac package. The nightly folder has
  no permanent URLs, so the archive and the source code for the same commits
  are mirrored to the release «kilder-apertium-windows» in the release repo
  (docs/spike-sidecar.md, «nynorsk på Windows»). Only the 14 programs the
  modes use and the DLLs they load are copied.
- Apertium language data: the modes and data files from the published Mac
  package nynorsk 0.1.0, byte for byte, so both platforms translate the same.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    version: str
    url: str
    sha256: str
    kind: str  # "zip", "nsis" (unpacked with 7-Zip), "file" or "data" (read by programs.py)
    license: str
    homepage: str
    source_code: str  # where the corresponding source code is
    used_by: tuple[str, ...]
    note: str = ""

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


APERTIUM_MIRROR = "https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/"
_APERTIUM_SOURCES = " ".join(APERTIUM_MIRROR + f for f in (
    "kilde-lttoolbox-ed9b682b9e3e.tar.gz",
    "kilde-apertium-d8dfb942e31d.tar.gz",
    "kilde-apertium-lex-tools-1ccefa6269ad.tar.gz",
    "kilde-apertium-separable-18045e4da12c.tar.gz",
    "kilde-cg3-0250250fe982.tar.gz",
))
_APERTIUM_DATA_SOURCES = " ".join(APERTIUM_MIRROR + f for f in (
    "kilde-apertium-nob-3d63c61e5520.tar.gz",
    "kilde-apertium-nno-2efb61642310.tar.gz",
    "kilde-apertium-nno-nob-af921d87acad.tar.gz",
))

TESSDATA_TAG = "4.1.0"
_TESSDATA = "https://github.com/tesseract-ocr/tessdata_fast/raw/" + TESSDATA_TAG + "/{lang}.traineddata"

SOURCES: dict[str, Source] = {
    s.key: s
    for s in [
        Source(
            "ffmpeg", "FFmpeg (gyan.dev essentials)", "9.0.2",
            "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip",
            "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
            "zip", "GPL-3.0-or-later", "https://www.gyan.dev/ffmpeg/builds/",
            "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz (commit 946fcce07b; bibliotekene og versjonene står i README.txt)",
            ("keyframes", "loudness"),
            "Statisk bygg: ffmpeg.exe og ffprobe.exe er med, ffplay.exe ikke.",
        ),
        Source(
            "exiftool", "ExifTool (Windows-pakke)", "13.59",
            "https://downloads.sourceforge.net/project/exiftool/exiftool-13.59_64.zip",
            "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec",
            "zip", "Artistic-1.0-Perl OR GPL-1.0-or-later", "https://exiftool.org/",
            "https://downloads.sourceforge.net/project/exiftool/Image-ExifTool-13.59.tar.gz "
            "(Strawberry Perl: https://strawberryperl.com/releases.html)",
            ("metadata",),
            "Inneholder en portabel Strawberry Perl (Artistic/GPL) og en liten oppstarter av "
            "Oliver Betz (CC0-1.0). «exiftool(-k).exe» er gitt nytt navn til exiftool.exe, slik "
            "pakken selv sier.",
        ),
        Source(
            "tesseract", "Tesseract OCR (UB Mannheim)", "5.5.3.20260724",
            "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe",
            "bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4",
            "nsis", "Apache-2.0", "https://github.com/UB-Mannheim/tesseract/wiki",
            "https://github.com/tesseract-ocr/tesseract/archive/refs/tags/5.5.3.tar.gz "
            "(byggeoppsett: https://github.com/UB-Mannheim/tesseract/tree/v5.5.3.20260724)",
            ("ocr",),
            "Installasjonsfilen pakkes ut med 7-Zip og kjøres aldri. Bare tesseract.exe, "
            "DLL-ene den laster og tessdata/configs er med.",
        ),
        Source(
            "tessdata-nor", "Tesseract-språkdata nor (tessdata_fast)", TESSDATA_TAG,
            _TESSDATA.format(lang="nor"),
            "0451eb4f8049ae78196806bf878a389a2f40f1386fe038568cf4441226ba6ef2",
            "file", "Apache-2.0", "https://github.com/tesseract-ocr/tessdata_fast",
            "https://github.com/tesseract-ocr/tessdata_fast/tree/" + TESSDATA_TAG, ("ocr",),
            "Samme fil som i Homebrews tesseract-lang (Mac).",
        ),
        Source(
            "tessdata-eng", "Tesseract-språkdata eng (tessdata_fast)", TESSDATA_TAG,
            _TESSDATA.format(lang="eng"),
            "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
            "file", "Apache-2.0", "https://github.com/tesseract-ocr/tessdata_fast",
            "https://github.com/tesseract-ocr/tessdata_fast/tree/" + TESSDATA_TAG, ("ocr",),
            "Samme fil som i Homebrews tesseract (Mac).",
        ),
        Source(
            "tessdata-osd", "Tesseract-språkdata osd (tessdata_fast)", TESSDATA_TAG,
            _TESSDATA.format(lang="osd"),
            "9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff",
            "file", "Apache-2.0", "https://github.com/tesseract-ocr/tessdata_fast",
            "https://github.com/tesseract-ocr/tessdata_fast/tree/" + TESSDATA_TAG, ("ocr",),
            "Samme fil som i Homebrews tesseract (Mac).",
        ),
        Source(
            "poppler", "poppler (poppler-windows, conda-forge)", "26.09.0-0",
            "https://github.com/oschwartz10612/poppler-windows/releases/download/v26.09.0-0/Release-26.09.0-0.zip",
            "7a6f256a0ddf7536182246a5733331bf4677cbcc34f4663774947ad34556c8d0",
            "zip", "GPL-2.0-only OR GPL-3.0-only", "https://github.com/oschwartz10612/poppler-windows",
            "https://poppler.freedesktop.org/poppler-26.09.0.tar.xz "
            "(byggeoppskrift: https://github.com/conda-forge/poppler-feedstock)",
            ("redact",),
            "Bare pdftotext.exe og DLL-ene den laster er med (se components.py).",
        ),
        Source(
            "apertium", "Apertium for Windows (apertium-all-dev)",
            "2026-10-14",
            APERTIUM_MIRROR + "apertium-all-dev-2026-10-14.x86_64.zip",
            "c8236ac537be7ba35849cf9ad4222a399646076f9cfa75bf86806e3a614de8a8",
            "zip", "GPL-2.0-or-later AND GPL-3.0-or-later", "https://apertium.projectjj.com/win32/nightly/",
            _APERTIUM_SOURCES,
            ("nynorsk",),
            "Speil av https://apertium.projectjj.com/win32/nightly/apertium-all-dev.x86_64.zip (14.10.2026, "
            "uendret). Versjoner og commiter: lttoolbox 3.8.4 ed9b682b, apertium 3.9.12 d8dfb942, "
            "apertium-lex-tools 0.5.0 1ccefa62, apertium-separable 0.7.1 18045e4d, cg3 1.7.0 0250250f "
            "(de samme som i Mac-pakken). "
            "GPL-2.0-or-later: lttoolbox og apertium; GPL-3.0-or-later: apertium-lex-tools, "
            "apertium-separable og cg3. Bare de 14 programmene modusene bruker og DLL-ene de laster er med.",
        ),
        Source(
            "apertium-data", "Apertium-språkdata (apertium-nno-nob)",
            "1.6.0",
            "https://github.com/JohnLLA/sd-verktoy-releases/releases/download/jv-nynorsk-v0.1.0/"
            "jv-nynorsk-0.1.0-aarch64-apple-darwin.tar.gz",
            "4f5f100fc92c5437ef4708c8054a4586fdbd50805c3f93e4b47353baeedccd26",
            "data", "GPL-2.0-or-later", "https://github.com/apertium/apertium-nno-nob",
            _APERTIUM_DATA_SOURCES,
            ("nynorsk",),
            "Commiter: apertium-nno-nob af921d87, apertium-nob 3d63c61e, apertium-nno 2efb6164. "
            "Modusene og datafilene hentes fra Mac-pakken nynorsk 0.1.0 (Resources/apertium), så Windows og Mac "
            "oversetter likt. Datafilene er uendret; i mode-filene er bare stiene gjort relative til datamappa.",
        ),
    ]
}

# Which sources each tool's package uses on Windows.
TOOL_SOURCES: dict[str, tuple[str, ...]] = {
    "compare": (),
    "metadata": ("exiftool",),
    "keyframes": ("ffmpeg",),
    "loudness": ("ffmpeg",),
    "subtitles": (),
    "pdf-tables": (),
    "ocr": ("tesseract", "tessdata-nor", "tessdata-eng", "tessdata-osd"),
    "redact": ("poppler",),
    "nynorsk": ("apertium", "apertium-data"),
}

# Tools without a Windows package, and why (shown in the build summary and
# the README; the app shows «Kommer for Windows»). Empty since nynorsk 0.2.0.
NOT_ON_WINDOWS: dict[str, str] = {}
