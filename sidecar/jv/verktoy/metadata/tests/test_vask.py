"""jv metadata vask: the cleaned file is read again and checked."""

import subprocess
import zipfile
from pathlib import Path

import pikepdf
import pytest
from jv_common import sha256_file, skip_if_missing
from PIL import Image, ImageOps
from PIL.PngImagePlugin import PngInfo

from jv_metadata.core import _office_fields, _pdf_fields, image_orientation

SECRETS = ("Ola Testesen", "Kari Fiktivsen", "Eksempelfirma")


def _exif_text(path: Path) -> str:
    proc = subprocess.run(
        ["exiftool", "-a", "-G1", "-s", str(path)], capture_output=True, text=True, check=False
    )
    return proc.stdout


@skip_if_missing("exiftool")
def test_vask_image_removes_gps_and_keeps_orientation(run, copy_to, tmp_path):
    src = copy_to("bilde_gps.jpg", "bilde med æøå; og mellomrom.jpg")
    before = sha256_file(src)
    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0, report
    assert sha256_file(src) == before

    out = Path(report["outputs"][0]["path"])
    assert out.parent == tmp_path / "ut"
    assert out.name == "bilde med æøå; og mellomrom-vasket.jpg"
    assert report["outputs"][0]["verified"] is True
    assert report["warnings"] == []

    text = _exif_text(out)
    for tag in ("GPS", "Artist", "Make", "Model", "Software", "DateTimeOriginal"):
        assert tag not in text
    assert "Ola Testesen" not in out.read_bytes().decode("latin-1")

    assert image_orientation(out) == 6
    assert report["outputs"][0]["orientation"] == 6
    with Image.open(out) as img:
        shown = ImageOps.exif_transpose(img).convert("RGB")
    assert shown.size == (480, 640)
    r, g, b = shown.getpixel((240, 20))
    assert r > 180 and g < 90 and b < 90, "rødt felt skal være øverst"

    removed = {f["field"] for f in report["outputs"][0]["removed"]}
    assert {"GPSLatitude", "Artist", "Make"} <= removed


@skip_if_missing("exiftool")
def test_vask_png(run, tmp_path):
    src = tmp_path / "skjerm bilde.png"
    info = PngInfo()
    info.add_text("Author", "Ola Testesen")
    Image.new("RGB", (40, 30), (0, 128, 0)).save(src, pnginfo=info)
    subprocess.run(
        ["exiftool", "-q", "-overwrite_original", "-GPSLatitude=60.39745",
         "-GPSLatitudeRef=N", "-Artist=Ola Testesen", str(src)],
        check=True,
    )
    code, report, _ = run("vis", src)
    assert code == 0
    assert report["outputs"][0]["sensitive_count"] >= 2

    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0
    out = Path(report["outputs"][0]["path"])
    text = _exif_text(out)
    assert "GPS" not in text and "Ola Testesen" not in text
    with Image.open(out) as img:
        assert img.size == (40, 30)


def test_vask_pdf(run, copy_to, tmp_path):
    src = copy_to("dokument_forfatter.pdf", "notat ÆØÅ.pdf")
    before = sha256_file(src)
    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0
    assert sha256_file(src) == before
    out = Path(report["outputs"][0]["path"])
    assert report["outputs"][0]["verified"] is True

    with pikepdf.open(out) as pdf:
        assert "/Info" not in pdf.trailer
        assert "/Metadata" not in pdf.Root
        assert len(pdf.pages) == 1
        # write an uncompressed copy to search every byte
        plain = tmp_path / "plain.pdf"
        pdf.save(plain, compress_streams=False, object_stream_mode=pikepdf.ObjectStreamMode.disable)
    raw = plain.read_bytes()
    for secret in SECRETS:
        assert secret.encode() not in raw
        assert secret.encode("utf-16-be") not in raw
    fields, _ = _pdf_fields(out)
    assert fields == []


def test_vask_docx(run, copy_to, tmp_path):
    src = copy_to("dokument_forfatter.docx", "intern notat.docx")
    before = sha256_file(src)
    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0
    assert sha256_file(src) == before
    out = Path(report["outputs"][0]["path"])

    with zipfile.ZipFile(src) as a, zipfile.ZipFile(out) as b:
        assert b.testzip() is None
        assert a.namelist() == b.namelist()
        for name in a.namelist():
            if not name.startswith("docProps/") or name.endswith(".jpeg"):
                assert a.read(name) == b.read(name), name
        props = b.read("docProps/core.xml") + b.read("docProps/app.xml")
    for secret in (*SECRETS, "Per Prøvesen"):
        assert secret.encode() not in props
    fields = {f.name: f.value for f in _office_fields(out)}
    assert fields["title"] == "Internt notat"
    assert "creator" not in fields and "Company" not in fields


