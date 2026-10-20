"""OCR logic: ocrmypdf with nor+eng, skip pages with text, rotate and deskew.

No printing, no sys.exit. Raises jv_common.UserError for problems the user
can fix.
"""

from __future__ import annotations

import csv
import io
import contextlib
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from jv_common import UserError, require_binary, safe_output_path

LANGUAGES = "nor+eng"
LOW_CONFIDENCE = 60.0
DEFAULT_IMAGE_DPI = 300
CONFIDENCE_DPI = 300

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
SUPPORTED_SUFFIXES = PDF_SUFFIXES | IMAGE_SUFFIXES

ProgressFn = Callable[[float], None]


@dataclass
class PageResult:
    number: int  # 1-based
    ocr: bool
    confidence: float | None = None  # mean word confidence, only for OCR pages
    words: int = 0


@dataclass
class FileResult:
    source: Path
    output: Path
    text_output: Path | None
    pages: list[PageResult]
    image_dpi_assumed: int | None = None
    repaired: bool = False

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def ocr_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.ocr]

    @property
    def low_confidence(self) -> list[PageResult]:
        return [
            p
            for p in self.pages
            if p.ocr and (p.confidence is None or p.confidence < LOW_CONFIDENCE)
        ]


# --------------------------------------------------------------------------
# Environment checks


def check_dependencies() -> None:
    """Raise UserError (Norwegian, with brew command) if something is missing."""
    # Ghostscript is not needed: ocrmypdf writes plain PDF (output_type="pdf"),
    # not PDF/A (docs/spike-sidecar.md, decided by John Inge 19.10.2026).
    tesseract = require_binary("tesseract")
    proc = subprocess.run(
        [tesseract, "--list-langs"], capture_output=True, text=True, check=False
    )
    langs = {line.strip() for line in (proc.stdout + proc.stderr).splitlines()}
    missing = [lang for lang in LANGUAGES.split("+") if lang not in langs]
    if missing:
        raise UserError(
            "Tesseract mangler språkdata for "
            + ", ".join(f"«{m}»" for m in missing)
            + ". Installer det med: brew install tesseract-lang"
        )


# --------------------------------------------------------------------------
# Inputs


def collect_inputs(paths: list[str | Path]) -> list[Path]:
    """Expand folders (one level, sorted) and validate every file."""
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise UserError(f"Finner ikke «{path}».")
        if path.is_dir():
            found = sorted(
                p
                for p in path.iterdir()
                if p.is_file()
                and not p.name.startswith(".")
                and p.suffix.lower() in SUPPORTED_SUFFIXES
            )
            if not found:
                raise UserError(
                    f"Mappen «{path}» inneholder ingen PDF- eller bildefiler "
                    "(pdf, jpg, png, tif)."
                )
            files.extend(found)
        else:
            files.append(path)
    for file in files:
        _validate_file(file)
    return files


