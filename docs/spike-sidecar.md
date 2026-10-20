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

## nynorsk på Windows (fase 1, 20.10.2026)

Gren `jv-nynorsk-windows`. Bare undersøkelse: ingenting er bygget, og Python er ikke endret.
Prøvene er kjørt på John Inges Mac med filer lastet ned til en midlertidig mappe utenfor repoet.

### Kort

- **Det finnes ferdige, vedlikeholdte Windows-bygg (x64)** av alle fem programmene, laget av Apertium
  selv (Tino Didriksen, som også lager Apertiums Debian- og Mac-pakker). De er bygget med MinGW-w64 og
  oppdateres hver natt. **De har nøyaktig de samme commitene som Mac-pakken.**
- **Ulempen:** nattbyggene har ingen fast URL. Hver fil blir liggende bare til neste bygg, og gamle
  versjoner slettes. Arkivene må derfor speiles til en fast release (se beslutninger).
- **Verken MSYS2 eller conda-forge** har pakker for apertium, lttoolbox eller cg3 (søkt 20.10.2026).
- **De kompilerte språkdataene er ikke knyttet til plattformen.** Apertiums egen Debian-pakke for
  `apertium-nno-nob` er `Architecture: all`, og Apertiums Windows-side viser brukerne til de samme
  Debian-pakkene. Prøve på Mac: Linux-bygde data kjørt med Mac-bygde programmer virker. Windows må
  bekreftes i CI.
- **Den foreslåtte arkitekturen virker.** Hvis Python leser modusfila og kobler programmene sammen med
  `subprocess` uten skall, blir utdataene **byte for byte like** dem fra `apertium -f txt` på Mac. Det
  er prøvd i begge retninger på fem tekster, med 65 B til 18,7 kB tekst. Da trengs verken bash, gawk
  eller `apertium`-skriptet, heller ikke på Mac.
- Cygwin og de gamle SourceForge-installasjonsfilene er vurdert og **forkastet**. De krever installasjon
  hos brukeren, får problemer med stier som har æøå, og er ikke vedlikeholdt.

### Ferdige bygg: Apertiums nattbygg for Windows

Kilde: `https://apertium.projectjj.com/win32/nightly/`. Mappenavnet sier `win32`, men filene er x86_64.

| Del | Fil i nattbygget (14.10.2026) | Commit (Windows = Mac) | SHA-256 | Lisens |
|---|---|---|---|---|
| lttoolbox 3.8.4 | `lttoolbox-3.8.4+g660~ed9b682b.x86_64.zip` (18,0 MB) | `ed9b682b` = `ed9b682b9e3e…` | `e3d8e4c74a928ed8a37c7db83cb26f0bb5154ab3f46d3c9b06b8673f3fa0b915` | GPL-2.0-or-later |
| apertium 3.9.12 | `apertium-3.9.12+g944~d8dfb942.x86_64.zip` (21,5 MB) | `d8dfb942` = `d8dfb942e31d…` | `6d7b82987bde12837b1c08ebc730ef34c4ef69ef2348e810ca129a3edfa271c5` | GPL-2.0-or-later |
| apertium-lex-tools 0.5.0 | `apertium-lex-tools-0.5.0+g551~1ccefa62.x86_64.zip` (17,9 MB) | `1ccefa62` = `1ccefa6269ad…` | `89e730e51df6a5334a67fe6d87e34497ed5b90f4400f985228fd0c25a8fd99a2` | GPL-3.0-or-later |
| apertium-separable 0.7.1 | `apertium-separable-0.7.1+g279~18045e4d.x86_64.zip` (17,7 MB) | `18045e4d` = `18045e4da12c…` | `63dc4942493d94f7ac334d35cb05d5456301aa2ee2989f43223247395a13368d` | GPL-3.0-or-later |
| cg3 1.7.0 | `cg3-1.7.0+g2354~0250250f.x86_64.zip` (17,4 MB) | `0250250f` = `0250250fe982…` | `349586731701ceeeeabfbf28e3a34c0679d9d8caac7e4e3427dd746d21ecf357` | GPL-3.0-or-later |
| alle fem samlet | `apertium-all-dev.x86_64.zip` (44,3 MB, uten versjon i navnet) | samme natt | `c8236ac537be7ba35849cf9ad4222a399646076f9cfa75bf86806e3a614de8a8` | som over |

Funn:

- Programmene er `PE32+ console x86-64` fra MinGW-w64 (`libstdc++-6.dll`, `libgcc_s_seh-1.dll`,
  `libwinpthread-1.dll`). De trenger ikke MSYS2, Cygwin eller bash, og de er ikke signert.
