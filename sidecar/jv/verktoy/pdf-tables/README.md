# pdf-tables – tabelluttrekk

Henter tabeller fra PDF-er med tekstlag (budsjetter, regnskap, postlister) til
regneark. Hver PDF gir én XLSX-fil med ett ark per tabell. Arket heter
`s<side>_t<nr>`, for eksempel `s3_t1` for første tabell på side 3.

Norske tall gjenkjennes og lagres som tall: `1 234 567,50` (mellomrom, hardt
mellomrom U+00A0 eller smalt hardt mellomrom U+202F som tusenskille), komma som
desimaltegn, `−12` (U+2212) og `-12` som minus, og `(12)` som negativt tall.
Tall i et format som kan tolkes på flere måter (`1.234.567,50`, `12.5`, `12-`)
lagres også som tall, men med originalteksten i en kommentar i cellen.
Heltall med ledende null (`0301`) beholdes som tekst, fordi de som regel er koder.

```
uv run jv pdf-tables budsjett.pdf --out ut/ --pages 3-7 --merge --csv
```

- `--pages 3-7` eller `--pages 1,4-5`: bare disse sidene.
- `--merge`: en tabell som slutter en side, slås sammen med første tabell på neste
  side når kolonnene er like (samme overskriftsrad, som da tas bort, eller samme
  antall kolonner uten overskrift). Arket får navnet til første del.
- `--csv`: også én CSV per tabell (`<navn>-s1_t1.csv`), UTF-8 med BOM, semikolon
  som skilletegn og punktum som desimaltegn i tallene.

Rapporten (JSON på stdout) lister arkene med sider, rader og kolonner.

## Advarsler

- PDF eller sider uten tekstlag: kjør `jv ocr` først. Ingen fil skrives hvis det
  ikke finnes noen tabeller.
- Tabell med ujevnt antall kolonner (sammenslåtte eller manglende celler).

## Kjente begrensninger

- Tabeller finnes med PyMuPDF `find_tables()`, som virker best med rutenett eller
  tydelige linjer. Tabeller uten linjer kan bli delt opp eller ikke funnet.
- Første rad i hver tabell regnes som overskrift og lagres som tekst.
- Sammenslåing skjer bare mellom påfølgende sider, ikke over sider som er valgt bort.
- Celler med tekst over flere linjer slås sammen til én linje.
