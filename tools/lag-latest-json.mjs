#!/usr/bin/env node
// Lager latest.json for Tauri sin updater (og sjekker at alle filene finnes).
// Bare Node sin standardbibliotek.
//
//   node tools/lag-latest-json.mjs --version 0.2.0 --dir release-filer \
//        [--notes-file notater.md] [--repo JohnLLA/lla-verktoykasse-releases] [--out latest.json]
//
// Filnavnene er en avtale med nedlastingssiden (site/lla-no/verktoy.html, som
// velger fil på endelsen .dmg, og .msi eller setup.exe for Windows) og med release-arbeidsflyten:
//   LLAs-verktoykasse_<versjon>_aarch64.dmg           Mac, til nedlasting
//   LLAs-verktoykasse_<versjon>_aarch64.app.tar.gz    Mac, til updater (+ .sig)
//   LLAs-verktoykasse_<versjon>_x64-setup.exe         Windows (NSIS, per bruker uten administrator), til nedlasting og updater (+ .sig)

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export const DEFAULT_REPO = "JohnLLA/lla-verktoykasse-releases";

export function assetNames(version) {
  const base = `LLAs-verktoykasse_${version}`;
  return {
    dmg: `${base}_aarch64.dmg`,
    macUpdate: `${base}_aarch64.app.tar.gz`,
    macSig: `${base}_aarch64.app.tar.gz.sig`,
    exe: `${base}_x64-setup.exe`,
    exeSig: `${base}_x64-setup.exe.sig`,
  };
}

export function buildLatest({ version, notes, repo = DEFAULT_REPO, macSig, exeSig, date = new Date() }) {
  if (!/^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/.test(version)) throw new Error(`Ugyldig versjon: ${version}`);
  const n = assetNames(version);
  const url = (name) => `https://github.com/${repo}/releases/download/v${version}/${encodeURIComponent(name)}`;
  const mac = { signature: macSig.trim(), url: url(n.macUpdate) };
  const win = { signature: exeSig.trim(), url: url(n.exe) };
  if (!mac.signature || !win.signature) throw new Error("Tom signatur.");
  return {
    version,
    notes: notes ?? "",
    pub_date: date.toISOString(),
    platforms: {
      "darwin-aarch64": mac,
      "darwin-aarch64-app": mac,
      "windows-x86_64": win,
      "windows-x86_64-nsis": win,
    },
  };
}

function main() {
  const args = Object.fromEntries(
    process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
  );
  const { version, dir } = args;
  if (!version || !dir) throw new Error("Bruk: --version X.Y.Z --dir mappe [--notes-file fil] [--repo eier/repo] [--out fil]");
  const n = assetNames(version);
  for (const f of Object.values(n)) {
    if (!existsSync(join(dir, f))) throw new Error(`Mangler ${f} i ${dir}`);
  }
  const latest = buildLatest({
    version,
    repo: args.repo,
    notes: args["notes-file"] ? readFileSync(args["notes-file"], "utf8").trim() : "",
    macSig: readFileSync(join(dir, n.macSig), "utf8"),
    exeSig: readFileSync(join(dir, n.exeSig), "utf8"),
  });
  writeFileSync(args.out ?? join(dir, "latest.json"), JSON.stringify(latest, null, 2) + "\n");
  console.log(`latest.json for ${version}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  try {
    main();
  } catch (e) {
    console.error(String(e.message ?? e));
    process.exit(1);
  }
}
