import pytest
from jv_common import UserError

from jv_keyframes import core


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("2s", 2.0), ("2", 2.0), ("0.5s", 0.5), ("0,5s", 0.5), (" 10 s ", 10.0), ("3sek", 3.0)],
)
def test_parse_interval(text, seconds):
    assert core.parse_interval(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "-2s", "0s", "2m", "2 minutter"])
def test_parse_interval_invalid(text):
    with pytest.raises(UserError):
        core.parse_interval(text)


def test_parse_threshold():
    assert core.parse_threshold("0.3") == 0.3
    assert core.parse_threshold("0,4") == 0.4
    for bad in ["0", "1", "1.5", "x", "-0.1"]:
        with pytest.raises(UserError):
            core.parse_threshold(bad)


def test_names_and_timecodes():
    assert core.frame_filename(12.48) == "000012.480.jpg"
    assert core.frame_filename(0) == "000000.000.jpg"
    assert core.frame_filename(3725.0004) == "003725.000.jpg"
    assert core.format_timecode(3725.5) == "01:02:05.500"


def test_rotation_ffmpeg_44_tag():
    stream = {"tags": {"rotate": "90"}, "side_data_list": [{"rotation": -90}]}
    assert core._rotation(stream) == 90


def test_rotation_newer_ffmpeg_display_matrix_only():
    # ffmpeg 5+ dropped the "rotate" tag; only the display matrix remains,
    # with counter-clockwise sign.
    assert core._rotation({"side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]}) == 90
    assert core._rotation({"side_data_list": [{"rotation": 90}]}) == 270
    assert core._rotation({"side_data_list": [{"rotation": 180}]}) == 180
    assert core._rotation({}) == 0


def test_interval_times_stays_inside_video():
    assert core.interval_times(10.0, 2.0, 25.0) == [0, 2, 4, 6, 8]
    assert core.interval_times(4.0, 1.5, 25.0) == [0, 1.5, 3.0]
    assert core.interval_times(0.5, 2.0, 25.0) == [0]
