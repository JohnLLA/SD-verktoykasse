# Steg 0 – spike: whisper-rs + NB-Whisper + symphonia/rubato

Dato: 2026-10-17. Kjørt av `transkriberingsbygger`. Koden ligger i `spike/` og er ikke en del av appen.

## Kort fortalt

- **Anbefaling: bruk bindingen (`whisper-rs`, lenket inn).** Den bygget uten problemer på Mac med Metal (25 s), alle kjøringene virket, avbryt stopper på under 15 ms, og segmentene kommer fortløpende. Sidecar trengs ikke på Mac. På Windows bygger og kjører bindingen i CI (windows-latest, MSVC, AVX2), men **bare etter en rettelse i byggeoppsettet** (ggml ble ellers bygget uten optimalisering og var 50 ganger tregere, se «Windows»). Resultatene derfra er fra en CI-runner med 2 vCPU, ikke fra en ekte redaksjons-PC, og må bekreftes på ekte maskin.
- **`nn` gir nynorsk** med alle tre modellvariantene (verbatim, semantic og hovedmodellen). Med verbatim blir nynorsken mindre stabil: enkelte bokmålsformer blir stående.
- **Semantic-modellene finnes bare i `NbAiLabBeta`** (release candidate fra desember 2023). I `NbAiLab` finnes hovedmodellen og verbatim. Lenkene til `NbAiLab/nb-whisper-*-semantic` på modellkortet gir 401, altså finnes de ikke. Dette er en **beslutning for John Inge** (se under).
- **Faktiske størrelser (q5_0):** small 175 MB, medium 539 MB, large 1081 MB. Det stemmer omtrent med anslagene i spesifikasjonen. `models.json` er fylt ut med URL låst til commit, størrelse og SHA-256 for 18 filer.
- **Fart, Mac (M5 Max, Metal):** medium q5 med beam 5 kjører 30 ganger raskere enn sanntid. Et intervju på 30 minutter tar da omtrent 1 minutt. Med small tar det omtrent 30 sekunder. M1 er mye tregere og må måles der.
- **q5_0 er ikke merkbart dårligere** enn full modell (f16) på testsetningene.
- **Dekoding:** alle formatene i spesifikasjonen (mp3, m4a/AAC, wav, flac, ogg/Vorbis, mp4, mov med videospor først) leses og resamples riktig. En fil på 3 timer bruker 662 MB minne til dekoding, og det er bare utdatabufferet (16 kHz f32).
- **Fem ting steg 1 må ta hensyn til:** (0) På Windows må ggml bygges med `/O2` via `CMAKE_PROJECT_INCLUDE` (se «Windows»), ellers er det ubrukelig tregt. (1) `set_abort_callback_safe` i whisper-rs 0.16 har en minnefeil og skal ikke brukes. (2) ggml må bygges med `GGML_NATIVE=OFF`, ellers kan appen krasje på andre maskiner. (3) Verbatim-modellen gir dårlige tidskoder: hele 30-sekundersvinduer. (4) Whisper bør få lyden i biter, ikke hele filen på én gang. En fil på 3 timer brukte 2 GB med small.

## Hva som ble kjørt

| | |
|---|---|
| Maskin | MacBook Pro, Apple M5 Max, 18 kjerner, 36 GB, macOS 26.6.2 |
| Rust | 1.96.0 |
| whisper-rs | 0.16.0 (whisper-rs-sys 0.15.0, whisper.cpp 1.8.3), feature `metal` på macOS |
| symphonia | 0.5.5 (features: mp3, aac, isomp4, flac, vorbis, ogg, wav, pcm) |
| rubato | 0.16.2 (`FftFixedIn`) |
| cmake | 4.4.4. Var ikke installert på Macen, så den ble lagt i et midlertidig Python-venv utenfor prosjektet. Ingen systemendring. |

Ingen andre crates. Ingen ffmpeg (testfilene ble laget med macOS-verktøyene `say`, `afconvert` og AVFoundation via et lite Swift-skript utenfor repoet).

**Testlyd**

- `king.mp3`, 85 s, stereo 44,1 kHz. Kongens tale fra NbAiLabs eget eksempel: <https://github.com/NbAiLab/nb-whisper/raw/main/audio/king.mp3>
- `knuthamsun.mp3`, 23,1 min, mono. Også fra NbAiLab-repoet. Brukt til fartsmåling.
- Syntetisk norsk tale (`say -v Nora`) konvertert til alle format.
- To korte Vorbis-filer fra Wikimedia Commons og én webm/Opus derfra (negativ test).
- 3-timersfiler (wav 2,07 GB og m4a 81 MB) laget ved å gjenta kongens tale.

**Modeller lastet ned til testen: 2,04 GB totalt** (lagt utenfor repoet)

small verbatim q5 (175 MB), small hovedmodell q5 (175 MB), small semantic q5 (175 MB), small semantic f16 (488 MB), small verbatim f16 (488 MB), medium semantic q5 (539 MB). Large er ikke lastet ned og ikke målt.

## Modellfiler

### NbAiLab eller NbAiLabBeta

| Org | Hovedmodell (`nb-whisper-<s>`) | Verbatim (`-verbatim`) | Semantic (`-semantic`) |
|---|---|---|---|
| `NbAiLab` | Ja, offisiell utgivelse 13.02.2024. large oppdatert 13.07.2024, men ggml-filene er uendret | Ja, 13.02.2024 | **Nei** (401) |
| `NbAiLabBeta` | Ja, 27.01.2024 (release candidate) | Ja, 27.01.2024 | Ja, 20.12.2023, «Release Candidate» |

