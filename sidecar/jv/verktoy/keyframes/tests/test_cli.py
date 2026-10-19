import json
import shutil
from pathlib import Path

import pytest
from jv_common import sha256_file, skip_if_missing
from PIL import Image

from jv_keyframes.cli import main

pytestmark = [skip_if_missing("ffmpeg"), skip_if_missing("ffprobe")]

DATA = Path(__file__).resolve().parents[3] / "testdata" / "keyframes"
CLIP = DATA / "klipp.mp4"
PORTRAIT = DATA / "stående.mov"
CUTS = [2.0, 5.0, 8.0]


def run(capsys, *args):
    code = main([str(a) for a in args])
    captured = capsys.readouterr()
    return code, captured


def run_ok(capsys, *args):
    code, captured = run(capsys, *args)
    assert code == 0, captured.err
    return json.loads(captured.out)


def frames(report):
    return [o for o in report["outputs"] if o["type"] == "bilde"]


def sheets(report):
    return [o for o in report["outputs"] if o["type"] == "kontaktark"]


def center_rgb(path):
    with Image.open(path) as im:
        return im.convert("RGB").getpixel((im.width // 2, im.height // 2))


def test_scene_cuts_within_tolerance(tmp_path, capsys):
    report = run_ok(capsys, CLIP, "--out", tmp_path, "--scenes", "0.3")
    times = [f["time"] for f in frames(report)]
    for cut in CUTS:
        assert any(abs(t - cut) <= 0.2 for t in times), (cut, times)
    # every frame is either the opening frame or one of the known cuts
    assert all(t == 0 or any(abs(t - c) <= 0.2 for c in CUTS) for t in times)
    assert len(times) == 4

    # the frame at each cut shows the new shot (after the cut, not before)
    by_time = {round(f["time"]): Path(f["path"]) for f in frames(report)}
    assert min(center_rgb(by_time[2])) > 200  # white
    r, g, b = center_rgb(by_time[5])
    assert b > 200 and r < 60 and g < 60  # blue
    r, g, b = center_rgb(by_time[8])
    assert r > 200 and g > 200 and b < 60  # yellow


def test_filenames_carry_timecode(tmp_path, capsys):
    report = run_ok(capsys, CLIP, "--out", tmp_path, "--scenes", "0.3")
    names = sorted(Path(f["path"]).name for f in frames(report))
    assert names == ["000000.000.jpg", "000002.000.jpg", "000005.000.jpg", "000008.000.jpg"]
    for f in frames(report):
        assert Path(f["path"]).is_file()
        with Image.open(f["path"]) as im:
            assert im.format == "JPEG"


def test_every_interval(tmp_path, capsys):
    report = run_ok(capsys, CLIP, "--out", tmp_path, "--every", "2s")
    assert [f["time"] for f in frames(report)] == [0, 2, 4, 6, 8]
    assert report["warnings"] == []


def test_contact_sheet(tmp_path, capsys):
    report = run_ok(capsys, CLIP, "--out", tmp_path, "--every", "2s")
    (sheet,) = sheets(report)
    path = Path(sheet["path"])
    assert path.name == "klipp-kontaktark.jpg"
    assert sheet["frames"] == 5
    with Image.open(path) as im:
        assert im.format == "JPEG"
        # five thumbnails of 240 px plus padding side by side
        assert im.width >= 5 * 240
        # the timecode labels are drawn in white below the thumbnails
        label_band = im.convert("L").crop((0, im.height - 24, im.width, im.height))
        assert label_band.getextrema()[1] > 200


def test_report_documents_video(tmp_path, capsys):
    report = run_ok(capsys, CLIP, "--out", tmp_path, "--every", "5s")
    assert report["tool"] == "keyframes"
    assert set(report) >= {"tool", "version", "inputs", "outputs", "warnings", "summary"}
    assert report["inputs"][0]["sha256"] == sha256_file(CLIP)
    (video,) = report["videos"]
    assert video["duration"] == pytest.approx(10.0, abs=0.05)
    assert (video["width"], video["height"]) == (320, 240)
    assert video["fps"] == pytest.approx(25.0)
    assert video["rotation"] == 0
    assert "bilder" in report["summary"]


def test_rotated_video_gives_portrait_frames(tmp_path, capsys):
    report = run_ok(capsys, PORTRAIT, "--out", tmp_path, "--every", "1s")
    (video,) = report["videos"]
    assert video["rotation"] == 90
    assert (video["width"], video["height"]) == (180, 320)
    assert (video["stored_width"], video["stored_height"]) == (320, 180)
    assert len(frames(report)) == 4
    for f in frames(report):
        with Image.open(f["path"]) as im:
            assert im.size == (180, 320)
    # four portrait thumbnails side by side: each cell is taller than wide
    with Image.open(sheets(report)[0]["path"]) as im:
        assert im.width < 4 * 240


def test_rotated_video_scene_mode(tmp_path, capsys):
    report = run_ok(capsys, PORTRAIT, "--out", tmp_path, "--scenes", "0.3")
    for f in frames(report):
        with Image.open(f["path"]) as im:
            assert im.height > im.width


def test_odd_filename_and_original_untouched(tmp_path, capsys):
    odd = tmp_path / "inn mappe; æøå" / "Klipp fra møtet; del 1 (å).mp4"
    odd.parent.mkdir()
    shutil.copy(CLIP, odd)
    before = sha256_file(odd)
    # --out is the same folder as the input
    report = run_ok(capsys, odd, "--out", odd.parent, "--scenes", "0.3")
    assert sha256_file(odd) == before
    assert report["inputs"][0]["sha256"] == before
    assert len(frames(report)) == 4
    assert Path(sheets(report)[0]["path"]).name == "Klipp fra møtet; del 1 (å)-kontaktark.jpg"
    assert sorted(p.name for p in odd.parent.iterdir()) == sorted(
        [odd.name, "Klipp fra møtet; del 1 (å)-bilder", "Klipp fra møtet; del 1 (å)-kontaktark.jpg"]
    )


def test_second_run_does_not_overwrite(tmp_path, capsys):
    first = run_ok(capsys, CLIP, "--out", tmp_path, "--every", "5s")
    second = run_ok(capsys, CLIP, "--out", tmp_path, "--every", "5s")
    assert Path(sheets(first)[0]["path"]).name == "klipp-kontaktark.jpg"
    assert Path(sheets(second)[0]["path"]).name == "klipp-kontaktark-2.jpg"
    assert Path(frames(second)[0]["path"]).parent.name == "klipp-bilder-2"
    assert Path(frames(first)[0]["path"]).is_file()


def test_several_inputs(tmp_path, capsys):
    report = run_ok(capsys, CLIP, PORTRAIT, "--out", tmp_path, "--every", "2s")
    assert [i["sha256"] for i in report["inputs"]] == [sha256_file(CLIP), sha256_file(PORTRAIT)]
    assert len(sheets(report)) == 2
    assert len(report["videos"]) == 2


def test_progress_on_stderr(tmp_path, capsys):
    code, captured = run(capsys, CLIP, "--out", tmp_path, "--scenes", "0.3")
    assert code == 0
    lines = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    assert lines and all("progress" in line for line in lines)
    assert lines[-1]["progress"] == 1.0


def _assert_user_error(code, captured, *words):
    assert code == 1
    messages = [line for line in captured.err.splitlines() if not line.startswith('{"progress"')]
    assert messages and messages[0].startswith("Feil:")
    assert "Traceback" not in captured.err
    assert captured.out == ""
    for word in words:
        assert word in captured.err


def test_missing_file(tmp_path, capsys):
    code, captured = run(capsys, tmp_path / "finnes_ikke.mp4", "--out", tmp_path, "--every", "2s")
    _assert_user_error(code, captured, "Finner ikke")


def test_empty_file(tmp_path, capsys):
    empty = tmp_path / "tom.mp4"
    empty.write_bytes(b"")
    code, captured = run(capsys, empty, "--out", tmp_path / "ut", "--every", "2s")
    _assert_user_error(code, captured, "tom")


def test_wrong_format(tmp_path, capsys):
    text = tmp_path / "notat.mp4"
    text.write_text("Dette er ikke en video.\n" * 20, encoding="utf-8")
    code, captured = run(capsys, text, "--out", tmp_path / "ut", "--every", "2s")
    _assert_user_error(code, captured)
    assert not (tmp_path / "ut").exists() or not any((tmp_path / "ut").iterdir())


def test_bad_options(tmp_path, capsys):
    code, captured = run(capsys, CLIP, "--out", tmp_path, "--every", "to sekunder")
    _assert_user_error(code, captured, "intervall")
    code, captured = run(capsys, CLIP, "--out", tmp_path, "--scenes", "3")
    _assert_user_error(code, captured, "mellom 0 og 1")
    code, captured = run(capsys, CLIP, "--out", tmp_path)
    _assert_user_error(code, captured)
    code, captured = run(capsys, CLIP, "--out", tmp_path, "--every", "2s", "--scenes", "0.3")
    _assert_user_error(code, captured)


# ---------------------------------------------------------------- URL-like names


class _Listener:
    """Local TCP listener that records any connection attempt.

    bind/listen/accept are not blocked by the root conftest (only connect and
    DNS are), and ffmpeg runs as a separate process outside the block anyway,
    so a connection from ffmpeg would be seen here.
    """

    def __init__(self):
        import socket
        import threading

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.connections = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        import socket

        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            self.connections += 1
            conn.close()

    def close(self):
        self._stop.set()
        self._thread.join(2)
        self.sock.close()


@pytest.fixture
def listener():
    lst = _Listener()
    yield lst
    lst.close()


@pytest.mark.parametrize("mode", [("--every", "2s"), ("--scenes", "0.3")])
def test_http_like_relative_path_is_read_as_local_file(tmp_path, monkeypatch, capsys, listener, mode):
    # "http://127.0.0.1:<port>/klipp.mp4" is also a valid relative path:
    # the folder "http:" / "127.0.0.1:<port>" / "klipp.mp4".
    local = tmp_path / "http:" / f"127.0.0.1:{listener.port}" / "klipp.mp4"
    local.parent.mkdir(parents=True)
    shutil.copy(CLIP, local)
    monkeypatch.chdir(tmp_path)
    url_like = f"http://127.0.0.1:{listener.port}/klipp.mp4"

    report = run_ok(capsys, url_like, "--out", tmp_path / "ut", *mode)

    assert listener.connections == 0
    assert report["inputs"][0]["sha256"] == sha256_file(local)
    assert report["videos"][0]["duration"] == pytest.approx(10.0, abs=0.05)
    assert len(frames(report)) in (4, 5)


def test_name_starting_with_http_colon(tmp_path, monkeypatch, capsys, listener):
    name = f"http:127.0.0.1:{listener.port}.mp4"
    shutil.copy(CLIP, tmp_path / name)
    monkeypatch.chdir(tmp_path)
    report = run_ok(capsys, name, "--out", "ut", "--scenes", "0.3")
    assert listener.connections == 0
    assert [round(f["time"]) for f in frames(report)] == [0, 2, 5, 8]


@pytest.mark.parametrize("name", ["opptak:1.mp4", "tcp:opptak.mp4", "concat:a.mp4", "pipe:0", "-i.mp4"])
def test_colon_and_dash_names(tmp_path, monkeypatch, capsys, name):
    shutil.copy(CLIP, tmp_path / name)
    monkeypatch.chdir(tmp_path)
    # "--" ends the options, so even a name starting with "-" is a file
    report = run_ok(capsys, "--out", "ut", "--every", "5s", "--", name)
    assert report["inputs"][0]["sha256"] == sha256_file(CLIP)
    assert [f["time"] for f in frames(report)] == [0, 5]
    for f in frames(report):
        assert Path(f["path"]).is_file()


def test_ffmpeg_arguments_are_local_only(tmp_path, monkeypatch):
    import subprocess

    from jv_keyframes import core

    calls = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def spy_run(args, *a, **kw):
        calls.append(list(args))
        return real_run(args, *a, **kw)

    class SpyPopen(real_popen):
        def __init__(self, args, *a, **kw):
            calls.append(list(args))
            super().__init__(args, *a, **kw)

    monkeypatch.setattr(core.subprocess, "run", spy_run)
    monkeypatch.setattr(core.subprocess, "Popen", SpyPopen)
    src = tmp_path / "opptak:1.mp4"
    shutil.copy(CLIP, src)
    core.extract(src, tmp_path / "ut", scenes=0.3)

    assert calls
    for args in calls:
        i = args.index("-protocol_whitelist")
        assert args[i + 1] == "file"
        file_args = [a for a in args if a.startswith("file:")]
        assert file_args == ["file:" + str(src.resolve())]
        assert args[args.index(file_args[0]) - 1] == "-i"
        assert args.index("-protocol_whitelist") < args.index("-i")
        assert not any(a.startswith(("http", "tcp", "udp", "rtmp")) for a in args)


def test_no_empty_frames_folder_on_failure(tmp_path, monkeypatch, capsys):
    from jv_keyframes import core

    monkeypatch.setattr(core, "extract_frame", lambda *a, **kw: None)
    out = tmp_path / "ut"
    code, captured = run(capsys, CLIP, "--out", out, "--every", "2s")
    _assert_user_error(code, captured, "noen bilder")
    assert not (out / "klipp-bilder").exists()
    assert not out.exists() or list(out.iterdir()) == []
