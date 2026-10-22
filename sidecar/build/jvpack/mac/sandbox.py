# SPDX-License-Identifier: AGPL-3.0-or-later
"""The app's sandbox on macOS, for running packed tools outside the app.

Same profile and the same rules as the Rust module
(src-tauri/src/tools/jv/sandbox/mod.rs):

  /usr/bin/sandbox-exec -f <profil.sb + generated lines> -D NAME=value ... <entry> <args>

- The profile is the fixed template src-tauri/src/tools/jv/sandbox/profil.sb.
  Paths never go into the profile text, only into -D parameters. The only
  generated lines are «(allow file-read* (literal (param "IN_3")))» (subpath
  for folders) and «(allow process-exec-interpreter (literal (param "INTERP_0")))».
- All paths are canonical (realpath): /var and /private/var are the same place.
- Each run gets its own folder with the profile and tmp/ (TMPDIR), removed
  afterwards.

The app knows from its whitelist which arguments are files (inputs, --plan,
--terms) and which folder is written (--out, the folder of datawrapper's --csv).
Here, for the tools' own tests, every argument that is an existing path is a
file to read, the value after --out is the folder to write, and the folder of
the value after --csv (datawrapper) is the folder to write.

`extra` lets the tests add stricter rules after the app's (never looser).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
PROFILE = Path(__file__).resolve().parents[4] / "src-tauri" / "src" / "tools" / "jv" / "sandbox" / "profil.sb"

# Same table as sandbox::interpreters in Rust.
INTERPRETERS = {"metadata": ["/usr/bin/perl"]}


def _canonical(p: str) -> str:
    """realpath; for a path that does not exist yet, the real parent + the last part."""
    path = Path(p)
    if path.exists():
        return os.path.realpath(path)
    return os.path.join(os.path.realpath(path.parent), path.name)


def access_from_argv(tool_id: str, argv: list[str]) -> tuple[list[str], str | None]:
    """(paths to read, folder to write) from a tool's argument list."""
    read: list[str] = []
    write: str | None = None
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if arg == "--out" and nxt is not None:
            write = nxt
            skip_next = True
            continue
        if tool_id == "datawrapper" and arg == "--csv" and nxt is not None:
            write = str(Path(nxt).parent)
            skip_next = True
            continue
        if arg.startswith("--out="):
            write = arg[len("--out="):]
            continue
        if not arg.startswith("-") and os.path.lexists(arg):
            read.append(arg)
    return read, write


def profile_and_params(
    package: Path, tool_id: str, argv: list[str], tmp: Path, extra: str = ""
) -> tuple[str, list[tuple[str, str]]]:
    read, write = access_from_argv(tool_id, argv)
    home = os.path.realpath(os.environ["HOME"]) if os.environ.get("HOME") else "/Users"
    tmp_c = os.path.realpath(tmp)
    params = [
        ("HOME", home),
        ("PKG", os.path.realpath(package)),
        ("OUT", _canonical(write) if write else tmp_c),
        ("TMP", tmp_c),
    ]
    text = PROFILE.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    for i, p in enumerate(read):
        real = os.path.realpath(p)
        kind = "subpath" if os.path.isdir(real) else "literal"
        text += f'(allow file-read* ({kind} (param "IN_{i}")))\n'
        params.append((f"IN_{i}", real))
    for i, p in enumerate(INTERPRETERS.get(tool_id, [])):
        text += f'(allow process-exec-interpreter (literal (param "INTERP_{i}")))\n'
        params.append((f"INTERP_{i}", p))
    return text + extra, params


@contextlib.contextmanager
def sandboxed(
    package: Path, tool_id: str, entry: str, argv: list[str], extra: str = ""
) -> Iterator[tuple[list[str], str]]:
    """(command, TMPDIR) for `<entry> <tool_id> <argv...>` inside the sandbox.

    The run folder (profile and TMPDIR) is removed afterwards.
    """
    run_dir = Path(tempfile.mkdtemp(prefix="jv-kjoring-"))
    try:
        tmp = run_dir / "tmp"
        tmp.mkdir()
        text, params = profile_and_params(package, tool_id, argv, tmp, extra)
        profile = run_dir / "profil.sb"
        profile.write_text(text, encoding="utf-8")
        cmd = [SANDBOX_EXEC, "-f", str(profile)]
        for name, value in params:
            cmd += ["-D", f"{name}={value}"]
        yield [*cmd, entry, tool_id, *argv], str(tmp)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
