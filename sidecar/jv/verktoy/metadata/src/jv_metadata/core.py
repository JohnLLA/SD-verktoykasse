"""Read and remove metadata from images, PDF and Office files.

Images (JPEG, PNG, HEIC) go through exiftool. PDF goes through pikepdf.
Office files (DOCX, XLSX, PPTX) are read and rewritten with zipfile and
ElementTree, because exiftool on some systems lacks Archive::Zip.

Orientation policy for images: the Orientation tag is kept (copied back
after "exiftool -all="). Pixels are never re-encoded, so cleaning is
lossless and the image is shown the same way as before.
"""

from __future__ import annotations

import io
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jv_common import UserError, require_binary, safe_output_path

GROUPS = ("Sted", "Person", "Utstyr", "Tid", "Annet")
SENSITIVE_GROUPS = frozenset({"Sted", "Person"})

# extension -> kind
SUPPORTED: dict[str, str] = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".heic": "image",
    ".heif": "image",
    ".pdf": "pdf",
    ".docx": "office",
    ".xlsx": "office",
    ".pptx": "office",
}

_FORMAT_LABEL = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".heic": "HEIC",
    ".heif": "HEIC",
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".xlsx": "XLSX",
    ".pptx": "PPTX",
}

# --- classification -------------------------------------------------------

_PLACE = {
    "location",
    "locationcreated",
    "locationshown",
    "city",
    "country",
    "countrycode",
    "country-primarylocationname",
    "country-primarylocationcode",
    "state",
    "province-state",
    "sublocation",
}
_PERSON = {
    "artist",
    "author",
    "authorsposition",
    "by-line",
    "by-linetitle",
    "cameraownername",
    "captionwriter",
    "company",
    "copyright",
    "copyrightnotice",
    "creator",
    "credit",
    "lastmodifiedby",
    "manager",
    "ownername",
    "rights",
    "writer-editor",
    "xpauthor",
}
_EQUIPMENT = {
    "application",
    "appversion",
    "bodyserialnumber",
    "creatortool",
    "hostcomputer",
    "internalserialnumber",
    "lensid",
    "lensinfo",
    "lensmake",
    "lensmodel",
    "lensserialnumber",
    "localizedcameramodel",
    "make",
    "model",
    "producer",
    "serialnumber",
    "software",
    "template",
    "uniquecameramodel",
}
_TIME = {"created", "modified", "lastprinted"}
_NOT_TIME = {"exposuretime"}


def classify(name: str) -> str:
    """Map a field name (without namespace/group) to one of GROUPS."""
    n = name.lower()
    if n.startswith("gps") or n in _PLACE:
        return "Sted"
    if n in _PERSON:
        return "Person"
    if n in _EQUIPMENT:
        return "Utstyr"
    if n in _TIME or (n not in _NOT_TIME and ("date" in n or "time" in n)):
        return "Tid"
    return "Annet"


@dataclass(frozen=True)
class Field:
    source: str
    name: str
    value: str
    group: str

    @property
    def sensitive(self) -> bool:
        return self.group in SENSITIVE_GROUPS

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.name,
            "source": self.source,
            "value": self.value,
            "group": self.group,
            "sensitive": self.sensitive,
        }


def _field(source: str, name: str, value: Any, group: str | None = None) -> Field:
    return Field(source, name, _as_text(value), group or classify(name))


