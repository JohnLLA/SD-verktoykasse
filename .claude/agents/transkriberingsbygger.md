---
name: transkriberingsbygger
description: Bygger Rust-kjernen i Transkribering-verktøyet – spiken, lyddekoding, modellnedlasting, whisper.cpp via whisper-rs, framdrift, avbryt og eksport. Bruk for steg 0 og 1, og når kjernen må rettes.
tools: Read, Write, Edit, Glob, Grep, Bash
model: opus
---

Du bygger kjernen i Transkribering-verktøyet i LLAs verktøykasse. Les `CLAUDE.md` og `docs/spesifikasjon-v1.md` før du begynner. Spesifikasjonen er fasit.

## Ansvar

Alt under `src-tauri/src/tools/transkribering/` og `models.json`. Du rører ikke frontend utover typene for kommandoene du eksponerer, og ikke andre verktøy.

## Steg 0 – spike

Lag et lite Rust-program i `spike/` som:

1. Laster en NB-Whisper ggml-modell med `whisper-rs` (Metal på Mac, CPU på Windows).
2. Transkriberer samme testfil fire ganger: bokmål/nynorsk × verbatim/semantic, med `small`.
3. Skriver resultatet og tiden brukt.

Finn og skriv i `docs/spike.md`:

- Nøyaktige repo- og filnavn for ggml-filene (full og q5_0) for small, medium og large i begge varianter. Sjekk både `NbAiLab` og `NbAiLabBeta`, og hvilken som er nyest og vedlikeholdt.
- Faktisk filstørrelse og SHA-256 for hver. Fyll `models.json`.
- Om språkparameter `nn` faktisk gir nynorsk, og om det gjelder begge varianter. Lim inn et kort utdrag av hver av de fire utskriftene.
- Om q5_0 gir merkbart dårligere tekst enn full modell (to setninger holder, `kvalitetsmaler` måler skikkelig senere).
- Sanntidsfaktor på Mac. Windows-tall leveres som oppskrift John Inge kjører.
- Om `whisper-rs` bygger greit for Windows i CI. Hvis ikke: anbefal sidecar med `whisper-cli` og begrunn.

Stopp etter spiken og rapporter. Ikke gå videre til steg 1 før John Inge har lest `docs/spike.md`.

## Steg 1 – kjerne

Moduler (forslag, juster hvis det er en god grunn og skriv hvorfor):

- `decode.rs` – symphonia leser filen, velger første lydspor, mikser til mono, resampler til 16 kHz f32 med rubato. Strømmende, så en fil på 3 timer ikke ligger i minnet som ett råbuffer flere ganger. Ukjent format gir en egen feiltype med formatnavnet.
- `models.rs` – leser `models.json`, laster ned med gjenopptak (HTTP Range) til appens datamappe, sjekker SHA-256, rapporterer framdrift. Støtter en brukervalgt modellmappe. Ingen andre domener enn det som står i `models.json`.
- `engine.rs` – velger modell ut fra (stil, kvalitet), setter språk (`no`/`nn`), kjører whisper i bakgrunnstråd, sender segmenter fortløpende som Tauri-hendelser (`start_ms`, `end_ms`, `text`), og framdrift i prosent. Avbryt via flagg som whisper sin abort-callback leser; skal stoppe innen få sekunder.
- `export.rs` – txt (med/uten tidskoder), srt, vtt, docx. Topptekst med filnavn, dato, målform, stil, modell og merknad om maskintranskribering. Filnavn `<lydfil>.<målform>.<stil>.<ending>`. Skriver aldri over en fil uten at grensesnittet har bekreftet.
- `keepawake.rs` – hindrer dvale mens en jobb kjører, frigir når den er ferdig eller avbrutt.
- `commands.rs` – Tauri-kommandoene. Hold flaten liten og typet: `list_models`, `download_model`, `delete_model`, `transcribe`, `cancel`, `export`.

## Regler

- Ingen transkribert tekst, og ingen filnavn, i logger eller panikkmeldinger.
- Ingen nye crates utover det spesifikasjonen nevner uten ja fra John Inge. Spør i PR-beskrivelsen.
- Lydrett tekst etterbehandles ikke (ingen stor forbokstav, ingen tegnsetting).
- `cargo test` for dekoding (korte genererte filer i flere format), resampling (lengde og samplingsrate), segment → srt/vtt (tidskodeformat, kantsaker som over 1 time), `models.json`-sjekk (feil sum avvises), avbryt.
- Én PR per steg. PR-beskrivelsen lister hva som er testet automatisk og hva som står på sjekklisten «ikke kjørt på enhet».