- ggml-filene for hovedmodell og verbatim er **byte-like** i de to organisasjonene (samme SHA-256). Da bruker vi `NbAiLab`, som er den offisielle og vedlikeholdte.
- Semantic finnes bare i `NbAiLabBeta`, er eldre enn den offisielle utgivelsen og har aldri blitt flyttet over. Nedlastingstallene er lave (10–21 per måned mot 1100–4600 for hovedmodellene).
- Alle repoene har lisens Apache 2.0 og er ikke låst (ingen innlogging).
- Modellkortet sier at *hovedmodellen* er laget for å gjøre muntlig tale om til «grammatisk korrekte skriftlige setninger». Det er i praksis allerede «tolket». Semantic er trent 200 ekstra steg for å bruke «så få ord som mulig» (teksting).

### Filer, størrelser og SHA-256

SHA-256 er hentet fra Hugging Face-API-et (`siblings[].lfs.sha256`). For de seks filene som ble lastet ned, er summen kontrollert med `shasum -a 256`, og alle stemte. URL-mønster: `https://huggingface.co/<repo>/resolve/<revision>/<fil>`. Revision er låst til commit (står i `models.json`), ikke `main`.

| Repo | Fil | Kvant | Byte | SHA-256 |
|---|---|---|---|---|
| NbAiLab/nb-whisper-small-verbatim | ggml-model-q5_0.bin | q5_0 | 175 209 680 | `8982b4a4e365f3f64a60ca12abb7382132e59b2a1040d52ab8ddd577948a5c96` |
| NbAiLab/nb-whisper-small-verbatim | ggml-model.bin | f16 | 487 601 984 | `f80a415709dbd56e13cd7ee8b961f881bf81082c84247109e29ae2cd171afe72` |
| NbAiLab/nb-whisper-medium-verbatim | ggml-model-q5_0.bin | q5_0 | 539 212 484 | `600aff00e417bf070364da36d6d4a6ed5f28a3deac11c5919b62733ee17cecd1` |
| NbAiLab/nb-whisper-medium-verbatim | ggml-model.bin | f16 | 1 533 763 076 | `5d6c56c7ccaeee20b8ef65f0188ba9f6a06c2f0d35797b86b851e77adc451770` |
| NbAiLab/nb-whisper-large-verbatim | ggml-model-q5_0.bin | q5_0 | 1 081 140 203 | `344f6cbda0fb44b20d19d02dd423bb87723a6fc13fe02d45dff3d7505a12f919` |
| NbAiLab/nb-whisper-large-verbatim | ggml-model.bin | f16 | 3 095 033 483 | `0227866ef47189f79d04347a080c73fcd8267c8e2255da5f77803506ab4ffc7d` |
| NbAiLabBeta/nb-whisper-small-semantic | ggml-model-q5_0.bin | q5_0 | 175 209 680 | `575a6413fd028d8c397722da81ad599961a378b562e2c4200d5904325ce99439` |
| NbAiLabBeta/nb-whisper-small-semantic | ggml-model.bin | f16 | 487 601 984 | `a90000916a4794816ab64f192d4445747aea6eac23525ec3bae55dc71b4126be` |
| NbAiLabBeta/nb-whisper-medium-semantic | ggml-model-q5_0.bin | q5_0 | 539 212 484 | `71f7e6db73cd80a8b7f044d277beaf7a286018c7092766a6f1bdc134ae34ac72` |
| NbAiLabBeta/nb-whisper-medium-semantic | ggml-model.bin | f16 | 1 533 763 076 | `c837ce74a9ba4efbff2b723229b56aa276f35b374c8cc8a985d7ad6900e42f1c` |
| NbAiLabBeta/nb-whisper-large-semantic | ggml-model-q5_0.bin | q5_0 | 1 081 140 203 | `30fdeeb40825c69f0e02c3e07be5b10a6e15b231b7f05feb7a8ab79d397184cc` |
| NbAiLabBeta/nb-whisper-large-semantic | ggml-model.bin | f16 | 3 095 033 483 | `2a94af1175899a074e5e7b3da63a6009763202d9b10ce4d1c09c9f905d37bfb8` |
| NbAiLab/nb-whisper-small | ggml-model-q5_0.bin | q5_0 | 175 209 680 | `2a9025afb6e825fc4ae6a46671e0cb2f43e62f1dec87270deea6fe61b5285a20` |
| NbAiLab/nb-whisper-small | ggml-model.bin | f16 | 487 601 984 | `a0fc1555f5bd51044b0ea88bb9b7891e1ee331a8087eddb0afc3a05839db48ab` |
| NbAiLab/nb-whisper-medium | ggml-model-q5_0.bin | q5_0 | 539 212 484 | `18733de634af639a43b0f8c5f5a2ea0920de4c5b32a5570ec130981581c0e5e7` |
| NbAiLab/nb-whisper-medium | ggml-model.bin | f16 | 1 533 763 076 | `f73141401d203ee77fc7ddf7bf97926a8a85fe85faa6066a6920e4815f48a73d` |
| NbAiLab/nb-whisper-large | ggml-model-q5_0.bin | q5_0 | 1 081 140 203 | `feb5951ae694a62cfeb81fb501f6cfa8cc50d96bcddb1e4e8215f7006bac23a2` |
| NbAiLab/nb-whisper-large | ggml-model.bin | f16 | 3 095 033 483 | `0f2f66f22e11a7c7da3c582d8e5c89cb2c0011753ba9c7c9731e320a4ba33e76` |

Hovedmodellen står i `models.json` med `"style": null` som kandidat, til John Inge har bestemt seg.

### Nedlasting: domener og gjenopptak

- `huggingface.co/.../resolve/...` svarer med **302 til en CDN-adresse**, nå `us.aws.cdn.hf.co` (xet-bridge). Adressen er signert og har en utløpstid. Nedlastingen må derfor følge omdirigering til `*.hf.co`, og ved gjenopptak må den spørre `huggingface.co` på nytt for å få en fersk adresse.
- `Range` virker gjennom omdirigeringen (svar 206, testet). Gjenopptak med HTTP Range går altså an.
- `HEAD` mot `huggingface.co` gir `x-linked-size` og `x-linked-etag` (lik SHA-256). Da kan appen vise størrelsen før nedlasting uten å hente filen.
- Konsekvens for «bare to domener» i spesifikasjonen: modellnedlastingen trenger `huggingface.co` **og** `*.hf.co`. Nedlastingen gjøres i Rust, så CSP-en til webvisningen påvirkes ikke, men allowlist-en i `models.rs` må ha med begge.

