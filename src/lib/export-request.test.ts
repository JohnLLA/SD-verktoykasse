import { describe, expect, it } from "vitest";
import { t } from "../i18n/nb";
import { SAVE_OPTIONS, buildExportRequest, saveOption } from "./export-request";

const base = {
  audioPath: "/Users/kari/intervju.mp3",
  segments: [{ start_ms: 0, end_ms: 1500, text: "og så sa han" }],
  malform: "nynorsk" as const,
  stil: "lydrett" as const,
  modelId: "nb-whisper-small-verbatim-q5_0",
  now: new Date(2026, 9, 18, 14, 30),
  targetPath: "/Users/kari/intervju.nynorsk.lydrett.txt",
  overwrite: true,
};

describe("eksportforespørsel", () => {
  it("tilbyr docx og txt med og uten tidskoder, srt og vtt", () => {
    expect(SAVE_OPTIONS.map((o) => `${o.format}:${o.timestamps}`)).toEqual([
      "docx:true",
      "docx:false",
      "txt:true",
      "txt:false",
      "srt:false",
      "vtt:false",
    ]);
  });

  it("sender stien fra lagringsdialogen, og overwrite siden dialogen har spurt", () => {
    const r = buildExportRequest({ ...base, option: saveOption("docx-time") });
    expect(r.target_path).toBe(base.targetPath);
    expect(r.overwrite).toBe(true);
    expect(r.audio_path).toBe(base.audioPath);
  });

  it("lar docx være med eller uten tidskoder, som txt", () => {
    expect(buildExportRequest({ ...base, option: saveOption("docx-time") }).timestamps).toBe(true);
    const plain = buildExportRequest({ ...base, option: saveOption("docx-plain") });
    expect(plain.timestamps).toBe(false);
    expect(plain.format).toBe("docx");
  });

  it("tar med dato og topptekster fra språkfilen", () => {
    const r = buildExportRequest({ ...base, option: saveOption("txt-time") });
    expect(r.date).toBe("18. oktober 2026");
    expect(r.labels).toEqual(t.headerLabels);
    expect(r.labels.notice).toMatch(/maskintranskribert/);
    expect(r.timestamps).toBe(true);
    expect(r.format).toBe("txt");
  });

  it("sender teksten slik brukeren har rettet den, uten å endre den", () => {
    const r = buildExportRequest({ ...base, option: saveOption("srt") });
    expect(r.segments).toEqual([{ start_ms: 0, end_ms: 1500, text: "og så sa han" }]);
    expect(r.malform).toBe("nynorsk");
    expect(r.stil).toBe("lydrett");
    expect(r.model_id).toBe(base.modelId);
  });
});
