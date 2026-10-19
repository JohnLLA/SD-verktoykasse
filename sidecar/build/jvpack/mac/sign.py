# SPDX-License-Identifier: AGPL-3.0-or-later
"""Code signing (Developer ID, hardened runtime, secure timestamp) and checks."""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .macho import BuildError, macho_files


def _codesign(path: Path, identity: str, runtime: bool = True, entitlements: Path | None = None) -> None:
    # Ad hoc ("-") cannot have a secure timestamp.
    stamp = "--timestamp=none" if identity == "-" else "--timestamp"
    cmd = ["codesign", "--force", stamp, "--sign", identity]
    if runtime:
        cmd += ["--options", "runtime"]
    if entitlements:
        cmd += ["--entitlements", str(entitlements)]
    cmd.append(str(path))
    for attempt in range(3):  # the timestamp server sometimes times out
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return
        if "timestamp" not in proc.stderr.lower() or attempt == 2:
            raise BuildError(f"Signering av {path} feilet:\n{proc.stderr}")


def sign_app(app: Path, identity: str, entitlements: Path | None = None) -> int:
    """Sign inside out: every Mach-O file, then the app bundle itself."""
    main_exe = app / "Contents" / "MacOS"
    inner = [p for p in macho_files(app / "Contents") if p.parent != main_exe]
    inner.sort(key=lambda p: len(p.parts), reverse=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda p: _codesign(p, identity), inner))
    _codesign(app, identity, entitlements=entitlements)
    return len(inner) + 1


def check(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def verify_app(app: Path) -> dict[str, tuple[bool, str]]:
    return {
        "codesign": check(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)]),
        # Not notarised: spctl is expected to say «Unnotarized Developer ID».
        "spctl": check(["spctl", "-a", "-t", "exec", "-vv", str(app)]),
    }


def find_identity() -> str | None:
    """The Developer ID Application identity in the keychain, or JV_SIGN_IDENTITY."""
    import os

    wanted = os.environ.get("JV_SIGN_IDENTITY")
    if wanted:
        return wanted
    proc = subprocess.run(["security", "find-identity", "-v", "-p", "codesigning"],
                          capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if '"Developer ID Application:' in line:
            return line.split('"')[1]
    return None


def team_id(identity: str) -> str | None:
    """«Developer ID Application: Name (TEAMID)» -> TEAMID."""
    if identity.endswith(")") and "(" in identity:
        return identity.rsplit("(", 1)[1][:-1]
    return None
