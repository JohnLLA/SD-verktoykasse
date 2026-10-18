import { describe, expect, it } from "vitest";
import { ERROR_CODES, type CoreError } from "../tools/transkribering/api";
import { errorSentence, errorText, isCancelled, toCoreError } from "./errors";

/** Ett eksempel per feilkode, med feltene Rust sender. */
const SAMPLES: CoreError[] = [
  { code: "file_not_found" },
  { code: "unsupported_format", format: "webm" },
  { code: "no_audio_track" },
  { code: "empty_audio" },
  { code: "decode_failed" },
  { code: "unknown_model" },
  { code: "model_missing", model_id: "nb-whisper-medium-semantic-q5_0" },
  { code: "model_load_failed" },
  { code: "model_in_shared_folder" },
  { code: "invalid_catalog", reason: "x" },
  { code: "host_not_allowed", host: "example.com" },
  { code: "http_status", status: 503 },
  { code: "network" },
  { code: "checksum_mismatch" },
  { code: "size_mismatch" },
  { code: "disk_full" },
  { code: "cpu_unsupported", missing: ["avx2", "fma"] },
  { code: "busy" },
  { code: "already_downloading" },
  { code: "cancelled" },
  { code: "whisper", whisper_code: -3 },
  { code: "file_exists" },
  { code: "not_a_directory" },
  { code: "invalid_path" },
  { code: "permission_denied" },
  { code: "io", kind: "Other" },
  { code: "internal" },
];

describe("feilkoder og tekster", () => {
  it("har et eksempel for hver feilkode", () => {
    expect(SAMPLES.map((s) => s.code)).toEqual([...ERROR_CODES]);
  });

  it("har en tekst for hver feilkode, med tittel", () => {
    for (const e of SAMPLES) {
      const text = errorText(e);
      expect(text.title.length, e.code).toBeGreaterThan(0);
      if (e.code !== "cancelled") expect(text.hint.length, e.code).toBeGreaterThan(0);
    }
  });

  it("lekker aldri tekniske felt, koder eller stakkspor til brukeren", () => {
    for (const e of SAMPLES) {
      const s = errorSentence(e);
      expect(s).not.toMatch(/\b(undefined|null|NaN|Error|panic|stack|whisper_code|http_status|\{|\})/i);
      expect(s).not.toContain("example.com");
      expect(s).not.toContain("nb-whisper");
      expect(s).not.toContain("-3");
    }
  });

  it("foreslår mp3 eller wav og nevner formatet når filtypen ikke støttes", () => {
    const s = errorSentence({ code: "unsupported_format", format: "webm" });
    expect(s).toContain("webm");
    expect(s).toMatch(/mp3 eller wav/);
    expect(s).toMatch(/mp3, m4a, wav, flac, ogg, mp4 og mov/);
  });

  it("klarer seg uten formatnavn", () => {
    const s = errorSentence({ code: "unsupported_format", format: "" });
    expect(s).not.toContain("«»");
    expect(s).toMatch(/mp3 eller wav/);
  });

  it("sier at maskinen mangler en funksjon når prosessoren er for gammel", () => {
    const s = errorSentence({ code: "cpu_unsupported", missing: ["avx2"] });
    expect(s).toMatch(/for gammel/);
    expect(s).toContain("avx2");
  });

  it("sier fra om nett, sjekksum og diskplass med råd", () => {
    expect(errorSentence({ code: "network" })).toMatch(/nett/);
    expect(errorSentence({ code: "checksum_mismatch" })).toMatch(/laste ned på nytt/i);
    expect(errorSentence({ code: "disk_full" })).toMatch(/plass/);
  });
});

describe("toCoreError", () => {
  it("godtar feil fra Rust slik de er", () => {
    const e = { code: "unsupported_format", format: "caf" };
    expect(toCoreError(e)).toBe(e);
  });
  it("gjør alt annet om til en intern feil uten å ta med teksten", () => {
    expect(toCoreError("command plugin:transkribering|x not allowed")).toEqual({ code: "internal" });
    expect(toCoreError(new Error("/Users/kari/hemmelig.mp3"))).toEqual({ code: "internal" });
    expect(toCoreError({ code: "finnes-ikke" })).toEqual({ code: "internal" });
    expect(toCoreError(null)).toEqual({ code: "internal" });
  });
  it("kjenner avbrutt", () => {
    expect(isCancelled({ code: "cancelled" })).toBe(true);
    expect(isCancelled({ code: "busy" })).toBe(false);
  });
});
