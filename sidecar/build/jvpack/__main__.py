# SPDX-License-Identifier: AGPL-3.0-or-later
"""python -m jvpack mac <id>[,<id>...]|alle [--notariser [profil]]
        build packages for aarch64-apple-darwin (optionally notarised)
python -m jvpack katalog ...               tools.json and tools.json.sig (see catalog.py)
python -m jvpack lisenser                  write THIRD_PARTY_LICENSES.md
"""

from __future__ import annotations

import json
import sys

from . import OUT, tools


def cmd_mac(ids: list[str], notary_profile: str | None) -> int:
    from .mac.build import build
    from .mac.macho import BuildError
    from .mac import notarize

    if notary_profile and not notarize.profile_works(notary_profile):
        print(f"MERKNAD: notarytool-profilen «{notary_profile}» finnes ikke eller virker ikke. "
              "Pakkene bygges og signeres, men notariseres IKKE.", file=sys.stderr)
        notary_profile = None

    failed = 0
    summary = {}
    for tool_id in ids:
        try:
            r = build(tool_id, notary_profile)
        except BuildError as exc:
            print(f"[{tool_id}] FEIL: {exc}", file=sys.stderr)
            failed += 1
            continue
        ok = all(v[0] for k, v in r.checks.items() if k != "spctl")
        failed += 0 if ok else 1
        summary[tool_id] = {
            "ok": ok, "versjon": r.version, "arkiv": r.archive.name, "arkiv_bytes": r.archive_bytes,
            "utpakket_bytes": r.unpacked_bytes, "sha256": r.sha256, "minste_macos": r.min_os,
            "signering": r.signing, "notarisering": r.notarization, "signerte_filer": r.signed_files, "deler_bytes": r.sizes,
            "manglende_lisenstekster": r.missing_licenses, "sekunder": round(r.seconds),
            "kontroller": {k: {"ok": v[0], "utdata": v[1][-400:]} for k, v in r.checks.items()},
        }
        print(f"[{tool_id}] ferdig: {r.archive.name} ({r.archive_bytes / 1e6:.1f} MB, utpakket "
              f"{r.unpacked_bytes / 1e6:.1f} MB), minste macOS {r.min_os}, {r.notarization}, {r.seconds:.0f} s")
        for k, (good, out) in r.checks.items():
            print(f"    {k}: {'OK' if good else 'IKKE OK'}  {out.splitlines()[-1] if out else ''}")
    OUT.mkdir(exist_ok=True)
    path = OUT / "bygg-oppsummering.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    old.update(summary)
    path.write_text(json.dumps(old, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "mac":
        from .mac.notarize import DEFAULT_PROFILE

        ids = tools.parse_ids(argv[1])
        profile = None
        if "--notariser" in argv:
            i = argv.index("--notariser")
            profile = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else DEFAULT_PROFILE
        return cmd_mac(ids, profile)
    if argv and argv[0] == "lisenser":
        from .third_party import main as tp_main

        return tp_main()
    if argv and argv[0] == "katalog":
        from .catalog import main as catalog_main

        return catalog_main(argv[1:])
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
