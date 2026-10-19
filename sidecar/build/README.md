# sidecar/build – verktøypakkene

Bygger én nedlastbar pakke per journalistverktøy og plattform (`docs/spesifikasjon-journalistverktoy.md`).
Spiken (steg 6.1) dekker `subtitles` og `ocr` for Mac. Funnene står i `docs/spike-sidecar.md`.

## Kommandoer

```
sidecar/build/bygg-mac.sh subtitles,ocr          # bygg, signer, pakk og prøvekjør (Mac, Apple Silicon)
cd sidecar/jv
PYTHONPATH=../build uv run python -m jvpack katalog lag --test-key   # tools.json + tools.json.sig (TESTNØKKEL)
PYTHONPATH=../build uv run python -m jvpack lisenser                 # THIRD_PARTY_LICENSES.md
JV_PACKAGE_DIR=<utpakket pakke> PYTHONPATH=../build \
  uv run pytest -p pytest_packaged verktoy/<id>                      # verktøyets tester mot pakken, uten nett
```

Med `UV_OFFLINE=1` henter `bygg-mac.sh` ingenting fra nett (pakkene må ligge i uv-cachen).
Resultatet havner i `sidecar/build/out/` (utenfor git): `dist/jv-<id>-<versjon>-aarch64-apple-darwin.tar.gz`,
`dist/tools.json(.sig)` og `bygg-oppsummering.json`.

## Innhold i en pakke

Arkivet har ingen toppmappe:

| Sti | Innhold |
|---|---|
| `jv-package.json` | id, versjon, plattform, `entry`, mapper til `PATH`, miljøvariabler (relative stier), bunter som skal ha gyldig kodesignatur |
| `jv-<id>.app/Contents/MacOS/jv` | PyInstaller (onedir som app-bunt, bare kommandolinje, uten tkinter) |
| `jv-<id>.app/Contents/Helpers/` | systemprogrammene (tesseract, gs …) |
| `jv-<id>.app/Contents/Frameworks/jv-lib/` | bibliotekene deres, med omskrevne stier |
| `jv-<id>.app/Contents/Resources/` | data (tessdata, Ghostscript-ressurser, fontconfig) |
| `Lisenser/` | lisenstekster og «Kildekode og versjoner.txt» |

`jv --version` skriver JSON med id og versjon og kjører hvert innebygde program én gang; det er
prøvekjøringen appen gjør før en pakke tas i bruk. `jv <id> <inngang…> --out <mappe> [valg]` er den
vanlige kontrakten (rapport som JSON på stdout, fremdrift som JSON-linjer på stderr, kode 1/2 ved feil).

Miljøet settes av den som kjører pakken (Rust-modulen `src-tauri/src/tools/jv`, eller
`jvpack.pack.package_env` i testene): bare `PATH` (pakkens mapper + systemet), `HOME`, `TMPDIR` og
variablene fra `jv-package.json` (`JV_TESSERACT`, `JV_GS`, `TESSDATA_PREFIX` …).

## Struktur

- `jvpack/` – felles: verktøyliste (`tools.py`), pakking og prøvekjøring (`pack.py`), katalog og
  minisign (`catalog.py`), tredjepartsliste (`third_party.py`).
- `jvpack/mac/` – Mac: Mach-O-stier (`macho.py`), Homebrew-data (`resources.py`), lisenser
  (`licenses.py`), signering (`sign.py`), `binaries.json` (`binaries.py`) og bygget (`build.py`).
  Tilpasset fra `pakking/mac/builder` i Verktoy2_0.
- `jvpack/windows/` – kommer i runde B, med samme `jv-package.json` og `.zip`.
- `launcher/jv_launcher.py` – inngangen PyInstaller fryser.
- `pytest_packaged.py` – kjører verktøyets egne tester mot pakken i `sandbox-exec` uten nett og uten
  lesetilgang til Homebrew.
- `binaries.json` – kilde, versjon, SHA-256 og lisens for hvert systemprogram (generert).

Signering: bygget bruker identiteten «Developer ID Application» i nøkkelringen (eller
`JV_SIGN_IDENTITY`). Finnes den ikke, signeres pakken ad hoc med en tydelig advarsel, og den kan
ikke publiseres (appen krever Developer ID fra team `4F539U49GA`).
