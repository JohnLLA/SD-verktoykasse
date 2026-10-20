# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lisenser/: licence texts and a source list for everything in an app.

All texts are copied from local files: the Homebrew kegs (and their
sbom.spdx.json for version, licence and source URL), the dist-info folders
of the Python packages, and the uv Python installation. Texts that are not
installed anywhere locally are kept in builder/lisenstekster/ (see
STORED_TEXTS). Nothing is fetched.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

from .. import JV
from . import CELLAR, HOMEBREW
from .resources import keg_of

LICENSE_PATTERNS = ("LICEN", "COPYING", "COPYRIGHT", "NOTICE", "AUTHORS", "PATENTS", "UNLICENSE",
                    "GPL-", "LGPL-", "AGPL-", "MPL-", "MIT", "BSD-", "APACHE-")
SKIP_SUFFIXES = (".html", ".htm", ".pdf", ".png", ".svg")

STORED = Path(__file__).resolve().parent / "lisenstekster"

# Licence texts for packages whose installation carries none. Key: package
# name in lower case. Value: (folder under lisenstekster/, origin note).
STORED_TEXTS: dict[str, tuple[str, str]] = {
    "bzip2": ("bzip2", "Lisensteksten er standardteksten fra LICENSE i bzip2 1.0.8; "
                       "opphavsrettslinjen stemmer med «bzip2 --license» i macOS."),
    "expat": ("expat", "Lisensteksten er hentet fra lisensmerknaden i expat.h (expat 2.7.4) "
                       "i macOS SDK fra Command Line Tools. Samme MIT-lisens."),
    "libffi": ("libffi", "Lisensteksten er hentet fra lisensmerknaden i ffi/ffi.h i macOS SDK "
                         "fra Command Line Tools (eldre libffi). Samme MIT-lisens."),
    "sqlite": ("sqlite", "Public domain. Erklæringen er satt sammen fra merknaden i sqlite3.h "
                         "(Homebrews sqlite) og SQLites egen beskrivelse."),
    "leptonica": ("leptonica", "Lisensteksten er hentet fra lisensmerknaden i "
                               "include/leptonica/allheaders.h i Homebrews leptonica."),
    "nspr": ("mpl-2.0", "Standardteksten for MPL-2.0. NSPR har ingen egen opphavsrettslinje; "
                        "kildefilene viser bare MPL-merknaden."),
    "nss": ("mpl-2.0", "Standardteksten for MPL-2.0. NSS har ingen egen opphavsrettslinje; "
                       "kildefilene viser bare MPL-merknaden."),
}


# Licence texts added even when the installation has its own: the keg's text
# does not cover the part that is bundled. Key: package name in lower case.
EXTRA_TEXTS: dict[str, tuple[str, str]] = {
    "gettext": ("lgpl-2.1", "Bare libintl er med i appen, og den er LGPL-2.1-or-later. COPYING i "
                            "Homebrews gettext er GPL-3-teksten for resten av gettext. LGPL-2.1-teksten "
                            "(LGPL-2.1.txt) er standardteksten, kopiert fra COPYING.hunalign i "
                            "Apertium-kildene (lik COPYING.LGPLv2.1 i Homebrews ffmpeg)."),
}


@dataclass
class Package:
    name: str
    version: str
    license: str
    source: str
    kind: str  # "Homebrew", "Python-pakke", "Kjøretid"
    texts: list[Path] = field(default_factory=list)
    note: str = ""

    @property
    def folder(self) -> str:
        return re.sub(r"[^A-Za-z0-9._+-]", "_", self.name)


def _license_files(folder: Path, depth: int = 1) -> list[Path]:
    found = []
    if not folder.is_dir():
        return found
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.name.upper().startswith(LICENSE_PATTERNS) and not p.name.lower().endswith(SKIP_SUFFIXES):
            found.append(p)
        elif p.is_dir() and depth > 1:
            found += _license_files(p, depth - 1)
    return found


# ------------------------------------------------------------------ Homebrew


def _sbom(keg: Path) -> tuple[str, str]:
    """(licence, source URL) from the keg's sbom.spdx.json."""
    path = keg / "sbom.spdx.json"
    if not path.exists():
        return "ukjent", "ukjent"
    data = json.loads(path.read_text(encoding="utf-8"))
    for pkg in data.get("packages", []):
        if str(pkg.get("SPDXID", "")).startswith("SPDXRef-Archive"):
            lic = pkg.get("licenseConcluded") or pkg.get("licenseDeclared") or "ukjent"
            if lic == "NOASSERTION":
                lic = pkg.get("licenseDeclared", "ukjent")
            return lic, pkg.get("downloadLocation", "ukjent")
    return "ukjent", "ukjent"


