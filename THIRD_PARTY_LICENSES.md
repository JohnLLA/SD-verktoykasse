# Tredjepartsprogramvare

LLAs verktøykasse er fri programvare under AGPL-3.0-or-later (`LICENSE`).

## Verktøypakkene (journalistverktøyene)

Generert av `sidecar/build` (`python -m jvpack lisenser`) fra pakkene som er bygget. Hver pakke har lisenstekstene i `Lisenser/` og samme liste i «Kildekode og versjoner.txt». Systemprogrammene står med kilde og SHA-256 i `sidecar/build/binaries.json`.

Rust- og npm-delene av appen står i `src/assets/tredjepart.txt` (Om-vinduet). De to listene slås sammen av byggmester (docs/brief-jv-distribusjon.md).

| Del | Versjon | Lisens | Type | Plattform | Brukt i | Kilde |
|---|---|---|---|---|---|---|
| apertium | 3.9.12 | GPL-2.0-or-later | Apertium | Mac | nynorsk | https://github.com/apertium/apertium (commit d8dfb942e31d740e938967fb18b017734b339f0d) |
| apertium-lex-tools | 0.5.0 | GPL-3.0-or-later | Apertium | Mac | nynorsk | https://github.com/apertium/apertium-lex-tools (commit 1ccefa6269ad1b3f1c0a0ef17f14e3d9c7c346ea) |
| apertium-nno | 1.5.0 | GPL-2.0-or-later | Apertium | Mac | nynorsk | https://github.com/apertium/apertium-nno (commit 2efb61642310ca504b9f1b2ed29fc6bb7a030b13) |
| apertium-nno-nob | 1.6.0 | GPL-2.0-or-later | Apertium | Mac | nynorsk | https://github.com/apertium/apertium-nno-nob (commit af921d87acad00f45e79a5b7f17d71068adb5ec8) |
| apertium-nob | 1.5.0 | GPL-2.0-or-later | Apertium | Mac | nynorsk | https://github.com/apertium/apertium-nob (commit 3d63c61e55209cd847c8ef4b863715036cce04bf) |
| apertium-separable | 0.7.1 | GPL-3.0-or-later | Apertium | Mac | nynorsk | https://github.com/apertium/apertium-separable (commit 18045e4da12c5f8dd7373c842cc93e38291d1826) |
| cg3 | 1.7.0.13898 | GPL-3.0-or-later | Apertium | Mac | nynorsk | https://github.com/GrammarSoft/cg3 (commit 0250250fe98241d681fd8081f2b6495c52729d5b) |
| lttoolbox | 3.8.4 | GPL-2.0-or-later | Apertium | Mac | nynorsk | https://github.com/apertium/lttoolbox (commit ed9b682b9e3e90d4207882be2caf54845619a255) |
| brotli | 1.2.0 | MIT | Homebrew | Mac | redact | https://github.com/google/brotli/archive/refs/tags/v1.2.0.tar.gz |
| dav1d | 1.5.4 | BSD-2-Clause | Homebrew | Mac | keyframes, loudness | https://code.videolan.org/videolan/dav1d/-/archive/1.5.4/dav1d-1.5.4.tar.bz2 |
| exiftool | 13.55_1 | Artistic-1.0-Perl OR GPL-1.0-or-later (samme vilkår som Perl) | Homebrew | Mac | metadata | https://downloads.sourceforge.net/project/exiftool/Image-ExifTool-13.55.tar.gz |
| ffmpeg | 9.0.2_1 | GPL-3.0-or-later | Homebrew | Mac | keyframes, loudness | https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz |
| fontconfig | 2.18.3 | HPND-sell-variant AND Unicode-3.0 AND MIT-Modern-Variant AND MIT AND LicenseRef-Homebrew-public-domain | Homebrew | Mac | redact | https://gitlab.freedesktop.org/fontconfig/fontconfig/-/archive/2.18.3/fontconfig-2.18.3.tar.gz |
| freetype | 2.15.0 | FTL | Homebrew | Mac | redact | https://downloads.sourceforge.net/project/freetype/freetype2/2.15.0/freetype-2.15.0.tar.xz |
| gettext | 1.0 | GPL-3.0-or-later AND LGPL-2.1-or-later | Homebrew | Mac | redact | https://ftpmirror.gnu.org/gettext/gettext-1.0.tar.gz |
| giflib | 6.1.3 | MIT | Homebrew | Mac | ocr | https://downloads.sourceforge.net/project/giflib/giflib-6.x/giflib-6.1.3.tar.gz |
| glib | 2.90.1 | LGPL-2.1-or-later | Homebrew | Mac | redact | https://download.gnome.org/sources/glib/2.90/glib-2.90.1.tar.xz |
| gpgme | 2.2.0 | LGPL-2.1-or-later | Homebrew | Mac | redact | https://www.gnupg.org/ftp/gcrypt/gpgme/gpgme-2.2.0.tar.bz2 |
| gpgmepp | 2.2.0 | LGPL-2.1-or-later | Homebrew | Mac | redact | https://www.gnupg.org/ftp/gcrypt/gpgmepp/gpgmepp-2.2.0.tar.xz |
| graphite2 | 1.3.15 | GPL-2.0-or-later OR LGPL-2.1-or-later OR MPL-1.1+ | Homebrew | Mac | redact | https://github.com/silnrsi/graphite/releases/download/1.3.15/graphite2-1.3.15.tgz |
| harfbuzz | 14.6.0 | MIT | Homebrew | Mac | redact | https://github.com/harfbuzz/harfbuzz/releases/download/14.6.0/harfbuzz-14.6.0.tar.xz |
| icu4c@78 | 78.3 | ICU | Homebrew | Mac | nynorsk | https://github.com/unicode-org/icu/releases/download/release-78.3/icu4c-78.3-sources.tgz |
| jpeg-turbo | 3.2.0 | IJG AND Zlib AND BSD-3-Clause | Homebrew | Mac | ocr, redact | https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0.tar.gz |
| lame | 4.0 | LGPL-2.0-or-later | Homebrew | Mac | keyframes, loudness | https://downloads.sourceforge.net/project/lame/lame/4.0/lame-4.0.tar.gz |
| leptonica | 1.87.0 | BSD-2-Clause | Homebrew | Mac | ocr | https://github.com/DanBloomberg/leptonica/releases/download/1.87.0/leptonica-1.87.0.tar.gz |
| libarchive | 3.8.10 | BSD-2-Clause | Homebrew | Mac | ocr | https://www.libarchive.org/downloads/libarchive-3.8.10.tar.xz |
| libassuan | 3.0.2 | LGPL-2.1-or-later AND GPL-3.0-or-later AND FSFULLR | Homebrew | Mac | redact | https://gnupg.org/ftp/gcrypt/libassuan/libassuan-3.0.2.tar.bz2 |
| libb2 | 0.98.1 | CC0-1.0 | Homebrew | Mac | ocr | https://github.com/BLAKE2/libb2/releases/download/v0.98.1/libb2-0.98.1.tar.gz |
| libgpg-error | 1.61 | LGPL-2.1-or-later | Homebrew | Mac | redact | https://gnupg.org/ftp/gcrypt/libgpg-error/libgpg-error-1.61.tar.bz2 |
| libpng | 1.6.59 | libpng-2.0 | Homebrew | Mac | ocr, redact | https://downloads.sourceforge.net/project/libpng/libpng16/1.6.59/libpng-1.6.59.tar.xz |
| libtiff | 4.7.2 | libtiff | Homebrew | Mac | ocr, redact | https://download.osgeo.org/libtiff/tiff-4.7.2.tar.gz |
| libvmaf | 3.2.1 | BSD-2-Clause-Patent | Homebrew | Mac | keyframes, loudness | https://github.com/Netflix/vmaf/archive/refs/tags/v3.2.1.tar.gz |
| libvpx | 1.17.0 | BSD-3-Clause | Homebrew | Mac | keyframes, loudness | https://github.com/webmproject/libvpx/archive/refs/tags/v1.17.0.tar.gz |
| little-cms2 | 2.19.1 | MIT | Homebrew | Mac | redact | https://downloads.sourceforge.net/project/lcms/lcms/2.19.1/lcms2-2.19.1.tar.gz |
| lz4 | 1.10.0 | BSD-2-Clause | Homebrew | Mac | ocr | https://github.com/lz4/lz4/archive/refs/tags/v1.10.0.tar.gz |
| mpg123 | 1.33.7 | LGPL-2.1-only | Homebrew | Mac | keyframes, loudness | https://www.mpg123.de/download/mpg123-1.33.7.tar.bz2 |
| nspr | 4.40 | MPL-2.0 | Homebrew | Mac | redact | https://archive.mozilla.org/pub/nspr/releases/v4.40/src/nspr-4.40.tar.gz |
| nss | 3.131 | MPL-2.0 | Homebrew | Mac | redact | https://ftp.mozilla.org/pub/security/nss/releases/NSS_3_131_RTM/src/nss-3.131.tar.gz |
| openjpeg | 2.5.4_1 | BSD-2-Clause | Homebrew | Mac | ocr, redact | https://github.com/uclouvain/openjpeg/archive/refs/tags/v2.5.4.tar.gz |
| openssl@4 | 4.0.3 | Apache-2.0 | Homebrew | Mac | keyframes, loudness | https://github.com/openssl/openssl/releases/download/openssl-4.0.3/openssl-4.0.3.tar.gz |
| opus | 1.6.1 | BSD-3-Clause | Homebrew | Mac | keyframes, loudness | https://ftp.osuosl.org/pub/xiph/releases/opus/opus-1.6.1.tar.gz |
| pcre2 | 10.49 | BSD-3-Clause | Homebrew | Mac | redact | https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.49/pcre2-10.49.tar.bz2 |
| poppler | 26.10.0 | GPL-2.0-only OR GPL-3.0-only | Homebrew | Mac | redact | https://poppler.freedesktop.org/poppler-26.10.0.tar.xz |
| svt-av1 | 4.2.0 | BSD-3-Clause | Homebrew | Mac | keyframes, loudness | https://gitlab.com/AOMediaCodec/SVT-AV1/-/archive/v4.2.0/SVT-AV1-v4.2.0.tar.bz2 |
| tesseract | 5.5.3 | Apache-2.0 | Homebrew | Mac | ocr | https://github.com/tesseract-ocr/tesseract/archive/refs/tags/5.5.3.tar.gz |
| tesseract-lang | 4.1.0 | Apache-2.0 | Homebrew | Mac | ocr | https://github.com/tesseract-ocr/tessdata_fast/archive/refs/tags/4.1.0.tar.gz |
| webp | 1.6.0 | BSD-3-Clause | Homebrew | Mac | ocr, redact | https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.6.0.tar.gz |
| x264 | r3222 | GPL-2.0-or-later | Homebrew | Mac | keyframes, loudness | https://code.videolan.org/videolan/x264.git |
| x265 | 4.3 | GPL-2.0-or-later | Homebrew | Mac | keyframes, loudness | https://github.com/Multicorewareinc/x265/releases/download/4.3/x265_4.3.tar.gz |
| xz | 5.8.4 | 0BSD AND GPL-2.0-or-later | Homebrew | Mac | keyframes, loudness, ocr, redact | https://github.com/tukaani-project/xz/releases/download/v5.8.4/xz-5.8.4.tar.gz |
| zstd | 1.5.7_1 | (BSD-3-Clause OR GPL-2.0-only) AND BSD-2-Clause AND MIT | Homebrew | Mac | ocr, redact | https://github.com/facebook/zstd/archive/refs/tags/v1.5.7.tar.gz |
| bzip2 | ukjent | bzip2-1.0.6 | Kjøretid | Mac, Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://sourceware.org/bzip2/downloads.html |
| expat | 2.8.4 | MIT | Kjøretid | Mac | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/libexpat/libexpat/releases |
| Expat | 2.7.1 | MIT | Kjøretid | Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/libexpat/libexpat/releases |
| libffi | ukjent | MIT | Kjøretid | Mac, Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/libffi/libffi/releases |
| Microsoft Visual C++ Redistributable (vcruntime140, msvcp140) | 14.x | LicenseRef-Microsoft-Visual-C-Redistributable | Kjøretid | Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files |
| mpdecimal | 4.0.0 | BSD-2-Clause | Kjøretid | Mac | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://www.bytereef.org/mpdecimal/download.html |
| mpdecimal | 2.5.1 | BSD-2-Clause | Kjøretid | Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://www.bytereef.org/mpdecimal/download.html |
| OpenSSL | 3.5.8 | Apache-2.0 | Kjøretid | Mac | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/openssl/openssl/releases/tag/openssl-3.5.8 |
| OpenSSL | 3.0.16 | Apache-2.0 | Kjøretid | Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/openssl/openssl/releases |
| PyInstaller (bootloader) | 6.6.0 | GPL-2.0-or-later WITH PyInstaller-Bootloader-exception | Kjøretid | Mac | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/pyinstaller/pyinstaller/releases/tag/v6.6.0 |
| PyInstaller (bootloader) | 6.22.3 | GPL-2.0-or-later WITH PyInstaller-Bootloader-exception | Kjøretid | Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/pyinstaller/pyinstaller/releases/tag/v6.22.3 |
| Python | 3.12.14 | PSF-2.0 | Kjøretid | Mac | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz (bygget av python-build-standalone: https://github.com/astral-sh/python-build-standalone) |
| Python | 3.12.10 | PSF-2.0 | Kjøretid | Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tar.xz (bygget av python-build-standalone: https://github.com/astral-sh/python-build-standalone) |
| SQLite | 3.53.1 | blessing (public domain) | Kjøretid | Mac | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://www.sqlite.org/download.html |
| xz (liblzma) | ukjent | 0BSD | Kjøretid | Mac, Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://github.com/tukaani-project/xz/releases |
| zlib | ukjent | Zlib | Kjøretid | Windows | compare, datawrapper, keyframes, loudness, metadata, nynorsk, ocr, pdf-tables, redact, subtitles | https://zlib.net/ |
| altgraph | 0.17.5 | MIT | Python-pakke | Windows | ocr | https://pypi.org/project/altgraph/0.17.5/#files (kildekodearkiv: https://github.com/ronaldoussoren/altgraph) |
| annotated-types | 0.8.0 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/annotated-types/0.8.0/#files (kildekodearkiv: https://github.com/annotated-types/annotated-types) |
| attrs | 26.1.0 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/attrs/26.1.0/#files (kildekodearkiv: https://github.com/python-attrs/attrs) |
| cffi | 2.1.1 | MIT-0 | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/cffi/2.1.1/#files (kildekodearkiv: https://github.com/python-cffi/cffi) |
| charset-normalizer | 3.5.2 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/charset-normalizer/3.5.2/#files (kildekodearkiv: https://github.com/jawah/charset_normalizer) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/cryptography/50.0.2/#files (kildekodearkiv: https://github.com/pyca/cryptography/) |
| defusedxml | 0.7.1 | PSFL | Python-pakke | Mac, Windows | compare, datawrapper, keyframes, metadata, ocr, pdf-tables, redact | https://pypi.org/project/defusedxml/0.7.1/#files |
| et_xmlfile | 2.0.0 | MIT | Python-pakke | Mac, Windows | datawrapper, pdf-tables | https://pypi.org/project/et_xmlfile/2.0.0/#files (kildekodearkiv: https://foss.heptapod.net/openpyxl/et_xmlfile) |
| fonttools | 4.67.0 | MIT | Python-pakke | Mac, Windows | compare, ocr, pdf-tables, redact | https://pypi.org/project/fonttools/4.67.0/#files |
| fpdf2 | 2.8.9 | LGPL-3.0-only | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/fpdf2/2.8.9/#files (kildekodearkiv: https://github.com/py-pdf/fpdf2) |
| img2pdf | 0.6.3 | GNU Lesser General Public License v3 (LGPLv3) | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/img2pdf/0.6.3/#files |
| jsonschema | 4.26.0 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/jsonschema/4.26.0/#files (kildekodearkiv: https://github.com/python-jsonschema/jsonschema) |
| jsonschema-specifications | 2025.9.1 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/jsonschema-specifications/2025.9.1/#files (kildekodearkiv: https://github.com/python-jsonschema/jsonschema-specifications) |
| lxml | 6.1.3 | BSD-3-Clause | Python-pakke | Mac, Windows | compare, datawrapper, metadata, nynorsk, ocr, pdf-tables, redact | https://pypi.org/project/lxml/6.1.3/#files (kildekodearkiv: https://github.com/lxml/lxml) |
| markdown-it-py | 4.2.0 | MIT License | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/markdown-it-py/4.2.0/#files |
| mdurl | 0.1.2 | MIT License | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/mdurl/0.1.2/#files |
| ocrmypdf | 17.13.0 | MPL-2.0 | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/ocrmypdf/17.13.0/#files (kildekodearkiv: https://github.com/ocrmypdf/OCRmyPDF) |
| openpyxl | 3.1.5 | MIT | Python-pakke | Mac, Windows | datawrapper, pdf-tables | https://pypi.org/project/openpyxl/3.1.5/#files (kildekodearkiv: https://foss.heptapod.net/openpyxl/openpyxl) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/packaging/26.3/#files (kildekodearkiv: https://github.com/pypa/packaging) |
| pdfminer.six | 20260107 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/pdfminer.six/20260107/#files |
| pefile | 2024.8.26 | MIT | Python-pakke | Windows | ocr | https://pypi.org/project/pefile/2024.8.26/#files |
| pikepdf | 10.17.0 | MPL-2.0 | Python-pakke | Mac, Windows | metadata, ocr | https://pypi.org/project/pikepdf/10.17.0/#files (kildekodearkiv: https://github.com/pikepdf/pikepdf) |
| pillow | 13.0.0 | MIT-CMU | Python-pakke | Mac, Windows | compare, datawrapper, keyframes, metadata, ocr, pdf-tables, redact | https://pypi.org/project/pillow/13.0.0/#files (kildekodearkiv: https://github.com/python-pillow/Pillow) |
| pluggy | 1.7.0 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/pluggy/1.7.0/#files (kildekodearkiv: https://github.com/pytest-dev/pluggy) |
| pycparser | 3.11 | BSD-3-Clause | Python-pakke | Windows | ocr | https://pypi.org/project/pycparser/3.11/#files |
| pydantic | 2.14.1 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/pydantic/2.14.1/#files (kildekodearkiv: https://github.com/pydantic/pydantic) |
| pydantic_core | 2.50.1 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/pydantic_core/2.50.1/#files (kildekodearkiv: https://github.com/pydantic/pydantic/tree/main/pydantic-core) |
| Pygments | 2.21.0 | BSD-2-Clause | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/Pygments/2.21.0/#files (kildekodearkiv: https://github.com/pygments/pygments) |
| pyinstaller | 6.22.3 | GNU General Public License v2 (GPLv2) | Python-pakke | Windows | ocr | https://pypi.org/project/pyinstaller/6.22.3/#files (kildekodearkiv: https://github.com/pyinstaller/pyinstaller) |
| pymupdf | 1.28.2 | Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License | Python-pakke | Mac, Windows | compare, ocr, pdf-tables, redact | https://pypi.org/project/pymupdf/1.28.2/#files (kildekodearkiv: https://github.com/pymupdf/pymupdf) |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0, dependency licenses | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/pypdfium2/5.14.0/#files (kildekodearkiv: https://github.com/pypdfium2-team/pypdfium2) |
| python-docx | 1.2.0 | MIT | Python-pakke | Mac, Windows | compare, nynorsk | https://pypi.org/project/python-docx/1.2.0/#files (kildekodearkiv: https://github.com/python-openxml/python-docx) |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause | Python-pakke | Windows | ocr | https://pypi.org/project/pywin32-ctypes/0.2.3/#files |
| referencing | 0.37.0 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/referencing/0.37.0/#files (kildekodearkiv: https://github.com/python-jsonschema/referencing) |
| rich | 15.0.0 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/rich/15.0.0/#files |
| rpds-py | 2026.9.1 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/rpds-py/2026.9.1/#files (kildekodearkiv: https://github.com/crate-py/rpds) |
| setuptools | 84.2.0 | MIT | Python-pakke | Windows | ocr | https://pypi.org/project/setuptools/84.2.0/#files (kildekodearkiv: https://github.com/pypa/setuptools) |
| typing-inspection | 0.4.4 | MIT | Python-pakke | Mac, Windows | ocr | https://pypi.org/project/typing-inspection/0.4.4/#files (kildekodearkiv: https://github.com/pydantic/typing-inspection) |
| typing_extensions | 4.16.0 | PSF-2.0 | Python-pakke | Mac, Windows | compare, nynorsk, ocr, pdf-tables, redact | https://pypi.org/project/typing_extensions/4.16.0/#files (kildekodearkiv: https://github.com/python/typing_extensions) |
| uharfbuzz | 0.56.3 | Apache License 2.0 | Python-pakke | Mac, Windows | compare, ocr, pdf-tables, redact | https://pypi.org/project/uharfbuzz/0.56.3/#files |
| xlrd | 2.0.2 | BSD | Python-pakke | Mac, Windows | datawrapper | https://pypi.org/project/xlrd/2.0.2/#files |
| Brotli | ukjent | MIT | Windows-bibliotek | Windows | ocr | https://github.com/google/brotli/releases |
| Expat | ukjent | MIT | Windows-bibliotek | Windows | ocr | https://github.com/libexpat/libexpat/releases |
| FreeType | ukjent | FTL OR GPL-2.0-or-later | Windows-bibliotek | Windows | redact | https://download.savannah.gnu.org/releases/freetype/ |
| GCC-kjøretid (libgcc, libstdc++, libgomp) | ukjent | GPL-3.0-or-later WITH GCC-exception-3.1 | Windows-bibliotek | Windows | nynorsk, ocr | https://gcc.gnu.org/ |
| gettext (libintl) | ukjent | LGPL-2.1-or-later | Windows-bibliotek | Windows | ocr | https://ftp.gnu.org/gnu/gettext/ |
| giflib | ukjent | MIT | Windows-bibliotek | Windows | ocr | https://sourceforge.net/projects/giflib/files/ |
| GNU libiconv | ukjent | LGPL-2.1-or-later | Windows-bibliotek | Windows | nynorsk, ocr | https://ftp.gnu.org/gnu/libiconv/ |
| ICU | ukjent | Unicode-3.0 | Windows-bibliotek | Windows | nynorsk, redact | https://github.com/unicode-org/icu/releases |
| JBIG-KIT | ukjent | GPL-2.0-or-later | Windows-bibliotek | Windows | ocr | https://www.cl.cam.ac.uk/~mgk25/jbigkit/ |
| Leptonica | ukjent | BSD-2-Clause | Windows-bibliotek | Windows | ocr | https://github.com/DanBloomberg/leptonica/releases |
| LERC | ukjent | Apache-2.0 | Windows-bibliotek | Windows | ocr, redact | https://github.com/Esri/lerc/releases |
| libarchive | ukjent | BSD-2-Clause | Windows-bibliotek | Windows | ocr | https://github.com/libarchive/libarchive/releases |
| libb2 (BLAKE2) | ukjent | CC0-1.0 | Windows-bibliotek | Windows | ocr | https://github.com/BLAKE2/libb2/releases |
| libcurl | ukjent | curl | Windows-bibliotek | Windows | ocr, redact | https://curl.se/download.html |
| libdeflate | ukjent | MIT | Windows-bibliotek | Windows | ocr, redact | https://github.com/ebiggers/libdeflate/releases |
| libidn2 | ukjent | LGPL-3.0-or-later OR GPL-2.0-or-later | Windows-bibliotek | Windows | ocr | https://ftp.gnu.org/gnu/libidn/ |
| libjpeg-turbo | ukjent | IJG AND BSD-3-Clause AND Zlib | Windows-bibliotek | Windows | ocr, redact | https://github.com/libjpeg-turbo/libjpeg-turbo/releases |
| libpng | ukjent | libpng-2.0 | Windows-bibliotek | Windows | ocr, redact | https://github.com/pnggroup/libpng/releases |
| libpsl | ukjent | MIT | Windows-bibliotek | Windows | ocr, redact | https://github.com/rockdaboot/libpsl/releases |
| libssh2 | ukjent | BSD-3-Clause | Windows-bibliotek | Windows | ocr, redact | https://libssh2.org/download/ |
| libtiff | ukjent | libtiff | Windows-bibliotek | Windows | ocr, redact | https://download.osgeo.org/libtiff/ |
| libunistring | ukjent | LGPL-3.0-or-later OR GPL-2.0-or-later | Windows-bibliotek | Windows | ocr | https://ftp.gnu.org/gnu/libunistring/ |
| libwebp | ukjent | BSD-3-Clause | Windows-bibliotek | Windows | ocr | https://github.com/webmproject/libwebp/releases |
| libxml2 | ukjent | MIT | Windows-bibliotek | Windows | nynorsk | https://gitlab.gnome.org/GNOME/libxml2/-/releases |
| Little CMS | ukjent | MIT | Windows-bibliotek | Windows | redact | https://github.com/mm2/Little-CMS/releases |
| lttoolbox (liblttoolbox) | ukjent | GPL-2.0-or-later | Windows-bibliotek | Windows | nynorsk | https://github.com/apertium/lttoolbox |
| LZ4 | ukjent | BSD-2-Clause | Windows-bibliotek | Windows | ocr | https://github.com/lz4/lz4/releases |
| Microsoft Visual C++ Redistributable (vcruntime140, msvcp140) | ukjent | LicenseRef-Microsoft-Visual-C-Redistributable | Windows-bibliotek | Windows | redact | https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files |
| OpenJPEG | ukjent | BSD-2-Clause | Windows-bibliotek | Windows | ocr, redact | https://github.com/uclouvain/openjpeg/releases |
| OpenSSL | ukjent | Apache-2.0 | Windows-bibliotek | Windows | redact | https://github.com/openssl/openssl/releases |
| SQLite | ukjent | blessing (public domain) | Windows-bibliotek | Windows | nynorsk | https://www.sqlite.org/download.html |
| VISL CG-3 (libcg3) | ukjent | GPL-3.0-or-later | Windows-bibliotek | Windows | nynorsk | https://github.com/GrammarSoft/cg3 |
| winpthreads (mingw-w64) | ukjent | MIT AND BSD-3-Clause | Windows-bibliotek | Windows | nynorsk, ocr | https://github.com/mingw-w64/mingw-w64 |
| Zstandard | ukjent | BSD-3-Clause OR GPL-2.0-only | Windows-bibliotek | Windows | ocr, redact | https://github.com/facebook/zstd/releases |
| Apertium for Windows (apertium-all-dev) | 2026-10-14 | GPL-2.0-or-later AND GPL-3.0-or-later | Windows-program | Windows | nynorsk | https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-lttoolbox-ed9b682b9e3e.tar.gz https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-apertium-d8dfb942e31d.tar.gz https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-apertium-lex-tools-1ccefa6269ad.tar.gz https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-apertium-separable-18045e4da12c.tar.gz https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-cg3-0250250fe982.tar.gz |
| Apertium-språkdata (apertium-nno-nob) | 1.6.0 | GPL-2.0-or-later | Windows-program | Windows | nynorsk | https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-apertium-nob-3d63c61e5520.tar.gz https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-apertium-nno-2efb61642310.tar.gz https://github.com/JohnLLA/sd-verktoy-releases/releases/download/kilder-apertium-windows/kilde-apertium-nno-nob-af921d87acad.tar.gz |
| ExifTool (Windows-pakke) | 13.59 | Artistic-1.0-Perl OR GPL-1.0-or-later | Windows-program | Windows | metadata | https://downloads.sourceforge.net/project/exiftool/Image-ExifTool-13.59.tar.gz (Strawberry Perl: https://strawberryperl.com/releases.html) |
| FFmpeg (gyan.dev essentials) | 9.0.2 | GPL-3.0-or-later | Windows-program | Windows | keyframes, loudness | https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz (commit 946fcce07b; bibliotekene og versjonene står i README.txt) |
| poppler (poppler-windows, conda-forge) | 26.09.0-0 | GPL-2.0-only OR GPL-3.0-only | Windows-program | Windows | redact | https://poppler.freedesktop.org/poppler-26.09.0.tar.xz (byggeoppskrift: https://github.com/conda-forge/poppler-feedstock) |
| Tesseract OCR (UB Mannheim) | 5.5.3.20260724 | Apache-2.0 | Windows-program | Windows | ocr | https://github.com/tesseract-ocr/tesseract/archive/refs/tags/5.5.3.tar.gz (byggeoppsett: https://github.com/UB-Mannheim/tesseract/tree/v5.5.3.20260724) |
| Tesseract-språkdata eng (tessdata_fast) | 4.1.0 | Apache-2.0 | Windows-program | Windows | ocr | https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0 |
| Tesseract-språkdata nor (tessdata_fast) | 4.1.0 | Apache-2.0 | Windows-program | Windows | ocr | https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0 |
| Tesseract-språkdata osd (tessdata_fast) | 4.1.0 | Apache-2.0 | Windows-program | Windows | ocr | https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0 |
