"""Checks for external programs (ffmpeg, tesseract, ...)."""

from __future__ import annotations

import os
import re
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


def env_var(name: str) -> str:
    """Environment variable that may point to the program: ffprobe -> JV_FFPROBE.

    The packaged tools (sidecar/build, jv-package.json) set these to the
    programs inside the package.
    """
    return "JV_" + re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def _from_env(name: str) -> str | None:
    value = os.environ.get(env_var(name))
    if value and os.path.isabs(value) and os.path.isfile(value) and os.access(value, os.X_OK):
        return value
    return None


def find_binary(name: str) -> str | None:
    """Full path to the program: JV_<NAME> first, then PATH. None if missing."""
    return _from_env(name) or shutil.which(name)


def has_binary(name: str) -> bool:
    """True if the program is found (JV_<NAME> or PATH)."""
    return find_binary(name) is not None


def install_hint(name: str) -> str:
    """Short Norwegian hint on how to install the program."""
    if name in SETUP_GUIDE:
        return f"se {SETUP_GUIDE[name]}"
    return f"brew install {BREW_FORMULA.get(name, name)}"


def require_binary(name: str) -> str:
    """Return the full path to the program, or raise a Norwegian UserError.

    JV_<NAME> (set by the packaged tools) is checked before PATH.
    """
    path = find_binary(name)
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
