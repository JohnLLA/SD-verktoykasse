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

NB-Whisper finnes i to varianter som passer nøyaktig til de to stilene:

- **Lydrett → verbatim-modellene** (`nb-whisper-<størrelse>-verbatim`). Mer bokstavelig, retter ikke grammatikk. Gir små bokstaver og lite tegnsetting. Det er slik modellen er trent, ikke en feil.
- **Tolket → semantic-modellene** (`nb-whisper-<størrelse>-semantic`). Fanger innholdet heller enn hvert ord, egnet til referat og teksting.

Målform styres med språkparameteren til Whisper: `no` for bokmål og `nn` for nynorsk. Spiken (steg 0) bekrefter at dette virker i whisper.cpp med NB-Whisper-modellene, og at begge stilene kan gi nynorsk.

Kvalitet styrer modellstørrelse:

| Kvalitet | Modell | Omtrent nedlasting (q5) | Når |
|---|---|---|---|
| Rask | small | ~200 MB | Eldre maskiner, rask førsteutkast |
| Anbefalt | medium | ~550 MB | De fleste |
| Best | large | ~1,1 GB | Apple Silicon eller kraftig PC |

Størrelsene er anslag og må bekreftes i spiken. Appen viser faktisk størrelse før nedlasting.

Lydrett med små bokstaver: vis teksten slik modellen gir den i v1. Ikke legg på automatisk stor forbokstav eller tegnsetting, det gjør teksten mindre lydrett.

### Filer inn

Lyd: mp3, m4a/AAC, wav, flac, ogg/Vorbis. Video: mp4 og mov (lydsporet brukes). Flere filer kan legges i kø. Lange filer (minst 3 timer) skal virke uten å gå tom for minne.

Ikke støttet i v1: webm/Opus og andre format symphonia ikke leser. Appen sier tydelig hvilket format filen har og hva som støttes, og foreslår å konvertere til mp3 eller wav.

### Under kjøring

- Framdrift i prosent og anslått gjenværende tid.
- Teksten vises fortløpende etter hvert som segmentene blir ferdige.
- Avbryt-knapp som stopper innen få sekunder.
- Maskinen skal ikke gå i dvale mens en jobb kjører (Mac: `NSProcessInfo` beginActivity; Windows: `SetThreadExecutionState`).

### Resultatet

- Tekst delt i segmenter med tidskode. Klikk på et segment spiller av lyden fra det punktet.
- Teksten kan rettes direkte i appen.
- Lagre som: **.txt** (med eller uten tidskoder), **.srt**, **.vtt**, **.docx**. Kopier alt til utklippstavlen.
- Standard lagringssted: samme mappe som lydfilen, filnavn `<lydfil>.<målform>.<stil>.<ending>`, f.eks. `intervju.nynorsk.tolket.docx`.
- Øverst i eksportert tekst: filnavn, dato, målform, stil, modell og en linje om at teksten er maskintranskribert og må kontrolleres mot lyden.

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

Ingenting annet. Ingen analyse, ingen feilrapportering til nett, ingen innlogging. Lyd, tekst og filnavn sendes aldri noe sted. Tauri sin CSP og `capabilities` skal låse nettilgangen til nettopp de to domenene.

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
| Akselerasjon | Mac: Metal. Windows: CPU (AVX2) i v1. Vulkan for GPU vurderes etter måling |
| Lyddekoding | `symphonia` + resampling til 16 kHz mono med `rubato`. Ingen ffmpeg i v1 |
| Frontend | Vanilla TypeScript + Vite, ingen tungt rammeverk |
| docx | Rust-crate (`docx-rs` eller tilsvarende) – krever ja fra John Inge som alle avhengigheter |
| Lagring av innstillinger | Tauri `store`-plugin, lokalt |
| Oppdatering | Tauri `updater`-plugin mot GitHub Releases, signerte oppdateringer |

### Plattformer

- **Mac:** macOS 13 eller nyere, Apple Silicon. Intel-Mac er ikke med i v1.
- **Windows:** Windows 10 og 11, 64-bit x86. ARM-Windows er ikke med i v1.
- Minst 8 GB minne. «Best» anbefales bare med 16 GB eller mer; appen sier fra hvis maskinen har mindre.

### Ytelsesmål

Målt med «Anbefalt» på et intervju på 30 minutter:

| Maskin | Mål |
|---|---|
| MacBook med Apple Silicon (M1 eller nyere) | under 10 minutter |
| Vanlig Windows-laptop, 4–8 kjerner, uten GPU | under 30 minutter |

Målene justeres etter første måling. Viser det seg at Windows uten GPU blir for tregt med medium, blir «Rask» standard på Windows.

## Distribusjon

- GitHub Actions bygger `.dmg` (Mac) og `.msi` (Windows) når en versjonstagg pushes.
- **Mac:** signert med Developer ID og notarisert. Uten det stopper Gatekeeper appen.
- **Windows:** kodesignert. Uten signatur viser SmartScreen en skremmende advarsel som vil stoppe mange medlemmer. Sertifikat avklares (se åpne spørsmål).
### Nedlastingssiden på Railway

- Verktøykassen har en offentlig nedlastingsside med Mac- og Windows-knapp, systemkrav, personvernavsnitt og installasjonsveiledning med skjermbilder.
- Siden kjøres på **Railway under LLA-kontoen (john@lla.no)**, i et eget prosjekt, aldri på John Inges private konto.
- Siden er statisk (HTML/CSS) servert av en liten webserver i en container. Den leser siste versjon fra GitHub Releases, så knappene alltid peker på nyeste bygg uten ny deploy.
- **Selve installasjonsfilene ligger ikke på Railway.** De ligger på GitHub Releases, som tåler store filer og mange nedlastinger uten trafikkostnad. Det krever at releasene er offentlige: enten et offentlig repo, eller et eget offentlig repo bare for releaser (`lla-verktoykasse-releases`) mens koden er privat. Den samme adressen brukes av oppdateringsfunksjonen i appen.
- Eget domene (f.eks. `verktoy.lla.no`) kobles til Railway-tjenesten når LLA har bestemt navnet.

### Tilgang til Railway

- Deploy skjer med et **prosjekttoken** fra LLA-prosjektet på Railway (`RAILWAY_TOKEN`), lagt i en lokal `.env` som er i `.gitignore`, og i GitHub Secrets hvis siden skal deployes fra CI. Da kan Railway-CLI-en på Macen fortsatt være logget inn på den private kontoen uten at noe havner feil sted.
- Før hver deploy sjekkes at målet er LLA-prosjektet. Deployer noe mot feil konto eller feil prosjekt, stoppes det.

### Hvem gjør hva

- `byggmester` kan deploye nedlastingssiden til LLA-prosjektet på Railway når John Inge ber om det.
- Agentene pusher ikke versjonstagger, lager ikke releaser og sender ikke noe til medlemmene. Det gjør John Inge.

## Testing

- Rust-logikk (dekoding, resampling, segmentering, eksport, `models.json`-sjekk) testes med `cargo test`.
- Kvalitet måles med et fast testsett (se `kvalitetsmaler`): ordfeilrate (WER) per målform og stil, mot håndskrevne fasiter.
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
