# Distribusjon: bygg, signering, oppdatering og release

Steg 4. Dette dokumentet er oppskriften for John Inge. Agentene lager ikke releaser, pusher ikke versjonstagger og laster ikke opp installasjonsfiler (regel 11). Alt under er forberedt og venter på at du lager hemmelighetene og trykker på knappen.

Det som er prøvd og ikke prøvd, står i PR-beskrivelsen. Det som må prøves på ekte maskiner, står i `docs/sjekkliste-steg-4.md` (merket «ikke kjørt på enhet»).

## Oversikt

```
privat repo  JohnLLA/lla-verktoykasse            kode, CI, hemmeligheter
                    |  tagg v0.2.0 (du pusher)
                    v
        arbeidsflyten «release»  (.github/workflows/release.yml)
          1. plan: sjekker tagg, versjon, hemmeligheter, tester
          2. bygg: .dmg (Mac arm64) og .msi (Windows x64), signert når hemmelighetene finnes
          3. publiser: UTKAST i det offentlige repoet
                    |
                    v
offentlig repo  JohnLLA/lla-verktoykasse-releases   installasjonsfiler + latest.json
                    ^                          ^
   nedlastingssiden på lla.no          appens oppdatering
   (site/lla-no/verktoy.html, din)     (Tauri updater, signert)
```

Alle releaser ligger i `JohnLLA/lla-verktoykasse-releases`. Arbeidsflyten lager bare **utkast** (draft). Medlemmer og appen ser ingenting før du selv trykker «Publish release» i GitHub.

## Filnavn (avtale med nedlastingssiden)

Nedlastingssiden (`site/lla-no/verktoy.html`) henter `releases/latest` fra API-et og velger fil på endelsen: `.dmg` for Mac (foretrekker navn med `aarch64`), `.msi` for Windows. Release-arbeidsflyten gir derfor disse navnene, alltid bare ASCII og uten mellomrom:

| Fil | Bruk |
|---|---|
| `LLAs-verktoykasse_<versjon>_aarch64.dmg` | Mac, nedlasting for medlemmer |
| `LLAs-verktoykasse_<versjon>_x64.msi` | Windows, nedlasting for medlemmer, og oppdateringspakken på Windows |
| `LLAs-verktoykasse_<versjon>_x64.msi.sig` | signatur for oppdateringen |
| `LLAs-verktoykasse_<versjon>_aarch64.app.tar.gz` (+ `.sig`) | oppdateringspakken på Mac |
| `latest.json` | oppdateringsfilen appen leser |

Det er nøyaktig én fil som slutter på `.dmg` og én på `.msi` per release (`.sig` og `.tar.gz` treffer ikke siden). Mønsteret er låst i `tools/lag-latest-json.mjs` og testet (`npm run test:tools`). Endres siden, må filnavnene fortsatt tilfredsstille dette.

Versjonsnummeret finnes ett sted: `version` i `src-tauri/tauri.conf.json`. Taggen må være `v` + det nummeret (arbeidsflyten stopper ellers). `version` i `src-tauri/Cargo.toml` og `package.json` brukes ikke av bygget og trenger ikke endres.

## Hemmeligheter og variabler du må lage

Legges inn i det **private** repoet: GitHub, `JohnLLA/lla-verktoykasse`, Settings, Secrets and variables, Actions. Hemmeligheter under «Secrets», variabler under «Variables». Ingenting av dette skal inn i repoet eller i en chat.

### 1. Token for releases-repoet (påkrevd)

| Navn | Innhold |
|---|---|
| `RELEASES_TOKEN` | fingranulert personlig token |

Lag den slik: github.com, Settings, Developer settings, Personal access tokens, Fine-grained tokens, Generate new token.
- Resource owner: `JohnLLA`.
- Repository access: **bare** `lla-verktoykasse-releases`.
- Permissions: Repository permissions, **Contents: Read and write**. Ingenting annet.
- Utløpsdato: maks ett år. Sett en påminnelse i kalenderen; utløper den, stopper arbeidsflyten med melding om at `RELEASES_TOKEN` mangler eller avvises.

