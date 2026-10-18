// Kontrast (WCAG AA) for fargene i theme.css, lys og mørk.

import { describe, expect, it } from "vitest";
import themeCss from "./theme.css?raw";

function parseTokens(block: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of block.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    out.set(m[1] as string, (m[2] as string).toLowerCase());
  }
  return out;
}

const darkStart = themeCss.indexOf("@media (prefers-color-scheme: dark)");
const light = parseTokens(themeCss.slice(0, darkStart));
const dark = new Map([...light, ...parseTokens(themeCss.slice(darkStart))]);

function luminance(hex: string): number {
  const ch = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = ch.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** Tekst mot bakgrunn: minst 4,5:1. */
const TEXT_PAIRS: [string, string][] = [
  ["text", "bg"],
  ["text", "surface"],
  ["text", "surface-2"],
  ["text", "accent-soft"],
  ["text-muted", "bg"],
  ["text-muted", "surface"],
  ["text-muted", "surface-2"],
  ["on-accent", "accent"],
  ["gold", "bg"],
  ["gold", "surface"],
  ["gold", "surface-2"],
  ["gold", "accent-soft"],
  ["danger", "danger-bg"],
  ["danger", "surface"],
  ["text", "danger-bg"],
  ["on-danger-solid", "danger-solid"],
  ["success", "success-bg"],
  ["success", "bg"],
  ["success", "surface"],
  ["warning", "warning-bg"],
  ["bg", "text"], // meldingen nederst: bg-tekst på text-bakgrunn
];

/** Kantlinjer, fokusring og andre deler av grensesnittet: minst 3:1. */
const UI_PAIRS: [string, string][] = [
  ["border-strong", "surface"],
  ["border-strong", "bg"],
  ["border-strong", "surface-2"],
  ["focus", "bg"],
  ["focus", "surface"],
  ["gold", "surface-2"], // framdriftslinjen mot sporet
  ["accent", "bg"],
  ["accent", "surface"],
  ["danger", "danger-bg"],
];

describe.each([
  ["lys", light],
  ["mørk", dark],
])("kontrast, %s modus", (_name, tokens) => {
  it.each(TEXT_PAIRS)("%s på %s har minst 4,5:1", (fg, bg) => {
    const a = tokens.get(fg);
    const b = tokens.get(bg);
    expect(a, fg).toBeDefined();
    expect(b, bg).toBeDefined();
    expect(contrast(a as string, b as string)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(UI_PAIRS)("%s mot %s har minst 3:1", (fg, bg) => {
    expect(contrast(tokens.get(fg) as string, tokens.get(bg) as string)).toBeGreaterThanOrEqual(3);
  });
});

describe("tema", () => {
  it("har samme fargenavn i lys og mørk modus", () => {
    const darkOnly = parseTokens(themeCss.slice(darkStart));
    for (const key of darkOnly.keys()) expect(light.has(key), key).toBe(true);
    for (const key of light.keys()) expect(darkOnly.has(key), `${key} mangler i mørk`).toBe(true);
  });
});