## Målform: `no` og `nn`

Samme fil (kongens tale), small q5_0, beam 5. Første 3–4 segmenter av hver:

**Lydrett (verbatim), bokmål `no`**
```
[00:00:00.500 --> 00:00:30.500] nordmenn er nordlendinger trøndere sørlendinger og folk fra alle andre regioner nordmenn er også innvandrere fra afghanistan pakistan og polen sverige somalia og syria
[00:00:30.720 --> 00:00:39.140] det vi kaller hjem er der hjertet vårt er og det kan ikke alltid plasseres
[00:00:39.140 --> 00:00:46.780] innenfor landegrenser nordmenn er jenter som er glad i jenter gutter som er glad i gutter
```

**Lydrett (verbatim), nynorsk `nn`**
```
[00:00:00.040 --> 00:00:30.040] nordmenn er nordlendingar trøndere sørlendingar og folk frå alle andre regionar nordmenn er også innvandrar frå afghanistan pakistan og polen sverige somalia og syria
[00:00:30.400 --> 00:01:00.400] det vi kallar hjem er der hjartet vårt er og det kan ikkje alltid plasserast innanfor landegrenser nordmenn er jenter som er glad i jenter gutar som er glad i gutar og jenter og gutar som er glad i kvarandre ...
[00:01:00.820 --> 00:01:15.620] med andre ord noreg er dere noreg er oss mitt største håp for noreg er at vi skal klare
```

**Tolket (semantic, NbAiLabBeta), bokmål `no`**
```
[00:00:00.040 --> 00:00:08.680] Nordmenn er nordlendinger, trøndere, sørlendinger og folk fra alle andre regioner.
[00:00:08.680 --> 00:00:16.360] Nordmenn er også innvandret fra Afghanistan, Pakistan og Polen, Sverige, Somalia og Syria.
[00:00:16.360 --> 00:00:27.880] Det er ikke alltid så lett å si hvor vi er fra.
[00:00:30.040 --> 00:00:36.800] Det er det vi tilhører. Det vi kaller hjem, er der hjertet vårt er.
```

**Tolket (semantic, NbAiLabBeta), nynorsk `nn`**
```
[00:00:00.040 --> 00:00:08.480] Nordmenn er nordlendingar, trøndarar, sørlendingar og folk frå andre regionar.
[00:00:08.480 --> 00:00:16.600] Nordmenn er òg innvandrarar frå Afghanistan, Pakistan, Polen, Sverige, Somalia og Syria.
[00:00:16.600 --> 00:00:28.520] Det er ikkje alltid så lett å seie kvar vi er frå.
[00:00:30.040 --> 00:00:36.720] Nordmenn er det vi tilhøyrer. Det vi kallar heim, er der hjartet vårt er.
```

**Til sammenligning: hovedmodellen (NbAiLab), nynorsk `nn`**
```
[00:00:00.040 --> 00:00:07.560] Nordmenn er nordlendingar, trøndarar, sørlendingar og folk frå alle andre regionar.
[00:00:07.560 --> 00:00:15.040] Nordmenn er også innvandrarar frå Afghanistan, Pakistan, Polen, Sverige,
[00:00:15.040 --> 00:00:17.800] Somalia og Syria.
[00:00:17.800 --> 00:00:28.680] Det er ikkje alltid så lett å seie kvar vi er frå. Kva nasjonalitet?
```

**Vurdering**

- `nn` gir tydelig nynorsk i alle variantene (*ikkje, kvar, frå, kallar, hjartet, Noreg, kvarandre, vidare, gutar*). Begge stilene kan altså gi nynorsk, som spesifikasjonen forutsetter.
- **Verbatim + `nn` blander mer**: «trøndere» og «hjem» blir stående på bokmål, og i ett segment står «norge» før modellen går over til «noreg». Semantic og hovedmodellen er jevnere. `kvalitetsmaler` bør måle andelen bokmålsformer i lydrett nynorsk.
- Lydrett gir små bokstaver uten tegnsetting, som forventet. Teksten er vist uendret.
- Alle modellene hopper av og til over tekst ved 30-sekundersgrensene. Eksempel: lydrett mistet «det er ikke alltid så lett å si hvor vi er fra». **Semantic medium hoppet over hele setninger** («Det er ikke alltid så lett …» på bokmål, «Det vi kallar heim …» på nynorsk). For journalister som trenger sitater, er dette et argument for hovedmodellen som «tolket». Det må måles skikkelig i steg 3.

## q5_0 mot full modell (f16)

small, `no`, beam 5:

| | q5_0 | f16 |
|---|---|---|
| semantic | «Med andre ord: Norge er dere. Norge er oss.» | «Med andre ord: Norge er dere - Norge er oss.» |
| semantic | «Nordmenn er også innvandret fra Afghanistan, Pakistan og Polen, Sverige, Somalia og Syria.» | Samme tekst, men delt i to segmenter |
| verbatim | «nordmenn liker grieg kygo hellbillies og kari bremnes» | «nordmenn liker grieg-hyggo helbillis og carrie billis» |

Ingen merkbar forskjell. På denne prøven var q5 til og med best for verbatim, men det er tilfeldig variasjon. **Bruk q5_0.** Modellene blir 64 % mindre, og farten er lik (f16 small semantic: 1,36 s mot 1,25 s for q5).

## Fart

### Mac, Metal (M5 Max)

`speed` = antall sekunder lyd per sekund kjøretid. Inkluderer ikke dekoding (0,05 s for 85 s mp3, 0,7 s for 23 min) eller modellasting (0,06–0,15 s).

