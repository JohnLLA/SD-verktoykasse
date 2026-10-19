import pytest

from jv_common import EXIT_INTERNAL, EXIT_USER, UserError, make_parser, run_cli


def _user_error(argv):
    raise UserError("Filen finnes ikke.")


def _crash(argv):
    raise ValueError("noe gikk galt")


def test_user_error_code_1_no_traceback(capsys):
    assert run_cli(_user_error, []) == EXIT_USER
    err = capsys.readouterr().err
    assert "Feil: Filen finnes ikke." in err
    assert "Traceback" not in err


def test_internal_error_code_2_no_traceback(capsys):
    assert run_cli(_crash, []) == EXIT_INTERNAL
    err = capsys.readouterr().err
    assert "Intern feil" in err and "--debug" in err
    assert "Traceback" not in err


def test_debug_shows_traceback(capsys):
    assert run_cli(_crash, ["--debug"]) == EXIT_INTERNAL
    assert "Traceback" in capsys.readouterr().err


def test_return_value_passed_through():
    assert run_cli(lambda argv: 0, []) == 0
    assert run_cli(lambda argv: None, []) == 0
    assert run_cli(lambda argv: 3, []) == 3


def test_argv_passed_unchanged():
    seen = []
    run_cli(lambda argv: seen.extend(argv), ["a", "--debug"])
    assert seen == ["a", "--debug"]


def test_parser_bad_args_is_user_error(capsys):
    def main(argv):
        parser = make_parser("jv test")
        parser.add_argument("--out", required=True)
        parser.parse_args(argv)
        return 0

    assert run_cli(main, []) == EXIT_USER
    assert "Ugyldige argumenter" in capsys.readouterr().err


def test_parser_help_exits_0(capsys):
    def main(argv):
        make_parser("jv test").parse_args(argv)

    assert run_cli(main, ["--help"]) == 0


def test_parser_has_debug():
    args = make_parser("jv test").parse_args(["--debug"])
    assert args.debug is True


def _parse(argv, setup):
    def main(args):
        parser = make_parser("jv test")
        setup(parser)
        parser.parse_args(args)
        return 0

    return run_cli(main, argv)


def test_parser_missing_required_in_norwegian(capsys):
    code = _parse([], lambda p: (p.add_argument("inn"), p.add_argument("--out", required=True)))
    err = capsys.readouterr().err
    assert code == EXIT_USER
    assert "disse argumentene mangler: inn, --out" in err
    assert "the following" not in err


def test_parser_unrecognized_in_norwegian(capsys):
    assert _parse(["--tull"], lambda p: None) == EXIT_USER
    err = capsys.readouterr().err
    assert "ukjente argumenter: --tull" in err and "unrecognized" not in err


def test_parser_invalid_float_in_norwegian(capsys):
    assert _parse(["--gap", "x"], lambda p: p.add_argument("--gap", type=float)) == EXIT_USER
    err = capsys.readouterr().err
    assert "argumentet --gap: 'x' er ikke et tall" in err and "invalid" not in err


def test_parser_invalid_choice_and_missing_value_in_norwegian(capsys):
    assert _parse(["--fmt", "doc"], lambda p: p.add_argument("--fmt", choices=["srt", "vtt"])) == EXIT_USER
    err = capsys.readouterr().err
    assert "ugyldig valg 'doc' (velg mellom " in err and "choose" not in err
    assert _parse(["--out"], lambda p: p.add_argument("--out")) == EXIT_USER
    assert "argumentet --out trenger én verdi" in capsys.readouterr().err


def test_translate_unknown_message_unchanged():
    from jv_common.errors import translate_argparse_message

    assert translate_argparse_message("noe helt annet") == "noe helt annet"


def test_permission_error_is_user_error(capsys):
    def main(argv):
        raise PermissionError(13, "Permission denied", "/ut/fil.pdf")

    assert run_cli(main, []) == EXIT_USER
    err = capsys.readouterr().err
    assert "Feil:" in err and "«/ut/fil.pdf»" in err and "skrivetilgang" in err
    assert "Intern feil" not in err and "Traceback" not in err


def test_readonly_and_full_disk_are_user_errors(capsys):
    import errno

    for code in (errno.EROFS, errno.ENOSPC):
        def main(argv, code=code):
            raise OSError(code, "nei", "/ut")

        assert run_cli(main, []) == EXIT_USER
        assert "Intern feil" not in capsys.readouterr().err


def test_other_os_error_is_still_internal(capsys):
    import errno

    def main(argv):
        raise OSError(errno.EIO, "I/O error")

    assert run_cli(main, []) == EXIT_INTERNAL
    assert "Intern feil" in capsys.readouterr().err


def test_write_to_readonly_out_dir_gives_code_1(tmp_path, capsys):
    import os

    from jv_common import safe_output_path

    if os.geteuid() == 0:
        pytest.skip("root har skrivetilgang overalt – testen hoppes over")
    src = tmp_path / "inn.txt"
    src.write_text("x")
    out = tmp_path / "laast"
    out.mkdir()
    out.chmod(0o500)
    try:
        def main(argv):
            safe_output_path(src, out, ".srt").write_text("y")

        assert run_cli(main, []) == EXIT_USER
        err = capsys.readouterr().err
        assert "skrivetilgang" in err and "Intern feil" not in err

        def main_raw(argv):
            (out / "direkte.txt").write_text("y")

        assert run_cli(main_raw, []) == EXIT_USER
        assert "Intern feil" not in capsys.readouterr().err
    finally:
        out.chmod(0o700)
