# Journalistverktøyene i verktøykassen – spesifikasjon (steg 6)

De ni journalistverktøyene fra `Verktoy2_0/journalistverktoy` (nå i `sidecar/jv/`; den opprinnelige mappen er slettet 23.10.2026) skal inn i LLAs verktøykasse. Appen er et skall med samme utseende som Transkribering. Alle ti verktøyene står i venstremenyen. Transkribering følger med appen, og de ni andre lastes ned inne i appen når brukeren vil ha dem (bestemt av John Inge 19.10.2026).

Medlemmene laster ned én app per plattform fra det offentlige release-repoet `JohnLLA/sd-verktoy-releases` eller fra `verktoy.html` på lla.no. Verktøyene lastes deretter ned fra det samme repoet, inne i appen.

`docs/spesifikasjon-v1.md` gjelder fortsatt. Dette dokumentet utvider den, og der de to sier noe forskjellig, gjelder dette for journalistverktøyene. Spør John Inge før du endrer noe av det.

## Verktøyene

| id | Navn i menyen | Systemprogrammer |
|---|---|---|
| `compare` | Sammenlign versjoner | – |
| `metadata` | Metadata – vis og fjern | exiftool |
| `keyframes` | Stillbilder fra video | ffmpeg, ffprobe |
| `loudness` | Lydnivå | ffmpeg, ffprobe |
| `subtitles` | Teksting | – |
| `pdf-tables` | Tabeller fra PDF | – |
| `ocr` | Søkbare PDF-er (OCR) | tesseract (`nor`, `eng`, `osd`) |
| `redact` | Sladding av PDF | pdftotext (valgfri, se under) |
| `nynorsk` | Bokmål ↔ nynorsk | Apertium-programmene + `nob-nno`/`nno-nob` (uten bash-skriptet `apertium`) |

Logikken og testene i Python er godkjent og skal ikke skrives om. Kontrakten er den samme som før: `jv <id> <inngang…> --out <mappe> [valg]` gir én JSON-rapport på stdout, fremdrift som JSON-linjer på stderr, kode 1 ved brukerfeil og kode 2 ved intern feil.

## Arkitektur

```
sidecar/jv/                    Python-workspacet flyttet hit uendret (verktoy/*, conftest.py, testdata/)
sidecar/build/                 Pakkeskript for verktøypakkene (PyInstaller) per plattform, og binaries.json
src-tauri/src/tools/jv/        Rust: katalog, nedlasting, kontroll, installasjon, kjøring, avbryt, fjerning
src/tools/jv/                  Felles skjermbilde for jv-verktøy, i samme stil som Transkribering
src/tools/<id>/                Én liten modul per verktøy: registeroppføring, beskrivelse og skjema for valg
```

### Verktøypakker

- **Én pakke per verktøy og plattform.** Den inneholder PyInstaller-bygget av verktøyet (`onedir`, bare kommandolinje, ingen tkinter) og systemprogrammene verktøyet trenger, med lisenser og «Kildekode og versjoner.txt».
  - Filnavn: `jv-<id>-<versjon>-aarch64-apple-darwin.tar.gz` og `jv-<id>-<versjon>-x86_64-pc-windows-msvc.zip`.
  - Byggeskriptet i `Verktoy2_0/journalistverktoy/pakking/mac/` lager allerede signerte app-er med en skjult CLI-modus (`--jv-cli`). Det er utgangspunktet for Mac-pakkene.
- **Katalog:** `tools.json` ligger som vedlegg i en fast release med taggen `katalog` i release-repoet. Den har en linje per verktøy og plattform:
  - id, navn og versjon
  - URL, størrelse og SHA-256
  - laveste appversjon som støttes
  - kort endringsnotat

  Katalogen signeres med minisign (`tools.json.sig`). Appen har den offentlige nøkkelen innebygd, og den er en annen nøkkel enn oppdateringsnøkkelen.
- **Kontroll før installasjon:**
  - Signaturen på katalogen og SHA-256 på pakken skal stemme, ellers forkastes alt.
  - Pakken pakkes ut i en midlertidig mappe og flyttes på plass først når alt er kontrollert.
  - Stier i arkivet som peker ut av mappen (`..`, absolutte stier, symlenker ut) avvises.
