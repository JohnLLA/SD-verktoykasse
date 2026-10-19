# Spesifikasjon v1 – ni journalistverktøy

Felles for alle: kontrakten i `CLAUDE.md`, ingen nett, originalen røres aldri, norsk rapport.

---

## 1. `compare` – versjonssammenligning

**Hva:** Viser hva som er endret mellom to versjoner av et dokument, for eksempel to utkast av et vedtak.

- **Inn:** to filer, `.txt`, `.md`, `.docx` eller `.pdf` med tekstlag. Ulike formater kan sammenlignes.
- **Ut:** én selvstendig HTML-rapport (all CSS inline, ingen eksterne ressurser) med to kolonner. Slettet tekst rødt og overstreket, ny tekst grønn. Øverst: antall endrede avsnitt, tillagte og fjernede ord.
- **Logikk:** sammenlign avsnitt først, deretter ord innenfor endrede avsnitt (`difflib`). Valg `--ignore-whitespace` (standard på) og `--ignore-case`.
- **Advarsel** når en PDF mangler tekstlag: «PDF-en ser ut til å være skannet. Kjør `ocr` først.»
- **Godkjent når:** en flyttet setning, en endret tallverdi (1 200 000 → 1 250 000) og et slettet avsnitt i testfilene vises riktig.

## 2. `metadata` – les og fjern

**Hva:** Viser skjult informasjon i filer og lager en vasket kopi. Brukes før deling og for å sjekke tips.

- **Inn:** JPEG, PNG, HEIC, PDF, DOCX, XLSX, PPTX. Flere filer eller en mappe.
- **Kommandoer:** `jv metadata vis <fil>` og `jv metadata vask <fil> --out <mappe>`.
- **Vis:** grupper feltene i *Sted* (GPS), *Person* (forfatter, sist endret av, firma), *Utstyr* (kamera, programvare), *Tid* og *Annet*. GPS og personfelt merkes som følsomme i rapporten.
- **Vask:**
  - bilder: `exiftool -all=`, men behold orienteringen slik at bildet ikke snus
  - PDF: `pikepdf`, fjern både Info-ordbok og XMP
  - Office: skriv `docProps/core.xml` og `app.xml` på nytt uten person- og firmafelt
- **Etter vask:** les filen på nytt og bekreft at de følsomme feltene er borte. Rapporter det som eventuelt ble igjen.
- **Godkjent når:** testbildet med GPS og testdokumentet med «Ola Testesen» som forfatter kommer ut uten disse, og bildet har samme orientering.

## 3. `keyframes` – stillbilder fra video

**Hva:** Trekker ut bilder fra video til verifisering eller illustrasjon.

- **Inn:** MP4, MOV, MKV og alt ffmpeg leser.
- **Modus:** `--every 2s` (fast intervall) eller `--scenes 0.3` (ved klipp).
- **Ut:** JPEG-filer med tidskode i navnet (`000012.480.jpg`), pluss en kontaktark-JPEG med alle bildene og tidskoden påskrevet.
- **Rapport:** varighet, oppløsning, bildefrekvens, rotasjon og SHA-256 for videoen, så uttrekket kan dokumenteres.
- **Rotasjon:** respekter rotasjonsmetadata, så stående mobilvideo blir stående bilder.
- **Godkjent når:** testvideoen med kjente klipp på 2, 5 og 8 sekunder gir bilder innenfor ±0,2 s, og den roterte testvideoen gir stående bilder.

## 4. `loudness` – normalisering

**Hva:** Setter lydnivået til standard med ett valg.

- **Inn:** WAV, MP3, M4A, FLAC, og lydsporet i video.
- **Mål:** `--target podcast` (−16 LUFS, −1 dBTP) eller `--target broadcast` (−23 LUFS, −1 dBTP, EBU R128). Egendefinert med `--lufs`.
- **Logikk:** ffmpeg `loudnorm` i to pass. Første pass måler, andre bruker målingene.
- **Ut:** samme format som inn (WAV inn gir WAV ut). For video kopieres bildesporet uten omkoding.
- **Rapport:** integrert loudness og true peak før og etter, målt med `ebur128`.
- **Godkjent når:** testlyd på −30 og −8 LUFS ender innenfor ±0,5 LU av målet og under −1 dBTP.

## 5. `subtitles` – teksting

**Hva:** Gjør en transkripsjon med tidskoder om til undertekster.

- **Inn:** Whisper-JSON (segmenter med `start`, `end`, `text`, eventuelt ordtidskoder), og verktøykassens eksportformat når det finnes.
- **Ut:** `.srt` og `.vtt`.
- **Regler (kan justeres):** høyst 42 tegn per linje og 2 linjer per tekst, minst 1 s og høyst 7 s visning, minst 2 bilder (80 ms) mellom tekster. Del på setningsgrenser og komma før ord, aldri midt i et ord.
- **Ordtidskoder** brukes til delingen når de finnes. Ellers fordeles tiden etter antall tegn.
- **Godkjent når:** et 3 minutters testsegment gir gyldig SRT og VTT (kan leses av ffmpeg uten feil) og ingen linje bryter reglene.

