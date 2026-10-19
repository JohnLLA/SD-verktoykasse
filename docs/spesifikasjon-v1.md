# LLAs verktøykasse – spesifikasjon v1

Skrivebordsapp for Mac og Windows som LLA-medlemmene installerer selv. Appen er et skall med verktøy. Det første verktøyet er **Transkribering** med NB-Whisper. Alt kjører lokalt, og lyden forlater aldri maskinen.

Dette dokumentet er fasit. Står noe i en agentinstruks i strid med det, gjelder spesifikasjonen. Spør John Inge før du endrer den.

## Hvorfor lokalt

Lokalaviser transkriberer intervjuer med kilder. Lyd som sendes til en skytjeneste, er ute av redaksjonens kontroll. Verktøyet skal kunne brukes på kildebeskyttet materiale uten å spørre noen om lov. Det er hovedpoenget med appen og må aldri svekkes for å vinne fart eller funksjoner.

## Brukeren

En journalist i en liten lokalavis, ofte på en vanlig jobb-PC med Windows, eller en Mac. Ikke teknisk. Skal klare dette uten hjelp:

1. Laste ned og installere appen.
2. Dra inn en lydfil.
3. Velge bokmål eller nynorsk, og lydrett eller tolket.
4. Få tekst med tidskoder, rette den og lagre den.

## Transkribering – funksjoner i v1

### Valg

| Valg | Alternativer | Standard |
|---|---|---|
| Målform | Bokmål · Nynorsk | Bokmål (husker siste valg) |
| Stil | **Lydrett** – det som faktisk blir sagt · **Tolket** – muntlig språk rettet til skriftlig | Tolket |
| Kvalitet | Rask · Anbefalt · Best | Anbefalt |

### Hvordan valgene slår ut

Hver stil har sin NB-Whisper-modell, begge fra `NbAiLab`:

- **Lydrett → verbatim-modellene** (`nb-whisper-<størrelse>-verbatim`). Mer bokstavelig, retter ikke grammatikk. Gir små bokstaver og lite tegnsetting. Det er slik modellen er trent, ikke en feil.
- **Tolket → hovedmodellen** (`nb-whisper-<størrelse>`). Retter muntlig språk til skriftlig, egnet til referat og teksting. Kjøres med de samme tidsstempel-innstillingene som verbatim (`variant_options` i `models.json`), ellers blir segmentene 30 sekunder lange.
  - *Avgjort etter steg 3:* hovedmodellen ga færre feil og strøk færre ord enn semantic-modellene, som bare finnes som uferdig utgave i `NbAiLabBeta` (desember 2023). Semantic brukes ikke (se `docs/kvalitet.md`).

Målform styres med språkparameteren til Whisper: `no` for bokmål og `nn` for nynorsk. Spiken (steg 0) bekrefter at dette virker i whisper.cpp med NB-Whisper-modellene, og at begge stilene kan gi nynorsk.

Lydrett nynorsk gir det som blir sagt: snakker personen bokmål, blir noe stående på bokmål (steg 3). Når både lydrett og nynorsk er valgt, viser appen en kort forklaring om dette under Stil. Teksten etterbehandles ikke.

Kvalitet styrer modellstørrelse:

| Kvalitet | Modell | Omtrent nedlasting (q5) | Når |
|---|---|---|---|
| Rask | small | ~200 MB | Eldre maskiner, rask førsteutkast |
| Anbefalt | medium | ~550 MB | De fleste |
| Best | large | ~1,1 GB | Apple Silicon eller kraftig PC |

Størrelsene er anslag og må bekreftes i spiken. Appen viser faktisk størrelse før nedlasting.

Søkemåten er beam 5 som standard. «Raskere» (greedy) kan velges i innstillingene, men gjelder bare tolket. Lydrett bruker alltid beam 5, fordi greedy der gir nesten dobbelt så mange feil uten å være raskere (steg 3).

Lydrett med små bokstaver: vis teksten slik modellen gir den i v1. Ikke legg på automatisk stor forbokstav eller tegnsetting, det gjør teksten mindre lydrett.

### Filer inn

Lyd: mp3, m4a/AAC (også rå `.aac`), wav, flac, ogg/Vorbis (`.ogg`, `.oga`). Video: mp4 og mov (lydsporet brukes). Flere filer kan legges i kø. Lange filer (minst 3 timer) skal virke uten å gå tom for minne.

Ikke støttet i v1: webm/Opus og andre format symphonia ikke leser. Appen sier tydelig hvilket format filen har og hva som støttes, og foreslår å konvertere til mp3 eller wav.

### Under kjøring

