# Fasit for testdata

Alle filene er syntetiske og laget av `scripts/lag_testdata.py`. Alle personer, firma, saker, fødselsnumre, telefonnumre og adresser er oppdiktet. Lag filene på nytt fra repo-roten med:

```
uv run --no-project --python 3.12 --with reportlab --with pillow --with python-docx \
    --with openpyxl --with pymupdf python scripts/lag_testdata.py
```

Skriptet krever `ffmpeg`, `ffprobe` og `exiftool` og gjør ingen nettkall. Til slutt kontrollerer det hver fil (PyMuPDF, ffprobe/ebur128, exiftool, tesseract hvis det finnes) og avslutter med feil hvis noe ikke stemmer. Teksten i PDF-ene bruker en lokal TTF-skrift (DejaVu Sans på Linux, Arial på macOS). Hvis ingen av dem finnes, brukes Helvetica, og da blir U+2212 (−) erstattet med vanlig bindestrek.

Maskinlesbare fasiter: `pdf-tables/budsjett_fasit.json` og `redact/personopplysninger_fasit.json`.

---

## compare/

`vedtak_v1.*` og `vedtak_v2.*` finnes som `.docx`, `.txt` og `.pdf` (med tekstlag), med samme innhold i alle tre formatene. Tittel: «Vedtak i sak 42/26 – Tilskudd til Fiktivhavn kulturhus». v1 har 6 avsnitt og v2 har 5 (tittelen ikke medregnet).

Endringer fra v1 til v2:

| Endring | v1 | v2 |
|---|---|---|
| Endret tall | avsnitt 2: «tilskudd på **1 200 000** kroner» | avsnitt 2: «tilskudd på **1 250 000** kroner» |
| Flyttet setning | «Tilskuddet utbetales i to like deler.» er setning 2 i avsnitt 2 | den samme setningen står til slutt i avsnitt 4 (sluttrapport) |
| Slettet avsnitt | avsnitt 5: «Ubrukte midler skal betales tilbake til kommunen. Kommunen kan kreve tilbakebetaling dersom vilkårene ikke er oppfylt.» | finnes ikke |

Avsnitt 1, 3 og det siste avsnittet (klage) er uendret. Det endrede avsnittet 2 har altså både et ordbytte (1 200 000 → 1 250 000) og en fjernet setning.

## metadata/

**`bilde_gps.jpg`**: 640×480 piksler lagret liggende, laget med Pillow. EXIF-feltene er satt med exiftool:

| Felt | Verdi | Gruppe |
|---|---|---|
| GPSLatitude / Ref | 60.39745 N | Sted (følsom) |
| GPSLongitude / Ref | 5.32374 E | Sted (følsom) |
| GPSAltitude | 4 m | Sted |
| Make / Model | Testkamera / Fiktiv X100 | Utstyr |
| Software | lag_testdata.py | Utstyr |
| Artist | Ola Testesen | Person (følsom) |
| DateTimeOriginal | 2026:01:15 10:30:00 | Tid |
| Orientation | 6 (Rotate 90 CW) | |

Punktet ligger på Bryggen i Bergen. Med orientering 6 skal bildet vises **stående, 480×640**. Da er det røde feltet øverst, pilen peker opp og «TOPP» kan leses vannrett. Etter vask skal GPS, Artist og kamerafeltene være borte, mens orienteringen (eller en tilsvarende fysisk rotasjon) skal være beholdt, slik at bildet fortsatt vises 480×640 med rødt øverst.

**`dokument_forfatter.docx`**:
- `docProps/core.xml`: `dc:creator` = «Ola Testesen», `cp:lastModifiedBy` = «Kari Fiktivsen», tittel «Internt notat», kommentar «Oppdiktet testdokument»
- `docProps/app.xml`: `Company` = «Eksempelfirma AS», `Manager` = «Per Prøvesen», Application «Microsoft Office Word»

NB: Den exiftool-versjonen som er installert i Linux-skallet, mangler Archive::Zip og kan **ikke** lese Office-metadata. Les derfor DOCX/XLSX/PPTX med `zipfile`.