def homebrew_package(formula: str, version: str) -> Package:
    keg = CELLAR / formula / version
    lic, source = _sbom(keg)
    texts = _license_files(keg)
    share = keg / "share"
    if share.is_dir():
        for sub in share.iterdir():
            if sub.is_dir() and sub.name not in ("man", "locale", "info"):
                texts += _license_files(sub, depth=3)
    note = ""
    if not texts:
        for readme in sorted(keg.glob("README*")):
            if readme.suffix.lower() in (".md", ".txt", "") and re.search(
                r"licen[cs]e", readme.read_text(encoding="utf-8", errors="replace"), re.I
            ):
                texts.append(readme)
                note = f"Lisensen er beskrevet i {readme.name}; hele lisensteksten følger kildekoden."
                break
    pkg = Package(formula, version, lic, source, "Homebrew", texts, note)
    if not texts:
        pkg.note = "Lisensteksten ligger ikke i Homebrew-installasjonen; se kildekoden."
    return pkg


def homebrew_packages(files: list[Path], formulas: list[str] = ()) -> list[Package]:
    kegs: dict[str, str] = {}
    for f in files:
        k = keg_of(f)
        if k:
            kegs[k[0]] = k[1]
    for formula in formulas:
        opt = (HOMEBREW / "opt" / formula).resolve()
        k = keg_of(opt)
        if k:
            kegs[k[0]] = k[1]
    return [homebrew_package(name, ver) for name, ver in sorted(kegs.items())]


# ------------------------------------------------------------------ Python


def _python_source_paths(work: Path) -> set[Path]:
    """Every source file PyInstaller put in the app (modules, binaries, data)."""
    paths: set[Path] = set()
    for toc_name in ("PYZ-00.toc", "COLLECT-00.toc"):
        toc = work / toc_name
        if not toc.exists():
            continue
        data = ast.literal_eval(toc.read_text(encoding="utf-8"))

        def walk(node):
            if isinstance(node, (list, tuple)):
                if len(node) == 3 and all(isinstance(x, str) for x in node):
                    paths.add(Path(node[1]))
                else:
                    for item in node:
                        walk(item)

        walk(data)
    return paths


def _dist_index() -> dict[Path, metadata.Distribution]:
    index: dict[Path, metadata.Distribution] = {}
    for dist in metadata.distributions():
        for f in dist.files or []:
            try:
                index[Path(dist.locate_file(f)).resolve()] = dist
            except OSError:
                continue
    return index


def _dist_license(dist: metadata.Distribution) -> str:
    md = dist.metadata
    lic = md.get("License-Expression") or ""
    if not lic:
        raw = (md.get("License") or "").strip()
        if raw and len(raw) < 80 and "\n" not in raw:
            lic = raw
    if not lic:
        classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
        lic = ", ".join(classifiers)
    return lic or "se lisensfilen"


def _dist_source(dist: metadata.Distribution) -> str:
    name = dist.metadata["Name"]
    pypi = f"https://pypi.org/project/{name}/{dist.version}/#files"
    for entry in dist.metadata.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("source", "source code", "repository", "code", "github"):
            return f"{pypi} (kildekodearkiv: {url.strip()})"
    return pypi


def _dist_texts(dist: metadata.Distribution) -> list[Path]:
    texts = []
    for f in dist.files or []:
        parts = Path(str(f)).parts
        if parts and parts[0].endswith(".dist-info") and len(parts) > 1:
            name = parts[-1]
            if name.upper().startswith(LICENSE_PATTERNS) or (len(parts) > 2 and parts[1] == "licenses"):
                p = Path(dist.locate_file(f))
                if p.is_file():
                    texts.append(p)
    return texts


def python_packages(work: Path) -> list[Package]:
    index = _dist_index()
    own_src = (JV / "verktoy").resolve()
    dists: dict[str, metadata.Distribution] = {}
    for p in _python_source_paths(work):
        try:
            real = p.resolve()
        except OSError:
            continue
        if real.is_relative_to(own_src):
            continue
        dist = index.get(real)
        if dist is not None and not dist.metadata["Name"].startswith("jv-"):
            dists[dist.metadata["Name"]] = dist
    out = []
    for name in sorted(dists, key=str.lower):
        d = dists[name]
        pkg = Package(name, d.version, _dist_license(d), _dist_source(d), "Python-pakke", _dist_texts(d))
        if not pkg.texts:
            pkg.note = "Pakken har ingen egen lisensfil; lisensen står i metadataene (se over)."
        out.append(pkg)
    return out


