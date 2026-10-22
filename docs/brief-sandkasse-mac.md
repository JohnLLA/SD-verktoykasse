# Brief til sidecar-bygger: sandkasse for verktøyene på Mac (steg 6.4)

Bruk: «bruk sidecar-bygger på docs/brief-sandkasse-mac.md». Les først:
- `CLAUDE.md`
- `docs/spesifikasjon-journalistverktoy.md`
- `src-tauri/src/tools/jv/runner.rs`, `package.rs` og `args.rs`

Gren og PR: `steg-6-4-sandkasse-mac`.

## Hvorfor

Verktøyene leser filer fra utenforstående: lekkede PDF-er, tilsendte videoer og skannede bilder. En fil kan være laget for å utnytte en feil i ffmpeg, poppler, tesseract, libtiff eller et av Python-bibliotekene. I dag kjører verktøyprosessene med brukerens fulle rettigheter. Sandkassen skal sørge for at en utnyttet feil ikke kan:
1. sende noe ut av maskinen (viktigst)
2. lese andre filer enn dem brukeren valgte
3. skrive andre steder enn i utmappen

## Oppgave

1. **Start gjennom `sandbox-exec` på Mac.** Endre `runner::command` slik at verktøyet startes som `/usr/bin/sandbox-exec -f <profil> -D NAVN=verdi … <entry> <args>`.
   - Bare på `target_os = "macos"`. Windows-veien endres ikke i dette steget, men CI skal fortsatt bygge og teste begge plattformer (regel 9).
   - Prosessgruppen, avbryt (`kill_tree`), det rene miljøet og fremdriftslesingen skal virke som før.
2. **Profilen.** Lag en fast mal i `src-tauri/src/tools/jv/sandbox/profil.sb` og bygg den inn med `include_str!`.
   - **Stier sendes aldri inn i profilteksten.** Alle stier går som parametere (`-D IN_0=…`, `(param "IN_0")`). Det eneste som genereres, er linjer som `(literal (param "IN_3"))` for antallet inndatafiler. Da kan ikke et filnavn med `"`, `)`, `;` eller linjeskift endre profilen.
   - Stiene normaliseres med `canonicalize` før de sendes inn. `/var` og `/private/var` er samme sted på macOS, og profilen må treffe den virkelige stien.
   - **Nett:** `(deny network*)`. Hvis Python-arbeidere (ocrmypdf) trenger lokale unix-sockets, åpnes bare `(local unix-socket)`, ikke mer.
   - **Skriving:** alt stengt, unntatt:
     - utmappen
     - en egen midlertidig mappe per kjøring i appens datamappe, som settes som `TMPDIR`
     - `/dev/null` og `/dev/dtracehelper`
   - **Lesing:**
     - stengt for hele `HOME` og `/Volumes`
     - åpnet igjen for pakkens mappe, filene brukeren valgte, utmappen og den midlertidige mappen
     - systemstier (`/System`, `/usr/lib`, `/Library/Fonts` osv.) kan leses
   - **Kjøring av programmer (`process-exec`):** bare filer inne i pakkens mappe. ocrmypdf starter tesseract, og keyframes starter ffmpeg, så det må virke. Ingenting utenfor pakken kan startes, heller ikke `/bin/sh`.
   - **Mach-tjenester:** steng tjenestene som kan åpne nettadresser eller andre programmer på vegne av prosessen, for eksempel `com.apple.coreservices.launchservicesd` og `com.apple.lsd.*`. Skriv i PR-en hvilke tjenester du stengte og hvorfor resten må stå åpne.
   - Prøv gjerne `(deny default)` med en hviteliste. Blir det for skjørt, er `(allow default)` med de forbudene over godt nok, og valget står i PR-en.
3. **Den midlertidige mappen** lages før kjøring og slettes etterpå, også ved feil og avbryt. Rydd opp gamle mapper fra kjøringer som krasjet, ved neste oppstart av en kjøring.
4. **Feil lukker, aldri åpner.**
   - Hvis `sandbox-exec` mangler eller profilen avvises, kjøres verktøyet **ikke**.
   - Brukeren får en norsk melding: «Verktøyet kunne ikke startes i beskyttet modus.»
   - Det finnes ingen innstilling for å slå sandkassen av.
