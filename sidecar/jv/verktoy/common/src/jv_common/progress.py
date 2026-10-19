"""Progress lines on stderr: {"progress": 0.42}."""

from __future__ import annotations

import json
import sys
from typing import TextIO


def emit(fraction: float, file: TextIO | None = None) -> None:
    """Write one JSON progress line to stderr. fraction is clamped to 0..1."""
    value = round(min(1.0, max(0.0, float(fraction))), 4)
    out = sys.stderr if file is None else file
    out.write(json.dumps({"progress": value}) + "\n")
    out.flush()
