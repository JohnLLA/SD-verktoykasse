// Låser nettilgangen (regel 1, spesifikasjonen «Nettverk og personvern»):
// webvisningen har ingen nettilgang, og oppdateringen peker bare på releases-repoet.

import { describe, expect, it } from "vitest";
import capabilities from "../../src-tauri/capabilities/default.json";
import tauriConf from "../../src-tauri/tauri.conf.json";

const csp = (s: string) =>
  Object.fromEntries(s.split(";").map((d) => d.trim().split(/\s+/)).filter((p) => p[0]).map(([k, ...v]) => [k, v]));

describe("CSP", () => {
  for (const key of ["csp", "devCsp"] as const) {
    it(`${key}: connect-src tillater ikke noe nettsted`, () => {
      const directives = csp(tauriConf.app.security[key]);
      const connect = directives["connect-src"] ?? [];
      for (const src of connect) {
        expect(src).toMatch(/^(ipc:|http:\/\/ipc\.localhost|ws:\/\/localhost:1420)$/);
      }
      expect(directives["default-src"]).toEqual(["'self'"]);
      expect(directives["script-src"]).toEqual(["'self'"]);
    });
  }
});

describe("tillatelser", () => {
  it("webvisningen har ingen updater-, http-, fs- eller shell-tillatelser", () => {
    for (const p of capabilities.permissions) {
      expect(p).not.toMatch(/^(updater|http|fs|shell|process)/);
    }
  });
});

describe("oppdatering", () => {
  const u = tauriConf.plugins.updater;
  it("henter bare latest.json fra releases-repoet", () => {
    expect(u.endpoints).toEqual([
      "https://github.com/JohnLLA/lla-verktoykasse-releases/releases/latest/download/latest.json",
    ]);
  });
  it("lager oppdateringspakker", () => {
    expect(tauriConf.bundle.createUpdaterArtifacts).toBe(true);
  });
});
