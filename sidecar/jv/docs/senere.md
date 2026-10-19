# Senere (bygges ikke i v1)

- Støyfjerning med DeepFilterNet (går på CPU, men krever modellfil og mer pakking)
- Navnegjenkjenning i `redact` (lokal NER-modell)
- Skrivebordsskall med dra-og-slipp, eller innbygging i LLAs verktøykasse som sidecar
- Windows-pakking med ffmpeg, exiftool, Tesseract og Apertium inkludert
- Nettarkiv: lagre en nettside som PDF og WARC med tidsstempel og hash

## Fra kontraktvokter

- `compare`: gi `changed_paragraphs` (alle endrede, inkl. slettet/nye) et tydeligere navn, f.eks. `paragraphs_total_changed`, så det ikke forveksles med `paragraphs_changed`.
- `compare`: parring av avsnitt i en «replace»-blokk (`_pair_block`) er O(n·m) – 1000 mot 1000 ulike avsnitt tar ca. 4 s; kan merkes på store dokumenter.
- `compare`: setninger som bytter plass innenfor samme avsnitt vises som ordendringer, ikke som flyttet – nevn det i README.
- `compare`: flyttet setning vises rødt/grønt med stiplet ramme og telles ikke i ord lagt til/fjernet – rimelig tolkning, vurder om det skal beskrives i README.
- `metadata`: HEIC er ikke testet mot ekte fil – testfil-smed bør lage en HEIC-fil med GPS hvis exiftool kan skrive den.
- `metadata`: `docProps/custom.xml`, kommentarforfattere og sporede endringer i Office-filer vaskes ikke – vurder for v2.
- `metadata`: små utvidelser utover spesifikasjonen (`.heif`, XMP på sider/bilder i PDF, JSON-rapport og kode 1 ved delvis feil i mappe) – notert, ingen handling.
- `subtitles`: linjebrytingen vekter balanse høyt, så linjer kan ende på småord («… et / tilskudd») – lesbarhet.
- `subtitles`: verktøykassens eksportformat støttes ikke ennå (spesifikasjonen sier «når det finnes»).
- `pdf-tables`: ansvarskoder som «1000» lagres som tall i XLSX – vurder å lagre koder som tekst.
- `pdf-tables`: CSV skriver heltall med desimal fra `repr` («250000.0») – kosmetisk.
- `pdf-tables`: stoppmeldingen sier «de 1 filene», og når fil 1 feiler sier den «Fant ingen tabeller» – rett flertall og årsak.
- `pdf-tables`: to importlinjer fra `jv_common` i `cli.py` kan slås sammen.
- `nynorsk`: blandet formatering i DOCX etterlater en tom fet `w:r` – ufarlig, tapet meldes allerede.
- `nynorsk`: oppdeling ved `*`, `#` og `@` gir ca. 15 % dårligere oversettelse rundt symbolet (kjønn, artikler, verbformer). Dokumentert i README.
- `nynorsk`: siste ord i et avsnitt kan få en annen gyldig form avhengig av gruppering («også»/«òg»).
- `keyframes`: `inputs[].path` og `videos[].path` viser stien slik `pathlib` normaliserer den (`http://…` blir `http:/…`) – samme fil og riktig SHA-256, bare kosmetisk.
- `keyframes`: én ffmpeg-prosess per bilde (`core.py:285–304`) – tregt for lange videoer med kort `--every`.
- `keyframes`: testene sjekker at bildene er stående, men ikke rotasjonsretningen (følger ffmpegs autorotering) – godtas.
- `keyframes`: ekstra rapportfelt `videos` (varighet, oppløsning, fps, rotasjon, kodek) – innenfor spesifikasjonen, notert.
- `loudness`: ved skadet fil viser feilmeldingen hele `file:/<absolutt sti>` fra ffprobe – vis bare filnavnet.
- `loudness`: inngangsformatene MOV, M4V og MKV er lagt til utover listen i spesifikasjonen (følger av «lydsporet i video») – notert.
- `loudness`: tapsbaserte utfiler (MP3/AAC) får høyere bitrate enn kilden – dokumentert i README.
- `ocr`: libtiff skriver «tempfile.tif: Using code not yet in table.» på stderr (fd 2) ved skadet LZW-TIFF før den norske feilmeldingen – engelsk støy, fanges ikke av `warnings.catch_warnings()` (`core.py:142–157`).
- `ocr`: tilfeldig skadet PDF som MuPDF reparerer til 0 sider gir «har ingen sider» – «skadet eller avkuttet» hadde vært mer presist (`core.py:180/193`).
- `ocr`: PDF med ødelagt bildestrøm gir kode 0 med bare advarselen «OCR fant ingen ord» – ingen beskjed om at filen er skadet.
- `ocr`: navnekollisjon gir `x-ocr-2.pdf` når `x.pdf` og `x.png` behandles sammen, og `jobs=None` bruker alle kjernene – vurder fast lavere tall på maskiner med lite minne.
- `ocr`: ekstra rapportfelt (`confidence`, `skipped_pages`, `type`, `source`) – innenfor spesifikasjonen, notert.
- `ocr`: når alle temp-mapper er ubrukelige, kaster `_work_dir()` `OSError` og gir «Intern feil …» med kode 2 og to punktum på slutten. Det bør være brukerfeil (kode 1), uten dobbelt punktum.
- `ocr`: `_work_dir()` endrer `os.environ["TMPDIR"]` og `tempfile.tempdir` prosessglobalt. Det er trygt så lenge `ocr_many` kjører sekvensielt og verktøyet kjøres som egen prosess, men det er ikke trådsikkert. Det bør stå i en kommentar eller i README.
- `ocr`: en `TMPDIR` som ikke finnes eller ikke kan skrives til, gir ingen melding. Verktøyet går stille videre til neste temp-mappe. Det er akseptert.
- `redact`: forkastede kandidater sier ikke om en forekomst er usynlig tekst (`3 Tr`, hvit, Form XObject) – merk slike treff i `finn` eller foreslå `"sladd": true`.
- `redact`: blokkjustert tekst (LibreOffice, `text-align: justify`) og skjemaer med grupper i egne bokser gjør ekte numre om til forkastede kandidater – la avstandsgrensen følge ordavstanden på linjen.
- `redact`: advarselen «… er sladdet noen steder og strøket andre steder» er forvirrende når brukeren ikke har strøket noe.
- `redact`: ekstra term i planen med omregnet `termer_sha256` godtas uten advarsel – meld «termlisten er endret».
- `redact`: `finn` sier ingenting om skjult tekst (f.eks. `0 Tz`) som bare etterkontrollen ser – brukeren får først vite det når `sladd` stopper.
- `redact`: disse stopper trygt med kode 1 og kan ikke sladdes: tegn i omvendt rekkefølge, `0 Tz`, flismønster, orddeling over linjeskift, sperret tekst (`Tc`), fnr limt til et nytt tall med skilletegn («15068527101/2»).
- `common` (meldt av compare, subtitles, pdf-tables, nynorsk og keyframes): engelske argparse-meldinger og «Intern feil» ved manglende skrivetilgang i utmappe – rettet i `verktoy/common`.

## Fra kontraktvokter: pakking

- Minste macOS-versjon er 26.0 for keyframes, loudness og redact, og 26.6.2 for ocr, fordi Homebrew-binærene er bygget for macOS 26. Bygg dem selv med lavere `MACOSX_DEPLOYMENT_TARGET` hvis eldre Macer skal støttes.
- Lisenstekstene for expat og libffi er hentet fra eldre headere i macOS SDK (expat 2.7.4, libffi 3.4-rc1). Opphavsrettsårene kan være eldre enn versjonene som er pakket inn.
- Bygg DMG-ene på nytt fra den flettede main før utdeling.
- gawk og libintl har innebygde standardstier til `/opt/homebrew/Cellar/…`. De brukes ikke, og røyktesten uten `/opt/homebrew` er grønn.
- Minste macOS for nynorsk er 26.0.
