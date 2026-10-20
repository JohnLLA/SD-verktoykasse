# SPDX-License-Identifier: AGPL-3.0-or-later
"""pytest plugin: run the tools' own tests against an unpacked package.

    JV_PACKAGE_DIR=<unpacked package> \
    PYTHONPATH=sidecar/build uv run pytest -p pytest_packaged verktoy/<id>

Every test that calls `jv_<id>.cli.main(argv)` or `jv_common.cli.main([id, ...])`
gets the packaged binary instead: `<entry> <id> <argv...>` in a subprocess,
with the environment from jv-package.json (jvpack.pack.package_env, the same
rules as the Rust module) and inside `sandbox-exec` with

  - no network (outbound and inbound IP denied; Unix sockets still allowed,
    multiprocessing needs them), and
  - no reads from /opt/homebrew, /usr/local or ~/.local, so a Homebrew
    program can never stand in for a missing bundled one.

The report on stdout and the progress lines on stderr are written to the test's
own sys.stdout/sys.stderr, so capsys sees exactly what the app would see.

Tests that use `monkeypatch` (themselves or through a fixture, such as the
fake apertium in nynorsk) patch the tool's internals or the environment in
process; the patch cannot reach a subprocess, so they keep running in process
and are counted separately. Unit tests of core functions run in process too.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jvpack import pack

HIDDEN = ["/opt/homebrew", "/usr/local", str(Path.home() / ".local")]
SANDBOX = (
    "(version 1)(allow default)"
    '(deny network-outbound (remote ip "*:*"))'
    '(deny network-inbound (local ip "*:*"))'
    "(deny file-read* " + " ".join(f'(subpath "{p}")' for p in HIDDEN) + ")"
)

_ROOT: Path | None = None
_DATA: dict = {}
_COUNTS = {"pakket": 0, "i_prosess_monkeypatch": 0}


def pytest_configure(config):
    global _ROOT, _DATA
    root = os.environ.get("JV_PACKAGE_DIR")
    if not root:
        raise pytest.UsageError("JV_PACKAGE_DIR må peke på en utpakket verktøypakke.")
    _ROOT = Path(root).resolve()
    _DATA = pack.load_manifest(_ROOT)
    # skip_if_missing() and in-process code look in PATH: use the package's
    # programs and the system, never Homebrew.
    env = pack.package_env(_ROOT, _DATA)
    os.environ["PATH"] = env["PATH"]
    for name, value in env.items():
        # JV_* only reach the packaged binary: in-process tests that hide a
        # program (monkeypatch shutil.which) must not find it via JV_<NAME>.
        if name not in ("HOME", "TMPDIR") and not name.startswith("JV_"):
            os.environ[name] = value


def _run_packed(argv) -> int:
    cmd = ["/usr/bin/sandbox-exec", "-p", SANDBOX, pack.entry(_ROOT, _DATA), _DATA["id"], *map(str, argv)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          env=pack.package_env(_ROOT, _DATA), timeout=900)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    _COUNTS["pakket"] += 1
    return proc.returncode


# The root conftest's network block uses monkeypatch on socket only; it does
# not change anything the packaged binary would see.
_IGNORED_MONKEYPATCH_USERS = {"_block_network"}


def _uses_monkeypatch(request) -> bool:
    info = request.node._fixtureinfo
    if "monkeypatch" in info.argnames:
        return True
    for name in request.fixturenames:
        if name in _IGNORED_MONKEYPATCH_USERS:
            continue
        for fixturedef in info.name2fixturedefs.get(name, ()):
            if "monkeypatch" in fixturedef.argnames:
                return True
    return False


@pytest.fixture(autouse=True)
def _packaged_binary(request):
    tool_id = _DATA["id"]
    # A test that uses monkeypatch, directly or through a fixture (for example
    # nynorsk's fake apertium first in PATH), changes things in this process
    # that cannot reach the packaged binary: it runs in process.
    if _uses_monkeypatch(request):
        _COUNTS["i_prosess_monkeypatch"] += 1
        yield
        return
    mp = pytest.MonkeyPatch()
    module = importlib.import_module(f"jv_{tool_id.replace('-', '_')}.cli")
    import jv_common.cli as jv_cli

    def dispatch(argv=None):
        argv = list(argv or [])
        if argv and argv[0] == tool_id:
            return _run_packed(argv[1:])
        raise AssertionError("bare dette verktøyet finnes i pakken")

    packed = lambda argv=None: _run_packed(list(argv or []))  # noqa: E731
    originals = {id(module.main): packed, id(jv_cli.main): dispatch}
    mp.setattr(module, "main", packed)
    mp.setattr(jv_cli, "main", dispatch)
    # Tests and conftest files often do «from jv_<id>.cli import main»: patch
    # every name in the tool's test modules that is one of the two functions.
    tests_dir = str(Path(request.node.path).resolve().parent)
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if not f or not str(Path(f).resolve()).startswith(tests_dir):
            continue
        for name, value in list(vars(mod).items()):
            if id(value) in originals and callable(value):
                mp.setattr(mod, name, originals[id(value)])
    try:
        yield
    finally:
        mp.undo()


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(
        f"jv-pakke {_DATA.get('id')} {_DATA.get('version')}: {_COUNTS['pakket']} kjøringer av den pakkede "
        f"binærfila (sandbox uten nett), {_COUNTS['i_prosess_monkeypatch']} tester i prosess (monkeypatch)."
    )