- Hvert komponentarkiv har sine egne kopier av ICU, libstdc++ og libxml2, og byggene er ikke
  reproduserbare (samme DLL har forskjellig SHA-256 i hvert arkiv). Vi bør derfor bruke **ett** sett:
  enten `apertium-all-dev` (alt bygget sammen) eller programmene fra hvert komponentarkiv med de felles
  DLL-ene fra ett av dem. Jeg anbefaler `apertium-all-dev`, og at versjonen kontrolleres i CI med
  `--version` på hvert program.
- Pakken trenger 15 programmer (`apertium-destxt`, `apertium-retxt`, `apertium-wblank-attach`,
  `apertium-wblank-detach`, `lt-proc`, `lt-merge`, `cg-proc`, `apertium-tagger`, `lsx-proc`,
  `apertium-pretransfer`, `lrx-proc`, `apertium-transfer`, `apertium-interchunk`, `apertium-postchunk`,
  og `apertium-wblank-mode` hvis vi ikke gjør den jobben i Python). Med `jvpack/windows/pe.py` får de
  13 DLL-er: ICU 78 (`icudt78` er 33 MB), `libcg3`, `liblttoolbox`, `libstdc++`, `libgcc_s_seh`,
  `libwinpthread`, `libiconv`, `libxml2`, `libsqlite3` og `zlib1`. Det blir **48,5 MB** utpakket. Alle
  DLL-ene unntatt `liblttoolbox` og `libcg3` har allerede lisens og lisenstekst i
  `jvpack/windows/components.py`. For de to nye finnes lisenstekstene i kildene, og de står allerede i
  Mac-pakken.
- **Ingen ufrie deler.** Microsofts Visual C++-kjøretid trengs ikke for Apertium, fordi MinGW bruker
  Windows' egen C-kjøretid.
- Hvor lenge en fil ligger i nattbygget, er ukjent. Mappa viser bare siste bygg for hver del.
- Det finnes ingen faste Windows-utgaver. `win32/apertium-all-dev.zip` er fra 2022 og passer ikke med
  Mac-versjonene. GitHub-utgavene til Apertium har bare kildekode, og lttoolbox 3.8.4 og cg3 1.7.0 er
  ikke utgitt der ennå: Mac-pakken er bygget fra `main`.

### Bygge selv med MSYS2 (reserveløsning)

Det går an å bygge på `windows-latest` med MSYS2 (MinGW-w64, `mingw-w64-x86_64-*`):

- **Det trengs:** `cmake`, `autotools`, `libtool`, `pkgconf`, `icu`, `libxml2`, `utf8cpp`, `boost`
  (headere for cg3) og `rapidjson` (apertium-separable). Kildene hentes som GitHub-arkiv per commit
  (`github.com/apertium/<repo>/archive/<commit>.tar.gz`) med SHA-256.
- **Rekkefølgen er som på Mac:** lttoolbox og cg3 bygges med cmake, apertium, lex-tools og separable
  med autotools.
- **Risiko:** autotools-byggene til Apertium er ikke laget for MSYS2. Apertium bygger selv for Windows
  ved å krysskompilere fra Linux, så det kan trenges lapper. MSYS2-pakkene har heller ingen helt fast
  URL over tid. Byggetid i CI er anslått til 20–30 minutter uten hurtiglager.
- **Fordel:** hele kjeden går fra kildekode med commit og SHA-256, uten speiling.
- **Anslag:** 2–3 dager mer enn vei A, og utfallet er usikkert.

### Språkdataene

- Pakken trenger 40 datafiler fra `apertium-nno-nob` (.bin, .rlx.bin, .prob, .t1x–.t3x) og de to
  modusfilene. Det er omtrent 28 MB, som i Mac-pakken (`Resources/apertium`).
- **Prøve 1:** Debian-pakken `apertium-nno-nob 1.6.0+g9188~af921d87` (bygget på Linux, samme commit
  som Mac) ble kjørt med Mac-programmene. Den gir samme oversettelse som Mac-dataene på 9 av 10
  prøver. Den siste prøven skiller seg i noen få ord («ms» → «ss» i nno-nob). Det er forskjell i
  ordboka, ikke i filformatet: 17 av 43 datafiler er ulike byte for byte, så Debian-bygget brukte andre
  kilder for de enspråklige pakkene. **Konklusjon:** filformatet kan flyttes, men innholdet må komme fra
  samme bygg.
- **Anbefaling:** Windows-pakken bruker **nøyaktig de samme datafilene som Mac-pakken av samme
  versjon**. Byggeskriptet kan hente dem fra Mac-arkivet, som allerede har en fast URL og SHA-256 i
  katalogen. Da gir begge plattformene samme oversettelse.