- **Lagring:** i appens datamappe, `verktoy/<id>/<versjon>/`. Den gamle versjonen slettes først når en ny er installert og prøvekjørt med `--version`.
- **Mac:** alle binærfiler i pakken er signert med Developer ID og hardened runtime. Rust-modulen setter ikke karantene-attributt. Den nekter å kjøre en pakke der `codesign --verify` feiler.
- **Windows:** binærfilene signeres når LLA har sertifikat. Til da er de usignert, og det står i release-notatet.

### Rust-modulen (`jv`)

- `jv_catalog()` henter katalogen. Den gjør det bare når brukeren åpner et verktøy som ikke er lastet ned, eller trykker «Se etter oppdateringer». Er nettet nede, brukes siste kontrollerte kopi.
- `jv_install(id)` laster ned med fremdrift, kan gjenopptas og kan avbrytes. `jv_remove(id)` fjerner et verktøy, og `jv_installed()` lister det som er installert.
- `jv_run(id, args)` og `jv_cancel(job)` fungerer som før:
  - argumentliste fra en hviteliste per verktøy, aldri skall
  - fremdrift som hendelser
  - rapporten brukes bare ved kode 0
  - filstier bare fra dialog og slipp
- Miljøvariablene (`JV_FFMPEG`, `JV_EXIFTOOL`, `JV_TESSERACT`, `TESSDATA_PREFIX` osv.) peker inn i pakken. `jv_common.require_binary` sjekker dem før `PATH`.
- Gjenbruk nedlastingskoden fra modellnedlastingen i Transkribering: gjenopptak, SHA-256 og fremdrift.

### Grensesnitt (samme utseende som Transkribering)

- **Venstremenyen** viser alle ti verktøyene, gruppert under «Lyd og video», «Dokumenter» og «Språk». Et verktøy som ikke er lastet ned, har et lite nedlastingsikon og grå tekst. Det er klikkbart.
- **Når et verktøy ikke er lastet ned,** viser siden for verktøyet:
  - tittel og en kort beskrivelse av hva det gjør
  - størrelsen
  - «Last ned verktøyet»-knappen
  - en linje om at filene behandles lokalt

  Mens det lastes ned, vises fremdrift og en Avbryt-knapp. Skjermen er bygget som modellnedlastingen i Transkribering (`docs/skjermbilder/04-nedlasting-*`).
- **Når et verktøy er lastet ned,** ser det ut som Transkribering:
  - stor tittel
  - stiplet slippsone med «Velg fil» og lista over filtyper
  - «Valg» med segmentknapper (samme komponent som Målform, Stil og Kvalitet)
  - Kjør, fremdrift og resultat med «Vis i Finder/Utforsker»
- **`redact` har to steg.** «Finn» gir en liste med avkrysning, der forkastede kandidater er tydelig merket. «Sladd» bruker den redigerte planen.
- **Innstillinger** får seksjonen «Verktøy». Den viser hvert verktøy med versjon og plass det tar, og har knappene «Se etter oppdateringer», «Oppdater» og «Fjern». En oppdatering lastes aldri ned uten at brukeren trykker.
- **Om-vinduet** lister installerte verktøy med versjon og lisens.
- Verktøy som ikke finnes for plattformen (katalogen har ingen linje for den), vises med «Kommer for Windows» eller «Kommer for Mac» og har ingen knapp.

### Nettverk

Spesifikasjon v1 tillater to nettkall: nedlasting av språkmodeller og sjekk etter ny appversjon. Nå kommer et tredje til: **katalog og verktøypakker fra `github.com/JohnLLA/sd-verktoy-releases`** (og GitHubs CDN for vedlegg). Kallet skjer bare når brukeren ber om det, og ingenting om brukeren eller filene sendes med. Det er godkjent av John Inge 19.10.2026.

- Verktøyene selv har aldri nett. Kontrollvokteren kjører hver pakke med nettet sperret.
- `capabilities`: bare kjøring av installerte jv-pakker fra appens datamappe, gjennom Rust. Webvisningen har ingen nettilgang, og CSP endres ikke.

