# Måling på en vanlig Windows-PC (fart og ordfeilrate med medium)

**Ikke kjørt på enhet.** John Inge kjører dette på en vanlig redaksjons-PC (4–8 kjerner,
uten GPU). Målet er å svare på to spørsmål som Mac-målingen ikke kan svare på:

1. Holder «Anbefalt» (medium) målet i spesifikasjonen, **under 30 minutter for 30 minutter lyd**
   (`speed_x` 1,0 eller mer)?
2. Er ordfeilraten med medium den samme på Windows som på Mac (den skal være det; samme modell, samme kode)?

Det tar omtrent 2–3 timer, mest ventetid. Ingenting av dette er en del av appen, og ingenting
sendes noe sted bortsett fra nedlasting av modeller og testlyd fra Hugging Face og GitHub.

## Før du begynner

Det samme som i sjekklisten for steg 1 (`docs/sjekkliste-steg-1.md`):

- Visual Studio Build Tools 2022 («Desktop development with C++»), Rust (rustup), CMake og LLVM, alle på PATH.
- Node.js (for `npm run build`, siden Tauri bygger inn `dist/`).
- Python 3 (bare til hjelpeskriptene; ingen pakker).
- Git med tilgang til det private repoet. Sjekk ut grenen `steg-3-kvalitet`.
- PC-en bør stå i strømsparing «Høy ytelse», koblet til strøm, og ingenting annet tungt åpent
  (ingen nettleser med mange faner, ingen Teams-møte). Fartstallene er verdiløse ellers.

## 1. Bygg måleprogrammet

PowerShell, i repoet:

```powershell
npm ci
npm run build
cd src-tauri
cargo build --release --features maling --example maal
cd ..
```

`.cargo/config.toml` setter AVX2-flaggene og `/O2`-rettelsen automatisk. Den første byggingen tar
noen minutter (whisper.cpp bygges). Måleprogrammet havner i
`src-tauri\target\release\examples\maal.exe`. Det bruker nøyaktig samme kjerne som appen
(`run_job` i `engine.rs`: samme dekoding, samme biter på 10 minutter, samme tråder, beam 5).

## 2. Hent modeller og testlyd

```powershell
python -I tools\maling\hent_modeller.py --dir C:\lla-test\modeller --sizes small medium --variants verbatim semantic main
python -I tools\maling\hent_testdata.py hent --cache C:\lla-test\kilder
```

