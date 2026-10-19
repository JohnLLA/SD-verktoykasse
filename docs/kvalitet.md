# Kvalitet og fart (steg 3)

Målt 19. oktober 2026 på en MacBook Pro med Apple M5 Max (6 + 12 kjerner, 36 GB, macOS 26.6.2, Metal),
gjennom appens egen kjerne (`run_job` i `src-tauri/src/tools/transkribering/engine.rs`: samme dekoding, samme
biter på 10 minutter, samme innstillinger fra `models.json`, beam 5 som standard, 6 tråder).
Basis: `main` ved `4f18fb2`. 549 kjøringer. Alle tall i tabellene under er hentet fra
`rapporter/kvalitet-2026-10-19-tall.json`; flere tabeller står i `rapporter/kvalitet-2026-10-19.md`.

## Kort fortalt

| # | Spørsmål | Anbefaling |
|---|---|---|
| 1 | Tolket: semantic (`NbAiLabBeta`) eller hovedmodellen (`NbAiLab`)? | **Hovedmodellen**, men bare sammen med tidsstempel-innstillingene fra verbatim. Uten dem blir segmentene 30 sekunder lange. |
| 2 | Beam 5 eller greedy? | **Beam 5 som standard.** Greedy er verken raskere eller bedre for lydrett. For tolket er greedy ca. 1,6 ganger raskere uten nevneverdig tap på bokmål (og et lite tap på nynorsk); det er et mulig Windows-grep, ikke en Mac-innstilling. |
| 3 | Størrelse? | **Medium er riktig «Anbefalt».** Large er ikke målbart bedre på dette testsettet, men 1,5–1,7 ganger tregere og ca. 1,7 ganger så stor i minnet. Small er 1–5 prosentpoeng dårligere og 2–3 ganger raskere. Ytelsesmålet på M1 kan ikke avgjøres her (se under), og lydrett er den risikable kombinasjonen. |
| 4 | Lydrett nynorsk | Nynorsk tale gir nynorsk tekst (0,1 % bokmålsformer). **Bokmålstale som skal bli nynorsk** får bokmålsformer: 9,6 % av formene på lista i lydrett (2,7 % small, **22 % medium**, 3,8 % large), mot 4,6–4,9 % i tolket. |

Det viktigste funnet er ikke på noen av de fire punktene: **alle modellene hopper av og til over hele setninger**
(også hovedmodellen og large). Se «Hoppet innhold». Det er den største kilden til feil for journalister som skal sitere.

## Metode

### Testsett

Bare offentlig lyd med åpen lisens og fasit; ingen ekte intervjuer. Kilder, lisens, varighet og innhold står i
`testdata/README.md`. Kort: 8 klipp fra Stortinget (NPSC, CC0), 4 bokmål og 4 nynorsk, 2–3 minutter hver, ulike
talere; 25 opplest setninger fra FLEURS (bokmål, 10 menn og 15 kvinner, CC BY 4.0); 6 forringede varianter
(telefon, ekko, kafé, bil) laget av to av klippene; et langt klipp på 31 minutter fra Stortinget (bokmål); og
NbAiLabs eksempler `king.mp3` og `knuthamsun.mp3` (23 min opplesning, bare til fart). Lyden ligger i
`testdata/lyd/` (ikke i git) og hentes igjen med `tools/maling/hent_testdata.py`, som sjekker SHA-256.

### Kombinasjoner

Alle klipp ble kjørt med begge målformer (`no` og `nn`), tre modellvarianter (verbatim, semantic, hovedmodell), tre
størrelser (small, medium, large, alle q5_0) og to dekodinger (beam 5, greedy). Unntak: forringede klipp bare i egen målform og
beam 5; det lange klippet bare bokmål (large bare beam 5). I tillegg: tidsstempel-innstillingene fra verbatim på semantic og
hovedmodellen (medium, beam 5), og fartsmåling på Hamsun (23 min) i alle kombinasjoner.

### Fasit per stil

- **Lydrett** måles mot den **ordrette** fasiten (`sentence_text` i NPSC; transkribert av filologer, med gjentakelser og
  avbrutte ord).
- **Tolket** måles mot `normsentence_text` (samme ord, tall og datoer som sifre) og, for sammenlikning, også mot den ordrette
  fasiten. **Det finnes ingen menneskeskrevet «tolket»-fasit**: NPSC er ordrett, og FLEURS er opplest skrift. WER for tolket
  måler derfor «hvor langt unna ordrett tale», ikke «hvor riktig skriftlig språk». En modell som med rette stryker «eh» og
  «president» straffes. Dette er en begrensning ved tallene i spørsmål 1.
- **Nynorsk fra bokmålstale** (og omvendt) har bare NPSCs maskinoversatte fasit. Den er ikke kontrollert av et menneske,
  og brukes bare som grov referanse. For målformen ser vi i stedet på andelen bokmålsformer.

