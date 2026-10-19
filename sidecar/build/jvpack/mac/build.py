# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build one tool package for aarch64-apple-darwin.

Steps: PyInstaller (onedir as a .app bundle, command line only), bundled
Homebrew programs with rewritten library paths, licence texts, Info.plist,
signing (Developer ID + hardened runtime, or ad hoc with a clear warning),
jv-package.json and the .tar.gz.

Why an .app bundle and not a bare onedir folder: codesign seals every file
in a bundle (Contents/_CodeSignature/CodeResources), so one
`codesign --verify --deep --strict` in the app covers the Python code and the
data files too, not only the Mach-O files. The bundle is never opened from
Finder; the app runs Contents/MacOS/jv directly. LSUIElement keeps it out of
the Dock if it ever were.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import APP_IDENTIFIER, BUILD_ROOT, DIST, MANIFEST, MANIFEST_SCHEMA, TARGET_MAC, WORK, archive_name
from .. import pack, tools
from . import binaries, licenses, macho, resources, sign
from .macho import BuildError

LAUNCHER = BUILD_ROOT / "launcher" / "jv_launcher.py"

# Local PyInstaller, as in pakking/mac: the copy installed for Apple's Python 3.9
# plus altgraph/macholib from the Command Line Tools. Nothing is downloaded.
USER_SITE = Path.home() / "Library/Python/3.9/lib/python/site-packages"
CLT_SITE = Path("/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/site-packages")
PKG_RESOURCES_STUB = '''"""Minimal stand-in for pkg_resources.require(), used only by altgraph 0.17.2
at import time. setuptools >= 81 no longer ships pkg_resources."""
from importlib import metadata as _md


class _Dist:
    def __init__(self, name):
        self.project_name = name
        self.version = _md.version(name)


def require(name):
    return [_Dist(name)]
'''


def log(msg: str) -> None:
    print(msg, flush=True)


def pyinstaller_env() -> dict[str, str]:
    """Environment that lets the build Python import PyInstaller.

    1. PyInstaller importable already (installed in the venv, as in CI): use it.
    2. Otherwise a small path folder pointing to the local PyInstaller 6.6
       (Apple's Python 3.9) and altgraph/macholib from the Command Line Tools.
    """
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    probe = subprocess.run([sys.executable, "-c", "import PyInstaller"], capture_output=True)
    if probe.returncode == 0:
        return env
    shim = WORK / "pyinstaller-lokal"
    needed = {
        "PyInstaller": USER_SITE, "_pyinstaller_hooks_contrib": USER_SITE,
        "altgraph": CLT_SITE, "macholib": CLT_SITE,
    }
    missing = [n for n, site in needed.items() if not (site / n).is_dir()]
    if missing:
        raise BuildError(
            "PyInstaller finnes ikke lokalt (mangler: " + ", ".join(missing) + "). "
            "Installer det i venv-en (uv pip install pyinstaller) eller lokalt for Python 3.9."
        )
    if shim.exists():
        shutil.rmtree(shim)
    shim.mkdir(parents=True)
    for name, site in needed.items():
        (shim / name).symlink_to(site / name)
    for site, pattern in ((USER_SITE, "pyinstaller-*.dist-info"), (USER_SITE, "pyinstaller_hooks_contrib-*.dist-info"),
                          (CLT_SITE, "altgraph-*.dist-info"), (CLT_SITE, "macholib-*.dist-info")):
        for d in site.glob(pattern):
            (shim / d.name).symlink_to(d)
    (shim / "pkg_resources.py").write_text(PKG_RESOURCES_STUB, encoding="utf-8")
    env["PYTHONPATH"] = str(shim)
    return env


def pyinstaller_version(env: dict[str, str]) -> str:
    out = subprocess.run([sys.executable, "-c", "import PyInstaller; print(PyInstaller.__version__)"],
                         capture_output=True, text=True, env=env)
    return out.stdout.strip() or "ukjent"


@dataclass
class Result:
    tool_id: str
    version: str
    archive: Path | None = None
    archive_bytes: int = 0
    unpacked_bytes: int = 0
    sha256: str = ""
    min_os: str = ""
    signed_files: int = 0
    signing: str = ""
    checks: dict[str, tuple[bool, str]] = field(default_factory=dict)
    missing_licenses: list[str] = field(default_factory=list)
    seconds: float = 0.0
    sizes: dict[str, int] = field(default_factory=dict)


