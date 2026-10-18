# Steg 2 – skall og grensesnitt: sjekkliste «ikke kjørt på enhet»

Alt i denne listen krever ekte maskin og er **ikke kjørt på enhet**, med unntak av det som står under «Prøvd på Mac under bygging». John Inge kjører den, Windows-delen på en vanlig redaksjons-PC.

Frontendlogikken (tidskoder, framdrift, kø, valg, feilkoder mot tekster, eksportforespørsel, kontrast) testes automatisk med `npm test`, og Rust-delen med `cargo test`. Begge kjøres i CI på macOS og Windows.

## Slik starter du appen

```sh
npm ci
npm run tauri dev        # utvikling, med ekte Rust-kjerne
```

`cargo test` i `src-tauri` trenger at `dist/` finnes (Tauri bygger inn frontenden). Kjør `npm run build` først, ellers feiler kompileringen med «frontendDist … doesn't exist».

For å slippe å laste ned en modell på 175 MB til prøving: legg `nb-whisper-small-verbatim-q5_0.bin` og `nb-whisper-small-semantic-q5_0.bin` i en mappe og velg den under Innstillinger → Egen modellmappe. (Appen sjekker SHA-256 første gang hver fil brukes.)

## Prøvevisning uten Tauri (utvikling)

`npm run dev` og åpne `http://localhost:1420/` i en vanlig nettleser. Da brukes en etterlikning av kjernen (`src/dev/mock.ts`) med oppdiktet tekst. Nyttig til å se alle tilstander. Parametre i adressen: `?modeller=ingen|alle`, `?tid=40` (sekunder en jobb varer), `?minne=8`, `?cpu=nei`, `?nedlasting=feil`, `?os=windows`. I konsollen: `__mock.drop(["/mappe/fil.mp3"])`. Dette følger ikke med i den ferdige appen.

## Mac

### Hele flyten med ekte modell

- [ ] Første start: tom tilstand med slippsone, «Velg fil» og tre valg. Standard er Bokmål, Tolket, Anbefalt.
- [ ] Dra en mp3 inn i vinduet: den dukker opp under «Klare til å transkribere». Dra flere filer samtidig, og dra inn flere etterpå.
- [ ] «Velg fil» åpner filvelgeren med lyd og video; flere filer kan velges.
- [ ] Med modell som mangler: «Denne kombinasjonen trenger en modell på N MB. Last ned?» der N er den faktiske størrelsen (small 175 MB, medium 539 MB, large 1,1 GB). «Last ned» viser framdrift. Avbryt midt i, trykk «Last ned» igjen: teksten sier at den fortsetter, og den gjør det.
- [ ] Slå av nettet midt i nedlastingen: melding «Ingen nettforbindelse» med råd. Slå på igjen og last ned: fortsetter.
- [ ] Når nedlastingen er ferdig, starter transkriberingen av seg selv.
- [ ] Under transkribering: framdrift i prosent, gjenværende tid, tekst som fyller seg fortløpende, «Avbryt» som stopper innen få sekunder, og at en ny fil kan startes rett etterpå.
- [ ] Flere filer i kø: de kjører én og én, og listen viser status for hver.
- [ ] Resultat: segmenter med tidskode til venstre. Klikk på tidskoden spiller lyden fra det punktet (test mp3, m4a og en mp4/mov). Segmentet som spilles, er fremhevet.
- [ ] Rett i teksten (inkludert Enter, som flytter til neste segment, og lim inn tekst med linjeskift). Lagre: rettelsene er med i filen.
- [ ] Lagre som: Word med og uten tidskoder, txt med og uten tidskoder, srt og vtt. Lagringsdialogen åpnes hver gang, forhåndsutfylt med `<lydfil>.<målform>.<stil>.<ending>` i samme mappe som lydfilen. Velg en annen mappe og et annet navn: filen havner der. Velg en fil som finnes: dialogen spør om erstatning (macOS og Windows), og filen erstattes ved «Ja». Lukk dialogen: ingenting lagres.
- [ ] Åpne Word-filen med og uten tidskoder: tidskoder er bare med i den første.
- [ ] «Vis i Finder» viser den lagrede filen (eller lydfilen hvis ingenting er lagret).
- [ ] «Kopier alt» legger teksten på utklippstavlen (lim inn i Pages/Word).
- [ ] Åpne docx og txt: toppteksten (fil, dato på norsk, målform, stil, modell og linjen om maskintranskribert) stemmer med språkfilen.
- [ ] Prøv alle seks kombinasjoner av målform og stil (to målformer × to stiler): riktig modell lastes ned og brukes. Lydrett skal vise små bokstaver og lite tegnsetting uten at appen retter det.
- [ ] Lukk vinduet midt i en jobb, og med tekst som ikke er lagret: «Avslutte appen?» vises. «Bli i appen» lar alt stå. Når alt er lagret, lukkes vinduet uten spørsmål.

### Feilmeldinger

