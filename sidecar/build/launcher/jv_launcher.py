# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point of a packed jv tool (PyInstaller, command line only, no tkinter).

    jv --version                         JSON with id, version and bundled programs
    jv <id> <inputs...> --out <dir> ...  the tool, same contract as «jv <id>»

The environment (PATH, JV_*, TESSDATA_PREFIX, ...) is set by the caller
from jv-package.json. Nothing here touches the network.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys


def _utf8_streams() -> None:
    # The report is JSON on stdout; never let the locale decide the encoding.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _version(cfg) -> int:
    """Print id and version, and run each bundled program once.

    This is the trial run the app does before a package is taken into use:
    it fails (code 2) if Python or a bundled program cannot start.
    cfg.PROGRAMS maps program -> version arguments (None: only check that
    JV_<NAME> points to an executable file).
    """
    programs = {}
    ok = True
    for name, version_args in cfg.PROGRAMS.items():
        var = "JV_" + name.upper().replace("-", "_")
        path = os.environ.get(var)
        if not path or not os.path.isabs(path):
            programs[name] = {"ok": False, "error": f"{var} er ikke satt"}
            ok = False
            continue
        if version_args is None:
            good = os.path.isfile(path) and os.access(path, os.X_OK)
            programs[name] = {"ok": good, "version": ""}
            ok = ok and good
            continue
        try:
            proc = subprocess.run([path, *version_args], capture_output=True, text=True, timeout=30)
            first = (proc.stdout or proc.stderr).strip().splitlines()[:1]
            programs[name] = {"ok": proc.returncode == 0, "version": first[0] if first else ""}
            ok = ok and proc.returncode == 0
        except (OSError, subprocess.SubprocessError) as exc:
            programs[name] = {"ok": False, "error": type(exc).__name__}
            ok = False
    print(json.dumps({"id": cfg.TOOL_ID, "version": cfg.VERSION, "programs": programs}, ensure_ascii=False))
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    import jv_pack_config as cfg  # written by the build

    _utf8_streams()
    if argv == ["--version"]:
        return _version(cfg)
    if not argv or argv[0] != cfg.TOOL_ID:
        print(
            f"Feil: denne pakken inneholder bare «{cfg.TOOL_ID}». "
            f"Bruk: jv {cfg.TOOL_ID} <inngang…> --out <mappe>",
            file=sys.stderr,
        )
        return 1
    from importlib.metadata import EntryPoint

    tool_main = EntryPoint(name=cfg.TOOL_ID, value=cfg.ENTRY, group="jv.tools").load()
    result = tool_main(argv[1:])
    return 0 if result is None else int(result)


if __name__ == "__main__":
    # ocrmypdf can start worker processes; in a frozen build they start this
    # executable again, and freeze_support() sends them to the worker code.
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:]))
