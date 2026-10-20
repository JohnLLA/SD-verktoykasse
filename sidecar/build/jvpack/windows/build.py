# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build one tool package for x86_64-pc-windows-msvc.

Steps: PyInstaller (onedir, console program, no tkinter), bundled programs
from pinned downloads (programs.py), licence texts, Authenticode signing when
the workflow has a certificate (sign.py), jv-package.json and the .zip, then a
trial run (`jv.exe --version`) from a freshly unpacked copy.

Runs on Windows only (GitHub Actions, windows-latest). The structure follows
mac/build.py so the two stay easy to compare.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import BUILD_ROOT, DIST, MANIFEST, MANIFEST_SCHEMA, TARGET_WINDOWS, WORK, archive_name
from .. import pack, tools
from ..mac import licenses as common_licenses
from ..mac.macho import BuildError
from . import components, licenses, programs, sign
from .sources import NOT_ON_WINDOWS

LAUNCHER = BUILD_ROOT / "launcher" / "jv_launcher.py"
# Longest path inside a package we accept. The app installs to
# %APPDATA%\no.samarbeidsdesken.verktoy\verktoy\<id>\.ny-<versjon>\ (about 90 characters
# for a typical user name); Windows' classic limit is 260.
MAX_REL_PATH = 150


def log(msg: str) -> None:
    print(msg, flush=True)


@dataclass
class Result:
    tool_id: str
    version: str
    archive: Path | None = None
    archive_bytes: int = 0
    unpacked_bytes: int = 0
    sha256: str = ""
    signing: str = ""
    signed_files: int = 0
    longest_path: int = 0
    not_free: list[str] = field(default_factory=list)
    checks: dict[str, tuple[bool, str]] = field(default_factory=dict)
    missing_licenses: list[str] = field(default_factory=list)
    seconds: float = 0.0
    sizes: dict[str, int] = field(default_factory=dict)


def pyinstaller_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    probe = subprocess.run([sys.executable, "-c", "import PyInstaller"], capture_output=True)
    if probe.returncode != 0:
        raise BuildError("PyInstaller finnes ikke i venv-en. Installer det med "
                         "uv pip install --require-hashes -r sidecar/build/jvpack/windows/pyinstaller-krav.txt")
    return env


def pyinstaller_version(env: dict[str, str]) -> str:
    out = subprocess.run([sys.executable, "-c", "import PyInstaller; print(PyInstaller.__version__)"],
                         capture_output=True, text=True, env=env)
    return out.stdout.strip() or "ukjent"


