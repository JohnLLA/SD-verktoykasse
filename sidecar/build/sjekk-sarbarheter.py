#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Spør OSV (api.osv.dev) om kjente sårbarheter i systemprogrammene i binaries.json.

    python3 sidecar/build/sjekk-sarbarheter.py             sjekk programmene (nett kreves)
    python3 sidecar/build/sjekk-sarbarheter.py --unntak    sjekk bare at unntakene ikke er utløpt (ingen nett)
    python3 sidecar/build/sjekk-sarbarheter.py --json      maskinlesbar rapport
    python3 sidecar/build/sjekk-sarbarheter.py --pip-ignore  argumenter til pip-audit for unntak med pakke «python:<navn>»

OSV har ikke noe Homebrew-økosystem. Skriptet slår derfor opp programmets
kildekoderepo i OSVs GIT-økosystem med versjonen som tagg. Et program regnes
som «kontrollert» bare når OSV har oppføringer for repoet (ellers kan «ingen
funn» bety «ukjent»). Resten står som «ikke kontrollert», med lenke til
prosjektets sikkerhetsside. Bare programnavn og versjoner sendes til OSV,
aldri filer eller innhold fra brukere (regel 1 gjelder appen, og dette er et
byggeverktøy som bare kjøres i CI og på byggemaskinen).

Avslutningskode: 0 ingen funn utenom unntakene, 1 funn eller utløpt unntak,
2 nettfeil (OSV kunne ikke nås).

Unntak ligger i sidecar/build/sarbarhet-unntak.json (id, pakke, begrunnelse,
utloper) og i src-tauri/deny.toml (Rust, «utloper: ÅÅÅÅ-MM-DD» i begrunnelsen).
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HER = Path(__file__).resolve().parent
ROOT = HER.parent.parent
BINARIES = HER / "binaries.json"
UNNTAK = HER / "sarbarhet-unntak.json"
DENY = ROOT / "src-tauri" / "deny.toml"
OSV = "https://api.osv.dev/v1/query"