- Modellene (ca. 1,7 GB for small og medium i alle tre variantene) sjekkes mot SHA-256 fra `models.json`.
- `hent_testdata.py` laster ned ca. 0,5 GB med NPSC og FLEURS og bygger klippene i `testdata\lyd\`.
  De forringede variantene lages i ren Python og tar noen minutter. (Du kan i stedet kopiere
  `testdata\lyd\` fra Macen; kjør da `python -I tools\maling\hent_testdata.py sjekk`.
  Avvik i SHA-256 på siste bit er mulige mellom Mac og Windows og er ikke et problem.)

## 3. Mål

Alle kommandoer skriver til `C:\lla-test\resultater`. De kan avbrytes og startes på nytt (ferdige
kjøringer hoppes over).

**a) Fart: 30 minutter, medium, uten GPU.** Dette er selve ytelsesmålet. På en treg PC kan hver
kjøring ta over en time. Passerer første kjøring en time, kan du avbryte (Ctrl+C): da er svaret
allerede «nei» (se tabellen under).

```powershell
python -I tools\maling\maal.py kjor --modeller C:\lla-test\modeller --ut C:\lla-test\resultater --klipp lang-nb-30 --storrelser medium --varianter semantic verbatim --dekoding beam5 greedy
```

Det gir fire kjøringer (to modellvarianter × beam 5 og greedy), alle på bokmål. `semantic` og
`verbatim` har omtrent samme fart bortsett fra at verbatim kan prøve flere ganger. Se
`speed_x` i utskriften: 1,0 betyr 30 minutter lyd på 30 minutter.

**b) Fart og minne for small og large (valgfritt):**

```powershell
python -I tools\maling\maal.py kjor --modeller C:\lla-test\modeller --ut C:\lla-test\resultater --klipp lang-nb-30 --storrelser small --varianter semantic --dekoding beam5 greedy
```

For large må du først hente `--sizes large` i steg 2. Bare på PC-er med 16 GB eller mer.

**c) Ordfeilrate med medium (ca. 11 minutters lyd, 12 kjøringer):**

```powershell
python -I tools\maling\maal.py kjor --modeller C:\lla-test\modeller --ut C:\lla-test\resultater --klipp nb-1 nn-1 fleurs-nb --storrelser medium --varianter verbatim semantic main --dekoding beam5
```

(Hvis (a) viser at medium går under sanntid, så er denne også treg: regn med 11 minutter lyd × 3 varianter × 2 målformer
delt på `speed_x`. Kjør i så fall bare `--klipp nb-1 nn-1`.)

## 4. Regn ut og send tilbake

```powershell
python -I tools\maling\maal.py analyser --ut C:\lla-test\resultater --dato windows-PCNAVN
Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_ComputerSystem | Select TotalPhysicalMemory
```

Filen `rapporter\kvalitet-windows-PCNAVN-tall.json` er det som trengs.

Send tilbake:

- `rapporter\kvalitet-windows-PCNAVN-tall.json` (inneholder fart, minne og ordfeilrate, og er offentlig testdata, ikke noe privat)
- Utskriften fra de to `Get-CimInstance`-kommandoene (PC-modell, CPU, antall kjerner, minne).
- Om PC-en hadde strøm tilkoblet og hvilken strømplan.

## Hva du skal lese av

| Spørsmål | Hvor | Godkjent når |
|---|---|---|
| Holder medium målet? | `speed_x` for `lang-nb-30__bokmal__semantic__medium__beam5` | 1,0 eller mer (30 min lyd på 30 min) |
| Holder greedy målet hvis beam 5 ikke gjør det? | samme, `greedy` | 1,0 eller mer |
| Samme kvalitet som Mac? | `mot_lydrett.wer` / `mot_skriftlig.wer` i `-tall.json` | Innen ±0,5 prosentpoeng av Mac-tallene i `docs/kvalitet.md` |
| Minne | `peak_rss_mb` | Under halve minnet i PC-en (medium trenger ca. 1,2–1,4 GB) |
| Antall tråder | `threads` | Lik antall fysiske kjerner, høyst 8 |

Er `speed_x` under 1,0 for medium med beam 5 og greedy, er svaret at «Rask» (small) bør være standard på
Windows uten GPU (spesifikasjonen sier det allerede). Kjør da (b) for small.

## Kjent forskjell mot Mac

- Windows bruker CPU (AVX2). Mac bruker Metal. Fartstallene er derfor ikke sammenliknbare, men tekstene bør bli (nesten) like.
- Første kjøring etter oppstart leser modellfilen fra disk; legg merke til at en kald disk (nettverksstasjon, eldre SSD)
  kan gi flere sekunder ekstra på første kjøring. Kjør (a) to ganger hvis tallet ser mistenkelig ut.

## Sjekkliste (ikke kjørt på enhet)

- [ ] `maal.exe` bygger på Windows (CI bygger det ikke; det er bare med `--features maling`).
- [ ] 30 min, medium, beam 5: `speed_x` = ______ (mål: ≥ 1,0)
- [ ] 30 min, medium, greedy: `speed_x` = ______
- [ ] Toppminne medium (`peak_rss_mb`) = ______ MB
- [ ] Ordfeilrate nb-1, verbatim, medium, beam 5 = ______ % (Mac: se `docs/kvalitet.md`)
- [ ] Ordfeilrate nn-1, verbatim, medium, beam 5 = ______ %
- [ ] PC: ______ (CPU, kjerner, minne, strømplan)
