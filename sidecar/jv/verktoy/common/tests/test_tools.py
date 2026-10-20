import os
import stat

import pytest

from jv_common import UserError, has_binary, require_binary, skip_if_missing


def test_require_binary_found():
    assert require_binary("sh").endswith("sh")


def test_require_binary_missing_gives_brew_hint():
    with pytest.raises(UserError, match="brew install"):
        require_binary("finnes-ikke-jv-12345")


def test_require_binary_known_formula(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(UserError, match="brew install ffmpeg"):
        require_binary("ffprobe")


def test_require_binary_without_formula_points_to_guide(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(UserError, match="OPPSETT.md") as e:
        require_binary("apertium")
    assert "brew" not in str(e.value)


def test_has_binary():
    assert has_binary("sh")
    assert not has_binary("finnes-ikke-jv-12345")


def test_skip_if_missing_mark():
    mark = skip_if_missing("finnes-ikke-jv-12345")
    assert mark.mark.name == "skipif"
    assert mark.mark.args == (True,)
    assert "finnes-ikke-jv-12345" in mark.mark.kwargs["reason"]
    assert skip_if_missing("sh").mark.args == (False,)


@skip_if_missing("finnes-ikke-jv-12345")
def test_is_skipped():
    raise AssertionError("skulle vært hoppet over")


def _fake_program(tmp_path, name="ffprobe"):
    exe = tmp_path / name
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def test_require_binary_prefers_jv_variable(tmp_path, monkeypatch):
    exe = _fake_program(tmp_path)
    monkeypatch.setenv("JV_FFPROBE", str(exe))
    monkeypatch.setattr("shutil.which", lambda name: "/fra/path/ffprobe")
    assert require_binary("ffprobe") == str(exe)
    assert has_binary("ffprobe")


def test_jv_variable_name_for_dashes(tmp_path, monkeypatch):
    exe = _fake_program(tmp_path, "pdf-to-x")
    monkeypatch.setenv("JV_PDF_TO_X", str(exe))
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert require_binary("pdf-to-x") == str(exe)


def test_jv_variable_that_is_not_a_program_falls_back_to_path(tmp_path, monkeypatch):
    not_exe = tmp_path / "ffprobe"
    not_exe.write_text("ikke kjørbar")
    for value in (str(not_exe), "ffprobe", str(tmp_path / "finnes-ikke"), ""):
        monkeypatch.setenv("JV_FFPROBE", value)
        monkeypatch.setattr("shutil.which", lambda name: "/fra/path/ffprobe")
        assert require_binary("ffprobe") == "/fra/path/ffprobe"
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(UserError, match="brew install ffmpeg"):
        require_binary("ffprobe")


def test_relative_jv_variable_is_ignored(tmp_path, monkeypatch):
    _fake_program(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JV_FFPROBE", "ffprobe")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert not os.path.isabs(os.environ["JV_FFPROBE"])
    assert not has_binary("ffprobe")