- Framdrift i prosent og anslått gjenværende tid.
- Teksten vises fortløpende etter hvert som segmentene blir ferdige.
- Avbryt-knapp som stopper innen få sekunder. Grensesnittet får svar med en gang; whisper regner ferdig vinduet sitt i bakgrunnen, og en ny jobb venter til det er gjort.
- Maskinen skal ikke gå i dvale mens en jobb kjører (Mac: IOKit-påstand `PreventUserIdleSystemSleep`, samme mekanisme som `NSProcessInfo` beginActivity; Windows: `SetThreadExecutionState`).

### Resultatet

- Tekst delt i segmenter med tidskode. Klikk på et segment spiller av lyden fra det punktet.
- Teksten kan rettes direkte i appen.
- Lagre som: **.txt** og **.docx** (begge med eller uten tidskoder, brukeren velger), **.srt**, **.vtt**. «Lagre som» åpner alltid lagringsdialogen, forhåndsutfylt med standard navn og mappe (under). Kopier alt legger teksten på utklippstavlen, uten tidskoder.
- Standard lagringssted: samme mappe som lydfilen, filnavn `<lydfil>.<målform>.<stil>.<ending>`, f.eks. `intervju.nynorsk.tolket.docx`. Målform skrives `bokmal` (uten å) eller `nynorsk`.
- Øverst i eksportert tekst: filnavn, dato, målform, stil, modell og en linje om at teksten er maskintranskribert og må kontrolleres mot lyden. I .vtt står dette som `NOTE`. .srt har ingen topptekst, siden den ville blitt vist som undertekst.

### Modeller

- Modellene følger ikke med installasjonen. De lastes ned første gang de trengs, etter at brukeren har sett navn og størrelse og trykket «Last ned».
- Kilde: Nasjonalbibliotekets KI-lab på Hugging Face (`NbAiLab`, ev. `NbAiLabBeta`), ggml-filer for whisper.cpp. Lisens Apache 2.0, nevnes i Om-vinduet.
- Hver modell har fast URL og SHA-256 i `models.json` i repoet. Filen sjekkes etter nedlasting og forkastes hvis summen ikke stemmer.
- Nedlasting kan gjenopptas etter brudd.
- Innstillinger viser nedlastede modeller, plass de bruker og en slett-knapp.
- Mulighet for å peke på en mappe med modeller (for redaksjoner som deler dem på en nettverksdisk eller minnepinne).

## Nettverk og personvern

Appen gjør bare disse nettkallene:

1. Nedlasting av modeller, når brukeren trykker «Last ned».
2. Sjekk etter ny versjon ved oppstart. Kan slås av i innstillingene.

Ingenting annet. Ingen analyse, ingen feilrapportering til nett, ingen innlogging. Lyd, tekst og filnavn sendes aldri noe sted. Tauri sin CSP og `capabilities` skal låse nettilgangen til nettopp disse vertene: `huggingface.co` og `*.hf.co` for modellnedlasting (Hugging Face sender videre til CDN), og GitHub for versjonssjekk.

Logger skrives lokalt og inneholder aldri transkribert tekst eller filnavn utover det brukeren selv eksporterer.

## Verktøykassen som skall

- Venstremeny med verktøy. I v1 bare Transkribering, men skallet bygges for flere.
- Hvert verktøy er en egen modul: én mappe i frontend, én Rust-modul, og en oppføring i et register (`id`, navn, ikon, kort beskrivelse). Et nytt verktøy skal kunne legges til uten å røre de andre.
- Felles for alle verktøy: innstillinger, Om-vindu, oppdatering, lys/mørk modus etter systemet.
- Grensesnitt på norsk (bokmål). Nynorsk grensesnitt er ønsket senere, så alle tekster ligger i én språkfil fra start.

## Teknisk

| Del | Valg |
|---|---|
| Rammeverk | Tauri 2 (Rust + webgrensesnitt) |
| Transkribering | whisper.cpp via `whisper-rs`, lenket inn i appen. Sidecar med `whisper-cli` er reserve hvis bindingen skaper problemer (avgjøres i spiken) |
| Akselerasjon | Mac: Metal. Windows: CPU (AVX2) i v1. Vulkan for GPU vurderes etter måling. whisper.cpp bygges med `GGML_NATIVE=OFF` |
| Lyddekoding | `symphonia` + resampling til 16 kHz mono med `rubato`. Ingen ffmpeg i v1 |
| Frontend | Vanilla TypeScript + Vite, ingen tungt rammeverk |
| docx | `docx-rs` |
| Nedlasting og sjekksum | `ureq` (features `rustls`, `platform-verifier`, `win-system-proxy`) og `sha2`. Godkjent etter spiken, sammen med `docx-rs`, `serde`/`serde_json` og featuren `raw-api` i `whisper-rs`. symphonia 0.5 |
| Lagring av innstillinger | Tauri `store`-plugin, lokalt |
| Oppdatering | Tauri `updater`-plugin mot GitHub Releases, signerte oppdateringer |

