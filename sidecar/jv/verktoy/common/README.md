# jv-common

Felles kode for journalistverktøyene: JSON-rapport, trygge utstier, norske
feilmeldinger, fremdrift på stderr, sjekk av systemprogrammer og kommandoen `jv`.

```
uv run jv --list
uv run jv <id> <inngang...> --out <mappe> [valg]
```

Verktøy registreres med et entry point i gruppen `jv.tools` som peker på
`main(argv) -> int`. Endres bare av agenten `samler`.