### 2. Oppdateringsnøkkel (påkrevd for å publisere)

Tauri signerer hver oppdatering med et nøkkelpar. Appen har den offentlige nøkkelen og avviser alt som ikke er signert med den private.

```
npx tauri signer generate -w ~/.tauri/lla-verktoykasse.key
```

Velg et passord. Du får to filer:
- `lla-verktoykasse.key.pub`: den **offentlige** nøkkelen. Lim innholdet (én linje) inn i `src-tauri/tauri.conf.json` som `plugins.updater.pubkey`, i stedet for `ERSTATT-MED-OFFENTLIG-OPPDATERINGSNOKKEL ...`. Dette committes i en vanlig PR.
- `lla-verktoykasse.key`: den **private** nøkkelen. Aldri i repoet.

| Navn | Innhold |
|---|---|
| `TAURI_SIGNING_PRIVATE_KEY` | hele innholdet i `lla-verktoykasse.key` |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | passordet du valgte |

**Sikkerhetskopier den private nøkkelen og passordet nå**, på minst to ulike steder (passordbehandler og en kryptert kopi utenfor maskinen), helst også hos en annen i LLA.

**Mister du nøkkelen:** da kan ingen eksisterende installasjon oppdatere seg selv til nye versjoner, for de godtar bare signaturer fra den gamle nøkkelen. Du må lage et nytt nøkkelpar, bytte `pubkey`, lage en ny versjon og be alle om å laste ned og installere den manuelt fra nedlastingssiden. Fra den versjonen virker automatisk oppdatering igjen. Lekker nøkkelen, gjelder det samme (og den gamle må regnes som kompromittert).

### 3. Mac: Developer ID og notarisering (påkrevd for å publisere)

Uten signering og notarisering stopper Gatekeeper appen. Arbeidsflyten laster ikke opp en Mac-fil som ikke er signert.

**Åpent spørsmål: hvem eier Apple-kontoen** (LLA som organisasjon, eller en person)? Developer ID-sertifikat kan bare opprettes av kontoens Account Holder. Oppsettet er laget for å være lett å bytte: bytter du konto, lager du nytt sertifikat og ny API-nøkkel og erstatter hemmelighetene under. Oppdateringsnøkkelen (punkt 2) og resten påvirkes ikke. Medlemmer som allerede har appen, får oppdateringen som vanlig.

Sertifikatet:
1. Apple Developer, Certificates, opprett **Developer ID Application** (krever en CSR fra Nøkkelring: Nøkkelringtilgang, Sertifikatassistent, Be om et sertifikat fra en sertifiseringsinstans, lagre til disk).
2. Last ned `.cer`, dobbeltklikk for å legge i Nøkkelring, finn det under «Mine sertifikater», høyreklikk, Eksporter som `.p12` med et passord.
3. Lag base64: `base64 -i sertifikat.p12 | pbcopy`.
4. Signeringsnavnet: `security find-identity -v -p codesigning` gir noe som `Developer ID Application: Landslaget for lokalaviser (ABCDE12345)`. Team-ID er de ti tegnene i parentes.
5. Slett `.p12`-filen fra disken når den er lagt inn, eller lagre den kryptert.

| Navn | Innhold |
|---|---|
| `APPLE_CERTIFICATE` | base64 av `.p12` |
| `APPLE_CERTIFICATE_PASSWORD` | passordet til `.p12` |
| `APPLE_SIGNING_IDENTITY` | hele navnet, f.eks. `Developer ID Application: ... (ABCDE12345)` |
| `APPLE_TEAM_ID` | team-ID |

Notarisering, velg **én** av to måter (API-nøkkel anbefales, den er ikke knyttet til et personlig passord):

- **A. App Store Connect API-nøkkel (anbefalt).** App Store Connect, Users and Access, Integrations, Team Keys, generer en nøkkel med rollen *Developer*. Last ned `.p8` (kan bare lastes ned én gang).

  | Navn | Innhold |
  |---|---|
  | `APPLE_API_ISSUER` | Issuer ID (øverst på siden) |
  | `APPLE_API_KEY` | Key ID |
  | `APPLE_API_KEY_P8` | hele innholdet i `.p8`-filen (inkludert BEGIN/END-linjene) |

