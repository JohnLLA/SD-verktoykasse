# Klargjør for Datawrapper – spesifikasjon

Verktøy nummer ti i SD-Verktøy. Brukeren slipper en Excel- eller CSV-fil, ser en ren tabell og trykker «Kopier til Datawrapper». Teksten limes rett inn i Datawrapper («Upload data» → «Copy & paste»). Alt skjer lokalt, uten nett.

Beslutninger fra John Inge 20.10.2026:
- Analysen er regelbasert. Det brukes ingen språkmodell.
- Verktøyet tar imot `.xlsx`, `.xls` og `.csv`.
- Brukeren får en forhåndsvisning, kopierer til utklippstavlen og kan lagre som `.csv`.
- Tall skrives med punktum som desimaltegn og uten tusenskille.
- `xlrd` er godkjent som ny avhengighet. Den brukes bare til å lese `.xls`.

## Plass i appen

| id | Navn i menyen | Gruppe | Systemprogrammer |
|---|---|---|---|
| `datawrapper` | Klargjør for Datawrapper | Dokumenter | – |

Verktøyet er en verktøypakke som de ni andre: Python i `sidecar/jv/verktoy/datawrapper/`, pakket med PyInstaller, signert og lastet ned inne i appen. Det trengs ingen systemprogrammer, så pakken lages for **Mac og Windows fra start**.

## Inndata

- `.xlsx`/`.xlsm` med `openpyxl`, som allerede er med. Verktøyet leser verdier, ikke formler, og bruker den siste lagrede verdien.
- `.xls` med `xlrd`.
- `.csv` og `.txt`:
  - Skilletegnet `;`, `,` eller tab finnes automatisk.
  - Tegnkodingen er UTF-8, med eller uten BOM, eller Windows-1252.
- Største fil er 50 MB. Er fila større, eller passordbeskyttet, får brukeren en norsk feilmelding.
- Grenser mot fiendtlige filer (beslutning fra John Inge 20.10.2026, etter kontrollen av PR #19). Fila avvises med en norsk feilmelding hvis den bryter en av dem:
  - Et ark kan ha høyst 5 millioner celler, regnet fra cellene med innhold, før rutenettet lages. Én celle i `XFD1048576` er nok til å avvise arket.
  - En `.xlsx` sjekkes ut fra zip-katalogen før noe pakkes ut. Utpakket kan den være høyst 500 MB til sammen, og ingen del over 1 MB kan ha komprimeringsgrad over 100:1.
  - Ingen XML-del i en `.xlsx` kan ha DTD eller entiteter (`<!DOCTYPE`, `<!ENTITY`). openpyxl leser arkene med defusedxml.
- Feilmeldingene nevner ikke filnavn, arknavn eller mappenavn (regel 2).

## Analyse (regler, i denne rekkefølgen)

1. **Ark:** Alle synlige ark listes, og skjulte ark hoppes over. Det arket med mest tall velges først.
2. **Tabellområde:**
   - Det største sammenhengende området med data er tabellen.
   - Tomme rader og kolonner rundt tabellen fjernes.
   - Har arket flere tabeller med tomme rader eller kolonner mellom, blir hver av dem et valg.
3. **Tittel, kilde og fotnoter:**
   - Over tabellen: linjer med tekst i bare én celle blir *tittel*.
   - Under tabellen: linjer som begynner med «Kilde», «Note», «Merknad», «*», «¹» eller tall og «)» blir *kilde* og *fotnoter*.
   - Tittel, kilde og fotnoter vises for seg og er ikke med i tabellen. Datawrapper har egne felt for dem.
4. **Overskrifter:**
   - Rader over første rad med tall er overskrifter.
   - Sammenslåtte celler fylles ut.
   - Overskrifter over flere rader slås sammen med « – », for eksempel «2023 – Menn».
5. **Skjulte rader og kolonner** fjernes, og det står i rapporten.
6. **Sumrader og sumkolonner:** Rader og kolonner med etikett som «I alt», «Sum», «Totalt», «Hele landet» eller «Total» merkes. De fjernes som standard, og brukeren kan ta dem med igjen.
7. **Tall:**
   - Norske formater tolkes med parseren fra `pdf-tables`. Den flyttes til `jv_common`, slik at begge verktøyene bruker samme kode.
   - Mellomrom, U+00A0 og U+202F som tusenskille, komma som desimaltegn, «−» og parentes som minus, og «%» fjernes og tallet beholdes.
   - SSB-symbolene «.», «..», «:», «-» og «x» blir tomme celler. Hvilke symboler som ble funnet, står i rapporten.
   - Tall lagret som tekst gjøres om til tall.
   - Celler som er formatert som prosent i Excel, ganges med 100 (0,125 blir 12.5). Overskriften får « (%)» hvis den ikke sier prosent fra før. Det gis ingen advarsel (beslutning fra John Inge 20.10.2026).
   - Kan et tall leses på to måter, som «1.234», brukes samme regel som i `pdf-tables`, og det står en advarsel i rapporten.
