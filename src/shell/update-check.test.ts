import { describe, expect, it } from "vitest";
import { KEYS, MemorySettings } from "../lib/settings";
import type { UpdateCheckResult } from "../platform/types";
import { runManualUpdateCheck, runStartupUpdateCheck, type UpdateCheckDeps } from "./update-check";

function setup(opts: { now?: UpdateCheckResult; switchOn?: boolean; version?: string | null; installOk?: boolean; confirm?: boolean }) {
  const settings = new MemorySettings();
  if (opts.switchOn !== undefined) settings.data.set(KEYS.versionCheck, opts.switchOn);
  const calls: string[] = [];
  let onInstall: (() => void) | undefined;
  let onRetry: (() => void) | undefined;
  const deps: UpdateCheckDeps = {
    platform: {
      settings,
      async checkForUpdate() {
        calls.push("check");
        return opts.version ?? null;
      },
      async checkForUpdateNow() {
        calls.push("now");
        return opts.now ?? { status: "none" };
      },
      async installUpdate() {
        calls.push("install");
        return opts.installOk ?? true;
      },
    },
    notice: {
      show(v, cb) {
        calls.push(`show:${v}`);
        onInstall = cb;
      },
      installing() {
        calls.push("installing");
      },
      failed(cb) {
        calls.push("failed");
        onRetry = cb;
      },
    },
    confirmInstall: async () => opts.confirm ?? true,
  };
  return { deps, calls, install: () => onInstall?.(), retry: () => onRetry?.() };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

describe("versjonssjekk ved oppstart", () => {
  it("gjør ingen nettkall når bryteren er av", async () => {
    const s = setup({ switchOn: false, version: "9.9.9" });
    expect(await runStartupUpdateCheck(s.deps)).toBe(false);
    expect(s.calls).toEqual([]);
  });

  it("sjekker når bryteren er på, også som standard (aldri satt)", async () => {
    const s = setup({ version: null });
    expect(await runStartupUpdateCheck(s.deps)).toBe(true);
    expect(s.calls).toEqual(["check"]);
  });

  it("viser varselet bare hvis det finnes en ny versjon", async () => {
    const s = setup({ switchOn: true, version: "0.2.0" });
    await runStartupUpdateCheck(s.deps);
    expect(s.calls).toEqual(["check", "show:0.2.0"]);
  });

  it("installerer først når brukeren trykker, og viser feil med nytt forsøk", async () => {
    const s = setup({ version: "0.2.0", installOk: false });
    await runStartupUpdateCheck(s.deps);
    expect(s.calls).not.toContain("install");
    s.install();
    await tick();
    expect(s.calls.slice(2)).toEqual(["installing", "install", "failed"]);
    s.retry();
    await tick();
    expect(s.calls.filter((c) => c === "install")).toHaveLength(2);
  });

  it("installerer ikke hvis brukeren velger å vente", async () => {
    const s = setup({ version: "0.2.0", confirm: false });
    await runStartupUpdateCheck(s.deps);
    s.install();
    await tick();
    expect(s.calls).toEqual(["check", "show:0.2.0"]);
  });

  describe("Se etter ny versjon nå", () => {
    it("sjekker også når den automatiske sjekken er av, og viser samme varsel", async () => {
      const s = setup({ switchOn: false, now: { status: "available", version: "0.3.0" } });
      expect(await runStartupUpdateCheck(s.deps)).toBe(false);
      expect(s.calls).toEqual([]);
      expect(await runManualUpdateCheck(s.deps)).toEqual({ status: "available", version: "0.3.0" });
      expect(s.calls).toEqual(["now", "show:0.3.0"]);
      s.install();
      await tick();
      expect(s.calls).toContain("install");
    });

    it("gjør ingen nettkall før den trykkes", async () => {
      const s = setup({ switchOn: false });
      await runStartupUpdateCheck(s.deps);
      expect(s.calls).not.toContain("now");
    });

    it("ingen ny versjon eller feil gir ikke noe varsel", async () => {
      for (const now of [{ status: "none" }, { status: "failed" }] as UpdateCheckResult[]) {
        const s = setup({ now });
        expect((await runManualUpdateCheck(s.deps)).status).toBe(now.status);
        expect(s.calls).toEqual(["now"]);
      }
    });
  });
});
