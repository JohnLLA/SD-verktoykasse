# Spike: verktøypakker for journalistverktøyene (steg 6.1)

Gren: `steg-6-spike-verktoypakker`, dato 19.10.2026. Runde A (Mac). Fasit:
`docs/spesifikasjon-journalistverktoy.md`. **Steg 6.2 er ikke påbegynt; John Inge bestemmer neste steg.**

## Kort

- Kjeden virker fra ende til ende på Mac: signert katalog fra en lokal testserver → minisign-sjekk →
  nedlasting med brudd og gjenopptak (koden fra modellnedlastingen) → SHA-256 → trygg utpakking →
  `codesign --verify` med krav om Developer ID fra team `4F539U49GA` → `--version` → kjøring på testfil.
- `subtitles`: 9,7 MB nedlasting, 21,5 MB på disk. `ocr`: 100,3 MB nedlasting, 211 MB på disk.
- Oppstart er rask: `--version` tar 30–60 ms når pakken er lest én gang, og 0,4–0,6 s første gang etter utpakking.
- Verktøyenes egne Python-tester består mot den pakkede binærfila, kjørt i `sandbox-exec` uten nett
  og uten tilgang til Homebrew: `subtitles` 51 bestått og 2 hoppet over, `ocr` 31 bestått.
- **Største funn:** `ocr` krever **macOS 26.6.2**, fordi Homebrew-programmene på denne Macen er bygget
  for macOS 26. Spesifikasjonen sier macOS 13+. Det må løses før publisering (se beslutninger).
- Ghostscript trengs ikke av ocrmypdf 17 (`output_type="pdf"`). Det er likevel med, fordi
  `jv_ocr` kaller `require_binary("gs")`. Uten Ghostscript blir pakken omtrent 17 MB mindre.

## Valg i spiken

| Valg | Hva | Hvorfor |
|---|---|---|
| Byggested | John Inges Mac (macOS 26.6.2, M-serie), lokal Homebrew og den lokale PyInstaller 6.6.0, som i `pakking/mac` | Det var raskest: alt lå klart, og ingenting ble lastet ned (`UV_OFFLINE=1`). Ulempen er minste macOS-versjon, se under. |
| Format | `.tar.gz` uten toppmappe, med `jv-package.json` | Som i spesifikasjonen. Python `tarfile` skriver ingen utvidede attributter, så verken karantene eller `com.apple.provenance` følger med pakken. |
| PyInstaller | onedir som **app-bunt** (`jv-<id>.app`) med `LSUIElement`. Kjøres direkte (`Contents/MacOS/jv`), og tkinter er utelatt | `codesign` forsegler hver fil i en bunt (`_CodeSignature/CodeResources`). Én `codesign --verify --deep --strict` dekker da også Python-koden og datafilene, ikke bare Mach-O-filene. |
| Inngang | `jv --version` og `jv <id> …`, samme kontrakt som før | `--version` kjører også hvert innebygde program én gang (`tesseract --version`, `gs --version`). Prøvekjøringen fanger dermed opp biblioteker som mangler. |
| Miljø | Rust tømmer miljøet og setter bare `PATH` (pakken + `/usr/bin:/bin:/usr/sbin:/sbin`), `HOME`, `TMPDIR` og variablene i `jv-package.json` (`JV_TESSERACT`, `JV_GS`, `TESSDATA_PREFIX`, `GS_LIB`, `FONTCONFIG_FILE` …) | Brukerens `PATH`, `DYLD_*` og `PYTHON*` slipper aldri inn. `jv-package.json` får ikke sette `PATH`, `HOME`, `DYLD_*`, `LD_*`, `PYTHON*` eller lignende. Python-koden er uendret i spiken: `require_binary` finner programmene via `PATH`. `JV_*` er satt allerede, klare for 6.2. |
| Utpakking | Systemets `tar` (bsdtar) gjør arkivet om til en ukomprimert tar-strøm (`tar -c -f - @arkiv`). En egen parser i Rust kontrollerer og skriver hver oppføring | Ingen nye crates (regel 7). bsdtar finnes på macOS og i Windows 10 1803+ (`tar.exe`), og det leser både `.tar.gz` og `.zip`. Alt som skrives til disken, er kontrollert i Rust. Se beslutning 3. |
| Katalogsignatur | minisign, forhåndshashet («ED»), sjekket med `minisign-verify` (godkjent i spesifikasjonen) over de rå bytene før JSON leses | Testnøkkelen kommer fra en offentlig tekst (`sidecar/build/jvpack/catalog.py`). Den er ikke hemmelig, og appen stoler bare på den i tester. Python-signeringen (`cryptography`, som allerede er i `uv.lock`) lager minisign-formatet nøyaktig. |

