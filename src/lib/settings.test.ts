import { describe, expect, it } from "vitest";
import { KEYS, MemorySettings, loadChoices, loadDecoding, loadVersionCheck, saveChoices, type SettingsStore } from "./settings";

describe("innstillinger", () => {
  it("husker siste valg", async () => {
    const s = new MemorySettings();
    expect(await loadChoices(s)).toEqual({ malform: "bokmål", stil: "tolket", kvalitet: "anbefalt" });
    await saveChoices(s, { malform: "nynorsk", stil: "lydrett", kvalitet: "rask" });
    expect(await loadChoices(s)).toEqual({ malform: "nynorsk", stil: "lydrett", kvalitet: "rask" });
  });
  it("har versjonssjekk på som standard", async () => {
    const s = new MemorySettings();
    expect(await loadVersionCheck(s)).toBe(true);
    await s.set(KEYS.versionCheck, false);
    expect(await loadVersionCheck(s)).toBe(false);
    await s.set(KEYS.versionCheck, "nei");
    expect(await loadVersionCheck(s)).toBe(true);
  });
  it("har beam som standard søkemåte", async () => {
    const s = new MemorySettings();
    expect(await loadDecoding(s)).toBe("beam5");
    await s.set(KEYS.decoding, "greedy");
    expect(await loadDecoding(s)).toBe("greedy");
  });
  it("gir standard hvis lageret svikter", async () => {
    const broken: SettingsStore = {
      get: () => Promise.reject(new Error("x")),
      set: () => Promise.reject(new Error("x")),
    };
    expect((await loadChoices(broken)).stil).toBe("tolket");
    expect(await loadVersionCheck(broken)).toBe(true);
    expect(await loadDecoding(broken)).toBe("beam5");
  });
  it("bruker nøkler som ikke kolliderer med modellmappen Rust leser", async () => {
    const all = Object.values(KEYS);
    expect(all).not.toContain("transkribering.modelDir");
    expect(new Set(all).size).toBe(all.length);
  });
});
