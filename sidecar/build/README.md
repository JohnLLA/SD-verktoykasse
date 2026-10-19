# sidecar/build – verktøypakkene

Bygger én nedlastbar pakke per journalistverktøy og plattform (`docs/spesifikasjon-journalistverktoy.md`).
Runde A: alle ni for Mac (Apple Silicon), bygget **lokalt** på John Inges Mac (betaversjon; ingen
GitHub Actions for pakkene ennå). Funnene fra spiken står i `docs/spike-sidecar.md`.

## Kommandoer (fra repo-roten)

```
sidecar/build/bygg-mac.sh alle                       # bygg, signer, pakk og prøvekjør alle ni
sidecar/build/bygg-mac.sh alle --notariser           # … og notariser (notarytool-profilen «jv-notary»)
sidecar/build/bygg-mac.sh ocr,redact                 # noen av dem
sidecar/build/test-pakker-mac.sh alle                # verktøyenes Python-tester mot de pakkede binærfilene
```

Med `UV_OFFLINE=1` henter `bygg-mac.sh` ingenting fra nett (pakkene må ligge i uv-cachen).
Resultatet havner i `sidecar/build/out/` (utenfor git): `dist/jv-<id>-<versjon>-aarch64-apple-darwin.tar.gz`,
`bygg-oppsummering.json` (størrelser, minste macOS, signering, notarisering, kontroller) og
`test-oppsummering.txt`.

Katalog, lisensliste og en lokal betanøkkel. `jvpack` står under for
`uv run --frozen --all-packages --no-sync env PYTHONPATH=../build python -m jvpack`, kjørt i `sidecar/jv`:

```
jvpack katalog nokkel lag                                 # lokal betanøkkel i ~/.lla-verktoykasse/katalog-beta.key
jvpack katalog lag --key-file ~/.lla-verktoykasse/katalog-beta.key [--base-url URL] [--min-app 0.2.0]
jvpack katalog lag --test-key --base-url http://127.0.0.1:47613   # for full_chain-testen i Rust
jvpack lisenser                                           # THIRD_PARTY_LICENSES.md fra pakkene som er bygget
```

`katalog lag` skriver `out/dist/tools.json` og `tools.json.sig` for alle pakkene i `out/dist`
(Mac og, i runde B, Windows). Uten `--base-url` peker URL-ene på release-repoet
(`…/releases/download/jv-<id>-v<versjon>/<fil>`).

### Katalognøkkelen

- **Testnøkkelen** (`--test-key`) er avledet av en offentlig tekst og er ikke hemmelig. Appen stoler
  bare på den i `cargo test`.
- **Lokal betanøkkel** (`--key-file`): 32 tilfeldige byte i en fil med modus 600 utenfor repoet
  (`katalog nokkel lag` nekter å skrive inne i et git-repo, og `*.key` er sperret i `.gitignore`).
  Appen stoler på den bare når den bygges med den offentlige nøkkelen i miljøet:
  `JV_CATALOG_PUBLIC_KEY=<RW…> npm run tauri build` (eller `cargo build`). Den offentlige nøkkelen
  skrives ut av `katalog nokkel lag` og `katalog nokkel --key-file <fil>`.
- **Den ekte nøkkelen** lager John Inge selv med `minisign -G`. Den offentlige linjen settes inn i
  `PUBLIC_KEY` i `src-tauri/src/tools/jv/catalog.rs` (plassholderen er tom; da avviser appen alle
  kataloger). Katalogen signeres da med `minisign -S -m tools.json` (samme format som Python-signeringen).

### Hele kjeden i Rust (alle ni)

```
(cd sidecar/jv && jvpack katalog lag --test-key --base-url http://127.0.0.1:47613)
cd src-tauri
JV_DIST=../sidecar/build/out/dist cargo test full_chain -- --ignored --nocapture
```

Testen starter en lokal server på port 47613 med brudd i første forespørsel mot hver pakke, henter og
kontrollerer katalogen, laster ned (med gjenopptak), sjekker SHA-256, pakker ut, kjører
`codesign --verify` med krav om Developer ID fra team `4F539U49GA`, prøvekjører og kjører hvert
verktøy på en testfil. Den skriver bare tall.

## Innhold i en pakke

Arkivet har ingen toppmappe:

