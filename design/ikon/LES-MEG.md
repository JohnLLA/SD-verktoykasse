# App-ikon for LLAs verktøykasse

- `lla-verktoykasse-ikon.svg`: kilden, i vektor. «LLA» er gjort om til konturer (Inter Display Bold, SIL OFL), så ingen skrift trengs.
- `ikon-1024.png`: 1024 × 1024 med ekte gjennomsiktighet. Følger Apples rutenett for macOS-ikoner: 824 × 824 flate med 100 px marg og skygge.
- `LLA-verktoykasse.icns`: ferdig macOS-ikon, 16–1024 px.
- `LLA-verktoykasse.iconset/`: de enkelte størrelsene, for `iconutil -c icns LLA-verktoykasse.iconset`.
- `LLA-verktoykasse.ico`: Windows-ikon, 16–256 px.

I Tauri lager du alle ikonene appen trenger, i én kommando fra prosjektroten:

    npx tauri icon design/ikon/ikon-1024.png

Kommandoen skriver over `src-tauri/icons/`.
