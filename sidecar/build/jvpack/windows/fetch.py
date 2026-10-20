# SPDX-License-Identifier: AGPL-3.0-or-later
"""Download a pinned source, check its SHA-256 and unpack it.

Files are kept in out/kilder/ (not in git). A file that is already there is
checked again before use; a wrong SHA-256 deletes it and stops the build.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .. import OUT
from ..mac.macho import BuildError
from .sources import Source

CACHE = OUT / "kilder"
UNPACKED = OUT / "work" / "kilder"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(src: Source) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{src.key}-{src.filename}"
    if not path.exists():
        part = path.with_name(path.name + ".part")
        req = urllib.request.Request(src.url, headers={"User-Agent": "lla-verktoykasse-sidecar-build"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(part, "wb") as out:
            shutil.copyfileobj(resp, out, 1 << 20)
        part.replace(path)
    got = sha256(path)
    if got != src.sha256:
        path.unlink()
        raise BuildError(f"{src.name}: feil SHA-256 ({got}, ventet {src.sha256}). Filen er slettet.")
    return path


def _safe_zip_extract(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            p = PurePosixPath(info.filename.replace("\\", "/"))
            if p.is_absolute() or ".." in p.parts or ":" in info.filename:
                raise BuildError(f"{archive.name}: sti utenfor mappen i arkivet")
        z.extractall(dest)


def seven_zip() -> str:
    for name in ("7z", "7z.exe", "7zz", "7za"):
        found = shutil.which(name)
        if found:
            return found
    default = Path("C:/Program Files/7-Zip/7z.exe")
    if default.exists():
        return str(default)
    raise BuildError("7-Zip (7z) finnes ikke. Det trengs for å pakke ut Tesseract-installasjonsfilen.")


def unpack(src: Source) -> Path:
    """The unpacked folder (or, for kind «file», the checked file itself)."""
    path = download(src)
    if src.kind == "file":
        return path
    dest = UNPACKED / src.key
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if src.kind == "zip":
        _safe_zip_extract(path, dest)
    elif src.kind == "nsis":
        # 7-Zip reads NSIS installers without running them.
        proc = subprocess.run([seven_zip(), "x", "-y", "-bd", f"-o{dest}", str(path)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise BuildError(f"7-Zip klarte ikke å pakke ut {src.filename}:\n{proc.stdout[-2000:]}{proc.stderr[-2000:]}")
        for p in dest.rglob("*"):
            if p.is_symlink():
                raise BuildError(f"{src.filename}: symlenke i installasjonsfilen")
    else:
        raise BuildError(f"ukjent type {src.kind}")
    return dest


def single_child(folder: Path) -> Path:
    """The one top folder of an unpacked zip (ffmpeg-9.0.2-essentials_build/...)."""
    children = [c for c in folder.iterdir() if not c.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return folder
