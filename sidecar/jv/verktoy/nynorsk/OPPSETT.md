# Oppsett: Apertium og språkparet nno-nob på macOS

`jv nynorsk` trenger to ting som **ikke** følger med Python-pakken:

1. Programmene fra **`apertium`**, `lttoolbox`, `apertium-lex-tools`, `apertium-separable` og `cg3`, som språkparet bruker. Verktøyet bruker ikke selve skriptet `apertium` (fra 0.2.0), men skriptet er greit å ha for å prøve språkparet for hånd.
2. Språkparet **`apertium-nno-nob`**, som gir de to modusene verktøyet bruker:
   - `nob-nno` (bokmål → nynorsk, `--to nn`)
   - `nno-nob` (nynorsk → bokmål, `--to nb`)

Verktøyet laster aldri ned noe selv. Mangler noe, stopper det med en norsk feilmelding og kode 1.

Stegene under er prøvd på John Inges Mac (Apple Silicon, macOS) med Apertium 3.9.12, lttoolbox 3.8.4, cg3 og apertium-nno-nob 1.6.0, alt bygd fra kilde og installert i `~/.local`. Det finnes ingen Homebrew-formel for språkparet, så bygging fra kilde er veien som er bekreftet.

---

## Steg 1: Sjekk hva som finnes

```
which apertium
apertium -l          # lister installerte moduser; se etter nob-nno og nno-nob
```

Viser `apertium -l` både `nob-nno` og `nno-nob`, er du ferdig. Gå til steg 5.

## Steg 2: Homebrew-pakker til bygget

```
brew install autoconf automake libtool pkg-config gawk utf8cpp boost rapidjson
```

`icu4c` måtte også til; den var installert fra før (her `icu4c@78`). `boost` og `rapidjson` ble krevd av byggene (cg3 og apertium-separable).

## Steg 3: Miljø

Lag en fil, for eksempel `~/Kilder/apertium/env.sh`, og kjør `source` på den i hvert nytt skall før bygging og kjøring:

```
export P=$HOME/.local
export PATH=$P/bin:/opt/homebrew/opt/libtool/libexec/gnubin:/opt/homebrew/bin:$PATH
export PKG_CONFIG_PATH=$P/lib/pkgconfig:$P/share/pkgconfig:/opt/homebrew/opt/icu4c@78/lib/pkgconfig:/opt/homebrew/lib/pkgconfig
export ACLOCAL_PATH=$P/share/aclocal:/opt/homebrew/share/aclocal
export CPPFLAGS="-I/opt/homebrew/opt/icu4c@78/include -I/opt/homebrew/include -I/opt/homebrew/include/utf8cpp"
export LDFLAGS="-L/opt/homebrew/opt/icu4c@78/lib -L/opt/homebrew/lib"
export CMAKE_PREFIX_PATH=$P:/opt/homebrew/opt/icu4c@78:/opt/homebrew
export ICU_ROOT=/opt/homebrew/opt/icu4c@78
```

Det som betyr noe:

- `CPPFLAGS` må ha `-I/opt/homebrew/include/utf8cpp`, ellers finner ikke bygget `utf8cpp`.
- ICU finnes med `ICU_ROOT` og `CMAKE_PREFIX_PATH=/opt/homebrew/opt/icu4c@78`.
- GNU-`libtool` (`libexec/gnubin`) står først i `PATH`.
- Endre `icu4c@78` hvis Homebrew har en annen versjon.
- Verktøyet trenger bare at `~/.local/bin` står i `PATH` når det kjører: `PATH=$HOME/.local/bin:$PATH uv run jv nynorsk …`. Datamappa finner det selv (`~/.local/share/apertium`, ved siden av programmene), eller i `APERTIUM_DATADIR`.

## Steg 4: Bygg fra kilde

Hent kildene til en egen mappe utenfor prosjektet (for eksempel `~/Kilder/apertium/`) fra disse repoene, i denne rekkefølgen:

1. `lttoolbox` (apertium)
2. `apertium` (apertium)
3. `apertium-lex-tools` (apertium)
4. `apertium-separable` (apertium)
5. `cg3` (GrammarSoft)
6. `apertium-nob` (apertium)
7. `apertium-nno` (apertium)
8. `apertium-nno-nob` (apertium)

