"""Safe output paths: never the input file, never an existing file."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import UserError


def _with_counter(name: str, n: int) -> str:
    path = Path(name)
    if path.suffix:
        return f"{path.stem}-{n}{path.suffix}"
    return f"{name}-{n}"


def safe_output_path(
    input: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    suffix: str,
) -> Path:
    """Return a free path in out_dir named <input stem><suffix>.

    suffix examples: ".srt" (new extension) or "-sladdet.pdf".
    Existing files get -2, -3, ... before the extension. Raises UserError
    if the result would be the input file itself, or if out_dir cannot be
    created or written to. Creates out_dir.
    """
    src = Path(input)
    out = Path(out_dir)
    if out.exists() and not out.is_dir():
        raise UserError(f"Utmappen «{out}» finnes og er ikke en mappe.")
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UserError(
            f"Kan ikke lage utmappen «{out}»: {exc.strerror or exc}. "
            "Velg en annen mappe med --out."
        ) from exc
    if not os.access(out, os.W_OK | os.X_OK):
        raise UserError(
            f"Mangler skrivetilgang til utmappen «{out}». "
            "Velg en annen mappe med --out."
        )

    name = src.stem + suffix
    candidate = out / name
    src_resolved = src.resolve()
    if candidate.resolve() == src_resolved:
        raise UserError(
            f"Utfilen ville fått samme navn som originalen «{src.name}» i samme mappe. "
            "Velg en annen mappe med --out, så originalen ikke overskrives."
        )

    n = 2
    while candidate.exists() or candidate.resolve() == src_resolved:
        candidate = out / _with_counter(name, n)
        n += 1
    return candidate
