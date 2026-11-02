# Brief til sidecar-bygger: Tesseract 5.5.4 i ocr-pakken

Bruk: «bruk sidecar-bygger på docs/brief-tesseract-5-5-4.md».

Gren og PR: `tesseract-5-5-4`.

## Bakgrunn

Den ukentlige sårbarhetssjekken 2.11.2026 stoppet på tre nye avvik i Tesseract 5.5.3:
- CVE-2026-119338
- CVE-2026-119339
- CVE-2026-119340

Tesseract 5.5.4 kom 28.10.2026 og retter alle tre. Den retter også:
- de åtte avvikene som i dag står som unntak (CVE-2026-88047 til -88054)
- en heap use-after-free i `PAGE_RES_IT::ReplaceCurrentWord` «with several languages». Den har ennå ingen CVE.

Den siste treffer vanlig gjenkjenning med flere språk, og ocr-verktøyet bruker `nor+eng`. Den gjelder altså bilder og PDF-er fra brukeren, ikke bare språkfilene. Derfor oppgraderes Tesseract nå, i stedet for at avvikene føres som unntak.

## Oppgave

1. **Mac:**
   - `brew upgrade tesseract` (Homebrew har 5.5.4).
   - Bygg ocr-pakken på nytt med `sidecar/build/`, slik at `binaries.json` genereres på nytt.
   - Ny pakkeversjon: patch, `jv-ocr` 0.1.2.
2. **Windows:**
   - Sjekk om det finnes et Windows-installasjonsprogram for 5.5.4 under https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.4 eller hos UB Mannheim.
     - **Hvis ja:** oppdater `jvpack/windows/sources.py` med ny adresse og SHA-256, og kjør `jv-windows-pakker.yml`.
     - **Hvis nei:** la Windows stå på 5.5.3. Legg CVE-2026-119338, -119339 og -119340 i `sidecar/build/sarbarhet-unntak.json` med utløpsdato 2026-11-30.
   - Begrunnelsen for unntakene skal si:
     - de gjelder bare Windows-pakken til 5.5.4-bygget finnes
     - 119339 og 119340 krever en ondsinnet `.traineddata`, og verktøyet bruker bare de medfølgende språkfilene
     - 119338 gjelder PAGE XML-utdata, som verktøyet ikke bruker (bare TSV og ocrmypdfs PDF)
3. **Unntakslista:** fjern unntakene for CVE-2026-88047 til -88054 når begge plattformer er på 5.5.4. Mens Windows står på 5.5.3, beholdes de, men begrunnelsen skal si at de bare gjelder Windows.
4. **Tester:**
   - ocr-testene mot den pakkede binærfila på Mac
   - `python3 sidecar/build/sjekk-sarbarheter.py` skal vise 0 funn uten unntak
5. **Katalogen:** ny `tools.json` som utkast. John Inge publiserer (regel 11).

## Grenser

- Ikke rør andre verktøypakker eller appen.
- Ingen release og ingen tagger.

## Rapport

Kort på norsk:
- Tesseract-versjon per plattform
- hvilke unntak som er lagt til og fjernet
- testresultat
- om Windows venter på 5.5.4