### Sandkasse (Mac)

Verktøyene leser filer fra utenforstående. En fil kan være laget for å utnytte en feil i ffmpeg, poppler, tesseract eller et Python-bibliotek. Derfor kjører hvert verktøy i en sandkasse (steg 6.4), slik at en utnyttet feil ikke kan sende noe ut av maskinen, lese andre filer enn dem brukeren valgte, eller skrive andre steder enn i utmappen.

- **Start:** `/usr/bin/sandbox-exec -f <profil> -D NAVN=verdi … <entry> <args>`. Det gjelder både kjøringer og prøvekjøringen med `--version`. Prosessgruppen, avbryt, det rene miljøet og fremdriften virker som før.
- **Profilen** er en fast mal i `src-tauri/src/tools/jv/sandbox/profil.sb`, bygget inn i appen. Stier står aldri i profilteksten. De sendes som parametere (`-D IN_0=…`), og Rust legger bare til linjer med parameternavn, for eksempel `(allow file-read* (literal (param "IN_3")))`. Alle stier gjøres kanoniske først (`/var` er `/private/var`).
- **Hva profilen tillater** (grunnregel `(allow default)` med forbud, se under):
  - **Nett:** ingenting (`(deny network*)`), heller ikke lokale unix-sockets.
  - **Mach-tjenester:** alle stengt. Det stenger blant annet LaunchServices (åpne nettadresser og programmer), Apple Events, DNS-oppslag (mDNSResponder), nsurlsessiond, utklippstavlen, skjermen og brukeroppslag. Ingen av verktøyene trenger noen. Apple Events, `lsopen`, nye launchd-jobber og IOKit er også stengt, og signaler og prosessinformasjon gjelder bare verktøyets egen prosessgruppe.
  - **Lesing:** stengt for hjemmemappen, `/Users`, `/Volumes`, `/Network` og de midlertidige mappene (`/private/tmp`, `/private/var/tmp`, `/private/var/folders`). Åpnet igjen for pakkens mappe, filene og mappene brukeren valgte (også planfil og termliste), utmappen og den midlertidige mappen. Systemstiene (`/System`, `/usr/lib`, `/Library/Fonts` osv.) kan leses. Metadata (om en fil finnes, størrelse og tid) kan leses overalt, fordi Python og PyInstaller slår opp hver mappe på veien til en fil. Innhold og mappelister er stengt.
  - **Skriving:** bare utmappen (for `datawrapper`: mappen for CSV-filen), en egen midlertidig mappe for kjøringen, `/dev/null` og `/dev/dtracehelper`. Pakken selv kan ikke endres.
  - **Programmer:** bare filer inne i pakken kan startes (ocrmypdf starter tesseract, keyframes starter ffmpeg). `/bin/sh`, `/usr/bin/open` og alt annet utenfor pakken er stengt. Eneste unntak: `metadata` får bruke `/usr/bin/perl` som tolk for exiftool-skriptet i pakken (`process-exec-interpreter`, ikke vanlig start).
- **Midlertidig mappe:** `verktoy/.kjoring/<app-pid>-<n>/` i appens datamappe, med profilen og `tmp/`, som blir `TMPDIR`. Den lages før kjøringen og slettes etterpå, også ved feil og avbryt. Mapper etter en app som krasjet, slettes når neste kjøring starter.
- **Feil lukker:** mangler `sandbox-exec`, eller avviser den profilen, kjøres verktøyet ikke. Brukeren får «Verktøyet kunne ikke startes i beskyttet modus.» (`sandbox_failed`). Det finnes ingen innstilling for å slå sandkassen av. Meldinger fra `sandbox-exec` logges ikke (regel 2).
- **Testene:** `cargo test` kjører en falsk pakke (en kopi av testbinærfila) gjennom sandkassen og sjekker at nett, DNS, lesing i `HOME` og på `/Volumes`, skriving utenfor utmappen og start av `/bin/sh` og `/usr/bin/open` stoppes, mens den valgte fila og utmappen virker. Verktøyenes egne Python-tester kjøres mot de pakkede binærfilene med den samme profilen (`sidecar/build/pytest_packaged.py`).
- **Kjente grenser** (godkjent av John Inge 22.10.2026):
  - En utnyttet prosess kan oppdage (ikke lese) filnavn i HOME via metadata.
  - `datawrapper` får skrive i hele mappen til CSV-fila (ikke bare én utfil).
  - Verktøyet kan lese alt i utmappen, ikke bare skrive dit. Andre filer brukeren har der, kan altså leses (ikke sendes, siden nettet er stengt).
  - Velger brukeren HOME selv som utmappe, blir hele HOME lesbart for verktøyet.
