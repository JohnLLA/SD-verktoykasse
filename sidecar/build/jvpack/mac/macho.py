# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mach-O helpers: find dylib dependencies, copy them in, rewrite load paths.

Executables go to Contents/Helpers, their dylibs to Contents/Frameworks/jv-lib.
Load commands are rewritten to
  @executable_path/../Frameworks/jv-lib/<name>   (in the executables)
  @loader_path/<name>                            (in the dylibs)
so nothing points to /opt/homebrew any more.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

SYSTEM_PREFIXES = ("/usr/lib/", "/System/")
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",  # 32-bit
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",  # 64-bit
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",  # fat
}

LIB_DIR = "Frameworks/jv-lib"
HELPERS_DIR = "Helpers"


class BuildError(RuntimeError):
    pass


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if proc.returncode != 0:
        raise BuildError(f"{' '.join(cmd)} feilet:\n{proc.stdout}\n{proc.stderr}")
    return proc


def is_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with open(path, "rb") as fh:
            magic = fh.read(4)
    except OSError:
        return False
    if magic == b"\xca\xfe\xba\xbe":
        # Java class files share this magic; a fat Mach-O has a small arch count.
        with open(path, "rb") as fh:
            fh.seek(4)
            count = int.from_bytes(fh.read(4), "big")
        return 0 < count < 20
    return magic in MACHO_MAGICS


def load_commands(path: Path) -> list[str]:
    """Install names this file loads (otool -L), without its own id."""
    out = run(["otool", "-L", str(path)]).stdout.splitlines()[1:]
    names = [line.strip().split(" (compatibility")[0] for line in out if line.strip()]
    own_id = dylib_id(path)
    return [n for n in names if n != own_id]


def dylib_id(path: Path) -> str | None:
    out = run(["otool", "-D", str(path)]).stdout.splitlines()
    return out[1].strip() if len(out) > 1 else None


def rpaths(path: Path) -> list[str]:
    text = run(["otool", "-l", str(path)]).stdout
    return re.findall(r"cmd LC_RPATH\n\s+cmdsize \d+\n\s+path (.+?) \(offset", text)


def min_os(path: Path) -> tuple[int, ...] | None:
    """Minimum macOS from LC_BUILD_VERSION (minos) or LC_VERSION_MIN_MACOSX."""
    text = run(["otool", "-l", str(path)]).stdout
    versions = re.findall(r"cmd LC_BUILD_VERSION\n(?:.*\n){1,3}?\s+minos (\S+)", text)
    versions += re.findall(r"cmd LC_VERSION_MIN_MACOSX\n\s+cmdsize \d+\n\s+version (\S+)", text)
    if not versions:
        return None
    return max(tuple(int(x) for x in v.split(".")) for v in versions)


def _expand(name: str, loader: Path, executable: Path) -> list[Path]:
    """Possible real paths for an install name as seen from loader."""
    if name.startswith("@loader_path/"):
        return [loader.parent / name[len("@loader_path/"):]]
    if name.startswith("@executable_path/"):
        return [executable.parent / name[len("@executable_path/"):]]
    if name.startswith("@rpath/"):
        rest = name[len("@rpath/"):]
        out = []
        for rp in rpaths(loader) + rpaths(executable):
            base = rp.replace("@loader_path", str(loader.parent)).replace(
                "@executable_path", str(executable.parent)
            )
            out.append(Path(base) / rest)
        return out
    return [Path(name)]


@dataclass
class Closure:
    executables: dict[str, Path] = field(default_factory=dict)  # command name -> real path
    libs: dict[str, Path] = field(default_factory=dict)  # basename -> real path
    edges: dict[Path, list[tuple[str, Path]]] = field(default_factory=dict)  # file -> [(install name, real dep)]


def collect(executables: dict[str, Path]) -> Closure:
    """All non-system dylibs the executables need, recursively."""
    closure = Closure()
    todo: list[tuple[Path, Path]] = []
    for name, exe in executables.items():
        real = exe.resolve()
        closure.executables[name] = real
        todo.append((real, real))
    seen: set[Path] = set()
    while todo:
        current, executable = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        deps: list[tuple[str, Path]] = []
        for install_name in load_commands(current):
            if install_name.startswith(SYSTEM_PREFIXES):
                continue
            candidates = [c for c in _expand(install_name, current, executable) if c.exists()]
            if not candidates:
                raise BuildError(f"Finner ikke {install_name} (brukt av {current}).")
            real = candidates[0].resolve()
            base = real.name
            known = closure.libs.get(base)
            if known is not None and known != real:
                raise BuildError(f"To ulike biblioteker heter {base}: {known} og {real}.")
            closure.libs[base] = real
            deps.append((install_name, real))
            todo.append((real, executable))
        closure.edges[current] = deps
    return closure


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst, follow_symlinks=True)
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IWUSR)


def install(closure: Closure, contents: Path) -> list[Path]:
    """Copy executables and dylibs into the bundle and rewrite their load paths."""
    lib_dir = contents / LIB_DIR
    helpers = contents / HELPERS_DIR
    placed: dict[Path, Path] = {}
    for name, real in closure.executables.items():
        dst = helpers / name
        _copy(real, dst)
        placed[real] = dst
    for base, real in closure.libs.items():
        dst = lib_dir / base
        _copy(real, dst)
        placed[real] = dst

    for real, dst in placed.items():
        is_exe = dst.parent == helpers
        args: list[str] = []
        for install_name, dep_real in closure.edges.get(real, []):
            target = (
                f"@executable_path/../{LIB_DIR}/{dep_real.name}" if is_exe else f"@loader_path/{dep_real.name}"
            )
            if install_name != target:
                args += ["-change", install_name, target]
        if not is_exe:
            args += ["-id", f"@rpath/{dst.name}"]
        for rp in rpaths(dst):
            args += ["-delete_rpath", rp]
        if args:
            run(["install_name_tool", *args, str(dst)])
    return list(placed.values())


def macho_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if is_macho(p))


def foreign_references(files: Iterable[Path], forbidden: tuple[str, ...] = ("/opt/homebrew", "/usr/local")) -> list[str]:
    """Load commands or rpaths that point outside the bundle and the system."""
    problems = []
    for f in files:
        for name in load_commands(f) + rpaths(f):
            if name.startswith(forbidden) or (
                name.startswith("/") and not name.startswith(SYSTEM_PREFIXES)
            ):
                problems.append(f"{f}: {name}")
    return problems
