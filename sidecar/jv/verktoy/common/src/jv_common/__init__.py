"""Shared building blocks for journalistverktøy."""

from .errors import (
    EXIT_INTERNAL,
    EXIT_OK,
    EXIT_USER,
    UserError,
    make_parser,
    run_cli,
)
from .paths import safe_output_path
from .progress import emit
from .report import build_report, print_report, sha256_file
from .tools import has_binary, require_binary, skip_if_missing

__version__ = "0.1.0"

__all__ = [
    "EXIT_INTERNAL",
    "EXIT_OK",
    "EXIT_USER",
    "UserError",
    "build_report",
    "emit",
    "has_binary",
    "make_parser",
    "print_report",
    "require_binary",
    "run_cli",
    "safe_output_path",
    "sha256_file",
    "skip_if_missing",
]
