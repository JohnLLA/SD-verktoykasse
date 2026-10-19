# Testdata for kvalitetsmåling (steg 3)

Her ligger fasitene og oversikten over testlyden. **Selve lyden ligger ikke i git**
(`testdata/lyd/` står i `.gitignore`). Den hentes på nytt med ett skript som også
sjekker alt mot SHA-256.

All lyd i testsettet er **offentlig, med åpen lisens og med fasit**. Det er ingen
ekte intervjuer og ingen private opptak. Private opptak (intervjuer, telefon) hører
ikke hjemme her. Skal John Inge senere måle på egne klipp med samtykke, legges de i en
privat mappe utenfor repoet, aldri i `testdata/`.

## Hente lyden igjen

Krever Python 3 (bare standardbiblioteket) og at måleprogrammet er bygget
(`maal decode` brukes til å dekode mp3, med samme dekoder som appen):

```sh
cd src-tauri && cargo build --release --features maling --example maal && cd ..
python3 -I tools/maling/hent_testdata.py hent     # laster ned (ca. 0,5 GB) og bygger testdata/lyd/
python3 -I tools/maling/hent_testdata.py sjekk    # sjekker SHA-256 uten å bygge
```

- Kildene (NPSC, FLEURS, NbAiLab-eksemplene) lastes ned til `~/lla-test/kilder`
  (`--cache` endrer det). SHA-256 på hver kildefil står i `klipp.json`; avvik stopper
  skriptet.
- Klippene er 16 kHz mono WAV. SHA-256 på hvert ferdig klipp står i `klipp.json`.
  Avvik gir en advarsel (exit 2 med `--streng`), siden dekoding med flyttall kan gi
  avvik på siste bit mellom CPU-arkitekturer. På Mac (arm64) stemte alle 19 filene ved
  gjenbygging.
- De forringede variantene lages i ren Python med fast frø. Det tar noen sekunder per klipp.

## Hva som er med

NPSC = Norsk talekorpus fra Stortinget (Nasjonalbiblioteket, Språkbanken), via
`NbAiLab/NPSC` på Hugging Face, revisjon `e906435c`. **Lyd og transkripsjoner er CC0.**
Det er taler fra talerstolen i Stortinget, manuelt transkribert av filologer og
korrekturlest. Hvert klipp er sammenhengende setninger fra én taler (setningene limt
sammen med 0,3 s pause). Taler er oppgitt som `speaker_id`; dialekt er ikke merket i
Hugging Face-utgaven, så vi kan ikke gi dialekt per klipp (se «Mangler»).

| Klipp | Målform | Kilde | Lengde | Ord i fasit | Innhold |
|---|---|---|---|---|---|
| `nb-1` | bokmål | NPSC test 20171219, taler 3 | 3:20 | 540 | Stortingstale, bokmål |
| `nb-2` | bokmål | NPSC test 20170207, taler 26 | 2:16 | 309 | Stortingstale, bokmål |
| `nb-3` | bokmål | NPSC eval 20180611, taler 132 | 2:06 | 263 | Stortingstale, bokmål |
| `nb-4` | bokmål | NPSC eval 20180109, taler 289 | 2:05 | 295 | Stortingstale, bokmål |
| `nn-1` | nynorsk | NPSC eval 20170209, taler 36 | 3:14 | 424 | Stortingstale, nynorsk |
| `nn-2` | nynorsk | NPSC test 20171219, taler 92 | 2:14 | 294 | Stortingstale, nynorsk |
| `nn-3` | nynorsk | NPSC eval 20180109, taler 253 | 2:10 | 253 | Stortingstale, nynorsk |
| `nn-4` | nynorsk | NPSC eval 20180611, taler 271 | 2:07 | 363 | Stortingstale, nynorsk |
| `fleurs-nb` | bokmål | FLEURS nb_no test | 4:53 | 551 | 25 opplest setninger, 10 menn og 15 kvinner, ulike opptaksmiljøer |
| `lang-nb-30` | bokmål | NPSC test 20171122, 266 setninger | 31:20 | 4803 | Sammenhengende debatt med mange talere (bare bokmål) |
| `king` | bokmål | NbAiLab/nb-whisper `audio/king.mp3` | 1:25 | – | Kongens tale. Offentlig referanse, ingen fasit |
| `knuthamsun` | bokmål | NbAiLab/nb-whisper `audio/knuthamsun.mp3` | 23:08 | – | Opplesning. Bare til fartsmåling, ingen fasit |

Forringede varianter av `nb-1` og `nn-1` (samme fasit som originalen). **Simulert, ikke
ekte opptak.** De er laget for å se hvordan feilraten endrer seg, ikke for å etterligne
en bestemt telefon eller kafé:

| Klipp | Effekt |
|---|---|
| `nb-1-telefon`, `nn-1-telefon` | Båndbegrenset 300–3400 Hz, 8 kHz, mu-lov 8 bit |
| `nb-1-ekko` | Rom med mye etterklang (Schroeder-romklang, RT60 ca. 1 s, rommet like høyt som stemmen) |
| `nb-1-kafe`, `nn-1-kafe` | Babbel fra fire andre talere (NPSC 20171122), 8 dB over støy |
| `nb-1-bil` | Lavfrekvent rumling (motor), 5 dB over støy |

`stoy-babble` er bare støykilden til kafé-klippene.

### Lisenser og kreditering

- **NPSC:** CC0 1.0 (lyd og transkripsjoner). Solberg & Ortiz (2022), *The Norwegian
  Parliamentary Speech Corpus*, LREC 2022. Hugging Face-utgaven er satt sammen av
  Nasjonalbiblioteket (CC-BY-SA 3.0 på selve datasett-pakken). Fasitfilene i
  `testdata/fasit/` er utdrag av CC0-teksten.
- **FLEURS:** CC BY 4.0, Google. Conneau et al. (2022), *FLEURS: Few-shot Learning
  Evaluation of Universal Representations of Speech*. Fasiten for `fleurs-nb` er
  FLEURS-teksten (rå og normalisert), uendret.
- **King og Knut Hamsun:** ligger i NbAiLab/nb-whisper-repoet (Apache 2.0), men det sier ikke
  noe om rettighetene til selve lydinnholdet (Kongehuset, Nasjonalbiblioteket).
  **Lyden distribueres ikke fra dette repoet**; skriptet henter den fra NbAiLab, og den
  brukes bare lokalt til fart og et kvalitativt sammenlikningsgrunnlag.

## Fasiter

`testdata/fasit/<klipp>.json`, én fil per innholdsklipp (de forringede variantene bruker
fasiten til originalen). Hver setning har:

- `lydrett`: **ordrett** fasit. For NPSC er det `sentence_text` (manuell transkripsjon
  med gjentakelser og avbrutte ord, men med markører som `<ee>`; markørene fjernes ved
  måling). For FLEURS er det den normaliserte teksten.
- `skriftlig`: det nærmeste vi har en «skriftlig» fasit. For NPSC er det `normsentence_text`
  (tall og datoer skrevet med sifre, ellers samme ord som den ordrette). For FLEURS er det
  den rå teksten med stor forbokstav og tegnsetting.
- `maskinoversatt` (bare NPSC): `transsentence_text`, en **maskinoversatt** versjon til
  den andre målformen. Brukes bare som en grov referanse når bokmålstale skal gi nynorsk tekst
  (og omvendt). Den er ikke menneskelig kontrollert og skal ikke leses som en riktig fasit.

**Ingen av fasitene er skrevet av et menneske for «tolket».** NPSC er ordrett
transkripsjon, og FLEURS er opplest skriftspråk. Se «Begrensninger» i `docs/kvalitet.md`.
Stortingets egne referater (som er redigert, skriftlig språk) følger med i den offisielle
NPSC-utgaven fra Språkbanken, men er ikke koblet til setningene her. De er den beste kilden
til en ekte tolket-fasit hvis John Inge vil ha en senere.

Normalisering og regler for måling står i `tools/maling/ordfeil.py` og i `docs/kvalitet.md`.

## Mangler (det Hugging Face-utgaven ikke kan gi)

Original-listen over ønsket testsett var bredere. Disse delene mangler, og kan skaffes
bare av John Inge med samtykke fra de som snakker:

| Mangler | Hvorfor det trengs | Hvem skaffer |
|---|---|---|
| Intervju mellom to personer på telefonmikrofon | Vanligste bruk i redaksjoner | John Inge (med samtykke, privat lagring) |
| Sterk dialekt, merket med område (f.eks. nordnorsk, vestnorsk) | Lydrett mot tolket blir tydeligst her | John Inge, eller NPSC-metadata om talerne fra Språkbanken (store nedlastinger på nb.no) |
| Ekte støy (kafé, bil) og ekte romklang | Simulert støy etterligner ikke alt | John Inge |
| Menneskeskrevet tolket-fasit | Å måle om tolket mister innhold | En person; NPSC-referatene kan være grunnlag |

Slike klipp skal ikke i dette repoet. Bruk en privat mappe og la `maal.py` peke dit
(`testdata/` leses fra repoet; legg egne klipp i `klipp.json` i en lokal kopi).