def _as_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def group_fields(fields: list[Field]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
    for f in fields:
        grouped[f.group].append(f.to_dict())
    return grouped


# --- input handling -------------------------------------------------------


def collect_inputs(paths: list[str]) -> tuple[list[Path], list[str]]:
    """Expand folders (not recursively) and check that all files exist.

    Returns (files, warnings). Unsupported files inside a folder are
    skipped with a warning; an unsupported file named directly is an error.
    """
    files: list[Path] = []
    warnings: list[str] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            raise UserError(f"Filen «{raw}» finnes ikke.")
        if p.is_dir():
            found = []
            for child in sorted(p.iterdir()):
                if not child.is_file() or child.name.startswith("."):
                    continue
                if child.suffix.lower() in SUPPORTED:
                    found.append(child)
                else:
                    warnings.append(f"Hoppet over «{child.name}»: filtypen støttes ikke.")
            if not found:
                raise UserError(f"Mappen «{raw}» inneholder ingen filer som støttes.")
            files.extend(found)
        else:
            files.append(p)
    for f in files:
        detect_kind(f)
    return files, warnings


def detect_kind(path: Path) -> str:
    """Return "image", "pdf" or "office", or raise a Norwegian UserError."""
    if not path.is_file():
        raise UserError(f"Filen «{path}» finnes ikke.")
    ext = path.suffix.lower()
    kind = SUPPORTED.get(ext)
    if kind is None:
        supported = ", ".join(sorted({_FORMAT_LABEL[e] for e in SUPPORTED}))
        raise UserError(
            f"Filtypen til «{path.name}» støttes ikke. Støttet: {supported}."
        )
    if path.stat().st_size == 0:
        raise UserError(f"Filen «{path.name}» er tom.")
    with open(path, "rb") as handle:
        head = handle.read(1024)
    label = _FORMAT_LABEL[ext]
    if kind == "office" and head.startswith(b"\xd0\xcf\x11\xe0"):
        raise UserError(
            f"«{path.name}» er passordbeskyttet eller i gammelt Office-format, "
            "og kan ikke behandles."
        )
    ok = {
        "JPEG": head.startswith(b"\xff\xd8\xff"),
        "PNG": head.startswith(b"\x89PNG\r\n\x1a\n"),
        "HEIC": head[4:8] == b"ftyp",
        "PDF": b"%PDF-" in head,
    }.get(label, head.startswith(b"PK\x03\x04"))
    if not ok:
        raise UserError(
            f"«{path.name}» ser ikke ut til å være en gyldig {label}-fil."
        )
    return kind


# --- images (exiftool) ----------------------------------------------------

_SKIP_EXIF_GROUPS = {"ExifTool", "System", "File", "Composite"}


def _exiftool(args: list[str], path: Path) -> list[tuple[str, Any]]:
    exe = require_binary("exiftool")
    proc = subprocess.run(
        [exe, "-j", *args, str(path.resolve())],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        data = json.loads(proc.stdout, object_pairs_hook=list)
        pairs = data[0]
    except (ValueError, IndexError, TypeError):
        detail = proc.stderr.strip() or "ukjent feil"
        raise UserError(f"exiftool kunne ikke lese «{path.name}»: {detail}") from None
    for key, value in pairs:
        if key.split(":")[-1] == "Error":
            raise UserError(f"exiftool kunne ikke lese «{path.name}»: {value}")
    return pairs


def _image_fields(path: Path) -> list[Field]:
    fields = []
    for key, value in _exiftool(["-G1", "-a", "-s"], path):
        if key == "SourceFile":
            continue
        group, _, tag = key.partition(":")
        if not tag or group in _SKIP_EXIF_GROUPS:
            continue
        fields.append(_field(group, tag, value))
    return fields


def image_orientation(path: Path) -> int | None:
    """EXIF orientation as a number (1-8), or None when not set."""
    for key, value in _exiftool(["-n", "-Orientation"], path):
        if key.split(":")[-1] == "Orientation":
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _clean_image(src: Path, out: Path) -> None:
    exe = require_binary("exiftool")
    proc = subprocess.run(
        [
            exe,
            "-q",
            "-m",
            "-all=",
            "-tagsFromFile",
            "@",
            "-Orientation",
            "-o",
            str(out.resolve()),
            str(src.resolve()),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0 or not out.exists():
        _unlink(out)
        detail = proc.stderr.strip() or "ukjent feil"
        raise UserError(f"exiftool kunne ikke vaske «{src.name}»: {detail}")


# --- PDF (pikepdf) --------------------------------------------------------

_XMP_PREFIX = {
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/pdf/1.3/": "pdf",
    "http://ns.adobe.com/xap/1.0/mm/": "xmpMM",
    "http://ns.adobe.com/xap/1.0/rights/": "xmpRights",
    "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://ns.adobe.com/pdfx/1.3/": "pdfx",
    "http://ns.adobe.com/tiff/1.0/": "tiff",
    "http://ns.adobe.com/exif/1.0/": "exif",
    "http://www.aiim.org/pdfa/ns/id/": "pdfaid",
    "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/": "Iptc4xmpCore",
}


def _open_pdf(path: Path):
    import pikepdf

    try:
        return pikepdf.open(path)
    except pikepdf.PasswordError:
        raise UserError(f"PDF-en «{path.name}» er passordbeskyttet.") from None
    except pikepdf.PdfError as exc:
        raise UserError(f"PDF-en «{path.name}» kan ikke leses: {exc}") from None


def _qname(key: str) -> str:
    if key.startswith("{"):
        uri, _, local = key[1:].partition("}")
        prefix = _XMP_PREFIX.get(uri)
        return f"{prefix}:{local}" if prefix else local
    return key


def _pdf_fields(path: Path) -> tuple[list[Field], list[str]]:
    import pikepdf

    fields: list[Field] = []
    notes: list[str] = []
    with _open_pdf(path) as pdf:
        info = pdf.trailer.get("/Info")
        if isinstance(info, pikepdf.Dictionary):
            for key, value in info.items():
                name = str(key).lstrip("/")
                # /Creator in the Info dictionary is the authoring program
                group = "Utstyr" if name == "Creator" else None
                fields.append(_field("PDF Info", name, _pdf_value(value), group))
        if "/Metadata" in pdf.Root:
            try:
                meta = pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False)
                for key in list(meta):
                    qn = _qname(str(key))
                    value = meta.get(key)
                    if value in (None, "", [], set()):
                        continue
                    fields.append(_field("XMP", qn, value, classify(qn.split(":")[-1])))
            except Exception as exc:  # noqa: BLE001 - malformed XMP is common
                notes.append(f"XMP-metadataene i «{path.name}» kunne ikke tolkes: {exc}")
                fields.append(_field("XMP", "XMP", "kan ikke tolkes", "Annet"))
        extra = _other_xmp_count(pdf)
        if extra:
            fields.append(
                _field("PDF", "XMP i sider eller bilder", f"{extra} stk", "Annet")
            )
    return fields, notes


def _other_xmp_count(pdf) -> int:
    import pikepdf

    root_objgen = pdf.Root.objgen
    count = 0
    for obj in pdf.objects:
        if isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)) and "/Metadata" in obj:
            if obj.objgen != root_objgen:
                count += 1
    return count


def _pdf_value(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return repr(value)


def _clean_pdf(src: Path, out: Path) -> bool:
    """Clean a PDF. Returns True if the original was encrypted (owner password only)."""
    import pikepdf

    with _open_pdf(src) as pdf:
        was_encrypted = bool(pdf.is_encrypted)
        if "/Info" in pdf.trailer:
            del pdf.trailer["/Info"]
        for obj in pdf.objects:
            if isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)) and "/Metadata" in obj:
                del obj["/Metadata"]
        if "/Metadata" in pdf.Root:
            del pdf.Root["/Metadata"]
        try:
            pdf.save(out)
        except Exception as exc:  # noqa: BLE001
            _unlink(out)
            raise UserError(f"Kunne ikke lagre vasket PDF for «{src.name}»: {exc}") from None
    return was_encrypted