def _fake_ooxml(path: Path) -> None:
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Ola Testesen</dc:creator>'
        "<cp:lastModifiedBy>Kari Fiktivsen</cp:lastModifiedBy><dc:title>Regneark</dc:title></cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Application>Microsoft Excel</Application><Company>Eksempelfirma AS</Company></Properties>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("xl/workbook.xml", "<workbook/>")


@pytest.mark.parametrize("ext", [".xlsx", ".pptx"])
def test_vask_other_office(run, tmp_path, ext):
    src = tmp_path / f"fil{ext}"
    _fake_ooxml(src)
    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0
    assert report["outputs"][0]["verified"] is True
    fields = {f.name: f.value for f in _office_fields(Path(report["outputs"][0]["path"]))}
    assert fields == {"title": "Regneark", "Application": "Microsoft Excel"}


@skip_if_missing("exiftool")
def test_vask_folder_and_no_overwrite(run, copy_to, tmp_path):
    copy_to("bilde_gps.jpg")
    copy_to("dokument_forfatter.pdf")
    copy_to("dokument_forfatter.docx")
    inn = tmp_path / "inn"
    hashes = {p.name: sha256_file(p) for p in inn.iterdir()}

    code, report, err = run("vask", inn, "--out", inn)
    assert code == 0
    assert len(report["outputs"]) == 3
    assert '"progress"' in err
    code, report2, _ = run("vask", inn / "bilde_gps.jpg", "--out", inn)
    assert code == 0
    assert Path(report2["outputs"][0]["path"]).name == "bilde_gps-vasket-2.jpg"
    for name, digest in hashes.items():
        assert sha256_file(inn / name) == digest


def _heic_files(data_dir: Path) -> list[Path]:
    return sorted(p for p in data_dir.iterdir() if p.suffix.lower() in (".heic", ".heif"))


@skip_if_missing("exiftool")
def test_vask_heic(run, data_dir, copy_to, tmp_path):
    files = _heic_files(data_dir)
    if not files:
        pytest.skip("Ingen HEIC-testfil i testdata/metadata – HEIC går via exiftool som JPEG")
    src = copy_to(files[0].name)
    before = image_orientation(src)
    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0
    out = Path(report["outputs"][0]["path"])
    assert "GPS" not in _exif_text(out)
    assert image_orientation(out) == before


def test_heic_goes_through_exiftool(monkeypatch, tmp_path):
    """HEIC is handled as an image via exiftool; without it: Norwegian error."""
    from jv_common import UserError

    from jv_metadata import core

    src = tmp_path / "bilde.heic"
    src.write_bytes(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32)
    assert core.detect_kind(src) == "image"
    calls = []

    def fake_require(name):
        calls.append(name)
        raise UserError(f"Programmet «{name}» er ikke installert")

    monkeypatch.setattr(core, "require_binary", fake_require)
    with pytest.raises(UserError, match="exiftool"):
        core.read_metadata(src)
    assert calls == ["exiftool"]


def _make_pdf(path: Path, encrypt: bool) -> None:
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.docinfo["/Author"] = "Ola Testesen"
    if encrypt:
        pdf.save(
            path,
            encryption=pikepdf.Encryption(
                owner="eier-hemmelig", user="", allow=pikepdf.Permissions(extract=False, print_lowres=False)
            ),
        )
    else:
        pdf.save(path)


def test_vask_pdf_eierpassord_gir_advarsel(run, tmp_path):
    src = tmp_path / "låst fil.pdf"
    _make_pdf(src, encrypt=True)
    before = sha256_file(src)
    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0, report
    assert sha256_file(src) == before
    out = Path(report["outputs"][0]["path"])
    assert any(
        "kryptert" in w and "ikke lenger krypteringen" in w and "tillatelsesbegrensningene" in w
        for w in report["warnings"]
    ), report["warnings"]
    with pikepdf.open(out) as pdf:
        assert not pdf.is_encrypted
        assert "/Info" not in pdf.trailer


def test_vask_pdf_ukryptert_gir_ikke_krypteringsadvarsel(run, tmp_path):
    src = tmp_path / "åpen.pdf"
    _make_pdf(src, encrypt=False)
    code, report, _ = run("vask", src, "--out", tmp_path / "ut")
    assert code == 0, report
    assert not any("kryptert" in w for w in report["warnings"])
    assert report["warnings"] == []
