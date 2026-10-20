"""Fixtures for jv-nynorsk: a fake ``apertium`` placed first in PATH."""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TESTDATA = REPO_ROOT / "testdata" / "nynorsk"
FAKE_SOURCE = Path(__file__).with_name("fake_apertium.py")


@dataclass
class FakeApertium:
    bin_dir: Path
    log: Path

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text("utf-8").splitlines()]


@pytest.fixture
def testdata() -> Path:
    return TESTDATA


@pytest.fixture
def fake_apertium(tmp_path, monkeypatch) -> FakeApertium:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    script = bin_dir / "apertium"
    script.write_text(
        f"#!{sys.executable}\n" + FAKE_SOURCE.read_text("utf-8"), encoding="utf-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "apertium-calls.jsonl"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_APERTIUM_LOG", str(log))
    for var in (
        "FAKE_APERTIUM_MODES",
        "FAKE_APERTIUM_NO_LIST",
        "FAKE_APERTIUM_FAIL",
        "FAKE_APERTIUM_JOIN_LINES",
        "FAKE_APERTIUM_MOVE_SYMBOLS",
        "FAKE_APERTIUM_SPLIT_WORD",
    ):
        monkeypatch.delenv(var, raising=False)
    return FakeApertium(bin_dir, log)


@pytest.fixture
def no_apertium(tmp_path, monkeypatch) -> None:
    """PATH without any apertium (only an empty directory)."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