**Kongens tale, 85 s, de fire kombinasjonene med small q5:**

| Modell | Språk | Greedy | Beam 5 |
|---|---|---|---|
| small verbatim | no | 3,75 s (23×) | 5,33 s (16×) |
| small verbatim | nn | 4,69 s (18×) | 7,26 s (12×) |
| small semantic | no | 0,84 s (102×) | 1,25 s (68×) |
| small semantic | nn | 0,72 s (118×) | 1,27 s (67×) |
| small hovedmodell | no / nn | 0,83 / 0,82 s | 1,30 / 1,25 s |
| medium semantic | no / nn | – | 2,46 / 2,32 s (35–37×) |

**Knut Hamsun, 23,1 min (1386 s):**

| Modell | Innstilling | Tid | Speed | Anslått for 30 min | Toppminne |
|---|---|---|---|---|---|
| small verbatim q5 | beam 5 | 79,8 s | 17× | 1 min 44 s | 736 MB |
| small hovedmodell q5 | beam 5 | 22,9 s | 61× | 30 s | 724 MB |
| small semantic q5 (nn) | beam 5 | 20,3 s | 68× | 26 s | 727 MB |
| **medium semantic q5** | **beam 5** | **46,7 s** | **30×** | **61 s** | 1386 MB |
| medium semantic q5 | greedy | 28,8 s | 48× | 37 s | 1080 MB |

- **Verbatim er 3–4 ganger tregere** enn de andre. Grunnen er at whisper.cpp prøver på nytt med høyere temperatur (fallback) når verbatim-utdata ikke består kvalitetssjekkene. Uten fallback (`temperature_inc = 0`) halveres tiden (2,2 s mot 5,3 s), men det kan gi flere gjentakelsesløkker. `kvalitetsmaler` må måle dette før noen slår det av.
- Ytelsesmålet «under 10 min for 30 min med Anbefalt på M1» ser greit ut på M5 Max (1 min). **En M1 har langt færre GPU-kjerner enn M5 Max, så det må måles på M1.** Grovt anslag: 5–10 min med beam 5 og 3–6 min med greedy. Det er et anslag, ikke en måling.

### CPU uten GPU (proxy for Windows, men **ikke representativt**)

5 min lyd, Metal slått av, Apple-CPU med Accelerate/NEON:

| Modell | Tråder | Greedy | Beam 5 |
|---|---|---|---|
| small hovedmodell q5 | 4 | 9,5 s (32×) | 18,3 s (16×) |
| medium semantic q5 | 4 | 28,7 s (10×) | 48,1 s (6,2×) |
| medium semantic q5 | 8 | – | 35,6 s (8,4×) |

En M5 Max-kjerne er klart raskere enn en kjerne i en vanlig redaksjons-PC med AVX2. Med en grov faktor 3–6 blir medium med beam 5 omtrent 1–2× sanntid på en slik PC, altså 15–30 minutter for et intervju på 30 minutter. Det er akkurat på grensen til målet. **Windows-tallene må måles på ekte PC** (oppskrift under). Hvis tallene er for dårlige: greedy i stedet for beam 5 på Windows, eller «Rask» som standard der, som spesifikasjonen allerede åpner for.

## Dekoding og resampling

Strømmende: pakke for pakke fra symphonia, miks til mono, biter på 4096 rammer gjennom rubato `FftFixedIn`. Forsinkelsen i filteret trekkes fra, og resultatet kuttes til nøyaktig lengde. Utdata reserveres på forhånd når containeren oppgir lengden.

| Fil | Kodek | Inn | Ut (16 kHz) | Avvik |
|---|---|---|---|---|
| mp3 (kongens tale) | mp3 | 44,1 kHz stereo | 1 367 191 | 0,0 ms |
| m4a | aac | 44,1 kHz stereo | 85 449 | se merknad |
| mp4 (bare lyd) | aac | 44,1 kHz stereo | 85 449 | se merknad |
| **mov med H.264-video som første spor** | aac | 44,1 kHz stereo | 85 449 | lydsporet ble valgt riktig |
| **mp4 med H.264-video som første spor** | aac | 44,1 kHz stereo | 85 449 | lydsporet ble valgt riktig |
| wav s16 | pcm | 48 kHz stereo | 84 658 | 0,0 ms |
| wav s24 | pcm | 44,1 kHz stereo | 84 658 | 0,0 ms |
| wav f32 | pcm | 22,05 kHz mono | 84 658 | 0,0 ms |
| flac | flac | 44,1 kHz stereo | 84 658 | 0,0 ms |
| ogg (Commons) | vorbis | 44,1 kHz stereo | 44 722 / 39 288 | 0,0 ms |
| m4a ALAC | alac | – | **feil: «unsupported format: codec alac»** | ikke i spesifikasjonen |
| mp4 med Opus | opus | – | **feil: «unsupported format: codec opus»** | riktig |
| webm (Opus) | – | – | **feil: «io error: unexpected end of file»** | feil melding |
| caf, aiff | – | – | **feil: «io error: unexpected end of file»** | feil melding |

Merknader:

- **AAC er 48 ms lengre enn kilden** (5,341 s mot 5,291 s). Det er encoderens priming-forsinkelse (2112 rammer), som ikke trekkes fra i symphonia 0.5. Tidskodene blir da 48 ms for sent. Det er neppe merkbart, men vi kan trekke det fra i steg 1 hvis det viser seg.
- **Ukjent container gir ikke «Unsupported» i symphonia 0.5.** Proben leter gjennom hele filen etter en kjent markør og ender på EOF. Steg 1 må gjenkjenne formatet selv (magiske byte: `1A 45 DF A3` = webm/mkv, `FORM` = aiff, `caff` = caf, `OggS` + `OpusHead` = ogg/Opus) for å kunne si «filen er webm/Opus, som ikke støttes; konverter til mp3 eller wav».
- **symphonia 0.6.1** (august 2026) er nyeste versjon. Den har heller ikke Opus, men har aiff, caf, alac og mkv som valgfrie features. Spiken brukte 0.5.5. Om steg 1 skal bruke 0.6, avgjøres der. Det krever at dekodingen testes på nytt, og API-et er endret.
- symphonia skriver selv at enkelte strømmer kan få den til å panikke. Dekodingen bør derfor kjøres i en egen tråd med `catch_unwind`, så en ødelagt fil ikke tar ned appen.