### Plattformer

- **Mac:** macOS 13 eller nyere, Apple Silicon. Intel-Mac er ikke med i v1.
- **Windows:** Windows 10 og 11, 64-bit x86 med AVX2. ARM-Windows er ikke med i v1. PC-er uten AVX2 (eldre Celeron/Pentium Silver) støttes ikke; appen sier tydelig fra i stedet for å krasje.
- Minst 8 GB minne. «Best» anbefales bare med 16 GB eller mer; appen sier fra hvis maskinen har mindre.

### Ytelsesmål

Målt med «Anbefalt» på et intervju på 30 minutter:

| Maskin | Tolket | Lydrett |
|---|---|---|
| MacBook med Apple Silicon (M1 eller nyere) | under 10 minutter | under 30 minutter |
| Vanlig Windows-laptop, 4–8 kjerner, uten GPU | under 30 minutter | ikke satt |

Lydrett har et eget, slakkere mål fordi verbatim-modellene er omtrent fire ganger tregere enn hovedmodellen (steg 3). Tallene for M1 er foreløpige: de endelige settes etter måling på en ekte M1. Målene justeres etter første måling. Viser det seg at Windows uten GPU blir for tregt med medium, blir «Rask» standard på Windows.

## Distribusjon

- GitHub Actions bygger `.dmg` (Mac) og `.msi` (Windows) når en versjonstagg pushes.
- **Mac:** signert med Developer ID og notarisert. Uten det stopper Gatekeeper appen.
- **Windows:** kodesignert. Uten signatur viser SmartScreen en skremmende advarsel som vil stoppe mange medlemmer. Sertifikat avklares (se åpne spørsmål).
### Nedlastingssiden

- Verktøykassen har en offentlig nedlastingsside på **lla.no** med Mac- og Windows-knapp, systemkrav, personvernavsnitt og installasjonsveiledning. Siden er `site/lla-no/verktoy.html`; John Inge eier den og legger den ut selv.
- LLA-logoen står øverst på siden (`site/lla-logo.png`, samme fil som i LLAs andre verktøy).
- Siden leser siste versjon fra GitHub Releases i nettleseren, så knappene alltid peker på nyeste bygg uten at siden må endres.
- **Installasjonsfilene ligger på GitHub Releases** i det offentlige repoet `JohnLLA/lla-verktoykasse-releases`, mens koden er privat. Den samme adressen brukes av oppdateringsfunksjonen i appen.

### Hvem gjør hva

- Agentene pusher ikke versjonstagger, lager ikke releaser og sender ikke noe til medlemmene. Det gjør John Inge.

## Testing

- Rust-logikk (dekoding, resampling, segmentering, eksport, `models.json`-sjekk) testes med `cargo test`.
- Kvalitet måles med et fast testsett (se `kvalitetsmaler`): ordfeilrate (WER) per målform og stil, mot håndskrevne fasiter.
- I steg 3 fantes ingen menneskeskrevet fasit for tolket. **Før release** lages en ekte tolket-fasit fra NPSC-referatene, og tolket måles på nytt mot den (neste kvalitetsrunde).
- Hver PR skal bygge på både Mac og Windows i CI.
- Det som krever ekte maskin (installasjon, signering, Gatekeeper, SmartScreen, dvale, store filer), leveres som manuell sjekkliste merket «ikke kjørt på enhet». John Inge kjører den, og Windows-delen på en vanlig redaksjons-PC.

## Rekkefølge

0. **Spike:** whisper-rs + NB-Whisper ggml på Mac og Windows. Bekreft `no`/`nn`, verbatim/semantic, modell-URL-er, størrelser og SHA-256. Mål fart. Skriv funnene i `docs/spike.md`.
1. **Kjerne** (Rust): dekoding, modellnedlasting, transkribering med framdrift og avbryt, eksport.
2. **Skall og grensesnitt:** verktøymeny, Transkribering-skjermen, innstillinger.
3. **Kvalitet:** testsett og måling av alle seks kombinasjoner (2 målformer × 2 stiler, i minst to størrelser).
4. **Distribusjon:** CI, signering, notarisering, oppdatering, nedlastingsside.
5. **Pilot:** 3–5 redaksjoner, med en kort tilbakemeldingsrunde før bred utsending.

## Utenfor v1 (skrives i `docs/senere.md`, bygges ikke)

- Talerseparasjon (hvem sier hva)
- Opptak direkte i appen
- Engelsk og samisk
- Oversettelse
- Nynorsk grensesnitt
- Intel-Mac og ARM-Windows
- GPU på Windows (Vulkan/CUDA), hvis målingene viser at det trengs
- Flere verktøy i kassen
- Sammendrag med språkmodell (vil kreve egen vurdering av personvern, siden det bryter med «alt lokalt» hvis det går via nett)
