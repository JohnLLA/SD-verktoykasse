# SPDX-License-Identifier: AGPL-3.0-or-later
"""Notarisation of a signed package bundle (local, with a notarytool profile).

    sidecar/build/bygg-mac.sh alle --notariser            profile «jv-notary»
    sidecar/build/bygg-mac.sh alle --notariser <profil>

Only the finished, signed bundle (jv-<id>.app, zipped with ditto) is sent to
Apple; no user files. The ticket is stapled to the bundle, so Gatekeeper can
check it offline. The credentials stay in the keychain profile, made once by
John Inge with `xcrun notarytool store-credentials <profil> ...`. Nothing here
reads key files.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .macho import BuildError

DEFAULT_PROFILE = "jv-notary"


def profile_works(profile: str) -> bool:
    proc = subprocess.run(["xcrun", "notarytool", "history", "--keychain-profile", profile],
                          capture_output=True, text=True)
    return proc.returncode == 0


def notarize_app(app: Path, profile: str, work: Path) -> str:
    archive = work / f"{app.stem}-notarisering.zip"
    if archive.exists():
        archive.unlink()
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True)
    proc = subprocess.run(
        ["xcrun", "notarytool", "submit", str(archive), "--keychain-profile", profile,
         "--wait", "--output-format", "json"],
        capture_output=True, text=True,
    )
    archive.unlink(missing_ok=True)
    try:
        answer = json.loads(proc.stdout)
    except json.JSONDecodeError:
        answer = {}
    status, sub_id = answer.get("status", "ukjent"), answer.get("id", "")
    (work / "notarisering.json").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if status != "Accepted":
        raise BuildError(
            f"Notariseringen ble ikke godkjent (status {status}). Se loggen med: "
            f"xcrun notarytool log {sub_id} --keychain-profile {profile}"
        )
    staple = subprocess.run(["xcrun", "stapler", "staple", str(app)], capture_output=True, text=True)
    if staple.returncode != 0:
        raise BuildError(f"stapler feilet:\n{staple.stdout}{staple.stderr}")
    return f"notarisert og stiftet ({sub_id})"
