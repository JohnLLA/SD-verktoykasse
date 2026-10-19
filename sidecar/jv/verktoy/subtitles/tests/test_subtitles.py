"""Tests for jv subtitles. Uses testdata/subtitles/ and writes to tmp_path."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from jv_common import sha256_file, skip_if_missing
from jv_subtitles import cli, core

DATA = Path(__file__).resolve().parents[3] / "testdata" / "subtitles"
WITH_WORDS = DATA / "transkripsjon.json"
NO_WORDS = DATA / "transkripsjon_uten_ord.json"
BOTH = [WITH_WORDS, NO_WORDS]

MAX_CHARS, MAX_LINES, MIN_MS, MAX_MS, GAP_MS = 42, 2, 1000, 7000, 80

TS = r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"


def _ms(h, m, s, ms) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def run(argv, capsys):
    code = cli.main([str(a) for a in argv])
    captured = capsys.readouterr()
    report = json.loads(captured.out) if code == 0 else None
    return code, report, captured.err


def convert(src: Path, out: Path, capsys, *extra):
    code, report, err = run([src, "--out", out, *extra], capsys)
    assert code == 0, err
    srt = next(Path(o["path"]) for o in report["outputs"] if o["format"] == "srt")
    vtt = next(Path(o["path"]) for o in report["outputs"] if o["format"] == "vtt")
    return report, srt, vtt


# ---------------------------------------------------------- strict parsers


def parse_srt(path: Path) -> list[tuple[int, int, list[str]]]:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "SRT har BOM"
    text = raw.decode("utf-8")
    assert "\n" not in text.replace("\r\n", ""), "SRT har linjeskift som ikke er CRLF"
    text = text.replace("\r\n", "\n")
    cues = []
    blocks = text.strip("\n").split("\n\n")
    for n, block in enumerate(blocks, start=1):
        lines = block.split("\n")
        assert lines[0] == str(n), f"feil nummer i blokk {n}: {lines[0]!r}"
        m = re.fullmatch(TS + " --> " + TS, lines[1])
        assert m and "," in lines[1], f"ugyldig tidskode: {lines[1]!r}"
        g = m.groups()
        cues.append((_ms(*g[:4]), _ms(*g[4:]), lines[2:]))
    return cues


def parse_vtt(path: Path) -> list[tuple[int, int, list[str]]]:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "VTT har BOM"
    text = raw.decode("utf-8")
    assert "\r" not in text
    assert text.startswith("WEBVTT\n\n")
    cues = []
    for block in text[len("WEBVTT\n\n"):].strip("\n").split("\n\n"):
        lines = block.split("\n")
        m = re.fullmatch(TS + " --> " + TS, lines[0])
        assert m and "." in lines[0], f"ugyldig tidskode: {lines[0]!r}"
        g = m.groups()
        cues.append((_ms(*g[:4]), _ms(*g[4:]), lines[1:]))
    return cues


def rule_violations(cues) -> list[str]:
    bad = []
    for i, (start, end, lines) in enumerate(cues):
        if not lines:
            bad.append(f"{i}: tom")
        if len(lines) > MAX_LINES:
            bad.append(f"{i}: {len(lines)} linjer")
        for line in lines:
            if len(line) > MAX_CHARS:
                bad.append(f"{i}: {len(line)} tegn: {line}")
            if line != line.strip() or not line:
                bad.append(f"{i}: mellomrom i kant/tom linje")
        if not MIN_MS <= end - start <= MAX_MS:
            bad.append(f"{i}: varighet {end - start} ms")
        if i + 1 < len(cues) and cues[i + 1][0] - end < GAP_MS:
            bad.append(f"{i}: mellomrom {cues[i + 1][0] - end} ms")
    return bad


def source_tokens(path: Path) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    tokens = []
    for seg in doc["segments"]:
        tokens.extend(unicodedata.normalize("NFC", seg["text"]).split())
    return tokens


def ffmpeg_reads(path: Path, codec: str) -> int:
    """ffprobe and ffmpeg read the file without error; returns packet count."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name",
         "-of", "json", str(path)],
        check=False, capture_output=True, text=True,
    )
    assert probe.returncode == 0 and probe.stderr == "", probe.stderr
    streams = json.loads(probe.stdout)["streams"]
    assert [s["codec_name"] for s in streams] == [codec]

    packets = subprocess.run(
        ["ffprobe", "-v", "error", "-show_packets", "-of", "json", str(path)],
        check=False, capture_output=True, text=True,
    )
    assert packets.returncode == 0 and packets.stderr == "", packets.stderr

    remux = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", "0:s:0",
         "-f", "srt", "-"],
        check=False, capture_output=True, text=True,
    )
    assert remux.returncode == 0 and remux.stderr == "", remux.stderr
    assert remux.stdout.count("-->") == len(json.loads(packets.stdout)["packets"])
    return len(json.loads(packets.stdout)["packets"])