- **B. Apple-ID med app-spesifikt passord.** appleid.apple.com, Sign-In and Security, App-Specific Passwords.

  | Navn | Innhold |
  |---|---|
  | `APPLE_ID` | Apple-ID-en (e-post) |
  | `APPLE_PASSWORD` | det app-spesifikke passordet, ikke vanlig passord |

Hva arbeidsflyten gjør: legger sertifikatet i en midlertidig nøkkelring, lar `tauri build` signere (hardened runtime) og notarisere `.app`, signerer og notariserer deretter `.dmg`, stifter (staple) billetten på begge og kjører `spctl` og `stapler validate` som kontroll. Bygget feiler hvis noe av dette ikke går gjennom.

### 4. Windows: kodesignering (avklares; usignert fungerer til da)

Spesifikasjonens åpne spørsmål. Til du har bestemt deg, bygges `.msi` **usignert**, og release-notatene får automatisk en tydelig merknad om at Windows kan vise «Windows beskyttet PCen» og hvordan man går forbi. Dette styres av **variabelen** `WINDOWS_SIGNING`:

| `WINDOWS_SIGNING` (Variables) | Betydning |
|---|---|
| ikke satt, eller `none` | usignert (standard), merknad i release-notatene |
| `certificate` | OV/EV-sertifikat som `.pfx`-fil |
| `trusted-signing` | Azure Trusted Signing (skybasert) |

Settes den til noe annet enn `none`, men hemmelighetene mangler, stopper arbeidsflyten med melding om hva som mangler.

**Valget du må ta** (kort, uten å ha prøvd noen av dem):
- **Azure Trusted Signing:** billig, ingen maskinvarenøkkel, signerer fra skyen i CI. Kontroller først at en norsk organisasjon i dag kan registreres i tjenesten (den har hatt begrensninger på land og organisasjonstype), og at identitetsverifiseringen går gjennom. Tjenesten kan ha skiftet navn; arbeidsflyten bruker kommandolinjeverktøyet `trusted-signing-cli`, som installeres i CI (ikke en avhengighet i appen).
- **OV- eller EV-sertifikat fra en CA:** de fleste CA-er leverer nå sertifikater der den private nøkkelen ligger på maskinvare (token eller skybasert HSM) og **ikke kan eksporteres til en `.pfx`**. Modusen `certificate` virker bare hvis du får en `.pfx` du kan eksportere. Leverer CA-en bare skysignering (f.eks. DigiCert KeyLocker eller SSL.com eSigner), må vi legge til en egen modus med CA-ens verktøy; si fra, det er en liten endring i `tools/lag-byggkonfig.mjs` og `release.yml`.
- Uansett type bygger SmartScreen omdømme over tid. Selv med gyldig signatur kan de første nedlastingene av en ny versjon få advarsel; installasjonsveiledningen på siden forklarer «Mer informasjon, Kjør likevel».

Hemmeligheter og variabler for `certificate`:

| Navn | Innhold |
|---|---|
| `WINDOWS_CERTIFICATE` (secret) | base64 av `.pfx`: i PowerShell `[Convert]::ToBase64String([IO.File]::ReadAllBytes("kode.pfx")) \| Set-Clipboard` |
| `WINDOWS_CERTIFICATE_PASSWORD` (secret) | passordet til `.pfx` |
| `WINDOWS_TIMESTAMP_URL` (variable, valgfri) | tidsstempeltjeneste; standard `http://timestamp.digicert.com` |

For `trusted-signing`: Azure-portalen, opprett Trusted Signing-konto og sertifikatprofil, opprett en app-registrering (service principal) med rollen *Trusted Signing Certificate Profile Signer* på kontoen.

| Navn | Innhold |
|---|---|
| `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (secrets) | fra app-registreringen |
| `AZURE_TS_ENDPOINT` (variable) | f.eks. `https://weu.codesigning.azure.net` (regionen til kontoen) |
| `AZURE_TS_ACCOUNT` (variable) | navnet på signeringskontoen |
| `AZURE_TS_PROFILE` (variable) | navnet på sertifikatprofilen |

