"""Extract still frames from video, at fixed intervals or at scene cuts.

Pure logic: no printing, no sys.exit. External programs (ffprobe, ffmpeg)
are called with argument lists, never through a shell. Only options that
exist in both ffmpeg 4.4 and newer releases are used.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path

from jv_common import UserError, require_binary, safe_output_path
from PIL import Image, ImageDraw, ImageFont

JPEG_QUALITY = 92
THUMB_BOX = 240  # max width/height of a contact-sheet thumbnail
LABEL_HEIGHT = 22
PADDING = 6

ProgressFn = Callable[[float], None]

# ffmpeg/ffprobe may only read local files: no http:, tcp:, concat: etc.
# (the whitelist is an input option and does not affect pipe output).
PROTOCOL_WHITELIST = "file"


def ffmpeg_input(path: Path) -> list[str]:
    """Input arguments that can never be read as a URL or an option.

    A bare name like "http:x.mp4" or "opptak:1.mp4" would otherwise be
    parsed by ffmpeg as a protocol prefix.
    """
    return ["-protocol_whitelist", PROTOCOL_WHITELIST, "-i", "file:" + str(path.resolve())]


@dataclass
class VideoInfo:
    duration: float  # seconds
    width: int  # as displayed (after rotation)
    height: int
    stored_width: int
    stored_height: int
    fps: float | None
    rotation: int  # degrees clockwise the stored picture is turned for display
    codec: str
    start_time: float = 0.0


@dataclass
class Frame:
    time: float  # seconds from the start of the video
    path: Path


@dataclass
class VideoResult:
    input: Path
    info: VideoInfo
    frames_dir: Path
    frames: list[Frame] = field(default_factory=list)
    contact_sheet: Path | None = None
    warnings: list[str] = field(default_factory=list)

    def info_dict(self) -> dict:
        data = asdict(self.info)
        data.pop("start_time", None)
        data["duration"] = round(self.info.duration, 3)
        if self.info.fps is not None:
            data["fps"] = round(self.info.fps, 3)
        return {"path": str(self.input), **data}


# ---------------------------------------------------------------- parsing

_INTERVAL_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(s|sek)?\s*$", re.IGNORECASE)


def parse_interval(text: str) -> float:
    """'2s', '2', '0,5s' -> seconds (float > 0)."""
    match = _INTERVAL_RE.match(str(text))
    if not match:
        raise UserError(
            f"Ugyldig intervall «{text}». Bruk sekunder, for eksempel «--every 2s»."
        )
    value = float(match.group(1).replace(",", "."))
    if value <= 0:
        raise UserError("Intervallet må være større enn null.")
    return value


def parse_threshold(text: str) -> float:
    try:
        value = float(str(text).replace(",", "."))
    except ValueError:
        raise UserError(
            f"Ugyldig terskel «{text}». Bruk et tall mellom 0 og 1, for eksempel «--scenes 0.3»."
        ) from None
    if not 0 < value < 1:
        raise UserError("Terskelen for --scenes må være mellom 0 og 1 (for eksempel 0.3).")
    return value


def format_timecode(seconds: float) -> str:
    """12.48 -> '00:00:12.480' (used on the contact sheet)."""
    ms_total = max(0, round(seconds * 1000))
    hours, rest = divmod(ms_total, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def frame_filename(seconds: float) -> str:
    """12.48 -> '000012.480.jpg'."""
    ms_total = max(0, round(seconds * 1000))
    secs, ms = divmod(ms_total, 1000)
    return f"{secs:06d}.{ms:03d}.jpg"


# ---------------------------------------------------------------- probing


def _parse_rate(text: str | None) -> float | None:
    if not text or text in ("0/0", "0"):
        return None
    try:
        value = float(Fraction(text))
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def _rotation(stream: dict) -> int:
    """Clockwise display rotation in degrees (0, 90, 180, 270).

    ffmpeg 4.4 exposes both the 'rotate' tag and the display matrix;
    newer releases only the display matrix, whose 'rotation' has the
    opposite sign (counter-clockwise).
    """
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        try:
            return int(round(float(tags["rotate"]))) % 360
        except ValueError:
            pass
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            try:
                return int(round(-float(side["rotation"]))) % 360
            except (TypeError, ValueError):
                continue
    return 0


def _float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def check_input(path: Path) -> None:
    if not path.exists():
        raise UserError(f"Finner ikke filen «{path}».")
    if not path.is_file():
        raise UserError(f"«{path}» er ikke en fil.")
    if path.stat().st_size == 0:
        raise UserError(f"Filen «{path}» er tom.")


def probe(path: Path) -> VideoInfo:
    ffprobe = require_binary("ffprobe")
    proc = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_streams", "-show_format", "-of", "json", *ffmpeg_input(path),
        ],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise UserError(f"Filen «{path.name}» kan ikke leses som video av ffprobe.")
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        raise UserError(f"Filen «{path.name}» kan ikke leses som video av ffprobe.") from None
    streams = [s for s in data.get("streams") or [] if s.get("codec_type") == "video"]
    if not streams:
        raise UserError(f"Fant ikke noe videospor i «{path.name}».")
    stream = streams[0]
    fmt = data.get("format") or {}
    if (stream.get("disposition") or {}).get("attached_pic"):
        raise UserError(f"«{path.name}» har bare et omslagsbilde, ikke video.")
    duration = _float(fmt.get("duration")) or _float(stream.get("duration"))
    if not duration or duration <= 0:
        raise UserError(f"Klarte ikke å lese varigheten til «{path.name}».")
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise UserError(f"Klarte ikke å lese oppløsningen til «{path.name}».")
    rotation = _rotation(stream)
    disp_w, disp_h = (height, width) if rotation in (90, 270) else (width, height)
    fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(stream.get("r_frame_rate"))
    start = _float(fmt.get("start_time")) or _float(stream.get("start_time")) or 0.0
    return VideoInfo(
        duration=duration,
        width=disp_w,
        height=disp_h,
        stored_width=width,
        stored_height=height,
        fps=fps,
        rotation=rotation,
        codec=str(stream.get("codec_name") or "ukjent"),
        start_time=start,
    )


# ---------------------------------------------------------------- timestamps


def interval_times(duration: float, step: float, fps: float | None) -> list[float]:
    """0, step, 2*step, ... strictly before the last frame."""
    last = duration - (1.0 / fps if fps else 0.04)
    count = int(math.floor(max(0.0, last) / step + 1e-9)) + 1
    return [round(i * step, 6) for i in range(count)]


_PTS_RE = re.compile(r"\bpts_time:\s*(-?\d+(?:\.\d+)?)")
_OUT_TIME_RE = re.compile(r"^out_time_(?:us|ms)=(\d+)")


def scene_times(
    path: Path,
    info: VideoInfo,
    threshold: float,
    progress: ProgressFn | None = None,
) -> list[float]:
    """Times of scene cuts (score > threshold), plus 0 for the first shot."""
    ffmpeg = require_binary("ffmpeg")
    vf = f"select='gt(scene,{threshold:g})',showinfo"
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(
            [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "info",
                *ffmpeg_input(path), "-map", "0:v:0", "-an", "-sn", "-dn",
                "-vf", vf, "-progress", "pipe:1", "-nostats", "-f", "null", "-",
            ],
            stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL,
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            match = _OUT_TIME_RE.match(raw.decode("ascii", errors="ignore").strip())
            if match and progress is not None:
                # out_time_ms is in microseconds in every ffmpeg release
                progress(min(1.0, int(match.group(1)) / 1e6 / info.duration))
        proc.wait()
        err.seek(0)
        log = err.read().decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise UserError(f"ffmpeg klarte ikke å analysere «{path.name}» for klipp.")
    times = [0.0]
    for line in log.splitlines():
        if "showinfo" not in line:
            continue
        match = _PTS_RE.search(line)
        if match:
            t = max(0.0, float(match.group(1)) - info.start_time)
            if t > 0.0005:
                times.append(round(t, 6))
    return sorted(set(times))


# ---------------------------------------------------------------- extraction


def extract_frame(path: Path, seconds: float) -> Image.Image | None:
    """Decode one frame at `seconds` (autorotated, as displayed)."""
    ffmpeg = require_binary("ffmpeg")
    proc = subprocess.run(
        [
            ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", f"{seconds:.6f}", *ffmpeg_input(path),
            "-map", "0:v:0", "-an", "-sn", "-dn", "-frames:v", "1",
            "-f", "image2pipe", "-c:v", "png", "pipe:1",
        ],
        capture_output=True, check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        image = Image.open(io.BytesIO(proc.stdout))
        image.load()
    except Exception:  # noqa: BLE001 - treat any decode problem as "no frame"
        return None
    return image.convert("RGB")


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, OSError, ImportError):
        return ImageFont.load_default()


def make_contact_sheet(frames: list[Frame], images: list[Image.Image], target: Path) -> None:
    if not images:
        raise ValueError("no frames")
    thumbs = []
    for img in images:
        thumb = img.copy()
        thumb.thumbnail((THUMB_BOX, THUMB_BOX))
        thumbs.append(thumb)
    cell_w = max(t.width for t in thumbs) + 2 * PADDING
    cell_h = max(t.height for t in thumbs) + LABEL_HEIGHT + 2 * PADDING
    n = len(thumbs)
    cols = max(1, min(n, max(6, math.ceil(math.sqrt(n)))))
    rows = math.ceil(n / cols)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font = _font(15)
    for i, (frame, thumb) in enumerate(zip(frames, thumbs)):
        col, row = i % cols, i // cols
        x0, y0 = col * cell_w, row * cell_h
        sheet.paste(thumb, (x0 + (cell_w - thumb.width) // 2, y0 + PADDING))
        label = format_timecode(frame.time)
        box = draw.textbbox((0, 0), label, font=font)
        text_w = box[2] - box[0]
        ty = y0 + cell_h - PADDING - LABEL_HEIGHT + (LABEL_HEIGHT - (box[3] - box[1])) // 2 - box[1]
        draw.text((x0 + (cell_w - text_w) // 2 - box[0], ty), label, fill=(255, 255, 255), font=font)
    sheet.save(target, "JPEG", quality=88)


def extract(
    input_path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    *,
    every: float | None = None,
    scenes: float | None = None,
    progress: ProgressFn | None = None,
) -> VideoResult:
    """Extract frames from one video into a new folder in out_dir.

    Exactly one of `every` (seconds) and `scenes` (threshold 0..1) is used.
    Writes <stem>-bilder/<timecode>.jpg and <stem>-kontaktark.jpg.
    """
    if (every is None) == (scenes is None):
        raise UserError("Velg enten --every eller --scenes.")
    src = Path(input_path)
    check_input(src)
    info = probe(src)

    def report(part: float, offset: float, share: float) -> None:
        if progress is not None:
            progress(offset + share * part)

    if every is not None:
        times = interval_times(info.duration, every, info.fps)
        extract_share, extract_offset = 1.0, 0.0
    else:
        times = scene_times(src, info, scenes, lambda p: report(p, 0.0, 0.5))
        extract_share, extract_offset = 0.5, 0.5

    frames_dir = safe_output_path(src, out_dir, "-bilder")
    result = VideoResult(input=src, info=info, frames_dir=frames_dir)

    images: list[Image.Image] = []
    missing: list[float] = []
    for i, t in enumerate(times):
        image = extract_frame(src, t)
        if image is None:
            missing.append(t)
        else:
            if not result.frames:
                # created only once there is a frame, so no empty folder is left behind
                frames_dir.mkdir(parents=False, exist_ok=False)
            target = frames_dir / frame_filename(t)
            image.save(target, "JPEG", quality=JPEG_QUALITY)
            result.frames.append(Frame(time=t, path=target))
            thumb = image.copy()
            thumb.thumbnail((THUMB_BOX, THUMB_BOX))
            images.append(thumb)
        report((i + 1) / len(times), extract_offset, extract_share)

    if missing:
        listed = ", ".join(format_timecode(t) for t in missing[:5])
        more = " …" if len(missing) > 5 else ""
        result.warnings.append(
            f"{src.name}: fant ikke bilde ved {len(missing)} tidspunkt ({listed}{more})."
        )
    if not result.frames:
        raise UserError(f"Klarte ikke å trekke ut noen bilder fra «{src.name}».")

    sheet = safe_output_path(src, out_dir, "-kontaktark.jpg")
    make_contact_sheet(result.frames, images, sheet)
    result.contact_sheet = sheet
    return result