**`dokument_forfatter.pdf`**:
- Info-ordbok: Author «Ola Testesen», Title «Internt notat», Subject, Keywords, Creator «Microsoft Word», Producer, og de egendefinerte nøklene `/Company` «Eksempelfirma AS» og `/LastModifiedBy` «Kari Fiktivsen»
- XMP: `dc:creator` «Ola Testesen», `dc:title`, `pdf:Producer`, `xmp:CreatorTool`

Etter vask skal verken Info eller XMP inneholde «Ola Testesen», «Kari Fiktivsen» eller «Eksempelfirma».

## keyframes/

**`klipp.mp4`**: 10,00 s, 320×240, 25 fps, H.264, uten lyd. Ensfargede flater med harde klipp:

| Tid | Farge |
|---|---|
| 0–2 s | svart |
| 2–5 s | hvit |
| 5–8 s | blå |
| 8–10 s | gul |

Kontroll: `select='gt(scene,0.3)'` gir klipp ved nøyaktig 2,00, 5,00 og 8,00 s. Verktøyet skal treffe innenfor ±0,2 s.

**`stående.mov`**: 4 s, 180×320 når den vises (testsrc-mønster). Den er lagret som 320×180 med rotasjonsmetadata, som en stående mobilvideo. Bekreftet med ffprobe: stream-tag `rotate=90` og display matrix `rotation: -90` (vis 90° med klokka, samme konvensjon som iPhone). ffmpeg med autorotate dekoder bildene som 180×320. Uttrukne bilder skal derfor være stående (høyde > bredde).

Teknisk merknad: ffmpeg 4.4 i Linux-skallet snur fortegnet når `-metadata:s:v:0 rotate=` skrives, så skriptet sjekker resultatet med ffprobe og skriver på nytt med den andre verdien ved behov.

## loudness/

Tale-lignende signal: rosa støy båndbegrenset til 200–4000 Hz med 4 Hz amplitudemodulasjon (som stavelser), mono, 48 kHz, 16 bit, 20 s. Nivået er målt med `ffmpeg -af ebur128=peak=true`:

| Fil | Integrert loudness | True peak |
|---|---|---|
| `lav.wav` | −30,0 LUFS | −16,3 dBTP |
| `høy.wav` | −8,2 LUFS | −0,8 dBTP |
| `video_med_lyd.mp4` | −20,2 LUFS | −9,3 dBTP |

`høy.wav` er hardt limitert (alimiter med tak på −1 dBFS), så true peak ligger tett under 0. `video_med_lyd.mp4` er 10 s, 320×240 H.264 og AAC i stereo med 48 kHz. Etter normalisering skal bildesporet være kopiert uten omkoding (samme codec og bitstrøm).

Godkjent: begge WAV-filene ender innenfor ±0,5 LU av målet (−16 eller −23 LUFS) og under −1 dBTP.

## subtitles/

**`transkripsjon.json`**: Whisper-format (`text`, `language: "no"`, `segments` med `id`, `seek`, `start`, `end`, `text`, `tokens`, `avg_logprob` og så videre, og `words` med `word` (med mellomrom foran), `start`, `end` og `probability`). Innholdet er et oppdiktet podkastintervju om Fiktivhavn kulturhus.

- 46 segmenter, fra 0,50 s til 180,01 s. Det er 0,4 s pause mellom segmentene. Ordene er 389 til sammen.
- Over 7 s: segment 4 (13,63 s, en lang setning med flere komma), segment 24 (10,16 s) og segment 44 (8,24 s). Disse må deles.
- Under 1 s: «Ja.», «Mm.», «Takk.» (0,70 s) og «Takk selv.» (0,77 s). Disse må forlenges til minst 1 s, uten at det blir mindre enn 80 ms til neste tekst.
- Ordtidskodene ligger alltid innenfor segmentet sitt og er fordelt etter ordlengde.

