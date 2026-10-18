import { describe, expect, it } from "vitest";
import type { Segment } from "../tools/transkribering/api";
import { lastEndMs, normalizeEditedText, plainText, segmentIndexAt } from "./segments";

const segs: Segment[] = [
  { start_ms: 0, end_ms: 4_000, text: "første" },
  { start_ms: 4_000, end_ms: 9_000, text: "andre" },
  { start_ms: 12_000, end_ms: 15_000, text: "tredje" },
];

describe("segmentIndexAt", () => {
  it("finner siste segment som har begynt", () => {
    expect(segmentIndexAt(segs, 0)).toBe(0);
    expect(segmentIndexAt(segs, 3_999)).toBe(0);
    expect(segmentIndexAt(segs, 4_000)).toBe(1);
    expect(segmentIndexAt(segs, 10_000)).toBe(1); // pause mellom segmentene
    expect(segmentIndexAt(segs, 99_000)).toBe(2);
  });
  it("gir -1 før første segment og for tom liste", () => {
    expect(segmentIndexAt([{ start_ms: 500, end_ms: 900, text: "x" }], 100)).toBe(-1);
    expect(segmentIndexAt([], 100)).toBe(-1);
  });
});

describe("rettet tekst", () => {
  it("gjør linjeskift til mellomrom og trimmer", () => {
    expect(normalizeEditedText("  hei\nverden \t og  hei\r\n")).toBe("hei verden og hei");
  });
  it("rører ikke store bokstaver eller tegnsetting (lydrett)", () => {
    expect(normalizeEditedText("og så sa han ikke noe")).toBe("og så sa han ikke noe");
  });
});

describe("samlet tekst", () => {
  it("setter segmentene sammen uten tidskoder og hopper over tomme", () => {
    expect(plainText([...segs, { start_ms: 16_000, end_ms: 17_000, text: "  " }])).toBe(
      "første andre tredje",
    );
  });
  it("finner slutten av lyden", () => {
    expect(lastEndMs(segs)).toBe(15_000);
    expect(lastEndMs([])).toBe(0);
  });
});
