# sidecar/build – verktøypakkene

Bygger én nedlastbar pakke per journalistverktøy og plattform (`docs/spesifikasjon-journalistverktoy.md`).

- **Runde A (Mac):** alle ni for Apple Silicon, bygget **lokalt** på John Inges Mac. Funnene fra
  spiken står i `docs/spike-sidecar.md`.
- **Runde B (Windows):** åtte av ni for Windows x64, bygget i GitHub Actions
  (`.github/workflows/jv-windows-pakker.yml`, `windows-latest`). `nynorsk` venter på Apertium og vises
  som «Kommer for Windows». Se «Windows» under.

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
- **Den ekte nøkkelen** (id FD360273935858EB) har John Inge laget med `minisign -G`. Den offentlige linjen står i
  `PUBLIC_KEY` i `src-tauri/src/tools/jv/catalog.rs` (er den tom, avviser appen alle
  kataloger). Katalogen signeres da med `minisign -S -s <katalog.key> -m tools.json -x tools.json.sig` (samme format som Python-signeringen). Uten `-x` lagrer minisign signaturen som `tools.json.minisig`, men appen henter `tools.json.sig`.

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
- `jvpack/windows/` – Windows: faste nedlastinger med SHA-256 (`sources.py`), utpakking (`fetch.py`),
  DLL-ene et program laster (`pe.py`), lisens for hver DLL (`components.py`, `lisenstekster/`),
  programmene (`programs.py`), lisenser (`licenses.py`), Authenticode (`sign.py`), `binaries.json`
  (`binaries.py`) og bygget (`build.py`). `pyinstaller-krav.txt` er PyInstaller med SHA-256.
  `targets` i `tools.py` sier hvilke verktøy som har Windows-pakke.
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

## Windows (runde B)

### Bygg i GitHub Actions

Pakkene kan ikke bygges på en Mac. Arbeidsflyten **jv-windows-pakker** kjører på `windows-latest`:

- startes for hånd (Actions → jv-windows-pakker → Run workflow; feltet «verktoy» er `alle` eller en
  kommaliste), og på pull request bare når `sidecar/build/**` eller arbeidsflyten endres;
- bygger med `python -m jvpack windows <id>[,<id>…]|alle` (alle = de åtte);
- prøvekjører hver pakke (`jv.exe --version`), kjører verktøyenes Python-tester mot den pakkede
  binærfila med utgående trafikk sperret i Windows-brannmuren (`test-pakker-windows.sh`), og kjører
  `full_chain` i Rust med de åtte pakkene;
- laster opp pakkene som **artefakter** på kjøringen (`jv-windows-pakker`, 14 dager), sammen med
  lisenslistene (`jv-windows-lisenser`) og testloggene. **Ingenting lastes opp til releases.**

### Innhold i en Windows-pakke (`.zip`, uten toppmappe)

| Sti | Innhold |
|---|---|
| `jv-package.json` | som på Mac; `entry` er `jv-<id>/jv.exe`, `codesign` er tom |
| `jv-<id>/jv.exe`, `jv-<id>/_internal/` | PyInstaller (onedir, konsollprogram uten vindu, uten tkinter) |
| `jv-<id>/programmer/<gruppe>/` | systemprogrammet og bare DLL-ene det laster (ffmpeg, exiftool, tesseract, poppler) |
| `jv-<id>/data/tessdata/` | `nor`, `eng`, `osd` (tessdata_fast 4.1.0, samme filer som på Mac), `configs`, `pdf.ttf` |
| `Lisenser/` | lisenstekster og «Kildekode og versjoner.txt» |

| Verktøy | Programmer (kilde i `binaries.json`) | Miljøvariabler |
|---|---|---|
| compare, subtitles, pdf-tables | – | – |
| metadata | ExifTool 13.59, Windows-pakken (med portabel Strawberry Perl) | `JV_EXIFTOOL` |
| keyframes, loudness | ffmpeg og ffprobe 9.0.2 (gyan.dev essentials, GPL-3, uten «nonfree») | `JV_FFMPEG`, `JV_FFPROBE` |
| ocr | Tesseract 5.5.3 (UB Mannheim, pakket ut med 7-Zip, aldri kjørt) | `JV_TESSERACT`, `TESSDATA_PREFIX` |
| redact | pdftotext fra poppler 26.09.0 (poppler-windows, conda-forge) | `JV_PDFTOTEXT` |
| nynorsk | **ingen Windows-pakke** (Apertium) | – |

