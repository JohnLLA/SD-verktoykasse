# Senere

Ønsker som ikke bygges i v1. Se «Utenfor v1» i spesifikasjon-v1.md.

## Journalistverktøy: avhengigheter som venter

- **pymupdf 2.0.** `pdf-tables`, `ocr`, `redact` og `compare` holdes på 1.x (`pymupdf>=1.24,<2`).
  2.0 drar inn nye avhengigheter: onnxruntime, numpy, pymupdf-layout og pymupdf4llm (regel 7).
  Besluttet av John Inge i steg 6.5 (22.10.2026).
- **pikepdf 10.14 eller nyere.** `ocr` og `metadata` er låst til `pikepdf>=10,<10.14` (10.13.0.post1).
  Fra 10.14 finnes det bare hjul for macOS 15 eller nyere (arm64), og da krever pakkene macOS 15.
  Låsen gjør at `ocrmypdf` blir på 17.12.1, fordi 17.13 krever pikepdf 10.15 eller nyere.
  Låsen oppheves når minstekravet for Mac-pakkene er macOS 15, eller når pikepdf bygges fra kildekode.
