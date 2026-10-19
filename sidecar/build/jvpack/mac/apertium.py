# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apertium for the nynorsk package: programs, the apertium script, modes and data.

Apertium is installed from source in ~/.local (see verktoy/nynorsk/OPPSETT.md).
Its .mode files are shell pipelines with absolute paths to the language data,
and the ``apertium`` script has its install prefix written into it.

Relocation: the mode files are rewritten at build time so
every data path becomes ``"${APERTIUM_DATADIR}/<rest>"``. jv-package.json
sets APERTIUM_DATADIR and APERTIUM_PATH (the app passes them on), and the
``apertium`` script already reads both variables. The script runs the mode
through ``apertium-wblank-mode`` and ``bash``, so the variable is expanded
there. Nothing inside the signed bundle is written at run time.

Layout in the package bundle:
  Contents/Helpers/<program>              Mach-O programs (via macho.install)
  Contents/Resources/apertium/bin/apertium   the shell script
  Contents/Resources/apertium/modes/<mode>.mode
  Contents/Resources/apertium/<pair>/<data files the modes use>
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .macho import BuildError

PREFIX = Path.home() / ".local"
SOURCES = Path.home() / "Kilder" / "apertium"

# The modes the nynorsk tool uses (``apertium -f txt <mode>``). nob-nno_e and
# the other variants are left out: the tool never asks for them.
MODES = ("nob-nno", "nno-nob")

# Programs the apertium script itself runs for ``-f txt`` (besides the mode
# pipeline): the deformatter, reformatter and the wordbound-blank wrapper.
SCRIPT_PROGRAMS = ("apertium-destxt", "apertium-retxt", "apertium-wblank-mode")
# gawk is needed too (setvar_wrap/setvar_unwrap in the script always run it,
# with a regex RS and RT); it comes from Homebrew via AppInfo.binaries.

DATA_VAR = "APERTIUM_DATADIR"
PATH_VAR = "APERTIUM_PATH"
RESOURCE_DIR = "apertium"  # under Contents/Resources

# Characters that would change the meaning of a path inside "…" in bash.
_UNSAFE = re.compile(r'["$`\\\n]')

# Source repositories: (folder in ~/Kilder/apertium, version, licence, extra texts).
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
    """Point a mode pipeline at ${APERTIUM_DATADIR} instead of datadir.

    Returns the new text and the data files it uses, relative to datadir.
    Paths are single-quoted in the installed mode files; they become
    double-quoted so the variable is expanded and spaces still work.
    Raises BuildError if any absolute path would be left behind.
    """
    prefix = str(datadir).rstrip("/") + "/"
    used: list[str] = []

    def repl(m: re.Match[str]) -> str:
        rel = m.group(2)
        if _UNSAFE.search(rel) or ".." in Path(rel).parts:
            raise BuildError(f"Uventet tegn i stien {rel!r} i en mode-fil.")
        if rel not in used:
            used.append(rel)
        return f'"${{{DATA_VAR}}}/{rel}"'

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


def rewrite_script(text: str, prefix: Path = PREFIX) -> str:
    """Make the installed apertium script find its programs and data itself.

    The generated header sets APERTIUM_PATH and APERTIUM_DATADIR to the install
    prefix. They become defaults relative to the script's own folder
    (Resources/apertium/bin), so the script also works when it is started
    without the shell's environment. Both are exported, because the mode
    pipelines read APERTIUM_DATADIR. Nothing else in the script changes.
    """
    lines = text.splitlines(keepends=True)
    if not lines or not lines[0].startswith("#!"):
        raise BuildError("apertium-skriptet har ingen #!-linje.")
    head = (
        '_jv_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # journalistverktøy: relocatable\n'
        f'{PATH_VAR}="${{{PATH_VAR}:-$_jv_here/../../../Helpers}}"\n'
        f'{DATA_VAR}="${{{DATA_VAR}:-$_jv_here/..}}"\n'
        f"export {PATH_VAR} {DATA_VAR}\n"
    )
    found = 0
    out = [lines[0]]
    for line in lines[1:]:
        if re.match(rf"^({PATH_VAR}|{DATA_VAR})=", line):
            found += 1
            if found == 1:
                out.append(head)
            continue
        out.append(line)
    if found != 2:
        raise BuildError("Fant ikke APERTIUM_PATH- og APERTIUM_DATADIR-linjene i apertium-skriptet.")
    new = "".join(out)
    if str(prefix) in new:
        raise BuildError(f"apertium-skriptet peker fortsatt til {prefix}.")
    return new


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
    """Copy the script, the rewritten modes and the data files into Resources."""
    datadir = prefix / "share" / "apertium"
    dst = resources / RESOURCE_DIR
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "bin").mkdir(parents=True)
    (dst / "modes").mkdir()
    script = (prefix / "bin" / "apertium").read_text(encoding="utf-8")
    (dst / "bin" / "apertium").write_text(rewrite_script(script, prefix), encoding="utf-8")
    (dst / "bin" / "apertium").chmod(0o755)
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
    """Text files (script, modes) that still name a path outside the app."""
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
