"""Independent check of a redacted PDF before it is handed to the user.

Any finding means no output file. Two kinds of checks:

1. The known redacted values are searched for (with and without spaces) in
   the page text from PyMuPDF and pdftotext (default and -layout), read with
   all layers on and without clipping to the page, and in metadata and all
   decoded strings of the file.
2. The detector itself (fødselsnummer/D-nummer with mod 11, phone, e-mail,
   terms) is run on ALL text in the output: the page text as above, every
   decoded string, name and comment in every PDF object and decompressed
   stream, and the raw text of non-content streams (XMP, attachments, ...).
   A detection that is not a hit the user struck from the plan is a finding.

Structure is checked as well: one revision only, no metadata, no outline,
no page labels, no external links, no annotations, form fields, embedded
files or layers.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .detect import (
    TEXT_FLAGS,
    TYPE_LABELS,
    collapse_ws,
    find_in_page,
    find_in_string,
    normalize_text,
    page_text,
    scan_text,
)
from .pdfstrings import text_pieces
from .prepare import EXTERNAL_LINK_KINDS, page_label_strings, working_copy


def norm_text(text: str) -> str:
    """NFKC, invisible characters removed, lower case, every whitespace run
    as one space."""
    return collapse_ws(normalize_text(text)).casefold()


def no_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _mask(t: str) -> str:
    if len(t) <= 4:
        return "*" * len(t)
    return t[:2] + "*" * (len(t) - 4) + t[-2:]


def label(type_: str, text: str) -> str:
    return f"{TYPE_LABELS.get(type_, type_)} «{_mask(text)}»"


@dataclass(frozen=True)
class Value:
    """One redacted value and the strings it is searched for as."""

    type: str
    text: str  # normalised with norm_text

    def variants(self) -> tuple[str, ...]:
        base = norm_text(self.text)
        out = [base, no_ws(base)]
        if self.type == "telefon":
            out.append(re.sub(r"\D", "", base)[-8:])
        if self.type in ("fodselsnummer", "d_nummer"):
            out.append(re.sub(r"\D", "", base))
        seen: list[str] = []
        for v in out:
            if v and v not in seen:
                seen.append(v)
        return tuple(seen)

    def label(self) -> str:
        return label(self.type, self.text)


def count_variant(text_norm: str, variant: str) -> int:
    """Occurrences of variant in normalised text; variants without spaces
    are also counted in the whitespace-free text."""
    if " " in variant:
        return text_norm.count(variant)
    n = max(text_norm.count(variant), no_ws(text_norm).count(variant))
    if variant.isdigit():
        # digits separated by hyphens, dots, slashes, dashes ...
        n = max(n, re.sub(r"[^\w+]", "", text_norm).count(variant))
    return n


# ---------------------------------------------------------------- extractors


def _which(name: str) -> str | None:
    return shutil.which(name)


def has_pdftotext() -> bool:
    return _which("pdftotext") is not None


def pdftotext_pages(pdf_path: Path, layout: bool) -> list[str]:
    exe = _which("pdftotext")
    assert exe is not None
    args = [exe, "-q", "-enc", "UTF-8"]
    if layout:
        args.append("-layout")
    args += [str(pdf_path), "-"]
    res = subprocess.run(args, capture_output=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(
            f"pdftotext feilet (kode {res.returncode}): "
            f"{res.stderr.decode('utf-8', 'replace').strip()}"
        )
    pages = res.stdout.decode("utf-8", "replace").split("\f")
    return pages


def extract_raw(doc: pymupdf.Document, pdf_bytes: bytes) -> dict[str, list[str]]:
    """Un-normalised page texts per extractor. doc and pdf_bytes must be a
    working copy (layers flattened, boxes widened)."""
    result = {
        "PyMuPDF": [
            page.get_text("text", flags=TEXT_FLAGS, clip=pymupdf.INFINITE_RECT()) for page in doc
        ]
    }
    if has_pdftotext():
        with tempfile.TemporaryDirectory(prefix="jv-redact-") as tmp:
            path = Path(tmp) / "kontroll.pdf"
            path.write_bytes(pdf_bytes)
            try:
                result["pdftotext"] = pdftotext_pages(path, layout=False)
                result["pdftotext -layout"] = pdftotext_pages(path, layout=True)
            finally:
                path.unlink(missing_ok=True)
    return result


def extract_all(doc: pymupdf.Document, pdf_bytes: bytes) -> dict[str, list[str]]:
    return {k: [norm_text(p) for p in v] for k, v in extract_raw(doc, pdf_bytes).items()}


# --------------------------------------------------------------- raw strings

_REF = re.compile(r"(\d+)\s+0\s+R")
_UNSCANNED_FILTERS = ("/DCTDecode", "/JPXDecode", "/JBIG2Decode", "/CCITTFaxDecode")
_COMPONENTS = {
    "/DeviceGray": 1, "/CalGray": 1, "/G": 1, "/DeviceRGB": 3, "/CalRGB": 3,
    "/RGB": 3, "/Lab": 3, "/DeviceCMYK": 4, "/CMYK": 4,
}


def _key(doc: pymupdf.Document, xref: int, key: str) -> tuple[str, str]:
    try:
        return doc.xref_get_key(xref, key)
    except Exception:  # noqa: BLE001
        return ("null", "null")


def _val(doc: pymupdf.Document, xref: int, key: str) -> str:
    kind, value = _key(doc, xref, key)
    return "" if kind == "null" else value


def _ref(value: str) -> int | None:
    m = _REF.match(value.strip())
    return int(m.group(1)) if m else None


def _dict_after(src: str, key: str) -> list[str]:
    """Bodies of the dictionaries that follow /key in src (inline only)."""
    out = []
    for m in re.finditer(rf"/{key}\s*<<", src):
        depth, i = 1, m.end()
        while i < len(src) and depth:
            if src.startswith("<<", i):
                depth += 1
                i += 2
            elif src.startswith(">>", i):
                depth -= 1
                i += 2
            else:
                i += 1
        out.append(src[m.end(): i - 2])
    return out


def _referenced(doc: pymupdf.Document, sources: dict[int, str], key: str) -> set[int]:
    """xrefs that some object refers to as /key N 0 R."""
    out: set[int] = set()
    pat = re.compile(rf"/{key}\s+(\d+)\s+0\s+R")
    for src in sources.values():
        out.update(int(m.group(1)) for m in pat.finditer(src))
    return out


def _xobject_refs(doc: pymupdf.Document, sources: dict[int, str]) -> set[int]:
    """xrefs listed in /XObject resource dictionaries (inline or indirect)."""
    out: set[int] = set()
    for src in sources.values():
        bodies = _dict_after(src, "XObject")
        for m in re.finditer(r"/XObject\s+(\d+)\s+0\s+R", src):
            bodies.append(sources.get(int(m.group(1)), ""))
        for body in bodies:
            out.update(int(r) for r in _REF.findall(body))
    return out


def _components(doc: pymupdf.Document, xref: int) -> set[int]:
    kind, cs = _key(doc, xref, "ColorSpace")
    if kind == "null":
        return {1, 3, 4}
    if kind == "xref":
        r = _ref(cs)
        cs = doc.xref_object(r, compressed=True) if r else cs
    cs = cs.strip()
    for name, n in _COMPONENTS.items():
        if cs == name or cs.startswith("[" + name) or cs.startswith("[ " + name):
            return {n}
    if "/Indexed" in cs or "/Separation" in cs:
        return {1}
    m = re.search(r"/ICCBased\s+(\d+)\s+0\s+R", cs)
    if m:
        n = _val(doc, int(m.group(1)), "N")
        if n.isdigit():
            return {int(n)}
    return {1, 3, 4}


def _is_real_image(doc: pymupdf.Document, xref: int) -> bool:
    """A referenced image stream whose data looks like image data."""
    if _val(doc, xref, "Subtype") != "/Image":
        return False
    filters = _val(doc, xref, "Filter")
    if any(f in filters for f in _UNSCANNED_FILTERS):
        return True
    try:
        w = int(float(_val(doc, xref, "Width")))
        h = int(float(_val(doc, xref, "Height")))
        data = doc.xref_stream(xref) or b""
    except Exception:  # noqa: BLE001
        return False
    if _val(doc, xref, "ImageMask") == "true":
        bpc, comps = 1, {1}
    else:
        bpc_s = _val(doc, xref, "BitsPerComponent")
        bpc = int(bpc_s) if bpc_s.isdigit() else 8
        comps = _components(doc, xref)
    return any(len(data) == ((w * bpc * n + 7) // 8) * h for n in comps)


def _is_real_font(doc: pymupdf.Document, xref: int) -> bool:
    try:
        data = doc.xref_stream(xref) or b""
    except Exception:  # noqa: BLE001
        return False
    head = data[:16]
    if head.startswith((b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf", b"%!")):
        return True
    # bare CFF (FontFile3 /Type1C or /CIDFontType0C): major version 1, header size 4
    return len(head) >= 4 and head[0] == 1 and head[2] == 4


def _classify(doc: pymupdf.Document) -> tuple[set[int], set[int], set[int], set[int]]:
    """(skip, cmap, content, streams) xref sets.

    skip: images and font programs that are both referenced as such and
    look like what they claim to be. Everything else is scanned.
    """
    sources: dict[int, str] = {}
    for xref in range(1, doc.xref_length()):
        try:
            sources[xref] = doc.xref_object(xref, compressed=True)
        except Exception:  # noqa: BLE001
            continue
    streams = {x for x in sources if _safe_is_stream(doc, x)}

    images = {x for x in _xobject_refs(doc, sources) if x in streams}
    smasks = _referenced(doc, sources, "SMask") | _referenced(doc, sources, "Mask")
    skip = {x for x in images | (smasks & streams) if _is_real_image(doc, x)}

    descriptors = {x for x, src in sources.items() if "/FontDescriptor" in src}
    fontfiles: set[int] = set()
    for x in descriptors:
        for key in ("FontFile", "FontFile2", "FontFile3"):
            r = _ref(_val(doc, x, key))
            if r and r in streams:
                fontfiles.add(r)
    skip |= {x for x in fontfiles if _is_real_font(doc, x)}

    cmaps = (_referenced(doc, sources, "ToUnicode") & streams) | {
        x for x in streams if _val(doc, x, "Type") == "/CMap"
    }
    content: set[int] = set()
    for page in doc:
        content.update(page.get_contents())
    for x in streams:
        if _val(doc, x, "Subtype") == "/Form" or _val(doc, x, "PatternType"):
            content.add(x)
    for src in sources.values():
        for body in _dict_after(src, "CharProcs"):
            content.update(int(r) for r in _REF.findall(body))
    return skip, cmaps - skip, content - skip, streams


def _safe_is_stream(doc: pymupdf.Document, xref: int) -> bool:
    try:
        return bool(doc.xref_is_stream(xref))
    except Exception:  # noqa: BLE001
        return False


def _cmap_texts(data: bytes) -> list[str]:
    """A CMap read structurally: every hex string on its own, decoded as
    UTF-16BE (that is what bfchar/bfrange targets are), and the rest of the
    stream without the hex strings."""
    out: list[str] = []
    for m in re.finditer(rb"<([0-9A-Fa-f\s]*)>", data):
        digits = re.sub(rb"\s", b"", m.group(1))
        if len(digits) % 4 == 0 and digits:
            out.append(bytes.fromhex(digits.decode()).decode("utf-16-be", "replace"))
    out.append(re.sub(rb"<[0-9A-Fa-f\s]*>", b" ", data).decode("latin-1"))
    return out


def raw_texts(doc: pymupdf.Document) -> list[tuple[str, str, int]]:
    """(where, text, xref) for all decoded strings in the file."""
    out: list[tuple[str, str, int]] = []
    skip, cmaps, content, streams = _classify(doc)
    try:
        trailer = doc.pdf_trailer(compressed=True)
        out.append(("trailer", "\n".join(text_pieces(trailer.encode("utf-8", "replace"))), 0))
    except Exception:  # noqa: BLE001
        pass
    for xref in range(1, doc.xref_length()):
        try:
            src = doc.xref_object(xref, compressed=True)
        except Exception:  # noqa: BLE001 - free or broken entry
            continue
        out.append((f"PDF-objekt {xref}", "\n".join(text_pieces(src.encode("utf-8", "replace"))), xref))
        if xref not in streams or xref in skip or _val(doc, xref, "Type") == "/XRef":
            continue
        try:
            data = doc.xref_stream(xref) or b""
        except Exception:  # noqa: BLE001 - undecodable filter: look at raw bytes
            try:
                data = doc.xref_stream_raw(xref) or b""
            except Exception:  # noqa: BLE001
                data = b""
        where = f"strøm i PDF-objekt {xref}"
        if xref in cmaps:
            out.extend((where, t, xref) for t in _cmap_texts(data))
            continue
        is_content = xref in content
        if is_content:
            # one text object at a time: a string operand or a whole TJ
            # array (large adjustments read as spaces), never joined with
            # the next one, so separate table cells never form a number
            out.extend((where, piece, xref) for piece in text_pieces(data, content=True))
            continue
        out.append((where, "\n".join(text_pieces(data)), xref))
        for enc in ("utf-8", "utf-16-be", "utf-16-le", "latin-1"):
            try:
                out.append((where, data.decode(enc), xref))
                if enc == "utf-8":
                    break
            except UnicodeDecodeError:
                continue
    return out


def content_object_values(doc: pymupdf.Document, terms: Sequence[str]) -> set[tuple[str, str]]:
    """(type, normalized) of every detection inside one text object (string
    operand or TJ array) of any content stream."""
    _skip, _cmaps, content, _streams = _classify(doc)
    out: set[tuple[str, str]] = set()
    for xref in sorted(content):
        try:
            data = doc.xref_stream(xref) or b""
        except Exception:  # noqa: BLE001
            continue
        for piece in text_pieces(data, content=True):
            for typ, _t, normalized, _e in find_in_string(piece, terms):
                out.add((typ, normalized))
    return out


# ------------------------------------------------------------------- checks


@dataclass(frozen=True)
class Kept:
    """A hit the user struck from the plan: it may stay."""

    type: str
    normalized: str
    page: int | None


@dataclass(frozen=True)
class RejectedLeft:
    """A rejected candidate the user left unredacted: its digit groups as
    word boxes (working-copy page coordinates)."""

    type: str
    normalized: str
    page: int
    rects: tuple[tuple[float, float, float, float], ...]


_BBOX_WORD = re.compile(
    r'<word xMin="([\d.\-]+)" yMin="([\d.\-]+)" xMax="([\d.\-]+)" yMax="([\d.\-]+)">(.*?)</word>'
)
BOX_TOLERANCE = 1.5


def pdftotext_words(pdf_path: Path) -> list[list[tuple[str, tuple[float, float, float, float] | None]]]:
    """Per page: the words from `pdftotext -bbox-layout`, in reading order,
    with their boxes; line ends as ("\n", None)."""
    import html

    exe = _which("pdftotext")
    assert exe is not None
    res = subprocess.run([exe, "-q", "-bbox-layout", str(pdf_path), "-"], capture_output=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"pdftotext -bbox-layout feilet (kode {res.returncode})")
    out = []
    for page in res.stdout.decode("utf-8", "replace").split("<page ")[1:]:
        words: list[tuple[str, tuple[float, float, float, float] | None]] = []
        for line in page.split("</line>"):
            for m in _BBOX_WORD.finditer(line):
                box = tuple(float(m.group(i)) for i in range(1, 5))
                words.append((html.unescape(m.group(5)), box))
            words.append(("\n", None))
        out.append(words)
    return out


def _bbox_detections(words, terms) -> list[tuple[str, str, list[tuple[float, float, float, float]]]]:
    """Detections in a page of bbox words: (type, normalized, word boxes)."""
    text = ""
    spans: list[tuple[int, int, tuple[float, float, float, float]]] = []
    for w, box in words:
        if box is None:
            text += "\n"
            continue
        if text and not text.endswith("\n"):
            text += " "
        start = len(text)
        text += w
        spans.append((start, len(text), box))
    out = []
    norm = normalize_text(text)
    if norm != text:
        text = norm  # positions may shift; fall back to no boxes
        spans = []
    for sp in scan_text(text, terms):
        boxes = [b for a, e, b in spans if a < sp.end and sp.start < e]
        out.append((sp.type, sp.normalized, boxes))
    return out


def _same_box(a, b) -> bool:
    """Same word box: left and right edges within a small tolerance, and
    clearly overlapping vertically (PyMuPDF and pdftotext use different
    glyph heights, so the top and bottom are not compared exactly)."""
    if abs(a[0] - b[0]) > BOX_TOLERANCE or abs(a[2] - b[2]) > BOX_TOLERANCE:
        return False
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    return overlap >= 0.5 * min(a[3] - a[1], b[3] - b[1])


def _matches_rejected(boxes, candidates: list[RejectedLeft]) -> RejectedLeft | None:
    """The rejected candidate whose digit-group boxes are exactly these
    word boxes (each within a small tolerance), if any."""
    if not boxes:
        return None
    for cand in candidates:
        if len(cand.rects) != len(boxes):
            continue
        free = list(cand.rects)
        ok = True
        for b in boxes:
            hit = next((r for r in free if _same_box(b, r)), None)
            if hit is None:
                ok = False
                break
            free.remove(hit)
        if ok:
            return cand
    return None


def verify(
    pdf_bytes: bytes,
    before: dict[str, list[str]],
    redacted: Sequence[tuple[Value, int]],
    fully_redacted: set[Value],
    kept: Iterable[Kept] = (),
    terms: Sequence[str] = (),
    rejected: Iterable[RejectedLeft] = (),
) -> tuple[list[str], list[str]]:
    """Return (findings, warnings) for the finished PDF bytes.

    before: normalised page texts of the source working copy per extractor.
    redacted: (value, 1-based page) for every redacted page occurrence.
    fully_redacted: values with no kept occurrence anywhere.
    kept: struck page hits; the detector may find these again, nothing else.
    rejected: number candidates that finn did not count because the digit
    groups are far apart on the page (table cells), and that the user left
    unredacted. pdftotext joins such cells, so a detection in its page text
    is accepted only when pdftotext's own word boxes (-bbox-layout) are
    exactly the digit-group boxes of a rejected candidate. Raw strings and
    content streams are scanned per text object (string or TJ array), where
    separate cells never form a number; there rejected values are never
    accepted.
    """
    findings: list[str] = []
    warnings: list[str] = []
    kept = list(kept)
    kept_per_page = Counter((k.type, k.normalized, k.page) for k in kept)
    kept_values = {(k.type, k.normalized) for k in kept}
    rejected = list(rejected)

    if pdf_bytes.count(b"%%EOF") != 1 or pdf_bytes.count(b"startxref") != 1:
        findings.append(
            "Filen har mer enn én revisjon (inkrementell lagring), så eldre "
            "versjoner kan ligge igjen"
        )

    # ---- page text, all layers on, no clipping
    work = working_copy(pdf_bytes, flatten_layers=True)
    try:
        view = work.doc
        raw_pages = extract_raw(view, view.tobytes(garbage=0))
        after = {k: [norm_text(p) for p in v] for k, v in raw_pages.items()}
        if "pdftotext" not in after:
            warnings.append(
                "pdftotext er ikke installert, så etterkontrollen brukte bare "
                "PyMuPDF (brew install poppler)."
            )
        # rejected candidates are accepted in pdftotext's text only where the
        # digit groups are exactly the words in the rejected boxes
        verified: Counter = Counter()
        if rejected and has_pdftotext():
            with tempfile.TemporaryDirectory(prefix="jv-redact-") as tmp:
                path = Path(tmp) / "kontroll.pdf"
                path.write_bytes(view.tobytes(garbage=0))
                try:
                    pages_words = pdftotext_words(path)
                finally:
                    path.unlink(missing_ok=True)
            for i, words in enumerate(pages_words):
                free = [r for r in rejected if r.page == i + 1]
                for typ, normalized, boxes in _bbox_detections(words, terms):
                    cand = _matches_rejected(boxes, [c for c in free
                                                     if (c.type, c.normalized) == (typ, normalized)])
                    if cand is not None:
                        free.remove(cand)
                        verified[(typ, normalized, i + 1)] += 1
        detected: dict[str, list[Counter]] = {
            "PyMuPDF": [
                Counter((h.type, h.normalized, i + 1) for h in find_in_page(page_text(p), i + 1, terms))
                for i, p in enumerate(view)
            ]
        }
        for name, pages in raw_pages.items():
            if name == "PyMuPDF":
                continue
            detected[name] = [
                Counter((t, n, i + 1) for t, _x, n, _e in find_in_string(txt, terms))
                for i, txt in enumerate(pages)
            ]

    finally:
        work.doc.close()

    redacted_per_page: Counter = Counter((v, p) for v, p in redacted)
    values = sorted({v for v, _ in redacted}, key=lambda v: (v.type, v.text))

    for name, pages in after.items():
        before_pages = before.get(name)
        for value in values:
            done = False
            for variant in value.variants():
                for idx, page_txt in enumerate(pages):
                    page_no = idx + 1
                    n_after = count_variant(page_txt, variant)
                    if not n_after:
                        continue
                    if value in fully_redacted:
                        allowed = 0
                    else:
                        n_before = 0
                        if before_pages is not None and idx < len(before_pages):
                            n_before = count_variant(before_pages[idx], variant)
                        allowed = max(0, n_before - redacted_per_page[(value, page_no)])
                    if n_after > allowed:
                        findings.append(
                            f"{value.label()} finnes fortsatt i teksten fra {name} på side {page_no}"
                        )
                        done = True
                        break
                if done:
                    break

    for name, per_page in detected.items():
        for idx, counter in enumerate(per_page):
            for (typ, normalized, page_no), n in counter.items():
                key = (typ, normalized, page_no)
                allowed = kept_per_page[key]
                if name != "PyMuPDF":
                    # only rejected candidates verified by position (bbox)
                    allowed += verified[key]
                if n > allowed:
                    findings.append(
                        f"Gjenkjenningen finner {label(typ, normalized)} i teksten fra "
                        f"{name} på side {page_no}, og treffet er ikke strøket i planen"
                    )

    # ---- structure and metadata of the real output
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        meta = doc.metadata or {}
        meta_txt = " ".join(
            str(v) for k, v in meta.items() if k not in ("format", "encryption") and v
        )
        if meta_txt.strip():
            findings.append("Metadata (Info-ordboken) er ikke tomme")
        if (doc.get_xml_metadata() or "").strip():
            findings.append("XMP-metadata er ikke fjernet")
        if doc.get_toc(simple=True):
            findings.append("Dokumentet har fortsatt bokmerker")
        if page_label_strings(doc) or doc.xref_get_key(doc.pdf_catalog(), "PageLabels")[0] != "null":
            findings.append("Dokumentet har fortsatt sidelabels")
        if doc.xref_get_key(doc.pdf_catalog(), "OCProperties")[0] != "null":
            findings.append("Dokumentet har fortsatt innholdslag (OCG)")
        for page in doc:
            if page.first_annot is not None:
                findings.append(f"Side {page.number + 1} har fortsatt kommentarer/annotasjoner")
            if page.first_widget is not None:
                findings.append(f"Side {page.number + 1} har fortsatt skjemafelt")
            if any(link.get("kind") in EXTERNAL_LINK_KINDS for link in page.get_links()):
                findings.append(f"Side {page.number + 1} har fortsatt lenker til adresser eller filer")
        if doc.is_form_pdf:
            findings.append("Dokumentet har fortsatt et skjema (AcroForm)")
        if doc.embfile_count():
            findings.append("Dokumentet har fortsatt innebygde filer")

        # ---- every decoded string in the file
        for where, text, xref in raw_texts(doc):
            if not text:
                continue
            text_norm = norm_text(text)
            for value in fully_redacted:
                if any(count_variant(text_norm, v) for v in value.variants()):
                    findings.append(f"{value.label()} finnes i {where}")
            for typ, _shown, normalized, _e in find_in_string(text, terms):
                if (typ, normalized) in kept_values:
                    continue  # struck by the user; rejected candidates never count here
                findings.append(
                    f"Gjenkjenningen finner {label(typ, normalized)} i {where}, "
                    "og treffet er ikke strøket i planen"
                )
    finally:
        doc.close()

    seen: set[str] = set()
    unique = [f for f in findings if not (f in seen or seen.add(f))]
    return unique, warnings