### Minne på lange filer

| Fil | Dekodetid | Toppminne |
|---|---|---|
| 3 t wav, 48 kHz stereo, 2,07 GB | 6,5 s | **662 MB** |
| 3 t m4a, 81 MB | 3,8 s | **664 MB** |

Utdatabufferet for 3 timer i 16 kHz f32 er 691 MB (= 659 MiB). Dekodingen legger altså nesten ingenting til.

**Whisper på 3 timer** (small hovedmodell q5, greedy, Metal): 112 s, 96× sanntid, 1599 segmenter, **toppminne 2039 MB**. whisper.cpp regner ut mel-spektrogrammet for hele lydbufferet på én gang. Det koster omtrent 1,3 GB ekstra for 3 timer. Med large blir det over 3 GB. **Anbefaling for steg 1:** gi whisper lyden i biter på omtrent 10 minutter, delt ved stillhet, med tidsforskyvning, og send slutten av forrige bit som `initial_prompt`. Da holder minnet seg flatt uansett fillengde, framdriften blir jevn, og avbryt blir enklere. `full()` tar `c_int` samples, så én bit kan uansett ikke være lengre enn omtrent 37 timer.

## Framdrift, segmenter, avbryt og tidskoder

- **Segmenter fortløpende:** `set_segment_callback_safe_lossy` virker. Første segment kom etter 0,4–1,5 s.
- **Framdrift:** `set_progress_callback_safe` virker, men **går over 100** (125–126 %) når verbatim prøver på nytt. Må klemmes til 0–100 i appen.
- **Avbryt:** abort-callbacken leser et `AtomicBool`. Målt fra flagget settes til `full()` returnerer:

  | | Avbrutt etter 3 s | Avbrutt etter 7 s |
  |---|---|---|
  | medium, Metal | 3 ms | 1 ms |
  | medium, CPU 4 tråder | 6 ms | 11 ms |

  `full()` returnerer `GenericError(-8)` eller `(-9)`. Segmentene som var ferdige før avbruddet, er fortsatt tilgjengelige.
- **Tidskoder med verbatim er dårlige.** Verbatim-modellen gir nesten ingen tidsstempeltoken, så segmentene blir hele 30-sekundersvinduer, og siste segment kan **slutte etter at lyden er slutt** (01:47 for en fil på 85 s). Med `token_timestamps` + `max_len 60` + `split_on_word` blir segmentene 2–10 s, men av og til får et segment null lengde (start = slutt). Semantic og hovedmodellen gir gode tidskoder uten dette. **Steg 1:** slå på token-tidsstempler for lydrett, og klem alle tider til lydlengden. For «klikk på segment spiller av lyden» og for srt/vtt er dette avgjørende.

## Funn i whisper-rs 0.16 som steg 1 må ta hensyn til

1. **`FullParams::set_abort_callback_safe` er feil (udefinert oppførsel).** Trampolinen tolker brukerpekeren som `F`, mens den faktisk peker på en `Box<dyn FnMut() -> bool>`. Testen (`spike/src/bin/abort_safe_check.rs`): closuren ble kalt **0 ganger**, `full()` avbrøt likevel på tilfeldige data, og prosessen **krasjet med segfault (exit 139)** ved avslutning. **Bruk den usikre `set_abort_callback` + `set_abort_callback_user_data` med vår egen `extern "C"`-funksjon**, slik `spike/src/bin/transcribe.rs` gjør. Feilen bør meldes til whisper-rs (Codeberg), men det er John Inges valg.
2. **En panikk inne i en callback avslutter hele prosessen** (kan ikke rulle tilbake gjennom C). Observert: et brutt rør i `println!` i segment-callbacken førte til abort. I appen skal callbackene bare sende til en kanal og aldri kunne panikke.
3. `set_*_callback_safe` lekker sin `Box` hver gang (`Box::into_raw` uten frigjøring). Det er noen få byte per jobb og uten betydning i praksis.
4. **Logger:** `whisper_rs::install_logging_hooks()` uten `log`/`tracing`-feature gjør whisper.cpp og ggml helt stille. Uten den skriver whisper.cpp til stderr, blant annet stien til modellfilen (ikke lydfilen). Med `print_realtime`/`print_progress` av skriver whisper.cpp aldri tekst. **Steg 1:** installer hookene ved oppstart.
5. **`GGML_NATIVE` er på som standard.** ggml bygges da for CPU-en på byggemaskinen. På denne M5-en ble `MATMUL_INT8` og `SME` slått på, og det har ikke M1. En CI-maskin på Azure kan ha AVX-512, som de fleste laptoper mangler. Begge deler gir krasj med «illegal instruction» hos brukeren. **Alle utgivelsesbygg må ha `GGML_NATIVE=OFF`.** whisper-rs-sys sender alle miljøvariabler som begynner med `GGML_` videre til cmake, så det holder med en `[env]` i `.cargo/config.toml` eller i CI. Målt på Mac: portable bygg (`GGML_NATIVE=OFF`) er like raskt som native (Metal 19,58 s mot 19,55 s, CPU 49,8 s mot 51,7 s).
6. Byggeavhengigheter: **cmake** (påkrevd) og **libclang** for bindgen. whisper-rs-sys har ferdige bindings som reserve, men de er laget på Linux/glibc. Da er det bedre å ha libclang på byggemaskinen.
7. Modellsti på Windows: whisper.cpp gjør UTF-8-stien om til wide-string før `ifstream` (`#ifdef _WIN32`). Brukermapper med æøå skal derfor virke. Det må likevel stå på sjekklisten.

