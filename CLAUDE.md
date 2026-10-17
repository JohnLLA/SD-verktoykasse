# LLAs verktøykasse

Skrivebordsapp (Tauri 2) for Mac og Windows som LLA-medlemmene installerer selv. Første verktøy: Transkribering med NB-Whisper, lokalt, bokmål eller nynorsk, lydrett eller tolket.

**Fasit:** `docs/spesifikasjon-v1.md`. Står noe i en agentinstruks i strid med den, gjelder spesifikasjonen. Spør John Inge før du endrer den.

## Faste regler

1. **Lyden forlater aldri maskinen.** Bare to nettkall er lov: modellnedlasting når brukeren ber om det, og versjonssjekk (kan slås av). Ingen analyse, ingen feilrapportering, ingen innlogging.
2. **Ingen transkribert tekst eller filnavn i logger.**
3. **Modellene følger ikke med installasjonen.** De lastes ned fra Nasjonalbibliotekets KI-lab på Hugging Face (`NbAiLab`, eller `NbAiLabBeta` der modellen bare finnes der, f.eks. semantic) og sjekkes mot SHA-256 i `models.json`.
4. **Lydrett = verbatim-modell, tolket = semantic-modell.** Målform via Whisper-språk `no` / `nn`. Ikke etterbehandle lydrett tekst med stor forbokstav eller tegnsetting.
5. **Én brief/ett steg = én gren = én PR.** Ikke rør andre verktøy eller moduler enn steget sier.
6. **Hvert verktøy er en egen modul** (frontend-mappe + Rust-modul + oppføring i registeret). Et nytt verktøy legges til uten å endre de andre.
7. **Ingen nye avhengigheter** (crates eller npm-pakker) uten at John Inge har sagt ja. Unntak: det som står i spesifikasjonen.
8. **Ingen ffmpeg i v1.** Dekoding med `symphonia`.
9. **Begge plattformer i hver PR.** CI bygger Mac og Windows. Bygger det ikke på begge, er det ikke ferdig.
10. **Norsk mot brukeren, engelsk i kode.** Alle brukertekster i én språkfil.
11. **Agentene lager ikke releaser.** Ingen push av versjonstagger, ingen opplasting av installasjonsfiler, ingen utsending. John Inge gjør det.
12. **Nedlastingssiden ligger på Railway under LLA-kontoen (john@lla.no), aldri den private.** Deploy bare med prosjekttokenet i `RAILWAY_TOKEN` fra `.env`, og bare når John Inge ber om det. Installasjonsfilene ligger på GitHub Releases, ikke på Railway.

## Mapper

```
src-tauri/            Rust: skall, verktøymoduler, kommandoer
  src/tools/transkribering/
src/                  Frontend (TypeScript + Vite)
  tools/transkribering/
models.json           Modell-URL-er, størrelser, SHA-256
testdata/             Testlyd og fasiter (kvalitetsmaler)
site/                 Nedlastingssiden (Railway, LLA-kontoen)
docs/                 Spesifikasjon, spike, sjekklister, senere.md
.github/workflows/    Bygg for Mac og Windows
```

## Rekkefølge

0 spike → 1 kjerne → 2 skall og grensesnitt → 3 kvalitet → 4 distribusjon → 5 pilot.

## Agenter

| Når | Agent |
|---|---|
| Rust-kjernen: dekoding, modeller, whisper, eksport | `transkriberingsbygger` |
| Skallet og skjermene | `grensesnittbygger` |
| Testlyd, ordfeilrate, fartsmåling | `kvalitetsmaler` |
| Etter hver byggerunde, før merge | `kontraktvokter` (leser bare, gir GODKJENT / MÅ FIKSES) |
| CI, signering, notarisering, oppdatering, installasjon | `byggmester` |

## Testing

- `cargo test` for Rust-logikk, `npm test` for frontend-logikk.
- Det som krever ekte maskin, leveres som sjekkliste merket «ikke kjørt på enhet». John Inge kjører den.
