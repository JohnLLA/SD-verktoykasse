# metadata – les og fjern

Viser skjult informasjon i filer og lager en vasket kopi. Brukes før deling og
for å sjekke tips. Originalfilen røres aldri.

Støttet: JPEG, PNG, HEIC, PDF, DOCX, XLSX og PPTX. Du kan oppgi flere filer
eller en mappe (bare filene rett i mappen, ikke undermapper).

```
uv run jv metadata vis bilde.jpg
uv run jv metadata vask bilde.jpg notat.docx --out vasket/
```

## vis

Feltene grupperes i *Sted* (GPS), *Person* (forfatter, sist endret av, firma,
leder), *Utstyr* (kamera, programvare), *Tid* og *Annet*. Felt i Sted og Person
har `"sensitive": true` i JSON-rapporten.

## vask

- **Bilder:** `exiftool -all=`, deretter kopieres `Orientation` tilbake
  (`-tagsFromFile @ -Orientation`). Valgt løsning: **orienteringstaggen
  beholdes**, og pikslene roteres ikke. Da blir det ingen ny JPEG-komprimering
  (tapsfritt), og bildet vises som før. Testbildet har orientering 6 og vises
  fortsatt stående 480×640 etter vask.
- **PDF:** `pikepdf` fjerner Info-ordboken og all XMP (`/Metadata` i katalogen,
  på sider og i bilder).
- **Office:** `docProps/core.xml` og `app.xml` skrives på nytt uten person- og
  firmafelt (`dc:creator`, `cp:lastModifiedBy`, `Company`, `Manager`). Alle andre
  deler av filen kopieres uendret. Dette gjøres med `zipfile`, ikke exiftool.

Etter vask leses den nye filen på nytt. Rapporten viser for hver fil hva som
ble fjernet (`removed`), hva som er igjen (`remaining`) og `verified`. Finnes
sted-, person- eller utstyrsfelt igjen, eller står en fjernet verdi fortsatt i
et annet felt, kommer det en advarsel. Utfilene heter `<navn>-vasket.<endelse>`.

## Kjente begrensninger

- Bilder: også fargeprofilen (ICC) fjernes, fordi `-all=` tar alt. Bilder i
  Display P3 (nyere iPhone) kan da få litt blekere farger.
- HEIC: håndteres via exiftool som de andre bildene. Rotasjon som ligger i
  HEIF-strukturen (`irot`) blir værende, men kontrolleres ikke separat. Det
  finnes ingen HEIC-testfil, så den testen hoppes over.
- PDF: bilder inne i PDF-en kan ha egen EXIF i bildedataene, og det fjernes
  ikke. Det gjør heller ikke tekst i selve dokumentet, kommentarer eller
  programspesifikke data (`/PieceInfo`).
- Office: forfatternavn i kommentarer og sporede endringer, `docProps/custom.xml`
  og miniatyrbildet `docProps/thumbnail.jpeg` endres ikke. Egendefinerte felt
  som ser ut som personfelt, vises som advarsel etter vask.
- PDF med åpningspassord og krypterte Office-filer kan ikke behandles. PDF med bare eierpassord (tillatelser) behandles, men den vaskede filen mister krypteringen, og rapporten gir en advarsel.

## Kryptert PDF

En PDF med eierpassord (tillatelser, uten åpningspassord) lagres ukryptert etter vask. Rapporten får da en advarsel i `warnings`; verktøyet krypterer ikke på nytt.
