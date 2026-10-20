# datawrapper – klargjør for Datawrapper

Gjør en tabell fra Excel eller CSV klar til å limes inn i Datawrapper («Upload data» → «Copy & paste»).
Analysen er regelbasert og skjer lokalt, uten nett. Fasit: `docs/spesifikasjon-datawrapper.md`.

```
uv run jv datawrapper analyser tabell.xlsx --json
uv run jv datawrapper lag tabell.xlsx --ark Tabell --tabell 1 [--med-sum] [--bytt] \
    [--fjern-kolonne 3 --fjern-kolonne 5] [--csv ut.csv] --json
```

- **Inn:** `.xlsx`/`.xlsm` (openpyxl, siste lagrede verdi, ikke formler), `.xls` (xlrd) og `.csv`/`.txt`
  (`;`, `,` eller tab finnes automatisk; UTF-8 med eller uten BOM, UTF-16 med BOM eller Windows-1252).
  Største fil er 50 MB. Tom, ødelagt eller passordbeskyttet fil gir en norsk feilmelding og kode 1.
- **`analyser`:** lister de synlige arkene og tabellene i dem. Arket med flest tall og den største tabellen
  er merket `suggested`. For hver tabell: område (`A3:F20`), overskrifter, tittel, kilde, fotnoter,
  sumrader og sumkolonner, skjulte rader og kolonner, symboler og om bytte av rader og kolonner foreslås.
- **`lag`:** den rensede tabellen som TSV i rapporten (`datawrapper.tsv`): én overskriftsrad, tall med
  punktum som desimaltegn og uten tusenskille, tomme celler tomme. Uten `--ark` og `--tabell` brukes
  forslaget. `--fjern-kolonne` teller fra 1 i tabellen slik den blir med de andre valgene.
- **`--csv <ut>`:** UTF-8 uten BOM, komma og vanlig CSV-sitering. Finnes filen, eller er det originalen,
  skrives `<navn>-2.csv` (osv.). Originalen endres aldri. Stien står i `outputs`.

## Regler (i rekkefølge)

1. Skjulte ark hoppes over.
2. Arket deles ved tomme rader og kolonner. Hver del med minst to fylte celler i én rad er en tabell.
3. Linjer med tekst i bare én celle (første kolonne) over tabellen er tittel. Den første linjen er
   `title`, resten `description`. Linjer under tabellen som begynner med «Kilde», «Note», «Merknad»,
   «Tegnforklaring», «*», «¹» eller «1)» er kilde (`source`, uten «Kilde:») og fotnoter (`notes`).
   Linjer i egne blokker hører til tabellen over (kilde og fotnoter) eller under (tittel).
4. Rader over første rad med tall er overskrifter. Årstall (1900–2099) i en overskriftsrad teller som
   tekst når en rad med andre tall følger rett under. Sammenslåtte celler fylles ut, og overskrifter over
   flere rader slås sammen med « – » («2023 – Menn»).
5. Skjulte rader og kolonner fjernes og telles i rapporten.
6. Rader med etikett som begynner med «I alt», «Sum», «Totalt», «Total» eller «Hele landet» (eller slutter
   på «i alt»/«totalt»), og kolonner med slik overskrift, er sumrader og sumkolonner. De fjernes uten
   `--med-sum`.
7. Tall leses med `jv_common.numbers` (samme parser som `pdf-tables`). «%» til slutt fjernes. SSB-symbolene
   `.`, `..`, `:`, `-` og `x` blir tomme celler. Tall som kan leses på to måter («1.234», «12.5»), gir en
   advarsel med cellereferanse. Heltall med ledende null («0301») er koder og forblir tekst.
8. Datoer skrives `ÅÅÅÅ-MM-DD`. Årstall i overskrifter forblir tekst.
9. Kolonnene til venstre uten tall er etiketter. Har første kolonne tall og første rad tekst, foreslås
   bytte av rader og kolonner (`--bytt`).
10. Med to eller flere etikettkolonner fylles tomme etiketter (alle unntatt den siste) med etiketten over.

Celler med feilverdi fra Excel (#DIV/0! og lignende) blir tomme, med advarsel. Tall som er formatert som
prosent i Excel, ganges med 100 (0,125 blir 12.5), og overskriften får « (%)» hvis den ikke sier prosent fra før.

**Fiendtlige filer:** høyst 5 millioner celler per ark (regnet fra cellene med innhold, før rutenettet lages),
en `.xlsx` sjekkes mot zip-katalogen før utpakking (høyst 500 MB utpakket, høyst 100:1 for deler over 1 MB),
og ingen XML-del kan ha DTD eller entiteter. Feilmeldingene nevner ikke fil-, ark- eller mappenavn.

Ingenting fra cellene skrives til stderr eller logger. stderr har bare fremdriftslinjer og feilmeldingen.

## Testdata

`testdata/datawrapper/` lages av `scripts/lag_testdata_datawrapper.py` (oppdiktede tall og steder). Hver fil
har en fasit-TSV som testene sammenligner byte for byte. Se `testdata/FASIT.md`.
