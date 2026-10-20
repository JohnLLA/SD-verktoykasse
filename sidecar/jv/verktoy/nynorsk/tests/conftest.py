"""Fixtures for jv-nynorsk: fake Apertium programs and a fake language pair."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TESTDATA = REPO_ROOT / "testdata" / "nynorsk"
FAKE_SOURCE = Path(__file__).with_name("fake_apertium.py")


FAKE_STAGE = "lt-proc $1 -b 'apertium-nno-nob/{mode}.autobil.bin' $2\n"


@dataclass
class FakeApertium:
    datadir: Path
    log: Path

    def remove_mode(self, mode: str) -> None:
        (self.datadir / "modes" / f"{mode}.mode").unlink()

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text("utf-8").splitlines()]


@pytest.fixture
def testdata() -> Path:
    return TESTDATA


@pytest.fixture
def fake_apertium(tmp_path, monkeypatch) -> FakeApertium:
    """A data folder with nob-nno and nno-nob, and fake_apertium.py as every program."""
    from jv_nynorsk import core

    datadir = tmp_path / "fake-apertium"
    (datadir / "modes").mkdir(parents=True)
    (datadir / "apertium-nno-nob").mkdir()
    for mode in ("nob-nno", "nno-nob"):
        (datadir / "modes" / f"{mode}.mode").write_text(FAKE_STAGE.format(mode=mode), encoding="utf-8")
        (datadir / "apertium-nno-nob" / f"{mode}.autobil.bin").write_bytes(b"")

    def program_argv(name: str) -> list[str] | None:
        if name in core.PIPELINE_PROGRAMS:
            return [sys.executable, str(FAKE_SOURCE), name]
        return None

    monkeypatch.setattr(core, "_program_argv", program_argv)
    monkeypatch.setenv("APERTIUM_DATADIR", str(datadir))
    log = tmp_path / "apertium-calls.jsonl"
    monkeypatch.setenv("FAKE_APERTIUM_LOG", str(log))
    for var in (
        "FAKE_APERTIUM_FAIL",
        "FAKE_APERTIUM_JOIN_LINES",
        "FAKE_APERTIUM_MOVE_SYMBOLS",
        "FAKE_APERTIUM_SPLIT_WORD",
    ):
        monkeypatch.delenv(var, raising=False)
    return FakeApertium(datadir, log)


@pytest.fixture
def no_apertium(tmp_path, monkeypatch) -> None:
    """PATH without any Apertium program (only an empty directory), and no data folder."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.delenv("APERTIUM_DATADIR", raising=False)
