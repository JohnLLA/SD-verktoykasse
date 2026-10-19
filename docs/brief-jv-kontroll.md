# Brief til kontraktvokter: PR-er i steg 6 (journalistverktøyene)

Bruk: «bruk kontraktvokter på PR #N med docs/brief-jv-kontroll.md». Dette kommer i tillegg til den vanlige sjekklisten din.

## Sjekk i tillegg

1. **Nett:**
   - Katalogen og pakkene hentes bare når brukeren ber om det. Ingen bakgrunnsnedlasting og ingen sjekk ved oppstart.
   - Forespørslene inneholder ingenting om brukeren eller filene.
   - Kjør hver installerte pakke med nettet sperret og med en lokal lytter. Bruk filnavn som `http:127.0.0.1:<port>.mp4` mot `keyframes`, `loudness` og `ocr`. Ingen tilkobling er lov.
2. **Katalog og pakker:**
   - En katalog med feil eller manglende signatur avvises.
   - En pakke med feil SHA-256 avvises.
   - Et arkiv med `../`, absolutte stier eller symlenker ut av mappa avvises.
   - En avbrutt nedlasting gir ingen halvinstallert pakke.
   - Den gamle versjonen står urørt hvis den nye feiler.
   - Mac: en pakke med ødelagt signatur kjøres ikke.

   Prøv selv med manipulerte filer.
3. **`capabilities`:** bare kjøring gjennom Rust-modulen fra appens datamappe. Ingen `shell:allow-open` og ingen ny nettilgang for webvisningen.
4. **Argumenter:**
   - Rust bygger argumentene fra en hviteliste, aldri med skall.
   - Filstier kommer bare fra dialog eller slipp.
   - Prøv filnavn med mellomrom, æøå og `;`, filnavn som starter med `-`, og `--`.
5. **Logger:** ingen filnavn, filinnhold, treff fra `redact` eller tekst fra verktøyene i logger (regel 2).
6. **Originaler:** SHA-256 er uendret etter hvert verktøy, også når utmappen er samme mappe som filene.
7. **Sladding:**
   - Kjør `redact` gjennom appen (finn → kryss av → sladd) på `sidecar/jv/testdata/redact/`.
   - Kjør også prøvefilene fra kontrollrundene i Verktoy2_0, hvis de er lagt med.
   - Ingen sladdet verdi skal kunne finnes i utfila.
   - Forkastede kandidater skal være tydelig merket i grensesnittet.
8. **Lisenser og hemmeligheter:**
   - Versjon og SHA-256 stemmer med `sidecar/build/binaries.json`.
   - Hver ny avhengighet har fri lisens og står i `THIRD_PARTY_LICENSES.md`. Lisenskontrollen i CI er grønn.
   - Ufri, ukjent eller «ikke-kommersiell» lisens er MÅ FIKSES.
   - Ingen `.p8`-, `.p12`-, `.pem`- eller `.env`-filer, `notarisering/`, persondata eller filer med ukjent opphav i PR-en eller i pakkene.
9. **Python-testene** passerer mot de pakkede binærfilene på begge plattformer i CI.
10. **Grensesnittet:**
    - De ni verktøyene bruker komponentene fra Transkribering.
    - Tilstandene «ikke lastet ned», «laster ned», «feil», «klar» og «kommer» finnes og ser riktige ut i lys og mørk modus.
    - Status i `site/lla-no/verktoy.html` stemmer med det som er publisert.

Gi GODKJENT bare når alle punktene holder.