- **Windows** kjører verktøyene uten sandkasse ennå. Det kommer i et eget steg (AppContainer).

## Plattformer

- Mac (Apple Silicon, macOS 13+) og Windows 10/11 x64, som resten av appen.
- **nynorsk:** Mac først (John Inge 19.10.2026), Windows fra versjon 0.2.0 (John Inge 20.10.2026).
  - `jv_nynorsk` leser modusfila og kobler Apertium-programmene sammen selv, uten skall. Det gjelder på begge plattformene, og verken bash eller gawk trengs.
  - Windows bruker Apertiums eget Windows-bygg (`apertium-all-dev`, MinGW-w64) med de samme commitene som Mac. Det er speilet i taggen `kilder-apertium-windows` i release-repoet, sammen med kildekoden.
  - Begge plattformene bruker de samme språkdataene.
  - Detaljer står i `docs/spike-sidecar.md`, under «nynorsk på Windows».
  - Uten pakke for en plattform viser appen «Kommer for Windows», og `verktoy.html` viser det samme.
- **Windows-pakkene** bygges i CI (`windows-latest`) med fritt lisensierte bygg av ffmpeg, exiftool, Tesseract og poppler, som står med versjon og SHA-256 i `binaries.json`.
- **pdftotext** (poppler) er en ekstra kontroll i `redact`. Pakkes det ikke med, går etterkontrollen bare med PyMuPDF og gir en advarsel, slik verktøyet gjør i dag.

## Åpen kildekode og lisenser (bestemt av John Inge 19.10.2026)

- **Kildekoden er offentlig.** Repoet `JohnLLA/lla-verktoykasse` gjøres offentlig, sammen med journalistverktøyene i `sidecar/jv/`.
- **Bare kode med åpen lisens.** Hver del som brukes eller legges med (crates, npm-pakker, Python-pakker, systemprogrammer, modeller, skrifter, ikoner) skal ha en lisens godkjent av OSI eller en tilsvarende fri lisens: MIT, BSD, Apache 2.0, MPL, LGPL, GPL, AGPL, Artistic, CC0 eller CC BY for data. Ingen kommersielle lisenser, ingen «gratis for ikke-kommersiell bruk» og ingen deler uten lisens.
  - **Unntak (godkjent av John Inge 20.10.2026):** Microsofts Visual C++-kjøretid (`vcruntime140*.dll`, `msvcp140*.dll`) i Windows-pakkene. Den har ikke fri lisens, men Microsoft tillater at den deles med programmer, og PyInstaller, Python for Windows og MSVC-byggene av systemprogrammene krever den. Den står som `not_free` i `sidecar/build/binaries.json` og i `THIRD_PARTY_LICENSES.md`.
- **Lisens for verktøykassen: AGPL-3.0-or-later** (bestemt av John Inge 19.10.2026). Den gjelder hele repoet, også `sidecar/jv/`. Den er forenlig med PyMuPDF (AGPL), Apertium og poppler (GPL) og ffmpeg (LGPL/GPL). Lisensteksten ligger i `LICENSE`.
  - `Cargo.toml` og `package.json` får `license = "AGPL-3.0-or-later"`, og pakkene i `sidecar/jv/` får det samme i `pyproject.toml`.
  - Kildefiler får en kort SPDX-linje øverst: `SPDX-License-Identifier: AGPL-3.0-or-later`.
  - Om-vinduet sier at appen er fri programvare under AGPL-3.0-or-later, og lenker til kildekoden. Det oppfyller også nettverkspunktet (§ 13) hvis koden noen gang brukes i en nettjeneste.
  - **Ingen bidrag utenfra.** Bare John Inge (og de han gir skrivetilgang) endrer repoet. `CONTRIBUTING.md` sier kort at prosjektet ikke tar imot pull requests eller kodebidrag, og at alle står fritt til å lage sin egen kopi under AGPL. Issues er slått av på GitHub. Feil og spørsmål sendes til **john@lla.no**, og den adressen står i `CONTRIBUTING.md`, `README.md`, Om-vinduet og på `verktoy.html`.
  - `main` får grenbeskyttelse: ingen direkte push, bare PR-er som John Inge fletter selv.
