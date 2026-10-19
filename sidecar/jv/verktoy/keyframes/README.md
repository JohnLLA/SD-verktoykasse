# keyframes – stillbilder fra video

Trekker ut stillbilder fra en video til verifisering eller illustrasjon, enten
med fast intervall (`--every`) eller ved hvert klipp (`--scenes`). Hvert bilde
får tidskoden i filnavnet (`000012.480.jpg` = 12,480 s), og det lages et
kontaktark (JPEG) med alle bildene og tidskoden skrevet under hvert bilde.

Rotasjonsmetadata respekteres, så stående mobilvideo gir stående bilder.
Rapporten (JSON på stdout) dokumenterer uttrekket: SHA-256 for videoen i
`inputs`, og varighet, oppløsning (slik den vises og slik den er lagret),
bildefrekvens, rotasjon og kodek i `videos`. Hvert bilde står i `outputs` med
tid i sekunder og tidskode.

## Eksempel

```
uv run jv keyframes "Opptak fra møtet.mp4" --out uttrekk --scenes 0.3
uv run jv keyframes klipp.mov --out uttrekk --every 2s
```

Gir `uttrekk/Opptak fra møtet-bilder/000000.000.jpg`, `…/000002.000.jpg` osv.
og `uttrekk/Opptak fra møtet-kontaktark.jpg`. Finnes mappen eller kontaktarket
fra før, får de nye navnene `-2`, `-3` …, så ingenting overskrives.

## Valg

- `--every 2s` – ett bilde hvert 2. sekund, fra 0 s. Desimaler går (`0.5s`).
- `--scenes 0.3` – ett bilde ved hvert klipp der ffmpegs scenepoeng er over
  terskelen (0–1). Lavere tall gir flere bilder. Første bilde (0 s) tas alltid
  med, så den første scenen også er representert.
- Flere videoer kan gis på én gang.

## Krav

`ffmpeg` og `ffprobe` (`brew install ffmpeg`). Bruker bare valg og filtre som
finnes i både ffmpeg 4.4 og nyere versjoner. Kontaktarket lages med Pillow og
dens innebygde skrift, så det trengs ingen systemskrifter.

## Kjente begrensninger

- Scenedeteksjon finner harde klipp. Overtoninger og raske kamerabevegelser
  kan gi for få eller for mange bilder; juster terskelen.
- Tidskoden er tidspunktet fra starten av filen, ikke opptakstidspunktet.
- Bildene er dekodet fra videoen og JPEG-komprimert på nytt (kvalitet 92), så
  de egner seg ikke til piksel-for-piksel-analyse av komprimeringsspor.
- Svært lange videoer med kort intervall gir mange filer og et stort
  kontaktark.
