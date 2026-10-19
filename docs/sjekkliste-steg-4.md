# Sjekkliste steg 4: distribusjon

**Status: ikke kjørt på enhet.** Ingenting her er prøvd på ekte maskiner, og signering og notarisering er ikke prøvd i det hele tatt (hemmelighetene finnes ikke ennå). John Inge kjører listen. Windows-delen kjøres på en vanlig redaksjons-PC med begrensede rettigheter, ikke på en utviklermaskin.

Oppskrift for hemmeligheter og release: `docs/distribusjon.md`.

## Før release (arbeidsflyten)

- [ ] Alle hemmeligheter og variabler fra `docs/distribusjon.md` er lagt inn. `pubkey` i `src-tauri/tauri.conf.json` er byttet ut.
- [ ] Testbygg fra `main` uten opplasting (Actions, release, Run workflow): begge jobbene grønne, artefaktene `release-macOS` og `release-Windows` finnes.
- [ ] Windows-jobben viser «ggml-cpu: AVX2 påslått» og `MaxSpeed` for ggml-cpu, ggml-base og whisper, og ingen AVX-512-feil. Står det en AVX2-advarsel, les byggeloggen.
- [ ] Mac-jobben: `spctl --assess` og `stapler validate` er grønne for både dmg og app.
- [ ] Windows med signering valgt: steget «Kontroller Windows-signaturen» er grønt.
- [ ] Manglende hemmelighet gir tydelig feil: kjør en manuell start med «publish» på og fjern f.eks. `RELEASES_TOKEN` midlertidig. Arbeidsflyten stopper i planen med en melding som nevner navnet.
- [ ] Taggen `v9.9.9` som ikke stemmer med `tauri.conf.json` stoppes (prøv på en testgren/privat kopi, ikke i hoved-repoet).
- [ ] Utkastet i `JohnLLA/lla-verktoykasse-releases` har nøyaktig: `.dmg`, `-setup.exe`, `-setup.exe.sig`, `.app.tar.gz`, `.app.tar.gz.sig`, `latest.json`. Notatene nevner Windows-merknaden hvis Windows er usignert.
- [ ] Før «Publish»: nedlastingssiden (som bruker `releases/latest`) viser fortsatt forrige versjon. Etter «Publish»: knappene peker på de nye `.dmg` og `-setup.exe`.

## Mac (ren Mac, Apple Silicon, macOS 13 eller nyere, uten utviklerverktøy)

- [ ] Last ned `.dmg` fra nedlastingssiden i Safari. Åpne, dra til Programmer. Første oppstart: macOS spør «er lastet ned fra internett, vil du åpne?». Svar Åpne. **Ingen** melding om «utvikleren kan ikke bekreftes» eller «ødelagt».
- [ ] Terminal: `spctl --assess --type execute -vv "/Applications/LLAs verktøykasse.app"` sier `accepted` og `source=Notarized Developer ID`.
- [ ] Uten nett (Wi-Fi av) første gang etter installasjon: appen starter likevel (stiftet billett).
- [ ] Programmer-mappen: ikon og navn «LLAs verktøykasse». Om-vinduet viser riktig versjon.
- [ ] macOS 13 (eller eldste tilgjengelige): appen starter.
- [ ] Intel-Mac: dmg-en er ikke ment for den; siden sier at Apple Silicon kreves.
- [ ] Avinstallering: dra appen til papirkurven. Innstillinger og modeller ligger igjen i brukerens bibliotek (modellmappen kan slettes under Innstillinger først).

## Windows (vanlig redaksjons-PC, begrensede rettigheter)

- [ ] Last ned `-setup.exe` i Edge. Kjør den **som vanlig bruker uten administratorrettigheter**: ingen UAC-spørsmål, installasjonen havner under brukerens profil. Registrer hva som vises:
  - [ ] Usignert: SmartScreen «Windows beskyttet PCen». «Mer informasjon», «Kjør likevel» virker, og veiledningen på siden stemmer med det du ser.
  - [ ] Signert: Utgiver vises med riktig navn. Ingen advarsel, eller bare en mild en som forsvinner etter hvert.