def _run_pyinstaller(spec: tools.ToolSpec, version: str, work: Path, env: dict[str, str]) -> Path:
    config = work / "config"
    config.mkdir(parents=True, exist_ok=True)
    entry = tools.entry(spec.tool_id)
    (config / "jv_pack_config.py").write_text(
        "# Written by sidecar/build at build time.\n"
        f"TOOL_ID = {spec.tool_id!r}\nENTRY = {entry!r}\nVERSION = {version!r}\n"
        f"PROGRAMS = {({p: tools.VERSION_ARGS[p] for p in spec.checked_programs})!r}\n",
        encoding="utf-8",
    )
    module = entry.split(":")[0]
    package = module.split(".")[0]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--console", "--noupx", "--log-level", "WARN",
        "--name", "jv",
        "--paths", str(config),
        "--hidden-import", "jv_pack_config",
        "--hidden-import", module,
        "--collect-submodules", package,
        "--copy-metadata", f"jv-{spec.tool_id}",
        "--exclude-module", "pytest", "--exclude-module", "_pytest",
        "--exclude-module", "tkinter", "--exclude-module", "_tkinter",
        "--distpath", str(work / "pyi-dist"),
        "--workpath", str(work / "pyi-work"),
        "--specpath", str(work),
        *spec.pyinstaller_extra,
        str(LAUNCHER),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    (work / "pyinstaller.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise BuildError(f"PyInstaller feilet for {spec.tool_id}; se {work / 'pyinstaller.log'}:\n{proc.stderr[-3000:]}")
    return work / "pyi-dist" / "jv"


def manifest(spec: tools.ToolSpec, version: str, app_dir: str, added: programs.Added, pyi_version: str) -> dict:
    """jv-package.json. Every path is relative to the package root, «/» separated."""
    return {
        "schema": MANIFEST_SCHEMA,
        "id": spec.tool_id,
        "name": spec.name,
        "version": version,
        "target": TARGET_WINDOWS,
        "entry": f"{app_dir}/jv.exe",
        "path": added.path,
        "env": added.env,
        # Authenticode is checked by the app when LLA has a certificate (package.rs).
        "codesign": [],
        "programs": list(spec.checked_programs),
        "min_os": None,
        "built_with": {"python": ".".join(map(str, sys.version_info[:3])), "pyinstaller": pyi_version},
    }


def _du(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def build(tool_id: str) -> Result:
    if sys.platform != "win32":
        raise BuildError("Windows-pakkene må bygges på Windows (GitHub Actions: jv-windows-pakker).")
    if tool_id in NOT_ON_WINDOWS:
        raise BuildError(f"{tool_id} har ingen Windows-pakke: {NOT_ON_WINDOWS[tool_id]}")
    start = time.time()
    spec = tools.spec(tool_id)
    if TARGET_WINDOWS not in spec.targets:
        raise BuildError(f"{tool_id} er ikke merket for Windows i tools.py")
    version = tools.version(tool_id)
    result = Result(tool_id, version)
    work = WORK / TARGET_WINDOWS / tool_id
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    env = pyinstaller_env()
    pyi_version = pyinstaller_version(env)

    log(f"[{tool_id}] PyInstaller {pyi_version}")
    onedir = _run_pyinstaller(spec, version, work, env)

    stage = work / "pakke"
    stage.mkdir()
    app_dir = f"jv-{tool_id}"
    shutil.move(str(onedir), str(stage / app_dir))
    result.sizes["python"] = _du(stage / app_dir)
    py_dlls = {p.name.lower() for p in (stage / app_dir).rglob("*.dll")}

    log(f"[{tool_id}] innebygde programmer: {', '.join(spec.checked_programs) or 'ingen'}")
    added = programs.add(tool_id, stage, app_dir)
    for sub in ("programmer", "data"):
        if (stage / app_dir / sub).exists():
            result.sizes[sub] = _du(stage / app_dir / sub)

    log(f"[{tool_id}] lisenser")
    packages = (licenses.python_runtime(py_dlls)
                + [common_licenses.pyinstaller_bootloader(env)]
                + licenses.program_packages(added.sources, added.dlls)
                + common_licenses.python_packages(work / "pyi-work" / "jv"))
    missing = common_licenses.write(stage / "Lisenser", packages, tool_id, version, intro=licenses.INTRO)
    result.missing_licenses = [f"{p.name} {p.version}" for p in missing]
    result.not_free = sorted(added.not_free | {n for n in py_dlls if components.component_of(n)
                                                and not components.component_of(n).free})

    longest = max((len(p.relative_to(stage).as_posix()) for p in stage.rglob("*")), default=0)
    result.longest_path = longest
    result.checks["stilengde"] = (longest <= MAX_REL_PATH, f"lengste sti i pakken: {longest} tegn (grense {MAX_REL_PATH})")

    result.signing, result.signed_files = sign.sign_stage(stage)
    if sign.mode() == "none":
        log(f"[{tool_id}] {sign.UNSIGNED_NOTE}")
    else:
        result.checks["authenticode"] = sign.verify_stage(stage)

    data = manifest(spec, version, app_dir, added, pyi_version)
    (stage / MANIFEST).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result.unpacked_bytes = _du(stage)

    log(f"[{tool_id}] pakker")
    DIST.mkdir(parents=True, exist_ok=True)
    archive = DIST / archive_name(tool_id, version, TARGET_WINDOWS)
    result.sha256 = pack.make_zip(stage, archive)
    result.archive = archive
    result.archive_bytes = archive.stat().st_size

    log(f"[{tool_id}] prøvekjører pakken (utpakket på nytt, --version)")
    result.checks["--version"] = pack.trial_run(archive)
    result.seconds = time.time() - start
    return result