- **Filene leses binært** (`fopen(…, "rb")` i lttoolbox), så linjeskift på Windows ødelegger dem ikke.
  Programmene åpner filer med smale tegn (ANSI-tegntabell), så en sti med tegn utenfor tabellen kan
  feile. **Løsning:** Python starter programmene med arbeidsmappe lik datamappa i pakken og gir dem
  bare relative stier med ASCII-tegn (`apertium-nno-nob/nob-nno.automorf.bin`). Da betyr det ikke noe
  om brukernavnet eller appdatamappa har æøå. Teksten går alltid på stdin og aldri som argument.

### Arkitekturen: Python kobler sammen programmene uten skall

`apertium -f txt nob-nno` gjør dette (lest i skriptet, Apertium 3.9.12):

```
apertium-destxt  |  <modus, gjort om av apertium-wblank-mode>  |  apertium-retxt
```

- `$1` i modusfila blir `-g`, fordi `-f txt` uten `-u` gir merkene `*`, `#` og `@`.
- `$2` blir tom, fordi `-a` ikke brukes.
- `apertium-wblank-mode` legger `apertium-wblank-attach` etter steget som bruker `automorf.bin`, og
  `apertium-wblank-detach` foran steget som bruker `autogen.bin`. Regelen er på omtrent ti linjer C++.
- gawk brukes bare til `AP_SETVAR`, som er tom for oss, og da sender den teksten uendret videre.
  `apply_invert_setvars` trengs heller ikke.

**Prototype** (utenfor repoet, ikke i verktøyet):

- Python leser utdataene fra `apertium-wblank-mode <modus>` og deler dem ved `|` og med `shlex`.
- Den bytter ut `$1`/`$2` og starter 25 (`nob-nno`) eller 15 (`nno-nob`) prosesser med `Popen`, koblet
  med rør og uten skall.
- Den skriver stdin fra en egen tråd.

Resultat mot `apertium -f txt` på Mac: **likt byte for byte** for `testdata/nynorsk/avsnitt_nb.txt` og
`avsnitt_nn.txt`, for to korte prøver med `xqztvik`/`svibrent`/tomme linjer og for fire lengre
markdown-tekster (6–19 kB). Tiden var den samme som før (2–5 s for 6–19 kB, mest oppstart av
cg-proc og lt-proc).

Forslag til løsning i fase 2 (må gjennom kontraktvokter):

- **Modusfilen:** `Apertium.run` leser `<datamappe>/modes/<modus>.mode`, legger på wblank-regelen og
  deler den i steg.
- **Kontroll av stegene:** hvert programnavn må stå på en fast liste over de 15 programmene. Hvert
  filargument må være en relativ sti inne i datamappa, uten `..`. Ellers stopper verktøyet med en
  intern feil. Modusfila kan dermed ikke starte noe annet enn Apertium-programmene.
- **Datamappen og programmene:** de finnes med `JV_APERTIUM_DATADIR` og `JV_APERTIUM_BIN`, som
  `jv-package.json` setter. Utviklere uten pakke bruker `~/.local` som i dag.
- **Feil og stderr:** stderr fra alle stegene samles. Er en kode ulik 0, brukes de samme norske
  feilmeldingene som før. Advarselen om 500 kohorter fra cg-proc er ikke en feil, som før.
- **Moduser:** `apertium -l` erstattes av en liste over filene i `modes/`.
- **Linjeskift på Windows:** lttoolbox og cg3 setter ikke stdin og stdout i binærmodus. MinGW-programmer
  kan derfor gjøre `\n` om til `\r\n` på Windows. Mellom stegene oppheves det, men det endelige
  resultatet kan få `\r\n`. Det må måles i CI. Gjelder det, gjør Python `\r\n` om til `\n` i utdataene
  på Windows. På Mac skjer ingenting.
- **Avbryt:** `jv_cancel` dreper allerede hele prosesstreet (`taskkill /T` på Windows, prosessgruppe på
  Mac). Rust må ikke endres.
- **Tester:** `fake_apertium.py` brukes i dag som programmet `apertium` i `PATH`. Den må gjøres om til
  et falskt steg i en falsk modusfil. Selve sjekkene i testene skal ikke endres. Integrasjonstestene
  kjøres mot den ekte pakken på begge plattformene.
- **Mac-pakken** får samme kode og mister `apertium`-skriptet, gawk og bash-avhengigheten. Prototypen
  viser samme resultat byte for byte. Modusfilene får relative stier i stedet for `${APERTIUM_DATADIR}`.
  Mac-pakken må bygges, signeres og notariseres på nytt, og den får ny versjon sammen med Windows-pakken.

**Kontroll på tvers av plattformene i CI (fase 2):** de samme tekstene oversettes på Windows og på
Mac, og resultatene skal være like byte for byte, eventuelt etter at `\r\n` er gjort om. Det viser at
dataene og programmene virker likt.

### Anslag