GH = "https://github.com/"
# program -> (repo i OSVs GIT-økosystem, tagg-maler med {v}, side å følge med på)
MAP: dict[str, tuple[str, tuple[str, ...], str]] = {
    "brotli": (GH + "google/brotli", ("v{v}",), ""),
    "dav1d": ("https://code.videolan.org/videolan/dav1d", ("{v}",), ""),
    "exiftool": (GH + "exiftool/exiftool", ("{v}",), ""),
    "ffmpeg": ("https://git.ffmpeg.org/ffmpeg.git", ("n{v}",), ""),
    "fontconfig": ("https://gitlab.freedesktop.org/fontconfig/fontconfig", ("{v}",), ""),
    "freetype": ("https://gitlab.freedesktop.org/freetype/freetype", ("VER-{v-}",), ""),
    "gettext": ("https://git.savannah.gnu.org/git/gettext.git", ("v{v}",), ""),
    "glib": ("https://gitlab.gnome.org/GNOME/glib", ("{v}",), ""),
    "graphite2": (GH + "silnrsi/graphite", ("{v}",), ""),
    "harfbuzz": (GH + "harfbuzz/harfbuzz", ("{v}",), ""),
    "icu4c@78": (GH + "unicode-org/icu", ("release-{v}",), ""),
    "jpeg-turbo": (GH + "libjpeg-turbo/libjpeg-turbo", ("{v}",), ""),
    "leptonica": (GH + "DanBloomberg/leptonica", ("{v}",), ""),
    "libarchive": (GH + "libarchive/libarchive", ("v{v}",), ""),
    "libb2": (GH + "BLAKE2/libb2", ("v{v}",), ""),
    "libpng": (GH + "pnggroup/libpng", ("v{v}",), ""),
    "libtiff": ("https://gitlab.com/libtiff/libtiff", ("v{v}",), ""),
    "libvmaf": (GH + "Netflix/vmaf", ("v{v}",), ""),
    "libvpx": ("https://chromium.googlesource.com/webm/libvpx", ("v{v}",), ""),
    "little-cms2": (GH + "mm2/Little-CMS", ("lcms{v}",), ""),
    "lz4": (GH + "lz4/lz4", ("v{v}",), ""),
    "openjpeg": (GH + "uclouvain/openjpeg", ("v{v}",), ""),
    "openssl@4": (GH + "openssl/openssl", ("openssl-{v}",), ""),
    "opus": (GH + "xiph/opus", ("v{v}",), ""),
    "pcre2": (GH + "PCRE2Project/pcre2", ("pcre2-{v}",), ""),
    "poppler": ("https://gitlab.freedesktop.org/poppler/poppler", ("poppler-{v}",), ""),
    "svt-av1": ("https://gitlab.com/AOMediaCodec/SVT-AV1", ("v{v}",), ""),
    "tesseract": (GH + "tesseract-ocr/tesseract", ("{v}",), ""),
    "webp": (GH + "webmproject/libwebp", ("v{v}",), ""),
    "xz": (GH + "tukaani-project/xz", ("v{v}",), ""),
    "zstd": (GH + "facebook/zstd", ("v{v}",), ""),
}
# Programmer uten oppslag i OSV, med prosjektets sikkerhetsside.
IKKE_KONTROLLERT: dict[str, str] = {
    "giflib": "https://sourceforge.net/p/giflib/bugs/",
    "gpgme": "https://gnupg.org/download/security_advisories.html",
    "gpgmepp": "https://gnupg.org/download/security_advisories.html",
    "lame": "https://sourceforge.net/p/lame/bugs/",
    "libassuan": "https://gnupg.org/download/security_advisories.html",
    "libgpg-error": "https://gnupg.org/download/security_advisories.html",
    "mpg123": "https://www.mpg123.de/",
    "nspr": "https://www.mozilla.org/en-US/security/advisories/",
    "nss": "https://www.mozilla.org/en-US/security/advisories/",
    "tesseract-lang": "https://github.com/tesseract-ocr/tessdata_fast (språkdata, ingen kjørbar kode)",
    "x265": "https://bitbucket.org/multicoreware/x265_git/issues",
    "apertium": "https://github.com/apertium/apertium/security",
    "apertium-data": "https://github.com/apertium/apertium-nno-nob (språkdata, ingen kjørbar kode)",
    "tessdata-nor": "https://github.com/tesseract-ocr/tessdata_fast (språkdata, ingen kjørbar kode)",
    "tessdata-eng": "https://github.com/tesseract-ocr/tessdata_fast (språkdata, ingen kjørbar kode)",
    "tessdata-osd": "https://github.com/tesseract-ocr/tessdata_fast (språkdata, ingen kjørbar kode)",
}


def normalize(name: str, version: str) -> str:
    v = re.sub(r"_\d+$", "", version)  # Homebrew-revisjon (13.55_1)
    if name == "tesseract":
        v = ".".join(v.split(".")[:3])  # 5.5.3.20260724 -> 5.5.3
    if name == "poppler":
        v = re.sub(r"-\d+$", "", v)  # 26.09.0-0 -> 26.09.0
    return v


def tags(templates: tuple[str, ...], v: str) -> list[str]:
    return [t.replace("{v-}", v.replace(".", "-")).replace("{v}", v) for t in templates]