- [ ] Maskin uten WebView2 (eldre Windows 10): installasjonen henter den selv, og appen starter. Skriv ned om det krever administrator.
- [ ] Appen finnes i Start-menyen. Starter, riktig versjon i Om-vinduet.
- [ ] PC uten AVX2: appen starter og sier tydelig fra (steg 2), krasjer ikke.
- [ ] Installasjon på maskin med Defender og eventuelt annen sikkerhetsprogramvare: ingen blokkering eller falsk alarm.
- [ ] Avinstallering fra Innstillinger, Apper: appen er borte.

## Oppdatering (to versjoner trengs: installer forrige, publiser neste)

- [ ] Installer versjon A (forrige). Publiser versjon B (høyere nummer). Start A med bryteren «Se etter ny versjon når appen starter» på: varselet «Det finnes en ny versjon: B» vises øverst.
- [ ] «Senere» skjuler varselet. Neste oppstart viser det igjen.
- [ ] «Oppdater nå»: meldingen om nedlasting vises, appen starter på nytt som versjon B (Om-vinduet viser B). Innstillinger og nedlastede modeller er beholdt.
- [ ] Mac: oppdateringen virker uten ny Gatekeeper-advarsel. Windows: installasjonsvinduet (passiv modus) kommer og appen starter igjen etterpå.
- [ ] Mens en transkribering kjører: «Oppdater nå» spør først om du vil oppdatere likevel. «Vent» avbryter.
- [ ] Ingen nett: oppstart gir ingen feilmelding og ingen forsinkelse du merker.
- [ ] Feil signatur (valgfritt, krever en bevisst ødelagt testversjon): installasjonen avvises med «Oppdateringen mislyktes».
- [ ] Versjon B er den siste: ingen varsel.

## Se etter ny versjon nå

- [ ] Med den automatiske sjekken **av**: trykk «Se etter ny versjon nå». Teksten «Sjekker …» vises, og så «Du har den nyeste versjonen.» eller varselet øverst hvis en nyere versjon er publisert. Nettverksovervåkning viser kall bare i det øyeblikket du trykker.
- [ ] Uten nett: «Kunne ikke sjekke. Er maskinen på nett?». Ingen krasj.
- [ ] Skjermleser leser opp resultatet.

## Versjonssjekken slått av (ingen nettkall)

- [ ] Slå av «Se etter ny versjon når appen starter» under Innstillinger. Avslutt og start appen på nytt.
- [ ] Med Little Snitch eller Wireshark (Mac) / Resource Monitor eller Wireshark (Windows): **ingen** forbindelser fra appen til `github.com` eller `*.githubusercontent.com` ved oppstart eller etterpå, selv om en ny versjon finnes.
- [ ] Slå på igjen, start på nytt: det kommer ett kall til `github.com` (videresendt til `*.githubusercontent.com`), ingen andre verter.
- [ ] Under modellnedlasting: trafikk bare til `huggingface.co` og `*.hf.co`.
- [ ] Under transkribering: ingen trafikk.

## Om-vinduet

- [ ] «Vis full lisenstekst» åpner teksten (tar et øyeblikk første gang). Den kan rulleres med tastatur og mus. NB-Whisper (Apache License 2.0), whisper.cpp, Tauri og Symphonia står oppført.
- [ ] Ingen nettkall når den åpnes (teksten ligger i appen).

## Nedlastingssiden på mobil (`site/lla-no/verktoy.html`, når John Inge har lagt den ut på lla.no)

- [ ] iPhone og Android: siden er leselig, knappene rekker ikke utenfor skjermen, og Mac- og Windows-knappen vises uten å lete.
- [ ] Mac- og Windows-knappen laster ned riktig fil (.dmg / setup.exe) på en datamaskin. På mobil er det tydelig at filene er for datamaskin.
- [ ] Versjon, størrelse og dato stemmer med siste publiserte release.
- [ ] Rate limit på GitHub API (mange oppfriskninger eller delt nett): siden faller tilbake til GitHub-lenken og forklarer hvilken fil man skal velge.
- [ ] Lys og mørk modus.
- [ ] Mens det bare finnes et utkast (ikke publisert): siden sier «Kommer snart» eller viser forrige versjon, ikke feil.

## Nytt etter dette

Noter funn her eller i en PR og meld fra til John Inge: alt som avviker fra at medlemmet kan installere og oppdatere uten hjelp.
