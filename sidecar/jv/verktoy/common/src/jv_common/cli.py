"""The `jv` command: finds tools via entry points in the group "jv.tools"."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib.metadata import EntryPoint, entry_points

from .errors import UserError, run_cli

GROUP = "jv.tools"

USAGE = """\
Bruk: jv <verktøy> <inngang...> --out <mappe> [valg]
      jv --list       vis tilgjengelige verktøy
      jv <verktøy> --help
"""


def discover_tools() -> dict[str, EntryPoint]:
    """All registered tools, keyed by id."""
    return {ep.name: ep for ep in entry_points(group=GROUP)}


def _summary(ep: EntryPoint) -> str:
    try:
        dist = ep.dist
        return (dist.metadata.get("Summary") or "") if dist else ""
    except Exception:  # noqa: BLE001
        return ""


def format_tool_list(tools: dict[str, EntryPoint]) -> str:
    if not tools:
        return "Ingen verktøy er installert ennå. Kjør «uv sync --all-packages»."
    width = max(len(name) for name in tools)
    lines = ["Tilgjengelige verktøy:"]
    for name in sorted(tools):
        lines.append(f"  {name.ljust(width)}  {_summary(tools[name])}".rstrip())
    return "\n".join(lines)


def _dispatch(args: list[str]) -> int:
    if not args:
        print(USAGE, file=sys.stderr)
        return 1
    first = args[0]
    if first in ("-h", "--help"):
        print(USAGE)
        print(format_tool_list(discover_tools()))
        return 0
    if first == "--list":
        print(format_tool_list(discover_tools()))
        return 0
    tools = discover_tools()
    if first not in tools:
        raise UserError(f"Ukjent verktøy «{first}». Se «jv --list».")
    tool_main = tools[first].load()
    result = tool_main(args[1:])
    return 0 if result is None else int(result)


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(_dispatch, argv)


def entry() -> None:
    sys.exit(main())
