"""Bad input gives a Norwegian message and exit code 1, never a stack trace."""

import pytest


def _assert_user_error(code, report, err, needle):
    assert code == 1
    assert report is None
    assert err.startswith("Feil:")
    assert needle in err
    assert "Traceback" not in err


def test_missing_file(run, tmp_path):
    _assert_user_error(*run("vis", tmp_path / "finnes ikke.jpg"), "finnes ikke")


def test_empty_file(run, tmp_path):
    f = tmp_path / "tom.pdf"
    f.write_bytes(b"")
    _assert_user_error(*run("vask", f, "--out", tmp_path / "ut"), "tom")


@pytest.mark.parametrize("name", ["falsk.pdf", "falsk.jpg", "falsk.docx", "falsk.png"])
def test_wrong_format(run, tmp_path, name):
    f = tmp_path / name
    f.write_text("Dette er bare tekst.", encoding="utf-8")
    _assert_user_error(*run("vask", f, "--out", tmp_path / "ut"), "gyldig")
    assert not (tmp_path / "ut").exists() or list((tmp_path / "ut").iterdir()) == []


def test_unsupported_type(run, tmp_path):
    f = tmp_path / "notat.txt"
    f.write_text("hei", encoding="utf-8")
    _assert_user_error(*run("vis", f), "støttes ikke")


def test_broken_pdf(run, tmp_path):
    f = tmp_path / "ødelagt.pdf"
    f.write_bytes(b"%PDF-1.4\ngarbage without objects\n")
    code, report, err = run("vis", f)
    assert code == 1
    assert "Traceback" not in err


def test_zip_that_is_not_office(run, tmp_path):
    import zipfile

    f = tmp_path / "arkiv.docx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("hei.txt", "hei")
    _assert_user_error(*run("vis", f), "Office")


def test_missing_out(run, data_dir):
    _assert_user_error(*run("vask", data_dir / "dokument_forfatter.pdf"), "--out")


def test_missing_command(run):
    code, _, err = run()
    assert code == 1
    assert "Traceback" not in err


def test_partial_failure_in_folder(run, copy_to, tmp_path):
    copy_to("dokument_forfatter.docx")
    (tmp_path / "inn" / "ødelagt.pdf").write_bytes(b"%PDF-1.4\ngarbage\n")
    code, report, err = run("vis", tmp_path / "inn")
    assert code == 1
    assert len(report["outputs"]) == 1
    assert any("ødelagt.pdf" in w for w in report["warnings"])
