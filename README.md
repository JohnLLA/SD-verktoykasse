# Agenter for LLAs verktøykasse

Fem Claude Code-agenter som bygger en skrivebordsapp for Mac og Windows som LLA-medlemmene laster ned og installerer selv. Første verktøy: **Transkribering** med NB-Whisper, lokalt på maskinen, bokmål eller nynorsk, lydrett eller tolket. Nedlastingssiden kjører på Railway under LLA-kontoen.

## Installering

Pakk ut mappen der repoet skal ligge. `CLAUDE.md` og `docs/spesifikasjon-v1.md` i roten, agentene i `.claude/agents/`. Kall dem ved navn: «bruk transkriberingsbygger på steg 0».

## Agentene

| Agent | Jobb | Skriver kode? | Modell |
|---|---|---|---|
| `transkriberingsbygger` | Spike, Rust-kjernen: dekoding, modellnedlasting, whisper.cpp, eksport | Ja | opus |
| `grensesnittbygger` | Skallet med verktøymeny og Transkribering-skjermen | Ja (frontend) | sonnet |
| `kvalitetsmaler` | Testlyd, fasiter, ordfeilrate per målform og stil, fart | Bare måleskript | sonnet |
| `kontraktvokter` | Gjennomgår hver PR, særlig personvern og nettkall | Nei | sonnet |
| `byggmester` | CI for Mac og Windows, signering, oppdatering, nedlastingssiden på Railway | Konfig | sonnet |

## Flyt

1. `transkriberingsbygger` kjører spiken. **Du leser `docs/spike.md`** før noe annet bygges. Den avgjør modellfiler, nynorsk og fart.
2. `transkriberingsbygger` og `grensesnittbygger` bygger kjerne og skall.
3. `kontraktvokter` på hver PR. Rødt tilbake til byggeren.
4. `kvalitetsmaler` måler alle kombinasjoner. Du spiller inn testlyd og retter fasiter.
5. `byggmester` setter opp bygg, signering og nedlastingssiden.
6. Pilot med 3–5 redaksjoner.

## Lydrett og tolket

NB-Whisper har en modell for hver stil: **verbatim** (bokstavelig, retter ikke grammatikk, små bokstaver) for lydrett, og **hovedmodellen** `nb-whisper-<størrelse>` (retter til skriftlig, egnet til referat og teksting) for tolket. Valget ble tatt etter kvalitetsmålingen i steg 3. Nynorsk eller bokmål velges med språkparameteren.

## Railway-tilgang

Agentene logger aldri inn på Railway. Du lager et **prosjekttoken** i LLA-prosjektet og legger det i `site/.env`:

```
RAILWAY_TOKEN=<token fra LLA-prosjektet>
```

Da deployer `byggmester` nedlastingssiden dit, mens CLI-en din fortsatt er logget inn på den private kontoen.

## Åpne spørsmål

- **Navn:** «LLAs verktøykasse»? Domene, f.eks. `verktoy.lla.no`?
- **Repo:** under `JohnLLA` eller en LLA-organisasjon på GitHub? Koden offentlig, eller privat kode med et eget offentlig repo for releaser? Releasene må være offentlige for at medlemmene skal kunne laste ned.
- **Apple-konto:** din private, eller en LLA-konto? Appen bør signeres av LLA hvis den skal leve lenge.
- **Windows-signering:** Uten signatur stopper SmartScreen mange. Sertifikat eller skybasert signering må kjøpes av LLA.
- **Pilotredaksjoner:** hvilke 3–5, og har de Windows eller Mac?