## Hva som er laget

- `sidecar/jv/`: Python-workspacet er kopiert uendret (`verktoy/`, `conftest.py`, `pyproject.toml`,
  `uv.lock`, `testdata/`, `docs/`). Alle 705 Python-tester består der (2 er hoppet over, som før).
- `sidecar/build/`: Mac-bygget (`bygg-mac.sh`, `jvpack/`, `launcher/`, `pytest_packaged.py`),
  `binaries.json` (22 Homebrew-deler med versjon, lisens, kilde-URL, SHA-256 for kildearkivet og
  SHA-256 for bottelen) og `README.md`.
- `src-tauri/src/tools/jv/`: `catalog.rs`, `archive.rs`, `package.rs`, `error.rs` og `spike_tests.rs`.
  Modulen er ikke registrert som plugin og har ingen kommandoer. Ny avhengighet: `minisign-verify 0.3`
  (MIT), som allerede lå i `Cargo.lock`.
- `THIRD_PARTY_LICENSES.md`: delene i pakkene, generert med `python -m jvpack lisenser`.
- `.gitignore` sperrer `.p8`, `.p12`, `.pem` og `.env`, `notarisering/`, `.claude/` og `oppsett/` under `sidecar/`
  og `pakking/*/build|dist`. `tools/sjekk-hemmeligheter.sh` og `.github/workflows/hemmeligheter.yml`
  stopper bygget på Mac og Windows hvis slike filer eller private nøkler (også i filinnhold) er sporet.
- `.gitattributes`: de signerte testfilene i `src-tauri/src/tools/jv/testdata/` sjekkes ut byte for byte,
  ellers ville linjeskift på Windows ødelagt signaturen.

## Tester

`cargo test` (Mac, lokalt): 93 bestått, 6 ignorert (20 nye i `jv`):

- **katalog:** riktig signatur, én endret byte, oppdateringsnøkkelen i stedet for katalognøkkelen,
  tom signatur, «Kommer for Windows» (`NotForPlatform`) når katalogen ikke har en Windows-linje, og «krever nyere app»
