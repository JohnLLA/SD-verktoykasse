# redact – ekte sladding av PDF

Fjerner personopplysninger fra PDF-er slik at teksten faktisk er borte, ikke bare
dekket med en svart boks. Alt skjer lokalt.

Verktøyet finner automatisk:

- fødselsnummer og D-nummer (11 siffer, med eller uten mellomrom som 6+5, også
  over et linjeskift; begge kontrollsifrene kontrolleres med mod 11, og D-nummer
  kjennes på at første siffer er 4–7)
- norske telefonnumre (8 siffer i vanlige grupperinger som `58012345`,
  `58 01 23 45`, `580 12 345`, `5801 2345`, med eller uten `+47`/`0047`)
- e-postadresser
- egne ord og navn fra `--terms fil.txt` (ett per linje, uavhengig av store/små bokstaver)

Fødselsnummer med uvanlig gruppering eller skilletegn (`2 902 924 180 3`,
`150685-27101`, `29.02.92 41803`, skråstrek, tankestrek, midtpunkt) finnes også når
kontrollsifrene stemmer. Telefonnummer kan også skrives `58-01-23-45` og
`58.01.23.45`. Et løst siffer foran eller bak («Rad 1 15068527101», «… 2 vedlegg»,
nummererte lister) hindrer ikke treff. Et nummer som henger sammen med andre sifre
uten mellomrom eller via skilletegn (`1-15068527101`, `150685271012`), er ikke et
treff. Teksten normaliseres samlet (NFC og NFKC, så «A» + kombinerende ring blir
«Å»), og tegn uten bredde (myk bindestrek, nullbreddetegn, ordskjøt, BOM) fjernes
før søket. Termene i termfilen normaliseres på samme måte, så NFC/NFD-forskjeller
(for eksempel navn kopiert fra Finder) ikke betyr noe.
Termer treffer også i genitiv og sammensetninger med bindestrek («Kari Fiktivsens»,
«Fiktivsen's», «Fiktivsen’», «Fiktivsen-saken»), og hele ordet sladdes. Telefon- og
fødselsnummer kan ha opptil seks mellomrom eller tabulatorer mellom gruppene.

Søket går gjennom all tekst: synlig tekst, tekst i innholdslag som er slått av,
tekst utenfor sideflaten, kommentarer og skjemafelt (flates ut), og i tillegg
bokmerker, lenkeadresser (også `mailto:`), sidelabels og metadata. Feltet
`plassering` i planen sier hvor treffet er: `side`, `skjult lag`,
`utenfor sideflaten`, `bokmerke`, `lenke`, `sidelabel` eller `metadata`.

## Slik brukes det

```
uv run jv redact finn sak.pdf --terms termer.txt --out ut
# gå gjennom ut/sak-treff.json, stryk treff ved å sette "sladd": false
uv run jv redact sladd sak.pdf --plan ut/sak-treff.json --out ut
```

`finn` skriver en plan (JSON) med side, plassering, utdrag og rektangler (i vanlige
sidekoordinater) for hvert treff, og SHA-256 for PDF-en. `sladd` leverer `ut/sak-sladdet.pdf`.

## Sikkerhet

- `sladd` nekter å kjøre uten `--plan` og når PDF-ens SHA-256 ikke stemmer med
  planen. `sladd` kjører gjenkjenningen på nytt med termene i planen og krever at
  planen og resultatet stemmer én til én: hvert treff i planen må finnes (samme
  type, tekst, side, plassering og rektangler), og hvert treff i PDF-en må stå i
  planen. Treff strykes derfor med `"sladd": false`, ikke ved å slette dem. Er
  listen med termer endret, også med en ny `termer_sha256`, mangler treffene for
  den nye termen i planen, og planen avvises med beskjed om å kjøre `finn` på
  nytt. Planen kan bare brukes til å stryke treff.
- Kommentarer og skjemafelt flates ut før søket, slik at synlige verdier også
  sladdes, og selve kommentar-/feltobjektene forsvinner.
- Sladdingen bruker PyMuPDF `apply_redactions` med `text=PDF_REDACT_TEXT_REMOVE`
  (også usynlig OCR-tekst), `images=PDF_REDACT_IMAGE_PIXELS` (pikslene under
  boksen blankes) og `graphics=PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED`.
- Innholdslag (OCG) slås sammen før søk og sladding, så skjult tekst blir funnet
  og sladdet. I utfilen er lagene borte, og innhold som var skjult, er synlig.
- Sideflaten utvides midlertidig, så tekst utenfor siden blir funnet og sladdet.
  De opprinnelige sidestørrelsene settes tilbake før lagring.
- Alltid fjernet: metadata (Info og XMP), bokmerker, sidelabels, alle lenker,
  innebygde filer, JavaScript og handlinger (`OpenAction`, `AA`), navngitte mål,
  strukturtreet (tagger og alternativ tekst), `PieceInfo` og alle andre nøkler i
  katalogen og sideordbøkene som ikke trengs for å vise sidene. Dette gjelder også om treffet der er strøket i planen. Filen lagres
  på nytt fra bunnen (`garbage=4, clean=True`, ikke inkrementelt), så eldre
  versjoner forsvinner.
- **Etterkontroll** før filen skrives:
  1. Teksten trekkes ut på nytt med PyMuPDF og `pdftotext` (vanlig og `-layout`),
     med alle lag på og uten klipping til siden, og hver sladdet verdi søkes etter
     med og uten mellomrom.
  2. Selve gjenkjenningen (fødselsnummer/D-nummer med mod 11, telefon, e-post,
     termer) kjøres på all tekst i utfilen: sideteksten, og alle strenger, navn og
     kommentarer i alle PDF-objekter og dekomprimerte strømmer, riktig dekodet
     (PDFDocEncoding, UTF-16, hex, oktale escapes). Bare strømmer som faktisk
     brukes som bilde (og har bildedata av riktig størrelse) eller som skriftfil
     (og ser ut som en), hoppes over. ToUnicode-CMap-er leses strukturelt, så
     ligaturer som `fi` ikke blir falske treff. Bare treff som er strøket i
     planen, tillates.
  3. Metadata, bokmerker, sidelabels, lenker, kommentarer, skjemafelt, innebygde
     filer, innholdslag og antall revisjoner sjekkes.

  Ett funn betyr ingen utfil, avslutningskode 1 og en norsk forklaring (verdiene
  vises maskert).

## Ingen treff

`finn` uten treff gir kode 0, en tom plan og «Fant ingen treff …». `sladd` med en
plan der ingenting er merket, gir kode 0 og en vasket kopi (metadata, bokmerker,
lenker og så videre er fjernet, og etterkontrollen er kjørt), med sammendraget
«Ingen treff ble merket for sladding. Les gjennom dokumentet selv.» Verktøyet sier
aldri at et dokument er fritt for personopplysninger.

## Kjente begrensninger

- Krever tekstlag. Skannede PDF-er gir feilmelding med råd om å kjøre `jv ocr`
  først. Sider uten tekst i en ellers tekstbasert PDF gir en advarsel.
- Navn finnes bare via `--terms`; det er ingen automatisk navnegjenkjenning.
- Fødselsdatoen i nummeret sjekkes ikke, bare kontrollsifrene (da fanges også
  syntetiske og H-numre). Unntaket er dag eller måned 00, som aldri er gyldig.
- Gjenkjenning i rå PDF-strømmer kan ikke lese tekst i skrifter med egen koding
  (typisk innebygde delskrifter); der er sideteksten fra PyMuPDF og `pdftotext`
  kontrollen. Tekst som ligger mer enn 10 000 pt utenfor siden, finnes kanskje ikke av
  `finn`; havner slikt i etterkontrollen, stoppes jobben.
- Strukturtreet fjernes, så en tagget PDF mister taggene (tilgjengelighet).
  Interne lenker og navngitte mål fjernes også.
- Noen sjeldne oppsett gjør at jobben stopper (trygt, uten utfil): tegn eller
  deler av et nummer lagt ut i omvendt rekkefølge, orddeling over linjeskift i et
  navn, tekst med horisontal skalering 0 og tekst i flismønstre.
- **Tabeller og avstand:** siffergrupper slås bare sammen når de står tett på
  siden: på samme linje med høyst omtrent to vanlige mellomrom (eller så bredt som
  mellomrommene/tabulatorene som faktisk er skrevet), eller over et linjeskift når
  neste linje følger rett under (orddelt avsnitt, sifre stablet loddrett). Tall
  fra ulike tabellceller blir derfor ikke automatisk ett fødsels- eller
  telefonnummer. Slike kandidater står likevel i planen som vanlige treff med
  `"forkastet": true`, `"sladd": false`, grunn og rektangler. Sammendraget fra
  `finn` sier hvor mange det er («… ble IKKE merket for sladding»), og `sladd`
  gjentar det i sammendraget hvis noen står igjen usladdet. **Et nummer som med
  vilje er delt opp med stor avstand på linjen, havner også her.** Gå derfor alltid
  gjennom de forkastede, og sett `"sladd": true` på dem som skal bort (det virker
  også når de forkastede er de eneste treffene). Ellers kan bare `sladd` endres på
  disse oppføringene. En forkastet kandidat godtas i etterkontrollen bare
  der `pdftotext -bbox-layout` viser nøyaktig de samme ordboksene som cellene i
  planen. I innholdsstrømmer og strenger leses hvert tekstobjekt (en streng eller
  en hel TJ-array, der store justeringer regnes som mellomrom) for seg, så separate
  celler danner aldri et nummer der, og forkastede verdier godtas aldri. Står den
  samme verdien som ett tekstobjekt et sted i dokumentet (synlig med justering
  eller skjult), er den ikke forkastet, men et vanlig treff. Finnes en skjult kopi
  som ikke kan plasseres på siden, advarer `finn`, og `sladd` stopper uten fil.
- Avstanden måles mot ordmellomrommene på linjen, så blokkjustert tekst (der alle
  mellomrom er strukket) ikke gjør ekte numre om til forkastede kandidater.
- Kontonumre skrevet 4.2.5 (`1425.31.00827`) regnes ikke som fødselsnummer, selv
  om kontrollsifferet tilfeldigvis består mod 11. Følgen er at et ekte fødselsnummer
  skrevet i 4-2-5-oppsett (`0101.90.12480`) ikke blir funnet.
- **Stille kandidater:** en forkastet kandidat står alltid i planen hvis tallrekken
  består kontrollsifrene, uansett sifferoppsett og skilletegn (3+3+5, 1+10,
  «150.685.» + «27101» ...). Bare tallrekker der minst ett ord entydig er noe
  annet, er utelatt: en dato med firesifret år (`12.03.2026`), et saksnummer
  (`2026/2911`) eller et beløp med desimalkomma og to desimaler (`1 234,56`).
  Tusenskille alene («150.685») er ikke nok. Hele tallrekken blir stille hvis ett
  ord ligner dato (firesifret år), saksnummer (`19xx/` eller `20xx/`) eller beløp
  med to desimaler. Det kan i teorien skjule et fødselsnummer skrevet på
  konstruerte måter, for eksempel «685271,01» som siste del. De stille sladdes
  ikke, `finn` og `sladd` advarer med antallet, og etterkontrollen kjenner dem.
- Fødselsnummer med `/` mellom gruppene blir ikke funnet som ett nummer, og heller
  ikke «150685- 27101» med mellomrom etter bindestreken. Det samme gjelder
  celledeling med bindestrek: «150685-» + «27101» og «150685» + «-27101».
- En 8-sifret gruppe sammen med 3 sifre, fordelt på 1–2 celler (3+8, 8+3, 3+5+3,
  ...), blir et telefonnummer pluss tre siffer: de 8 sladdes som telefon, og de
  3 siste blir stående.
- Fødselsnummer satt sammen av flere løse grupper (`2 902 924 180 3`) i en lang
  rekke tall med mellomrom kan gi falske treff når 11 av sifrene tilfeldigvis
  består mod 11. Slike treff strykes i planen.
- Tekst som er tegnet som bilde eller konturer (uten tekstlag) kan ikke finnes.
  Pikslene under en sladdeboks blankes likevel.
- Sladder du en verdi ett sted og stryker den et annet sted, blir den stående der
  den er strøket. Rapporten advarer om dette.
- Uten `pdftotext` (`brew install poppler`) brukes bare PyMuPDF i etterkontrollen,
  med en advarsel i rapporten.
- Vektorgrafikk som berører en sladdeboks fjernes helt (for eksempel en tabellinje),
  og bilder under boksen får hvite piksler der boksen ligger.
