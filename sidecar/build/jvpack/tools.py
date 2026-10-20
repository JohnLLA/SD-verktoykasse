# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-tool build facts: menu name, bundled programs and PyInstaller extras.

Only the tools listed here can be built. Runde A (Mac) covers all nine.
Runde B (Windows) covers the eight that could be packed then; nynorsk 0.2.0
followed (Apertium's own Windows build, mirrored; docs/spike-sidecar.md,
«nynorsk på Windows»). A tool with a Windows package gets a Windows line in
the catalogue, and the app stops showing «Kommer for Windows» for it. The
Windows programs are listed in windows/sources.py (TOOL_SOURCES).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass

from . import JV, TARGET_MAC, TARGET_WINDOWS

ALL_IDS = ("compare", "metadata", "keyframes", "loudness", "subtitles", "pdf-tables", "ocr", "redact", "nynorsk")

# How `jv --version` runs each bundled program in the trial run. None: only
# check that the file is there and executable (the program has no version flag).
VERSION_ARGS: dict[str, tuple[str, ...] | None] = {
    "ffmpeg": ("-version",),
    "ffprobe": ("-version",),
    "tesseract": ("--version",),
    "pdftotext": ("-v",),
    "exiftool": ("-ver",),
    # Apertium: the trial run starts the two programs every mode uses (and
    # with them liblttoolbox, libcg3 and ICU).
    "lt-proc": ("--version",),
    "cg-proc": ("-v",),
}
APERTIUM_CHECKED = ("lt-proc", "cg-proc")


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
        """Programs `jv --version` checks: the Homebrew ones, exiftool and two Apertium programs."""
        scripts = ("exiftool",) if "exiftool" in self.extra else ()
        if "apertium" in self.extra:
            scripts += APERTIUM_CHECKED
        return self.programs + scripts


FIRST = "Første utgave i verktøykassen."
BOTH = (TARGET_MAC, TARGET_WINDOWS)

SPECS: dict[str, ToolSpec] = {
    s.tool_id: s
    for s in [
        ToolSpec("compare", "Sammenlign versjoner", targets=BOTH, note=FIRST),
        ToolSpec(
            "metadata", "Metadata – vis og fjern",
            extra=("exiftool",),
            pyinstaller_extra=("--copy-metadata", "pikepdf"),
            targets=BOTH,
            note=FIRST,
        ),
        ToolSpec("keyframes", "Stillbilder fra video", programs=("ffmpeg", "ffprobe"), targets=BOTH, note=FIRST),
        ToolSpec("loudness", "Lydnivå", programs=("ffmpeg", "ffprobe"), targets=BOTH, note=FIRST),
        ToolSpec("subtitles", "Teksting", targets=BOTH, note=FIRST),
        ToolSpec("pdf-tables", "Tabeller fra PDF", targets=BOTH, note=FIRST),
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
            targets=BOTH,
            note=FIRST,
        ),
        ToolSpec("redact", "Sladding av PDF", programs=("pdftotext",), targets=BOTH, note=FIRST),
        ToolSpec(
            "nynorsk", "Bokmål ↔ nynorsk",
            extra=("apertium",),
            targets=BOTH,
            note="Finnes nå også for Windows. Apertium kjøres direkte, uten bash-skriptet og gawk. "
                 "Oversettelsen er den samme som i 0.1.0.",
        ),
    ]
}
assert tuple(SPECS) == ALL_IDS


def spec(tool_id: str) -> ToolSpec:
    try:
        return SPECS[tool_id]
    except KeyError:
        raise SystemExit(f"Ukjent verktøy: {tool_id}. Velg blant: {', '.join(SPECS)} (eller «alle»).") from None


def parse_ids(arg: str, target: str | None = None) -> list[str]:
    """«alle» or a comma list. With `target`, «alle» means the tools built for it."""
    if arg == "alle":
        ids = [i for i in ALL_IDS if target is None or target in SPECS[i].targets]
    else:
        ids = [i for i in arg.split(",") if i]
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
