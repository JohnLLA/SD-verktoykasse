# loudness – normalisering

Setter lydnivået i en lyd- eller videofil til en standard, med ffmpeg `loudnorm`
i to pass: første pass måler, andre pass justerer ut fra målingene (lineært når
det er mulig). Lydnivået før og etter måles med `ebur128` og står i rapporten.

- **Inn:** WAV, MP3, M4A, FLAC og lydsporet i video (MP4, MOV, M4V, MKV).
- **Mål:** `--target podcast` (−16 LUFS, −1 dBTP, standard), `--target broadcast`
  (−23 LUFS, −1 dBTP, EBU R128) eller egendefinert med `--lufs` (−70 til −5).
- **Ut:** ny fil `<navn>-normalisert.<samme endelse>` i `--out`. Originalen røres aldri.
  - WAV beholder PCM-formatet (f.eks. 16 eller 24 bit), FLAC er tapsfri.
  - MP3 (libmp3lame) og AAC (M4A og video) kodes med kildens bitrate rundet opp
    til nærmeste standardtrinn, minst 128 og høyst 320 kb/s (192 kb/s hvis
    kilden ikke oppgir bitrate). Bitraten står i rapporten (`bitrate_kbps`).
  - Samplerate og antall kanaler beholdes (loudnorm jobber internt i 192 kHz).
  - I video kopieres bildesporet uten omkoding.

```
uv run jv loudness "Intervju råopptak.wav" --out normalisert --target podcast
```

Rapporten (JSON på stdout) har for hver fil `before` og `after` med
`integrated_lufs` og `true_peak_dbtp`, `normalization` (lineær/dynamisk) og
`within_target` (±0,5 LU og under −1 dBTP).

## Kjente begrensninger

- Bare det første lydsporet behandles. Andre lydspor, undertekster og omslagsbilde
  (i MP3/M4A) blir ikke med i utfilen.
- Er lineær justering umulig (f.eks. stille opptak som skal mye opp, eller stor
  dynamikk), bruker loudnorm dynamisk modus. Da kommer en advarsel, og resultatet
  kan bomme på målet.
- Etter tapsbasert koding (MP3/AAC) kan true peak havne litt over −1 dBTP. Det gis
  advarsel, ikke feil.
- Stille filer eller filer kortere enn ca. 0,4 s kan ikke måles og gir feil.
- Krever `ffmpeg` og `ffprobe` (`brew install ffmpeg`).
