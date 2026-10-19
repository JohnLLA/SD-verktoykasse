# SPDX-License-Identifier: AGPL-3.0-or-later
"""sidecar/build/binaries.json: source, version, SHA-256 and licence of every
system program and library that goes into a package.

On Mac they come from Homebrew bottles. The SHA-256 recorded is the one of
the upstream source archive (from the formula), which is what the AGPL/GPL
source offer points to, and the one of the bottle that was installed.
"""

from __future__ import annotations

import json
import os
import subprocess

from .. import BUILD_ROOT as ROOT
from .licenses import Package

PATH = ROOT / "binaries.json"


def _brew_info(formulas: list[str]) -> dict[str, dict]:
    if not formulas:
        return {}
    env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_ANALYTICS="1")
    proc = subprocess.run(["brew", "info", "--json=v2", *formulas], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        return {}
    return {f["name"]: f for f in json.loads(proc.stdout).get("formulae", [])}


def record(target: str, tool_id: str, brew: list[Package]) -> None:
    data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    data.setdefault("schema", 1)
    data.setdefault("note", "Generert av sidecar/build. Ikke rediger for hånd.")
    tgt = data.setdefault(target, {
        "source": "Homebrew-bottles (/opt/homebrew), kopiert inn med omskrevne bibliotekstier og signert på nytt",
        "programs": {},
    })
    info = _brew_info([p.name for p in brew])
    for p in brew:
        f = info.get(p.name, {})
        stable = f.get("urls", {}).get("stable", {})
        installed = next((i for i in f.get("installed", []) if i.get("version") == p.version.split("_")[0]), None)
        bottles = f.get("bottle", {}).get("stable", {}).get("files", {})
        bottle = next(iter(bottles.items()), (None, {}))
        same = f.get("versions", {}).get("stable") == p.version.split("_")[0]
        entry = tgt["programs"].setdefault(p.name, {"used_by": []})
        entry.update({
            "version": p.version,
            "license": f.get("license") or p.license,
            "source_url": stable.get("url") or p.source,
            "source_sha256": stable.get("checksum") if same else None,
            "bottle": {"tag": bottle[0], "sha256": bottle[1].get("sha256")} if same and bottle[0] else None,
            "homepage": f.get("homepage"),
            "built_as_bottle": installed.get("built_as_bottle") if installed else None,
        })
        if tool_id not in entry["used_by"]:
            entry["used_by"].append(tool_id)
            entry["used_by"].sort()
    tgt["programs"] = dict(sorted(tgt["programs"].items()))
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
