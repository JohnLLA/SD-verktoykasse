# Sjekkliste: Klargjør for Datawrapper, verktøypakken (punkt 1 i rekkefølgen)

**Status: ikke kjørt på enhet.** Pakken er bygget, signert og notarisert på John Inges Mac og testet
der med Python-testene mot den pakkede binærfila (sandkasse uten nett) og `full_chain` i Rust. Windows-
pakken er bygget og testet i CI (`jv-windows-pakker`). Skjermen og kopieringen til utklippstavlen lages av
grensesnittbyggeren og har sin egen sjekkliste. John Inge kjører listen.

Kommandoene under kjøres i en utpakket pakke (`jv-datawrapper.app/Contents/MacOS/jv` på Mac,
`jv-datawrapper\jv.exe` på Windows).

## Innliming i Datawrapper

- [ ] `jv datawrapper lag sidecar/jv/testdata/datawrapper/ssb_befolkning.xlsx --json`: kopier verdien av
      `datawrapper.tsv` (uten anførselstegn, med ekte tabulatorer) og lim den inn i Datawrapper under
      «Upload data» → «Copy & paste». Fem kommuner og fem kolonner, kolonnene 2022–2024 og «Endring» blir
      tallkolonner (blå i «Check & describe»), og tomme celler er tomme.
- [ ] Det samme med `tall_som_tekst.xlsx`: «Dato» blir en datokolonne, «Kode» (0301 …) blir tekst.
- [ ] `--csv ~/Desktop/ssb.csv`: last opp CSV-filen i Datawrapper («Upload data» → «XLS/CSV upload»).
      Samme tabell som over, æøå og «–» er riktige.
- [ ] Tittel, beskrivelse og kilde fra rapporten (`title`, `description`, `source`) passer i Datawrapper sine
      felt under «Annotate».

## Egne filer (ikke i repoet)

- [ ] Et ekte SSB-uttrekk (Statistikkbanken, «Lagre som Excel»): riktig ark og tabell foreslås, tittel og
      kilde skilles ut, og symbolene blir tomme celler.
- [ ] En `.xls` fra et eldre system og en CSV eksportert fra norsk Excel (semikolon, Windows-1252).
- [ ] En passordbeskyttet `.xlsx` gir «Filen er passordbeskyttet».

## Windows

- [ ] Pakken fra artefakten `jv-windows-pakker` pakkes ut på en Windows-PC uten Python, og
      `jv.exe --version` og `jv.exe datawrapper analyser <fil> --json` virker. Defender sier ingenting
      (pakken er usignert til LLA har sertifikat).