# --- Office (zipfile + XML) -----------------------------------------------

_CORE = "docProps/core.xml"
_APP = "docProps/app.xml"
_CUSTOM = "docProps/custom.xml"


def _open_zip(path: Path) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise UserError(f"«{path.name}» er ikke et gyldig Office-dokument.") from None
    if "[Content_Types].xml" not in z.namelist():
        z.close()
        raise UserError(f"«{path.name}» er ikke et gyldig Office-dokument.")
    return z


def _parse_xml(data: bytes, path: Path, part: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise UserError(f"Kunne ikke lese {part} i «{path.name}»: {exc}") from None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_text(el: ET.Element) -> str:
    return " ".join(t.strip() for t in el.itertext() if t.strip())


def _office_fields(path: Path) -> list[Field]:
    fields: list[Field] = []
    with _open_zip(path) as z:
        names = set(z.namelist())
        for part in (_CORE, _APP):
            if part not in names:
                continue
            root = _parse_xml(z.read(part), path, part)
            for child in root:
                text = _element_text(child)
                if text:
                    fields.append(_field(part, _local(child.tag), text))
        if _CUSTOM in names:
            root = _parse_xml(z.read(_CUSTOM), path, _CUSTOM)
            for prop in root:
                name = prop.get("name") or _local(prop.tag)
                text = _element_text(prop)
                if text:
                    fields.append(_field(_CUSTOM, name, text))
    return fields


def _strip_person_fields(data: bytes, path: Path, part: str) -> bytes:
    """Remove person and company elements from a docProps part."""
    for _event, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass
    root = _parse_xml(data, path, part)
    removed = False
    for child in list(root):
        if classify(_local(child.tag)) == "Person":
            root.remove(child)
            removed = True
    if not removed:
        return data
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def _clean_office(src: Path, out: Path) -> None:
    try:
        with _open_zip(src) as zin:
            names = set(zin.namelist())
            replacements = {
                part: _strip_person_fields(zin.read(part), src, part)
                for part in (_CORE, _APP)
                if part in names
            }
            with zipfile.ZipFile(out, "w") as zout:
                for info in zin.infolist():
                    data = replacements.get(info.filename)
                    if data is None:
                        data = zin.read(info.filename)
                    zout.writestr(info, data)
    except UserError:
        _unlink(out)
        raise
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        _unlink(out)
        raise UserError(f"Kunne ikke vaske «{src.name}»: {exc}") from None


# --- public API -----------------------------------------------------------


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _fields(path: Path, kind: str) -> tuple[list[Field], list[str]]:
    if kind == "image":
        return _image_fields(path), []
    if kind == "pdf":
        return _pdf_fields(path)
    return _office_fields(path), []


def read_metadata(path: Path) -> tuple[dict[str, Any], list[str]]:
    """Read all metadata of one file. Returns (result, warnings)."""
    kind = detect_kind(path)
    fields, notes = _fields(path, kind)
    result = {
        "path": str(path),
        "format": _FORMAT_LABEL[path.suffix.lower()],
        "field_count": len(fields),
        "sensitive_count": sum(1 for f in fields if f.sensitive),
        "groups": group_fields(fields),
    }
    return result, notes


def clean_file(path: Path, out_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Write a cleaned copy of path into out_dir and verify it.

    Returns (result, warnings). The input file is never modified.
    """
    kind = detect_kind(path)
    before, _ = _fields(path, kind)
    orientation_before = image_orientation(path) if kind == "image" else None

    out = safe_output_path(path, out_dir, f"-vasket{path.suffix}")
    was_encrypted = False
    if kind == "image":
        _clean_image(path, out)
    elif kind == "pdf":
        was_encrypted = _clean_pdf(path, out)
    else:
        _clean_office(path, out)

    # Verify by reading the cleaned file again.
    after, notes = _fields(out, kind)
    warnings = [f"{out.name}: {n}" for n in notes]
    if kind == "image":
        after = [f for f in after if f.name != "Orientation"]
    after_keys = {f.key for f in after}
    removed = [f for f in before if f.key not in after_keys and f.name != "Orientation"]

    alarm_groups = set(SENSITIVE_GROUPS)
    if kind != "office":
        alarm_groups.add("Utstyr")
    for f in after:
        if f.group in alarm_groups:
            warnings.append(
                f"«{f.name}» ({f.group}) finnes fortsatt i «{out.name}»: {f.value}"
            )
    secret_values = {f.value for f in before if f.sensitive and len(f.value) >= 3}
    for f in after:
        if f.group in alarm_groups:
            continue
        for secret in secret_values:
            if secret in f.value:
                warnings.append(
                    f"Feltet «{f.name}» i «{out.name}» inneholder fortsatt «{secret}»."
                )

    orientation_after = None
    if kind == "image":
        orientation_after = image_orientation(out)
        if orientation_before not in (None, 1) and orientation_after != orientation_before:
            warnings.append(
                f"Orienteringen i «{out.name}» ble ikke bevart "
                f"({orientation_before} før, {orientation_after} etter)."
            )

    result: dict[str, Any] = {
        "path": str(out),
        "source": str(path),
        "format": _FORMAT_LABEL[path.suffix.lower()],
        "removed": [f.to_dict() for f in removed],
        "remaining": [f.to_dict() for f in after],
        "verified": not warnings,
    }
    if kind == "image":
        result["orientation"] = orientation_after
    if was_encrypted:
        # Not part of "verified": metadata removal itself was checked above.
        warnings.append(
            f"Originalen «{path.name}» var kryptert (eierpassord med tillatelser). "
            f"Den vaskede filen «{out.name}» har ikke lenger krypteringen eller "
            "tillatelsesbegrensningene originalen hadde."
        )
    return result, warnings
