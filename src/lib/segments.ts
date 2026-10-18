// Segmenter: finne segmentet som spilles, og rette tekst.

import type { Segment } from "../tools/transkribering/api";

/**
 * Indeksen til segmentet som hører til et punkt i lyden: det siste som har
 * begynt. `-1` før første segment. Segmentene er sortert på starttid.
 */
export function segmentIndexAt(segments: readonly Segment[], ms: number): number {
  let lo = 0;
  let hi = segments.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const s = segments[mid];
    if (s && s.start_ms <= ms) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

/**
 * Tekst fra et redigerbart felt: linjeskift og tabulatorer blir mellomrom, og
 * mellomrom i endene fjernes. Ellers røres ikke teksten (lydrett tekst får
 * ikke stor forbokstav eller tegnsetting, regel 4).
 */
export function normalizeEditedText(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}

/** All tekst i ett stykke, uten tidskoder, til «Kopier alt». */
export function plainText(segments: readonly Segment[]): string {
  return segments
    .map((s) => s.text.trim())
    .filter((s) => s.length > 0)
    .join(" ");
}

/** Slutten av siste segment, til tidskodenes bredde. */
export function lastEndMs(segments: readonly Segment[]): number {
  return segments.reduce((max, s) => Math.max(max, s.end_ms), 0);
}
