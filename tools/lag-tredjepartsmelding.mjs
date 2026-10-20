#!/usr/bin/env node
// Lager tredjepartsmeldingen med full lisenstekst (src/assets/tredjepart.txt),
// som Om-vinduet viser. Bare Node sin standardbibliotek; ingen nye avhengigheter.
//
//   node tools/lag-tredjepartsmelding.mjs          skriver filen
//   node tools/lag-tredjepartsmelding.mjs --check  feiler hvis filen er utdatert
//
// Kilder:
//  - Rust: `cargo metadata --locked` for Mac (arm64) og Windows (x64), dvs. det
//    som faktisk havner i appen. Lisensfilene leses fra cargo-registeret.
//  - npm: pakkene i `dependencies` i package.json og deres egne `dependencies`,
//    lest fra node_modules (kjør `npm ci` først).
//  - Whisper.cpp (følger med whisper-rs-sys) og NB-Whisper (modellene, som
//    lastes ned og ikke følger med) legges til for hånd.
// Er det ingen lisensfil i en komponent, brukes standardteksten for lisensen
// som er oppgitt i Cargo.toml / package.json, og forfatterne står i listen.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "src", "assets", "tredjepart.txt");
const TARGETS = ["aarch64-apple-darwin", "x86_64-pc-windows-msvc"];
const LICENSE_FILE = /^(licen[cs]e|copying|unlicense|notice)([-_. ].*)?$/i;

// Enkel sammenligning på tegnkoder: samme rekkefølge på alle maskiner (localeCompare avhenger av ICU).
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

const norm = (s) =>
  s.replace(/\r\n?/g, "\n").split("\n").map((l) => l.replace(/\s+$/, "")).join("\n").trim();

// ---- standardtekster
const MIT = `Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.`;
const BSD3 = `Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.`;
const ZLIB = `This software is provided 'as-is', without any express or implied warranty. In no event will the authors be held liable for any damages arising from the use of this software.

Permission is granted to anyone to use this software for any purpose, including commercial applications, and to alter it and redistribute it freely, subject to the following restrictions:

1. The origin of this software must not be misrepresented; you must not claim that you wrote the original software. If you use this software in a product, an acknowledgment in the product documentation would be appreciated but is not required.
2. Altered source versions must be plainly marked as such, and must not be misrepresented as being the original software.
3. This notice may not be removed or altered from any source distribution.`;

/** Standardtekster for SPDX-id-er. Apache og MPL hentes fra komponenter som har dem i sin helhet. */
const standard = new Map([
  ["MIT", MIT],
  ["BSD-3-Clause", BSD3],
  ["Zlib", ZLIB],
]);
const SIGNATURES = {
  "Apache-2.0": /Apache License\s+Version 2\.0, January 2004/,
  "Unlicense": /This is free and unencumbered software released into the public domain/,
  "MPL-2.0": /Mozilla Public License Version 2\.0\n=+/,
};

