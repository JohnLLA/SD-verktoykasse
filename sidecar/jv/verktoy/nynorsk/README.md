# jv nynorsk – bokmål ↔ nynorsk

Lager et **førsteutkast** av en tekst på den andre målformen med [Apertium](https://apertium.org) (språkparet `apertium-nno-nob`). Alt skjer lokalt; ingen tekst sendes noe sted.

- Inn: `.txt`, `.md` eller `.docx`. Retning `--to nn` (bokmål → nynorsk) eller `--to nb` (nynorsk → bokmål).
- Ut: en ny fil `<navn>-nn.<ending>` eller `<navn>-nb.<ending>` i `--out`-mappen. Originalen røres aldri, og eksisterende filer overskrives ikke (`-2`, `-3` …).
- Ord Apertium ikke kjenner (`*`), ikke klarer å bøye (`#`) eller ikke finner i den tospråklige ordboken (`@`), merkes `[?ord]` i utfilen og listes i rapporten under `unknown_words` med type (`unknown`, `generation`, `untranslated`) og antall. Ingen rå `*`, `#` eller `@` fra Apertium blir stående i utkastet.
- Ved `#` (bøyningen mangler) er ordet i `[?…]` **grunnformen** (for eksempel «svibrent» eller «pådrage»), ikke en bøyd form. Du må selv bøye det riktig.
- Rapporten merker alltid resultatet som utkast (`"draft": true`, «UTKAST»-advarsel og oppsummering som begynner med «Utkast:»).
- DOCX oversettes avsnitt for avsnitt (også i tabeller). Rekkefølge, avsnittsstil (overskrift, punktliste, sitat …), justering, bilder og sideskift beholdes.

## Eksempel

```
uv run jv nynorsk "Sak om biblioteket.docx" --to nn --out ut/
```

## Oppsett

Krever Apertium-programmene og språkparet `apertium-nno-nob`. Se [OPPSETT.md](OPPSETT.md). Mangler de, stopper verktøyet med en norsk feilmelding og kode 1.

Verktøyet bruker ikke bash-skriptet `apertium`. Fra 0.2.0 leser det modusfila (`modes/nob-nno.mode` eller `modes/nno-nob.mode`) selv og kobler programmene sammen med `subprocess`, uten skall: `apertium-destxt | <modus> | apertium-retxt`, som `apertium -f txt` gjør. Resultatet er byte for byte det samme som før, og det virker likt på macOS og Windows. Programmene kjøres i datamappa og får bare relative stier, så æøå i stien til appdatamappa gjør ikke noe. En modusfil kan bare starte de 14 Apertium-programmene verktøyet kjenner, og bare peke på filer i datamappa.

## Slik virker det

Apertium setter selv `*`, `#` eller `@` på problemord; verktøyet gjenkjenner dem direkte (også `#` inne i et ord, som `på#drage`) og pakker ordet inn i `[?…]`. Ekte Apertium flytter og dupliserer derimot tegn som står i selve teksten (Markdown `**fet**`, `#emneknagg`, `@navn`), så slike tegn sendes aldri til Apertium: teksten deles ved hver `*`, `#` og `@`, delene oversettes, og tegnene settes tilbake på samme sted. Kommer Apertium ut av linjestrukturen, prøver verktøyet mindre biter, linje for linje. Klarer en linje seg fortsatt ikke, står den uendret i utkastet, og rapporten har en advarsel. DOCX sendes i grupper på rundt 300 ord per kall, så Apertiums grense på 500 kohorter ikke slår inn.

## Kjente begrensninger

- Apertium mister sammenhengen over `*`, `#` og `@`, fordi teksten deles der. Omtrent 15 % av ord med `**` rundt ga en annen oversettelse i en prøve, og noen fikk grammatiske feil som ikke fantes uten symbolet (for eksempel «en» → «ein» i stedet for «ei», «skal bygges» → «skal blir bygd», «Hun leser» → «lesar»). Kjønn, artikler og verbformer rett ved fet, kursiv, emneknagger og @navn blir derfor oftere feil. Les de stedene ekstra nøye.
- Fordi teksten deles ved `*`, `#` og `@` og sendes i grupper, kan siste ord i et avsnitt av og til få en annen, like gyldig form enn om avsnittet ble oversatt alene (for eksempel «også» → «òg» eller «også», «ung» → «ungt»).
- Gir du nynorsk tekst og `--to nn`, er det feil retning: Apertium kjenner ikke nynorske former som bokmål, og ordene som `Dei` kommer ut som `[?Dei]`. Bruk `--to nb` for nynorsk inndata.
- Dette er maskinoversettelse. Teksten **må** leses korrektur, særlig ordvalg, egennavn og fagord.
- Tegnformatering *inne i* et avsnitt (fet, kursiv, lenker på deler av teksten) beholdes ikke: hele avsnittet får formateringen til den første teksten i avsnittet. Rapporten sier fra hvor mange avsnitt det gjelder. Lenketekst blir vanlig tekst.
- Topptekst, bunntekst, fotnoter, kommentarer og tekstbokser i DOCX oversettes ikke.
- Markdown-syntaks sendes gjennom Apertium som vanlig tekst. Kodeblokker og lenkeadresser kan derfor bli endret.
- Egennavn Apertium ikke kjenner (for eksempel «Fiktivhavn»), merkes som ukjente selv om de er riktige.
- Bare standardmodusene `nob-nno` og `nno-nob` brukes; ingen valg for nynorsknorm (e-/a-infinitiv o.l.).
- Enhetstestene bruker falske Apertium-programmer og en falsk modusfil (`tests/fake_apertium.py`). Integrasjonstestene kjører mot ekte Apertium og sammenligner med fasiter i `testdata/nynorsk/referanse/` (laget med `apertium -f txt` på Mac). De hoppes over hvis Apertium eller språkparet mangler (se OPPSETT.md).
- Apertium deler ukjente sammensatte ord i deler (for eksempel «fjordglimring»), så slike ord oversettes uten å bli merket. Les alltid korrektur.
