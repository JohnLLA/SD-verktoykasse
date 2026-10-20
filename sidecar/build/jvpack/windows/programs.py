# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copy the bundled programs for one tool into a Windows package.

Each program group gets its own folder under jv-<id>/programmer/ so DLLs
with the same name from different builds never meet (Windows loads a DLL from
the program's own folder first).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..mac.macho import BuildError
from . import components, fetch, licenses, pe
from .sources import SOURCES, TOOL_SOURCES, Source

TESS_LANGS = ("nor", "eng", "osd")
IMAGE_MACHINE_AMD64 = 0x8664


@dataclass
class Added:
    path: list[str] = field(default_factory=list)  # relative to the package root, «/» separated
    env: dict[str, str] = field(default_factory=dict)
    dlls: dict[str, set[str]] = field(default_factory=dict)  # source key -> DLL names (lower case)
    sources: list[Source] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)  # DLLs without a known licence
    not_free: set[str] = field(default_factory=set)


def _copy_with_dlls(key: str, exes: list[Path], search: Path, dest: Path, added: Added) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for exe in exes:
        if pe.machine(exe) != IMAGE_MACHINE_AMD64:
            raise BuildError(f"{exe.name} er ikke et 64-bits x86-program")
        shutil.copy2(exe, dest / exe.name)
    found, missing = pe.closure(exes, [search])
    if missing:
        raise BuildError(f"{', '.join(sorted(missing))} trengs av {key}, men finnes ikke i bygget")
    for name, p in sorted(found.items()):
        c = components.component_of(name)
        if c is None:
            added.unknown.append(f"{key}: {p.name}")
            continue
        if not c.free:
            added.not_free.add(p.name)
        shutil.copy2(p, dest / p.name)
    added.dlls[key] = set(found)


def _ffmpeg(root: Path, rel: str, added: Added) -> None:
    src = SOURCES["ffmpeg"]
    unpacked = fetch.single_child(fetch.unpack(src))
    licenses.UNPACKED[src.key] = unpacked
    dest = root / rel
    exes = [unpacked / "bin" / "ffmpeg.exe", unpacked / "bin" / "ffprobe.exe"]
    _copy_with_dlls(src.key, exes, unpacked / "bin", dest, added)
    out = subprocess.run([str(dest / "ffmpeg.exe"), "-hide_banner", "-version"], capture_output=True, text=True)
    if out.returncode != 0 or "--enable-nonfree" in out.stdout:
        raise BuildError("ffmpeg-bygget kan ikke brukes: det starter ikke eller er bygget med --enable-nonfree")
    added.path.append(rel)
    added.env["JV_FFMPEG"] = f"{rel}/ffmpeg.exe"
    added.env["JV_FFPROBE"] = f"{rel}/ffprobe.exe"
    added.sources.append(src)


def _exiftool(root: Path, rel: str, added: Added) -> None:
    src = SOURCES["exiftool"]
    unpacked = fetch.single_child(fetch.unpack(src))
    licenses.UNPACKED[src.key] = unpacked
    dest = root / rel
    dest.mkdir(parents=True, exist_ok=True)
    launcher = unpacked / "exiftool(-k).exe"
    if not launcher.is_file() or not (unpacked / "exiftool_files" / "perl.exe").is_file():
        raise BuildError("ExifTool-pakken har ikke den ventede formen (exiftool(-k).exe og exiftool_files/)")
    # «For command-line use, rename to exiftool.exe» (README.txt in the package).
    shutil.copy2(launcher, dest / "exiftool.exe")
    shutil.copytree(unpacked / "exiftool_files", dest / "exiftool_files")
    added.path.append(rel)
    added.env["JV_EXIFTOOL"] = f"{rel}/exiftool.exe"
    added.sources.append(src)


def _find(folder: Path, name: str) -> Path:
    hits = sorted(p for p in folder.rglob(name) if p.is_file())
    if not hits:
        raise BuildError(f"fant ikke {name} i {folder.name}")
    return min(hits, key=lambda p: len(p.parts))


def _tesseract(root: Path, rel: str, data_rel: str, added: Added) -> None:
    src = SOURCES["tesseract"]
    unpacked = fetch.unpack(src)
    licenses.UNPACKED[src.key] = unpacked
    exe = _find(unpacked, "tesseract.exe")
    _copy_with_dlls(src.key, [exe], exe.parent, root / rel, added)
    tessdata = root / data_rel
    tessdata.mkdir(parents=True, exist_ok=True)
    inst_data = exe.parent / "tessdata"
    if (inst_data / "pdf.ttf").is_file():
        shutil.copy2(inst_data / "pdf.ttf", tessdata / "pdf.ttf")
    else:
        raise BuildError("pdf.ttf mangler i Tesseract-installasjonsfilen (trengs for tekstlaget i PDF)")
    for sub in ("configs", "tessconfigs"):
        if (inst_data / sub).is_dir():
            shutil.copytree(inst_data / sub, tessdata / sub, dirs_exist_ok=True)
    added.sources.append(src)
    for lang in TESS_LANGS:
        lsrc = SOURCES[f"tessdata-{lang}"]
        shutil.copy2(fetch.unpack(lsrc), tessdata / f"{lang}.traineddata")
        added.sources.append(lsrc)
    added.path.append(rel)
    added.env["JV_TESSERACT"] = f"{rel}/tesseract.exe"
    added.env["TESSDATA_PREFIX"] = data_rel


