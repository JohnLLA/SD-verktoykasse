"""Checks for external programs (ffmpeg, tesseract, ...)."""

from __future__ import annotations

import shutil

from .errors import UserError

# program -> Homebrew formula that provides it
BREW_FORMULA = {
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffmpeg",
    "exiftool": "exiftool",
    "tesseract": "tesseract tesseract-lang",
    "ocrmypdf": "ocrmypdf",
    "pdftotext": "poppler",
    "gs": "ghostscript",
    "qpdf": "qpdf",
}

# programs without a Homebrew formula -> setup guide
SETUP_GUIDE = {
    "apertium": "verktoy/nynorsk/OPPSETT.md",
}


def has_binary(name: str) -> bool:
    """True if the program is found in PATH."""
    return shutil.which(name) is not None


def install_hint(name: str) -> str:
    """Short Norwegian hint on how to install the program."""
    if name in SETUP_GUIDE:
        return f"se {SETUP_GUIDE[name]}"
    return f"brew install {BREW_FORMULA.get(name, name)}"


def require_binary(name: str) -> str:
    """Return the full path to the program, or raise a Norwegian UserError."""
    path = shutil.which(name)
    if path is None:
        raise UserError(
            f"Programmet «{name}» er ikke installert eller ikke i PATH. "
            f"Installer det: {install_hint(name)}"
        )
    return path


def skip_if_missing(name: str):
    """pytest mark that skips a test (or module) when the program is missing.

    Usage: @skip_if_missing("ffmpeg") or pytestmark = skip_if_missing("ffmpeg")
    """
    import pytest  # imported lazily: pytest is only a test dependency

    return pytest.mark.skipif(
        not has_binary(name),
        reason=f"«{name}» mangler – testen hoppes over ({install_hint(name)})",
    )
