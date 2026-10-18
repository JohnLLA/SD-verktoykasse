import { describe, expect, it } from "vitest";
import { fileExtension, fileName, isSupportedExtension } from "./files";

describe("filnavn", () => {
  it("tar siste del av stien, Mac og Windows", () => {
    expect(fileName("/Users/kari/Intervju æøå.mp3")).toBe("Intervju æøå.mp3");
    expect(fileName("C:\\Users\\Ola\\Opptak 1.m4a")).toBe("Opptak 1.m4a");
    expect(fileName("\\\\server\\delt\\møte.wav")).toBe("møte.wav");
    expect(fileName("/mappe/")).toBe("mappe");
  });
  it("finner filendelsen i små bokstaver", () => {
    expect(fileExtension("/a/b/Intervju.MP3")).toBe("mp3");
    expect(fileExtension("/a/b/arkiv.tar.gz")).toBe("gz");
    expect(fileExtension("/a/b/uten-endelse")).toBe("");
    expect(fileExtension("/a/b/.skjult")).toBe("");
    expect(fileExtension("/a/b/slutter.")).toBe("");
  });
  it("kjenner formatene verktøyet leser", () => {
    for (const ext of ["mp3", "m4a", "wav", "flac", "ogg", "mp4", "mov", "MP3"]) {
      expect(isSupportedExtension(`/x/fil.${ext}`)).toBe(true);
    }
    for (const ext of ["webm", "opus", "caf", "aiff", "wma", "txt"]) {
      expect(isSupportedExtension(`/x/fil.${ext}`)).toBe(false);
    }
    expect(isSupportedExtension("/x/mappe")).toBe(false);
  });
});
