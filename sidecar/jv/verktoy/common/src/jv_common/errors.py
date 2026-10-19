"""Error handling: Norwegian messages, no stack trace unless --debug."""

from __future__ import annotations

import argparse
import errno
import re
import sys
import traceback
from collections.abc import Callable, Sequence

EXIT_OK = 0
EXIT_USER = 1
EXIT_INTERNAL = 2


class UserError(Exception):
    """An error the user can fix (bad input, missing program). Exit code 1."""

    exit_code = EXIT_USER


def run_cli(
    func: Callable[[list[str]], int | None],
    argv: Sequence[str] | None = None,
) -> int:
    """Call func(argv) and turn exceptions into exit codes.

    UserError and OSErrors the user can fix (no permission, read-only or
    full disk) -> "Feil: ..." on stderr, code 1. Any other exception ->
    "Intern feil: ..." on stderr, code 2. The stack trace is printed only
    when "--debug" is in argv. argv is passed on unchanged.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    debug = "--debug" in args
    try:
        result = func(args)
        return EXIT_OK if result is None else int(result)
    except UserError as exc:
        if debug:
            traceback.print_exc()
        print(f"Feil: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("Avbrutt.", file=sys.stderr)
        return 130
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return EXIT_OK
        if isinstance(code, int):
            return code
        print(str(code), file=sys.stderr)
        return EXIT_USER
    except OSError as exc:
        message = os_error_message(exc)
        if message is None:
            return _internal(exc, debug)
        if debug:
            traceback.print_exc()
        print(f"Feil: {message}", file=sys.stderr)
        return EXIT_USER
    except Exception as exc:  # noqa: BLE001 - last line of defence
        return _internal(exc, debug)


def _internal(exc: BaseException, debug: bool) -> int:
    """Report an unexpected exception (called from inside an except block)."""
    if debug:
        traceback.print_exc()
    print(
        f"Intern feil: {type(exc).__name__}: {exc}. "
        "Kjør på nytt med --debug for detaljer.",
        file=sys.stderr,
    )
    return EXIT_INTERNAL


# errno values that mean "the user can fix this" when writing output.
_USER_ERRNOS = {
    errno.EACCES: "mangler skrivetilgang",
    errno.EPERM: "operasjonen er ikke tillatt",
    errno.EROFS: "disken er skrivebeskyttet",
    errno.ENOSPC: "det er ikke mer plass på disken",
    errno.EDQUOT: "diskkvoten er brukt opp",
}


def os_error_message(exc: OSError) -> str | None:
    """Norwegian message for OSErrors the user can fix, else None."""
    reason = _USER_ERRNOS.get(exc.errno) if exc.errno is not None else None
    if reason is None and isinstance(exc, PermissionError):
        reason = _USER_ERRNOS[errno.EACCES]
    if reason is None:
        return None
    target = exc.filename
    where = f" «{target}»" if target else ""
    return (
        f"Filsystemet nektet tilgang{where}: {reason}. "
        "Sjekk tilgangen, eller velg en annen utmappe med --out."
    )


# Common argparse messages (Python 3.12) -> Norwegian. Order matters.
_ARGPARSE_TRANSLATIONS: list[tuple[str, str]] = [
    (r"the following arguments are required: (.+)", r"disse argumentene mangler: \1"),
    (r"unrecognized arguments: (.+)", r"ukjente argumenter: \1"),
    (r"one of the arguments (.+) is required", r"ett av argumentene \1 må oppgis"),
    (r"ambiguous option: (\S+) could match (.+)", r"tvetydig valg: \1 kan bety \2"),
    (r"argument (.+?): expected one argument", r"argumentet \1 trenger én verdi"),
    (r"argument (.+?): expected at least one argument", r"argumentet \1 trenger minst én verdi"),
    (r"argument (.+?): expected at most one argument", r"argumentet \1 tar høyst én verdi"),
    (r"argument (.+?): expected (\d+) arguments?", r"argumentet \1 trenger \2 verdier"),
    (r"argument (.+?): invalid choice: (.+?) \(choose from (.+)\)",
     r"argumentet \1: ugyldig valg \2 (velg mellom \3)"),
    (r"argument (.+?): invalid int value: (.+)", r"argumentet \1: \2 er ikke et heltall"),
    (r"argument (.+?): invalid float value: (.+)", r"argumentet \1: \2 er ikke et tall"),
    (r"argument (.+?): invalid (\S+) value: (.+)", r"argumentet \1: ugyldig verdi \3"),
    (r"argument (.+?): not allowed with argument (.+)",
     r"argumentet \1 kan ikke brukes sammen med \2"),
    (r"argument (.+?): ignored explicit argument (.+)",
     r"argumentet \1 tar ingen verdi (fikk \2)"),
    (r"expected one argument", r"trenger én verdi"),
]


def translate_argparse_message(message: str) -> str:
    """Translate a known argparse error message to Norwegian."""
    for pattern, replacement in _ARGPARSE_TRANSLATIONS:
        if re.fullmatch(pattern, message):
            return re.sub(pattern, replacement, message)
    return message


class _NorwegianArgumentParser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[override]
        raise UserError(
            f"Ugyldige argumenter: {translate_argparse_message(message)}. "
            f"Se «{self.prog} --help»."
        )


def make_parser(prog: str, description: str = "") -> argparse.ArgumentParser:
    """ArgumentParser that raises UserError (code 1) on bad arguments
    instead of exiting with code 2, and already has --debug."""
    parser = _NorwegianArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "--debug", action="store_true", help="vis full feilsporing ved feil"
    )
    return parser