### Normalisering (bare for målingen)

Ligger i `tools/maling/ordfeil.py`. Unicode NFC; markører som `<ee>`, `<qq>`, `<INAUDIBLE>` og `*` fjernes fra fasiten; små
bokstaver; alt som ikke er bokstav eller siffer blir mellomrom (tegnsetting, bindestrek, prosent); mellomrom slås sammen.
**Ikke gjort:** tall til ord, skrivemåter (sjøl/selv), sammensetninger. Disse teller som feil. Appens tekst endres ikke.
For FLEURS er det også en «streng» WER mot den rå teksten (store bokstaver og tegnsetting teller).

### Hva som telles

- **WER** = (erstattede + manglende + ekstra ord) / ord i fasiten. Samlet over klippene (ikke snitt av prosenter).
  **CER** på normalisert tekst.
- **Hopp**: løp på minst 5 fasitord på rad som mangler helt. **Hoppet setning**: fasitsetning på minst 4 ord der minst 80 %
  av ordene mangler. **Lang innsetting**: minst 8 ekstra ord på rad (gjentakelser og hallusinasjon).
- **Bokmålsandel** i nynorsk utdata: bokmålsmarkører / (bokmåls- + nynorskmarkører), med en håndskrevet liste på ca. 70
  entydige former (`tools/maling/malform.py`). Det er et **anslag nedenfra**: bokmålsformer som ikke står på lista (for
  eksempel «tilbudet», «betydelig», «bekymringer») telles ikke. Kontroll: nynorsk-fasiten har 0,0 % bokmålsmarkører
  (64 markører), bokmål-fasiten 99,0 %.
- **Fart** = lydlengde / tid for hele `run_job` (dekoding, lasting av modell og transkribering). **Toppminne** = `ru_maxrss`
  for hele prosessen.

### Usikkerhet og begrensninger

1. **Små tall.** Hver celle i tabellene har 4 klipp og 1 300–1 400 ord. Avhengig av hvilke setninger som hoppes over, svinger
   en celle med flere prosentpoeng. Eksempler: lydrett bokmål greedy går 9,0 % (small), 6,6 % (medium), 11,3 % (large); semantic
   på ett og samme klipp (nb-1) går 9,2 %, 23,3 %, 24,2 % fra small til large. **Forskjeller under 3–4 prosentpoeng mellom to celler
   skal ikke tolkes.** Jeg lener meg derfor på samlede tall og på mønstre som går igjen i mange celler.
2. **NPSC er trolig med i treningsdataene til NB-Whisper** (modellkortet nevner NbAiLab/NPSC og NST). Feilratene kan være lavere
   enn på ukjent tale. Testsplitten (test/eval) er NPSCs egen, men jeg vet ikke om NbAiLab har holdt den utenfor.
3. **Klippene er limt sammen** av enkeltsetninger (0,3 s pause) fra ulike steder i et opptak. Det gir brå overganger som kan
   trigge hopp og tregere dekoding, og setningsgrensene i NPSC kan kutte et ord i kantene. Hamsun-filen (sammenhengende lyd) er
   derfor brukt som primær fartskilde, og det limte klippet på 31 minutter som stresstest.
4. **Dialekt er ikke merket** i Hugging Face-utgaven. Åtte ulike talere gir spredning, men jeg kan ikke si «nordnorsk» eller
   «vestnorsk». NPSC-fasiten bruker talerens egne former («heile», «sjøl», «teke»), og det gir feil for modeller som normaliserer.
5. **Nynorsk-fasiten har egenheter** som presser WER opp: nn-1 stavet «tunell-» (modellene skriver «tunnel-»; 12 av ca. 110 feil
   i en kjøring) og tall som ord («einogførti» mot «41»). Uten nn-1 er lydrett nynorsk beam 5 11,2 % mot 15,3 % med.
6. **Forringet lyd er simulert** (ren Python, fast frø). Den etterligner ikke en bestemt telefon eller kafé.
7. **Fart ble målt mens skrivebordet var i bruk** (WindowServer drar GPU). Regn med ±20 %. De første kvalitetskjøringene ble
   kjørt tre om gangen; fartstallene i denne rapporten kommer bare fra enkeltkjøringer.
8. **Fartstallene gjelder M5 Max**, ikke en M1 og ikke en Windows-PC.

## Resultater

### Ordfeilrate (samlet, NPSC-klippene i egen målform)

Lydrett mot ordrett fasit, tolket mot normalisert fasit. Bokmål: 4 klipp, 1 395 ord. Nynorsk: 4 klipp, 1 297 ord.

**Beam 5**