def _run_pyinstaller(spec: tools.ToolSpec, version: str, work: Path, env: dict[str, str]) -> Path:
    config = work / "config"
    config.mkdir(parents=True, exist_ok=True)
    entry = tools.entry(spec.tool_id)
    (config / "jv_pack_config.py").write_text(
        "# Written by sidecar/build at build time.\n"
        f"TOOL_ID = {spec.tool_id!r}\nENTRY = {entry!r}\nVERSION = {version!r}\n"
        f"PROGRAMS = {list(spec.programs)!r}\n",
        encoding="utf-8",
    )
    module = entry.split(":")[0]
    package = module.split(".")[0]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--log-level", "WARN",
        "--name", "jv",
        "--target-arch", "arm64",
        "--osx-bundle-identifier", f"{APP_IDENTIFIER}.jv.{spec.tool_id}",
        "--paths", str(config),
        "--hidden-import", "jv_pack_config",
        "--hidden-import", module,
        "--collect-submodules", package,
        "--copy-metadata", f"jv-{spec.tool_id}",
        "--exclude-module", "pytest", "--exclude-module", "_pytest",
        "--exclude-module", "tkinter", "--exclude-module", "_tkinter",
        # The build shim has a tiny pkg_resources for altgraph; it must never be frozen.
        "--exclude-module", "pkg_resources",
        "--distpath", str(work / "pyi-dist"),
        "--workpath", str(work / "pyi-work"),
        "--specpath", str(work),
        *spec.pyinstaller_extra,
        str(LAUNCHER),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (work / "pyinstaller.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise BuildError(f"PyInstaller feilet for {spec.tool_id}; se {work / 'pyinstaller.log'}:\n{proc.stderr[-3000:]}")
    return work / "pyi-dist" / "jv.app"


def _add_programs(spec: tools.ToolSpec, contents: Path) -> list[Path]:
    """Bundled Homebrew programs and their data. Returns the Homebrew files used."""
    used: list[Path] = []
    exes: dict[str, Path] = {}
    for b in spec.programs:
        found = shutil.which(b, path=str(resources.HOMEBREW / "bin"))
        if not found:
            raise BuildError(f"Fant ikke {b} i /opt/homebrew/bin.")
        exes[b] = Path(found)
    if exes:
        closure = macho.collect(exes)
        macho.install(closure, contents)
        used += list(closure.executables.values()) + list(closure.libs.values())
    res = contents / "Resources"
    if "tessdata" in spec.extra:
        resources.copy_tessdata(res)
    if "ghostscript" in spec.extra:
        resources.copy_ghostscript(res)
    if "exiftool" in spec.extra:
        resources.copy_exiftool(res)
    if "fontconfig" in spec.extra:
        resources.write_fontconfig(res)
    return used


def manifest(spec: tools.ToolSpec, version: str, app_name: str, min_os: str, pyi_version: str) -> dict:
    """jv-package.json. Every path is relative to the package root."""
    c = f"{app_name}/Contents"
    env: dict[str, str | list[str]] = {}
    for name in spec.programs:
        env["JV_" + name.upper().replace("-", "_")] = f"{c}/{macho.HELPERS_DIR}/{name}"
    if "tessdata" in spec.extra:
        env["TESSDATA_PREFIX"] = f"{c}/Resources/tessdata"
    if "ghostscript" in spec.extra:
        gs = f"{c}/Resources/ghostscript"
        env["GS_LIB"] = [f"{gs}/Resource/Init", f"{gs}/lib", f"{gs}/Resource/Font", f"{gs}/fonts", f"{gs}/iccprofiles"]
        env["GS_FONTPATH"] = [f"{gs}/fonts"]
    if "fontconfig" in spec.extra:
        env["FONTCONFIG_FILE"] = f"{c}/Resources/fontconfig/fonts.conf"
        env["FONTCONFIG_PATH"] = f"{c}/Resources/fontconfig"
    if "exiftool" in spec.extra:
        env["JV_EXIFTOOL"] = f"{c}/Resources/exiftool/exiftool"
    path = [f"{c}/{macho.HELPERS_DIR}"] if spec.programs else []
    return {
        "schema": MANIFEST_SCHEMA,
        "id": spec.tool_id,
        "name": spec.name,
        "version": version,
        "target": TARGET_MAC,
        "entry": f"{c}/MacOS/jv",
        "path": path,
        "env": env,
        "codesign": [app_name],
        "programs": list(spec.programs),
        "min_os": min_os,
        "built_with": {"python": ".".join(map(str, sys.version_info[:3])), "pyinstaller": pyi_version},
    }


def _min_os(contents: Path) -> str:
    best: tuple[int, ...] = (11, 0)
    for f in macho.macho_files(contents):
        v = macho.min_os(f)
        if v and v > best:
            best = v
    while len(best) > 2 and best[-1] == 0:
        best = best[:-1]
    return ".".join(map(str, best))


def _fix_plist(contents: Path, spec: tools.ToolSpec, version: str, min_os: str) -> None:
    path = contents / "Info.plist"
    with open(path, "rb") as fh:
        plist = plistlib.load(fh)
    plist.pop("CFBundleDocumentTypes", None)
    plist.update({
        "CFBundleIdentifier": f"{APP_IDENTIFIER}.jv.{spec.tool_id}",
        "CFBundleName": f"jv-{spec.tool_id}",
        "CFBundleDisplayName": f"jv-{spec.tool_id}",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": min_os,
        "LSArchitecturePriority": ["arm64"],
        # Command line only: never a Dock icon or a menu bar.
        "LSUIElement": True,
        "NSHumanReadableCopyright": "LLAs verktøykasse, AGPL-3.0-or-later. Se Lisenser/ for tredjepartsprogramvare.",
    })
    with open(path, "wb") as fh:
        plistlib.dump(plist, fh)


def _du(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def build(tool_id: str) -> Result:
    start = time.time()
    spec = tools.spec(tool_id)
    version = tools.version(tool_id)
    result = Result(tool_id, version)
    work = WORK / TARGET_MAC / tool_id
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    env = pyinstaller_env()
    pyi_version = pyinstaller_version(env)

    log(f"[{tool_id}] PyInstaller {pyi_version}")
    pyi_app = _run_pyinstaller(spec, version, work, env)

    stage = work / "pakke"
    stage.mkdir()
    app_name = f"jv-{tool_id}.app"
    app = stage / app_name
    shutil.move(str(pyi_app), str(app))
    contents = app / "Contents"
    result.sizes["python"] = _du(app)

    log(f"[{tool_id}] innebygde programmer: {', '.join(spec.programs) or 'ingen'}")
    used = _add_programs(spec, contents)
    for part in ("Helpers", "Frameworks/jv-lib", "Resources/tessdata", "Resources/ghostscript"):
        if (contents / part).exists():
            result.sizes[part] = _du(contents / part)

    log(f"[{tool_id}] kontrollerer stier (otool)")
    problems = macho.foreign_references(macho.macho_files(contents))
    if problems:
        raise BuildError("Disse filene peker utenfor pakken:\n" + "\n".join(problems[:30]))

    log(f"[{tool_id}] lisenser")
    formulas = ["tesseract", "tesseract-lang"] if "tessdata" in spec.extra else []
    brew = licenses.homebrew_packages(used, formulas)
    packages = licenses.python_runtime() + [licenses.pyinstaller_bootloader(env)] + brew + licenses.python_packages(work / "pyi-work" / "jv")
    missing = licenses.write(stage / "Lisenser", packages, tool_id, version)
    result.missing_licenses = [f"{p.name} {p.version}" for p in missing]
    binaries.record(TARGET_MAC, tool_id, brew)

    result.min_os = _min_os(contents)
    _fix_plist(contents, spec, version, result.min_os)

    identity = sign.find_identity()
    if identity is None:
        log(f"[{tool_id}] ADVARSEL: fant ingen «Developer ID Application»-identitet. "
            "Pakken signeres ad hoc og kan IKKE publiseres.")
        identity = "-"
    result.signing = identity
    log(f"[{tool_id}] signerer med {identity} (minste macOS {result.min_os})")
    result.signed_files = sign.sign_app(app, identity)
    result.checks.update(sign.verify_app(app))

    data = manifest(spec, version, app_name, result.min_os, pyi_version)
    (stage / MANIFEST).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result.unpacked_bytes = _du(stage)

    log(f"[{tool_id}] pakker")
    DIST.mkdir(parents=True, exist_ok=True)
    archive = DIST / archive_name(tool_id, version, TARGET_MAC)
    result.sha256 = pack.make_tar_gz(stage, archive)
    result.archive = archive
    result.archive_bytes = archive.stat().st_size

    log(f"[{tool_id}] prøvekjører pakken (utpakket på nytt, --version)")
    result.checks["--version"] = pack.trial_run(archive)
    result.seconds = time.time() - start
    return result