Hver DLL et program laster, må stå i `jvpack/windows/components.py` med kjent, fri lisens og
lisenstekst i `jvpack/windows/lisenstekster/` (hver mappe har `KILDE.txt`). En ukjent DLL stopper
bygget. Unntak som må godkjennes: Microsofts Visual C++-kjøretid (se `binaries.json`, `not_free`).

`python -m jvpack windows kilder` skriver Windows-delen av `binaries.json` fra `sources.py` og
`components.py` (kan kjøres på Mac). CI sjekker at filen er oppdatert (`--sjekk`).

### Signering

Som appen (`docs/distribusjon.md`, «Windows: kodesignering»): variabelen `WINDOWS_SIGNING`
(`none`, `certificate`, `trusted-signing`) og de samme hemmelighetene. Uten den, og alltid på pull
request, bygges pakkene **usignert**, og sammendraget for kjøringen sier det. Appen kontrollerer ikke
Authenticode (spesifikasjonen sier ikke hvordan, og det trengs en ny avhengighet for `WinVerifyTrust`).
Integriteten hviler på den signerte katalogen og SHA-256, som på Mac.

### Oppskrift for John Inge: Windows-linjer i katalogen

Kjør på Macen, i repoet. `jvpack` er
`uv run --frozen --all-packages --no-sync env PYTHONPATH=../build python -m jvpack`, kjørt i `sidecar/jv`.

1. **Bygg:** Actions → jv-windows-pakker → Run workflow (gren `main`, `alle`). Vent til den er grønn.
   Se sammendraget: størrelser, «--version OK», Python-testene og `full_chain`.
2. **Hent pakkene** til en tom mappe:
   ```zsh
   W=~/jv-windows; rm -rf $W; mkdir -p $W
   gh run download <kjørings-id> -R JohnLLA/lla-verktoykasse -n jv-windows-pakker -D $W
   ls $W/dist/*.zip       # åtte filer: jv-<id>-0.1.0-x86_64-pc-windows-msvc.zip
   ```
3. **Last opp** hver zip som et ekstra vedlegg til den eksisterende pre-releasen for verktøyet
   (samme tagg som Mac-pakken, så URL-ene i katalogen stemmer):
   ```zsh
   REPO=JohnLLA/sd-verktoy-releases
   for f in $W/dist/*.zip; do
     id=$(basename $f | sed -E 's/^jv-(.+)-[0-9.]+-x86_64-pc-windows-msvc\.zip$/\1/')
     v=$(basename $f | sed -E 's/^jv-.+-([0-9.]+)-x86_64-pc-windows-msvc\.zip$/\1/')
     gh release upload "jv-$id-v$v" "$f" --repo $REPO
   done
   ```
   Skriv i release-notatet at Windows-pakken er **usignert** (så lenge LLA ikke har sertifikat).
4. **Lag katalogen** med Windows-linjene. Den publiserte katalogen hentes og sjekkes mot appens nøkkel
   (`PUBLIC_KEY` i `catalog.rs`); Mac-linjene beholdes uendret, og bare Windows-linjene er nye:
   ```zsh
   K=~/jv-katalog; rm -rf $K; mkdir -p $K/ut
   gh release download katalog -R $REPO -D $K
   jvpack katalog lag --usignert --dist $W/dist --behold $K/tools.json --ut $K/ut --min-app 1.0.0
   ```
   `--usignert` skriver bare `tools.json` og sletter en gammel `.sig` i `--ut`. Se over at `$K/ut/tools.json`
   har ni Mac-linjer og åtte Windows-linjer.
5. **Signer** med den ekte nøkkelen (bare du har den):
   ```zsh
   minisign -S -s <sti>/katalog.key -m $K/ut/tools.json -x $K/ut/tools.json.sig
   minisign -Vm $K/ut/tools.json -x $K/ut/tools.json.sig -P RWTrWFiTcwI2/e2iLoLVgSHGrNE3jai91+WO8Pp3J4ihtZDIXngeCFuD
   ```
   Husk `-x tools.json.sig`; uten den blir filen `tools.json.minisig`, som appen ikke henter.
6. **Last opp** katalogen til den faste releasen `katalog` (erstatter de gamle filene):
   ```zsh
   gh release upload katalog $K/ut/tools.json $K/ut/tools.json.sig --repo $REPO --clobber
   ```
7. **Prøv** på en Windows-PC: «Se etter oppdateringer» i Innstillinger → Verktøy. De åtte skal
   få «Last ned verktøyet», `nynorsk` skal fortsatt si «Kommer for Windows».

Lisenslista: last ned artefakten `jv-windows-lisenser` til `sidecar/build/out/work/x86_64-pc-windows-msvc/`
og kjør `jvpack lisenser` (gir `THIRD_PARTY_LICENSES.md` med begge plattformene).
