# Sjekkliste: steg 6.4, sandkasse for verktøyene på Mac

**Status: ikke kjørt på enhet.** Sandkassen er testet på John Inges Mac (macOS 26.6.2) med `cargo test`
(den falske pakken), `full_chain` (alle ti pakkene lastet ned, installert og kjørt gjennom sandkassen) og
verktøyenes egne Python-tester mot de pakkede binærfilene med appens profil. Listen under kjøres på en
**ren Mac med macOS 26** (uten Python, Homebrew og utviklerverktøy). John Inge kjører den.

Bruk en app bygget fra grenen `steg-6-4-sandkasse-mac` (`npm run tauri build`, åpne `.app`-en fra
`src-tauri/target/release/bundle/macos/`). Verktøypakkene lastes ned fra release-repoet som vanlig.

Forbered:
- en ekstern disk eller minnepinne (vises under `/Volumes/…`) med testfilene fra
  `sidecar/jv/testdata/` i repoet (eller egne filer av samme type)
- de samme filene i `~/Documents/sandkassetest/`
- Konsoll.app åpen, med søket `sandbox` og prosessen `jv` (se siste del)

## Alle ti verktøyene

For hvert verktøy: last det ned i appen (eller oppdater), kjør det én gang på en fil fra den eksterne
disken og én gang på en fil fra `~/Documents`, med utmappe på skrivebordet. Resultatet skal se ut som før,
og «Vis i Finder» skal virke.

| Verktøy | Testfil | Ekstern disk | ~/Documents |
|---|---|---|---|
| Sammenlign versjoner | `compare/vedtak_v1.docx` og `vedtak_v2.docx` | [ ] | [ ] |
| Metadata – vis | `metadata/bilde_gps.jpg` | [ ] | [ ] |
| Metadata – fjern | `metadata/dokument_forfatter.pdf` | [ ] | [ ] |
| Stillbilder fra video | `keyframes/klipp.mp4` | [ ] | [ ] |
| Lydnivå | `loudness/video_med_lyd.mp4` | [ ] | [ ] |
| Teksting | `subtitles/transkripsjon.json` | [ ] | [ ] |
| Tabeller fra PDF | `pdf-tables/budsjett.pdf` | [ ] | [ ] |
| Klargjør for Datawrapper (med «Lagre som CSV») | `datawrapper/ssb_befolkning.xlsx` | [ ] | [ ] |
| Søkbare PDF-er (OCR) | `ocr/blandet.pdf` | [ ] | [ ] |
| Sladding av PDF (Finn, så Sladd) | `redact/personopplysninger.pdf` | [ ] | [ ] |
| Bokmål ↔ nynorsk | `nynorsk/avsnitt_nb.docx` | [ ] | [ ] |

- [ ] Et filnavn med mellomrom, æøå, parentes og semikolon (for eksempel `Søknad (ny); kopi.pdf`) virker
      for minst OCR og Sladding.
- [ ] En mappe som inngang (OCR og Metadata tar mapper) virker, også fra den eksterne disken.

## Valgfrie innstillinger

- [ ] OCR med flere språk: en flersidig skannet PDF med både norsk og engelsk tekst (verktøyet bruker
      `nor+eng`), og med valget for tekstfil slått på.
- [ ] Sladding av en flersidig PDF: Finn, fjern noen avkrysninger, Sladd. Treffene er sladdet på alle
      sidene, og etterkontrollen sier ingenting er igjen.
- [ ] Sladding med en egen termliste (fil fra `~/Documents`).
- [ ] Stillbilder fra en lang video (over 30 minutter) med «Ved klipp», og med «Hvert 10. sekund».
- [ ] Datawrapper: CSV-filen lagres i mappen du velger (også på den eksterne disken).

## Avbryt

- [ ] Start OCR på en stor PDF (eller Stillbilder på en lang video), og trykk Avbryt midt i.
      Appen viser at jobben er avbrutt.
- [ ] Etterpå er mappen `~/Library/Application Support/no.samarbeidsdesken.verktoy/verktoy/.kjoring/` tom
      (Finder: Gå → Gå til mappe …). Ingen `tesseract`, `ffmpeg` eller `jv` står igjen i Aktivitetsmonitor.
- [ ] Avslutt appen midt i en kjøring (Cmd-Q). Start den igjen og kjør et verktøy: `.kjoring/` er tom
      etterpå.

## Ingen bryter

- [ ] Innstillinger har ingen bryter for å slå av sandkassen.

## Konsoll.app

Filtrer på `sandbox` (og gjerne prosessen `jv`, `tesseract`, `ffmpeg`, `perl`, `pdftotext`, `lt-proc`).
Kjør verktøyene over én gang til. Avvisninger er ventet og stopper ikke verktøyene:

- `mach-lookup com.apple.system.opendirectoryd.libinfo`, `com.apple.system.notification_center`,
  `com.apple.logd`, `com.apple.diagnosticd` (alle Mach-tjenester er stengt)
- `file-read-data ~/.CFUserTextEncoding`

- [ ] Noter alle **andre** avvisninger (operasjon og verktøy, ikke filnavn) og send dem til sidecar-byggeren,
      så profilen kan strammes inn eller rettes.
- [ ] Noter om et verktøy feiler med «Verktøyet kunne ikke startes i beskyttet modus.» eller
      «Filsystemet nektet tilgang».
