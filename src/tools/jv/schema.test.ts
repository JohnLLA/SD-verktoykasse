// Skjemaene gir riktige argumenter til `jv_run`, og filer og stier behandles riktig.

import { describe, expect, it } from "vitest";
import { schema as compare } from "../compare/schema";
import { schema as keyframes } from "../keyframes/schema";
import { schema as loudness } from "../loudness/schema";
import { schema as metadata } from "../metadata/schema";
import { schema as nynorsk } from "../nynorsk/schema";
import { schema as ocr } from "../ocr/schema";
import { PAGES_PATTERN, schema as pdfTables } from "../pdf-tables/schema";
import { schema as redact } from "../redact/schema";
import { schema as subtitles } from "../subtitles/schema";
import { defaultOutDir, dirName, findSummary, isAccepted, outputPath, partitionFiles } from "./paths";
import { buildRunRequest, commandFor, defaultValues, needsOutDir, valuesValid } from "./schema";

const req = (schema: Parameters<typeof defaultValues>[0], inputs: string[], over: Record<string, string | number | boolean> = {}) => {
  const values = { ...defaultValues(schema), ...over };
  return buildRunRequest(schema, values, inputs, "/ut");
};

describe("skjemaer gir riktige argumenter til jv_run", () => {
  it("compare: to filer og begge valgene", () => {
    expect(req(compare, ["/a.docx", "/b.docx"])).toEqual({
      inputs: ["/a.docx", "/b.docx"],
      out_dir: "/ut",
      options: { ignore_whitespace: true, ignore_case: false },
    });
    expect(req(compare, ["/a.txt", "/b.txt"], { ignore_whitespace: false, ignore_case: true }).options).toEqual({
      ignore_whitespace: false,
      ignore_case: true,
    });
  });

  it("metadata: «vis» har underkommando og ingen utmappe, «fjern» har begge", () => {
    expect(req(metadata, ["/a.jpg"])).toEqual({ command: "vis", inputs: ["/a.jpg"], options: {} });
    expect(req(metadata, ["/a.jpg"], { mode: "clean" })).toEqual({ command: "vask", inputs: ["/a.jpg"], out_dir: "/ut", options: {} });
    expect(needsOutDir(metadata, { mode: "show" })).toBe(false);
    expect(needsOutDir(metadata, { mode: "clean" })).toBe(true);
    expect(commandFor(metadata, { mode: "clean" })).toBe("vask");
  });

  it("keyframes: nøyaktig én av fast intervall og klipp", () => {
    expect(req(keyframes, ["/v.mp4"]).options).toEqual({ every_seconds: 2 });
    expect(req(keyframes, ["/v.mp4"], { every_seconds: 0.5 }).options).toEqual({ every_seconds: 0.5 });
    expect(req(keyframes, ["/v.mp4"], { mode: "scenes" }).options).toEqual({ scene_threshold: 0.3 });
    expect(req(keyframes, ["/v.mp4"], { mode: "scenes", sensitivity: "strict" }).options).toEqual({ scene_threshold: 0.5 });
  });

  it("loudness: mål", () => {
    expect(req(loudness, ["/a.wav"]).options).toEqual({ target: "podcast" });
    expect(req(loudness, ["/a.wav"], { target: "broadcast" }).options).toEqual({ target: "broadcast" });
  });

  it("subtitles: linjelengde og antall linjer", () => {
    expect(req(subtitles, ["/t.json"]).options).toEqual({ max_chars: 42, max_lines: 2 });
    expect(req(subtitles, ["/t.json"], { length: "short", lines: "one" }).options).toEqual({ max_chars: 32, max_lines: 1 });
  });

  it("pdf-tables: tomt sidefelt sender ingenting, ellers sidene", () => {
    expect(req(pdfTables, ["/a.pdf"]).options).toEqual({ merge: false, csv: false });
    expect(req(pdfTables, ["/a.pdf"], { pages: " 3-7 ", merge: true }).options).toEqual({ pages: "3-7", merge: true, csv: false });
    expect(PAGES_PATTERN.test("1,4-5")).toBe(true);
    expect(PAGES_PATTERN.test("3-")).toBe(false);
    expect(PAGES_PATTERN.test("a")).toBe(false);
    expect(valuesValid(pdfTables, { ...defaultValues(pdfTables), pages: "3-" })).toBe(false);
    expect(valuesValid(pdfTables, { ...defaultValues(pdfTables), pages: "" })).toBe(true);
  });

  it("ocr: tekstfil", () => {
    expect(req(ocr, ["/skann.pdf"]).options).toEqual({ text: false });
    expect(req(ocr, ["/skann.pdf"], { text: true }).options).toEqual({ text: true });
  });

  it("nynorsk: retning", () => {
    expect(req(nynorsk, ["/a.txt"]).options).toEqual({ to: "nn" });
    expect(req(nynorsk, ["/a.txt"], { to: "nb" }).options).toEqual({ to: "nb" });
    expect(nynorsk.draftNotice).toBe(true);
  });

  it("redact: underkommando og planfil kommer utenfra, ikke fra skjemaet", () => {
    const values = defaultValues(redact);
    expect(buildRunRequest(redact, values, ["/s.pdf"], "/ut", { terms_file: "/ord.txt" }, "finn")).toEqual({
      command: "finn",
      inputs: ["/s.pdf"],
      out_dir: "/ut",
      options: { terms_file: "/ord.txt" },
    });
    expect(buildRunRequest(redact, values, ["/s.pdf"], "/ut", { plan_file: "/s-treff.json" }, "sladd").options).toEqual({ plan_file: "/s-treff.json" });
  });

  it("tall utenfor grensene gir ugyldige valg", () => {
    expect(valuesValid(keyframes, { ...defaultValues(keyframes), every_seconds: 0 })).toBe(false);
    expect(valuesValid(keyframes, { ...defaultValues(keyframes), every_seconds: Number.NaN })).toBe(false);
    expect(valuesValid(keyframes, { ...defaultValues(keyframes), every_seconds: 3 })).toBe(true);
    // Skjulte felt teller ikke.
    expect(valuesValid(keyframes, { ...defaultValues(keyframes), mode: "scenes", every_seconds: 0 })).toBe(true);
  });
});

