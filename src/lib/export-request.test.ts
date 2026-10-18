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
};

describe("eksportforespørsel", () => {
  it("tilbyr txt med og uten tidskoder, srt, vtt og docx", () => {
    expect(SAVE_OPTIONS.map((o) => `${o.format}:${o.timestamps}`)).toEqual([
      "docx:true",
      "txt:true",
      "txt:false",
      "srt:false",
      "vtt:false",
    ]);
  });

  it("bruker standard filnavn og mappe (ingen målsti) og spør før overskriving", () => {
    const r = buildExportRequest({ ...base, option: saveOption("docx") });
    expect(r.target_path).toBeNull();
    expect(r.overwrite).toBe(false);
    expect(r.audio_path).toBe(base.audioPath);
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

  it("sender valgt sted og bekreftet overskriving", () => {
    const r = buildExportRequest({
      ...base,
      option: saveOption("vtt"),
      targetPath: "/Users/kari/Skrivebord/min.vtt",
      overwrite: true,
    });
    expect(r.target_path).toBe("/Users/kari/Skrivebord/min.vtt");
    expect(r.overwrite).toBe(true);
  });
});