| Målform | Modell | small | medium | large | alle tre |
|---|---|---:|---:|---:|---:|
| bokmål | lydrett (verbatim) | 5,9 % | 4,3 % | 4,6 % | 4,9 % |
| bokmål | tolket, semantic (Beta) | 14,3 % | 16,3 % | 17,8 % | 16,1 % |
| bokmål | tolket, hovedmodell | 14,3 % | 9,5 % | 11,9 % | 11,9 % |
| nynorsk | lydrett (verbatim) | 15,6 % | 15,0 % | 15,4 % | 15,3 % |
| nynorsk | tolket, semantic (Beta) | 20,6 % | 21,7 % | 18,9 % | 20,4 % |
| nynorsk | tolket, hovedmodell | 22,0 % | 19,8 % | 19,0 % | 20,3 % |

**Greedy**

| Målform | Modell | small | medium | large | alle tre |
|---|---|---:|---:|---:|---:|
| bokmål | lydrett (verbatim) | 9,0 % | 6,6 % | 11,3 % | 9,0 % |
| bokmål | tolket, semantic (Beta) | 20,5 % | 12,8 % | 15,0 % | 16,1 % |
| bokmål | tolket, hovedmodell | 14,0 % | 10,4 % | 12,3 % | 12,2 % |
| nynorsk | lydrett (verbatim) | 25,2 % | 20,8 % | 22,9 % | 23,0 % |
| nynorsk | tolket, semantic (Beta) | 32,9 % | 31,9 % | 20,4 % | 28,4 % |
| nynorsk | tolket, hovedmodell | 22,8 % | 20,9 % | 21,2 % | 21,6 % |

Tegnfeilrate (CER) følger samme mønster (bokmål lydrett medium beam 5: 2,3 %; hovedmodell: 6,2 %; semantic: 12,2 %).
FLEURS (bokmål, opplest): lydrett 18,1 % (medium), 11,3 % (large); semantic 37,7 % (medium), 17,1 % (large); hovedmodell
18,7 % (medium), 23,9 % (large). Her er hele utterances borte i noen kjøringer, se under.

### 1. Tolket: semantic eller hovedmodellen?

Det jeg har målt:

- **Feilrate.** Hovedmodellen er best i 31 av 48 parvise sammenlikninger (samme klipp, størrelse og dekoding), semantic i 10, 7 er
  like. Gjennomsnittlig forskjell er 3,6 prosentpoeng i hovedmodellens favør (bokmål 3,9, nynorsk 3,3). Størst forskjell med greedy
  på nynorsk (semantic 28,4 % mot 21,6 %).
- **Innhold som forsvinner.** Telt som ord i lydrett-utdata som mangler i tolket-utdata (medium, beam 5, NPSC): semantic mister
  **10,7 %** på bokmål og 5,9 % på nynorsk, hovedmodellen **4,7 %** og 5,9 %. På Hamsun (uten fasit, beam 5) skriver semantic 10–21 % færre
  ord enn lydrett (small 21 %, medium 10 %, large 13 %), hovedmodellen 2–6 % færre. Det som strykes er mest «og», «så», «jo» og
  tiltaleordet «president». Men semantic stryker også innhold: «Levealder og helse er i dag *avhengig* av utdanningsnivå» ble til
  «er i dag av utdanningsnivå» (begge modellene gjør den feilen).
- **Hopp.** Samlet over 6 kjøringer per modell og målform: bokmål hoppet semantic over 20 av 540 setninger (5,9 % av ordene
  borte i hopp), hovedmodellen 17 av 540 (4,3 %), lydrett 9 av 540 (2,8 %). Nynorsk: semantic 3 av 378, hovedmodell 1 av 378,
  lydrett 10 av 378. Spikens observasjon (medium semantic hopper over hele setninger) stemmer på bokmål: **7 av 90 setninger,
  10,1 % av ordene, med medium + beam 5**; hovedmodellen hoppet over 1 av 90 samme sted. På det lange klippet er det omtrent likt
  (medium beam 5: 11 av 266 mot 10 av 266). Altså er hopp *ikke* et argument som alene skiller de to modellene; det er et problem
  hos alle.
- **Lesbarhet.** Begge tolket-modellene gir stor forbokstav, punktum og komma, og stryker fyllord. Lydrett gir små bokstaver uten
  tegnsetting. Samme avsnitt, nb-2, medium, beam 5:

  > **lydrett:** … noen fungerer godt og selvstendig i skole og arbeid fritidsaktiviteter men andre annen diagnose vil ha behov for
  > tilrettelegging og oppfølging gjennom heile livet familier som har barn med autisme forteller ofte om krevende hverdager …
  >
  > **semantic:** … Noen fungerer godt og selvstendig i skole, arbeid og fritidsaktiviteter, mens andre – med samme diagnose – vil ha
  > behov for tilrettelegging og oppfølging gjennom hele livet. Familier som har barn med autisme, forteller ofte om krevende hverdager. …
  >
  > **hovedmodell:** … Noen fungerer godt og selvstendig i skole, arbeid og fritidsaktiviteter, men andre samme diagnose vil ha behov
  > for tilrettelegging og oppfølging gjennom hele livet. Familier som har barn med autisme, forteller ofte om krevende hverdager. …

  Tolket er klart lettere å lese. Her fikk semantic med «med» i «andre – med samme diagnose», som hovedmodellen mistet. Men semantic skriver oftere om og korter,
  og det er lett å overse for en journalist som siterer. Begge kan miste ord.