def _poppler(root: Path, rel: str, added: Added) -> None:
    src = SOURCES["poppler"]
    unpacked = fetch.single_child(fetch.unpack(src))
    licenses.UNPACKED[src.key] = unpacked
    exe = _find(unpacked, "pdftotext.exe")
    _copy_with_dlls(src.key, [exe], exe.parent, root / rel, added)
    added.path.append(rel)
    added.env["JV_PDFTOTEXT"] = f"{rel}/pdftotext.exe"
    added.sources.append(src)


# Where the Apertium modes and data are inside the Mac package (apertium-data).
MAC_APERTIUM_DIR = "jv-nynorsk.app/Contents/Resources/apertium/"
_MAC_MODE_PATH = re.compile(r'"\$\{APERTIUM_DATADIR\}/([A-Za-z0-9._+/-]+)"')


def _apertium_data(dest: Path) -> list[str]:
    """Modes and data files from the Mac package nynorsk 0.1.0, byte for byte.

    Its mode files point at "${APERTIUM_DATADIR}/<file>" (for the bash script);
    here they get the relative form the tool reads ('<file>'), exactly what the
    Mac build writes from 0.2.0 on. Returns the files written (relative).
    """
    archive = fetch.download(SOURCES["apertium-data"])
    written: list[str] = []
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar.getmembers():
            name = m.name.removeprefix("./")
            if not name.startswith(MAC_APERTIUM_DIR) or m.isdir():
                continue
            rel = name[len(MAC_APERTIUM_DIR):]
            parts = PurePosixPath(rel).parts
            if not m.isfile() or ".." in parts or not rel or rel.startswith("/"):
                raise BuildError(f"uventet oppføring i Mac-pakken: {name}")
            if parts[0] == "bin":
                continue  # the apertium bash script of 0.1.0: not used any more
            data = tar.extractfile(m).read()
            if parts[0] == "modes":
                text = _MAC_MODE_PATH.sub(lambda mm: f"'{mm.group(1)}'", data.decode("utf-8"))
                if "${" in text or "\"" in text:
                    raise BuildError(f"{rel}: stier som ikke kunne gjøres relative")
                data = text.encode("utf-8")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(rel)
    if not any(w.startswith("modes/") for w in written):
        raise BuildError("fant ingen moduser i Mac-pakken")
    return written


def _apertium(root: Path, rel: str, data_rel: str, added: Added) -> None:
    from jv_nynorsk.core import MODES, PIPELINE_PROGRAMS, read_mode

    src = SOURCES["apertium"]
    unpacked = fetch.single_child(fetch.unpack(src))
    licenses.UNPACKED[src.key] = unpacked
    bindir = unpacked / "bin"
    exes = [bindir / f"{name}.exe" for name in sorted(PIPELINE_PROGRAMS)]
    missing = [e.name for e in exes if not e.is_file()]
    if missing:
        raise BuildError(f"Apertium-bygget mangler {', '.join(missing)}")
    _copy_with_dlls(src.key, exes, bindir, root / rel, added)
    datadir = root / data_rel
    _apertium_data(datadir)
    for mode in MODES.values():
        for name, *_args in read_mode(datadir, mode):  # same rules as the tool; data files must exist
            if name not in PIPELINE_PROGRAMS:
                raise BuildError(f"{mode}: {name} er ikke med")
    added.sources += [src, SOURCES["apertium-data"]]
    added.path.append(rel)
    added.env["APERTIUM_DATADIR"] = data_rel
    added.env["JV_LT_PROC"] = f"{rel}/lt-proc.exe"
    added.env["JV_CG_PROC"] = f"{rel}/cg-proc.exe"


def add(tool_id: str, stage: Path, app_dir: str) -> Added:
    """Put the programs `tool_id` needs into stage/<app_dir>/programmer/."""
    added = Added()
    keys = TOOL_SOURCES[tool_id]
    p = f"{app_dir}/programmer"
    if "ffmpeg" in keys:
        _ffmpeg(stage, f"{p}/ffmpeg", added)
    if "exiftool" in keys:
        _exiftool(stage, f"{p}/exiftool", added)
    if "tesseract" in keys:
        _tesseract(stage, f"{p}/tesseract", f"{app_dir}/data/tessdata", added)
    if "poppler" in keys:
        _poppler(stage, f"{p}/poppler", added)
    if "apertium" in keys:
        _apertium(stage, f"{p}/apertium", f"{app_dir}/data/apertium", added)
    if added.unknown:
        raise BuildError(
            "Disse DLL-ene har ukjent lisens og er ikke lagt med. Sjekk lisensen og legg dem inn i "
            "jvpack/windows/components.py først:\n  " + "\n  ".join(sorted(added.unknown))
        )
    return added
