# compare – versjonssammenligning

Viser hva som er endret mellom to versjoner av et dokument, for eksempel to
utkast av et vedtak. Inn: to filer i `.txt`, `.md`, `.docx` eller `.pdf` med
tekstlag (formatene kan blandes). Ut: én selvstendig HTML-rapport med to
kolonner (all CSS inline, ingen eksterne ressurser), og en JSON-rapport på stdout.

- Slettet tekst er rød og overstreket, ny tekst er grønn.
- En setning som er flyttet til et annet avsnitt, får stiplet ramme og
  merket «flyttet til/fra avsnitt N». Flyttet tekst telles ikke som lagt til
  eller fjernet.
- Øverst: antall endrede avsnitt (endret, slettet, nye), tillagte og fjernede
  ord og flyttede setninger.
- Avsnitt sammenlignes først, deretter ord innenfor endrede avsnitt (`difflib`).
  Tall med mellomrom som tusenskille («1 200 000») regnes som ett ord.

## Eksempel

```
uv run jv compare vedtak_v1.docx vedtak_v2.pdf --out ut/
```

Gir `ut/vedtak_v1-mot-vedtak_v2.html`. Finnes filen fra før, får den nye
`-2`, `-3` osv.

Valg:
- `--ignore-whitespace` (standard på): se bort fra mellomrom og linjeskift.
  Slå av med `--no-ignore-whitespace`.
- `--ignore-case`: regn store og små bokstaver som like.

## Kjente begrensninger

- PDF uten tekstlag gir advarselen «PDF-en ser ut til å være skannet. Kjør
  `ocr` først.» Da blir sammenligningen tom eller ufullstendig.
- I PDF er et avsnitt det PyMuPDF finner som én tekstblokk. Topptekst,
  bunntekst og sidetall blir egne avsnitt. Et avsnitt som går over sideskift,
  slås sammen bare når neste side begynner med liten bokstav.
- Orddeling ved linjeskift i PDF («kultur-» + «huset») slås sammen når neste
  linje begynner med liten bokstav.
- DOCX: bare brødtekst og tabeller (én tabellrad = ett avsnitt). Topptekst,
  bunntekst, fotnoter, kommentarer og sporede endringer tas ikke med.
- Markdown sammenlignes som ren tekst; tegn som `#` og `*` står med.
- Setninger deles ved `.`, `!`, `?` fulgt av stor bokstav. Forkortelser som
  «bl.a. Kommunen» kan gi feil deling. Bare setninger på minst fire ord
  regnes som flyttet.
- Avsnittsnumrene i rapporten teller alle avsnitt, også tittelen.
