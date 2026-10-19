from importlib.metadata import EntryPoint

import pytest

from jv_common import UserError, cli


def fake_tool(argv):
    print("args:" + ",".join(argv))
    return 0


def failing_tool(argv):
    raise UserError("Mangler --out.")


@pytest.fixture
def fake_tools(monkeypatch):
    tools = {
        "demo": EntryPoint("demo", f"{__name__}:fake_tool", cli.GROUP),
        "feiler": EntryPoint("feiler", f"{__name__}:failing_tool", cli.GROUP),
    }
    monkeypatch.setattr(cli, "discover_tools", lambda: tools)
    return tools


def test_list(fake_tools, capsys):
    assert cli.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "Tilgjengelige verktøy" in out and "demo" in out and "feiler" in out


def test_dispatch_passes_remaining_args(fake_tools, capsys):
    assert cli.main(["demo", "inn.pdf", "--out", "ut"]) == 0
    assert "args:inn.pdf,--out,ut" in capsys.readouterr().out


def test_tool_user_error(fake_tools, capsys):
    assert cli.main(["feiler"]) == 1
    assert "Feil: Mangler --out." in capsys.readouterr().err


def test_unknown_tool(fake_tools, capsys):
    assert cli.main(["finnesikke"]) == 1
    assert "Ukjent verktøy" in capsys.readouterr().err


def test_no_args_shows_usage(fake_tools, capsys):
    assert cli.main([]) == 1
    assert "Bruk: jv" in capsys.readouterr().err


def test_help(fake_tools, capsys):
    assert cli.main(["--help"]) == 0
    assert "Bruk: jv" in capsys.readouterr().out


def test_empty_list(monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover_tools", lambda: {})
    assert cli.main(["--list"]) == 0
    assert "Ingen verktøy" in capsys.readouterr().out


def test_real_discovery_runs():
    assert isinstance(cli.discover_tools(), dict)