8. **Datoer og år:**
   - Excel-datoer skrives som `ÅÅÅÅ-MM-DD`.
   - Årstall i overskrifter blir værende som tekst («2023»), ikke tall.
9. **Første kolonne** er etiketten for hver rad, med kommune, år eller kategori. Er det første kolonnene som er tall, og første rad er tekst, foreslår verktøyet å bytte rader og kolonner.
10. **Gjentatte etiketter:** I hierarkiske tabeller er tomme celler under en etikett fylt ut med etiketten over. Dette står i rapporten.

## Utdata

- **Til utklippstavlen:** Tabseparert tekst med én overskriftsrad og ingen sammenslåtte celler. Tall har `.` som desimaltegn og ingen tusenskille, og tomme celler er tomme.
- **Lagre som `.csv`:** UTF-8 med `,` som skilletegn, i samme mappe som originalen. Originalen endres aldri.
- **Rapport:** Den samme JSON-rapporten som de andre verktøyene. Den har `summary`, `warnings`, det som ble fjernet (sumrader, skjulte rader og kolonner, fotnoter), symbolene som ble tomme og tittel og kilde. Det står ingen celleinnhold i logger (regel 2).

## Kommandolinje (sidecar)

- `jv datawrapper analyser <fil> --json`: lister ark og tabeller, med forslag for hver tabell.
- `jv datawrapper lag <fil> --ark <navn> --tabell <n> [--med-sum] [--bytt] [--fjern-kolonne <i>…] [--csv <ut>] --json`
  - Skriver den rensede tabellen som TSV i rapporten og eventuelt `.csv`.
  - Argumentene legges inn i hvitelisten i `args.rs`.

## Grensesnitt

Felles verktøyskjerm som de andre. Valgene:
- **Ark og tabell:** nedtrekkslister, bare synlige når det er mer enn ett ark eller én tabell.
- **Avkrysning:** «Ta med sumrader» og «Bytt rader og kolonner».
- **Kolonner:** klikk på overskriften for å fjerne en kolonne.

Resultatet vises slik:
- **Forhåndsvisning:** de første 50 radene, med tall høyrejustert.
- **Tittel og kilde:** egne felt med kopiknapp, siden de skal inn i Datawrapper for seg.
- **Knapper:** den store knappen er **«Kopier til Datawrapper»**, og «Lagre som CSV» står ved siden av.
- **Advarsler:** som i de andre verktøyene.

**Utklippstavlen:** Bruk `navigator.clipboard.writeText` fra knappetrykket. Hvis det ikke virker i webvisningen på begge plattformer, trengs `tauri-plugin-clipboard-manager`, og den krever godkjenning fra John Inge først.

## Testdata og tester

- Syntetiske filer i `sidecar/jv/testdata/datawrapper/`, laget av et skript i `scripts/`:
  - SSB-lignende tabell med tittel, kilde, fotnoter og symboler
  - overskrifter over to rader med sammenslåtte celler
  - sumrader og sumkolonne
  - to tabeller i ett ark
  - skjult rad
  - tall lagret som tekst
  - semikolon-CSV i Windows-1252
  - `.xls`
  - tom og ødelagt fil
- Fasit for hver fil er den forventede TSV-en, byte for byte.
- Python-testene kjøres mot den pakkede binærfila på Mac og Windows, uten nett, som for de andre.
- Det som ikke kan testes automatisk, som innliming i Datawrapper og utklippstavlen på begge plattformer, leveres som sjekkliste merket «ikke kjørt på enhet».

## Lisenser

- `openpyxl`: MIT, allerede med.
- `xlrd`: BSD-3-Clause, ny og godkjent.
- Ingen andre nye avhengigheter.

## Ikke med i første versjon

- `.ods`
- Formler som må regnes ut på nytt
- Pivotering og omforming fra bred til lang tabell, utover å bytte rader og kolonner
- Diagramforslag
- Opplasting til Datawrapper via API, siden det er et nettkall (regel 1)

## Rekkefølge

1. **Sidecar-byggeren:** Python-verktøyet, testdata og pakker for Mac og Windows, på grenen `jv-datawrapper`.
2. **Grensesnittbyggeren:** skjema og visning, inkludert kopiering til utklippstavlen.
3. **Kontraktvokter**, deretter fletting.
4. **Pakkene lastes opp** til `jv-datawrapper-v0.1.0` i `sd-verktoy-releases`. Katalogen lages på nytt og signeres av John Inge.