## Windows

### Resultater fra CI (GitHub Actions, windows-latest) – ikke ekte redaksjons-PC

Tallene er fra kjøring <https://github.com/JohnLLA/lla-verktoykasse/actions/runs/39045943504>. Siste grønne kjøring (etter opprydding, samme bygg): <https://github.com/JohnLLA/lla-verktoykasse/actions/runs/39047556814>. Begge grønne på Windows x64 og macOS arm64. Arbeidsflyt: `.github/workflows/spike-build.yml`.

Runneren er en virtuell maskin med **2 vCPU** (Intel Xeon Platinum 8573C, en annen kjøring fikk AMD EPYC 9V74), ingen GPU. Det er langt svakere enn en typisk redaksjons-PC, så tallene under er **nedre grenser, ikke mål på hva en ekte PC klarer**. Mac-kolonnen er `macos-14` (virtuell M1, 3 kjerner, CPU uten Metal), tatt fra samme kjøring, så de to kan sammenlignes.

| | Windows (CI, 2 vCPU) | macOS M1 (CI, CPU) |
|---|---|---|
| `cargo build --release` | **lykkes** (MSVC, VS 2026-generator, AVX2, `GGML_NATIVE=OFF`), 2,5 min uten hurtigbuffer | lykkes, 13 s med hurtigbuffer |
| SHA-256 small verbatim q5_0 | stemmer (`8982b4a4…`) | stemmer |
| whisper.cpp system | `AVX = 1 \| AVX2 = 1 \| F16C = 1 \| FMA = 1 \| BMI2 = 1`, ingen AVX-512 | – |
| Dekoding av king.mp3 (85 s) | 0,11 s | 0,11 s |
| `no`, kongens tale, lydrett | bokmål: «nordmenn er nordlendinger trøndere sørlendinger og folk fra alle andre regioner …» (6 segmenter) | samme tekst |
| `nn`, kongens tale, lydrett | nynorsk: «nordmenn er nordlendingar trøndere sørlendingar …» (4 segmenter) | samme tekst (6 segmenter) |
| Fart `no`, 85 s, greedy | 319 s (0,3× sanntid) | 67 s (1,3×) |
| Fart `nn`, 85 s, greedy | 229 s (0,4×) | 108 s (0,8×) |
| Fart, 120 s Hamsun, small verbatim, greedy | 176 s (0,7×) | 46 s (2,6×) |
| Fart, 120 s Hamsun, small verbatim, beam 5 | 206 s (0,6×) | 58 s (2,1×) |
| Modellsti `…/Brukernavn æøå/modell.bin` | lastes og kjører | lastes og kjører |
| Avbryt (flagg satt etter 2 s, 23 min lyd) | `GenericError(-6)`, **19,0 s** fra flagget til retur | `GenericError(-6)`, **2,0 s** |

Merknader:

- Målform: `no` gir bokmål og `nn` gir nynorsk også på Windows. Samme tekst som på Mac. Verbatim + `nn` blander som før («trøndere» står igjen på bokmål).
- **Fart:** medium q5 (som er «Anbefalt») er ikke målt på CI. Small verbatim er den tregeste kombinasjonen (se fallback-funnet under «Fart»), så tallene er pessimistiske for «Rask» men sier lite om medium. Med bare 2 vCPU er det ikke overraskende at det er under sanntid. **Hvor fort det går på en vanlig redaksjons-PC (4–8 kjerner), vet vi ikke ennå.** Oppskriften under må kjøres.
- **Avbryt-forsinkelsen er ikke millisekunder på treg CPU.** På M5 Max var den 3–11 ms. På CI var den 2 s (M1) og 19 s (Windows) når det ble avbrutt tidlig. Årsaken er at whisper.cpp regner ut mel-spektrogrammet for **hele** lydbufferet (23 min her) før noe sjekker avbryt-flagget, og first segment kom aldri (`segments=0`). Det støtter anbefalingen om å mate whisper i biter på ca. 10 minutter: da blir både minnet og avbrytforsinkelsen begrenset til én bit.
- Ingen krasj, ingen manglende DLL-er (statisk lenking), ingen sidecar nødvendig for å få det til å kjøre. **Binding er fortsatt anbefalingen.**

### Funn: ggml ble bygget uten optimalisering på MSVC (må med i steg 1 og i release-bygget)

Første forsøk på Windows-CI bygget og kjørte, men var **uten rimelig fart**: 2 sekunder lyd tok 230 s (mot 4,6 s på Mac-runneren), og 85 s lyd kom ikke ferdig på 27 minutter. Det så ut som et hang, men var det ikke. `CMakeCache.txt` viste at `CMAKE_C_FLAGS_RELEASE` og `CMAKE_CXX_FLAGS_RELEASE` bare var `-nologo -MD -Brepro -W0`, altså uten `/O2`. `cmake-rs` (brukt av `whisper-rs-sys`) overstyrer standardflaggene for Release-konfigurasjonen med flaggene den henter fra `cc`, og optimaliseringsflaggene fjernes. Resultat: `<Optimization>` ble tom/Disabled for ggml. Å sette `CFLAGS`/`CXXFLAGS` hjalp ikke (`/O2` ble filtrert bort).

Løsningen som virker: en liten cmake-fil, `spike/ci/msvc-optimize.cmake`, som setter `CMAKE_C_FLAGS_RELEASE`/`CMAKE_CXX_FLAGS_RELEASE` til `/O2 /Ob2 /DNDEBUG …`, lastet via miljøvariabelen `CMAKE_PROJECT_INCLUDE` (whisper-rs-sys sender alle `CMAKE_*`-variabler videre). Med den gikk samme røyktest fra 230 s til 16 s. **Steg 1 må ta med dette i Tauri-bygget** (`.cargo/config.toml` `[env]` for MSVC-målet, eller `build.rs`), og Windows-CI-en må ha en sjekk som feiler hvis ggml bygges uten `/O2`. Verdt å melde til whisper-rs (Codeberg), men det er John Inges valg.