Arbeidsflyten kontrollerer med `Get-AuthenticodeSignature` at `.msi` har gyldig signatur når signering er valgt.

### Oversikt over alt

Secrets: `RELEASES_TOKEN`, `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_TEAM_ID`, enten (`APPLE_API_ISSUER`, `APPLE_API_KEY`, `APPLE_API_KEY_P8`) eller (`APPLE_ID`, `APPLE_PASSWORD`), og for Windows etter valg `WINDOWS_CERTIFICATE`, `WINDOWS_CERTIFICATE_PASSWORD` eller `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.

Variables: `WINDOWS_SIGNING` (valgfri), `WINDOWS_TIMESTAMP_URL`, `AZURE_TS_ENDPOINT`, `AZURE_TS_ACCOUNT`, `AZURE_TS_PROFILE`.

## Slik lager du en release

1. **Nytt versjonsnummer:** endre `version` i `src-tauri/tauri.conf.json` (bare der) i en vanlig PR, og merge til `main`. Versjonen må være høyere enn forrige, ellers tilbyr ikke appen oppdateringen.
2. **Testbygg først (anbefalt):** GitHub, Actions, *release*, Run workflow, gren `main`, la «publish» stå av. Det bygger begge plattformer uten opplasting og fyller hurtigbufferen (tagg-bygg kan ikke bruke hurtigbuffer fra andre tagger, bare fra `main`). Filene ligger som artefakter på kjøringen i 14 dager. Uten hemmeligheter er de usignerte og tydelig merket i kjøringens sammendrag. Første kjøring tar lang tid (whisper.cpp bygges); senere kjøringer er mye raskere.
3. **Kjør sjekklisten** `docs/sjekkliste-steg-4.md` (de delene som gjelder).
4. **Tagg og push** fra en oppdatert `main`:
   ```
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```
   Taggen må være `v` + versjonen i `tauri.conf.json`. Passer de ikke, stopper arbeidsflyten før noe bygges.
5. **Vent på arbeidsflyten.** Den stopper tydelig hvis noe av dette mangler: `RELEASES_TOKEN`, oppdateringsnøkkelen, ekte `pubkey` i konfigurasjonen, eller Apple-hemmelighetene. Sammendraget på kjøringen lister hva som mangler.
6. **Kontroller utkastet** i `https://github.com/JohnLLA/lla-verktoykasse-releases/releases`: nøyaktig seks filer finnes (`.dmg`, `.msi`, `.msi.sig`, `.app.tar.gz`, `.app.tar.gz.sig` og `latest.json`), og notatene stemmer. Rediger gjerne notatene (men `notes` i `latest.json` er generisk).
7. **Publiser** ved å trykke «Publish release». Først da får nedlastingssiden og appens oppdatering den nye versjonen. Er det en forhåndsversjon (`v0.2.0-beta.1`), merkes den som pre-release og vises ikke som «siste».
8. **Kontroller:** `https://github.com/JohnLLA/lla-verktoykasse-releases/releases/latest/download/latest.json` viser den nye versjonen, og nedlastingssiden gir riktige knapper.

Rettelser: en publisert versjon endres ikke (arbeidsflyten nekter å skrive over den). Er noe galt, lag en ny versjon. Et utkast kan slettes og taggen kjøres på nytt (slett taggen lokalt og i det private repoet først).

## Oppdatering i appen

- Tauri `updater`-pluginen (godkjent i spesifikasjonen). Ved oppstart spør appen om `latest.json` hvis bryteren «Se etter ny versjon når appen starter» er på (standard). Finnes det en nyere versjon, vises et varsel øverst med «Oppdater nå» og «Senere». Appen laster ned, kontrollerer signaturen mot den innebygde offentlige nøkkelen, installerer og starter på nytt. Er en jobb i gang, spør appen først.
- **Bryteren av:** da kaller ikke appen noe oppdateringskall. Det sjekkes både i grensesnittet og i Rust (`src-tauri/src/updater.rs` nekter å gjøre kallet). Testet i `src/shell/update-check.test.ts`.
- Feil (ingen nett, ugyldig signatur) gir ingen melding ved oppstartssjekken. Feiler selve installasjonen, står det en melding med «Prøv igjen».
- Ikke lagt til: `tauri-plugin-process` eller andre plugins. Omstart skjer med `AppHandle::restart()` i Tauri selv.

