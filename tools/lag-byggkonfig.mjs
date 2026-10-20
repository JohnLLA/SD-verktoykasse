#!/usr/bin/env node
// Lager tillegget til tauri.conf.json som release-arbeidsflyten sender med
// `tauri build --config <fil>`. Repoets konfigurasjon forblir uten signering,
// så et vanlig bygg uten hemmeligheter alltid virker. Bare Node sin standardbibliotek.
//
//   node tools/lag-byggkonfig.mjs ut.json
// Styres med miljøvariabler (satt av arbeidsflyten):
//   UPDATER_SIGN     "true" hvis oppdateringspakkene skal signeres (ellers lages de ikke)
//   WIN_MODE         none | certificate | trusted-signing
//   WIN_THUMBPRINT, WIN_TIMESTAMP_URL                         (certificate)
//   TS_ENDPOINT, TS_ACCOUNT, TS_PROFILE                        (trusted-signing)

import { writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export function buildConfig(env) {
  const conf = { bundle: { createUpdaterArtifacts: env.UPDATER_SIGN === "true" } };
  const mode = env.WIN_MODE || "none";
  if (mode === "certificate") {
    if (!env.WIN_THUMBPRINT) throw new Error("WIN_THUMBPRINT mangler.");
    conf.bundle.windows = {
      certificateThumbprint: env.WIN_THUMBPRINT,
      digestAlgorithm: "sha256",
      timestampUrl: env.WIN_TIMESTAMP_URL || "http://timestamp.digicert.com",
    };
  } else if (mode === "trusted-signing") {
    for (const k of ["TS_ENDPOINT", "TS_ACCOUNT", "TS_PROFILE"]) {
      if (!env[k]) throw new Error(`${k} mangler.`);
    }
    conf.bundle.windows = {
      signCommand: {
        cmd: "trusted-signing-cli",
        args: ["-e", env.TS_ENDPOINT, "-a", env.TS_ACCOUNT, "-c", env.TS_PROFILE, "-d", "SD-Verktøy", "%1"],
      },
    };
  } else if (mode !== "none") {
    throw new Error(`Ukjent WIN_MODE: ${mode}`);
  }
  return conf;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  try {
    const out = process.argv[2];
    if (!out) throw new Error("Bruk: node tools/lag-byggkonfig.mjs ut.json");
    writeFileSync(out, JSON.stringify(buildConfig(process.env), null, 2) + "\n");
  } catch (e) {
    console.error(String(e.message ?? e));
    process.exit(1);
  }
}
