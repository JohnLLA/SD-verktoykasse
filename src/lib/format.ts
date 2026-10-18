// Formatering av størrelser, tidskoder, framdrift og datoer. Rene funksjoner,
// uten Tauri, så de kan testes med `npm test`. Tekster kommer fra språkfilen.

import { t } from "../i18n/nb";

const NBSP = " ";

/** Norsk tallformat med komma: 1,1. */
function decimal(n: number, digits: number): string {
  return n.toFixed(digits).replace(".", ",");
}

/**
 * Filstørrelse slik brukeren leser den: «539 MB», «1,1 GB». Desimale enheter
 * (1 MB = 1 000 000 byte), slik Windows og macOS oppgir filstørrelser.
 */
export function formatBytes(bytes: number): string {
  const b = Math.max(0, Number.isFinite(bytes) ? bytes : 0);
  if (b >= 1e9) {
    const gb = b / 1e9;
    return `${gb >= 10 ? Math.round(gb) : decimal(gb, 1)}${NBSP}${t.units.gb}`;
  }
  if (b >= 1e6) return `${Math.round(b / 1e6)}${NBSP}${t.units.mb}`;
  return `${Math.max(b > 0 ? 1 : 0, Math.round(b / 1e3))}${NBSP}${t.units.kb}`;
}

/**
 * Tidskode for et punkt i lyden: `03:07`, eller `1:03:07` når filen varer en
 * time eller mer (`withHours`). Rundes ned til hele sekunder, slik avspilleren
 * hopper dit.
 */
export function formatTimecode(ms: number, withHours = false): string {
  const total = Math.max(0, Math.floor((Number.isFinite(ms) ? ms : 0) / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return withHours || h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Framdrift som heltall 0–100, aldri over 100 og aldri NaN. */
export function clampPercent(p: number): number {
  if (!Number.isFinite(p)) return 0;
  return Math.min(100, Math.max(0, Math.floor(p)));
}

export function formatPercent(p: number): string {
  return t.transkribering.progress.percent(clampPercent(p));
}

/** Anslått gjenværende tid: «ca. 5 min igjen». `null` de første sekundene. */
export function formatEta(etaMs: number | null): string {
  const p = t.transkribering.progress;
  if (etaMs === null || !Number.isFinite(etaMs) || etaMs < 0) return p.etaUnknown;
  if (etaMs < 10_000) return p.etaSeconds;
  if (etaMs < 60_000) return p.etaLessThanMinute;
  const minutes = Math.ceil(etaMs / 60_000);
  if (minutes < 60) return p.etaMinutes(minutes);
  return p.etaHours(Math.floor(minutes / 60), minutes % 60);
}

/** Framdrift og tid i én linje: «42 % · ca. 3 min igjen». */
export function formatProgressLine(percent: number, etaMs: number | null): string {
  return `${formatPercent(percent)} · ${formatEta(etaMs)}`;
}

/** Lokal dato til toppen av eksporten: «18. oktober 2026». */
export function formatDate(d: Date): string {
  return t.dateLong(d);
}

/** Minnet i hele GB slik det står på esken (8, 16), ikke 7,8 eller 15,9. */
export function roundedGb(bytes: number): number {
  return Math.round(bytes / 2 ** 30);
}
