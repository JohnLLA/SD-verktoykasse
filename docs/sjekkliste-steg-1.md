# Steg 1 – kjerne: sjekkliste «ikke kjørt på enhet»

Det som er testet automatisk (`cargo test` lokalt og i CI på macOS arm64 og Windows x64), står i PR-beskrivelsen. Her står det som krever ekte maskin. John Inge kjører den, Windows-delen på en vanlig redaksjons-PC.

Steg 1 har ikke grensesnitt ennå. Punktene under kan kjøres med testene i `src-tauri` (se «Slik kjører du»), eller vente til steg 2, der de samme punktene kan prøves fra skjermen.

## Slik kjører du testene med ekte modell

```sh
cd src-tauri
export LLA_TEST_MODEL_DIR="$HOME/lla-test/modeller"   # modellene havner her som <id>.bin
export LLA_TEST_AUDIO_DIR="$HOME/lla-test/lyd"        # king.mp3 og knuthamsun.mp3 fra NbAiLab
cargo test real_download_from_hugging_face -- --ignored --nocapture
cargo test real_ -- --ignored --nocapture --test-threads=1
```

På Windows (PowerShell): `$env:LLA_TEST_MODEL_DIR="C:\lla-test\modeller"` osv. Byggeverktøy som i oppskriften i `docs/spike.md` (Visual Studio Build Tools, Rust, CMake, LLVM). `.cargo/config.toml` setter nå `GGML_NATIVE=OFF`, AVX2-flaggene og `/O2`-rettelsen automatisk, så de trenger ikke settes for hånd.

Testene skriver bare tall (tider, antall segmenter), aldri transkribert tekst.

## Windows, ekte redaksjons-PC

- [ ] `cargo test` er grønn.
- [ ] `real_`-testene er grønne. Noter tiden for `lydrett no` og `tolket nn` og hva `avbryt` skriver (sekunder fra flagg til retur). Det er tiden maskinen fortsatt regner etter avbryt (whisper.cpp sjekker mellom 30-sekundersvinduene). Grensesnittet får beskjed med en gang uansett. Windows-CI med 2 vCPU: 14–25 s med small; på en vanlig PC bør det være noen få sekunder, men det kan bli mer med large.
- [ ] Avbryt mens en lang fil (minst 1 time) dekodes og transkriberes: stopper innen få sekunder (først mulig å prøve fra skjermen i steg 2).
- [ ] Fart med «Anbefalt» (medium q5) og beam 5 på et intervju på 30 minutter. Mål: under 30 minutter (spesifikasjonen). Prøv også greedy (innstillingen `decoding: "greedy"`).
- [ ] Antall tråder: `check_system` viser `physical_cores` og `whisper_threads`. Stemmer `physical_cores` med Oppgavebehandling → Ytelse → CPU → «Kjerner»?
- [ ] PC **uten AVX2** (eldre Celeron/Pentium Silver): `check_system` gir `cpu_supported: false` med `missing_cpu_features`, og `transcribe` gir feilen `cpu_unsupported` i stedet for å krasje.
- [ ] Brukernavn eller mapper med æøå (også OneDrive-omdirigerte mapper): modellnedlasting, egen modellmappe og lydfil i slik mappe.
- [ ] Dvale: start en lang jobb, la PC-en stå urørt lenger enn dvaletiden i strøminnstillingene. Den skal ikke gå i dvale mens jobben kjører, og skal kunne gå i dvale etter at jobben er ferdig eller avbrutt. `powercfg /requests` (som administrator) viser appen under `SYSTEM` mens jobben kjører.
- [ ] Modellnedlasting bak bedriftens brannmur/proxy (hvis redaksjonen har det). Appen bruker systemets sertifikatlager. Proxy leses fra miljøvariablene `HTTPS_PROXY`/`HTTP_PROXY`, ellers fra den faste proxyen i Windows' innstillinger (Innstillinger → Nettverk → Proxy, «Bruk en proxyserver»). Automatisk oppsett med skript (PAC/WPAD) leses ikke; noter om redaksjonen bruker det.
- [ ] Nedlasting brytes (slå av nettet midt i), slå på igjen, last ned på nytt: fortsetter fra der den slapp. Avslutt appen midt i og start igjen: fortsetter også.
- [ ] Lagre eksport til en nettverksdisk og en minnepinne (FAT/exFAT): txt, srt, vtt og docx. Lagre på nytt uten bekreftelse skal gi `file_exists`; med bekreftelse skrives filen over.
- [ ] docx åpnes i Word uten feilmelding; topptekst og tidskoder ser riktige ut.
- [ ] srt og vtt fungerer i en spiller eller et redigeringsprogram redaksjonen bruker.

## Mac, ekte maskin

- [ ] Mac M1 (eldste støttede) med Metal: `real_`-testene, og fart med medium q5 og beam 5 på 30 min intervju, både tolket (mål: under 10 min) og lydrett (mål: under 30 min). De endelige målene i spesifikasjonen settes etter denne målingen.
- [ ] macOS 13 på ekte maskin: appen starter og transkriberer.
- [ ] Dvale: under en lang jobb viser `pmset -g assertions` linjen `PreventUserIdleSystemSleep named: "SD-Verktoy: transkribering"`, og den forsvinner når jobben er ferdig eller avbrutt. Maskinen går ikke i dvale av seg selv under jobben (skjermen kan slukke).
- [ ] «Best» (large q5, 1,1 GB) på en Mac med 16 GB: fart og minne.
- [ ] Modellmappe på delt disk (SMB) og ekstern disk: modellen finnes, sjekkes mot SHA-256 første gang (tar litt tid), og neste gang uten ny sjekk.

## Begge plattformer

- [ ] Fil på minst 3 timer (wav og m4a): fullfører uten å gå tom for minne. Målt på Mac (M5 Max, small, greedy): 3 timer m4a, 19 biter, toppminne 531 MB (mot 2 GB uten biter i spiken), 100 s. Bør måles på Windows og med medium/large.
- [ ] Lydfiler fra telefon (iPhone Taleopptak .m4a, Android-opptak) og fra vanlige opptakere: dekodes, og klikk på segmenter (steg 2) treffer riktig sted i lyden. AAC-forsinkelsen (2112 rammer) trekkes fra; andre kodere kan ha en annen verdi.
- [ ] Ikke støttede filer (webm, Opus, caf, aiff, ALAC m.fl.) gir `unsupported_format` med riktig format.
- [ ] Ingen filnavn eller tekst i noen logg: kjør en jobb og se gjennom terminalutskriften (Mac: start appen fra Terminal; Windows: debug-bygg).