- **Tidskoder (viktig).** Med dagens innstillinger i `models.json` (`variant_options.main = {}`) gir hovedmodellen segmenter på 30
  sekunder: median 30,0 s og 34 % over 15 s, mot median 8,6 s for semantic (18,5 % over 15 s). Segmentene er hele 30-sekundersvinduer,
  så «klikk på segment» og srt/vtt blir ubrukelige. Med verbatim sine innstillinger (`token_timestamps`, `max_len 60`,
  `split_on_word`) blir median 4,1 s og lengste 15 s, og **teksten og feilraten er uendret** (identiske WER i tabellen under).

  | Modell | Segmenter | Median | Lengste | Over 15 s | Null lengde |
  |---|---:|---:|---:|---:|---:|
  | lydrett (verbatim) | 673 | 4,3 s | 24 s | 0,7 % | 26 |
  | semantic | 232 | 8,6 s | 30 s | 18,5 % | 0 |
  | hovedmodell | 190 | 30,0 s | 30 s | 34,2 % | 0 |
  | semantic + tidsstempler | 724 | 4,0 s | 14 s | 0,0 % | 2 |
  | hovedmodell + tidsstempler | 699 | 4,1 s | 15 s | 0,1 % | 15 |

  (Medium, beam 5, alle rene klipp, begge målformer.)
- **Fart.** Samme for begge: medium beam 5 på Hamsun 28,2× (semantic) mot 26,9× (hovedmodell); small 67× mot 58×; large 19,0× mot
  18,6×. Hovedmodellen med tidsstempler er like rask som uten (28,1× mot 28,6× på 400 s Hamsun).
- **Kilde og vedlikehold.** Semantic finnes bare som release candidate fra desember 2023 i `NbAiLabBeta` (spiken). Hovedmodellen er
  den offisielle, mest nedlastede og vedlikeholdte, i samme repo som lydrett-modellene.

**Anbefaling:** bytt «tolket» til **hovedmodellen** (`style_to_variant.tolket = "main"`) og gi `variant_options.main` de samme
tidsstempel-innstillingene som verbatim. Begrunnelse: lavere feilrate (3,6 poeng), betydelig mindre ord som strykes (4,7 mot 10,7 %
på bokmål), samme fart, offisiell modell. Usikkerheten er stor (se begrensningene), og hopp rammer begge modeller. Hvis John Inge
likevel vil beholde semantic fordi den er «mer referat», er det et valg om stil, ikke om presisjon.
**Test i tillegg før lansering** at «klikk på segment» og srt/vtt ser riktige ut med hovedmodellen (15 segmenter av 699 har null
lengde, nesten alle helt på slutten av filen, se «Funn i appen»).

### 2. Beam 5 eller greedy?

| | Beam 5 | Greedy |
|---|---|---|
| WER lydrett bokmål / nynorsk (alle tre størrelser) | **4,9 % / 15,3 %** | 9,0 % / 23,0 % |
| WER tolket hovedmodell bokmål / nynorsk | 11,9 % / 20,3 % | 12,2 % / 21,6 % |
| WER tolket semantic bokmål / nynorsk | 16,1 % / 20,4 % | 16,1 % / 28,4 % |
| Fart Hamsun, medium, hovedmodell | 26,9× | 44,0× |
| Fart Hamsun, medium, **lydrett** | **7,1×** | **6,1×** |
| Fart stresstest, medium, lydrett | 4,9× | **1,9×** |

- **Lydrett: beam 5 er bedre og ikke tregere.** Greedy gir nesten dobbelt så mange feil, og er ikke raskere (verbatim-modellene
  prøver på nytt med høyere temperatur når en kjøring ikke består kvalitetssjekkene, og med greedy skjer det oftere). Greedy for
  lydrett bør ikke tilbys.
- **Tolket: greedy er ca. 1,6 ganger raskere** (medium Hamsun 44× mot 27×), med omtrent samme feilrate på bokmål (12,2 mot 11,9 %) og
  1,3 poeng verre på nynorsk. På en svak PC er det et rimelig valg. På Mac er det ingen grunn til å bruke det.
- Sett bort fra dette er forskjellene mellom celler små i forhold til støyen.

**Anbefaling:** beam 5 som standard på begge plattformer og for begge stiler. Greedy er bare aktuelt som reserve for *tolket* på
en Windows-PC som ikke ellers klarer målet. (Appen har allerede innstillingen `decoding`.)

### 3. Størrelse, fart og ytelsesmålet