### Vurdering av risiko

Teoretisk vurdering som nå er delvis bekreftet: whisper-rs-sys har egen MSVC-håndtering (`/utf-8`, lenker `advapi32`). Den bygger statisk (`BUILD_SHARED_LIBS=OFF`), så det blir ingen ekstra DLL-er. CPU-backenden setter `/arch:AVX2` (`EnableEnhancedInstructionSet = AdvancedVectorExtensions2` i genererte prosjektfiler).

Kjente risikoer på Windows:

- **PC-er uten AVX2.** Eldre Celeron og Pentium Silver (Gemini Lake, Jasper Lake), som er vanlige i billige jobblaptoper, mangler AVX2. Et AVX2-bygg krasjer der med «illegal instruction». Forslag: sjekk `is_x86_feature_detected!("avx2")` og `"fma"` ved oppstart og vis en tydelig melding i stedet for å krasje. Alternativet er å bygge alle CPU-varianter (`GGML_BACKEND_DL` + `GGML_CPU_ALL_VARIANTS`), men det krever delte biblioteker og gjør pakkingen mer komplisert. **Beslutning for John Inge.** Ikke testet (CI-runnerne har AVX2).
- **MSVC mot clang-cl:** ggml er ofte raskere bygget med clang enn med MSVC. Det bør måles hvis Windows-farten blir for dårlig.
- Antall tråder: spiken bruker min(logiske kjerner, 8). På PC-er med hyperthreading kan antall fysiske kjerner være bedre. På CI (2 vCPU) ble 4 tråder katastrofalt tregere enn 2, fordi ggml-trådene venter aktivt. Aldri sett flere tråder enn det finnes kjerner. Det må måles på ekte PC.

**CI:** `.github/workflows/spike-build.yml` bygger spiken på `windows-latest` og `macos-14` med portable flagg (`GGML_NATIVE=OFF`; Windows: AVX2, ikke AVX-512), hurtigbuffer for cargo, bygg, modell og testlyd, sjekker SHA-256 på small-modellen og kjører dekoding, `no`/`nn` (to linjer, 200 tegn), fart, avbryt og æøå-sti. Loggen får ellers bare tider. Ingen versjonstagger, ingen releaser. Arbeidsflyten er en del av PR #1, og `byggmester` bygger release-arbeidsflyten videre fra den.

### Oppskrift for John Inge: kjør spiken på en Windows-PC (ikke kjørt på enhet)

Én gang:

1. Installer **Visual Studio Build Tools 2022** med arbeidsmengden «Desktop development with C++».
2. Installer **Rust** fra <https://rustup.rs> (standardvalg, `x86_64-pc-windows-msvc`).
3. Installer **CMake** (<https://cmake.org/download/>, velg «Add to PATH») og **LLVM** (<https://github.com/llvm/llvm-project/releases>, Windows x64-installer, velg «Add to PATH»).
4. Kopier mappen `spike/` til PC-en, for eksempel til `C:\spike`.

I PowerShell (åpne «Developer PowerShell for VS 2022»):

```powershell
cd C:\spike
$env:GGML_NATIVE="OFF"; $env:GGML_AVX="ON"; $env:GGML_AVX2="ON"; $env:GGML_FMA="ON"; $env:GGML_F16C="ON"; $env:GGML_BMI2="ON"
$env:LIBCLANG_PATH="C:\Program Files\LLVM\bin"
$env:CMAKE_PROJECT_INCLUDE="C:\spike\ci\msvc-optimize.cmake"   # uten denne blir ggml bygget uten /O2
cargo build --release

mkdir data
curl.exe -L -o data\king.mp3 https://github.com/NbAiLab/nb-whisper/raw/main/audio/king.mp3
curl.exe -L -o data\hamsun.mp3 https://github.com/NbAiLab/nb-whisper/raw/main/audio/knuthamsun.mp3
curl.exe -L -o data\small-verbatim.bin https://huggingface.co/NbAiLab/nb-whisper-small-verbatim/resolve/6ecf80f5084aae499964121ea34651aa6bfc5b51/ggml-model-q5_0.bin
curl.exe -L -o data\medium-semantic.bin https://huggingface.co/NbAiLabBeta/nb-whisper-medium-semantic/resolve/da8360cda8228888a27473c45f45f0a6784fab02/ggml-model-q5_0.bin
Get-FileHash data\small-verbatim.bin, data\medium-semantic.bin -Algorithm SHA256
# Skal være 8982B4A4... og 71F7E6DB...

# 1) Virker det, og gir nn nynorsk?
.\target\release\transcribe.exe --model data\small-verbatim.bin --lang no --audio data\king.mp3 --no-gpu
.\target\release\transcribe.exe --model data\small-verbatim.bin --lang nn --audio data\king.mp3 --no-gpu

# 2) Fart: 10 min av Hamsun med medium ("Anbefalt"), beam 5 og greedy
.\target\release\transcribe.exe --model data\medium-semantic.bin --lang no --audio data\hamsun.mp3 --no-gpu --no-text --max-secs 600 --beam 5
.\target\release\transcribe.exe --model data\medium-semantic.bin --lang no --audio data\hamsun.mp3 --no-gpu --no-text --max-secs 600

# 3) Avbryt etter 5 s
.\target\release\transcribe.exe --model data\medium-semantic.bin --lang no --audio data\hamsun.mp3 --no-gpu --no-text --cancel-after-ms 5000
```

Send meg: PC-modell og CPU (`Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors`), minne, og den siste linjen (`result=... run_s=... speed_x_realtime=...`) fra hver kjøring. Prøv gjerne punkt 2 også med `--threads` lik antall fysiske kjerner. `speed_x_realtime` ganger 30 min gir hvor lang lyd som blir transkribert på 30 min. Målet er at det blir minst 30 min, altså `speed_x_realtime` ≥ 1.

## Binding eller sidecar

**Binding.** Begrunnelse:

- Det virket på første forsøk på Mac med Metal, med segmenter fortløpende, framdrift og avbryt på millisekunder.
- En sidecar (`whisper-cli`) løser ikke byggeproblemene. whisper.cpp må uansett kompileres per plattform med de samme cmake- og ggml-flaggene. Sidecaren gir i tillegg en ekstra binær som må signeres og notariseres, framdrift og tekst må tolkes fra stdout, og lyden må skrives til en midlertidig wav-fil på disk. Det siste er uheldig for kildevern.
- Sidecar er bare aktuelt hvis det å *lenke* whisper.cpp inn i Tauri-binæren skaper trøbbel på Windows, for eksempel kollisjon mellom CRT-varianter eller symboler. Det vet vi først når Windows-CI har kjørt. Utsett avgjørelsen til da, men planlegg for binding.

## Beslutninger John Inge må ta

1. **Hvilken modell skal «tolket» bruke?** Spesifikasjonen sier semantic, men semantic finnes bare som release candidate i `NbAiLabBeta` fra desember 2023, og den hoppet over hele setninger i testen. Alternativet er **hovedmodellen i `NbAiLab`**, som er offisiell, mest brukt og ifølge modellkortet laget for å gi grammatisk korrekt skriftspråk. Mitt forslag er å la `kvalitetsmaler` måle begge i steg 3 og velge da. Til det trenger spesifikasjonen en åpning, for eksempel «tolket = semantic eller hovedmodell, avgjøres av målingen». `models.json` har begge.
2. **Domener for modellnedlasting:** `huggingface.co` + `*.hf.co` (CDN-omdirigering). Er det greit innenfor «bare to nettkall»? Det er fortsatt samme tjeneste.
3. **PC-er uten AVX2:** vis en melding (enkelt) eller støtt dem (mer komplisert pakking)?
4. **Beam 5 eller greedy som standard?** Beam 5 er NbAiLabs anbefaling og ca. 1,6× tregere. Forslag: beam 5 på Mac, avgjøres etter Windows-målingen der.
5. **Nye crates til steg 1** (ikke i spesifikasjonen, krever ja): en HTTP-klient for modellnedlasting med Range (`reqwest` eller `ureq`), `sha2` for SHA-256, `serde`/`serde_json` for `models.json` (kommer allerede med Tauri), og `docx-rs` som spesifikasjonen nevner. Eventuelt `symphonia` 0.6 i stedet for 0.5.
6. **Git:** løst. Spiken ligger på `steg-0-spike` (PR #1) og CI kjører på begge plattformer.

## Sjekkliste – ikke kjørt på enhet

Avkrysset = kjørt i CI (GitHub Actions-runner, 2 vCPU), **ikke på ekte maskin**. «Ekte maskin» står som egen linje der det fortsatt trengs.

- [x] Windows (CI): `cargo build --release` av `spike/` lykkes med MSVC og portable flagg (krever `msvc-optimize.cmake`).
- [x] Windows (CI): `no`/`nn` gir bokmål og nynorsk på kongens tale.
- [ ] Windows, **ekte PC**: kjør oppskriften over og send tallene.
- [ ] Windows, **ekte PC**: fart med medium q5, beam 5 og greedy, på en vanlig redaksjons-PC (4–8 kjerner, uten GPU). CI målte bare small verbatim på 2 vCPU (0,6–0,7× sanntid).
- [x] Windows (CI): avbryt returnerer (`GenericError(-6)`), men med 19 s forsinkelse på 23 min lyd, fordi mel-spektrogrammet regnes ut for hele filen først. Må løses med biter i steg 1 og måles på ekte PC.
- [x] Windows (CI): modell i en mappe med æøå i stien lastes.
- [ ] Windows, **ekte PC**: en brukermappe med æøå i det virkelige brukernavnet (OneDrive-omdirigerte mapper o.l.).
- [ ] Windows, **ekte PC uten AVX2**: hva skjer (forventet krasj, må fanges i steg 1). Ikke mulig på CI.
- [ ] Windows, **ekte PC**: SmartScreen/antivirus reagerer ikke på spike-binæren (gjelder først signert installasjon, steg 4).
- [ ] Mac M1 (eller eldste støttede), **ekte maskin**: fart med medium q5, beam 5 og greedy, med Metal, på et intervju på 30 min. (CI-runneren kjører bare CPU: small verbatim 2,1–2,6× sanntid.)
- [x] Mac (CI): bygger på `macos-14` med `GGML_NATIVE=OFF` og `MACOSX_DEPLOYMENT_TARGET=13.0`.
- [ ] Mac: binæren kjører på macOS 13 og en ekte M1 (CI kjører macOS 14 på virtuell M1).
- [ ] Large q5 (1,1 GB): fart og minne på en Mac med 16 GB.

## Kjøre spiken selv

Krever Rust, cmake og Xcode-verktøyene (Mac).

```sh
cd spike
GGML_NATIVE=OFF cargo build --release
./target/release/decode <lydfil>
./target/release/transcribe --model <ggml-fil> --lang no|nn --audio <lydfil> \
    [--beam 5] [--threads N] [--max-secs S] [--cancel-after-ms MS] \
    [--no-gpu] [--no-text] [--no-fallback] [--max-len 60] [--verbose]
./target/release/abort_safe_check <ggml-fil>   # viser feilen i set_abort_callback_safe
```

`transcribe` skriver segmentene til stdout (det er poenget med spiken) og aldri filnavn. Siste linje har tider og sanntidsfaktor.
