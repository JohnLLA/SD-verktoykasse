# Steg 6: journalistverktøyene inn i verktøykassen

Verktøykassen blir et skall med samme utseende som Transkribering. De ni verktøyene fra `Verktoy2_0` står i menyen og lastes ned inne i appen når brukeren vil ha dem. Agenten `sidecar-bygger` lager verktøypakkene, den signerte katalogen og Rust-delen som laster ned og kjører dem. De andre agentene får egne briefer for dette steget.

## Installer

```
sh oppsett/installer.sh
```

Skriptet kopierer `sidecar-bygger.md` til `.claude/agents/`. Spesifikasjonen og briefene ligger allerede i `docs/`.

## Flyt

1. **Ta beslutningene under først.**
2. «Bruk sidecar-bygger på spiken.» Les `docs/spike-sidecar.md` når den er ferdig.
3. «Bruk sidecar-bygger på steg 6.2.»
4. «Bruk grensesnittbygger på docs/brief-jv-grensesnitt.md.»
5. «Bruk kontraktvokter på PR #N med docs/brief-jv-kontroll.md» for hver PR.
6. «Bruk byggmester på docs/brief-jv-distribusjon.md.»
7. Lag release-repoet og tokenet, og push taggen selv, som beskrevet i `docs/release.md`.
8. Publiser `site/lla-no/verktoy.html` på lla.no.

## Beslutninger før start

**Bestemt:** kildekoden skal være offentlig, og bare kode med fri lisens brukes.
- Verktøykassen får lisensen AGPL-3.0-or-later. Lisensteksten ligger i `LICENSE` i roten.
- Lisenskontrollen i CI stopper alt annet.
- Før du gjør `JohnLLA/lla-verktoykasse` offentlig, går du gjennom sjekklisten i `docs/publisering.md`, som byggmester lager. Den dekker hemmeligheter i historikken, opphavet til testlyd og testfiler, og persondata.

**Også bestemt 19.10.2026:**
- ffmpeg brukes av `keyframes` og `loudness` gjennom sidecaren. Regel 8 gjelder fortsatt transkriberingen.
- Bokmål ↔ nynorsk kommer først på Mac. Windows kommer når Apertium lar seg pakke der.
- Mac først: skallet og de ni Mac-pakkene publiseres før Windows-pakkene (runde A og B i spesifikasjonen).
- Verktøyene lastes ned i appen, ikke bygget inn. Det gir et tredje nettkall: katalog og pakker fra release-repoet, bare når brukeren ber om det.

Alle beslutningene er tatt. Start med «bruk sidecar-bygger på spiken».
