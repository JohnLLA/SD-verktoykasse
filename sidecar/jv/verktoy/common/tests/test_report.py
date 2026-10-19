import hashlib
import io
import json

from jv_common import build_report, print_report, sha256_file


def test_sha256_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"hei verden")
    assert sha256_file(f) == hashlib.sha256(b"hei verden").hexdigest()


def test_build_report_shape(tmp_path):
    f = tmp_path / "inn.txt"
    f.write_text("æøå", encoding="utf-8")
    out = tmp_path / "ut" / "inn.srt"
    report = build_report(
        tool="subtitles",
        version="0.1.0",
        inputs=[f],
        outputs=[out, {"path": "x.vtt", "type": "vtt"}],
        warnings=["en advarsel"],
        summary="Laget to filer.",
    )
    assert list(report) == ["tool", "version", "inputs", "outputs", "warnings", "summary"]
    assert report["inputs"] == [
        {"path": str(f), "sha256": hashlib.sha256("æøå".encode()).hexdigest()}
    ]
    assert report["outputs"] == [str(out), {"path": "x.vtt", "type": "vtt"}]
    assert report["warnings"] == ["en advarsel"]
    json.dumps(report)  # serialisable


def test_build_report_defaults(tmp_path):
    report = build_report("x", "1", [], summary="s")
    assert report["outputs"] == [] and report["warnings"] == []


def test_print_report_utf8():
    buf = io.StringIO()
    print_report({"summary": "Ferdig på nynorsk"}, file=buf)
    assert "Ferdig på nynorsk" in buf.getvalue()
    assert json.loads(buf.getvalue()) == {"summary": "Ferdig på nynorsk"}
