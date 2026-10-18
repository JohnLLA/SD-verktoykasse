import { describe, expect, it } from "vitest";
import {
  clampPercent,
  formatBytes,
  formatDate,
  formatEta,
  formatPercent,
  formatProgressLine,
  formatTimecode,
  roundedGb,
} from "./format";

const NB = "\u00a0";

describe("formatTimecode", () => {
  it("bruker mm:ss under en time", () => {
    expect(formatTimecode(0)).toBe("00:00");
    expect(formatTimecode(7_000)).toBe("00:07");
    expect(formatTimecode(187_000)).toBe("03:07");
    expect(formatTimecode(3_599_999)).toBe("59:59");
  });
  it("runder ned til hele sekunder", () => {
    expect(formatTimecode(1_999)).toBe("00:01");
  });
  it("bruker t:mm:ss fra én time, eller når timer er bedt om", () => {
    expect(formatTimecode(3_600_000)).toBe("1:00:00");
    expect(formatTimecode(3_787_000)).toBe("1:03:07");
    expect(formatTimecode(36_000_000 + 59_000)).toBe("10:00:59");
    expect(formatTimecode(5_000, true)).toBe("0:00:05");
  });
  it("tåler ugyldige tall", () => {
    expect(formatTimecode(-5)).toBe("00:00");
    expect(formatTimecode(Number.NaN)).toBe("00:00");
  });
});

describe("framdrift", () => {
  it("holder prosent mellom 0 og 100", () => {
    expect(clampPercent(-3)).toBe(0);
    expect(clampPercent(42.9)).toBe(42);
    expect(clampPercent(140)).toBe(100);
    expect(clampPercent(Number.NaN)).toBe(0);
  });
  it("skriver prosent med hardt mellomrom", () => {
    expect(formatPercent(42.7)).toBe(`42${NB}%`);
  });
  it("skriver gjenværende tid på norsk", () => {
    expect(formatEta(null)).toBe("Beregner tid …");
    expect(formatEta(4_000)).toBe("noen sekunder igjen");
    expect(formatEta(45_000)).toBe("under ett minutt igjen");
    expect(formatEta(60_000)).toBe("ca. 1 min igjen");
    expect(formatEta(61_000)).toBe("ca. 2 min igjen");
    expect(formatEta(59 * 60_000)).toBe("ca. 59 min igjen");
    expect(formatEta(60 * 60_000)).toBe("ca. 1 t igjen");
    expect(formatEta(80 * 60_000)).toBe("ca. 1 t 20 min igjen");
  });
  it("setter prosent og tid sammen", () => {
    expect(formatProgressLine(42, 185_000)).toBe(`42${NB}% · ca. 4 min igjen`);
    expect(formatProgressLine(1, null)).toBe(`1${NB}% · Beregner tid …`);
  });
});

describe("formatBytes", () => {
  it("bruker MB og GB med komma", () => {
    expect(formatBytes(175_209_680)).toBe(`175${NB}MB`);
    expect(formatBytes(539_212_484)).toBe(`539${NB}MB`);
    expect(formatBytes(1_081_140_203)).toBe(`1,1${NB}GB`);
    expect(formatBytes(3_095_033_483)).toBe(`3,1${NB}GB`);
    expect(formatBytes(12_500_000_000)).toBe(`13${NB}GB`);
  });
  it("tåler små og ugyldige tall", () => {
    expect(formatBytes(0)).toBe(`0${NB}kB`);
    expect(formatBytes(300)).toBe(`1${NB}kB`);
    expect(formatBytes(Number.NaN)).toBe(`0${NB}kB`);
  });
});

describe("dato og minne", () => {
  it("skriver lokal dato på norsk", () => {
    expect(formatDate(new Date(2026, 9, 18))).toBe("18. oktober 2026");
    expect(formatDate(new Date(2027, 0, 3))).toBe("3. januar 2027");
  });
  it("runder minne til GB på esken", () => {
    expect(roundedGb(17_179_869_184)).toBe(16);
    expect(roundedGb(8 * 2 ** 30 - 200_000_000)).toBe(8);
  });
});
