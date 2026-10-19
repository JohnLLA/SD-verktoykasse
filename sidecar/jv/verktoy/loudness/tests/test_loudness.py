"""Tests for jv loudness. Uses testdata/loudness/ and writes to tmp_path."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from jv_common import UserError, sha256_file, skip_if_missing
from jv_loudness import cli, core

pytestmark = [skip_if_missing("ffmpeg"), skip_if_missing("ffprobe")]

DATA = Path(__file__).resolve().parents[3] / "testdata" / "loudness"
LAV = DATA / "lav.wav"
HOY = DATA / "høy.wav"
VIDEO = DATA / "video_med_lyd.mp4"


def run_cli(argv, capsys):
    code = cli.main([str(a) for a in argv])
    captured = capsys.readouterr()
    report = json.loads(captured.out) if code == 0 else None
    return code, report, captured.err


def ffprobe_streams(path: Path) -> list[dict]:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=False, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)["streams"]


def video_md5(path: Path) -> str:
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy",
         "-f", "md5", "-"],
        check=False, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


def make_audio(src: Path, dst: Path, *args: str) -> Path:
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-n", "-i", str(src), *args, str(dst)],
        check=False, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    return dst


# ------------------------------------------------------------ acceptance


@pytest.mark.parametrize("target,lufs", [("podcast", -16.0), ("broadcast", -23.0)])
@pytest.mark.parametrize("src", [LAV, HOY], ids=["lav", "høy"])
def test_wav_reaches_target(src, target, lufs, tmp_path, capsys):
    before = sha256_file(src)
    code, report, err = run_cli([src, "--out", tmp_path, "--target", target], capsys)
    assert code == 0, err
    assert sha256_file(src) == before
    (out,) = report["outputs"]
    out_path = Path(out["path"])
    assert out_path.suffix == ".wav" and out_path.parent == tmp_path
    # independent check of the written file
    measured = core.measure(out_path)
    assert abs(measured.integrated_lufs - lufs) <= 0.5
    assert measured.true_peak_dbtp < -1.0
    assert out["within_target"] is True
    assert report["warnings"] == []
    stream = ffprobe_streams(out_path)[0]
    assert stream["codec_name"] == "pcm_s16le"
    assert stream["sample_rate"] == "48000"
    assert stream["channels"] == 1


def test_report_has_before_and_after(tmp_path, capsys):
    code, report, _ = run_cli([LAV, "--out", tmp_path], capsys)
    assert code == 0
    assert report["tool"] == "loudness"
    assert report["inputs"][0]["sha256"] == sha256_file(LAV)
    out = report["outputs"][0]
    assert out["before"]["integrated_lufs"] == pytest.approx(-30.0, abs=0.3)
    assert out["before"]["true_peak_dbtp"] == pytest.approx(-16.3, abs=0.3)
    assert out["after"]["integrated_lufs"] == pytest.approx(-16.0, abs=0.5)
    assert out["target"] == {"integrated_lufs": -16.0, "true_peak_dbtp": -1.0}
    assert "LUFS" in report["summary"] and "podcast" in report["summary"]


def test_custom_lufs(tmp_path, capsys):
    code, report, _ = run_cli([HOY, "--out", tmp_path, "--lufs", "-19"], capsys)
    assert code == 0
    out = report["outputs"][0]
    assert out["target"]["integrated_lufs"] == -19.0
    assert abs(core.measure(Path(out["path"])).integrated_lufs + 19) <= 0.5


def test_video_stream_copied(tmp_path, capsys):
    before = sha256_file(VIDEO)
    code, report, err = run_cli([VIDEO, "--out", tmp_path], capsys)
    assert code == 0, err
    assert sha256_file(VIDEO) == before
    out = report["outputs"][0]
    out_path = Path(out["path"])
    assert out_path.suffix == ".mp4"
    assert out["video"] == "kopiert uten omkoding"
    assert video_md5(out_path) == video_md5(VIDEO)
    streams = {s["codec_type"]: s for s in ffprobe_streams(out_path)}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    assert streams["audio"]["sample_rate"] == "48000"
    assert streams["audio"]["channels"] == 2
    assert abs(core.measure(out_path).integrated_lufs + 16) <= 0.5


@pytest.mark.parametrize(
    "name,args,codec",
    [
        ("tale.mp3", ["-c:a", "libmp3lame", "-b:a", "128k"], "mp3"),
        ("tale.m4a", ["-c:a", "aac", "-b:a", "96k"], "aac"),
        ("tale.flac", ["-c:a", "flac"], "flac"),
    ],
)
def test_other_audio_formats_keep_format(name, args, codec, tmp_path, capsys):
    src = make_audio(LAV, tmp_path / name, *args)
    code, report, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    assert code == 0, err
    out = report["outputs"][0]
    out_path = Path(out["path"])
    assert out_path.suffix == src.suffix
    stream = ffprobe_streams(out_path)[0]
    assert stream["codec_name"] == codec
    assert stream["sample_rate"] == "48000"
    if codec in ("mp3", "aac"):
        assert out["bitrate_kbps"] == 128
    assert abs(core.measure(out_path).integrated_lufs + 16) <= 0.5


def test_sample_rate_preserved_44k(tmp_path, capsys):
    src = make_audio(LAV, tmp_path / "tale44.wav", "-ar", "44100", "-c:a", "pcm_s24le")
    code, report, _ = run_cli([src, "--out", tmp_path / "ut"], capsys)
    assert code == 0
    stream = ffprobe_streams(Path(report["outputs"][0]["path"]))[0]
    assert stream["sample_rate"] == "44100"
    assert stream["codec_name"] == "pcm_s24le"


def test_awkward_file_names(tmp_path, capsys):
    odd_dir = tmp_path / "mappe med æøå; og mer"
    odd_dir.mkdir()
    src = odd_dir / "Intervju – Åse; Ødegård (råopptak).wav"
    shutil.copyfile(LAV, src)
    before = sha256_file(src)
    out_dir = tmp_path / "ut mappe ÆØÅ"
    code, report, err = run_cli([src, "--out", out_dir], capsys)
    assert code == 0, err
    out_path = Path(report["outputs"][0]["path"])
    assert out_path.exists()
    assert out_path.name == "Intervju – Åse; Ødegård (råopptak)-normalisert.wav"
    assert sha256_file(src) == before


@pytest.mark.parametrize("name", ["opptak:1.wav", "http:eksempel.wav"])
def test_relative_path_with_colon(name, tmp_path, capsys, monkeypatch):
    """Relative names with a colon must be read as local files, never as
    protocols (no "Protocol not found", no network attempt)."""
    monkeypatch.chdir(tmp_path)
    shutil.copyfile(LAV, tmp_path / name)
    before = sha256_file(tmp_path / name)
    code, report, err = run_cli([name, "--out", "ut:mappe"], capsys)
    assert code == 0, err
    out_path = Path(report["outputs"][0]["path"])
    assert out_path.resolve().parent == (tmp_path / "ut:mappe").resolve()
    assert out_path.exists()
    assert abs(core.measure(out_path).integrated_lufs + 16) <= 0.5
    assert sha256_file(tmp_path / name) == before


def test_http_name_is_not_fetched(tmp_path, capsys, monkeypatch):
    """A relative path "http:/..." that does not exist locally gives a
    Norwegian "finnes ikke" error, not a network call."""
    monkeypatch.chdir(tmp_path)
    code, _, err = run_cli(["http://127.0.0.1:9/lyd.wav", "--out", "ut"], capsys)
    _assert_user_error(code, err)
    assert "finnes ikke" in err


def test_ffmpeg_gets_file_urls(tmp_path, monkeypatch):
    calls = []
    real_run = core._run

    def spy(cmd):
        calls.append(cmd)
        return real_run(cmd)

    monkeypatch.setattr(core, "_run", spy)
    monkeypatch.chdir(tmp_path)
    shutil.copyfile(LAV, tmp_path / "http:lyd.wav")
    core.normalize("http:lyd.wav", "ut", -16.0)
    assert calls
    for cmd in calls:
        i = cmd.index("-i")
        assert cmd[i - 2:i] == ["-protocol_whitelist", "file"]
        assert cmd[i + 1].startswith("file:/")
        if cmd[-1] != "-":
            assert cmd[-1].startswith("file:/")


def test_never_overwrites(tmp_path, capsys):
    src = tmp_path / "lyd.wav"
    shutil.copyfile(LAV, src)
    existing = tmp_path / "lyd-normalisert.wav"
    existing.write_bytes(b"ikke rett")
    code, report, _ = run_cli([src, "--out", tmp_path], capsys)
    assert code == 0
    assert existing.read_bytes() == b"ikke rett"
    assert Path(report["outputs"][0]["path"]).name == "lyd-normalisert-2.wav"


def test_progress_on_stderr(tmp_path, capsys):
    code, _, err = run_cli([LAV, "--out", tmp_path], capsys)
    assert code == 0
    lines = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
    assert lines[0] == {"progress": 0.0}
    assert lines[-1] == {"progress": 1.0}


# ------------------------------------------------------------ user errors


def _assert_user_error(code, err):
    assert code == 1
    messages = [line for line in err.splitlines() if not line.startswith("{")]
    assert messages and messages[0].startswith("Feil:")
    assert "Traceback" not in err


def test_missing_file(tmp_path, capsys):
    code, _, err = run_cli([tmp_path / "finnes_ikke.wav", "--out", tmp_path], capsys)
    _assert_user_error(code, err)
    assert "finnes ikke" in err


def test_empty_file(tmp_path, capsys):
    src = tmp_path / "tom.wav"
    src.write_bytes(b"")
    code, _, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err)
    assert "tom" in err


def test_wrong_format(tmp_path, capsys):
    src = tmp_path / "notat.txt"
    src.write_text("hei", encoding="utf-8")
    code, _, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err)
    assert "støttes ikke" in err


def test_garbage_with_audio_extension(tmp_path, capsys):
    src = tmp_path / "skadet.mp3"
    src.write_bytes(b"dette er ikke lyd" * 100)
    code, _, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err)
    assert not (tmp_path / "ut" / "skadet-normalisert.mp3").exists()


def test_silent_file(tmp_path, capsys):
    src = tmp_path / "stille.wav"
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", "5", str(src)],
        check=False, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    code, _, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err)
    assert "stille" in err
    out_dir = tmp_path / "ut"
    assert not out_dir.exists() or not list(out_dir.iterdir())


def test_video_without_audio(tmp_path, capsys):
    src = tmp_path / "stumt.mp4"
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
         "-c:v", "mpeg4", str(src)],
        check=False, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    code, _, err = run_cli([src, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err)
    assert "lydspor" in err


@pytest.mark.parametrize("value", ["-3", "-80", "abc"])
def test_bad_lufs(value, tmp_path, capsys):
    code, _, err = run_cli([LAV, "--out", tmp_path, "--lufs", value], capsys)
    _assert_user_error(code, err)


def test_target_and_lufs_exclusive(tmp_path, capsys):
    code, _, err = run_cli(
        [LAV, "--out", tmp_path, "--target", "podcast", "--lufs", "-18"], capsys
    )
    _assert_user_error(code, err)


def test_unknown_target(tmp_path, capsys):
    code, _, err = run_cli([LAV, "--out", tmp_path, "--target", "radio"], capsys)
    _assert_user_error(code, err)
    with pytest.raises(UserError):
        core.resolve_target("radio", None)


def test_bad_input_writes_nothing_for_others(tmp_path, capsys):
    out_dir = tmp_path / "ut"
    code, _, err = run_cli([LAV, tmp_path / "mangler.wav", "--out", out_dir], capsys)
    _assert_user_error(code, err)
    assert not out_dir.exists() or not list(out_dir.iterdir())


# ------------------------------------------------------------ parsing


EBUR128_44 = """
[Parsed_ebur128_0 @ 0x1] t: 9.9  TARGET:-23 LUFS  M: -20.1 S: -20.2  I: -20.2 LUFS  LRA: 0.1 LU  FTPK: -9.4 dBFS  TPK: -9.3 dBFS
[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -20.2 LUFS
    Threshold: -30.2 LUFS

  Loudness range:
    LRA:         0.1 LU
    Threshold: -40.2 LUFS
    LRA low:   -20.2 LUFS
    LRA high:  -20.1 LUFS

  True peak:
    Peak:       -9.3 dBFS
"""

# newer ffmpeg (6/7) with peak=sample+true prints a sample peak block too
EBUR128_7 = """
[Parsed_ebur128_0 @ 0x600] Summary:

  Integrated loudness:
    I:         -16.0 LUFS
    Threshold: -26.0 LUFS

  Loudness range:
    LRA:         0.2 LU
    Threshold: -36.1 LUFS
    LRA low:   -16.1 LUFS
    LRA high:  -15.9 LUFS

  Sample peak:
    Peak:       -3.0 dBFS

  True peak:
    Peak:       -2.2 dBFS
[out#0/null @ 0x601] video:0KiB audio:3750KiB subtitle:0KiB other streams:0KiB
"""

LOUDNORM = """
[Parsed_loudnorm_1 @ 0xbe] \n{
\t"input_i" : "-8.26",
\t"input_tp" : "-0.77",
\t"input_lra" : "0.20",
\t"input_thresh" : "-18.26",
\t"output_i" : "-16.01",
\t"output_tp" : "-8.55",
\t"output_lra" : "0.10",
\t"output_thresh" : "-26.01",
\t"normalization_type" : "linear",
\t"target_offset" : "0.01"
}
[out#0/null @ 0x1] size=N/A
"""


def test_parse_ebur128_44():
    m = core.parse_ebur128(EBUR128_44)
    assert (m.integrated_lufs, m.true_peak_dbtp) == (-20.2, -9.3)


def test_parse_ebur128_newer_with_sample_peak():
    m = core.parse_ebur128(EBUR128_7)
    assert (m.integrated_lufs, m.true_peak_dbtp) == (-16.0, -2.2)


def test_parse_ebur128_silence():
    text = EBUR128_44.replace("-20.2 LUFS\n    Threshold: -30.2", "-70.0 LUFS\n    Threshold: -70.0")
    text = text.replace("Peak:       -9.3", "Peak:       -inf")
    m = core.parse_ebur128(text)
    assert m.integrated_lufs == -70.0
    assert m.as_dict()["true_peak_dbtp"] is None


def test_parse_loudnorm():
    stats = core.parse_loudnorm(LOUDNORM)
    assert stats["input_i"] == -8.26
    assert stats["target_offset"] == 0.01
    assert stats["normalization_type"] == "linear"


def test_parse_loudnorm_inf_values():
    text = LOUDNORM.replace('"-8.26"', '"-inf"').replace('"-0.77"', '"-inf"')
    stats = core.parse_loudnorm(text)
    assert stats["input_i"] == float("-inf")


def test_parse_missing_output():
    with pytest.raises(ValueError):
        core.parse_ebur128("ingenting her")
    with pytest.raises(ValueError):
        core.parse_loudnorm("ingenting her")


def test_bitrate_choice():
    assert core._lossy_bitrate({"bit_rate": "96316"}, {}) == 128
    assert core._lossy_bitrate({"bit_rate": "128000"}, {}) == 128
    assert core._lossy_bitrate({"bit_rate": "200000"}, {}) == 224
    assert core._lossy_bitrate({"bit_rate": "500000"}, {}) == 320
    assert core._lossy_bitrate({}, {"format": {"bit_rate": "160000"}}) == 160
    assert core._lossy_bitrate({}, {}) == 192
