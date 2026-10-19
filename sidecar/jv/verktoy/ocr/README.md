# ocr – søkbare PDF-er

Gjør skannede innsynsdokumenter søkbare. Tar PDF-er og bilder (JPEG, PNG,
TIFF) og lager en ny PDF med usynlig tekstlag. En mappe gir én jobb per fil
(bare filene rett i mappen, ikke undermapper). Originalen røres aldri.

```
uv run jv ocr innsyn/skannet.pdf --out ut/ --text
uv run jv ocr innsyn/ --out ut/
```

- Språk: norsk og engelsk (`nor+eng`).
- Sider som har tekst fra før, hoppes over og kopieres uendret.
- Snudde sider roteres, og skjeve sider rettes opp.
- `--text` lager også `<navn>-ocr.txt` med all teksten i den nye PDF-en
  (både teksten som fantes og den nye OCR-teksten), med sideskift (`\f`)
  mellom sidene.
- Rapporten viser antall sider, hvilke sider som fikk OCR, gjennomsnittlig
  ordsikkerhet per OCR-side, og en advarsel for hver side med sikkerhet under 60.
- Fremdrift skrives som JSON-linjer på stderr.

Krever `tesseract` med språkdata `nor` og `eng`, og `ghostscript`:
`brew install tesseract tesseract-lang ghostscript`.

## Valg og kjente begrensninger

- **ocrmypdf-valg:** `language=nor+eng`, `skip_text=True` (= `--skip-text`/`--mode skip`),
  `rotate_pages=True`, `deskew=True`, `output_type="pdf"`. I ocrmypdf 17
  kan `--skip-text` og `--deskew` kombineres: rotasjon og oppretting gjelder
  bare sidene som får OCR, mens sider med tekst kopieres uendret. `--clean`
  (unpaper) brukes ikke.
- **Vanlig PDF, ikke PDF/A.** Det unngår at ghostscript konverterer hele filen.
- **Rettede sider blir nye bilder.** Oppretting og rotasjon gjør at siden
  kodes på nytt, så filen kan bli større enn originalen.
- **Sikkerhet** måles ved å kjøre tesseract (TSV) én gang til på hver OCR-side
  i den nye PDF-en (300 dpi). Det er uavhengig av ocrmypdfs interne filer, men
  gjør jobben omtrent dobbelt så lang. Tallet er et hint, ikke en garanti.
- **Bilder uten oppløsning (DPI):** da brukes 300 dpi, og rapporten gir en
  advarsel. Sidestørrelsen i PDF-en kan da avvike fra originalen.
- Bare én side per bildefil er testet (flersidig TIFF er ikke testet).
- Krypterte, passordbeskyttede og digitalt signerte PDF-er avvises med en
  norsk melding.
- **Alle filer kontrolleres før OCR starter.** Hver PDF åpnes og hver side
  tegnes i lav oppløsning. Bilder dekodes helt. Skadede eller avkuttede filer
  avvises med en norsk melding før noen fil behandles.
- **Reparerte PDF-er:** mangler bare kryssreferansetabellen eller trailer, men
  innholdet er helt, lagres en reparert kopi i en midlertidig mappe og brukes til
  OCR. Rapporten gir da en advarsel. Feiler en fil likevel underveis i en
  kjøring med flere filer, sier feilmeldingen hvilke filer som ble ferdige.
- Hvilke sider som «har tekst», avgjøres av ocrmypdf. En side med bare litt
  tekst (for eksempel et stempel som tekst) hoppes over i sin helhet.
