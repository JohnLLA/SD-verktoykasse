# Brief til grensesnittbygger: journalistverktøyene i skallet

Bruk: «bruk grensesnittbygger på docs/brief-jv-grensesnitt.md». Les `docs/spesifikasjon-journalistverktoy.md` først, særlig «Grensesnitt». Start ikke før steg 6.2 (Rust-modulen `jv`) er flettet.

## Mål

De ni verktøyene skal se ut og oppføre seg som Transkribering. Bruk de samme komponentene og stilene, ikke nye:
- stor tittel
- stiplet slippsone med «Velg fil» og lista over filtyper
- seksjonen «Valg» med segmentknapper
- mørke knapper
- samme venstremeny, innstillinger og Om

Skjermbildene i `docs/skjermbilder/` er fasit for utseendet.

## Oppgave

1. **Venstremenyen:** alle ti verktøyene, gruppert under «Lyd og video», «Dokumenter» og «Språk». Transkribering står først.
   - Et verktøy som ikke er lastet ned, har grå tekst og et lite nedlastingsikon, men kan klikkes.
   - Et verktøy som ikke finnes for plattformen, viser «Kommer» og kan ikke lastes ned.
2. **Verktøy som ikke er lastet ned:**
   - tittel og to–tre linjer om hva verktøyet gjør
   - hvilke filer det tar imot
   - størrelse og versjon fra katalogen
   - knappen «Last ned verktøyet»
   - linjen «Filene dine behandles bare på denne maskinen.»

   Nedlastingen viser fremdrift og har en Avbryt-knapp. Feil (ikke nett, feil sjekksum, ikke plass) får en forståelig norsk melding og knappen «Prøv igjen». Bygg skjermen som modellnedlastingen (`04-nedlasting-*` og `18-nedlasting-feil-*`).
3. **Verktøy som er lastet ned:** et felles skjermbilde i `src/tools/jv/`, styrt av et skjema per verktøy i `src/tools/<id>/`.
   - **Øverst:** tittel og slippsone med filtypene til verktøyet.
   - **Valg:** segmentknapper eller andre felt fra skjemaet, med samme forklarende tekst under som Stil i Transkribering.
   - **Utmappe:** standard er samme mappe som første fil, og den kan endres. En linje sier at originalen ikke endres.
   - **Kjør:** fremdriftslinje og Avbryt.
   - **Resultat:** `summary` som overskrift og `warnings` som tydelige meldinger. Utfilene vises med «Vis i Finder/Utforsker».
4. **`redact` har to steg:**
   - «Finn» viser treffene i en tabell med type, side, utdrag og avkrysning for sladding.
   - Forkastede kandidater står i en egen gruppe, merket og avkrysset av. Teksten forklarer at de kan være ekte numre.
   - «Sladd» bruker den redigerte planen. Brukeren kan bare krysse av og på.
5. **`nynorsk`:** «Utkast – må leses over» står alltid i resultatet.
6. **Innstillinger → Verktøy:**
   - lista over verktøy med versjon og plass de tar
   - knappene «Se etter oppdateringer», «Oppdater» og «Fjern»
   - samme oppsett som lista over nedlastede modeller
7. **Om:** installerte verktøy med versjon og lisens.

All tekst skal ligge i språkfila. Lys og mørk modus skal fungere som resten av appen.

## Skjermbilder

Lagre skjermbilder i lys og mørk modus i `docs/skjermbilder/jv/` for:
- menyen med verktøy som er og ikke er lastet ned
- et verktøy som ikke er lastet ned
- nedlasting og nedlastingsfeil
- hvert av de ni verktøyene klart til bruk, med resultat
- de to stegene i `redact`
- Innstillinger → Verktøy

## Tester

Kjør `npm test` med en falsk backend, slik transkriberingsmodulen gjør. Testene skal dekke:
- menytilstandene
- at skjemaene gir riktige argumenter til `jv_run`
- at bare `sladd` endres i redact-planen
- visning av rapport og advarsler
- feil ved nedlasting

## Grenser

Ikke rør transkriberingsmodulen, Rust-koden eller `sidecar/`. Ingen nye npm-pakker.
