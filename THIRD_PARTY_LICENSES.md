# Tredjepartsprogramvare

LLAs verktøykasse er fri programvare under AGPL-3.0-or-later (`LICENSE`).

## Verktøypakkene (journalistverktøyene)

Generert av `sidecar/build` (`python -m jvpack lisenser`) fra pakkene som er bygget. Hver pakke har lisenstekstene i `Lisenser/` og samme liste i «Kildekode og versjoner.txt». Systemprogrammene står med kilde og SHA-256 i `sidecar/build/binaries.json`.

Rust- og npm-delene av appen står i `src/assets/tredjepart.txt` (Om-vinduet). De to listene slås sammen i steg 6.2.

| Del | Versjon | Lisens | Type | Brukt i | Kilde |
|---|---|---|---|---|---|
| brotli | 1.2.0 | MIT | Homebrew | ocr | https://github.com/google/brotli/archive/refs/tags/v1.2.0.tar.gz |
| fontconfig | 2.18.3 | HPND-sell-variant AND Unicode-3.0 AND MIT-Modern-Variant AND MIT AND LicenseRef-Homebrew-public-domain | Homebrew | ocr | https://gitlab.freedesktop.org/fontconfig/fontconfig/-/archive/2.18.3/fontconfig-2.18.3.tar.gz |
| freetype | 2.15.0 | FTL | Homebrew | ocr | https://downloads.sourceforge.net/project/freetype/freetype2/2.15.0/freetype-2.15.0.tar.xz |
| gettext | 1.0 | GPL-3.0-or-later AND LGPL-2.1-or-later | Homebrew | ocr | https://ftpmirror.gnu.org/gettext/gettext-1.0.tar.gz |
| ghostscript | 10.08.0 | AGPL-3.0-or-later | Homebrew | ocr | https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10080/ghostpdl-10.08.0.tar.xz |
| giflib | 6.1.3 | MIT | Homebrew | ocr | https://downloads.sourceforge.net/project/giflib/giflib-6.x/giflib-6.1.3.tar.gz |
| jbig2dec | 0.20 | AGPL-3.0-or-later | Homebrew | ocr | https://github.com/ArtifexSoftware/jbig2dec/archive/refs/tags/0.20.tar.gz |
| jpeg-turbo | 3.2.0 | IJG AND Zlib AND BSD-3-Clause | Homebrew | ocr | https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0.tar.gz |
| leptonica | 1.87.0 | BSD-2-Clause | Homebrew | ocr | https://github.com/DanBloomberg/leptonica/releases/download/1.87.0/leptonica-1.87.0.tar.gz |
| libarchive | 3.8.10 | BSD-2-Clause | Homebrew | ocr | https://www.libarchive.org/downloads/libarchive-3.8.10.tar.xz |
| libb2 | 0.98.1 | CC0-1.0 | Homebrew | ocr | https://github.com/BLAKE2/libb2/releases/download/v0.98.1/libb2-0.98.1.tar.gz |
| libidn | 1.44 | GPL-2.0-or-later OR LGPL-3.0-or-later | Homebrew | ocr | https://ftpmirror.gnu.org/gnu/libidn/libidn-1.44.tar.gz |
| libpng | 1.6.59 | libpng-2.0 | Homebrew | ocr | https://downloads.sourceforge.net/project/libpng/libpng16/1.6.59/libpng-1.6.59.tar.xz |
| libtiff | 4.7.2 | libtiff | Homebrew | ocr | https://download.osgeo.org/libtiff/tiff-4.7.2.tar.gz |
| little-cms2 | 2.19.1 | MIT | Homebrew | ocr | https://downloads.sourceforge.net/project/lcms/lcms/2.19.1/lcms2-2.19.1.tar.gz |
| lz4 | 1.10.0 | BSD-2-Clause | Homebrew | ocr | https://github.com/lz4/lz4/archive/refs/tags/v1.10.0.tar.gz |
| openjpeg | 2.5.4_1 | BSD-2-Clause | Homebrew | ocr | https://github.com/uclouvain/openjpeg/archive/refs/tags/v2.5.4.tar.gz |
| tesseract | 5.5.3 | Apache-2.0 | Homebrew | ocr | https://github.com/tesseract-ocr/tesseract/archive/refs/tags/5.5.3.tar.gz |
| tesseract-lang | 4.1.0 | Apache-2.0 | Homebrew | ocr | https://github.com/tesseract-ocr/tessdata_fast/archive/refs/tags/4.1.0.tar.gz |
| webp | 1.6.0 | BSD-3-Clause | Homebrew | ocr | https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.6.0.tar.gz |
| xz | 5.8.4 | 0BSD AND GPL-2.0-or-later | Homebrew | ocr | https://github.com/tukaani-project/xz/releases/download/v5.8.4/xz-5.8.4.tar.gz |
| zstd | 1.5.7_1 | (BSD-3-Clause OR GPL-2.0-only) AND BSD-2-Clause AND MIT | Homebrew | ocr | https://github.com/facebook/zstd/archive/refs/tags/v1.5.7.tar.gz |
| bzip2 | ukjent | bzip2-1.0.6 | Kjøretid | ocr, subtitles | https://sourceware.org/bzip2/downloads.html |
| expat | 2.8.4 | MIT | Kjøretid | ocr, subtitles | https://github.com/libexpat/libexpat/releases |
| libffi | ukjent | MIT | Kjøretid | ocr, subtitles | https://github.com/libffi/libffi/releases |
| mpdecimal | 4.0.0 | BSD-2-Clause | Kjøretid | ocr, subtitles | https://www.bytereef.org/mpdecimal/download.html |
| OpenSSL | 3.5.8 | Apache-2.0 | Kjøretid | ocr, subtitles | https://github.com/openssl/openssl/releases/tag/openssl-3.5.8 |
| PyInstaller (bootloader) | 6.6.0 | GPL-2.0-or-later WITH PyInstaller-Bootloader-exception | Kjøretid | ocr, subtitles | https://github.com/pyinstaller/pyinstaller/releases/tag/v6.6.0 |
| Python | 3.12.14 | PSF-2.0 | Kjøretid | ocr, subtitles | https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz (bygget av python-build-standalone: https://github.com/astral-sh/python-build-standalone) |
| SQLite | 3.53.1 | blessing (public domain) | Kjøretid | ocr, subtitles | https://www.sqlite.org/download.html |
| xz (liblzma) | ukjent | 0BSD | Kjøretid | ocr, subtitles | https://github.com/tukaani-project/xz/releases |
| annotated-types | 0.8.0 | MIT | Python-pakke | ocr | https://pypi.org/project/annotated-types/0.8.0/#files (kildekodearkiv: https://github.com/annotated-types/annotated-types) |
| attrs | 26.1.0 | MIT | Python-pakke | ocr | https://pypi.org/project/attrs/26.1.0/#files (kildekodearkiv: https://github.com/python-attrs/attrs) |
| cffi | 2.1.1 | MIT-0 | Python-pakke | ocr | https://pypi.org/project/cffi/2.1.1/#files (kildekodearkiv: https://github.com/python-cffi/cffi) |
| charset-normalizer | 3.5.2 | MIT | Python-pakke | ocr | https://pypi.org/project/charset-normalizer/3.5.2/#files (kildekodearkiv: https://github.com/jawah/charset_normalizer) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Python-pakke | ocr | https://pypi.org/project/cryptography/50.0.2/#files (kildekodearkiv: https://github.com/pyca/cryptography/) |
| defusedxml | 0.7.1 | PSFL | Python-pakke | ocr | https://pypi.org/project/defusedxml/0.7.1/#files |
| fonttools | 4.67.0 | MIT | Python-pakke | ocr | https://pypi.org/project/fonttools/4.67.0/#files |
| fpdf2 | 2.8.9 | LGPL-3.0-only | Python-pakke | ocr | https://pypi.org/project/fpdf2/2.8.9/#files (kildekodearkiv: https://github.com/py-pdf/fpdf2) |
| img2pdf | 0.6.3 | GNU Lesser General Public License v3 (LGPLv3) | Python-pakke | ocr | https://pypi.org/project/img2pdf/0.6.3/#files |
| jsonschema | 4.26.0 | MIT | Python-pakke | ocr | https://pypi.org/project/jsonschema/4.26.0/#files (kildekodearkiv: https://github.com/python-jsonschema/jsonschema) |
| jsonschema-specifications | 2025.9.1 | MIT | Python-pakke | ocr | https://pypi.org/project/jsonschema-specifications/2025.9.1/#files (kildekodearkiv: https://github.com/python-jsonschema/jsonschema-specifications) |
| lxml | 6.1.3 | BSD-3-Clause | Python-pakke | ocr | https://pypi.org/project/lxml/6.1.3/#files (kildekodearkiv: https://github.com/lxml/lxml) |
| markdown-it-py | 4.2.0 | MIT License | Python-pakke | ocr | https://pypi.org/project/markdown-it-py/4.2.0/#files |
| mdurl | 0.1.2 | MIT License | Python-pakke | ocr | https://pypi.org/project/mdurl/0.1.2/#files |
| ocrmypdf | 17.13.0 | MPL-2.0 | Python-pakke | ocr | https://pypi.org/project/ocrmypdf/17.13.0/#files (kildekodearkiv: https://github.com/ocrmypdf/OCRmyPDF) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Python-pakke | ocr | https://pypi.org/project/packaging/26.3/#files (kildekodearkiv: https://github.com/pypa/packaging) |
| pdfminer.six | 20260107 | MIT | Python-pakke | ocr | https://pypi.org/project/pdfminer.six/20260107/#files |
| pikepdf | 10.17.0 | MPL-2.0 | Python-pakke | ocr | https://pypi.org/project/pikepdf/10.17.0/#files (kildekodearkiv: https://github.com/pikepdf/pikepdf) |
| pillow | 13.0.0 | MIT-CMU | Python-pakke | ocr | https://pypi.org/project/pillow/13.0.0/#files (kildekodearkiv: https://github.com/python-pillow/Pillow) |
| pluggy | 1.7.0 | MIT | Python-pakke | ocr | https://pypi.org/project/pluggy/1.7.0/#files (kildekodearkiv: https://github.com/pytest-dev/pluggy) |
| pydantic | 2.14.1 | MIT | Python-pakke | ocr | https://pypi.org/project/pydantic/2.14.1/#files (kildekodearkiv: https://github.com/pydantic/pydantic) |
| pydantic_core | 2.50.1 | MIT | Python-pakke | ocr | https://pypi.org/project/pydantic_core/2.50.1/#files (kildekodearkiv: https://github.com/pydantic/pydantic/tree/main/pydantic-core) |
| Pygments | 2.21.0 | BSD-2-Clause | Python-pakke | ocr | https://pypi.org/project/Pygments/2.21.0/#files (kildekodearkiv: https://github.com/pygments/pygments) |
| pymupdf | 1.28.2 | Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License | Python-pakke | ocr | https://pypi.org/project/pymupdf/1.28.2/#files (kildekodearkiv: https://github.com/pymupdf/pymupdf) |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0, dependency licenses | Python-pakke | ocr | https://pypi.org/project/pypdfium2/5.14.0/#files (kildekodearkiv: https://github.com/pypdfium2-team/pypdfium2) |
| referencing | 0.37.0 | MIT | Python-pakke | ocr | https://pypi.org/project/referencing/0.37.0/#files (kildekodearkiv: https://github.com/python-jsonschema/referencing) |
| rich | 15.0.0 | MIT | Python-pakke | ocr | https://pypi.org/project/rich/15.0.0/#files |
| rpds-py | 2026.9.1 | MIT | Python-pakke | ocr | https://pypi.org/project/rpds-py/2026.9.1/#files (kildekodearkiv: https://github.com/crate-py/rpds) |
| typing-inspection | 0.4.4 | MIT | Python-pakke | ocr | https://pypi.org/project/typing-inspection/0.4.4/#files (kildekodearkiv: https://github.com/pydantic/typing-inspection) |
| typing_extensions | 4.16.0 | PSF-2.0 | Python-pakke | ocr | https://pypi.org/project/typing_extensions/4.16.0/#files (kildekodearkiv: https://github.com/python/typing_extensions) |
| uharfbuzz | 0.56.3 | Apache License 2.0 | Python-pakke | ocr | https://pypi.org/project/uharfbuzz/0.56.3/#files |