| Sti | Innhold |
|---|---|
| `jv-package.json` | id, navn, versjon, plattform, `entry`, mapper til `PATH`, miljøvariabler (relative stier), bunter som skal ha gyldig kodesignatur, minste macOS |
| `jv-<id>.app/Contents/MacOS/jv` | PyInstaller (onedir som app-bunt, bare kommandolinje, uten tkinter) |
| `jv-<id>.app/Contents/Helpers/` | systemprogrammene (ffmpeg, ffprobe, tesseract, pdftotext, gawk, Apertium-programmene) |
| `jv-<id>.app/Contents/Frameworks/jv-lib/` | bibliotekene deres, med omskrevne stier |
| `jv-<id>.app/Contents/Resources/` | data: tessdata, exiftool (Perl-skript og bibliotek), Apertium (skript, moduser, språkdata), fontconfig |
| `Lisenser/` | lisenstekster og «Kildekode og versjoner.txt» |

| Verktøy | Innebygde programmer | Miljøvariabler |
|---|---|---|
| compare, subtitles, pdf-tables | – | – |
| metadata | exiftool (kjøres med macOS' `/usr/bin/perl`) | `JV_EXIFTOOL` |
| keyframes, loudness | ffmpeg, ffprobe | `JV_FFMPEG`, `JV_FFPROBE` |
| ocr | tesseract med `nor`, `eng`, `osd` (ikke Ghostscript) | `JV_TESSERACT`, `TESSDATA_PREFIX` |
| redact | pdftotext (poppler) | `JV_PDFTOTEXT`, `FONTCONFIG_*` |
| nynorsk | Apertium (`nob-nno`, `nno-nob`) og gawk | `JV_APERTIUM`, `JV_GAWK`, `APERTIUM_DATADIR`, `APERTIUM_PATH` |

`jv_common.require_binary` sjekker `JV_<NAVN>` før `PATH`. `jv --version` skriver JSON med id og
versjon og kjører hvert innebygde program én gang; det er prøvekjøringen appen gjør før en pakke tas i
bruk. `jv <id> <inngang…> --out <mappe> [valg]` er den vanlige kontrakten (rapport som JSON på stdout,
fremdrift som JSON-linjer på stderr, kode 1/2 ved feil).

Miljøet settes av den som kjører pakken (Rust-modulen `src-tauri/src/tools/jv`, eller
`jvpack.pack.package_env` i testene): bare `PATH` (pakkens mapper + systemet), `HOME`, `TMPDIR` og
variablene fra `jv-package.json`.

## Struktur

- `jvpack/` – felles: verktøyliste (`tools.py`), pakking og prøvekjøring (`pack.py`), katalog og
  minisign (`catalog.py`), tredjepartsliste (`third_party.py`).
- `jvpack/mac/` – Mac: Mach-O-stier (`macho.py`), Homebrew-data (`resources.py`), Apertium
  (`apertium.py`), lisenser (`licenses.py`), signering (`sign.py`), notarisering (`notarize.py`),
  `binaries.json` (`binaries.py`) og bygget (`build.py`). Tilpasset fra `pakking/mac/builder` i Verktoy2_0.
- `jvpack/windows/` – kommer i runde B: samme `jv-package.json`, `.zip`, og en `targets`-linje per
  verktøy i `tools.py`. Katalogen (`catalog.py`) og Rust-modulen håndterer allerede begge plattformene.
- `launcher/jv_launcher.py` – inngangen PyInstaller fryser.
- `pytest_packaged.py` – kjører verktøyets egne tester mot pakken i `sandbox-exec` uten nett og uten
  lesetilgang til Homebrew, `/usr/local` og `~/.local`. Tester som bruker `monkeypatch` (selv eller
  gjennom en fixture) kjører i prosess og telles for seg.
- `binaries.json` – kilde, versjon, SHA-256 (kildearkiv og bottle) og lisens for hver Homebrew-del
  (generert). Apertium er bygget fra kilde i `~/.local` og står med repo og commit i pakkens
  «Kildekode og versjoner.txt».

## Forutsetninger (lokal Mac)

- Homebrew i `/opt/homebrew` med `ffmpeg`, `tesseract`, `tesseract-lang`, `poppler`, `exiftool` og `gawk`.
- Apertium med `apertium-nno-nob` bygget fra kilde i `~/.local`, og kildene i `~/Kilder/apertium/<repo>`
  (se `sidecar/jv/verktoy/nynorsk/OPPSETT.md`).
- PyInstaller i venv-en eller den lokale PyInstaller 6.6 for Apples Python 3.9 (som i Verktoy2_0).
- Identiteten «Developer ID Application» i nøkkelringen (eller `JV_SIGN_IDENTITY`). Uten den signeres
  pakken ad hoc med en tydelig advarsel, og appen nekter å kjøre den.
- For notarisering: nøkkelringprofilen `jv-notary` (`xcrun notarytool store-credentials`). Finnes den
  ikke, bygges pakkene uten notarisering, med en merknad.

**Minste macOS** arves fra Homebrew-programmene på byggemaskinen (står i `bygg-oppsummering.json` og
`jv-package.json`, og appen viser «krever nyere macOS» fra katalogen).
