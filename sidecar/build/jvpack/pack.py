# SPDX-License-Identifier: AGPL-3.0-or-later
"""Archive a package, unpack it again and run it the way the app does.

`package_env` is the Python twin of the environment the Rust module builds
from jv-package.json (src-tauri/src/tools/jv): a clean environment with only
PATH, HOME and TMPDIR, plus the package's own variables. The pytest plugin
(sidecar/build/pytest_packaged.py) uses the same function.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from . import MANIFEST

SYSTEM_PATH = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]


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


def load_manifest(root: Path) -> dict:
    return json.loads((root / MANIFEST).read_text(encoding="utf-8"))


def _inside(root: Path, rel: str) -> str:
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError(f"sti utenfor pakken i {MANIFEST}: {rel}")
    return str(root / rel)


def package_env(root: Path, data: dict | None = None) -> dict[str, str]:
    data = data or load_manifest(root)
    env = {"PATH": os.pathsep.join([_inside(root, p) for p in data.get("path", [])] + SYSTEM_PATH)}
    for name in ("HOME", "TMPDIR"):
        if os.environ.get(name):
            env[name] = os.environ[name]
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
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(root)], check=True)
        proc = subprocess.run([entry(root), "--version"], capture_output=True, text=True,
                              env=package_env(root), timeout=120)
        return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