- **arkiv:** `../`, absolutte stier, `C:`, `\`, symlenke ut (`../../etc`, `/etc`, `a/../../x`), sti gjennom
  symlenke, hard lenke, enhet, duplikat, feil header-sjekksum, setuid fjernes, symlenke innenfor beholdes,
  og hele veien gjennom systemets tar med en `.tar.gz` som har symlenke ut og `../`
- **pakke:** feil SHA-256 (pakken slettes), prøvekjøring som feiler (den gamle versjonen står urørt),
  god pakke erstatter den gamle (som slettes etterpå), usignert pakke avvises med team-krav, og
  `jv-package.json` med sti ut eller `DYLD_*`/`PATH` avvises
- **Windows (bare i CI):** en `.zip` laget med `tar.exe` pakkes ut gjennom `extract`, og symlenker avvises

`spike_full_chain` (ignorert som standard, kjørt lokalt med
`JV_SPIKE_DIST=../sidecar/build/out/dist cargo test spike_full_chain -- --ignored --nocapture`).
Pakkene ble installert i `~/Library/Application Support/no.lla.verktoykasse-spike/verktoy/<id>/<versjon>` (slettet etterpå).

Python mot pakken (`pytest -p pytest_packaged`, i `sandbox-exec` uten nett og uten lesetilgang til
`/opt/homebrew`, `/usr/local` og `~/.local`):

| Verktøy | Resultat | Kjøringer av den pakkede binærfila | I prosess |
|---|---|---|---|
| subtitles | 51 bestått, 2 hoppet over (testene som bruker ffprobe, som ikke er i pakken) | 46 | 0 |
| ocr | 31 bestått | 17 | 12 tester med egen `monkeypatch` (de lapper internt og kan ikke nå en underprosess) |

Sandkassen er kontrollert: `curl` får ikke koble til, og `ls /opt/homebrew/bin` blir nektet.

## Målinger (Mac, M-serie, macOS 26.6.2, lokal disk)

| | subtitles | ocr |
|---|---|---|
| Arkiv (nedlasting) | 9,7 MB | 100,3 MB |
| Utpakket | 21,5 MB | 211,1 MB |
| Byggetid (varm cache, med signering) | 5 s | 37 s |
| Nedlasting fra lokal testserver, med brudd etter 3 MB og gjenopptak | 0,6 s (2 forespørsler) | 0,8 s (7 forespørsler à 16 MB) |
| Anslått nedlasting på 50 / 10 Mbit/s | 2 s / 8 s | 16 s / 80 s |
| SHA-256 | 24 ms | 171 ms |
| Utpakking (bsdtar-strøm + Rust) | 35 ms | 302 ms |
| `codesign --verify --deep --strict` med team-krav | 21 ms | 163 ms |
| Prøvekjøring (`--version`, første gang) | 415 ms | 559 ms |
| `--version` etterpå (5 ganger) | 30–45 ms | 58–60 ms |
| Kjøring på testfil | 45 ms (2 utfiler) | 1,9 s (1 side, 4 fremdriftslinjer) |
| Minste macOS (fra `LC_BUILD_VERSION`) | 11.0 | **26.6.2** |

Hva `ocr` består av (utpakket): PyMuPDF 46 MB, libpython 17 MB, PIL 10 MB, cryptography 10 MB, lxml 9 MB,
pypdfium2 7 MB, Homebrew-biblioteker 11 MB, tesseract + gs 13 MB, tessdata (`nor`, `eng`, `osd`) 18 MB og
Ghostscript-ressurser 22 MB. Ghostscript (`gs`, ressursene og bibliotekene bare den bruker) utgjør omtrent
17 MB av arkivet.

Kald start rett etter omstart av maskinen er ikke målt (det krever omstart).

### Gatekeeper

- Filene Rust har skrevet, har ingen `com.apple.quarantine`. De har `com.apple.provenance`
  (satt av macOS, uten verdi; det utløser ikke Gatekeeper). Pakken kjører uten advarsel fra
  appdatamappen.
- `spctl -a -t exec` sier «rejected, source=Unnotarized Developer ID». Det har ingen betydning så lenge
  karantene ikke er satt, men viser at pakkene ikke er notarisert.
- **Med karantene** (satt for hånd som etter en nedlasting i Safari) blir `jv --version` hengende og venter
  på Gatekeeper-dialogen, uten at noe skrives ut. Prosessen ble stoppet. **NB:** dette kan ha vist en dialog
  på skjermen til John Inge 19.10. Konklusjon: Rust-modulen må aldri sette karantene (den gjør ikke det),
  og notarisering av pakkene er en god ekstra sikring (beslutning 5).

## Hva som ikke lot seg pakke, eller som mangler

- Alt i spiken lot seg pakke. Ingenting ble utelatt av lisensgrunner.
- **Minste macOS for `ocr`** er 26.6.2 med denne Macens Homebrew. Pakken virker altså ikke på macOS 13–26.5.
- `subtitles`-testene som bruker `ffprobe`, hoppes over mot pakken, fordi ffprobe ikke skal være med.
- `HostPolicy` for GitHub finnes ikke: `HostPolicy::production` i Transkriberings nedlastingskode er låst
  til Hugging Face. Spiken bruker testkonstruktøren. Steg 6.2 trenger en endring der (beslutning 4).
- Den ekte katalognøkkelen er ikke laget. `minisign` er ikke installert lokalt, og CI-signering med
  `TOOLS_MINISIGN_KEY` er ikke laget (6.2 og byggmester).
- Python-testene kjøres ikke i CI ennå, og pakkene bygges ikke i CI (`tools-release.yml` er byggmesters steg).
- `scripts/lag_testdata.py` fra Verktoy2_0 er ikke flyttet, fordi den ikke sto på lista. `testdata/FASIT.md`
  viser til den, og den er nyttig som dokumentasjon av opphavet når repoet blir offentlig.

## Signering

- Lokalt: **signert med «Developer ID Application: John Inge Johansen (4F539U49GA)»** fra nøkkelringen,
  med hardened runtime og sikkert tidsstempel (`timestamp.apple.com`; bare en hash sendes). 75 filer i
  `ocr`, `codesign --verify --deep --strict` er OK. Pakkene er **ikke notarisert**.
- Uten identitet signerer bygget ad hoc og skriver en tydelig advarsel. Appen avviser slike pakker,
  fordi kravet er Developer ID fra team `4F539U49GA`.
- Ingen hemmeligheter er lest, kopiert eller lagt i repoet. `notarisering/` i Verktoy2_0 er ikke rørt.

## Lisensfunn

Alle deler i de to pakkene har fri lisens (lista står i `THIRD_PARTY_LICENSES.md`, med kilde i `binaries.json`). Ingen har ukjent
eller ufri lisens. Verdt å merke seg:

- **AGPL-3.0:** Ghostscript og jbig2dec (bare via `gs`) og PyMuPDF. PyMuPDF har dobbel lisens
  (AGPL eller kommersiell fra Artifex), og vi bruker den under AGPL. Det er forenlig med AGPL-3.0-or-later.
- **GPL/LGPL:** gettext (bare libintl, LGPL-2.1), libidn (GPL-2+ eller LGPL-3+), xz (0BSD, verktøyene GPL),
  zstd (BSD eller GPL-2), fpdf2 og img2pdf (LGPL-3), og PyInstaller-bootloaderen (GPL-2.0+ med unntak for
  bootloaderen; lagt til i `Lisenser/`).
- **Tillatende lisenser med krav om kreditering:** FreeType (FTL), libjpeg-turbo (IJG), libtiff, libpng,
  fontconfig (HPND). Kravet er oppfylt med lisenstekstene i `Lisenser/`.
- `xz (liblzma)`, `libffi` og `bzip2` i libpython har ukjent versjon (python-build-standalone oppgir den ikke),
  men lisensen er kjent (0BSD, MIT og bzip2).
- Uten Ghostscript forsvinner AGPL-delene Ghostscript og jbig2dec og GPL-delen libidn fra `ocr`.

## Anslag for Windows-runden (runde B)

- **Rust:** formatet (`.zip` + `jv-package.json`), utpakkingen (`tar.exe`) og miljøet (`SystemRoot`, `TEMP`
  …) er på plass og testet i CI med en liten zip. Det som gjenstår, er Authenticode-sjekk når LLA har
  sertifikat, og eventuelt å avvise `.exe`-filer utenfor `entry` og `path`. Anslag: ½ dag.
- **Pakker uten systemprogram** (`compare`, `subtitles`, `pdf-tables`): PyInstaller på `windows-latest`,
  rett fram. Anslag: ½–1 dag med `jvpack/windows/`.
- **Systemprogrammer:** ffmpeg (BtbN- eller gyan.dev-bygg uten «nonfree», LGPL- eller GPL-variant),
  exiftool (Phil Harveys Windows-pakke, med samme vilkår som Perl), Tesseract (UB Mannheim-bygget, Apache-2.0,
  pakkes ut av installasjonsfilen) og poppler (poppler-windows, GPL). Hver må festes med URL og SHA-256 i
  `binaries.json`. Anslag: 1–2 dager.
- **Defender:** PyInstaller-bootloadere gir ofte falske treff. Det kan dempes med en bootloader bygget
  fra kilde og med kodesignering. Det må testes på en ren redaksjons-PC. Anslag: ½–1 dag med John Inge.
- **nynorsk** venter (Apertium).
- Til sammen: omtrent 3–5 arbeidsdager for agentene, pluss testing på en ekte PC.

## Sjekkliste – ikke kjørt på enhet

- [ ] På en Mac med macOS 14 eller 15: pakk ut `jv-subtitles-…tar.gz` med `tar -xzf` (ikke fra Safari) og
      kjør `jv-subtitles.app/Contents/MacOS/jv --version`. Det skal virke (minste macOS 11). Gjør det samme
      med `ocr`, som skal feile på grunn av macOS 26.6.2. Dette bekrefter funnet om minste versjon.
- [ ] Kald start: start Macen på nytt og kjør `--version` på `ocr` én gang. Noter tiden.
- [ ] Gatekeeper med den ekte appen (etter 6.2): installer appen fra DMG, last ned et verktøy inne i appen
      og kjør det. Det skal ikke komme noen dialog. Sjekk også `xattr -l` på `jv` i
      `~/Library/Application Support/no.lla.verktoykasse/verktoy/…`.
- [ ] Windows: «Kommer for Windows» for de ni verktøyene. Logikken er testet (`NotForPlatform`), men skjermen
      lages i steg 3 (`grensesnittbygger`).

## Beslutninger for John Inge

1. **Minste macOS for pakker med systemprogrammer.**
   - a) Bygg på `macos-14` i CI med Homebrew. Gir trolig macOS 14+ (Sonoma), og spesifikasjonen endres fra 13 til 14 for disse verktøyene.
   - b) Bygg tesseract, leptonica og bibliotekene fra kilde med `MACOSX_DEPLOYMENT_TARGET=13.0`. Gir 13+, men mer arbeid og lengre byggetid.
   - c) Godta at pakkene krever den macOS-versjonen byggemaskinen har (anbefales ikke).
2. **Fjerne Ghostscript fra `ocr`?** Det krever at `require_binary("gs")` tas ut av `jv_ocr.core`, og at
   to tester (`skip_if_missing("gs")` og `test_missing_ghostscript`) justeres. Det er en endring i
   verktøylogikken og må gjennom kontraktvokter. Gevinst: omtrent 17 MB mindre, og AGPL-delene Ghostscript
   og jbig2dec er ikke lenger med. Anbefales.
3. **Utpakking:** beholde systemets bsdtar + egen tar-parser (ingen nye crates, som nå), eller godkjenne
   `tar` + `flate2` (og `zip` for Windows) som direkte avhengigheter. De ligger allerede i `Cargo.lock`
   via tauri-plugin-updater. Kontrollen av stier og symlenker skal uansett ligge i vår kode.
4. **Nedlastingskoden:** for å bruke den for GitHub må `HostPolicy` i
   `src-tauri/src/tools/transkribering/download.rs` få en konstruktør for vertene i release-repoet (eller
   flyttes til en felles modul). Det er en liten endring i Transkriberings modul. Skal steg 6.2 få lov?
5. **Notarisere pakkene?** Det trengs ikke så lenge appen ikke setter karantene, men det beskytter hvis en
   pakke kopieres for hånd eller macOS strammer inn. Det koster noen minutter per pakke i `tools-release.yml`.
6. **Katalognøkkelen:** lag den ekte nøkkelen (`minisign -G`), legg den hemmelige delen i `TOOLS_MINISIGN_KEY`
   og den offentlige i appen. Avgjør også om CI skal signere med `minisign` (ISC) eller med
   Python-signeringen fra spiken, som da må kunne lese en kryptert nøkkel.
7. **App-bunt i stedet for ren onedir-mappe** for Mac-pakkene (begrunnet over). Godkjenne?
8. **`scripts/lag_testdata.py`:** skal den flyttes inn sammen med `testdata/` i 6.2?

### Avgjort av John Inge 19.10.2026

1. Bygg på `macos-14` i CI. Minste macOS for journalistverktøyene blir 14, og spesifikasjonen rettes i 6.2.
2. Ghostscript tas ut av `ocr` i 6.2, og endringen går gjennom kontraktvokter.
3. Systemets tar og vår egen parser beholdes. Ingen nye crates.
4. 6.2 får gjøre en liten endring i `download.rs` (`HostPolicy` for release-repoet).
5. Pakkene notariseres i CI.
6. CI signerer katalogen med `minisign`. John Inge lager nøkkelen og legger den i `TOOLS_MINISIGN_KEY`.
7. App-bunt (`jv-<id>.app`) godkjennes.
8. `scripts/lag_testdata.py` flyttes inn sammen med testdataene i 6.2.

## Runde B: Windows (20.10.2026)

Gren `steg-6-runde-b-windows`. Byggeoppsettet står i `sidecar/build/README.md` («Windows»), og
kildene står i `sidecar/build/binaries.json`.

- **Åtte av ni pakker er bygget** på `windows-latest` (`jv-windows-pakker.yml`). Hver er prøvekjørt
  med `jv.exe --version`. `nynorsk` er ikke med, fordi Apertium krever bash og kompilerte språkdata.
- **Python-testene mot de pakkede binærfilene består** for alle åtte. Utgående trafikk var sperret i
  Windows-brannmuren for hver `.exe` i pakken, og sperren er prøvd med en sperret `curl.exe`.
  Åtte tester er valgt bort på Windows (`sidecar/build/windows-ikke-portable-tester.txt`):
  - seks bruker filnavn med «:» eller «<>», som ikke er lov på Windows;
  - to antar Mac i selve sjekken (exiftool-utdata som UTF-8 og `file:/…`).
- **`full_chain` i Rust består på Windows** for alle åtte. Kjeden går fra signert katalog via nedlasting
  med brudd og gjenopptak, SHA-256, utpakking med `tar.exe` og prøvekjøring, til kjøring på testfil.

| Verktøy | Arkiv | Utpakket | Installasjon* | `--version` | Kjøring på testfil |
|---|---|---|---|---|---|
| compare | 43,5 MB | 90,0 MB | 1,6 s | 0,10–0,13 s | 0,2 s |
| metadata | 35,6 MB | 86,5 MB | 1,1 s | 0,27–0,34 s | 1,3 s |
| keyframes | 94,9 MB | 247,1 MB | 2,4 s | 0,16–0,17 s | 0,4 s |
| loudness | 87,0 MB | 232,2 MB | 2,1 s | 0,15–0,19 s | 0,8 s |
| subtitles | 9,3 MB | 21,5 MB | 0,4 s | 0,10–0,13 s | 0,2 s |
| pdf-tables | 43,6 MB | 89,2 MB | 0,7 s | 0,10–0,13 s | 1,0 s |
| ocr | 98,3 MB | 209,4 MB | 3,6 s | 0,27–0,33 s | 4,2 s |
| redact | 63,9 MB | 145,7 MB | 1,7 s | 0,13–0,15 s | 0,3 s |

\* SHA-256, utpakking og prøvekjøring. Målt på en GitHub-maskin, ikke på en redaksjons-PC.

Funn:
- `keyframes` og `loudness` er store fordi ffmpeg-bygget er statisk: `ffmpeg.exe` og `ffprobe.exe` er
  på omtrent 105 MB hver.
- Microsofts Visual C++-kjøretid (`vcruntime140*.dll`, `msvcp140*.dll`) ligger i alle pakkene. Den har
  ikke fri lisens (se `binaries.json`, `not_free`).
- ffmpeg, poppler (libcurl) og Tesseract (libcurl) har nettstøtte bygget inn. Verktøyene gir dem bare
  lokale filer, og testene ble kjørt med sperret nett.
- Pakkene er usignert. Appen sjekker ikke Authenticode, fordi spesifikasjonen ikke sier hvordan.
- Hva Defender gjør med pakkene, er ikke prøvd. Det krever en ekte PC (sjekklisten).