# ------------------------------------------------------------ acceptance


@skip_if_missing("ffmpeg")
@skip_if_missing("ffprobe")
@pytest.mark.parametrize("src", BOTH, ids=["med_ord", "uten_ord"])
def test_ffmpeg_reads_srt_and_vtt(src, tmp_path, capsys):
    _, srt, vtt = convert(src, tmp_path, capsys)
    n_srt = ffmpeg_reads(srt, "subrip")
    n_vtt = ffmpeg_reads(vtt, "webvtt")
    assert n_srt == n_vtt == len(parse_srt(srt))


@pytest.mark.parametrize("src", BOTH, ids=["med_ord", "uten_ord"])
def test_every_cue_follows_the_rules(src, tmp_path, capsys):
    report, srt, vtt = convert(src, tmp_path, capsys)
    srt_cues = parse_srt(srt)
    vtt_cues = parse_vtt(vtt)
    assert rule_violations(srt_cues) == []
    assert rule_violations(vtt_cues) == []
    assert srt_cues == vtt_cues  # same content in both formats
    expected = 1 if src == NO_WORDS else 0  # only the "no word timestamps" note
    assert len(report["warnings"]) == expected, report["warnings"]
    assert "Alle tekstene følger reglene" in report["summary"]
    # The test segment covers the full 3 minutes.
    assert srt_cues[0][0] == 500
    assert srt_cues[-1][1] >= 180_010


@pytest.mark.parametrize("src", BOTH, ids=["med_ord", "uten_ord"])
def test_never_splits_inside_a_word(src, tmp_path, capsys):
    _, srt, _ = convert(src, tmp_path, capsys)
    out_tokens = [tok for _, _, lines in parse_srt(srt) for line in lines for tok in line.split()]
    assert out_tokens == source_tokens(src)


def test_long_segments_are_split(tmp_path, capsys):
    _, srt, _ = convert(WITH_WORDS, tmp_path, capsys)
    cues = parse_srt(srt)
    texts = [" ".join(lines) for _, _, lines in cues]
    # Segment 4 (13.63 s), 24 (10.16 s) and 44 (8.24 s) must span several cues.
    for first, last in [
        ("Kulturhuset har fått", "la oss begynne der."),
        ("Men kulturhuset er", "under samme tak."),
        ("Neste uke snakker", "forsinket hver fredag."),
    ]:
        i = next(k for k, t in enumerate(texts) if t.startswith(first))
        j = next(k for k, t in enumerate(texts) if t.endswith(last))
        assert j > i, (first, texts[i])
    # Prefer clause boundaries: segment 4 breaks after a comma.
    i = next(k for k, t in enumerate(texts) if t.startswith("Kulturhuset har fått"))
    assert texts[i].endswith(",")


def test_short_cues_are_extended(tmp_path, capsys):
    _, srt, _ = convert(WITH_WORDS, tmp_path, capsys)
    cues = parse_srt(srt)
    shorts = [c for c in cues if " ".join(c[2]) in ("Ja.", "Mm.", "Takk.", "Takk selv.")]
    assert len(shorts) == 4
    for start, end, _ in shorts:
        assert end - start >= MIN_MS
    takk = next(c for c in cues if c[2] == ["Takk."])
    assert takk[0] == 12_630  # starts when spoken


