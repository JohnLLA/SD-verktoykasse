import json

from jv_common import emit


def test_emit_one_json_line_on_stderr(capsys):
    emit(0.42)
    emit(2)
    emit(-1)
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert [json.loads(line) for line in lines] == [
        {"progress": 0.42},
        {"progress": 1.0},
        {"progress": 0.0},
    ]