**Fart og minne** (Metal, M5 Max, beam 5, sammenhengende lyd = Hamsun 23 min; «per 30 min» er regnet om):

| Modell | Størrelse | Fart | Tid per 30 min | Toppminne |
|---|---|---:|---:|---:|
| tolket (hovedmodell) | small | 58× | 0,5 min | 603 MB |
| tolket (hovedmodell) | medium | 27× | 1,1 min | 1 263 MB |
| tolket (hovedmodell) | large | 18,6× | 1,6 min | 2 109 MB |
| lydrett (verbatim) | small | 20× | 1,5 min | 653 MB |
| lydrett (verbatim) | medium | **7,1×** | **4,2 min** | 1 297 MB |
| lydrett (verbatim) | large | 4,1× | 7,2 min | 2 158 MB |

**Stresstest** (31 min tett Stortingstale limt sammen, 266 overganger): alt blir 2–5 ganger tregere. Medium beam 5: tolket
(hovedmodell) 5,9× = 5,1 min per 30 min; semantic 8,0× = 3,8 min; **lydrett 4,9× = 6,2 min**; large lydrett 2,8× = 10,9 min.
Et ekte intervju ligger et sted mellom Hamsun og stresstesten. Største toppminne i alle 549 kjøringer var 2,6 GB (large, CPU).

**Kvalitet per størrelse** (beam 5, samlet, se tabellen over): medium er best eller likeverdig i nesten alle rader.
Large er ikke bedre enn medium for bokmål (lydrett 4,6 mot 4,3 %; hovedmodell 11,9 mot 9,5 %) og bare litt bedre for nynorsk
(hovedmodell 19,0 mot 19,8 %; lydrett 15,4 mot 15,0 %). Small er 1,6 poeng dårligere i lydrett bokmål (5,9 mot 4,3 %), 4,8 poeng
dårligere i tolket bokmål (14,3 mot 9,5 %) og 0,6–2,2 poeng dårligere på nynorsk. På FLEURS er large klart bedre (lydrett 11,3 mot
18,1 %), men der er hoppene dominerende, og det er bare 551 ord.

**Anbefaling:** behold medium som «Anbefalt». «Best» (large) er ikke begrunnet med denne målingen: 1,5–1,7 ganger tregere
og 1,7 ganger så mye minne uten målbar gevinst. Det kan ligge en gevinst på dårlig lyd (large var best på kafé-klippet for lydrett: 4,9 % mot
16–18 % for small og medium), men det er ett klipp. Hold «Best» som valg, men ikke som en lovnad.

**Ytelsesmålene i spesifikasjonen**

*Mac, under 10 minutter for 30 minutter med «Anbefalt» på M1.* **Kan ikke avgjøres her; M5 Max er ikke M1.** M5 Max har 40
GPU-kjerner og minnebåndbredde på rundt 600 GB/s; M1 har 8 kjerner og 68 GB/s. Som grovt anslag (ikke målt) er M1 5–10 ganger
tregere. Da blir medium beam 5 for 30 minutter:

| | M5 Max, målt | M1, anslag (5–10×) |
|---|---|---|
| tolket, Hamsun | 1,1 min | 5–11 min |
| tolket, stresstest | 5,1 min | 25–51 min |
| lydrett, Hamsun | 4,2 min | 21–42 min |
| lydrett, stresstest | 6,2 min | 31–62 min |

Tolket på sammenhengende lyd havner på kanten av målet; **lydrett med medium og beam 5 holder neppe målet på M1**, og det er
verbatim-modellenes gjentatte forsøk (fallback) som koster, ikke størrelsen: tolket og lydrett har like stor modell, men lydrett
er 4 ganger tregere. Dette må måles på en ekte M1 (sjekklisten for steg 1 har punktet). Før det er avklart bør man ikke love «under
10 minutter» for lydrett.

*Windows uten GPU, under 30 minutter for 30 minutter.* **Ikke målt** (ingen Windows-PC). Som øvre grense for CPU-banen: M5 Max
sin CPU (Accelerate, 6 tråder, ikke AVX2) gjør medium beam 5 på Hamsun i 8,5× (tolket) og 3,1× (lydrett), altså 3,5 og 9,7 minutter
per 30. En AVX2-laptop med 4–8 kjerner er trolig 3–6 ganger tregere per kjerne, som gir omtrent 1,4–2,8× (tolket) og 0,5–1,0×
(lydrett) på sammenhengende lyd, og 0,6–1,2× for tett tale i stresstesten (tolket 3,6× på M5 CPU). Altså: **tolket medium holder trolig
målet på sammenhengende lyd, lydrett medium er på kanten eller under, og tett tale er verre.** Oppskriften for å måle dette på en
vanlig PC står i `docs/kvalitet-windows.md` (ikke kjørt på enhet). Kommer medium under 1,0×, er «Rask» (small: 11–22× på M5 CPU) den
tryggeste standarden på Windows, slik spesifikasjonen allerede sier.

