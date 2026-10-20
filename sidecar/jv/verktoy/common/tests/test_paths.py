import pytest

from jv_common import UserError, safe_output_path


def test_new_name_in_other_dir(tmp_path):
    src = tmp_path / "inn" / "vedtak.pdf"
    src.parent.mkdir()
    src.write_bytes(b"x")
    out = safe_output_path(src, tmp_path / "ut", "-sladdet.pdf")
    assert out == tmp_path / "ut" / "vedtak-sladdet.pdf"
    assert out.parent.is_dir()


def test_collision_adds_counter(tmp_path):
    src = tmp_path / "vedtak.pdf"
    src.write_bytes(b"x")
    out_dir = tmp_path / "ut"
    out_dir.mkdir()
    (out_dir / "vedtak.pdf").write_bytes(b"1")
    (out_dir / "vedtak-2.pdf").write_bytes(b"2")
    assert safe_output_path(src, out_dir, ".pdf") == out_dir / "vedtak-3.pdf"


def test_same_dir_same_name_raises(tmp_path):
    src = tmp_path / "vedtak.pdf"
    src.write_bytes(b"x")
    with pytest.raises(UserError, match="samme navn som originalen"):
        safe_output_path(src, tmp_path, ".pdf")


def test_same_dir_different_suffix_ok(tmp_path):
    src = tmp_path / "vedtak.pdf"
    src.write_bytes(b"x")
    out = safe_output_path(src, tmp_path, "-ocr.pdf")
    assert out == tmp_path / "vedtak-ocr.pdf"
    assert out != src


def test_never_returns_input(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    for suffix in (".txt", "-ut.txt", ".md"):
        try:
            assert safe_output_path(src, tmp_path, suffix).resolve() != src.resolve()
        except UserError:
            pass


def test_out_dir_is_file_raises(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    blocker = tmp_path / "fil"
    blocker.write_text("x")
    with pytest.raises(UserError):
        safe_output_path(src, blocker, ".md")
