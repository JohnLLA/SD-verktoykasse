import json
import shutil
from pathlib import Path

import pytest

from jv_metadata.cli import main

DATA = Path(__file__).resolve().parents[3] / "testdata" / "metadata"


@pytest.fixture
def data_dir() -> Path:
    return DATA


@pytest.fixture
def copy_to(tmp_path):
    """Copy a test file into tmp_path/inn under an optional new name."""

    def _copy(name: str, new_name: str | None = None) -> Path:
        dst = tmp_path / "inn" / (new_name or name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DATA / name, dst)
        return dst

    return _copy


@pytest.fixture
def run(capsys):
    """Run the CLI; return (code, report or None, stderr)."""

    def _run(*args):
        code = main([str(a) for a in args])
        captured = capsys.readouterr()
        report = json.loads(captured.out) if captured.out.strip() else None
        return code, report, captured.err

    return _run


def fields_of(output: dict) -> list[dict]:
    return [f for items in output["groups"].values() for f in items]
