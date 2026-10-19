"""The JSON report every tool prints on stdout."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TextIO

_CHUNK = 1024 * 1024


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Return the hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _output_entry(item: Any) -> Any:
    if isinstance(item, os.PathLike):
        return str(item)
    return item


def build_report(
    tool: str,
    version: str,
    inputs: Iterable[str | os.PathLike[str]],
    outputs: Iterable[Any] = (),
    warnings: Iterable[str] = (),
    summary: str = "",
) -> dict[str, Any]:
    """Build the contract report.

    inputs: file paths; each gets {"path", "sha256"}.
    outputs: paths (converted to str) or ready-made dicts/strings, kept as-is.
    """
    return {
        "tool": tool,
        "version": version,
        "inputs": [
            {"path": str(Path(p)), "sha256": sha256_file(p)} for p in inputs
        ],
        "outputs": [_output_entry(o) for o in outputs],
        "warnings": [str(w) for w in warnings],
        "summary": summary,
    }


def print_report(report: dict[str, Any], file: TextIO | None = None) -> None:
    """Write the report as JSON (UTF-8, not ASCII-escaped) to stdout."""
    out = sys.stdout if file is None else file
    out.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    out.flush()
