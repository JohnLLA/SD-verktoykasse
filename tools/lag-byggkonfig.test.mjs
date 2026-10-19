import assert from "node:assert/strict";
import { test } from "node:test";
import { buildConfig } from "./lag-byggkonfig.mjs";

test("uten signering lages ingen oppdateringspakker og ingen Windows-signering", () => {
  assert.deepEqual(buildConfig({}), { bundle: { createUpdaterArtifacts: false } });
});

test("sertifikat gir tommelfingeravtrykk og tidsstempel", () => {
  const c = buildConfig({ UPDATER_SIGN: "true", WIN_MODE: "certificate", WIN_THUMBPRINT: "ABC" });
  assert.equal(c.bundle.createUpdaterArtifacts, true);
  assert.equal(c.bundle.windows.certificateThumbprint, "ABC");
  assert.equal(c.bundle.windows.digestAlgorithm, "sha256");
});

test("Trusted Signing gir signCommand med %1 sist", () => {
  const c = buildConfig({ WIN_MODE: "trusted-signing", TS_ENDPOINT: "https://x", TS_ACCOUNT: "a", TS_PROFILE: "p" });
  assert.equal(c.bundle.windows.signCommand.args.at(-1), "%1");
});

test("feil i oppsettet stopper tydelig", () => {
  assert.throws(() => buildConfig({ WIN_MODE: "certificate" }));
  assert.throws(() => buildConfig({ WIN_MODE: "trusted-signing", TS_ENDPOINT: "x" }));
  assert.throws(() => buildConfig({ WIN_MODE: "annet" }));
});
