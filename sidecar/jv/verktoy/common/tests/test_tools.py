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
