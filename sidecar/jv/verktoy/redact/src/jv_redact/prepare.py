"""Working copies of a PDF in which nothing is hidden from text extraction.

- optional content (layers) is flattened: /OCProperties is removed, so text
  in layers that are switched off becomes visible to PyMuPDF and pdftotext
- comments and form fields are baked into the page content
- every page's MediaBox/CropBox is widened by MARGIN points on all sides, so
  text placed outside the visible page is extracted (and can be redacted);
  the original boxes are kept so they can be put back before saving
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

MARGIN = 10000.0

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)"


@dataclass
class Working:
    doc: pymupdf.Document
    had_layers: bool
    # per page index: (own MediaBox, own CropBox) as raw PDF values or "null"
    original_boxes: list[tuple[str, str]] = field(default_factory=list)
    # per page index: the originally visible area in working-copy coordinates
    visible: list[pymupdf.Rect] = field(default_factory=list)


def _parse_box(value: str) -> list[float] | None:
    nums = re.findall(_NUM, value or "")
    if len(nums) != 4:
        return None
    x0, y0, x1, y1 = (float(n) for n in nums)
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _resolve(doc: pymupdf.Document, kind: str, value: str) -> str:
    """Resolve an indirect reference ("12 0 R") to the object source."""
    if kind == "xref":
        m = re.match(r"\s*(\d+)\s+\d+\s+R", value)
        if m:
            return doc.xref_object(int(m.group(1)), compressed=True)
    return value


def _inherited_box(doc: pymupdf.Document, xref: int, key: str) -> list[float] | None:
    seen: set[int] = set()
    while xref and xref not in seen:
        seen.add(xref)
        kind, value = doc.xref_get_key(xref, key)
        if kind != "null":
            box = _parse_box(_resolve(doc, kind, value))
            if box:
                return box
        kind, parent = doc.xref_get_key(xref, "Parent")
        m = re.match(r"\s*(\d+)\s+\d+\s+R", parent or "")
        xref = int(m.group(1)) if kind == "xref" and m else 0
    return None


def _catalog_has(doc: pymupdf.Document, key: str) -> bool:
    return doc.xref_get_key(doc.pdf_catalog(), key)[0] != "null"


def remove_catalog_key(doc: pymupdf.Document, key: str) -> None:
    cat = doc.pdf_catalog()
    if doc.xref_get_key(cat, key)[0] != "null":
        doc.xref_set_key(cat, key, "null")


def working_copy(data: bytes, flatten_layers: bool = True) -> Working:
    """Open data as a working copy. The caller closes Working.doc."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        had_layers = _catalog_has(doc, "OCProperties")
        if flatten_layers:
            remove_catalog_key(doc, "OCProperties")
        doc.bake(annots=True, widgets=True)
        boxes: list[tuple[str, str]] = []
        orig_visible: list[list[float]] = []
        for page in doc:
            own_mb = doc.xref_get_key(page.xref, "MediaBox")
            own_cb = doc.xref_get_key(page.xref, "CropBox")
            boxes.append(
                (
                    own_mb[1] if own_mb[0] != "null" else "null",
                    own_cb[1] if own_cb[0] != "null" else "null",
                )
            )
            mb = _inherited_box(doc, page.xref, "MediaBox") or [0, 0, 612, 792]
            cb = _inherited_box(doc, page.xref, "CropBox") or mb
            orig_visible.append(cb)
            big = f"[{mb[0] - MARGIN:g} {mb[1] - MARGIN:g} {mb[2] + MARGIN:g} {mb[3] + MARGIN:g}]"
            doc.xref_set_key(page.xref, "MediaBox", big)
            doc.xref_set_key(page.xref, "CropBox", big)
        out = doc.tobytes(garbage=0)
    finally:
        doc.close()
    work = pymupdf.open(stream=out, filetype="pdf")
    visible = []
    for page, box in zip(work, orig_visible):
        # PDF coordinates -> unrotated page coordinates (y down, origin at the
        # top-left of the widened MediaBox) -> rotated page coordinates
        mb = _inherited_box(work, page.xref, "MediaBox") or [0, 0, 612, 792]
        unrotated = pymupdf.Rect(box[0] - mb[0], mb[3] - box[3], box[2] - mb[0], mb[3] - box[1])
        visible.append(unrotated * page.rotation_matrix)
    return Working(work, had_layers, boxes, visible)


def restore_boxes(doc: pymupdf.Document, boxes: list[tuple[str, str]]) -> None:
    for page, (mb, cb) in zip(doc, boxes):
        doc.xref_set_key(page.xref, "MediaBox", mb)
        doc.xref_set_key(page.xref, "CropBox", cb)


def page_label_strings(doc: pymupdf.Document) -> list[tuple[int, str]]:
    out = []
    try:
        rules = doc.get_page_labels() or []
    except Exception:  # noqa: BLE001 - broken /PageLabels: raw scan covers it
        rules = []
    for rule in rules:
        prefix = str(rule.get("prefix") or "")
        if prefix:
            out.append((int(rule.get("startpage", 0)) + 1, prefix))
    return out


EXTERNAL_LINK_KINDS = {pymupdf.LINK_URI, pymupdf.LINK_LAUNCH, pymupdf.LINK_GOTOR}


def link_strings(doc: pymupdf.Document) -> list[tuple[int, str]]:
    from urllib.parse import unquote

    out = []
    for page in doc:
        for link in page.get_links():
            for key in ("uri", "file"):
                v = link.get(key)
                if v:
                    v = str(v)
                    out.append((page.number + 1, v))
                    if unquote(v) != v:
                        out.append((page.number + 1, unquote(v)))
    return out