# ------------------------------------------------------------------ runtime


def python_runtime() -> list[Package]:
    base = Path(sys.base_prefix)
    ver = ".".join(map(str, sys.version_info[:3]))
    import ssl
    import sqlite3
    import pyexpat
    import _decimal

    py = Package(
        "Python", ver, "PSF-2.0",
        f"https://www.python.org/ftp/python/{ver}/Python-{ver}.tar.xz "
        "(bygget av python-build-standalone: https://github.com/astral-sh/python-build-standalone)",
        "Kjøretid", [base / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "LICENSE.txt"],
    )
    # Libraries linked into libpython by python-build-standalone.
    parts = []
    openssl_ver = ssl.OPENSSL_VERSION.split()[1]
    for name, version, lic, source, formula in [
        ("OpenSSL", openssl_ver, "Apache-2.0", f"https://github.com/openssl/openssl/releases/tag/openssl-{openssl_ver}", "openssl@3"),
        ("SQLite", sqlite3.sqlite_version, "blessing (public domain)", "https://www.sqlite.org/download.html", "sqlite"),
        ("mpdecimal", _decimal.__libmpdec_version__, "BSD-2-Clause", "https://www.bytereef.org/mpdecimal/download.html", "mpdecimal"),
        ("xz (liblzma)", "ukjent", "0BSD", "https://github.com/tukaani-project/xz/releases", "xz"),
        ("expat", pyexpat.EXPAT_VERSION.split("_")[-1], "MIT", "https://github.com/libexpat/libexpat/releases", None),
        ("libffi", "ukjent", "MIT", "https://github.com/libffi/libffi/releases", None),
        ("bzip2", "ukjent", "bzip2-1.0.6", "https://sourceware.org/bzip2/downloads.html", None),
    ]:
        texts: list[Path] = []
        note = "Lenket inn i libpython (python-build-standalone)."
        if formula:
            kegs = sorted(CELLAR.glob(f"{formula}/*"))
            if kegs:
                texts = _license_files(kegs[-1])
                if texts:
                    note += f" Lisensteksten er hentet fra Homebrews {formula} {kegs[-1].name}."
        if not texts:
            note += " Lisensteksten finnes ikke lokalt; den følger kildekoden."
        parts.append(Package(name, version, lic, source, "Kjøretid", texts, note))
    return [py, *parts]


def exiftool_extra() -> list[Path]:
    """Perl's own licence texts (exiftool is licensed like Perl)."""
    pods = Path("/System/Library/Perl")
    found = sorted(pods.glob("5.*/pods/perlartistic.pod")) + sorted(pods.glob("5.*/pods/perlgpl.pod"))
    return found[-2:] if found else []