### Hvem appen snakker med (nettilgang)

Webvisningen (grensesnittet) har **ingen** nettilgang: CSP `connect-src` tillater bare Tauris interne kanal, og `capabilities/default.json` har ingen `updater`-, `http`-, `fs`- eller `shell`-tillatelser. Alt nettarbeid skjer i Rust. Verter, til sammen:

| Formål | Vert | Når |
|---|---|---|
| Modellnedlasting | `huggingface.co` og `*.hf.co` | bare når brukeren trykker «Last ned» |
| Versjonssjekk: `latest.json` | `github.com` (stien `/JohnLLA/lla-verktoykasse-releases/releases/latest/download/latest.json`), som GitHub videresender til `release-assets.githubusercontent.com` (tidligere `objects.githubusercontent.com`) | ved oppstart, hvis bryteren er på |
| Oppdateringspakke | `github.com` (`/JohnLLA/lla-verktoykasse-releases/releases/download/...`), videresendt til samme `*.githubusercontent.com`-vert | bare etter «Oppdater nå» |

Redaksjoner med brannmur som slipper gjennom utvalgte verter, må altså tillate disse. Begrensninger som er bygget inn utover vertslisten: adressen til `latest.json` ligger fast i `tauri.conf.json`; Rust-koden nekter å laste ned en pakke hvis adressen i `latest.json` ikke er `https://github.com/JohnLLA/lla-verktoykasse-releases/releases/download/...`; og pakken må ha gyldig signatur fra vår nøkkel. Videresendingen til `githubusercontent.com` styres av GitHub og kan ikke låses i CSP (den gjelder bare webvisningen); den er derfor dokumentert her og dekket av signaturkontrollen. Forespørslene inneholder ingen lyd, tekst eller filnavn (reqwest sender standard `User-Agent` og plattformens TLS).

## Byggeinnstillinger (uendret fra appbygget)

- `.cargo/config.toml`: `GGML_NATIVE=OFF`, AVX2/FMA/F16C/BMI2 på, `GGML_AVX512=OFF`, MSVC `/O2` via `src-tauri/cmake/msvc-optimize.cmake`, `MACOSX_DEPLOYMENT_TARGET=13.0`.
- Release-arbeidsflyten gjør samme kontroll av `/O2` på Windows som PR-bygget, og feiler hvis ggml er bygget med AVX-512. AVX2-flagget i `ggml-cpu.vcxproj` gir bare en advarsel hvis det ikke gjenkjennes (denne delen er ikke prøvd på Windows ennå).
- Appen sjekker AVX2 når den kjører og sier fra på eldre PC-er (steg 2).
- Mac: Metal. `minimumSystemVersion` 13.0. Windows: WiX-installasjon (`.msi`), norsk språk.

## Byggeminutter

- Pull request: `app-build` (som før). `release` kjører på PR bare når `release.yml`, `tauri.conf.json` eller release-verktøyene i `tools/` er endret, og bygger da usignert uten opplasting.
- Tagg `v*` og manuell start: fullt bygg. Hurtigbuffer (`actions/cache`) for cargo-register og `src-tauri/target` per OS; nøkkelen følger `Cargo.lock`, `.cargo/config.toml` og `src-tauri/cmake`.

## Tredjepartslisenser

`src/assets/tredjepart.txt` har full lisenstekst for alle komponenter som følger med appen (NB-Whisper, whisper.cpp, Tauri, Symphonia og resten), og vises under Om, «Vis full lisenstekst». Den lages av `tools/lag-tredjepartsmelding.mjs` fra `Cargo.lock` (via `cargo metadata`, for både Mac og Windows) og `node_modules`. Endrer du avhengigheter: kjør `npm run tredjepart` og commit filen. CI feiler (`--check`) hvis den er utdatert.