- [ ] Dra inn en `.webm`, `.opus`, `.caf` og `.aiff`: raden viser «Filformatet støttes ikke», navnet på formatet og forslag om mp3 eller wav.
- [ ] En ødelagt mp3 (avkortet fil): «Filen kunne ikke leses» med råd.
- [ ] Flytt lydfilen mens den ligger i køen, og start: «Fant ikke filen».
- [ ] Fyll disken (eller bruk en liten minnepinne) ved nedlasting eller lagring: «Det er ikke nok plass på disken».
- [ ] Lagre til en mappe uten skrivetilgang: «Appen har ikke tilgang».
- [ ] Ingen feilmelding viser filsti, kode eller teknisk tekst.

## Til steg 4 (distribusjon)

- [ ] Full lisenstekst for NB-Whisper (Apache 2.0) og øvrige komponenter (whisper.cpp, Tauri, Symphonia m.fl.) tas med i appen, som en tredjepartsmelding i Om-vinduet. Om-vinduet har i dag bare navn, eier og lisensnavn.

### Skall og innstillinger

- [ ] Menyen til venstre viser Transkribering, Innstillinger og Om. Tastaturet virker (Tab, Enter, piltaster i de segmenterte valgene). Fokus er synlig overalt. «Hopp til innholdet» vises ved første Tab.
- [ ] Innstillinger → Modeller: nedlastede modeller med størrelse og «Slett». Sletting spør først, og plassen i oversikten går ned. En delvis nedlastet modell kan slettes.
- [ ] Egen modellmappe: velg en mappe med modellfilene (`<id>.bin`); modellene vises som «I din egen modellmappe» uten slett-knapp, og transkribering bruker dem uten ny nedlasting. «Bruk appens mappe» går tilbake. En mappe som er slettet etterpå, gir «Fant ikke mappen».
- [ ] Nøyaktighet og fart: velg «Raskere», start en jobb og sjekk at den er raskere. Valget huskes etter omstart.
- [ ] «Se etter ny versjon når appen starter»: bryteren huskes etter omstart. (Selve sjekken kommer i steg 4; appen gjør ingen nettkall for dette ennå.)
- [ ] Om: versjon, setningen «Lyden din forlater aldri maskinen.», NB-Whisper med Apache License 2.0 fra Nasjonalbibliotekets KI-lab, og de øvrige lisensene.
- [ ] Siste valg (målform, stil, kvalitet) huskes etter omstart.
- [ ] Lys og mørk modus følger systemet (Systeminnstillinger → Utseende), også mens appen er åpen.
- [ ] Mac-minne under 16 GB: velg «Best» og se advarselen (kan testes ved å bytte til en Mac med 8 GB).
- [ ] Dvale: under en lang jobb går ikke maskinen i dvale (se `docs/sjekkliste-steg-1.md`).

### Personvern

- [ ] Start appen fra Terminal og kjør en jobb: ingen filnavn, tekst eller stier i terminalutskriften.
- [ ] Nettverkstrafikk (Little Snitch, Wireshark eller lignende): ingen kall ved oppstart og under transkribering. Under nedlasting går trafikken bare til `huggingface.co` og `*.hf.co`.
- [ ] Lyd fra en sluppet fil spilles av uten nettverkstrafikk. I utviklerverktøyet (hvis tilgjengelig) viser Console ingen CSP-brudd under normal bruk.

## Windows (vanlig redaksjons-PC)

- [ ] Alle punktene over, med disse tilleggene:
- [ ] Utseendet: skrift, avstander og farger ser riktige ut i WebView2, lys og mørk (Innstillinger → Personalisering → Farger).
- [ ] Dra-og-slipp fra Utforsker, også fra OneDrive-mappe og nettverksdisk, og fra mappe med æøå i navnet.
- [ ] Avspilling av mp3, m4a (AAC) og wav ved klikk på tidskode. Prøv også flac og ogg: WebView2 spiller dem, WKWebView på Mac spiller kanskje ikke alle (da vises «Lyden kan ikke spilles av her», og teksten virker likevel).
- [ ] Knappen sier «Vis i Utforsker», og Utforsker åpnes med filen markert.
- [ ] «Lagre som»: dialogen viser riktig filendelse; lagre til nettverksdisk og minnepinne.
- [ ] Kopier alt og lim inn i Word.
- [ ] PC uten AVX2: etter at filer er lagt til, vises «Denne maskinen er for gammel til å transkribere» i stedet for Start.
- [ ] Skalering 125 % og 150 %: ingenting er avkuttet i minstestørrelsen på vinduet (720 × 520).
- [ ] Skjermleser (Narrator eller NVDA): menyen, valgene og framdriften leses opp, og meldinger som «2 filer lagt til» og «Lagret som …» leses.

## Prøvd på Mac under bygging

Se PR-beskrivelsen for hva som faktisk ble kjørt (`npm run tauri dev`, prøvevisning i Chrome med skjermbilder av alle tilstander i lys og mørk modus, og hva som ikke lot seg prøve uten ekte hender på maskinen).