- **Filene:** `LICENSE` i roten, `THIRD_PARTY_LICENSES.md` med navn, versjon, lisens og kilde for hver del, og samme liste i Om-vinduet. Den genereres fra låsefilene (`Cargo.lock`, `package-lock.json`, `uv.lock`) og `sidecar/build/binaries.json`.
- **Automatisk kontroll i CI:**
  - `cargo-deny` for Rust
  - `license-checker` eller tilsvarende for npm
  - `pip-licenses` for sidecaren

  Kontrollen stopper bygget hvis en del har ukjent lisens eller en lisens utenfor lista. Kontrollverktøyene må selv ha fri lisens.
- **Systemprogrammene** bygges fra eller lastes ned som offisielle bygg med fri lisens. ffmpeg skal være et bygg uten «nonfree»-deler.
- **Modeller og testdata:**
  - NB-Whisper (Apache 2.0) lastes fortsatt ned ved bruk.
  - Testlyd og testfiler i repoet skal ha kjent, fri lisens eller være laget selv. Opptak av personer krever samtykke.
  - Alt annet tas ut før repoet blir offentlig.

## Regler som endres for dette steget

- Regel 8 («Ingen ffmpeg i v1») gjelder fortsatt transkriberingen. ffmpeg brukes bare av `keyframes` og `loudness`, gjennom sidecaren. John Inge godkjente dette 19.10.2026.
- Nye avhengigheter John Inge har godkjent for steget: `tauri-plugin-shell` (bare for å kjøre installerte jv-pakker), PyInstaller (bare bygg) og systemprogrammene i tabellen over. Alt annet: spør. Alle avhengigheter, også de godkjente, må ha fri lisens (se «Åpen kildekode og lisenser»).
- Python-koden i `sidecar/jv/` endres bare for å støtte stier fra miljøvariabler og pakking. Endringer i verktøylogikken går gjennom kontraktvokter med de samme kravene som i Verktoy2_0.
- **Hemmeligheter flyttes aldri inn.** Mappa `notarisering/` i Verktoy2_0 (med App Store Connect-nøkkelen) og alle `.p8`-, `.p12`-, `.pem`- og `.env`-filer skal aldri inn i `lla-verktoykasse`. `.gitignore` sperrer dem, og CI stopper bygget hvis noen finnes.
- Ny avhengighet for steget: `minisign-verify` (MIT), som sjekker signaturen på katalogen. Den er godkjent sammen med resten.

## Før repoet gjøres offentlig

`byggmester` lager en sjekkliste, og John Inge gjør selve endringen på GitHub:

- **Hemmeligheter:** søk etter hemmeligheter i hele historikken, for eksempel med `gitleaks`, som har fri lisens. `.env`, token og nøkler skal aldri ha vært committet. Finnes noe, byttes nøkkelen ut og historikken renskes før publisering.
- **Testdata:** gå gjennom hva som ligger i `testdata/` og `sidecar/jv/testdata/`, med kilde og lisens for hver fil.
- **Personopplysninger:** ingen persondata, ekte kildemateriale eller interne notater i repoet eller historikken. Det gjelder også rapporter og skjermbilder.
- **Lisensfiler:** `LICENSE` og `THIRD_PARTY_LICENSES.md` er på plass, og lisenskontrollen i CI er grønn.
- **Innstillinger på GitHub:** Issues er slått av, og `main` har grenbeskyttelse. Det er også verdt å slå av Wiki, Projects og Discussions. `CONTRIBUTING.md` med john@lla.no er på plass.

## Distribusjon