function run(cmd, args) {
  const r = spawnSync(cmd, args, { cwd: ROOT, encoding: "utf8", maxBuffer: 1 << 28 });
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(" ")} feilet:\n${r.stderr}`);
  return r.stdout;
}

function licenseFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile() && LICENSE_FILE.test(e.name))
    .map((e) => e.name)
    .sort()
    .map((n) => norm(readFileSync(join(dir, n), "utf8")))
    .filter((t) => t.length > 0);
}

// ---- samle komponenter
/** @type {{name:string, version:string, license:string, authors:string[], texts:string[], source:string}[]} */
const components = [];

const cargoPkgs = new Map();
for (const target of TARGETS) {
  const m = JSON.parse(run("cargo", ["metadata", "--format-version", "1", "--locked", "--manifest-path", "src-tauri/Cargo.toml", "--filter-platform", target]));
  const ids = new Set(m.resolve.nodes.map((n) => n.id));
  const root = m.resolve.root;
  for (const p of m.packages) {
    if (ids.has(p.id) && p.id !== root && p.source) cargoPkgs.set(`${p.name}@${p.version}`, p);
  }
}
for (const p of cargoPkgs.values()) {
  const dir = dirname(p.manifest_path);
  components.push({
    name: p.name,
    version: p.version,
    license: p.license ?? p.license_file ?? "ukjent",
    authors: (p.authors ?? []).map((a) => a.replace(/\s*<[^>]*>/, "")),
    texts: licenseFiles(dir),
    source: "rust",
    dir,
  });
}

// npm: bare det som havner i appen (dependencies, rekursivt)
{
  const pj = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  const seen = new Set();
  const walk = (name) => {
    if (seen.has(name)) return;
    seen.add(name);
    const dir = join(ROOT, "node_modules", name);
    if (!existsSync(join(dir, "package.json"))) throw new Error(`Mangler node_modules/${name}. Kjør npm ci.`);
    const p = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
    const author = typeof p.author === "string" ? p.author.replace(/\s*[<(][^>)]*[>)]/g, "") : p.author?.name;
    components.push({
      name: p.name,
      version: p.version,
      license: typeof p.license === "string" ? p.license : "ukjent",
      authors: author ? [author] : [],
      texts: licenseFiles(dir),
      source: "npm",
      dir,
    });
    for (const dep of Object.keys(p.dependencies ?? {})) walk(dep);
  };
  for (const dep of Object.keys(pj.dependencies ?? {})) walk(dep);
}

components.sort((a, b) => cmp(a.name, b.name) || cmp(a.version, b.version) || cmp(a.source, b.source));

// ---- finn full Apache- og MPL-tekst
const all = new Map(standard);
for (const [id, re] of Object.entries(SIGNATURES)) {
  const hit = components.flatMap((c) => c.texts).filter((t) => re.test(t)).sort((a, b) => a.length - b.length || cmp(a, b))[0];
  if (!hit) throw new Error(`Fant ikke full tekst for ${id} i noen komponent.`);
  all.set(id, hit);
}

// ---- whisper.cpp og NB-Whisper (for hånd)
const whisperSys = [...cargoPkgs.values()].find((p) => p.name === "whisper-rs-sys");
if (!whisperSys) throw new Error("whisper-rs-sys mangler i avhengighetene.");
const whisperText = licenseFiles(join(dirname(whisperSys.manifest_path), "whisper.cpp")).find((t) => /MIT License/i.test(t));
if (!whisperText) throw new Error("Fant ikke lisensen til whisper.cpp.");

// ---- grupper på lisenstekst
/** @type {Map<string, {text:string, users:string[]}>} */
const groups = new Map();
const add = (key, text, user) => {
  const g = groups.get(key) ?? { text, users: [] };
  g.users.push(user);
  groups.set(key, g);
};

for (const c of components.sort((a, b) => cmp(a.name, b.name) || cmp(a.version, b.version) || cmp(a.source, b.source))) {
  const label = `${c.name} ${c.version}` + (c.authors.length ? ` (${c.authors.join(", ")})` : "");
  if (c.texts.length > 0) {
    for (const t of c.texts) add("h:" + createHash("sha256").update(t).digest("hex"), t, label);
  } else {
    const ids = c.license.split(/\s+(?:OR|AND|WITH)\s+|[()/]/).map((s) => s.trim()).filter(Boolean);
    const known = ids.filter((id) => all.has(id));
    if (known.length === 0) throw new Error(`Ingen lisenstekst for ${c.name} (${c.license}).`);
    // Ved «A OR B» holder én av tekstene; ta den første vi har.
    const id = known.includes("MIT") ? "MIT" : known[0];
    add("s:" + id, all.get(id), label);
  }
}

{
  const apache = all.get("Apache-2.0");
  add("h:" + createHash("sha256").update(apache).digest("hex"), apache, "NB-Whisper-modellene (Nasjonalbibliotekets KI-lab, NbAiLab)");
}

const extra = [
  {
    title: "NB-Whisper (språkmodellene)",
    body: "Modellene NB-Whisper er laget av Nasjonalbibliotekets KI-lab (NbAiLab) og lisensiert under Apache License 2.0. De følger ikke med appen, men lastes ned fra Hugging Face når du ber om det. Full lisenstekst står blant tekstene under (Apache License 2.0).\nhttps://huggingface.co/NbAiLab",
  },
  {
    title: "whisper.cpp og ggml",
    body: "whisper.cpp og ggml av Georgi Gerganov og bidragsytere, lenket inn i appen via whisper-rs-sys.\n\n" + whisperText,
  },
];

// ---- skriv
const out = [];
out.push("TREDJEPARTSLISENSER FOR SD-VERKTØY");
out.push("=".repeat(33));
out.push("");
out.push("Verktøykassen bygger på åpen kildekode og åpne modeller. Her står hele lisensteksten for hver komponent som følger med appen, og hvem som har skrevet dem. Teksten er laget automatisk fra lisensfilene i komponentene (tools/lag-tredjepartsmelding.mjs).");
out.push("");
for (const e of extra) {
  out.push("-".repeat(72), e.title, "-".repeat(72), "", e.body, "");
}
out.push("");
out.push("KOMPONENTER OG LISENSTEKSTER");
out.push("=".repeat(28));
out.push("");
out.push("Hver lisenstekst står én gang, med listen over komponentene den gjelder for. Der en komponent ikke har med lisensfil, står standardteksten for lisensen den oppgir, og opphavsrettshaverne står i parentes ved navnet.");
out.push("");
const sorted = [...groups.values()].sort((a, b) => b.users.length - a.users.length || cmp(a.text, b.text));
sorted.forEach((g, i) => {
  out.push("-".repeat(72));
  out.push(`Lisenstekst ${i + 1} av ${sorted.length}`);
  out.push("-".repeat(72));
  out.push("Gjelder:");
  for (const u of [...new Set(g.users)].sort(cmp)) out.push("  " + u);
  out.push("");
  out.push(g.text);
  out.push("");
});
const text = out.join("\n") + "\n";

if (process.argv.includes("--check")) {
  const current = existsSync(OUT) ? readFileSync(OUT, "utf8") : "";
  if (current !== text) {
    console.error("src/assets/tredjepart.txt er utdatert. Kjør: node tools/lag-tredjepartsmelding.mjs");
    const a = new Set(current.split("\n"));
    const b = new Set(text.split("\n"));
    const only = (x, y) => [...x].filter((l) => !y.has(l)).slice(0, 15).map((l) => "    " + l.slice(0, 120));
    console.error("  Bare i generert:\n" + only(b, a).join("\n"));
    console.error("  Bare i filen:\n" + only(a, b).join("\n"));
    process.exit(1);
  }
  console.log(`tredjepart.txt er oppdatert (${components.length} komponenter, ${sorted.length} lisenstekster).`);
} else {
  writeFileSync(OUT, text);
  console.log(`Skrev ${OUT}: ${components.length} komponenter, ${sorted.length} lisenstekster, ${(text.length / 1024).toFixed(0)} kB.`);
}
