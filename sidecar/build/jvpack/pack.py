# SPDX-License-Identifier: AGPL-3.0-or-later
"""Archive a package, unpack it again and run it the way the app does.

`package_env` is the Python twin of the environment the Rust module builds
from jv-package.json (src-tauri/src/tools/jv, package::command_env): a clean
environment with only PATH, HOME and TMPDIR (Windows: PATH, SystemRoot, TEMP,
TMP, USERPROFILE, LOCALAPPDATA and APPDATA), plus the package's own
variables. The pytest plugin (sidecar/build/pytest_packaged.py) uses the same
function.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from . import MANIFEST

SYSTEM_PATH = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
WINDOWS = sys.platform == "win32"
# The variables Windows programs need to start (same list as command_env in Rust).
WINDOWS_ENV = ("SystemRoot", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA")


def system_path() -> list[str]:
    if WINDOWS:
        root = os.environ.get("SystemRoot") or r"C:\Windows"
        return [os.path.join(root, "System32"), root]
    return SYSTEM_PATH


def _normalise(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.pax_headers = {}
    if info.isfile() or info.isdir():
        info.mode = 0o755 if (info.isdir() or info.mode & 0o111) else 0o644
    return info


def make_tar_gz(stage: Path, archive: Path) -> str:
    """Pack the contents of stage (no top folder) and return the SHA-256.

    Python's tarfile writes no extended attributes, so no quarantine or
    provenance flags travel with the package. Symlinks stay symlinks.
    """
    if archive.exists():
        archive.unlink()
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT, compresslevel=9) as tar:
        for child in sorted(stage.iterdir()):
            tar.add(child, arcname=child.name, filter=_normalise)
    h = hashlib.sha256()
    with open(archive, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def make_zip(stage: Path, archive: Path) -> str:
    """Pack the contents of stage (no top folder) as .zip and return the SHA-256.

    Sorted entries, «/» separators, no symlinks (a symlink in the stage stops
    the build: the app refuses them on Windows).
    """
    if archive.exists():
        archive.unlink()
    files = sorted(p for p in stage.rglob("*"))
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            if p.is_symlink():
                raise ValueError(f"symlenke i pakken: {p.relative_to(stage)}")
            rel = p.relative_to(stage).as_posix()
            if p.is_dir():
                z.writestr(zipfile.ZipInfo(rel + "/", date_time=(2026, 1, 1, 0, 0, 0)), b"")
                continue
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(p, "rb") as fh, z.open(info, "w") as out:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    out.write(block)
    h = hashlib.sha256()
    with open(archive, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(root: Path) -> dict:
    return json.loads((root / MANIFEST).read_text(encoding="utf-8"))


def _inside(root: Path, rel: str) -> str:
    if rel.startswith("/") or "\\" in rel or ":" in rel or ".." in rel.split("/"):
        raise ValueError(f"sti utenfor pakken i {MANIFEST}: {rel}")
    return str(root.joinpath(*rel.split("/")))


def package_env(root: Path, data: dict | None = None) -> dict[str, str]:
    data = data or load_manifest(root)
    env = {"PATH": os.pathsep.join([_inside(root, p) for p in data.get("path", [])] + system_path())}
    for name in WINDOWS_ENV if WINDOWS else ("HOME", "TMPDIR"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    if WINDOWS and "SystemRoot" not in env:
        env["SystemRoot"] = r"C:\Windows"
    if "TMPDIR" not in env and sys.platform == "darwin":
        env["TMPDIR"] = os.confstr(65537)  # _CS_DARWIN_USER_TEMP_DIR
    for name, value in data.get("env", {}).items():
        values = value if isinstance(value, list) else [value]
        env[name] = os.pathsep.join(_inside(root, v) for v in values)
    return env


def entry(root: Path, data: dict | None = None) -> str:
    data = data or load_manifest(root)
    return _inside(root, data["entry"])


def trial_run(archive: Path) -> tuple[bool, str]:
    """Unpack with the system tar into a fresh folder and run --version."""
    with tempfile.TemporaryDirectory(prefix="jv-prove-") as tmp:
        root = Path(tmp)
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as z:
                z.extractall(root)
        else:
            subprocess.run(["tar", "-xzf", str(archive), "-C", str(root)], check=True)
        proc = subprocess.run([entry(root), "--version"], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=package_env(root), timeout=300)
        return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
