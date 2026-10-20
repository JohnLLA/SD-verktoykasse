"""jv metadata vis."""

from jv_common import skip_if_missing


def _fields(output):
    return {(f["source"], f["field"]): f for items in output["groups"].values() for f in items}


@skip_if_missing("exiftool")
def test_vis_image_groups(run, data_dir):
    code, report, _ = run("vis", data_dir / "bilde_gps.jpg")
    assert code == 0
    out = report["outputs"][0]
    assert set(out["groups"]) == {"Sted", "Person", "Utstyr", "Tid", "Annet"}
    names = {g: {f["field"] for f in items} for g, items in out["groups"].items()}
    assert {"GPSLatitude", "GPSLongitude", "GPSAltitude"} <= names["Sted"]
    assert "Artist" in names["Person"]
    assert {"Make", "Model", "Software"} <= names["Utstyr"]
    assert "DateTimeOriginal" in names["Tid"]
    for f in out["groups"]["Sted"] + out["groups"]["Person"]:
        assert f["sensitive"] is True
    for f in out["groups"]["Utstyr"] + out["groups"]["Tid"]:
        assert f["sensitive"] is False
    assert report["tool"] == "metadata"
    assert report["inputs"][0]["sha256"]
    assert "følsomme" in report["summary"]


def test_vis_pdf(run, data_dir):
    code, report, _ = run("vis", data_dir / "dokument_forfatter.pdf")
    assert code == 0
    fields = _fields(report["outputs"][0])
    assert fields[("PDF Info", "Author")]["value"] == "Ola Testesen"
    assert fields[("PDF Info", "Author")]["group"] == "Person"
    assert fields[("PDF Info", "Company")]["group"] == "Person"
    assert fields[("PDF Info", "LastModifiedBy")]["value"] == "Kari Fiktivsen"
    assert fields[("PDF Info", "Creator")]["group"] == "Utstyr"
    assert fields[("XMP", "dc:creator")]["value"] == "Ola Testesen"
    assert fields[("XMP", "dc:creator")]["sensitive"] is True
    assert fields[("XMP", "xmp:CreatorTool")]["group"] == "Utstyr"


def test_vis_docx(run, data_dir):
    code, report, _ = run("vis", data_dir / "dokument_forfatter.docx")
    assert code == 0
    out = report["outputs"][0]
    person = {f["field"]: f["value"] for f in out["groups"]["Person"]}
    assert person == {
        "creator": "Ola Testesen",
        "lastModifiedBy": "Kari Fiktivsen",
        "Company": "Eksempelfirma AS",
        "Manager": "Per Prøvesen",
    }
    assert out["sensitive_count"] == 4
    utstyr = {f["field"] for f in out["groups"]["Utstyr"]}
    assert "Application" in utstyr
    tid = {f["field"] for f in out["groups"]["Tid"]}
    assert {"created", "modified"} <= tid


@skip_if_missing("exiftool")
def test_vis_folder(run, copy_to, tmp_path):
    copy_to("bilde_gps.jpg")
    copy_to("dokument_forfatter.pdf")
    copy_to("dokument_forfatter.docx")
    (tmp_path / "inn" / "notat.txt").write_text("ikke støttet", encoding="utf-8")
    code, report, err = run("vis", tmp_path / "inn")
    assert code == 0
    assert len(report["outputs"]) == 3
    assert any("notat.txt" in w for w in report["warnings"])
    assert '"progress"' in err


def test_vis_does_not_write(run, data_dir, tmp_path):
    code, report, _ = run("vis", data_dir / "dokument_forfatter.docx")
    assert code == 0
    assert list(tmp_path.iterdir()) == []