| Del | Vei A (nattbygg, speilet) | Vei B (MSYS2 fra kilde) |
|---|---|---|
| Python: rørkobling, kontroll av steg, tester, kontraktvokter | 1 dag | 1 dag |
| Mac-pakken uten skript og gawk, nytt bygg og notarisering | ½ dag | ½ dag |
| Windows-bygget: kilder, programgruppe, data fra Mac-pakken, lisenser | 1 dag | 1 dag |
| Bygge Apertium selv | – | 2–3 dager (usikkert) |
| CI: Python-tester mot pakken, sammenligning med Mac, `full_chain` | ½–1 dag | ½–1 dag |
| **Til sammen** | **3–3½ dager** | **5–6½ dager** |

Størrelse på Windows-pakken: Python-delen omtrent som `compare` (43 MB arkiv), pluss Apertium-programmene og
DLL-ene (48,5 MB utpakket, med ICU-dataene som største del) og språkdataene (28 MB). Anslag:
**65–80 MB arkiv og 160–180 MB utpakket.** Mac-pakken er 47 MB.

### Beslutninger for John Inge (nynorsk på Windows)

1. **Vei:** A, Apertiums egne nattbygg for Windows, med samme commiter som Mac (anbefales), eller B,
   bygg fra kilde med MSYS2 i CI.
2. **Fast URL for nattbyggene (vei A):** du speiler arkivet eller arkivene (og kildearkivene for de
   samme commitene, for GPL) som vedlegg i en fast release, for eksempel taggen `kilder-apertium-windows`
   i `lla-verktoykasse-releases`. Byggeskriptet henter dem bare derfra og sjekker SHA-256. Agentene
   laster ikke opp (regel 11). Kildene i `binaries.json` er da den opprinnelige URL-en og speilet.
3. **Hvilket arkiv:** `apertium-all-dev` (ett sammenhengende sett, 44 MB) eller de fem
   komponentarkivene (versjon i filnavnet, men fem ulike kopier av ICU og libstdc++). Jeg anbefaler
   `apertium-all-dev`.
4. **Arkitekturen:** Python kobler sammen programmene selv (anbefales). Det endrer verktøylogikken i
   `jv_nynorsk` og testoppsettet, og det må gjennom kontraktvokter.
5. **Ny versjon for nynorsk på begge plattformene** (for eksempel 0.2.0). Mac-pakken bygges på nytt
   uten bash-skriptet og gawk.
6. **Språkdata:** Windows-pakken bruker datafilene fra Mac-pakken av samme versjon (anbefales), eller
   dataene kompileres i CI på Linux fra de samme commitene.

### Avgjort av John Inge 20.10.2026, og fase 2

John Inge bestemte dette:
- Vi bruker vei A med `apertium-all-dev`, speilet i taggen `kilder-apertium-windows` i `JohnLLA/sd-verktoy-releases`, sammen med kildearkivene.
- Python kobler programmene sammen selv.
- nynorsk får versjon 0.2.0 på begge plattformene.
- Begge plattformene bruker språkdataene fra Mac-pakken 0.1.0.

Dette er gjort i fase 2:

- **`jv_nynorsk`** (`core.py`) leser modusfila og kjører `apertium-destxt | <modus> | apertium-retxt` med `subprocess`, uten skall.
  - `$1` blir `-g`, og `$2` faller bort.
  - wblank-regelen er lagt inn.
  - Det er en fast liste med 14 programmer, og stiene er relative i datamappa.
  - stderr fra hvert steg går til en egen fil. Det er tidsgrense, og `CREATE_NO_WINDOW` brukes på Windows.
  - Linjeskift gjøres om fra `\r\n` til `\n` på Windows hvis inndataene ikke har `\r`.
- **Testene:**
  - Den falske `apertium` er erstattet med falske programmer og en falsk modusfil.
  - Det er lagt til nye tester for reglene i modusfila, mapper med æøå og mellomrom, krasj midt i kjeden og store tekster.
  - Det er lagt til fasiter i `sidecar/jv/testdata/nynorsk/referanse/`, laget med `apertium -f txt` (bash-skriptet) på Mac. Integrasjonstestene krever samme bytes på Mac og Windows.
- **Mac-pakken 0.2.0:**
  - Den har ikke lenger bash-skriptet, gawk, gmp, mpfr eller readline, og har 14 programmer i `Helpers`.
  - De 40 datafilene er identiske med 0.1.0.
  - Oversettelsen fra 0.1.0- og 0.2.0-pakken er byte for byte lik for 18 kjøringer: 9 filer (txt, md og docx, 0,4–36 kB) i begge retninger.
- **Windows-pakken:**
  - `jvpack/windows/programs.py` kopierer de 14 programmene og DLL-ene de laster fra speilet.
  - Modusene og datafilene kommer fra Mac-pakken 0.1.0. Modusene får relative stier og blir da identiske med Mac 0.2.0.