### 4. Lydrett nynorsk: hvor mye bokmål?

Andel bokmålsformer av alle kjente markører (lavere er bedre; markørlista er et anslag nedenfra):

**Nynorsk tale (nn-1…4) med `nn` som målform: ingen lekkasje.** 1 av 1 140 markører (0,1 %) i alle 36 kjøringer. I lydrett
er det 0 av 366. Tolket er like rent.

**Bokmålstale (nb-1…4) som skal bli nynorsk (`nn`)**, samlet over begge dekodinger:

| | small | medium | large | alle |
|---|---:|---:|---:|---:|
| lydrett | 2,7 % (6/214) | **22,2 % (48/168)** | 3,8 % (8/205) | **9,6 %** |
| tolket, semantic | 0,4 % (1/240) | 13,6 % (31/197) | 0,0 % (0/222) | 4,6 % |
| tolket, hovedmodell | 2,1 % (5/230) | 11,6 % (25/191) | 1,4 % (3/214) | 4,9 % |

- **Lydrett lekker mest, og medium lekker mest.** Medium (som er «Anbefalt») har ca. 22 % bokmålsformer i lydrett
  nynorsk fra bokmålstale; spriket mellom klippene er stort (nb-3: 3 %, nb-2: 16 %, nb-1: 28 %, nb-4: 31 %). Det er stabilt for
  beam 5 og greedy (21,1 og 23,4 %), så det er ikke tilfeldig sampling.
- Eksempler, medium lydrett nynorsk: «**kommer** i møte», «kan **være** krevjande», «mange har **bekymringer**», «tilbudet varierer
  **betydelig**» midt i ellers nynorske setninger, og i andre klipp «**hva**», «**mye**», «**hvor**», «**noen**», «**gjøre**».
  Small og large får det mye bedre til, men ikke helt rent (noen få former per klipp).
- Spikens eksempler («hjem» og «trøndere» i small lydrett) stemmer med at lekkasje finnes, men 2,7 % i small er lavt.
- **Motsatt vei:** med `no` (bokmål) på nynorsk tale får man ikke alltid bokmål. Andelen bokmålsformer er bare 48–98 %
  (medium hovedmodell 48 %, small 98 %; lydrett 80–93 %). Whisper følger delvis talerens målform selv om språkkoden er `no`.
  Brukeren som velger «Bokmål» på en nynorsktalende kilde får altså en blanding.
- Bokmålsformene sniker seg inn i begge stiler. Tolket lekker omtrent halvparten så mye som lydrett.

**Anbefaling:** ingenting må endres i appen for nynorsk tale. For bokmålstale som skal bli nynorsk bør appen ikke love ren nynorsk
(si det til brukeren: «kontroller formene»). Hvis John Inge ønsker å gjøre noe aktivt, er det en etterbehandling av tekst
(bokmål til nynorsk-ordliste), men det rører regel 4 om lydrett og er utenfor dette steget. Se også «Beslutninger».

### Hoppet innhold (felles for alle punktene)

Samlet over 30 kjøringer for bokmål (NPSC + FLEURS) og 24 for nynorsk, alle størrelser og begge dekodinger:

| Målform | Modell | Hoppede setninger | Ord borte i hopp | Lange innsettinger | WER mot ordrett |
|---|---|---:|---:|---:|---:|
| bokmål | lydrett | 9 av 540 | 2,8 % | 2 | 10,3 % |
| bokmål | semantic | 20 av 540 | 5,9 % | 19 | 19,8 % |
| bokmål | hovedmodell | 17 av 540 | 4,3 % | 3 | 14,6 % |
| nynorsk | lydrett | 10 av 378 | 4,6 % | 2 | 19,2 % |
| nynorsk | semantic | 3 av 378 | 2,1 % | 7 | 25,9 % |
| nynorsk | hovedmodell | 1 av 378 | 0,9 % | 0 | 22,5 % |

Når hoppede passasjer trekkes fra, blir kurvene mer ordnede (lydrett bokmål beam 5: small 5,4, medium 3,9, large 4,6 %), men det
fjerner ikke forskjellen mellom modellene. Eksempler på hele setninger som ikke kom med:

- FLEURS, hovedmodell large, beam 5: «Dersom du skal over Nord-Østersjøen på vinterstid bør du kontrollere hyttens beliggenhet …»
  (29 ord) og «Han satte ikke tall for kuttene, og sa at disse ville bli foretatt basert på Kinas økonomiske produksjon.» (18 ord).
- FLEURS, semantic medium, beam 5: «Så mye som 20 prosent av vannet som renner ut fra elevene på jorda og ut i havet kommer fra
  Amazonas.» (21 ord).
