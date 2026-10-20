# Sjekkliste: Klargjør for Datawrapper, skjermen (punkt 2 i rekkefølgen)

**Status: ikke kjørt på enhet.** Skjermen er bygget mot en falsk kjerne (`npm test`, 43 tester for
datawrapper) og sett i prøvevisningen i nettleser (`npm run dev`, skjermbilder i
`docs/skjermbilder/datawrapper/`, lys og mørk). Alt under krever ekte maskin og den installerte appen med
verktøypakken lastet ned. John Inge kjører listen, på Mac og på Windows.

## Utklippstavlen (`navigator.clipboard.writeText`)

Ingen plugin er lagt til. Knappen kaller `navigator.clipboard.writeText` rett fra knappetrykket, og
faller tilbake til `execCommand("copy")` hvis det nekter (samme kode som «Kopier alt» i Transkribering).

- [ ] **Mac (WKWebView):** «Kopier til Datawrapper» gir «Kopiert». Lim inn i TextEdit (vanlig tekst, ⌘⇧V):
      radene står på hver sin linje og kolonnene er skilt med tabulator.
- [ ] **Windows (WebView2):** det samme, limt inn i Notisblokk. Linjeskiftene er `\n`; Notisblokk i Windows 11
      viser dem riktig.
- [ ] Kopiering virker også rett etter at appen er startet og vinduet er klikket i første gang (ingen
      «tillatelse»-dialog, ingen feilmelding).
- [ ] Kopier-knappene ved tittel, beskrivelse, kilde og noter gir «Kopiert» og limer inn riktig tekst.
- [ ] Kopier en tabell med 5000 rader eller mer: det går uten merkbar ventetid, og alt kommer med.

## Innliming i Datawrapper

- [ ] `ssb_befolkning.xlsx` fra `sidecar/jv/testdata/datawrapper/`: «Kopier til Datawrapper», og lim inn
      i Datawrapper under «Upload data» → «Copy & paste». Tallkolonnene blir tall, tomme celler er tomme,
      og æøå er riktige.
- [ ] Tittel og kilde fra feltene limes inn i feltene for dem i Datawrapper.
- [ ] «Lagre som CSV», og last opp CSV-filen i Datawrapper («XLS/CSV upload»). Samme tabell.

## Filvalg og analyse

- [ ] Slipp en `.xlsx` i vinduet: analysen starter med en gang, og forhåndsvisningen kommer.
- [ ] Det samme med «Velg fil» (Mac: Finder, Windows: Utforsker), med `.xls` og med `.csv` (semikolon,
      Windows-1252).
- [ ] Slipp en `.docx`: «Filformatet støttes ikke», og forklaringen sier hva som støttes. Ingenting kjører.
- [ ] Slipp en ny fil mens en er åpen: den nye erstatter den gamle, og valgene nullstilles.
- [ ] Passordbeskyttet og ødelagt fil gir en norsk feilmelding og «Velg annen fil». Ingen filsti eller
      stakkspor.
- [ ] `to_tabeller.xlsx`: nedtrekkslistene for ark og tabell vises, og den foreslåtte er valgt.
      `ssb_befolkning.xlsx` (ett ark, én tabell): ingen nedtrekksliste.

## Valg og forhåndsvisning

- [ ] «Ta med sumrader» på `sumrader.xlsx`: sumrad og sumkolonne kommer med, og advarselen om fjernede
      sumrader forsvinner.
- [ ] «Bytt rader og kolonner» på `bytt.csv`.
- [ ] Klikk på en kolonneoverskrift: kolonnen forsvinner med en gang og kommer ikke tilbake etter
      oppdateringen. Under «Fjernede kolonner» kan den legges tilbake, én og én eller alle. Fokus havner
      på nabokolonnen, ikke på toppen av siden.
- [ ] Fjern to kolonner i rekkefølge (først kolonne 3, så kolonne 1): TSV-en har riktige kolonner. Slå på
      «Bytt rader og kolonner»: fjernede kolonner er nullstilt (tallene gjelder en annen tabell).
- [ ] Den siste kolonnen kan ikke fjernes (overskriften er ikke klikkbar).
- [ ] En tabell med mer enn 50 rader: forhåndsvisningen sier «De første 50 av N rader», og kopieringen tar
      med alle radene.
- [ ] Tall står høyrejustert, også etter bytte og fjerning.
- [ ] Endringer i rask rekkefølge (kryss av og på flere ganger): siste valg vinner, ingen feilmelding.

## Lagre som CSV

- [ ] Lagre-dialogen foreslår samme mappe og navn som originalen, med `.csv`.
- [ ] Velg et navn som ikke finnes: filen heter det du skrev, og skjermen sier «Lagret som …».
- [ ] Velg et navn som finnes fra før (og si ja til å erstatte i dialogen): ingenting overskrives. Filen
      blir `navn-2.csv`, og skjermen viser **det** navnet.
- [ ] Velg en mappe uten skrivetilgang: norsk feilmelding, forhåndsvisningen blir stående.
- [ ] «Vis i mappen» åpner Finder/Utforsker med filen valgt.
- [ ] Originalfilen er uendret (sjekk endringstidspunkt).

## Tilgjengelighet og utseende

- [ ] Alt kan nås med Tab: Velg fil, nedtrekkslister, bryterne, hver kolonneoverskrift, knappene og
      kopiknappene. Fokus er synlig i lys og mørk modus.
- [ ] VoiceOver (Mac) og NVDA (Windows) leser «Kopiert», «Oppdaterer …» og «Lagret som …», og
      kolonneknappene som «Fjern kolonnen Menn».
- [ ] Utseendet på Windows (skrift, nedtrekkslister og bryterne) er lesbart og ikke avskåret ved 125 % og
      150 % skalering.
- [ ] Lys og mørk følger systemet.