def test_word_timestamps_drive_the_split(tmp_path, capsys):
    _, srt_w, _ = convert(WITH_WORDS, tmp_path / "w", capsys)
    _, srt_c, _ = convert(NO_WORDS, tmp_path / "c", capsys)
    doc = json.loads(WITH_WORDS.read_text(encoding="utf-8"))
    word_starts = {round(w["start"] * 1000) for s in doc["segments"] for w in s["words"]}
    cues_w = parse_srt(srt_w)
    # A cue that starts mid-segment (after a split) starts at a word time
    # (or later, by the 80 ms gap rule only when touching the previous cue).
    seg_starts = {round(s["start"] * 1000) for s in doc["segments"]}
    mid = [c for c in cues_w if c[0] not in seg_starts]
    assert mid, "ingen delte segmenter"
    for start, _, _ in mid:
        assert start in word_starts or start - GAP_MS in {c[1] for c in cues_w}
    # Without words the time is spread by characters, so timings differ.
    assert [c[:2] for c in cues_w] != [c[:2] for c in parse_srt(srt_c)]


def test_no_words_gives_warning(tmp_path, capsys):
    report, _, _ = convert(NO_WORDS, tmp_path, capsys)
    assert any("ordtidskoder" in w for w in report["warnings"])
    assert "tegnfordeling" in report["summary"]


def test_report_contract(tmp_path, capsys):
    report, srt, vtt = convert(WITH_WORDS, tmp_path, capsys)
    assert set(report) == {"tool", "version", "inputs", "outputs", "warnings", "summary"}
    assert report["tool"] == "subtitles"
    assert report["inputs"][0]["sha256"] == sha256_file(WITH_WORDS)
    assert srt.suffix == ".srt" and vtt.suffix == ".vtt"
    assert srt.parent == tmp_path


def test_utf8_without_bom_keeps_norwegian_letters(tmp_path, capsys):
    _, srt, vtt = convert(WITH_WORDS, tmp_path, capsys)
    for path in (srt, vtt):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8")
        assert "Først og fremst" in text and "særlig" in text and "Døren står åpen." in text
    assert b"\r\n" in srt.read_bytes()
    assert vtt.read_bytes().startswith(b"WEBVTT\n")


def test_input_is_untouched(tmp_path, capsys):
    before = {p: sha256_file(p) for p in BOTH}
    for p in BOTH:
        convert(p, tmp_path, capsys)
    assert {p: sha256_file(p) for p in BOTH} == before


def test_filename_with_space_and_aeoeaa(tmp_path, capsys):
    src = tmp_path / "inn mappe" / "intervju æøå; del 1.json"
    src.parent.mkdir()
    shutil.copy(WITH_WORDS, src)
    before = sha256_file(src)
    _, srt, vtt = convert(src, tmp_path / "ut æ", capsys)
    assert srt.name == "intervju æøå; del 1.srt"
    assert vtt.name == "intervju æøå; del 1.vtt"
    assert sha256_file(src) == before


def test_output_in_same_folder_never_overwrites(tmp_path, capsys):
    src = tmp_path / "t.json"
    shutil.copy(WITH_WORDS, src)
    (tmp_path / "t.srt").write_text("finnes", encoding="utf-8")
    _, srt, vtt = convert(src, tmp_path, capsys)
    assert srt.name == "t-2.srt" and vtt.name == "t.vtt"
    assert (tmp_path / "t.srt").read_text(encoding="utf-8") == "finnes"


def test_rules_can_be_adjusted(tmp_path, capsys):
    _, srt, _ = convert(WITH_WORDS, tmp_path, capsys,
                        "--max-chars", "30", "--max-lines", "1", "--max-duration", "5")
    cues = parse_srt(srt)
    assert all(len(lines) == 1 and len(lines[0]) <= 30 for _, _, lines in cues)
    assert all(MIN_MS <= e - s <= 5000 for s, e, _ in cues)


def test_jv_dispatcher_finds_tool(tmp_path, capsys):
    from jv_common.cli import main as jv_main

    code = jv_main(["subtitles", str(WITH_WORDS), "--out", str(tmp_path)])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "subtitles"


# ---------------------------------------------------------------- errors


def _assert_user_error(code, err, needle):
    assert code == 1
    assert err.startswith("Feil: ")
    assert needle in err
    assert "Traceback" not in err