- NPSC nb-2, lydrett large greedy: «familier som har barn med autisme forteller ofte om krevende hverdager» (9 av 11 ord borte).
- NPSC nb-1, lydrett large greedy: 8 sekunder borte midt i en tale (23 av 39 ord i setningen «dårlig integrering … forskjellen på en
  norsk gutt med røtter i Porsgrunn og en norsk gutt med røtter i Mogadishu …»), og et sted en hallusinert setning («fight for
  otterhus som drar inn babyarbeiderne»).

Lydrett bokmål large greedy er et uttalt dårlig punkt: 5 av 90 setninger hoppet, 8,2 % av ordene borte, WER 11,3 % (mot 4,6 % med
beam 5) og 29,3 % på FLEURS. **Large med greedy bør ikke brukes til lydrett.**

### Dårlig lydkvalitet (simulert)

Én tale (nb-1, 200 s) i fem varianter, beam 5, WER mot fasit:

| Klipp | lydrett small | medium | large | hovedmodell small | medium | large |
|---|---:|---:|---:|---:|---:|---:|
| ren | 3,9 % | 3,0 % | 3,6 % | 10,7 % | 7,5 % | 9,4 % |
| telefon | 6,0 % | 3,8 % | 4,5 % | 15,0 % | 23,7 % | 9,4 % |
| ekko | 4,7 % | 5,1 % | 4,9 % | 14,5 % | 9,2 % | 6,8 % |
| kafé (4 talere, 8 dB) | **16,0 %** | **17,9 %** | 4,9 % | 13,3 % | 11,1 % | 13,0 % |
| bil (5 dB) | 7,0 % | 3,9 % | 4,1 % | 11,5 % | 10,3 % | 7,5 % |

- **Lydrett tåler telefon, ekko og bilstøy godt** (opptil ca. 3 poeng dårligere). Babbel fra flere talere er verre: small og
  medium blander inn de andre talerne, mens large klarer det (4,9 %). Det er ett klipp.
- Tolket hopper så mye på de rene klippene at forringelsene drukner i støyen (telefon medium 23,7 % er et hopp, ikke telefonen).
- Nynorsk (nn-1) følger samme mønster: kafé gir +10 poeng (lydrett 32–34 % mot 21–28 % rent). Alle nynorske tall er høye fordi
  nn-1 er et vanskelig klipp (se begrensninger).

### Typiske feil

Lydrett bokmål, medium, beam 5 (alle fire klipp; bare ett eksempel hver): endelser («utfordring»/«utfordringene», «føle»/«føler»),
små ord («og», «det», «om» slettes), egennavn («Annette Drangsholt» → «Anette Dangsholt»), «f eks» → «f» «eks», og forkortelser.
Lydrett nynorsk: «tunnel»-skrivemåte (fasiten), tall som sifre mot ord (nn: «41» mot «einogførti», «km» mot «kilometer»), infinitiv
(«avgjere» mot «avgjera»), og talerens dialektform («tilløpa» → «tidlegare»). Tolket: som lydrett, pluss fjernede fyllord, og
flytting av ord rundt tegnsetting.

## Funn i appen (ikke rettet, bare rapportert)

1. **Hovedmodellen får 30-sekunders segmenter** med nåværende `variant_options` (se punkt 1). Gjelder hvis «tolket» byttes til main.
2. **Siste segmenter i lydrett får null lengde.** I 94 av 126 lydrett-kjøringer på de korte klippene (alle 24 med medium og beam 5; 38 av 968
   segmenter) har det siste segmentet (ofte de to siste) `start = slutt =` filens slutt, selv om teksten er riktig (eksempel: nb-2, to segmenter som begge står på 135,9 s; 5 slike
   i det lange klippet, der noen ligger mellom biter). Whisper gir tider utenfor lyden for det siste vinduet, og klemmingen til
   lydlengden (`place_segment`) gir 0 ms. Gir null varighet i srt/vtt og ingen avspilling fra disse segmentene.
3. **Verbatim er 4–5 ganger tregere enn de andre variantene** med samme størrelse (Hamsun, medium, beam 5: 195 s mot 49–52 s).
   Det skyldes modellen, ikke tidsstempel-innstillingene (målt: verbatim-modellen 6,2× med og uten, hovedmodellen 28,1× / 28,6×). Spikens
   forklaring (temperatur-fallback) passer med at greedy er enda tregere enn beam 5 for lydrett. Å slå av fallback halverte tiden i
   spiken; effekten på kvalitet og hopp er ikke målt.
4. **Alle modeller hopper over setninger** (se over). Ingen sjekk i appen oppdager det. Et enkelt tegn kan være «hull» i tidskodene
   (segmentene dekker ikke hele lyden), som kan brukes til å varsle brukeren; det er ikke vurdert her.
5. **Språkkoden `no` tvinger ikke bokmål** og `nn` tvinger ikke nynorsk (se punkt 4 over).
6. **Fart avhenger av innholdet:** 28× på Hamsun og 8× på tett tale for samme modell (medium semantic). «30 minutter intervju» er
   derfor ikke ett tall; ytelsesmålet bør måles på ekte intervjulyd.

