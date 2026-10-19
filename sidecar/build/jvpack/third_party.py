# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIRD_PARTY_LICENSES.md (repo root): the parts inside the tool packages.

    python -m jvpack lisenser

Read from «Kildekode og versjoner.txt» in every built package
(out/work/<target>/<id>/pakke/Lisenser). The Rust and npm parts of the app
are listed in src/assets/tredjepart.txt (tools/lag-tredjepartsmelding.mjs);
merging the two lists is byggmester's step (docs/brief-jv-distribusjon.md).
"""

from __future__ import annotations

from pathlib import Path

from . import SIDECAR, WORK

OUT = SIDECAR.parent / "THIRD_PARTY_LICENSES.md"


def _parse(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    items, kind = [], ""
    for i, line in enumerate(lines):
        if line.startswith("== ") and line.endswith(" =="):
            kind = line.strip("= ")
        if line.startswith("  Lisens:"):
            name_ver = lines[i - 1].rsplit(" ", 1)
            src = lines[i + 1].split(":", 1)[1].strip() if i + 1 < len(lines) else ""
            items.append({"name": name_ver[0], "version": name_ver[1] if len(name_ver) > 1 else "",
                          "license": line.split(":", 1)[1].strip(), "source": src, "kind": kind})
    return items


def main() -> int:
    rows: dict[tuple[str, str], dict] = {}
    for txt in sorted(WORK.glob("*/*/pakke/Lisenser/Kildekode og versjoner.txt")):
        target, tool_id = txt.parts[-5], txt.parts[-4]
        for it in _parse(txt):
            r = rows.setdefault((it["name"], it["version"]), {**it, "tools": set(), "targets": set()})
            r["tools"].add(tool_id)
            r["targets"].add(target)
    out = [
        "# Tredjepartsprogramvare",
        "",
        "LLAs verktøykasse er fri programvare under AGPL-3.0-or-later (`LICENSE`).",
        "",
        "## Verktøypakkene (journalistverktøyene)",
        "",
        "Generert av `sidecar/build` (`python -m jvpack lisenser`) fra pakkene som er bygget. "
        "Hver pakke har lisenstekstene i `Lisenser/` og samme liste i «Kildekode og versjoner.txt». "
        "Systemprogrammene står med kilde og SHA-256 i `sidecar/build/binaries.json`.",
        "",
        "Rust- og npm-delene av appen står i `src/assets/tredjepart.txt` (Om-vinduet). "
        "De to listene slås sammen av byggmester (docs/brief-jv-distribusjon.md).",
        "",
        "| Del | Versjon | Lisens | Type | Brukt i | Kilde |",
        "|---|---|---|---|---|---|",
    ]
    for (name, version), r in sorted(rows.items(), key=lambda kv: (kv[1]["kind"], kv[0][0].lower())):
        src = r["source"].replace("|", "\\|")
        out.append(f"| {name} | {version} | {r['license'].replace('|', '/')} | {r['kind']} | "
                   f"{', '.join(sorted(r['tools']))} | {src} |")
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(OUT, len(rows))
    return 0
