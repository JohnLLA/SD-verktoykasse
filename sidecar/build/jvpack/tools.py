# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-tool build facts: menu name, bundled programs and PyInstaller extras.

Only the tools listed here can be built. The spike (steg 6.1) covers
`subtitles` (smallest) and `ocr` (largest); steg 6.2 adds the other seven.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

from . import JV


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    name: str  # name in the app's menu (Norwegian)
    # Programs bundled into the package, by command name. Each gets a
    # JV_<NAME> variable that points to it (jv_common.require_binary, 6.2).
    programs: tuple[str, ...] = ()
    # Data the programs need (Mac: copied from Homebrew).
    extra: tuple[str, ...] = ()
    pyinstaller_extra: tuple[str, ...] = ()
    targets: tuple[str, ...] = ("aarch64-apple-darwin",)
    note: str = ""  # short change note for the catalogue
    data: dict = field(default_factory=dict)


SPECS: dict[str, ToolSpec] = {
    s.tool_id: s
    for s in [
        ToolSpec("subtitles", "Teksting", note="Første utgave i verktøykassen."),
        ToolSpec(
            "ocr", "Søkbare PDF-er (OCR)",
            # gs: jv_ocr.core calls require_binary("gs") today. ocrmypdf 17 with
            # output_type="pdf" works without it (docs/spike-sidecar.md).
            programs=("tesseract", "gs"),
            extra=("tessdata", "ghostscript", "fontconfig"),
            pyinstaller_extra=(
                "--collect-submodules", "ocrmypdf",
                "--collect-data", "ocrmypdf",
                "--copy-metadata", "ocrmypdf",
                "--copy-metadata", "pikepdf",
                "--copy-metadata", "pymupdf",
            ),
            note="Første utgave i verktøykassen.",
        ),
    ]
}


def spec(tool_id: str) -> ToolSpec:
    try:
        return SPECS[tool_id]
    except KeyError:
        raise SystemExit(f"Ukjent eller ikke støttet verktøy: {tool_id}. Velg blant: {', '.join(SPECS)}.") from None


def project(tool_id: str) -> dict:
    with open(JV / "verktoy" / tool_id / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["project"]


def version(tool_id: str) -> str:
    return project(tool_id)["version"]


def entry(tool_id: str) -> str:
    return project(tool_id)["entry-points"]["jv.tools"][tool_id]