describe("filer og stier", () => {
  it("finner mappen til første fil, med både / og \\", () => {
    expect(dirName("/Users/kari/Saker/a.pdf")).toBe("/Users/kari/Saker");
    expect(dirName("C:\\Saker\\a.pdf")).toBe("C:\\Saker");
    expect(dirName("C:\\a.pdf")).toBe("C:\\");
    expect(dirName("/a.pdf")).toBe("/");
    expect(dirName("a.pdf")).toBe("");
    expect(defaultOutDir(["/x/y/a.pdf", "/z/b.pdf"])).toBe("/x/y");
    expect(defaultOutDir([])).toBeNull();
  });

  it("godtar filtyper skjemaet kjenner, og mapper bare der verktøyet tar mapper", () => {
    expect(isAccepted("/a/B.PDF", ocr)).toBe(true);
    expect(isAccepted("/a/skann.tif", ocr)).toBe(true);
    expect(isAccepted("/a/mappe", ocr)).toBe(true);
    expect(isAccepted("/a/mappe", pdfTables)).toBe(false);
    expect(isAccepted("/a/film.mov", pdfTables)).toBe(false);
  });

  it("sorterer filer og gir navnene på de som ikke passer", () => {
    expect(partitionFiles(["/a/x.pdf", "/a/film.mov", "/b/y.docx"], pdfTables)).toEqual({
      accepted: ["/a/x.pdf"],
      rejected: ["film.mov", "y.docx"],
    });
  });

  it("leser stien fra en rapportoppføring", () => {
    expect(outputPath("/ut/a.srt")).toBe("/ut/a.srt");
    expect(outputPath({ path: "/ut/a.pdf", sladdet: 2 })).toBe("/ut/a.pdf");
    expect(outputPath({ treff: 1 })).toBeNull();
    expect(outputPath(null)).toBeNull();
  });
});

describe("sladding: teksten over treffene", () => {
  it("lages av appen, uten kommandolinjen fra verktøyets egen setning", () => {
    expect(findSummary([])).toBe("Fant ingen treff.");
    expect(findSummary([{ rejected: false }])).toBe("Fant 1 treff.");
    expect(findSummary([{ rejected: false }, { rejected: false }, { rejected: true }])).toBe("Fant 2 treff. 1 mulig nummer ble forkastet.");
    expect(findSummary([{ rejected: true }, { rejected: true }])).toBe("Fant ingen treff. 2 mulige numre ble forkastet.");
    expect(findSummary([{ rejected: false }])).not.toMatch(/jv redact|--plan|\.json/);
  });
});