def _validate_file(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UserError(
            f"«{path.name}» har et format som ikke støttes. "
            "Bruk PDF, JPEG, PNG eller TIFF."
        )
    if path.stat().st_size == 0:
        raise UserError(f"«{path.name}» er tom.")
    with open(path, "rb") as handle:
        head = handle.read(1024)
    if suffix in PDF_SUFFIXES:
        if b"%PDF" not in head:
            raise UserError(f"«{path.name}» er ikke en gyldig PDF-fil.")
        _check_pdf_opens(path)
    else:
        _check_image_loads(path)


def _check_image_loads(path: Path) -> None:
    """Open, verify and fully decode the image (verify() alone skips pixel data)."""
    from PIL import Image

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # PIL "Truncated File Read" etc.
        try:
            with Image.open(path) as img:
                img_format = img.format
        except Exception as exc:  # noqa: BLE001 - not an image Pillow knows
            raise UserError(f"«{path.name}» er ikke et gyldig bilde.") from exc
        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                img.load()
        except Exception as exc:  # noqa: BLE001 - OSError, SyntaxError, ValueError
            raise UserError(
                f"«{path.name}» er skadet eller avkuttet og kan ikke leses som "
                f"bilde ({img_format}). Prøv å hente filen på nytt."
            ) from exc


def _damaged(path: Path) -> UserError:
    return UserError(
        f"«{path.name}» er skadet eller avkuttet og kan ikke leses som PDF. "
        "Prøv å hente filen på nytt."
    )


def _check_pdf_opens(path: Path) -> None:
    """Raise a Norwegian UserError if the PDF cannot be opened at all."""
    import pikepdf
    import pymupdf

    try:
        with pikepdf.open(path) as pdf:
            if len(pdf.pages) == 0:
                raise UserError(f"«{path.name}» har ingen sider.")
    except pikepdf.PasswordError as exc:
        raise UserError(
            f"«{path.name}»: PDF-en er kryptert eller passordbeskyttet. "
            "Fjern beskyttelsen først."
        ) from exc
    except UserError:
        raise
    except Exception as exc:  # noqa: BLE001 - pikepdf.PdfError and friends
        raise _damaged(path) from exc
    try:
        with _quiet_mupdf() as messages, pymupdf.open(path) as doc:
            if doc.page_count == 0:
                raise UserError(f"«{path.name}» har ingen sider.")
            # Render every page cheaply: truncated or broken content streams
            # only show up when the page is actually drawn.
            pymupdf.TOOLS.reset_mupdf_warnings()
            for page in doc:
                page.get_pixmap(dpi=20)
            render_problems = messages()
    except UserError:
        raise
    except Exception as exc:  # noqa: BLE001 - pymupdf.FileDataError etc.
        raise _damaged(path) from exc
    if _MUPDF_ERROR.search(render_problems):
        raise _damaged(path)


_MUPDF_ERROR = re.compile(
    r"error|cannot load|premature|truncated|corrupt", re.IGNORECASE
)


@contextlib.contextmanager
def _quiet_mupdf() -> Iterator[Callable[[], str]]:
    """Silence MuPDF's own stderr messages; yield a getter for its warnings."""
    import pymupdf

    tools = pymupdf.TOOLS
    previous = tools.mupdf_display_errors()
    tools.mupdf_display_errors(False)
    tools.reset_mupdf_warnings()
    try:
        yield tools.mupdf_warnings
    finally:
        tools.mupdf_display_errors(previous)


def _repaired_copy(src: Path, tmp_dir: Path) -> Path | None:
    """If MuPDF had to repair the PDF (e.g. missing xref/trailer), write a
    clean copy for ocrmypdf and return its path. Otherwise None."""
    import pymupdf

    with _quiet_mupdf(), pymupdf.open(src) as doc:
        if not doc.is_repaired:
            return None
        copy = tmp_dir / src.name
        doc.save(copy, garbage=1)
    return copy


def _image_dpi(path: Path) -> int | None:
    """Return None if the image claims a sensible DPI, else the DPI to assume."""
    from PIL import Image

    with Image.open(path) as img:
        dpi = img.info.get("dpi")
        if img.format == "JPEG" and not dpi and "jfif_density" in img.info:
            unit = img.info.get("jfif_unit", 0)
            if unit == 1:
                dpi = img.info["jfif_density"]
    try:
        x, y = (float(dpi[0]), float(dpi[1])) if dpi else (0.0, 0.0)
    except (TypeError, ValueError, IndexError):
        x = y = 0.0
    if x >= 50 and y >= 50:
        return None
    return DEFAULT_IMAGE_DPI


def _pages_with_text(path: Path) -> list[bool]:
    """Per page: does the PDF already have text? Same test as ocrmypdf uses."""
    try:
        from ocrmypdf.pdfinfo import PdfInfo

        return [bool(page.has_text) for page in PdfInfo(path)]
    except Exception:  # noqa: BLE001 - fall back to PyMuPDF
        import pymupdf

        with pymupdf.open(path) as doc:
            return [bool(page.get_text("text").strip()) for page in doc]


# --------------------------------------------------------------------------
# Confidence


def tesseract_tsv(png: bytes, lang: str = LANGUAGES) -> list[dict[str, str]]:
    """Run tesseract on a PNG image and return the TSV rows for words."""
    tesseract = require_binary("tesseract")
    proc = subprocess.run(
        [tesseract, "stdin", "stdout", "-l", lang, "tsv"],
        input=png,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "tesseract feilet: " + proc.stderr.decode("utf-8", "replace").strip()
        )
    text = proc.stdout.decode("utf-8", "replace")
    rows = csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE)
    return [r for r in rows if r.get("level") == "5" and (r.get("text") or "").strip()]


def render_page_png(pdf: Path, index: int, dpi: int = CONFIDENCE_DPI) -> bytes:
    """Render one page (0-based) to a grayscale PNG. Invisible text is not drawn."""
    import pymupdf

    with _quiet_mupdf(), pymupdf.open(pdf) as doc:
        pix = doc[index].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        return pix.tobytes("png")


def page_confidence(pdf: Path, index: int) -> tuple[float | None, int]:
    """Mean word confidence (0-100) for a page, and number of words."""
    rows = tesseract_tsv(render_page_png(pdf, index))
    confs = []
    for row in rows:
        try:
            value = float(row.get("conf", "-1"))
        except ValueError:
            continue
        if value >= 0:
            confs.append(value)
    if not confs:
        return None, 0
    return sum(confs) / len(confs), len(confs)


