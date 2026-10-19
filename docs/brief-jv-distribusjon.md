# Brief til byggmester: verktøypakker, katalog og release

Bruk: «bruk byggmester på docs/brief-jv-distribusjon.md». Les `docs/spesifikasjon-journalistverktoy.md`, `docs/spike-sidecar.md` og `docs/distribusjon.md` først. Release-arbeidsflyten for selve appen endres ikke.

## Oppgave

1. **`.github/workflows/tools-release.yml`** kjøres når John Inge pusher en tagg `jv-<id>-v<versjon>` eller `jv-alle-v<versjon>`.
   - **Bygg:** pakkene for `aarch64-apple-darwin` med `sidecar/build/` (runde A). Lag jobben slik at `x86_64-pc-windows-msvc` kan slås på i runde B uten omskriving. Systemprogrammene hentes etter `binaries.json`, med sjekk av SHA-256.
   - **Signering:**
     - Mac: alle binærfiler med Developer ID og hardened runtime, notarisert der det trengs.
     - Windows: når sertifikat finnes, ellers usignert med merknad i release-notatet.
   - **Test:** alle Python-testene mot de pakkede binærfilene, med nettet sperret.
   - **Kildekode:** `jv-<versjon>-kildekode.tar.gz` med egen kode (`sidecar/jv/`) og kildekoden til tredjepartsdelene, slik AGPL krever. Uten egen kode er releasen ikke komplett.
   - **Opplasting som utkast** til `JohnLLA/lla-verktoykasse-releases` med `RELEASES_TOKEN`:
     - pakkene som `jv-<id>-<versjon>-<target>.tar.gz/.zip`
     - ny `tools.json` og `tools.json.sig` som utkast til release-taggen `katalog`
2. **Katalognøkkel:**
   - et eget minisign-nøkkelpar for katalogen
   - den private nøkkelen bare i Secrets (`TOOLS_MINISIGN_KEY` og `TOOLS_MINISIGN_PASSWORD`)
   - den offentlige nøkkelen innebygd i appen

   Skriv i `docs/distribusjon.md` hva som skjer hvis nøkkelen mistes, nemlig at appene ikke kan få nye verktøy før appen er oppdatert med ny nøkkel. Skriv også at den må sikkerhetskopieres.
3. **`docs/distribusjon.md`:** ny seksjon «Verktøypakker» med det John Inge gjør steg for steg:
   - lage katalognøkkelen
   - pushe taggen
   - publisere pakke-releasen og katalog-releasen
   - kontrollere i appen at verktøyet kan lastes ned
4. **Åpen kildekode:**
   - lisenskontroll i CI: `cargo-deny`, npm-lisenssjekk og `pip-licenses`. Bygget stopper ved lisens utenfor lista.
   - generering av `THIRD_PARTY_LICENSES.md`
   - `docs/publisering.md` med sjekklisten fra «Før repoet gjøres offentlig». Kjør `gitleaks` på hele historikken og rapporter funnene til John Inge.
   - et CI-steg som stopper hvis en `.p8`-, `.p12`-, `.pem`- eller `.env`-fil eller `notarisering/` finnes i repoet

   Du endrer ikke synligheten på repoet selv.
5. **`site/lla-no/verktoy.html`:** når skallet med nedlasting er publisert, skal siden:
   - vise «Last ned verktøykassen» øverst for hver plattform
   - vise de ni verktøyene som «Lastes ned i appen», med status fra `tools.json`

   Siden leser i dag de frittstående DMG-ene. Behold det som reserve til John Inge sier at de skal bort.
6. **Sjekkliste «ikke kjørt på enhet»:** ren Mac uten Python eller Homebrew. På Windows sjekkes bare at appen viser «Kommer for Windows» og at Transkribering virker.
   - Installer appen.
   - Last ned hvert av de ni verktøyene i appen, kjør det på en testfil, oppdater og fjern.
   - Prøv nedlasting uten nett.
   - Sjekk Gatekeeper og SmartScreen.

## Grenser

Du pusher ikke tagger og lager ikke releaser (regel 11). Du lager alt klart og tester arbeidsflyten med `workflow_dispatch` mot en utkast-release.