**`transkripsjon_uten_ord.json`**: samme innhold, men uten `words`. Tiden må da fordeles etter antall tegn.

Godkjent: SRT og VTT kan leses av ffmpeg, har høyst 42 tegn per linje og 2 linjer per tekst, viser hver tekst 1–7 s og har minst 80 ms mellom tekstene.

## pdf-tables/

**`budsjett.pdf`**: 2 sider med tekstlag og rutenett i tabellene. Tallene står i norsk format med vanlig mellomrom som tusenskille og komma som desimaltegn. Negative tall skrives på tre måter: `(51 499,75)`, `−145 320,40` (U+2212) og `-410 000,00` (bindestrek).

Tabell 1, «Hovedoversikt drift», på side 1 (4 kolonner: Post, Regnskap 2025, Budsjett 2026, Endring):

| Post | Regnskap 2025 | Budsjett 2026 | Endring |
|---|---|---|---|
| Skatt på inntekt og formue | 1234567.50 | 1301000.00 | 66432.50 |
| Rammetilskudd | 2450000.00 | 2398500.25 | −51499.75 «(51 499,75)» |
| Brukerbetalinger | 312400.75 | 298000.00 | −14400.75 «(14 400,75)» |
| Salgsinntekter | 87650.00 | 91200.00 | 3550.00 |
| Renteutgifter | −145320.40 «−» | −162000.00 «−» | −16679.60 «−» |
| Avdrag på lån | −410000.00 «-» | −398250.60 «-» | 11749.40 |

Tabell 2, «Fordeling per ansvar», går over sidene 1 og 2. Den har de samme fire kolonnene (Ansvar, Rammeområde, Budsjett 2026, Endring fra 2025), og overskriftsraden er gjentatt på side 2. Den har 50 datarader: 24 på side 1 og 26 på side 2. Ansvar går fra 1000 til 1490 i steg på 10. Kontrollsummer: Budsjett 2026 = **57 976 226,25**, Endring = **−56 787,00**. Med `--merge` skal tabellen bli ett ark med 50 rader. PyMuPDF `find_tables()` finner tabellene som (7×4), (25×4) og (27×4). Alle verdiene står i `budsjett_fasit.json`.

**`skannet_tabell.pdf`**: side 1 av budsjettet som gråtonebilde i 150 dpi, uten tekstlag. Skal gi advarselen om å kjøre `ocr` først.

## ocr/

Kildeteksten (DejaVu Sans, 13 pt) har tittelen «Bergen kommune – Melding om vedtak» og inneholder blant annet «Særlige vilkår», «søknaden», «sjøen», «Høyden», «Åse Prøvesen» og «Bergen kommune» to ganger. Siden er gjort om til et gråtonebilde i 200 dpi med PyMuPDF. Ingen av de skannede sidene har tekstlag.

- `skannet_side.pdf`: 1 side, bare bilde. Tesseract (`-l nor`) leser «Bergen kommune», æ, ø og å.
- `skjev_side.pdf`: det samme bildet rotert 3° mot klokka med hvit bakgrunn (siden blir litt større). Etter `--deskew` skal linjene være vannrette.
- `blandet.pdf`: side 1 har tekstlag («Side med tekstlag … Ærlig, søt og åpen.») og skal hoppes over. Side 2 er den skannede siden og skal få OCR. Rapporten skal vise 2 sider, der 1 fikk OCR.

## redact/

**`personopplysninger.pdf`**: 2 sider med tekstlag. **`termer.txt`**: «Kari Fiktivsen».

| Type | Tekst i PDF | Side | Sladdes |
|---|---|---|---|
| Fødselsnummer (med mellomrom) | `010190 12480` | 1 | ja |
| Fødselsnummer | `15068527101` | 2 | ja |
| Fødselsnummer | `29029241803` | 2 | ja |
| D-nummer (dag + 40) | `41038815278` | 2 | ja |
| 11 siffer, feil kontrollsiffer | `15068527102` | 2 | **nei** |
| Telefon | `58 01 23 45` | 1 | ja |
| Telefon med +47 | `+47 58 98 76 54` | 2 | ja |
| E-post | `kari.fiktivsen@example.no` | 1 | ja |
| Term (`--terms`) | `Kari Fiktivsen` | 1 og 2 (én gang per side) | ja |

