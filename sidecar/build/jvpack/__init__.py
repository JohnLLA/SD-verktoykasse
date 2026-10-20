# SPDX-License-Identifier: AGPL-3.0-or-later
"""Builds the downloadable jv tool packages (one per tool and platform).

    sidecar/build/bygg-mac.sh <id>[,<id>...]     build, sign and pack for aarch64-apple-darwin

Layout of a package (the archive has no top folder):

    jv-package.json                  manifest: id, version, target, entry, PATH, env
    jv-<id>.app/Contents/MacOS/jv    PyInstaller onedir build (command line only)
    jv-<id>.app/Contents/Helpers/    bundled programs (tesseract, gs, ...)
    jv-<id>.app/Contents/Frameworks/jv-lib/   their libraries
    jv-<id>.app/Contents/Resources/  their data (tessdata, ...)
    Lisenser/                        licence texts and «Kildekode og versjoner.txt»

The app module in Rust (src-tauri/src/tools/jv) reads jv-package.json, sets
the environment from it and runs `<entry> <id> <inputs...> --out <dir>`.
"""

from pathlib import Path

BUILD_ROOT = Path(__file__).resolve().parent.parent  # sidecar/build
SIDECAR = BUILD_ROOT.parent  # sidecar
JV = SIDECAR / "jv"  # the Python workspace
OUT = BUILD_ROOT / "out"  # not in git
WORK = OUT / "work"
DIST = OUT / "dist"

MANIFEST = "jv-package.json"
MANIFEST_SCHEMA = 1
APP_IDENTIFIER = "no.samarbeidsdesken.verktoy"

TARGET_MAC = "aarch64-apple-darwin"
TARGET_WINDOWS = "x86_64-pc-windows-msvc"
ARCHIVE_SUFFIX = {TARGET_MAC: ".tar.gz", TARGET_WINDOWS: ".zip"}


def archive_name(tool_id: str, version: str, target: str) -> str:
    return f"jv-{tool_id}-{version}-{target}{ARCHIVE_SUFFIX[target]}"
