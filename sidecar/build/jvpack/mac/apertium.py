# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apertium for the nynorsk package: programs, modes and data.

Apertium is installed from source in ~/.local (see verktoy/nynorsk/OPPSETT.md).
Its .mode files are pipelines with absolute paths to the language data.

From nynorsk 0.2.0 the tool runs the mode itself (jv_nynorsk.core.read_mode):
no ``apertium`` script, no bash and no gawk. The mode files are rewritten at
build time so every data path is relative to the data folder
(``'apertium-nno-nob/nob-nno.automorf.bin'``); the tool starts the programs in
that folder. jv-package.json sets APERTIUM_DATADIR and puts Helpers/ in PATH.
Nothing inside the signed bundle is written at run time.

The Windows package (windows/programs.py) uses the same rewritten modes and
the same data files, taken from the Mac package of the same release
(windows/sources.py, «apertium-data»).

Layout in the package bundle:
  Contents/Helpers/<program>              Mach-O programs (via macho.install)
  Contents/Resources/apertium/modes/<mode>.mode
  Contents/Resources/apertium/<pair>/<data files the modes use>
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .macho import BuildError

PREFIX = Path.home() / ".local"
# Source checkouts (licence texts, commits): kilder/apertium/ at the repository
# root, outside git (.gitignore). JV_APERTIUM_SOURCES overrides it, for example
# when building from a worktree.
SOURCES = Path(
    os.environ.get("JV_APERTIUM_SOURCES")
    or Path(__file__).resolve().parents[4] / "kilder" / "apertium"
)

# The modes the nynorsk tool uses (``apertium -f txt <mode>``). nob-nno_e and
# the other variants are left out: the tool never asks for them.
MODES = ("nob-nno", "nno-nob")

# Programs the tool runs around the mode pipeline for ``-f txt``: the
# deformatter and the reformatter (jv_nynorsk.core.read_mode).
SCRIPT_PROGRAMS = ("apertium-destxt", "apertium-retxt")

DATA_VAR = "APERTIUM_DATADIR"
RESOURCE_DIR = "apertium"  # under Contents/Resources

# A data path in a rewritten mode file: plain ASCII, «/» separated.
_SAFE_REL = re.compile(r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*")

# Source repositories: (folder in SOURCES, version, licence, extra texts).
REPOS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("lttoolbox", "3.8.4", "GPL-2.0-or-later", ()),
    ("apertium", "3.9.12", "GPL-2.0-or-later", ("COPYING.hunalign",)),
    ("apertium-lex-tools", "0.5.0", "GPL-3.0-or-later", ()),
    ("apertium-separable", "0.7.1", "GPL-3.0-or-later", ()),
    ("cg3", "1.7.0.13898", "GPL-3.0-or-later", ("license.icu.txt",)),
    ("apertium-nob", "1.5.0", "GPL-2.0-or-later", ()),
    ("apertium-nno", "1.5.0", "GPL-2.0-or-later", ()),
    ("apertium-nno-nob", "1.6.0", "GPL-2.0-or-later", ()),
]


def rewrite_mode(text: str, datadir: Path) -> tuple[str, list[str]]:
    """Make every data path in a mode pipeline relative to datadir.

    Returns the new text and the data files it uses, relative to datadir.
    Paths stay single-quoted (``'apertium-nno-nob/nob-nno.automorf.bin'``).
    Raises BuildError if any absolute path would be left behind.
    """
    prefix = str(datadir).rstrip("/") + "/"
    used: list[str] = []

    def repl(m: re.Match[str]) -> str:
        rel = m.group(2)
        if not _SAFE_REL.fullmatch(rel) or ".." in rel.split("/"):
            raise BuildError(f"Uventet tegn i stien {rel!r} i en mode-fil.")
        if rel not in used:
            used.append(rel)
        return f"'{rel}'"

    pattern = re.compile(r"(['\"]?)" + re.escape(prefix) + r"([^'\"\s|]+)\1")
    new = pattern.sub(repl, text)
    leftover = re.findall(r"(?<![\w$}])/[^\s'\"|]+", new)
    if leftover:
        raise BuildError("Mode-filen har fortsatt absolutte stier: " + ", ".join(leftover[:5]))
    if not used:
        raise BuildError(f"Fant ingen stier under {datadir} i mode-filen.")
    return new, used