def pyinstaller_bootloader(env: dict[str, str]) -> Package:
    """The PyInstaller bootloader is part of every package (the «jv» executable)."""
    import subprocess

    code = ("import PyInstaller, importlib.metadata as m, pathlib; d = m.distribution('pyinstaller'); "
            "print(PyInstaller.__version__); "
            "print('\\n'.join(str(pathlib.Path(d.locate_file(f)).resolve()) for f in d.files or [] "
            "if f.name.upper().startswith('COPYING')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env).stdout.split("\n")
    version = out[0].strip() if out else "ukjent"
    texts = [Path(x) for x in out[1:] if x.strip() and Path(x).is_file()]
    return Package(
        "PyInstaller (bootloader)", version, "GPL-2.0-or-later WITH PyInstaller-Bootloader-exception",
        f"https://github.com/pyinstaller/pyinstaller/releases/tag/v{version}", "Kjøretid", texts,
        "Bare bootloaderen (den kjørbare filen «jv») er med. Unntaket i lisensen tillater å "
        "distribuere den sammen med programmer under andre lisenser.",
    )


# ------------------------------------------------------------------ Apertium


def apertium_packages(sources: Path | None = None) -> list[Package]:
    """Apertium programs and language data, built from source in ~/.local.

    Licence texts come from the COPYING files in the source checkouts
    (~/Kilder/apertium/<repo>); the source line names the GitHub repository
    and the exact commit that was built.
    """
    from . import apertium

    root = sources or apertium.SOURCES
    out = []
    for repo, version, lic, extra in apertium.REPOS:
        folder = root / repo
        texts = [folder / "COPYING", *(folder / name for name in extra)]
        texts = [t for t in texts if t.is_file()]
        commit = apertium.git_commit(folder)
        url = apertium.git_url(folder)
        note = ""
        if repo in ("apertium-nob", "apertium-nno"):
            note = "Ordbøkene er kompilert inn i språkdataene til apertium-nno-nob."
        elif repo == "apertium-nno-nob":
            note = ("Bare filene modusene nob-nno og nno-nob bruker, er med. Stiene i "
                    "mode-filene er skrevet om til ${APERTIUM_DATADIR}/….")
        elif repo == "apertium":
            note = ("Skriptet «apertium» er med. Linjene som setter APERTIUM_PATH og "
                    "APERTIUM_DATADIR er endret til relative standardverdier (regnet ut fra "
                    "skriptets egen mappe), og to linjer er lagt til: «_jv_here=…» og "
                    "«export APERTIUM_PATH APERTIUM_DATADIR». Resten av skriptet er uendret.")
        out.append(Package(repo, version, lic, f"{url} (commit {commit})", "Apertium", texts, note))
    return out


# ------------------------------------------------------------------ writing


def add_stored_texts(packages: list[Package]) -> None:
    """Fill in texts from lisenstekster/ for packages that have none, and add
    the extra texts in EXTRA_TEXTS."""
    for p in packages:
        extra = EXTRA_TEXTS.get(p.name.lower())
        if extra is not None:
            folder, note = extra
            p.texts += sorted(f for f in (STORED / folder).iterdir() if f.is_file() and f not in p.texts)
            p.note = f"{p.note} {note}".strip() if p.note else note
        if p.texts:
            continue
        entry = STORED_TEXTS.get(p.name.lower())
        if entry is None:
            continue
        folder, note = entry
        p.texts = sorted(f for f in (STORED / folder).iterdir() if f.is_file())
        linked = "Lenket inn i libpython (python-build-standalone)."
        p.note = f"{linked} {note}" if p.note.startswith(linked) else note


MAC_INTRO = [
    "Programmene fra Homebrew er kopiert uendret, bortsett fra at stiene til",
    "bibliotekene er skrevet om (install_name_tool) og at de er signert på nytt.",
    "I exiftool er #!-linjen endret til /usr/bin/perl og stien til bibliotekene",
    "satt til mappen ved siden av skriptet.",
    "",
]

# Order of the groups in «Kildekode og versjoner.txt».
KINDS = ("Kjøretid", "Homebrew", "Apertium", "Windows-program", "Windows-bibliotek", "Python-pakke")


def write(dst: Path, packages: list[Package], tool_id: str, tool_version: str,
          intro: list[str] | None = None) -> list[Package]:
    """Write Lisenser/ and return the packages that lack a licence text.

    `intro`: the lines about how the programs were copied (default: Mac/Homebrew).
    """
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    add_stored_texts(packages)
    missing = []
    lines = [
        f"Journalistverktøy – {tool_id} {tool_version}",
        "",
        "Denne pakken inneholder programvare fra andre. Under står hver pakke med",
        "versjon, lisens og hvor kildekoden kan lastes ned. Lisenstekstene ligger i",
        "mappen med samme navn som pakken.",
        "",
        *(MAC_INTRO if intro is None else intro),
    ]
    if any(p.kind == "Apertium" for p in packages):
        lines += [
            "Apertium er bygget fra kildekoden (commit står under) og kopiert inn på",
            "samme måte. I skriptet «apertium» og i mode-filene er bare stiene endret.",
            "",
        ]
    for kind in KINDS:
        group = [p for p in packages if p.kind == kind]
        if not group:
            continue
        lines += [f"== {kind} ==", ""]
        for p in group:
            folder = dst / p.folder
            folder.mkdir(exist_ok=True)
            used = set()
            for t in p.texts:
                name = t.name
                while name in used:
                    name = f"{t.parent.name}-{name}"
                used.add(name)
                shutil.copyfile(t, folder / name)
            if not p.texts:
                missing.append(p)
            lines += [
                f"{p.name} {p.version}",
                f"  Lisens:    {p.license}",
                f"  Kildekode: {p.source}",
                f"  Tekster:   {', '.join(sorted(used)) if used else '(ingen lokal lisensfil)'}",
            ]
            if p.note:
                lines.append(f"  Merknad:   {p.note}")
            lines.append("")
    (dst / "Kildekode og versjoner.txt").write_text("\n".join(lines), encoding="utf-8")
    return missing