**`lttoolbox` og `cg3` bygges med cmake**, og trenger at installasjonsnavn og rpath peker på `~/.local/lib`, ellers finner ikke programmene bibliotekene etterpå:

```
cmake -DCMAKE_INSTALL_PREFIX=$HOME/.local \
      -DCMAKE_INSTALL_NAME_DIR=$HOME/.local/lib \
      -DCMAKE_INSTALL_RPATH=$HOME/.local/lib \
      -DCMAKE_BUILD_TYPE=Release .
make
make install
```

**De andre** (`apertium`, `apertium-lex-tools`, `apertium-separable`, `apertium-nob`, `apertium-nno`, `apertium-nno-nob`) bygges med autotools mot samme prefiks:

```
./autogen.sh --prefix=$HOME/.local
make
make install
```

Språkdataene (`apertium-nob`, `apertium-nno`) må installeres før `apertium-nno-nob`. Advarsler om foreldede makroer («You should run autoupdate») i `autogen.sh` er ufarlige.

## Steg 5: Kontroller

```
PATH=$HOME/.local/bin:$PATH apertium -l
echo "Biblioteket holder åpent lenger om kvelden fra neste måned." | apertium nob-nno
echo "Biblioteket held ope lenger om kvelden frå neste månad." | apertium nno-nob
echo "Han skal xqztvik nå." | apertium nob-nno        # *xqztvik: ukjent ord
echo "Han skal svibrent nå." | apertium nob-nno       # #svibrent: kjent grunnform, bøyning mangler
```

Kjør så testene fra prosjektroten. Integrasjonstestene hoppes over hvis Apertium eller språkparet mangler, og kjøres ellers mot den ekte installasjonen:

```
PATH=$HOME/.local/bin:$PATH uv run --all-packages pytest verktoy/nynorsk -rs
```

## Slik tolker verktøyet utdata fra Apertium

Verktøyet gjør det samme som `apertium -f txt <modus>`, med teksten på stdin i UTF-8: det leser modusfila og kjører `apertium-destxt | <modus> | apertium-retxt` selv, uten bash og gawk. Det leser merkene Apertium selv setter:

- `*ord`: ukjent ord (type `unknown`). Merk at et ord som «fjordglimring» **ikke** gir `*`: Apertium deler det opp som et sammensatt ord og oversetter delene.
- `#ord` eller `på#drage`: grunnformen er kjent, men bøyningen kan ikke lages (type `generation`). Utdata viser da grunnformen, ikke den bøyde formen. `#` står vanligvis foran ordet, men kan også stå inne i det.
- `@ord`: mangler i den tospråklige ordboken (type `untranslated`). Ikke observert i 12 000 prøveord, men håndteres.

`-u` fjerner bare `*`, ikke `#` eller `@`, så verktøyet bruker ikke `-u`. Tegnene `*`, `#` og `@` som står i selve teksten (Markdown `**fet**`, `#emneknagg`, `@navn`) sendes aldri til Apertium, for ekte Apertium flytter og dupliserer dem. Teksten deles ved dem, og de settes tilbake etterpå.

Andre forhold som er bekreftet mot ekte Apertium:

- **Linjeskift:** `\n`, `\n\n` og `\n\n\n` bevares tegn for tegn (men en enkelt `\n` rett etter enkelte ord, som «var», kan få et ekstra linjeskift, så bitene skilles med en blank linje) med `-f txt`. Avsluttende linjeskift beholdes.
- **500 kohorter:** mange linjer uten setningsslutt gir `Warning: Hard limit of 500 cohorts reached … forcing break.` fra `cg-proc` på stderr (kode 0). Avsnitt glir ikke over i hverandre av den grunn, men DOCX deles likevel i grupper på rundt 300 ord per Apertium-kall for å holde seg trygt under grensen.
- **Locale:** får du rare tegn for æ, ø og å, sett `export LC_ALL=en_US.UTF-8`.
- **Varianter:** paret har også moduser som `nob-nno_e` (e-infinitiv). Verktøyet bruker bare standardmodusene `nob-nno` og `nno-nob`.
