// Kjør: node --test tools/
import assert from "node:assert/strict";
import { test } from "node:test";
import { assetNames, buildLatest } from "./lag-latest-json.mjs";

test("filnavn passer med nedlastingssiden (.dmg for Mac, setup.exe for Windows, bare ASCII)", () => {
  const n = assetNames("0.2.0");
  assert.match(n.dmg, /aarch64.*\.dmg$/);
  assert.match(n.exe, /setup\.exe$/i);
  for (const f of Object.values(n)) assert.match(f, /^[A-Za-z0-9._-]+$/);
  // Siden skal bare finne én .dmg og én setup.exe, og ingen .msi (signaturene slutter på .sig)
  const names = Object.values(n);
  assert.equal(names.filter((f) => /\.dmg$/i.test(f)).length, 1);
  assert.equal(names.filter((f) => /setup\.exe$/i.test(f)).length, 1);
  assert.equal(names.filter((f) => /\.msi$/i.test(f)).length, 0);
});

test("latest.json har riktige adresser og signaturer", () => {
  const j = buildLatest({ version: "0.2.0", notes: "Nytt", macSig: "AAA\n", exeSig: "BBB\n", date: new Date("2026-01-01T00:00:00Z") });
  assert.equal(j.version, "0.2.0");
  assert.equal(j.pub_date, "2026-01-01T00:00:00.000Z");
  assert.equal(j.platforms["darwin-aarch64"].signature, "AAA");
  assert.equal(
    j.platforms["windows-x86_64"].url,
    "https://github.com/JohnLLA/lla-verktoykasse-releases/releases/download/v0.2.0/LLAs-verktoykasse_0.2.0_x64-setup.exe",
  );
  assert.match(j.platforms["darwin-aarch64"].url, /_aarch64\.app\.tar\.gz$/);
});

test("avviser ugyldig versjon og tom signatur", () => {
  assert.throws(() => buildLatest({ version: "v0.2", macSig: "a", exeSig: "b" }));
  assert.throws(() => buildLatest({ version: "0.2.0", macSig: " ", exeSig: "b" }));
});