5. **Pakkene.** Endre PyInstaller-bygget i `sidecar/build/` bare hvis det må til. Det kan for eksempel være nødvendig hvis noe skriver til `~/Library` eller leser utenfor pakken ved oppstart. Skriv hver endring i PR-en.
6. **Spesifikasjonen.** Legg til seksjonen «Sandkasse (Mac)» i `docs/spesifikasjon-journalistverktoy.md`. Den skal beskrive hva profilen tillater, og at Windows kommer i et eget steg (AppContainer).

## Tester

- **`cargo test` (Mac):**
  - profilbygging med filnavn som inneholder mellomrom, æøå, `"`, `(`, `)`, `;`, linjeskift og starter med `-`
  - én og mange inndatafiler
  - at stiene bare står i `-D`-parametere og aldri i profilteksten
  - at kjøringen stopper hvis `sandbox-exec` mangler (falsk sti)
- **En falsk pakke (testprogram) som prøver det sandkassen skal stoppe.** Alle disse skal feile:
  - koble til en lokal lytter på `127.0.0.1`
  - slå opp et DNS-navn
  - lese en fil i `HOME` som ikke er valgt
  - lese en fil på `/Volumes` som ikke er valgt
  - skrive utenfor utmappen
  - starte `/bin/sh` og `/usr/bin/open`

  Det samme programmet skal klare å lese den valgte fila og skrive i utmappen.
- **Python-testene mot de pakkede binærfilene, gjennom sandkassen.** Utvid `sidecar/build/pytest_packaged.py` (eller tilsvarende) slik at alle ni verktøyene kjøres via `sandbox-exec` med den samme profilen som appen bruker. Alle testene skal passere.
- **Måling:** oppstartstid med og uten sandkasse for hvert verktøy. Skriv tallene i PR-en.

## Grenser

- Ingen nye avhengigheter (regel 7). `sandbox-exec` er en del av macOS.
- Ikke rør transkriberingsmodulen, grensesnittet eller Windows-koden.
- Ingen filnavn eller stier i logger (regel 2). Det gjelder også feilmeldinger fra `sandbox-exec`.
- Ingen release og ingen tagger (regel 11).

## Sjekkliste «ikke kjørt på enhet»

Lag `docs/sjekkliste-steg-6-4.md` som John Inge kjører på en ren Mac med macOS 26. Den skal dekke:
- **Alle ni verktøyene:** last ned og kjør hvert på en testfil fra en ekstern disk (`/Volumes/...`) og fra `~/Documents`.
- **Valgfrie innstillinger:** OCR med flere språk, sladding av flersidig PDF og keyframes på en lang video.
- **Avbryt** midt i en kjøring. Den midlertidige mappen skal være borte etterpå.
- **Konsoll.app** filtrert på `sandbox`. Notér avvisninger som ikke stopper verktøyet, så profilen kan strammes inn.

## Til kontraktvokter (i tillegg til docs/brief-jv-kontroll.md)

1. **Profilen** er en fast mal, og stier kommer bare som `-D`-parametere. Prøv selv et filnavn med `")` og linjeskift.
2. **Nett:** kjør `keyframes`, `loudness`, `ocr` og `redact` på filer som heter `http:127.0.0.1:<port>.mp4` og lignende, med en lokal lytter. Ingen tilkobling.
3. **Lesing og skriving:** et verktøy skal ikke kunne lese en fil i `HOME` som ikke er valgt, eller skrive utenfor utmappen. Test med den falske pakken.
4. **Feil lukker:** uten `sandbox-exec`, eller med ødelagt profil, starter ingenting.
5. **Opprydding:** ingen midlertidige mapper blir liggende igjen etter feil eller avbryt.
6. **Windows** bygger og består testene i CI uten endringer i oppførselen.
7. **Python-testene** passerer gjennom sandkassen for alle ni verktøyene.

Gi GODKJENT bare når alle punktene holder.

## Rapport

Kort på norsk:
- PR-nummer og hva som er bygget
- profilens hovedregler
- endringer i pakkebygget
- testresultat
- oppstartstider med og uten sandkasse
- det som ikke lot seg stenge, og hvorfor