# --------------------------------------------------------------------------
# OCR


_ERROR_TEXT = {
    "EncryptedPdfError": "PDF-en er kryptert eller passordbeskyttet. Fjern beskyttelsen først.",
    "DigitalSignatureError": "PDF-en er digitalt signert. OCR ville gjort signaturen ugyldig.",
    "InputFileError": "Filen kunne ikke leses som PDF eller bilde.",
    "UnsupportedImageFormatError": "Bildeformatet støttes ikke.",
    "DpiError": "Bildet har en ugyldig oppløsning (DPI).",
    "PriorOcrFoundError": "PDF-en har allerede et tekstlag.",
    "TaggedPDFError": "PDF-en er en tagget, digital PDF og trenger ikke OCR.",
    "MissingDependencyError": "Et program ocrmypdf trenger, mangler. "
    "Installer med: brew install tesseract tesseract-lang",
    "TesseractConfigError": "Tesseract er feil satt opp (mangler konfigurasjonsfiler). "
    "Installer på nytt med: brew reinstall tesseract tesseract-lang",
}


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:  # noqa: BLE001
            pass


def _run_ocrmypdf(
    src: Path,
    dst: Path,
    *,
    image_dpi: int | None,
    jobs: int | None,
    on_page: ProgressFn | None,
    name: str | None = None,
) -> list[str]:
    import ocrmypdf
    import pikepdf
    from ocrmypdf import exceptions as ocr_exc

    from . import _progress

    shown = Path(name) if name else src
    logger = logging.getLogger("ocrmypdf")
    capture = _Capture()
    old_propagate = logger.propagate
    logger.addHandler(capture)
    logger.propagate = False
    _progress.callback = on_page
    # ocrmypdf may swap sys.stdout/sys.stderr (for its console) without
    # restoring them; keep ours so the report and progress lines get out.
    saved_streams = (sys.stdout, sys.stderr)
    try:
        ocrmypdf.ocr(
            src,
            dst,
            language=LANGUAGES.split("+"),
            skip_text=True,
            rotate_pages=True,
            deskew=True,
            output_type="pdf",
            image_dpi=image_dpi,
            jobs=jobs,
            progress_bar=True,
            plugins=["jv_ocr._progress"],
        )
    except ocr_exc.ExitCodeException as exc:
        name = type(exc).__name__
        text = _ERROR_TEXT.get(name)
        if text is None:
            for base in type(exc).__mro__:
                if base.__name__ in _ERROR_TEXT:
                    text = _ERROR_TEXT[base.__name__]
                    break
        if text is None:
            text = f"OCR feilet ({name}: {exc})."
        raise _with_cleanup(UserError(f"«{shown.name}»: {text}"), dst) from exc
    except pikepdf.PdfError as exc:
        # Damaged/truncated PDFs that pikepdf/MuPDF "repaired" on open can
        # still fail inside ocrmypdf.
        raise _with_cleanup(_damaged(shown), dst) from exc
    except OSError as exc:
        # Pillow/img2pdf raise OSError without errno for truncated images.
        if exc.errno is not None:
            _remove_partial(dst)
            raise
        if shown.suffix.lower() in IMAGE_SUFFIXES:
            err = UserError(
                f"«{shown.name}» er skadet eller avkuttet og kan ikke leses som bilde. "
                "Prøv å hente filen på nytt."
            )
        else:
            err = _damaged(shown)
        raise _with_cleanup(err, dst) from exc
    except BaseException:
        _remove_partial(dst)
        raise
    finally:
        sys.stdout, sys.stderr = saved_streams
        _progress.callback = None
        logger.removeHandler(capture)
        logger.propagate = old_propagate
    return capture.messages


