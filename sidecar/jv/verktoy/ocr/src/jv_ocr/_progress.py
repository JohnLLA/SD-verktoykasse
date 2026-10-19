"""ocrmypdf plugin that forwards page progress to a Python callback.

ocrmypdf loads this module through its plugin system (``plugins=[...]``).
The progress bar object lives in the main process, so a module-level
callback is enough. Only the per-page "OCR" step is forwarded.
"""

from __future__ import annotations

from collections.abc import Callable

from ocrmypdf import hookimpl

# Set by core.ocr_file before calling ocrmypdf; receives a fraction 0..1.
callback: Callable[[float], None] | None = None


class _PageProgress:
    def __init__(self, *, total=None, desc=None, unit=None, disable=False, **_kwargs):
        self._total = float(total) if total else 0.0
        self._done = 0.0
        self._active = bool(desc == "OCR" and unit == "page" and self._total > 0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def update(self, n=1, *, completed=None):
        if not self._active or callback is None:
            return
        if completed is not None:
            self._done = float(completed)
        else:
            self._done += float(n if n is not None else 1)
        callback(min(1.0, self._done / self._total))


@hookimpl
def get_progressbar_class():
    return _PageProgress
