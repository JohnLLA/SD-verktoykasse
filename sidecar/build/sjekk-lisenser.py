#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lisenskontroll for npm og Python (Rust har cargo-deny, src-tauri/deny.toml).

    python3 sidecar/build/sjekk-lisenser.py --npm package-lock.json
    python3 sidecar/build/sjekk-lisenser.py --python pip-licenses.json

--npm leser «license» fra package-lock.json (ingen nett, ingenting installeres).
--python leser JSON fra `pip-licenses --format=json` (kjørt mot sidecar/jv/.venv).

Appen er AGPL-3.0-or-later. Avhengigheter må ha en tillatende lisens eller en
svak copyleft som kan brukes sammen med AGPL (MPL-2.0, LGPL). Avslutningskode 1
hvis en lisens ikke står i lista. Verktøypakkene våre (jv-*) har ikke egen
lisensmetadata i pyproject og hoppes over; de er vår egen kode.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

NPM_OK = {"MIT", "ISC", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "0BSD", "CC0-1.0", "Unlicense", "Zlib", "BlueOak-1.0.0"}

PYTHON_OK = {
    "MIT", "MIT License", "MIT-0", "MIT-CMU", "BSD-2-Clause", "BSD-3-Clause", "BSD License",
    "Apache-2.0", "Apache License 2.0", "Apache-2.0 OR BSD-2-Clause", "Apache-2.0 OR BSD-3-Clause",
    "BSD-3-Clause, Apache-2.0, dependency licenses",  # pypdfium2
    "MPL-2.0", "ISC", "Python Software Foundation License", "PSF-2.0",
    "LGPL-3.0-only", "GNU Lesser General Public License v3 (LGPLv3)",  # fpdf2, img2pdf
    "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License",  # pymupdf (AGPL, som appen)
}
OWN = re.compile(r"^jv-")


def ok_expr(expr: str, allowed: set[str]) -> bool:
    """SPDX-uttrykk: «A OR B» er greit når minst ett alternativ er tillatt, «A AND B» når alle er."""
    if expr in allowed:
        return True
    expr = expr.strip("() ")
    if " OR " in expr:
        return any(ok_expr(p, allowed) for p in expr.split(" OR "))
    if " AND " in expr:
        return all(ok_expr(p, allowed) for p in expr.split(" AND "))
    return expr in allowed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--npm")
    ap.add_argument("--python")
    args = ap.parse_args()
    bad: list[str] = []
    n = 0
    if args.npm:
        for path, pkg in json.load(open(args.npm, encoding="utf-8"))["packages"].items():
            if not path:
                continue
            n += 1
            lic = pkg.get("license")
            if not lic or not ok_expr(str(lic), NPM_OK):
                bad.append(f"npm: {path.split('node_modules/')[-1]} {pkg.get('version', '')}: {lic}")
    if args.python:
        for pkg in json.load(open(args.python, encoding="utf-8")):
            if OWN.match(pkg["Name"]):
                continue
            n += 1
            if not ok_expr(pkg["License"], PYTHON_OK):
                bad.append(f"python: {pkg['Name']} {pkg['Version']}: {pkg['License']}")
    for b in bad:
        print("FEIL: lisens utenfor lista:", b)
    print(f"{n} pakker kontrollert, {len(bad)} utenfor lista.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
