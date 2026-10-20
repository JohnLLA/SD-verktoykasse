# SPDX-License-Identifier: AGPL-3.0-or-later
"""The x86_64-pc-windows-msvc section of sidecar/build/binaries.json.

Written from sources.py and components.py (no build needed, so it can be
made on any machine): `python -m jvpack windows kilder`. With `--sjekk` it
only checks that the file is up to date (CI).
"""

from __future__ import annotations

import json

from .. import TARGET_WINDOWS
from ..mac.binaries import PATH
from . import components
from .sources import NOT_ON_WINDOWS, SOURCES, TOOL_SOURCES


def section() -> dict:
    progs = {}
    for key, s in SOURCES.items():
        progs[key] = {
            "used_by": sorted(t for t, keys in TOOL_SOURCES.items() if key in keys),
            "name": s.name,
            "version": s.version,
            "license": s.license,
            "download_url": s.url,
            "download_sha256": s.sha256,
            "source_url": s.source_code,
            "homepage": s.homepage,
            "note": s.note,
        }
    libs = {
        c.key: {"name": c.name, "license": c.license, "source_url": c.source, "free_license": c.free,
                **({"note": c.note} if c.note else {})}
        for c in components.COMPONENTS.values()
    }
    return {
        "source": "Faste nedlastinger med kjent SHA-256 (jvpack/windows/sources.py). Bygget kjøres i "
                  "GitHub Actions (jv-windows-pakker.yml) og kopierer bare programmene og DLL-ene de laster.",
        "programs": progs,
        "libraries": {
            "note": "Lisensene for DLL-er programmene kan laste. Bare DLL-er som står her, kan komme med i en "
                    "pakke (jvpack/windows/components.py). Hvilke som faktisk er med, står i hver pakkes "
                    "«Kildekode og versjoner.txt».",
            "items": libs,
        },
        "not_free": components.NOT_FREE_NOTE,
        "not_on_windows": NOT_ON_WINDOWS,
    }


def render() -> str:
    data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    data.setdefault("schema", 1)
    data.setdefault("note", "Generert av sidecar/build. Ikke rediger for hånd.")
    data[TARGET_WINDOWS] = section()
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--sjekk" in argv:
        if PATH.read_text(encoding="utf-8") != text:
            print("binaries.json er ikke oppdatert for Windows. Kjør: python -m jvpack windows kilder")
            return 1
        print("binaries.json er oppdatert for Windows.")
        return 0
    PATH.write_text(text, encoding="utf-8")
    print(PATH)
    return 0