## Forslag (jeg har ikke gjort noen av dem)

**`models.json`:**

```json
"style_to_variant": { "lydrett": "verbatim", "tolket": "main" },
"variant_options": {
  "verbatim": { "token_timestamps": true, "max_len": 60, "split_on_word": true },
  "semantic": {},
  "main":     { "token_timestamps": true, "max_len": 60, "split_on_word": true }
}
```

Hovedmodellene står allerede i `models.json` (kommentaren sier det). Teksten «Tolket → semantic-modellene» i spesifikasjonen bør
da endres til hovedmodellen (og «åpent etter spiken»-avsnittet fjernes). Semantic kan bli stående i `models.json` til John Inge har
bestemt seg.

**Videre arbeid utenfor steg 3:** (a) en M1-måling (sjekklisten for steg 1); (b) Windows-måling (`docs/kvalitet-windows.md`);
(c) undersøk fallback i verbatim (fart) og om `no_speech_thold`/`logprob_thold` kan redusere hoppene, med ny måling av både WER og
hopp; (d) klemme siste segment riktig (punkt 2 over); (e) en menneskeskrevet tolket-fasit.

## Beslutninger John Inge må ta

1. **Tolket-modell:** hovedmodellen med tidsstempel-innstillinger (min anbefaling), eller beholde semantic? Endrer spesifikasjonen.
2. **Beam 5 som standard på begge plattformer?** Jeg anbefaler ja. Skal greedy tilbys som reserve for tolket på Windows?
3. **«Anbefalt» = medium på Mac,** og på Windows avgjøres det av PC-målingen. Skal «Best» (large) beholdes siden den ikke målbart
   slår medium her?
4. **Hva sier appen til brukeren om nynorsk fra bokmålstale** (og bokmål fra nynorsktale)? Og skal lydrett nynorsk få en
   etterbehandling (som i så fall bryter med regel 4)?
5. **Ytelsesmålet «under 10 minutter på M1»** gjelder bare hvis det kan måles. Skal lydrett få et eget (tregere) mål, siden
   verbatim er 4 ganger tregere enn tolket?
6. **Skal NPSC-referatene brukes til en ekte tolket-fasit** (Språkbankens fulle utgave er store nedlastinger og krever mer arbeid)?

## Hva som ikke ble kjørt

- **M1 og Windows:** ikke målt (ingen slik maskin her). Se `docs/kvalitet-windows.md` og sjekklisten.
- **Ekte intervjuer, telefonopptak, ekte støy, dialekter med navn** (ingen åpen lyd med fasit; se `testdata/README.md`).
- **Menneskeskrevet tolket-fasit.**
- **Large med greedy på det lange klippet** (ville tatt 10–20 minutter per kjøring), og **f16-modeller** (spiken viste ingen forskjell).
- **Flere gjennomkjøringer av fartsmålingene.** Hver fartsverdi er én kjøring.
- Måleprogrammet er **ikke bygget på Windows** (kompileringsfeil kan oppstå; CI bygger det ikke).

## Slik gjentar du målingen

```sh
cd src-tauri && cargo build --release --features maling --example maal && cd ..
python3 -I tools/maling/hent_modeller.py --dir ~/lla-test/modeller               # 9 filer, ca. 5,4 GB, sjekkes mot models.json
python3 -I tools/maling/hent_testdata.py hent                                    # lyd i testdata/lyd/, sjekkes mot klipp.json
python3 -I tools/maling/maal.py kjor --ut ~/lla-test/resultater --uten-fart      # kvalitet; kan deles: --del 0/3, 1/3, 2/3
python3 -I tools/maling/maal.py kjor --ut ~/lla-test/resultater --bare-fart --cpu  # fart på det lange klippet, alene på maskinen
python3 -I tools/maling/maal.py kjor --ut ~/lla-test/resultater --klipp knuthamsun  # fart på naturlig lyd
python3 -I tools/maling/maal.py kjor --ut ~/lla-test/resultater --klipp knuthamsun --cpu --storrelser small medium
python3 -I tools/maling/maal.py analyser --ut ~/lla-test/resultater --dato 2026-10-19
python3 -I tools/maling/rapport.py tabeller --dato 2026-10-19                   # rapporter/kvalitet-<dato>.md
python3 -I tools/maling/test_ordfeil.py                                          # tester for WER og normalisering
```

Kvalitetsdelen tok noen timer (3–5 prosesser samtidig); fartsmålingene er sekvensielle og tok flere timer. Ikke mål fart mens noe annet tungt kjører.
Rådata (alle kjøringer med tekst) ligger i `rapporter/kvalitet-2026-10-19-tekst.json.gz`; eksempler på feil og hopp hentes med
`rapport.py feil|hopp --dato 2026-10-19 --kjoring <id>`.