Dette skal **ikke** sladdes: saksnummeret «2026/1234», datoen «3. mars 2026» og beløpet «45 000 kroner».

### Kontrollsifre (mod 11)

Nummeret er `d1 d2 m1 m2 å1 å2 i1 i2 i3 k1 k2`. Vektene er
- k1: 3 7 6 1 8 9 4 5 2
- k2: 5 4 3 2 7 6 5 4 3 2 (over de ti første sifrene, k1 medregnet)

Kontrollsifferet er `11 − (sum mod 11)`. Blir resultatet 11, er sifferet 0. Blir det 10, er individnummeret ugyldig, og det neste prøves.

| Nummer | Individnr. | Sum 1 | k1 | Sum 2 | k2 |
|---|---|---|---|---|---|
| 01019012480 | 124 | 102 (102 mod 11 = 3 → 8) | 8 | 110 (mod 11 = 0 → 11 → 0) | 0 |
| 15068527101 | 271 | 198 (mod 11 = 0 → 0) | 0 | 164 (mod 11 = 10 → 1) | 1 |
| 29029241803 | 418 | 198 (→ 0) | 0 | 173 (mod 11 = 8 → 3) | 3 |
| 41038815278 | 152 | 191 (mod 11 = 4 → 7) | 7 | 179 (mod 11 = 3 → 8) | 8 |
| 15068527102 | 271 | som over | 0 | 164 → 1, men siste siffer er 2 | **feil** |

Utregning for det første nummeret: k1 = 0·3+1·7+0·6+1·1+9·8+0·9+1·4+2·5+4·2 = 102, og 11 − 3 = 8. k2 = 0·5+1·4+0·3+1·2+9·7+0·6+1·5+2·4+4·3+8·2 = 110, og 11 − 0 = 11 → 0.

Hvert nummer er funnet ved å starte på et vilkårlig individnummer og gå oppover til begge kontrollsifrene ble gyldige. Ingen av dem er hentet fra en ekte person. Fordi alle 11-sifrede tall med gyldige kontrollsifre i prinsippet kan være tildelt noen, skal tallene aldri brukes utenfor testene. (Skatteetatens syntetiske testnumre har måned + 80. De ble valgt bort fordi verktøyet kanskje også sjekker datoen.)

### Telefonnumre

Begge numrene ligger i serien **58**. I Nkoms nummerplan er 58 en serie for **12-sifrede** M2M/IoT-numre (58 00 00 00 00 00–58 99 99 99 99 99), så et **8-sifret** nummer som begynner på 58, kan ikke være tildelt en abonnent. (8-sifrede fasttelefonnumre er 20–39, 50–57 og 60–79, mobilnumre er 40–49 og 90–99, og 59 er 8-sifret M2M.) Detektoren må derfor godta 8 siffer uansett første siffer, slik spesifikasjonen sier, og ikke bare mobilserier.

### E-post

`example.no` er brukt fordi instruksen krever det. Domenet er ikke reservert slik `example.com` er i RFC 2606, men adressen er oppdiktet og brukes bare i en lokal testfil.

## nynorsk/

- `avsnitt_nb.txt` / `avsnitt_nn.txt`: tre avsnitt hver med nøytralt innhold (biblioteket i Fiktivhavn). nn-filen er en manuell referanse, ikke en fasit ord for ord.
- Oppdiktede ord som Apertium ikke kjenner: **«fjordglimring»** (avsnitt 2) og **«knaskelure»** (avsnitt 3). Stedsnavnet «Fiktivhavn» er også oppdiktet og kan bli merket som ukjent.
- `avsnitt_nb.docx` har avsnittene i denne rekkefølgen: overskrift (Heading 1) «Lengre åpningstider på biblioteket», et avsnitt der «holder åpent lenger om kvelden» er **fet**, et vanlig avsnitt, «Nytt tilbud:», en punktliste (List Bullet) med 3 punkter (det andre inneholder «fjordglimring», det tredje «knaskelure») og et vanlig avsnitt. Rekkefølgen og stilen på avsnittsnivå skal være den samme i utdataene.

