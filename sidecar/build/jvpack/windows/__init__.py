# SPDX-License-Identifier: AGPL-3.0-or-later
"""Windows (x86_64-pc-windows-msvc) packaging: pinned downloads, PE imports, .zip.

Runde B. The packages are built on `windows-latest` in GitHub Actions
(.github/workflows/jv-windows-pakker.yml) and uploaded as workflow artefacts
only; John Inge uploads them to the release repo himself.

Layout of a Windows package (the archive has no top folder):

    jv-package.json
    jv-<id>/jv.exe                      PyInstaller onedir (command line only)
    jv-<id>/_internal/                  Python, the tool and its packages
    jv-<id>/programmer/<gruppe>/        bundled programs with the DLLs they load
                                        (ffmpeg, exiftool, tesseract, poppler)
    jv-<id>/data/tessdata/              Tesseract language data (ocr)
    Lisenser/                           licence texts and «Kildekode og versjoner.txt»

Every program comes from a pinned download with a known SHA-256
(sources.py). Only the files a program needs are copied: the DLLs it loads
(pe.py) and the data it reads. Each copied DLL must map to a component with a
known, free licence (components.py), otherwise the build stops.
"""
