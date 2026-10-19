"""Core logic: measure with ebur128, normalise with two-pass loudnorm.

No printing, no sys.exit. Everything external goes through
subprocess.run([...], check=False).
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jv_common import UserError, require_binary, safe_output_path

TARGETS: dict[str, tuple[float, float]] = {
    # name -> (integrated LUFS, true peak dBTP)
    "podcast": (-16.0, -1.0),
    "broadcast": (-23.0, -1.0),
}
TRUE_PEAK = -1.0
LUFS_MIN, LUFS_MAX = -70.0, -5.0  # range accepted by loudnorm's "i"
TOLERANCE_LU = 0.5
DEFAULT_LRA = 11.0
MAX_LRA = 20.0  # upper bound of loudnorm's "lra" in ffmpeg 4.4

AUDIO_FORMATS = {".wav", ".mp3", ".m4a", ".flac"}
VIDEO_FORMATS = {".mp4", ".mov", ".m4v", ".mkv"}
# muxer per extension, so ffmpeg never has to guess
MUXERS = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".m4a": "ipod",
    ".flac": "flac",
    ".mp4": "mp4",
    ".m4v": "mp4",
    ".mov": "mov",
    ".mkv": "matroska",
}
LOSSY_BITRATES_KBPS = (128, 160, 192, 224, 256, 320)
DEFAULT_BITRATE_KBPS = 192
OUTPUT_SUFFIX = "-normalisert"

ProgressFn = Callable[[float], None]


@dataclass
class Measurement:
    integrated_lufs: float
    true_peak_dbtp: float

    def as_dict(self) -> dict[str, float | None]:
        return {
            "integrated_lufs": _finite_or_none(self.integrated_lufs),
            "true_peak_dbtp": _finite_or_none(self.true_peak_dbtp),
        }


def _finite_or_none(value: float) -> float | None:
    return round(value, 1) if math.isfinite(value) else None


def resolve_target(target: str | None, lufs: float | None) -> tuple[float, float, str]:
    """Return (integrated LUFS, true peak, label)."""
    if lufs is not None:
        if not math.isfinite(lufs) or not LUFS_MIN <= lufs <= LUFS_MAX:
            raise UserError(
                f"--lufs må være mellom {LUFS_MIN:g} og {LUFS_MAX:g} (fikk {lufs:g})."
            )
        return float(lufs), TRUE_PEAK, "egendefinert"
    name = target or "podcast"
    if name not in TARGETS:
        raise UserError(f"Ukjent mål «{name}». Velg podcast eller broadcast.")
    i, tp = TARGETS[name]
    return i, tp, name


# ---------------------------------------------------------------- ffmpeg I/O


def file_url(path: Path) -> str:
    """Absolute "file:" URL, so ffmpeg never reads a name such as
    "opptak:1.wav" or "http:x" as a protocol."""
    return "file:" + str(Path(path).resolve())


def _input_args(path: Path) -> list[str]:
    # only the local file protocol is allowed for inputs
    return ["-protocol_whitelist", "file", "-i", file_url(path)]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )


def _tail(text: str, lines: int = 3) -> str:
    rows = [r.strip() for r in text.strip().splitlines() if r.strip()]
    return " | ".join(rows[-lines:])


def probe(path: Path) -> dict[str, Any]:
    """ffprobe the file. Raises UserError if it cannot be read as media."""
    ffprobe = require_binary("ffprobe")
    res = _run(
        [
            ffprobe, "-v", "error", "-show_streams", "-show_format",
            "-of", "json", *_input_args(path),
        ]
    )
    if res.returncode != 0:
        raise UserError(
            f"Kunne ikke lese «{path.name}» som lyd eller video. "
            f"Er filen skadet eller i et ukjent format? ({_tail(res.stderr, 1)})"
        )
    try:
        data = json.loads(res.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise UserError(f"Kunne ikke tolke ffprobe-svaret for «{path.name}».") from exc
    return data


def _audio_stream(info: dict[str, Any], path: Path) -> dict[str, Any]:
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    raise UserError(f"«{path.name}» har ikke noe lydspor.")


def _has_real_video(info: dict[str, Any]) -> bool:
    for stream in info.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        if (stream.get("disposition") or {}).get("attached_pic"):
            continue  # cover art, not a video track
        return True
    return False


_JSON_BLOCK = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)
_NUMBER = r"([-+]?(?:inf|nan|\d+(?:\.\d+)?))"


def _to_float(text: str) -> float:
    try:
        return float(str(text).strip())
    except ValueError:
        return float("nan")


def parse_loudnorm(stderr: str) -> dict[str, float | str]:
    """Return the last loudnorm JSON block from ffmpeg's log.

    Works for ffmpeg 4.x-7.x: the block is printed after a
    "[Parsed_loudnorm_N @ ...]" line and its values are strings.
    """
    blocks = _JSON_BLOCK.findall(stderr)
    if not blocks:
        raise ValueError("fant ingen loudnorm-måling i ffmpeg-utdata")
    raw = json.loads(blocks[-1])
    result: dict[str, float | str] = {}
    for key, value in raw.items():
        if key == "normalization_type":
            result[key] = str(value)
        else:
            result[key] = _to_float(value)
    return result


def parse_ebur128(stderr: str) -> Measurement:
    """Parse the last ebur128 summary (integrated loudness and true peak).

    The summary looks like this in ffmpeg 4.4 and newer:

        Integrated loudness:
          I:         -20.2 LUFS
        ...
        True peak:
          Peak:       -9.3 dBFS
    """
    idx = stderr.rfind("Summary:")
    if idx < 0:
        raise ValueError("fant ingen ebur128-oppsummering i ffmpeg-utdata")
    summary = stderr[idx:]
    m_i = re.search(r"Integrated loudness:\s*\n\s*I:\s*" + _NUMBER, summary, re.I)
    if not m_i:
        raise ValueError("fant ikke integrert loudness i ebur128-oppsummeringen")
    m_tp = re.search(r"True peak:\s*\n\s*Peak:\s*" + _NUMBER, summary, re.I)
    if not m_tp:
        raise ValueError("fant ikke true peak i ebur128-oppsummeringen")
    return Measurement(_to_float(m_i.group(1)), _to_float(m_tp.group(1)))


def _ebur128_filter() -> str:
    # framelog=40 (AV_LOG_VERBOSE) keeps per-frame lines out of the info log
    return "ebur128=peak=true:framelog=40"


def measure(path: Path) -> Measurement:
    """Integrated loudness and true peak of the first audio track."""
    ffmpeg = require_binary("ffmpeg")
    res = _run(
        [
            ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-loglevel", "info",
            *_input_args(path), "-map", "0:a:0", "-af", _ebur128_filter(),
            "-f", "null", "-",
        ]
    )
    if res.returncode != 0:
        raise UserError(
            f"ffmpeg kunne ikke måle lyden i «{path.name}» ({_tail(res.stderr, 1)})."
        )
    try:
        return parse_ebur128(res.stderr)
    except ValueError as exc:
        raise RuntimeError(f"Måling av «{path.name}» feilet: {exc}") from exc


def _first_pass(path: Path, i: float, tp: float) -> tuple[Measurement, dict[str, Any]]:
    """Measure with ebur128 and loudnorm in one decode."""
    ffmpeg = require_binary("ffmpeg")
    af = f"{_ebur128_filter()},loudnorm=I={i:g}:TP={tp:g}:LRA={DEFAULT_LRA:g}:print_format=json"
    res = _run(
        [
            ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-loglevel", "info",
            *_input_args(path), "-map", "0:a:0", "-af", af, "-f", "null", "-",
        ]
    )
    if res.returncode != 0:
        raise UserError(
            f"ffmpeg kunne ikke lese lyden i «{path.name}» ({_tail(res.stderr, 1)})."
        )
    try:
        before = parse_ebur128(res.stderr)
        stats = parse_loudnorm(res.stderr)
    except ValueError as exc:
        raise RuntimeError(f"Første pass for «{path.name}» feilet: {exc}") from exc
    return before, stats


# ---------------------------------------------------------------- encoding


def _lossy_bitrate(stream: dict[str, Any], info: dict[str, Any]) -> int:
    """Bitrate in kb/s: the source rate rounded up to a standard step,
    at least 128 and at most 320 kb/s. 192 kb/s if unknown."""
    raw = stream.get("bit_rate") or (info.get("format") or {}).get("bit_rate")
    try:
        kbps = int(raw) / 1000
    except (TypeError, ValueError):
        return DEFAULT_BITRATE_KBPS
    if kbps <= 0:
        return DEFAULT_BITRATE_KBPS
    for step in LOSSY_BITRATES_KBPS:
        if kbps <= step + 1:  # tolerate e.g. 128.3 kb/s
            return step
    return LOSSY_BITRATES_KBPS[-1]


def _audio_codec_args(
    ext: str, stream: dict[str, Any], info: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """ffmpeg arguments for the output audio codec, and report details."""
    codec = stream.get("codec_name") or ""
    if ext == ".wav":
        pcm = codec if codec.startswith("pcm_") else "pcm_s16le"
        return ["-c:a", pcm], {"codec": pcm}
    if ext == ".flac":
        bits = int(stream.get("bits_per_raw_sample") or 16)
        fmt = "s16" if bits <= 16 else "s32"
        args = ["-c:a", "flac", "-sample_fmt", fmt]
        if bits > 16:
            args += ["-bits_per_raw_sample", "24"]
        return args, {"codec": "flac"}
    kbps = _lossy_bitrate(stream, info)
    if ext == ".mp3":
        return ["-c:a", "libmp3lame", "-b:a", f"{kbps}k"], {
            "codec": "mp3", "bitrate_kbps": kbps,
        }
    # .m4a and all video containers: AAC
    return ["-c:a", "aac", "-b:a", f"{kbps}k"], {"codec": "aac", "bitrate_kbps": kbps}


def _second_pass(
    src: Path,
    dst: Path,
    ext: str,
    is_video: bool,
    i: float,
    tp: float,
    stats: dict[str, Any],
    stream: dict[str, Any],
    info: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ffmpeg = require_binary("ffmpeg")
    measured_i = max(-99.0, min(0.0, stats["input_i"]))
    measured_tp = max(-99.0, min(99.0, stats["input_tp"]))
    measured_lra = max(0.0, min(99.0, stats["input_lra"]))
    measured_thresh = max(-99.0, min(0.0, stats["input_thresh"]))
    offset = stats.get("target_offset", 0.0)
    if not math.isfinite(offset):
        offset = 0.0
    offset = max(-99.0, min(99.0, offset))
    # loudnorm falls back to dynamic mode if the source LRA exceeds the
    # target LRA, so allow the source's own range (up to the filter limit).
    lra = min(MAX_LRA, max(DEFAULT_LRA, math.ceil(measured_lra * 10 + 1) / 10))
    af = (
        f"loudnorm=I={i:g}:TP={tp:g}:LRA={lra:g}"
        f":measured_I={measured_i:.2f}:measured_TP={measured_tp:.2f}"
        f":measured_LRA={measured_lra:.2f}:measured_thresh={measured_thresh:.2f}"
        f":offset={offset:.2f}:linear=true:print_format=json"
    )
    sample_rate = str(stream.get("sample_rate") or "48000")
    codec_args, details = _audio_codec_args(ext, stream, info)

    cmd = [ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-loglevel", "info", "-n",
           *_input_args(src)]
    if is_video:
        cmd += ["-map", "0:v", "-map", "0:a:0", "-c:v", "copy"]
    else:
        cmd += ["-map", "0:a:0"]
    cmd += ["-map_metadata", "0", "-af", af, "-ar", sample_rate]
    cmd += codec_args
    if ext in {".mp4", ".m4v", ".mov", ".m4a"}:
        cmd += ["-movflags", "+faststart"]
    cmd += ["-f", MUXERS[ext], file_url(dst)]

    res = _run(cmd)
    if res.returncode != 0:
        _remove_quietly(dst)
        raise UserError(
            f"ffmpeg kunne ikke skrive «{dst.name}» ({_tail(res.stderr, 2)})."
        )
    try:
        out_stats = parse_loudnorm(res.stderr)
    except ValueError:
        out_stats = {}
    details["sample_rate"] = int(sample_rate)
    return details, out_stats


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------- public API


def check_input(path: Path) -> tuple[str, bool, dict[str, Any], dict[str, Any]]:
    """Validate one input. Returns (extension, is_video, audio stream, probe)."""
    if not path.exists():
        raise UserError(f"Filen «{path}» finnes ikke.")
    if not path.is_file():
        raise UserError(f"«{path}» er ikke en fil.")
    if path.stat().st_size == 0:
        raise UserError(f"Filen «{path.name}» er tom.")
    ext = path.suffix.lower()
    if ext not in AUDIO_FORMATS | VIDEO_FORMATS:
        supported = ", ".join(sorted(AUDIO_FORMATS | VIDEO_FORMATS))
        raise UserError(
            f"Formatet «{path.suffix or '(uten filendelse)'}» støttes ikke for «{path.name}». "
            f"Støttet: {supported}."
        )
    info = probe(path)
    stream = _audio_stream(info, path)
    # an .mp4 with only sound is written as an audio-only .mp4
    is_video = ext in VIDEO_FORMATS and _has_real_video(info)
    return ext, is_video, stream, info


def normalize(
    path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    lufs: float,
    true_peak: float = TRUE_PEAK,
    progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Normalise one file. Returns a report entry (dict) for the output."""
    src = Path(path)
    tick = progress or (lambda _f: None)
    ext, is_video, stream, info = check_input(src)

    before, stats = _first_pass(src, lufs, true_peak)
    tick(1 / 3)
    if not math.isfinite(stats.get("input_i", float("nan"))) or stats["input_i"] <= -70:
        raise UserError(
            f"«{src.name}» er stille eller for kort til å måle lydnivået."
        )

    dst = safe_output_path(src, out_dir, f"{OUTPUT_SUFFIX}{src.suffix}")
    details, out_stats = _second_pass(
        src, dst, ext, is_video, lufs, true_peak, stats, stream, info
    )
    tick(2 / 3)

    try:
        after = measure(dst)
    except Exception:
        _remove_quietly(dst)
        raise
    tick(1.0)

    warnings: list[str] = []
    mode = str(out_stats.get("normalization_type") or "ukjent")
    if mode == "dynamic":
        warnings.append(
            f"«{src.name}»: lineær justering var ikke mulig, så loudnorm brukte "
            "dynamisk modus (komprimering/limiter). Lyden kan høres litt annerledes ut."
        )
    within = (
        math.isfinite(after.integrated_lufs)
        and abs(after.integrated_lufs - lufs) <= TOLERANCE_LU
    )
    under_peak = math.isfinite(after.true_peak_dbtp) and after.true_peak_dbtp < true_peak
    if not within:
        warnings.append(
            f"«{dst.name}» endte på {after.integrated_lufs:.1f} LUFS, mer enn "
            f"{TOLERANCE_LU} LU fra målet {lufs:g} LUFS."
        )
    if not under_peak:
        warnings.append(
            f"«{dst.name}» har true peak {after.true_peak_dbtp:.1f} dBTP, over "
            f"grensen {true_peak:g} dBTP"
            + (" (vanlig etter tapsbasert koding)." if "bitrate_kbps" in details else ".")
        )

    entry: dict[str, Any] = {
        "path": str(dst),
        "source": str(src),
        "format": ext.lstrip("."),
        **details,
        "video": "kopiert uten omkoding" if is_video else None,
        "target": {"integrated_lufs": lufs, "true_peak_dbtp": true_peak},
        "before": before.as_dict(),
        "after": after.as_dict(),
        "normalization": {"linear": "lineær", "dynamic": "dynamisk"}.get(mode, mode),
        "within_target": bool(within and under_peak),
    }
    if not is_video:
        entry.pop("video")
    return {"entry": entry, "warnings": warnings}