def pipeline_programs(pipeline: str) -> list[str]:
    """Program names of the stages in a pipeline (first word of each stage)."""
    names: list[str] = []
    for stage in pipeline.split("|"):
        words = stage.split()
        if not words:
            continue
        name = words[0]
        if "/" in name or not re.fullmatch(r"[A-Za-z0-9._+-]+", name):
            raise BuildError(f"Uventet programnavn i mode-filen: {name!r}.")
        if name not in names:
            names.append(name)
    return names


@dataclass
class Plan:
    modes: dict[str, str]  # mode name -> rewritten text
    data: list[str]  # data files, relative to the datadir
    programs: dict[str, Path]  # program name -> path in the install prefix


def plan(prefix: Path = PREFIX, modes: tuple[str, ...] = MODES) -> Plan:
    """Everything the modes need, read from the local installation."""
    datadir = prefix / "share" / "apertium"
    bindir = prefix / "bin"
    wblank = bindir / "apertium-wblank-mode"
    rewritten: dict[str, str] = {}
    data: list[str] = []
    names: list[str] = []
    for mode in modes:
        path = datadir / "modes" / f"{mode}.mode"
        if not path.is_file():
            raise BuildError(f"Fant ikke {path}. Se verktoy/nynorsk/OPPSETT.md.")
        text, used = rewrite_mode(path.read_text(encoding="utf-8"), datadir)
        rewritten[mode] = text
        data += [u for u in used if u not in data]
        # The pipeline the script really runs: wblank-mode adds its own stages.
        proc = subprocess.run([str(wblank), str(path)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise BuildError(f"apertium-wblank-mode feilet for {mode}:\n{proc.stderr}")
        names += [n for n in pipeline_programs(proc.stdout) if n not in names]
    names += [n for n in SCRIPT_PROGRAMS if n not in names]
    programs: dict[str, Path] = {}
    for n in names:
        p = bindir / n
        if not p.is_file():
            raise BuildError(f"Fant ikke programmet {p}, som mode-filene bruker.")
        programs[n] = p
    for rel in data:
        if not (datadir / rel).is_file():
            raise BuildError(f"Fant ikke språkdatafilen {datadir / rel}.")
    return Plan(rewritten, data, programs)


def install_data(p: Plan, resources: Path, prefix: Path = PREFIX) -> Path:
    """Copy the rewritten modes and the data files into Resources."""
    datadir = prefix / "share" / "apertium"
    dst = resources / RESOURCE_DIR
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "modes").mkdir(parents=True)
    for mode, text in p.modes.items():
        (dst / "modes" / f"{mode}.mode").write_text(text, encoding="utf-8")
    for rel in p.data:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2((datadir / rel).resolve(), target)
    bad = foreign_text_references(dst)
    if bad:
        raise BuildError("Apertium-filer peker utenfor appen:\n" + "\n".join(bad[:20]))
    return dst


FOREIGN_TEXT = (b"/Users/", b"/opt/homebrew", b"/usr/local", b"/.local/")


def foreign_text_references(root: Path, checked_suffixes: tuple[str, ...] = (".mode", "")) -> list[str]:
    """Mode files that still name a path outside the app."""
    problems = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix not in checked_suffixes:
            continue
        data = f.read_bytes()
        for needle in FOREIGN_TEXT:
            if needle in data:
                problems.append(f"{f}: {needle.decode()}")
    return problems


def git_commit(repo: Path) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise BuildError(f"Fant ikke commit for {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_url(repo: Path) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True)
    url = proc.stdout.strip()
    if proc.returncode != 0 or not url:
        raise BuildError(f"Fant ikke GitHub-adressen for {repo}.")
    return url.removesuffix(".git")