## 6. `pdf-tables` – tabelluttrekk

**Hva:** Henter tabeller fra PDF-er (budsjetter, regnskap, postlister) til regneark.

- **Inn:** PDF med tekstlag. Valg `--pages 3-7`.
- **Ut:** én XLSX med ett ark per tabell (arknavn `s3_t1`), pluss CSV per tabell med `--csv`.
- **Tall:** gjenkjenn norsk format (`1 234 567,50`, `−12`, `(12)` som negativt) og lagre som tall i XLSX, med originalteksten i en kommentar når tolkningen er usikker.
- **Tabeller over flere sider** med samme kolonner slås sammen når `--merge` er valgt.
- **Advarsel** når PDF-en mangler tekstlag (kjør `ocr` først) eller når en tabell har ujevnt antall kolonner.
- **Godkjent når:** testbudsjettet med tusenskille, negative tall i parentes og en tabell over to sider gir riktige tallverdier.

## 7. `ocr` – søkbare PDF-er

**Hva:** Gjør skannede innsynsdokumenter søkbare.

- **Inn:** PDF og bilder (JPEG, PNG, TIFF). Mappe gir en jobb per fil.
- **Logikk:** `ocrmypdf -l nor+eng --skip-text --rotate-pages --deskew`. Sider med tekst fra før hoppes over.
- **Ut:** ny PDF med tekstlag, og valgfritt `.txt` med `--text`.
- **Rapport:** antall sider, hvor mange som fikk OCR, og sider med lav sikkerhet (gjennomsnittlig ordsikkerhet under 60) listet som advarsel.
- **Fremdrift** per side på stderr.
- **Godkjent når:** den skannede testsiden med «Bergen kommune», æ, ø og å blir søkbar, og en skjev side rettes opp.

## 8. `redact` – ekte sladding

**Hva:** Fjerner personopplysninger fra PDF-er slik at teksten faktisk er borte, ikke bare dekket.

- **Inn:** PDF med tekstlag. Skannet PDF gir feilmelding med råd om å kjøre `ocr` først.
- **Finner automatisk:**
  - fødselsnummer og D-nummer (11 siffer, med eller uten mellomrom, kontrollert med mod 11)
  - norske telefonnumre (8 siffer, med eller uten +47 og mellomrom)
  - e-postadresser
  - egne ord og navn fra `--terms fil.txt`
- **To steg:**
  1. `jv redact finn` lager en liste (JSON) over treff med side og utdrag. Brukeren kan stryke treff.
  2. `jv redact sladd --plan treff.json` sladder med PyMuPDFs redaksjon (`add_redact_annot` + `apply_redactions`), som fjerner teksten under.
- **Etter sladding:** fjern metadata, flat ut skjemafelt og kommentarer, og trekk ut all tekst på nytt. Finnes noe av det sladdede igjen, feiler jobben og ingen fil leveres.
- **Navnegjenkjenning** er utenfor v1. Navn legges inn med `--terms`.
- **Godkjent når:** testdokumentet med tre fødselsnumre (ett med mellomrom), to telefonnumre, én e-post og ett ugyldig 11-sifret tall gir riktige treff, det ugyldige tallet blir stående, og ingen av de sladdede verdiene kan hentes ut med `pdftotext` eller PyMuPDF etterpå.

## 9. `nynorsk` – bokmål ↔ nynorsk

**Hva:** Gir et førsteutkast av en tekst på den andre målformen.

- **Inn:** `.txt`, `.md` eller `.docx`. Retning `--to nn` eller `--to nb`.
- **Logikk:** Apertium (`nob-nno` og `nno-nob`). For DOCX oversettes avsnitt for avsnitt, og formatering på avsnittsnivå beholdes.
- **Ukjente ord** (merket med `*` av Apertium) listes i rapporten og markeres i utdata, så journalisten ser hva som må sjekkes.
- **Utdata merkes alltid** som utkast i rapporten.
- **Oppsett:** finnes ikke Apertium og språkparet, stopper agenten og skriver i `docs/oppsett-apertium.md` nøyaktig hva som må installeres. Ingen nedlasting fra agenten.
- **Godkjent når:** testavsnittet oversettes uten feil i kjøringen, ukjente ord listes, og DOCX-avsnittene kommer ut i samme rekkefølge.

## Pakking (Mac)

Hvert verktøy leveres som en egen DMG (`Journalistverktoy-<id>-<versjon>-arm64.dmg`) med en enkel app for Apple Silicon. Appen bygger skjemaet fra verktøyets argparse-oppsett og kjører verktøyet uendret i en underprosess. Systemprogrammene verktøyet trenger, ligger inne i appen, så Homebrew er ikke nødvendig hos brukeren. Appen bruker ikke nett. Hver DMG har `Lisenser/` med lisenstekster og kildeadresser for alt som er pakket inn. DMG-ene signeres med Developer ID og notariseres før de deles. Bygg og notarisering: `pakking/mac/bygg.sh` og `notariser.sh`.
