# subtitles – teksting

Gjør en Whisper-transkripsjon med tidskoder om til undertekster i **SRT** og **VTT**.

- Høyst 42 tegn per linje og 2 linjer per tekst, 1–7 s visning og minst 80 ms
  (2 bilder) mellom tekstene. Alt kan justeres med `--max-chars`, `--max-lines`,
  `--min-duration`, `--max-duration` og `--gap`.
- Lange segmenter deles helst ved setningsslutt, så ved komma og foran ord som
  «og», «men», «fordi» – aldri midt i et ord. Linjene brytes på samme måte.
- Ordtidskoder (`words`) brukes til delingen når de finnes. Ellers fordeles tiden
  i segmentet etter antall tegn, og rapporten advarer om det.
- For korte tekster forlenges (eller starter litt tidligere) uten å komme nærmere
  enn 80 ms neste tekst.
- Hver tekst kontrolleres mot reglene etter at filene er laget. Eventuelle brudd
  står i `warnings` i rapporten.

Filene skrives som UTF-8 uten BOM: SRT med CRLF-linjeskift, VTT med
`WEBVTT`-overskrift og LF. Originalen røres aldri.

## Eksempel

```
uv run jv subtitles intervju.json --out undertekster/
```

gir `undertekster/intervju.srt` og `undertekster/intervju.vtt`, og en JSON-rapport
på stdout.

## Kjente begrensninger

- Leser bare Whisper-JSON (et objekt med `segments`, eller en liste med segmenter).
  Verktøykassens eksportformat er ikke definert ennå og støttes ikke.
- Hvert Whisper-segment blir minst én tekst; korte segmenter slås ikke sammen.
- Et enkelt ord som er lengre enn linjegrensen får en egen tekst og gir en advarsel.
- Når en tekst må forlenges til 1 s og det er for lite plass, skyves neste tekst
  litt senere enn talen.
- Ingen tegnsetting eller stavekontroll – teksten brukes slik Whisper skrev den.

## Tette korte tekster

En kort tekst forlenges til minstevarighet, men aldri forbi neste tekst (unntatt høyst 150 ms). Kan den ikke forlenges, slås den sammen med neste tekst hvis reglene holder. Ellers blir den stående som kortere enn minstevarighet. Begge deler gir advarsel i rapporten, og ingen tekst starter mer enn 150 ms etter sin opprinnelige tidskode.
