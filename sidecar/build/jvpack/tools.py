# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-tool build facts: menu name, bundled programs and PyInstaller extras.

Only the tools listed here can be built. Runde A (Mac) covers all nine. A
Windows build (runde B) adds TARGET_WINDOWS to `targets` for the tools it can
pack; the catalogue then gets a Windows line and the app stops showing
«Kommer for Windows» for that tool.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass

from . import JV, TARGET_MAC

ALL_IDS = ("compare", "metadata", "keyframes", "loudness", "subtitles", "pdf-tables", "ocr", "redact", "nynorsk")

# How `jv --version` runs each bundled program in the trial run. None: only
# check that the file is there and executable (the program has no version flag).
VERSION_ARGS: dict[str, tuple[str, ...] | None] = {
    "ffmpeg": ("-version",),
    "ffprobe": ("-version",),
    "tesseract": ("--version",),
    "pdftotext": ("-v",),
    "gawk": ("--version",),
    "exiftool": ("-ver",),
    "apertium": None,
}


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    name: str  # name in the app's menu (Norwegian)
    # Homebrew programs (Mach-O) bundled into Contents/Helpers. Each gets a
    # JV_<NAME> variable (jv_common.require_binary checks it before PATH).
    programs: tuple[str, ...] = ()
    # Data and script programs: tessdata, exiftool, apertium.
    extra: tuple[str, ...] = ()
    pyinstaller_extra: tuple[str, ...] = ()
    targets: tuple[str, ...] = (TARGET_MAC,)
    note: str = ""  # short change note for the catalogue

    @property
    def checked_programs(self) -> tuple[str, ...]:
        """Programs `jv --version` checks: the Homebrew ones and the script programs."""
        scripts = tuple(p for p in ("exiftool", "apertium") if p in self.extra)
        return self.programs + scripts


FIRST = "Første utgave i verktøykassen."

SPECS: dict[str, ToolSpec] = {
    s.tool_id: s
    for s in [
        ToolSpec("compare", "Sammenlign versjoner", note=FIRST),
        ToolSpec(
            "metadata", "Metadata – vis og fjern",
            extra=("exiftool",),
            pyinstaller_extra=("--copy-metadata", "pikepdf"),
            note=FIRST,
        ),
        ToolSpec("keyframes", "Stillbilder fra video", programs=("ffmpeg", "ffprobe"), note=FIRST),
        ToolSpec("loudness", "Lydnivå", programs=("ffmpeg", "ffprobe"), note=FIRST),
        ToolSpec("subtitles", "Teksting", note=FIRST),
        ToolSpec("pdf-tables", "Tabeller fra PDF", note=FIRST),
        ToolSpec(
            "ocr", "Søkbare PDF-er (OCR)",
            # No Ghostscript: ocrmypdf writes plain PDF (decided 19.10.2026).
            programs=("tesseract",),
            extra=("tessdata",),
            pyinstaller_extra=(
                "--collect-submodules", "ocrmypdf",
                "--collect-data", "ocrmypdf",
                "--copy-metadata", "ocrmypdf",
                "--copy-metadata", "pikepdf",
                "--copy-metadata", "pymupdf",
            ),
            note=FIRST,
        ),
        ToolSpec("redact", "Sladding av PDF", programs=("pdftotext",), note=FIRST),
        ToolSpec("nynorsk", "Bokmål ↔ nynorsk", programs=("gawk",), extra=("apertium",), note=FIRST),
    ]
}
assert tuple(SPECS) == ALL_IDS


def spec(tool_id: str) -> ToolSpec:
    try:
        return SPECS[tool_id]
    except KeyError:
        raise SystemExit(f"Ukjent verktøy: {tool_id}. Velg blant: {', '.join(SPECS)} (eller «alle»).") from None


def parse_ids(arg: str) -> list[str]:
    ids = list(ALL_IDS) if arg == "alle" else [i for i in arg.split(",") if i]
    for i in ids:
        spec(i)
    return ids


def project(tool_id: str) -> dict:
    with open(JV / "verktoy" / tool_id / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["project"]


def version(tool_id: str) -> str:
    return project(tool_id)["version"]


def entry(tool_id: str) -> str:
    return project(tool_id)["entry-points"]["jv.tools"][tool_id]