def _remove_partial(path: Path) -> bool:
    """Delete a half-written output. False if it exists and could not be deleted."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _with_cleanup(err: UserError, dst: Path) -> UserError:
    if not _remove_partial(dst):
        return UserError(
            f"{err} En halvferdig fil kunne ikke slettes og bør fjernes: «{dst}»."
        )
    return err


def _write_text(pdf: Path, out_dir: Path) -> Path:
    """All text (existing and OCR) from the new PDF, pages separated by form feed."""
    import pymupdf

    txt_path = safe_output_path(pdf, out_dir, ".txt")
    with pymupdf.open(pdf) as doc:
        pages = [page.get_text("text") for page in doc]
    txt_path.write_text("\f".join(pages), encoding="utf-8")
    return txt_path


def _base_temp_dir() -> Path:
    """A real (symlink-free) temp base that Leptonica can read files from.

    Leptonica (used by tesseract) rewrites paths starting with /tmp, so the
    /tmp fallback Python uses without TMPDIR breaks tesseract on macOS.
    """
    candidates: list[str] = []
    env = os.environ.get("TMPDIR")
    if env:
        candidates.append(env)
    try:
        candidates.append(os.confstr("CS_DARWIN_USER_TEMP_DIR"))  # type: ignore[arg-type]
    except (AttributeError, ValueError, OSError):
        pass
    candidates.append(tempfile.gettempdir())
    for cand in candidates:
        real = os.path.realpath(cand)
        if os.path.isdir(real) and os.access(real, os.W_OK):
            if real != "/private/tmp" and not real.startswith("/private/tmp/"):
                return Path(real)
    return Path(os.path.realpath(tempfile.gettempdir()))


@contextlib.contextmanager
def _work_dir() -> Iterator[Path]:
    """Private temp dir with a resolved path; TMPDIR points to it while active.

    The environment is restored and the directory removed afterwards, also on
    failure.
    """
    old_tempdir = tempfile.tempdir  # gettempdir() below may cache a value
    try:
        tmp = Path(
            os.path.realpath(tempfile.mkdtemp(prefix="jv-ocr-", dir=_base_temp_dir()))
        )
    except OSError as exc:
        raise OSError(
            "Kunne ikke lage en midlertidig mappe for OCR. Sjekk at disken "
            "ikke er full og at TMPDIR peker til en mappe du kan skrive til."
        ) from exc
    finally:
        tempfile.tempdir = old_tempdir
    old_env = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = str(tmp)
    tempfile.tempdir = str(tmp)
    try:
        yield tmp
    finally:
        tempfile.tempdir = old_tempdir
        if old_env is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old_env
        shutil.rmtree(tmp, ignore_errors=True)


def ocr_file(
    src: Path,
    out_dir: Path,
    *,
    text: bool = False,
    jobs: int | None = None,
    progress: ProgressFn | None = None,
) -> FileResult:
    """OCR one PDF or image into a new PDF in out_dir."""
    src = Path(src)
    out_dir = Path(out_dir)
    is_image = src.suffix.lower() in IMAGE_SUFFIXES
    dst = safe_output_path(src, out_dir, "-ocr.pdf")

    def report(fraction: float) -> None:
        if progress is not None:
            progress(min(1.0, max(0.0, fraction)))

    image_dpi = _image_dpi(src) if is_image else None
    with _work_dir() as tmp:
        ocr_input = src
        repaired = False
        if not is_image:
            copy = _repaired_copy(src, Path(tmp))
            if copy is not None:
                ocr_input, repaired = copy, True
        had_text = [False] if is_image else _pages_with_text(ocr_input)
        if not had_text:
            raise UserError(f"«{src.name}» har ingen sider.")

        # 0..0.8 is OCR, 0.8..1.0 is the confidence pass
        _run_ocrmypdf(
            ocr_input,
            dst,
            image_dpi=image_dpi,
            jobs=jobs,
            on_page=lambda f: report(0.8 * f),
            name=src.name,
        )
    report(0.8)

    pages = [PageResult(number=i + 1, ocr=not t) for i, t in enumerate(had_text)]
    ocr_list = [p for p in pages if p.ocr]
    for n, page in enumerate(ocr_list, start=1):
        page.confidence, page.words = page_confidence(dst, page.number - 1)
        report(0.8 + 0.2 * n / len(ocr_list))

    text_path = _write_text(dst, out_dir) if text else None
    report(1.0)
    return FileResult(
        source=src,
        output=dst,
        text_output=text_path,
        pages=pages,
        image_dpi_assumed=image_dpi,
        repaired=repaired,
    )


def ocr_many(
    files: list[Path],
    out_dir: Path,
    *,
    text: bool = False,
    jobs: int | None = None,
    progress: ProgressFn | None = None,
) -> list[FileResult]:
    """One job per file. progress gets the overall fraction."""
    results = []
    total = len(files)
    for i, file in enumerate(files):

        def per_file(fraction: float, i: int = i) -> None:
            if progress is not None:
                progress((i + fraction) / total)

        try:
            results.append(
                ocr_file(file, out_dir, text=text, jobs=jobs, progress=per_file)
            )
        except UserError as exc:
            if not results:
                raise
            done = ", ".join(f"«{r.output.name}»" for r in results)
            raise UserError(
                f"{exc} Disse filene ble ferdige før feilen og ligger i utmappen: {done}."
            ) from exc
    return results