- **Appen (skallet):** den eksisterende release-arbeidsflyten (`docs/distribusjon.md`) er uendret. Den lager `.dmg`, `-setup.exe`, oppdateringsfilene og `latest.json`.
- **Verktøypakkene:** en ny arbeidsflyt, `tools-release.yml`, kjøres når John Inge pusher en tagg `jv-<id>-v<versjon>` eller `jv-alle-v<versjon>`. Den:
  - bygger pakkene for Mac og Windows
  - signerer binærfilene
  - kjører alle Python-testene mot den pakkede kopien med nettet sperret
  - laster opp pakkene som utkast til release-repoet
  - lager ny `tools.json` og `tools.json.sig` som utkast til release-taggen `katalog`

  John Inge publiserer selv. Signeringsnøkkelen for katalogen ligger bare i Secrets (`TOOLS_MINISIGN_KEY`).
- **Kildekode (AGPL):** hver verktøyrelease får med `jv-<versjon>-kildekode.tar.gz` med både egen kode (`sidecar/jv/`) og kildekoden til tredjepartsdelene. Arkivet som ligger ute nå (`Journalistverktoy-0.1.0-kildekode-tredjepart.tar`) har bare tredjepartsdelene. Egen kode må med i neste release, eller så må `lla-verktoykasse` være offentlig.
- **Agentene lager ikke releaser** og pusher ikke tagger (regel 11).
- **De frittstående DMG-ene** (`Journalistverktoy-<id>-0.1.0-arm64.dmg`) blir liggende til skallet med nedlasting er ute. Etter det sier `verktoy.html` «Last ned verktøykassen» og viser de ni verktøyene som «Lastes ned i appen». John Inge avgjør om de gamle DMG-ene skal fjernes.

## Rekkefølge: Mac først (bestemt av John Inge 19.10.2026)

Skallet med nedlasting og de ni Mac-pakkene lages først og publiseres når de er ferdige. Windows-brukerne får Transkribering som i dag, og de ni verktøyene står som «Kommer for Windows». Windows-pakkene kommer i en egen runde etterpå. Appen endres ikke for det, bare katalogen får nye linjer.

Alt bygges likevel slik at Windows passer inn: Rust-koden, katalogformatet og grensesnittet skal håndtere begge plattformer fra start. CI bygger og tester skallet på begge plattformer (regel 9), men lager bare Mac-pakker i runde A.

### Runde A – Mac

1. **Spike** (`sidecar-bygger`):
   - Lag pakker for `subtitles` og `ocr` for Mac, med utgangspunkt i `pakking/mac/`.
   - Lag katalog med signatur.
   - Last ned, kontroller og kjør pakken fra en Rust-test.
   - Mål størrelse, oppstartstid og tiden det tar å installere.
   - Skriv `docs/spike-sidecar.md`. **John Inge leser den før noe annet bygges.**
2. **Rust-modulen og Mac-pakkene for alle ni verktøyene** (`sidecar-bygger`).
3. **Skjermbildene** (`grensesnittbygger`, med `docs/brief-jv-grensesnitt.md`). På Windows viser de «Kommer for Windows» for de ni.
4. **Kontroll** (`kontraktvokter`, med `docs/brief-jv-kontroll.md`) på hver PR.
5. **Bygg og release for Mac-pakkene** (`byggmester`, med `docs/brief-jv-distribusjon.md`).
6. **Sjekkliste på ekte Mac** (John Inge): ren Mac uten Python, Homebrew eller utviklerverktøy. Last ned hvert verktøy i appen, kjør det på testfiler, oppdater og fjern. Sjekk også at Windows-appen viser «Kommer for Windows» og at Transkribering virker som før.

### Runde B – Windows (etter at runde A er publisert)

1. **Spike for Windows-pakkene** (`sidecar-bygger`):
   - ffmpeg, exiftool, Tesseract og poppler med fri lisens
   - PyInstaller på `windows-latest`
   - hva Defender gjør med pakkene
2. **Windows-pakker for de åtte verktøyene** som lar seg pakke. `nynorsk` fulgte i 0.2.0 (Apertiums Windows-bygg, se over).
3. **Kontroll, release** og **sjekkliste på en ren redaksjons-PC med Windows**.
