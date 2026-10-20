# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data the bundled programs need: tessdata, Ghostscript files, exiftool, fontconfig.

Everything is copied from the local Homebrew installation. The environment
variables that point to it are written to jv-package.json (see build.py).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import CELLAR, HOMEBREW
from .macho import BuildError

# Tesseract: Norwegian and English as in the spec, plus "osd" (orientation and
# script detection), which ocrmypdf --rotate-pages needs, plus the configs
# (hocr, txt, pdf, tsv) and pdf.ttf for the text layer.
TESS_LANGS = ("nor", "eng", "osd")

FONTS_CONF = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<!-- Journalistverktøy: Ghostscript and poppler link fontconfig but do not need
     system fonts for what the tools do. An empty configuration keeps fontconfig
     from looking for /opt/homebrew/etc/fonts and from writing a font cache. -->
<fontconfig>
</fontconfig>
"""


def keg(formula: str) -> Path:
    """The installed version folder of a Homebrew formula."""
    opt = HOMEBREW / "opt" / formula
    if not opt.exists():
        raise BuildError(f"Homebrew-pakken «{formula}» er ikke installert.")
    return opt.resolve()


def copy_tessdata(resources: Path) -> Path:
    src = (HOMEBREW / "share" / "tessdata").resolve()
    dst = resources / "tessdata"
    dst.mkdir(parents=True, exist_ok=True)
    for lang in TESS_LANGS:
        f = src / f"{lang}.traineddata"
        if not f.exists():
            raise BuildError(f"Mangler {f}. Installer tesseract og tesseract-lang.")
        shutil.copy2(f.resolve(), dst / f.name)
    shutil.copy2((src / "pdf.ttf").resolve(), dst / "pdf.ttf")
    for sub in ("configs", "tessconfigs"):
        if (src / sub).exists():
            shutil.copytree(src / sub, dst / sub, symlinks=False, dirs_exist_ok=True)
    return dst


def copy_ghostscript(resources: Path) -> Path:
    share = keg("ghostscript") / "share" / "ghostscript"
    dst = resources / "ghostscript"
    for sub in ("Resource", "lib", "iccprofiles", "fonts"):
        if (share / sub).exists():
            shutil.copytree(share / sub, dst / sub, symlinks=False, dirs_exist_ok=True)
    return dst


def copy_exiftool(resources: Path) -> Path:
    """exiftool is a Perl script: copy it and its Image::ExifTool library.

    Homebrew's copy hard-codes its own @INC; we replace that with the
    script's own lib folder and run it with the system /usr/bin/perl.
    Only Image/ and File/RandomAccess.pm are needed; the optional Brotli
    XS module from Homebrew is left out (exiftool works without it).
    """
    root = keg("exiftool")
    script = (root / "bin" / "exiftool").read_text(encoding="utf-8", errors="surrogateescape")
    lines = script.splitlines(keepends=True)
    if not lines[0].startswith("#!"):
        raise BuildError("exiftool har ingen #!-linje.")
    lines[0] = "#!/usr/bin/perl\n"
    text = "".join(lines)
    hard = re.findall(r"^unshift @INC, \"[^\"]*Cellar[^\"]*\";\n", text, flags=re.M)
    if not hard:
        raise BuildError("Fant ikke Homebrews @INC-linjer i exiftool; sjekk skriptet.")
    text = text.replace(hard[0], "unshift @INC, $incDir;  # journalistverktøy: bundled lib\n", 1)
    for extra in hard[1:]:
        text = text.replace(extra, "", 1)
    dst = resources / "exiftool"
    (dst / "lib" / "File").mkdir(parents=True, exist_ok=True)
    (dst / "exiftool").write_text(text, encoding="utf-8", errors="surrogateescape")
    (dst / "exiftool").chmod(0o755)
    perl5 = root / "libexec" / "lib" / "perl5"
    shutil.copytree(perl5 / "Image", dst / "lib" / "Image", dirs_exist_ok=True)
    shutil.copy2(perl5 / "File" / "RandomAccess.pm", dst / "lib" / "File" / "RandomAccess.pm")
    return dst


def write_fontconfig(resources: Path) -> Path:
    dst = resources / "fontconfig" / "fonts.conf"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(FONTS_CONF, encoding="utf-8")
    return dst


def keg_of(path: Path) -> tuple[str, str] | None:
    """(formula, version) for a file inside the Homebrew Cellar."""
    try:
        rel = path.resolve().relative_to(CELLAR)
    except ValueError:
        return None
    parts = rel.parts
    return (parts[0], parts[1]) if len(parts) >= 2 else None
