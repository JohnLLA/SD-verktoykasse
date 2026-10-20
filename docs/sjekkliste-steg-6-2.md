# Sjekkliste steg 6.2: verktøypakkene for Mac og Rust-modulen `jv`

**Status: ikke kjørt på enhet.** Pakkene er bygget, signert, notarisert og testet på byggemaskinen
(John Inges Mac, macOS 26.6.2). Ingenting her er prøvd på en annen Mac, og skjermbildene finnes
ikke ennå (steg 6.3, `grensesnittbygger`). John Inge kjører listen.

Oppskrift for bygg, katalog og nøkler: `sidecar/build/README.md`.

## Minste macOS (arves fra Homebrew på byggemaskinen)

| Pakke | Minste macOS |
|---|---|
| compare, subtitles, pdf-tables | 11.0 |
| metadata | 15.0 |
| keyframes, loudness, redact, nynorsk | 26.0 |
| ocr | 26.6.2 |

- [ ] På en Mac med macOS 14 eller 15: pakk ut `jv-subtitles-…tar.gz` og `jv-metadata-…tar.gz` med
      `tar -xzf` i en tom mappe og kjør `jv-<id>.app/Contents/MacOS/jv --version`. subtitles skal virke
      på 14 og 15, metadata bare på 15.
- [ ] Samme Mac: `jv-ocr` og `jv-keyframes` skal **ikke** starte (krever 26.x). Noter feilmeldingen.
- [ ] Bestem om dette er godt nok for betaen, eller om pakkene skal bygges på en eldre macOS
      (eller i CI på `macos-14`) før publisering.

## Pakkene fra en ren Mac (uten Homebrew, Python eller utviklerverktøy)

- [ ] For hver av de ni: pakk ut, kjør `--version` med `env -i PATH=/usr/bin:/bin HOME=$HOME`.
      Programmene skal vise `"ok": true`.
- [ ] `spctl -a -t exec -vv jv-<id>.app` sier `accepted` og `source=Notarized Developer ID`.
- [ ] `xcrun stapler validate jv-<id>.app` er OK.
- [ ] Kald start: start Macen på nytt og kjør `--version` på `ocr` én gang. Noter tiden.

## Appen med en lokal betakatalog

Krever at pakkene og en katalog signert med betanøkkelen ligger et sted appen får hente fra. Appen
henter bare fra `github.com/JohnLLA/lla-verktoykasse-releases` (og GitHubs CDN), så dette kan først
prøves når John Inge har lastet opp pakkene og katalogen (agentene laster ikke opp).

- [ ] Bygg appen med `JV_CATALOG_PUBLIC_KEY=<betanøkkelen>`.
- [ ] Ingen nettkall ved oppstart (Little Snitch eller `nettop`): appen kontakter ikke GitHub før et
      verktøy åpnes eller «Se etter oppdateringer» trykkes.
- [ ] Last ned hvert verktøy, kjør det på en fil fra `sidecar/jv/testdata/`, fjern det.
- [ ] Avbryt en nedlasting midtveis, start på nytt: den fortsetter der den slapp.
- [ ] Uten nett: verktøy som er lastet ned, virker; katalogen vises fra siste kopi.
- [ ] Gatekeeper: ingen dialog når et verktøy kjøres. `xattr -l` på
      `~/Library/Application Support/no.lla.verktoykasse/verktoy/<id>/<versjon>/jv-<id>.app/Contents/MacOS/jv`
      viser ingen `com.apple.quarantine`.
- [ ] Endre én byte i en fil inne i en installert pakke: appen nekter å kjøre den (kodesignatur).

## Windows

- [ ] Når skjermbildene finnes (6.3): alle ni verktøyene vises som «Kommer for Windows», uten knapp.
      Logikken er testet i `cargo test` (katalogen har ingen Windows-linjer i runde A).
- [ ] Transkribering virker som før.
