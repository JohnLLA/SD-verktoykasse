# Brief til byggmester: alle avhengigheter til tryggeste versjon (steg 6.5)

Bruk: «bruk byggmester på docs/brief-avhengigheter.md». Les først:
- `CLAUDE.md`
- `docs/spesifikasjon-journalistverktoy.md`
- `sidecar/build/binaries.json`

Gren og PR: `steg-6-5-avhengigheter`. Steget kjøres parallelt med `steg-6-4-sandkasse-mac` (se «Rekkefølge»).

## Utgangspunkt

Auditen 22.10.2026 fant:
- **Rust:** 6 kjente sårbarheter i 4 pakker:
  - `rustls-webpki` 0.103.15, RUSTSEC-2026-0382 → ≥ 0.103.16
  - `webpki-roots` 1.0.9, RUSTSEC-2026-0381 → ≥ 1.0.10
  - `webpki-root-certs` 1.0.9, RUSTSEC-2026-0383 → ≥ 1.0.10
  - `zip` 4.6.1 (via `tauri-plugin-updater`) og 8.6.0 (via `docx-rs`), RUSTSEC-2026-0367, -0368 og -0369 → ≥ 9.0.0
- **Rust, bare på Linux:** 5 varsler (glib, proc-macro-error, zbus_names, zvariant, zvariant_derive). De bygges ikke inn på Mac eller Windows.
- **npm og Python:** ingen kjente sårbarheter.
- **Systemprogrammene** er ikke kontrollert automatisk.

## Prinsipp

«Tryggeste versjon» betyr nyeste stabile versjon uten kjente sårbarheter:
- **Innenfor samme hovedversjon** oppdateres alt.
- **Hovedversjonshopp** tas bare når de retter en kjent sårbarhet. Andre hovedversjonshopp listes i rapporten, så John Inge kan bestemme.
- **Ingen nye avhengigheter** (regel 7). Gjelder også når en ny versjon drar inn nye pakker: si fra før det tas inn.

## Oppgave

1. **Rust (`src-tauri`):**
   - `cargo update`, så `cargo audit`. De tre TLS-pakkene skal være på rettet versjon.
   - **zip:** sjekk om nyeste `tauri-plugin-updater` og `docx-rs` bruker `zip` ≥ 9.0.0.
     - Hvis ja: oppgrader.
     - Hvis nei: legg avviket i `src-tauri/.cargo/audit.toml` (eller `deny.toml`) med begrunnelse og utløpsdato 31.12.2026.
     - Begrunnelsen: updater-pluginen sjekker minisign før utpakking. `docx-rs` pakker aldri ut. Verktøypakkene bruker ikke `zip`, men `archive.rs`.
   - Sett `license = "AGPL-3.0-or-later"` i `Cargo.toml`. Der står det `UNLICENSED` nå.
   - Øk appversjonen til 1.0.2 i `tauri.conf.json`, `Cargo.toml` og `package.json`.
2. **npm:**
   - `npm update` for både appen og byggeverktøyene.
   - `npm audit` skal vise 0.
   - Sjekk at `npm run build`, `npm test` og `npm run test:tools` passerer.
3. **Python (`sidecar/jv`):**
   - `uv lock --upgrade` og `pip-audit` mot alle låste pakker.
   - Alle Python-testene skal passere (583 per nå).
   - Oppdater `sidecar/build/jvpack/windows/pyinstaller-krav.txt` og PyInstaller-versjonen for Mac til nyeste.
   - Python skal være siste 3.12-utgave fra python-build-standalone.
4. **Systemprogrammer, Mac:**
   - `brew update` og `brew upgrade` for alle formlene i `binaries.json`.
   - Bygg pakkene på nytt med `sidecar/build/`, slik at `binaries.json` genereres på nytt.
   - Legg inn commit-ID for x264, som mangler kildesjekksum.
   - Løft exiftool til samme versjon som på Windows eller nyere.
5. **Systemprogrammer, Windows** (`jvpack/windows/sources.py`):
   - Ta nyeste utgave av:
     - ffmpeg (gyan.dev)
     - Tesseract (UB Mannheim)
     - poppler-windows
     - exiftool
   - Hent filene på nytt og sett ny SHA-256.
   - **Apertium:** bruk en utgitt versjon hvis den finnes. Hvis ikke, ta det nyeste nattbygget, speil det til release-repoet som før, og skriv datoen i `binaries.json`.
   - Kjør `jv-windows-pakker.yml` med `workflow_dispatch`.
6. **Systemprogrammene mot kjente sårbarheter:**
   - Lag `sidecar/build/sjekk-sarbarheter.py`. Den leser `binaries.json` og spør OSV (`api.osv.dev`) om hver programversjon.
   - Programmer OSV ikke kjenner (Homebrew-navn uten OSV-økosystem), listes som «ikke kontrollert», med lenke til prosjektets sikkerhetsside.
   - Kjør skriptet og legg resultatet i rapporten.
7. **CI:**
   - Ny arbeidsflyt `.github/workflows/sarbarheter.yml` som kjøres på hver PR og hver mandag:
     - `cargo audit` (eller `cargo deny check advisories`)
     - `npm audit --audit-level=low`
     - `pip-audit` mot `uv.lock`
     - `sjekk-sarbarheter.py`
   - Bygget stopper ved funn som ikke står i unntakslista med begrunnelse og utløpsdato.
   - Lag også lisenskontrollen fra `brief-jv-distribusjon.md` punkt 4 hvis den ikke finnes. Det finnes ingen `deny.toml` i dag.
8. **Nye verktøypakker og katalog:** alle ni pakkene får ny versjon (patch) for Mac og Windows. Den nye `tools.json` lages som utkast. John Inge publiserer (regel 11).

## Rekkefølge med sandkasse-steget

- Begge grenene rører `sidecar/build/`. Hold endringene her til versjoner og kilder, så det ikke kolliderer med profil- og kjørekoden i 6.4.
- **Flettes først.** Steg 6.4 rebases deretter, og Python-testene kjøres gjennom sandkassen med de nye pakkene før 6.4 godkjennes.
- Kontraktvokteren går gjennom PR-en med `docs/brief-jv-kontroll.md`, særlig punkt 8 om lisenser og SHA-256.

## Grenser

- Ingen release og ingen tagger. John Inge publiserer app, pakker og katalog.
- Ikke rør `notarisering/` eller nøkler.
- Ikke endre oppførselen i appen eller verktøyene. Hvis en oppgradering krever kodeendring, gjør den minste endringen og beskriv den i PR-en.
- Begge plattformer i CI (regel 9).

## Rapport

Kort på norsk:
- **Tabell over avhengigheter:** pakke, fra versjon, til versjon og årsak. Gjelder Rust (bare direkte avhengigheter og alle med avvik), npm, Python og systemprogrammer.
- **Auditresultat før og etter**, for alle fire lagene.
- **Unntakslista** med begrunnelse og utløpsdato.
- **Hovedversjonshopp** som ikke er tatt, og hvorfor de kan vente.
- **Testresultat per plattform.**