NB: Apertium er ikke installert i Linux-skallet.

## datawrapper/

Laget av `scripts/lag_testdata_datawrapper.py` (kjøres også til slutt av `lag_testdata.py`), med bare openpyxl og en liten BIFF8-skriver for `.xls`:

```
uv run --frozen --all-packages python scripts/lag_testdata_datawrapper.py
```

Alle steder og tall er oppdiktet. Filene er like byte for byte hver gang. Fasiten er den forventede TSV-en fra `jv datawrapper lag`, byte for byte (`<fil>.fasit.tsv`, og `<fil>.<valg>.fasit.tsv` for andre valg). Den skrives fra de forventede verdiene i skriptet, ikke fra verktøyet.

| Fil | Tilfelle | Fasit |
|---|---|---|
| `ssb_befolkning.xlsx` | SSB-lignende: tittel over to linjer (sammenslått A1:F1), tom rad, årstall i overskriften, «Hele landet» som sumrad, tall med U+00A0 og U+202F som tusenskille lagret som tekst, «−0,5», SSB-symbolene `.`, `..`, `:`, `-` og `x`, kilde, to fotnoter og tegnforklaring | `ssb_befolkning.fasit.tsv`, `ssb_befolkning.med-sum.fasit.tsv` |
| `to_overskriftsrader.xlsx` | overskrift over to rader med sammenslåtte celler (A2:A3, B2:C2, D2:E2) → «2023 – Menn»; tittel og kilde rett inntil tabellen | `to_overskriftsrader.fasit.tsv` |
| `sumrader.xlsx` | hierarkisk tabell (fylke/kommune) med tomme etiketter, to «Sum»-rader, «I alt» og sumkolonnen «Totalt» | `sumrader.fasit.tsv`, `sumrader.med-sum.fasit.tsv` |
| `to_tabeller.xlsx` | to tabeller i ett ark med tomme rader mellom, hver med tittel; tabell 2 er størst og foreslås; «54 %» som tekst | `to_tabeller.fasit.tsv` (tabell 2), `to_tabeller.tabell1.fasit.tsv` |
| `skjult_rad.xlsx` | skjult rad (4), skjult kolonne (C) og et skjult ark med flest tall; arket «Data» foreslås foran «Oversikt» | `skjult_rad.fasit.tsv` |
| `tall_som_tekst.xlsx` | tall lagret som tekst («1 234 567,50», «(51 499,75)», «12,5 %»), tvetydige «1.234» og «12.5» (C4, D4), koden «0301», Excel-datoer, en celle formatert som prosent (0,125) og `#DIV/0!` | `tall_som_tekst.fasit.tsv` |
| `semikolon_cp1252.csv` | semikolon, Windows-1252, CRLF, æøå, desimalkomma, U+00A0 som tusenskille, sitert felt, `..` og en «Sum»-rad | `semikolon_cp1252.fasit.tsv` |
| `bytt.csv` | UTF-8 med BOM og komma; første kolonne er tall og første rad tekst, så bytte foreslås | `bytt.fasit.tsv`, `bytt.bytt.fasit.tsv` (med `--bytt`) |
| `omsetning.xls` | `.xls` (BIFF8): sammenslått tittel, årstall, datoer, skjult rad, «I alt», `..`, kilde og et skjult ark | `omsetning.fasit.tsv` |
| `tom.xlsx`, `tom.csv` | tom arbeidsbok og tom fil | kode 1, «Filen er tom» |
| `odelagt.xlsx` | avkuttet zip | kode 1, «ødelagt» |
| `passord.xlsx` | OLE-fil med `EncryptionInfo`, slik krypterte .xlsx ser ut | kode 1, «passordbeskyttet» |