def test_missing_file(tmp_path, capsys):
    code, _, err = run([tmp_path / "finnes_ikke.json", "--out", tmp_path], capsys)
    _assert_user_error(code, err, "finnes ikke")


def test_empty_file(tmp_path, capsys):
    src = tmp_path / "tom.json"
    src.write_bytes(b"")
    code, _, err = run([src, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "tom")
    assert not (tmp_path / "ut").exists()


@pytest.mark.parametrize("content, needle", [
    (b"\x89PNG\r\n\x1a\n\x00\x00", "UTF-8"),
    (b"1\n00:00:01,000 --> 00:00:02,000\nhei\n", "gyldig JSON"),
    (b'{"text": "hei"}', "segments"),
    (b'{"segments": [{"start": 1, "text": "hei"}]}', "end"),
    (b'{"segments": [{"start": 2, "end": 1, "text": "hei"}]}', "før"),
    (b'{"segments": []}', "ingen tekst"),
], ids=["binær", "srt", "uten_segments", "uten_end", "end_før_start", "tom_liste"])
def test_wrong_format(tmp_path, capsys, content, needle):
    src = tmp_path / "feil.json"
    src.write_bytes(content)
    code, _, err = run([src, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, needle)
    assert not (tmp_path / "ut").exists()


def test_bad_file_among_many_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "tom.json"
    bad.write_bytes(b"")
    code, _, err = run([WITH_WORDS, bad, "--out", tmp_path / "ut"], capsys)
    _assert_user_error(code, err, "tom")
    assert not (tmp_path / "ut").exists()


def test_bad_rules(tmp_path, capsys):
    code, _, err = run([WITH_WORDS, "--out", tmp_path, "--min-duration", "8"], capsys)
    _assert_user_error(code, err, "--min-duration")
    code, _, err = run([WITH_WORDS, "--out", tmp_path, "--max-chars", "x"], capsys)
    _assert_user_error(code, err, "Ugyldige argumenter")


def test_missing_out_argument(capsys):
    code, _, err = run([WITH_WORDS], capsys)
    _assert_user_error(code, err, "--out")


# ------------------------------------------------------------ unit tests


def test_wrap_only_breaks_between_words():
    words = tuple("Kulturhuset har fått et tilskudd fra kommunen, og det har vært".split())
    lines = core.wrap(words, 42, 2)
    assert lines is not None and len(lines) == 2
    assert all(len(line) <= 42 for line in lines)
    assert " ".join(lines).split() == list(words)


def test_wrap_prefers_comma():
    words = tuple("Vi søkte om mer, men vi forstår at kommunen sier nei".split())
    assert core.wrap(words, 42, 2)[0] == "Vi søkte om mer,"


def test_wrap_impossible_returns_none():
    assert core.wrap(("a" * 50,), 42, 2) is None
    assert core.wrap(tuple(["ord"] * 40), 42, 2) is None


def test_overlong_word_gets_own_cue_and_warning(tmp_path):
    src = tmp_path / "lang.json"
    word = "Donaudampfschifffahrtsgesellschaftskapitänsmütze"
    src.write_text(json.dumps({"segments": [
        {"start": 0, "end": 3, "text": f" Hei {word} hei."},
    ]}), encoding="utf-8")
    rules = core.Rules()
    cues = core.make_cues(core.load_transcript(src), rules)
    assert [c.text for c in cues] == ["Hei", word, "hei."]
    problems = core.check_cues(cues, rules)
    assert any("tegn (maks 42)" in p for p in problems)


def _non_duration_problems(cues, rules):
    """check_cues without the minimum-duration findings (allowed on purpose)."""
    return [p for p in core.check_cues(cues, rules) if "(minst" not in p or "ms mellom" in p]


def test_fix_timing_keeps_gap_and_minimum():
    rules = core.Rules()
    w = core.Word
    cues = [
        core.Cue(0, 300, [w("a", 0, 300)], ["a"]),
        core.Cue(300, 600, [w("b", 300, 600)], ["b"]),
        core.Cue(600, 9600, [w("c", 600, 9600)], ["c"]),
    ]
    notes = {}
    core._fix_timing(cues, rules, notes)
    # Nothing is pushed later than its start; dense cues are merged instead.
    assert notes["merged"] >= 1
    assert cues[-1].start <= 600 + core.MAX_PUSH_MS
    assert all(c.start <= 600 + core.MAX_PUSH_MS for c in cues)
    assert all(b.start - a.end >= rules.gap_ms for a, b in zip(cues, cues[1:]))
    assert [p for p in _non_duration_problems(cues, rules) if "høyst 7 s" in p or "tegn" in p or "linjer" in p] == []


def test_check_cues_reports_violations():
    rules = core.Rules()
    w = core.Word("x", 0, 0)
    cues = [
        core.Cue(0, 500, [w], ["x" * 43, "y", "z"]),
        core.Cue(520, 9000, [w], ["ok"]),
    ]
    problems = " ".join(core.check_cues(cues, rules))
    for needle in ("43 tegn", "3 linjer", "minst 1 s", "høyst 7 s", "20 ms"):
        assert needle in problems


def test_bare_segment_list_and_punctuation_tokens(tmp_path):
    src = tmp_path / "liste.json"
    src.write_text(json.dumps([
        {"start": 0, "end": 2, "text": " Hei",
         "words": [{"word": " Hei", "start": 0, "end": 1.5}, {"word": ",", "start": 1.5, "end": 1.6}]},
        {"start": 3, "end": 5, "text": " Ha det ."},
    ]), encoding="utf-8")
    cues = core.make_cues(core.load_transcript(src), core.Rules())
    assert [c.lines for c in cues] == [["Hei,"], ["Ha det."]]


def test_vtt_escapes_markup():
    cue = core.Cue(0, 1000, [core.Word("a<b>&c", 0, 1000)], ["a<b>&c"])
    assert "a&lt;b&gt;&amp;c" in core.to_vtt([cue])


def test_dense_short_cues_do_not_accumulate_delay(tmp_path, capsys):
    segs = []
    for n in range(60):
        start = n * 0.3
        segs.append({"start": start, "end": start + 0.25, "text": f" Ja {n}."})
    src = tmp_path / "tett.json"
    src.write_text(json.dumps({"segments": segs}), encoding="utf-8")
    report, srt, vtt = convert(src, tmp_path / "ut", capsys)
    cues = parse_srt(srt)
    original_starts = [round(s["start"] * 1000) for s in segs]
    max_drift = core.MAX_PUSH_MS
    for start, _, _ in cues:
        # each cue starts at (or just after) the original time code of its first segment
        assert any(0 <= start - o <= max_drift for o in original_starts)
    assert cues[-1][0] <= original_starts[-1] + max_drift
    assert any("slått sammen" in w for w in report["warnings"])
    assert not [w for w in report["warnings"] if "tegn (maks" in w or "linjer (maks" in w or "høyst 7 s" in w]
    assert all(len(l) <= 42 and len(ls) <= 2 and e - st <= 7000 for st, e, ls in cues for l in ls)
    assert all(b[0] - a[1] >= 80 for a, b in zip(cues, cues[1:]))


def test_dense_cues_that_cannot_merge_are_truncated_with_warning(tmp_path, capsys):
    word = "Donaudampfschifffahrtsgesellschaftskapitänsmütze"
    segs = [{"start": n * 0.3, "end": n * 0.3 + 0.25, "text": f" {word}{n}"} for n in range(20)]
    src = tmp_path / "lange.json"
    src.write_text(json.dumps({"segments": segs}), encoding="utf-8")
    report, srt, _ = convert(src, tmp_path / "ut", capsys)
    cues = parse_srt(srt)
    for (start, _, _), seg in zip(cues, segs):
        assert 0 <= start - round(seg["start"] * 1000) <= core.MAX_PUSH_MS
    assert any("avkortet" in w or "slått sammen" in w for w in report["warnings"])


@pytest.mark.parametrize("flag", ["--gap", "--min-duration", "--max-duration"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1", "1e999"])
def test_non_finite_or_negative_durations_are_user_errors(flag, value, tmp_path, capsys):
    code, _, err = run([WITH_WORDS, "--out", tmp_path, f"{flag}={value}"], capsys)
    _assert_user_error(code, err, flag)
    assert not list(tmp_path.glob("*.srt"))
