# SPDX-License-Identifier: AGPL-3.0-or-later
"""Authenticode signing of the files in a Windows package (docs/distribusjon.md).

The mode comes from JV_WINDOWS_SIGNING, set by the workflow from the
repository variable WINDOWS_SIGNING (same values as the app release):

    none / unset      unsigned, with a clear note (the default until LLA has a certificate)
    certificate       signtool with the certificate the workflow imported
                      (WIN_THUMBPRINT, optional WIN_TIMESTAMP_URL)
    trusted-signing   trusted-signing-cli (Azure Trusted Signing: TS_ENDPOINT,
                      TS_ACCOUNT, TS_PROFILE and AZURE_* in the environment)

Only files without a valid signature are signed (Microsoft's own DLLs and
signed third-party programs keep their signature). Not tried yet: no
Windows certificate exists (20.10.2026).
"""

from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path

from ..mac.macho import BuildError

PE_SUFFIXES = (".exe", ".dll", ".pyd")
UNSIGNED_NOTE = ("USIGNERT: Windows-pakkene er ikke kodesignert (LLA har ikke Windows-sertifikat ennå). "
                 "Det må stå i release-notatet.")


def mode() -> str:
    return (os.environ.get("JV_WINDOWS_SIGNING") or "none").strip() or "none"


def _unsigned(stage: Path) -> list[Path]:
    script = (
        "$ErrorActionPreference='Stop'; "
        f"Get-ChildItem -LiteralPath '{stage}' -Recurse -File | "
        "Where-Object { @('.exe','.dll','.pyd') -contains $_.Extension.ToLower() } | "
        "ForEach-Object { if ((Get-AuthenticodeSignature -LiteralPath $_.FullName).Status -ne 'Valid') { $_.FullName } }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise BuildError(f"klarte ikke å lese signaturene: {out.stderr[-1000:]}")
    return [Path(line.strip()) for line in out.stdout.splitlines() if line.strip()]


def _signtool() -> str:
    hits = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\signtool.exe"))
    if not hits:
        raise BuildError("signtool.exe finnes ikke (Windows SDK)")
    return hits[-1]


def sign_stage(stage: Path) -> tuple[str, int]:
    """(description, number of files signed)."""
    m = mode()
    if m == "none":
        return "usignert", 0
    files = _unsigned(stage)
    if m == "certificate":
        thumb = os.environ.get("WIN_THUMBPRINT")
        if not thumb:
            raise BuildError("WINDOWS_SIGNING=certificate, men sertifikatet er ikke importert (WIN_THUMBPRINT)")
        ts = os.environ.get("WIN_TIMESTAMP_URL") or "http://timestamp.digicert.com"
        tool = _signtool()
        for i in range(0, len(files), 50):
            batch = [str(f) for f in files[i:i + 50]]
            r = subprocess.run([tool, "sign", "/sha1", thumb, "/fd", "sha256", "/tr", ts, "/td", "sha256", *batch],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise BuildError(f"signtool feilet: {r.stdout[-1500:]}{r.stderr[-1500:]}")
        return "Authenticode (sertifikat)", len(files)
    if m == "trusted-signing":
        need = [v for v in ("TS_ENDPOINT", "TS_ACCOUNT", "TS_PROFILE") if not os.environ.get(v)]
        if need:
            raise BuildError(f"WINDOWS_SIGNING=trusted-signing, men {', '.join(need)} mangler")
        for f in files:
            r = subprocess.run(["trusted-signing-cli", "-e", os.environ["TS_ENDPOINT"], "-a", os.environ["TS_ACCOUNT"],
                                "-c", os.environ["TS_PROFILE"], "-d", "LLAs verktøykasse", str(f)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise BuildError(f"trusted-signing-cli feilet: {r.stdout[-1500:]}{r.stderr[-1500:]}")
        return "Authenticode (Azure Trusted Signing)", len(files)
    raise BuildError(f"Ukjent verdi for WINDOWS_SIGNING: {m} (bruk none, certificate eller trusted-signing)")


def verify_stage(stage: Path) -> tuple[bool, str]:
    """After signing: every PE file must have a valid signature."""
    left = _unsigned(stage)
    if left:
        return False, f"{len(left)} filer uten gyldig signatur, for eksempel {left[0].name}"
    return True, "alle .exe, .dll og .pyd har gyldig signatur"