def osv(body: dict) -> list[dict]:
    out: list[dict] = []
    body = dict(body)
    for _ in range(20):
        req = urllib.request.Request(OSV, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        out += data.get("vulns", [])
        if not data.get("next_page_token"):
            break
        body["page_token"] = data["next_page_token"]
    return out


def program_status(name: str, entry: dict) -> dict:
    version = normalize(name, entry["version"])
    base = {"navn": name, "versjon": entry["version"]}
    rev = entry.get("source_revision")
    if rev:
        funn = osv({"commit": rev})
        return {**base, "status": "kontrollert", "kilde": f"commit {rev[:12]}", "funn": funn}
    if name in MAP:
        repo, templates, _ = MAP[name]
        pkg = {"name": repo, "ecosystem": "GIT"}
        if not osv({"package": pkg}):
            return {**base, "status": "ikke kontrollert", "lenke": repo, "grunn": "OSV har ingen oppføringer for prosjektet"}
        funn: dict[str, dict] = {}
        for tag in tags(templates, version):
            for v in osv({"version": tag, "package": pkg}):
                funn[v["id"]] = v
        return {**base, "status": "kontrollert", "kilde": f"{repo} {tags(templates, version)[0]}", "funn": list(funn.values())}
    return {**base, "status": "ikke kontrollert", "lenke": IKKE_KONTROLLERT.get(name, "ukjent"), "grunn": "OSV har ikke prosjektet"}


def last_exceptions() -> list[dict]:
    if not UNNTAK.exists():
        return []
    return json.loads(UNNTAK.read_text(encoding="utf-8")).get("unntak", [])


def check_expiry(today: datetime.date) -> list[str]:
    """Utløpte eller udaterte unntak (JSON-fila og deny.toml)."""
    problems = []
    for u in last_exceptions():
        try:
            if datetime.date.fromisoformat(u["utloper"]) < today:
                problems.append(f"unntaket {u['id']} ({u.get('pakke', '?')}) utløp {u['utloper']}")
        except (KeyError, ValueError):
            problems.append(f"unntaket {u.get('id', '?')} mangler gyldig «utloper»")
        if not u.get("begrunnelse"):
            problems.append(f"unntaket {u.get('id', '?')} mangler begrunnelse")
    if DENY.exists():
        for line in DENY.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("{ id ="):
                m = re.search(r"utloper: (\d{4}-\d{2}-\d{2})", line)
                ident = re.search(r'id = "([^"]+)"', line)
                name = ident.group(1) if ident else "?"
                if not m:
                    problems.append(f"deny.toml: {name} mangler «utloper: ÅÅÅÅ-MM-DD»")
                elif datetime.date.fromisoformat(m.group(1)) < today:
                    problems.append(f"deny.toml: unntaket {name} utløp {m.group(1)}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unntak", action="store_true", help="sjekk bare utløpsdatoene (ingen nett)")
    ap.add_argument("--json", action="store_true", help="skriv JSON")
    ap.add_argument("--pip-ignore", action="store_true",
                    help="skriv «--ignore-vuln ID»-argumenter for pip-audit (unntak med pakke «python:<navn>»)")
    ap.add_argument("--binaries", default=str(BINARIES))
    args = ap.parse_args()
    today = datetime.date.today()

    if args.pip_ignore:
        print(" ".join(f"--ignore-vuln {u['id']}" for u in last_exceptions() if str(u.get("pakke", "")).startswith("python:")))
        return 0

    expired = check_expiry(today)
    if args.unntak:
        for p in expired:
            print("FEIL:", p)
        print("Unntakene er gyldige." if not expired else "")
        return 1 if expired else 0

    data = json.loads(Path(args.binaries).read_text(encoding="utf-8"))
    allowed = {u["id"] for u in last_exceptions()}
    rows = []
    try:
        for target, section in data.items():
            if not isinstance(section, dict) or "programs" not in section:
                continue
            for name, entry in section["programs"].items():
                rows.append({"plattform": target, **program_status(name, entry)})
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"FEIL: OSV kunne ikke nås ({e.__class__.__name__}).", file=sys.stderr)
        return 2

    bad = 0
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        print("== Kontrollert mot OSV ==")
    for r in rows:
        funn = r.get("funn", [])
        ny = [f for f in funn if f["id"] not in allowed and not (set(f.get("aliases", [])) & allowed)]
        bad += len(ny)
        if r["status"] == "kontrollert" and not args.json:
            tegn = "FUNN" if ny else ("unntatt" if funn else "ok")
            print(f"{tegn:8} {r['plattform'].split('-')[0]:8} {r['navn']} {r['versjon']}  ({r['kilde']})")
            for f in funn:
                mark = "  (unntatt)" if f not in ny else ""
                print(f"           {f['id']} {f.get('summary', '')[:90]}{mark}")
    if not args.json:
        print("\n== Ikke kontrollert (OSV kjenner ikke programmet) ==")
        for r in rows:
            if r["status"] != "kontrollert":
                print(f"{r['plattform'].split('-')[0]:8} {r['navn']} {r['versjon']}: {r['lenke']}")
    for p in expired:
        print("FEIL:", p)
    n_ok = sum(1 for r in rows if r["status"] == "kontrollert")
    print(f"\n{n_ok} kontrollert, {len(rows) - n_ok} ikke kontrollert, {bad} funn uten unntak, {len(expired)} utløpte unntak.",
          file=sys.stderr if args.json else sys.stdout)
    return 1 if bad or expired else 0


if __name__ == "__main__":
    sys.exit(main())
