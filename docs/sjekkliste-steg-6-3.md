# Sjekkliste steg 6.3: skjermene for journalistverktøyene

**Status: ikke kjørt på enhet.** Skjermene er laget og testet med en falsk kjerne (`npm test`) og
sett i en vanlig nettleser med prøvevisningen (`src/dev/mock-jv.ts`, alle tilstander, lys og mørk).
Skjermbildene i `docs/skjermbilder/jv/` er tatt der, ikke i `npm run tauri dev`. Ingenting her er
prøvd mot den ekte Rust-modulen, den ekte katalogen eller de ekte pakkene. John Inge kjører listen.

Prøvevisningen startes med `npm run dev` og åpnes i nettleseren, for eksempel
`http://localhost:1420/?verktoy=alle&kjoring=hurtig`. Parameterne står øverst i `src/dev/mock-jv.ts`.

## Menyen

- [ ] Ti verktøy i tre grupper (Lyd og video, Dokumenter, Språk), Transkribering øverst.
- [ ] Verktøy som ikke er lastet ned, har grå tekst og nedlastingsikon, og kan klikkes.
- [ ] Når et verktøy er lastet ned, blir teksten vanlig og ikonet borte, uten at appen startes på nytt.
- [ ] På en Mac med katalog uten Windows-linjer vises ingen «Kommer». (Windows-utseendet er
      «ikke kjørt på enhet»: sjekk at ni verktøy viser «Kommer» og «Kommer for Windows» på siden.)
- [ ] Alt kan nås med tastaturet (Tab, Enter, piltaster i segmentknappene), og fokus er synlig.
- [ ] Menyen får plass i et vindu på 1100 × 760. Innstillinger og Om står nederst.

## Nedlasting (mot den ekte katalogen)

- [ ] Å åpne et verktøy som ikke er lastet ned henter katalogen fra nett. Ingen nettkall ved oppstart.
- [ ] Størrelse og versjon på siden stemmer med katalogen.
- [ ] Fremdrift og «Avbryt nedlasting» virker. Avbryt og last ned på nytt: nedlastingen fortsetter.
- [ ] Slå av nettet midt i nedlastingen: «Ingen nettforbindelse» og «Prøv igjen».
- [ ] Nedlastingen ferdig: verktøyet er klart uten omstart, og står i Innstillinger og Om.
- [ ] På en Mac med macOS eldre enn 26.6.2: ocr viser «Verktøyet trenger macOS 26.6.2 eller nyere»
      og har ingen nedlastingsknapp. Samme for metadata (15) og de to andre som krever 26.

## Hvert verktøy (på en Mac med verktøyene installert)

- [ ] Dra en fil inn i vinduet, og bruk «Velg fil». Dra en fil mens Innstillinger vises: den går
      til verktøyet som sist var åpent, og siden bytter dit.
- [ ] Feil filtype gir «Filformatet støttes ikke» og sier hvilke formater verktøyet leser.
- [ ] Utmappen er mappen til første fil. «Velg annen mappe» endrer den. Originalen er uendret.
- [ ] Kjør: fremdrift, Avbryt, og resultatet med overskrift, advarsler og utfiler.
- [ ] «Vis i Finder» åpner Finder med filen markert.
- [ ] compare: to filer, «Bytt rekkefølge» bytter gammel og ny. Tre filer gir en melding.
- [ ] metadata: «Vis» viser feltene gruppert og følsomme felt merket, uten utmappe. «Fjern» lager kopi.
      Test også en mappe («Velg mappe»).
- [ ] keyframes: fast intervall og ved klipp gir riktige bilder.
- [ ] loudness: begge målene. subtitles: json fra Transkribering. pdf-tables: sider «3-7», sammenslåing, csv.
- [ ] ocr: PDF, bilde og mappe. nynorsk: «Utkast – må leses over» står i resultatet, begge retninger.
- [ ] Feil fra verktøyet (for eksempel en skadet PDF) vises på vanlig norsk, uten stakkspor.

## Sladding (redact), to steg

- [ ] «Finn» viser treffene i tabellen med type, side, utdrag og avkrysning.
- [ ] Forkastede kandidater står i egen gruppe, merket «Forkastet» og avkrysset. **Beslutning:** de er
      avkrysset som standard (tryggest, slik briefen sier), selv om planfilen fra verktøyet har
      `sladd: false`. John Inge bekrefter at det er riktig valg.
- [ ] Fjern avkrysninger og trykk «Sladd». Åpne planfilen (`…-treff.json`) og sjekk at bare `sladd`
      er endret. Sladdet PDF mangler de sladdede verdiene (søk i Forhåndsvisning).
- [ ] Planfilen vises ikke som utfil i resultatet. «Tilbake til treffene» gir de samme avkrysningene.
- [ ] Tom tekstfil og en egen ordliste fra «Velg fil …» gir treff for ordene.
- [ ] Verktøyets advarsel om at forkastede treff «IKKE er merket» skjules i gjennomgangen, siden den
      sier det motsatte av avkrysningen. Sjekk at det er rimelig.

## Innstillinger og Om

- [ ] Innstillinger → Verktøy viser versjon og plass per verktøy, og samlet plass.
- [ ] «Se etter oppdateringer» henter katalogen og sier om noe er nytt. Ingenting lastes ned av seg selv.
- [ ] «Oppdater» laster ned og installerer ny versjon. «Fjern» spør først, og nekter mens verktøyet brukes.
- [ ] Om viser installerte verktøy med versjon og lisens.

## Utseende

- [ ] Lys og mørk følger systemet. Kontrast og fokusring er lesbare.
- [ ] Windows-utseendet (menyen med «Kommer», skriftene, vindusrammen) er «ikke kjørt på enhet».
- [ ] Smalt vindu (under 860 px): menyen blir ikoner. Sjekk at nedlastingsikonet fortsatt er til å se.
