// Kontrakten mot Rust-kjernen: feilkoder, kommandoer, hendelser og typer her
// må stemme med Rust-filene. Filene leses som tekst (`?raw`), så testen
// feiler hvis noen endrer bare den ene siden.

import { describe, expect, it } from "vitest";
import errorRsRaw from "../../../src-tauri/src/tools/transkribering/error.rs?raw";
import commandsRsRaw from "../../../src-tauri/src/tools/transkribering/commands.rs?raw";
import commandNamesRsRaw from "../../../src-tauri/src/tools/transkribering/command_names.rs?raw";
import exportRsRaw from "../../../src-tauri/src/tools/transkribering/export.rs?raw";
import typesRsRaw from "../../../src-tauri/src/tools/transkribering/types.rs?raw";
import { COMMANDS, ERROR_CODES, EVENTS, MODEL_DIR_KEY, SETTINGS_FILE } from "./api";
import { t } from "../../i18n/nb";

/** Som serdes `snake_case`: understrek foran hver stor bokstav, bortsett fra den første. */
// Windows kan sjekke ut filene med CRLF.
const lf = (s: string) => s.replace(/\r\n/g, "\n");
const errorRs = lf(errorRsRaw);
const commandsRs = lf(commandsRsRaw);
const commandNamesRs = lf(commandNamesRsRaw);
const exportRs = lf(exportRsRaw);
const typesRs = lf(typesRsRaw);

const snake = (s: string) => s.replace(/(?<!^)([A-Z])/g, "_$1").toLowerCase();

function enumVariants(src: string, name: string): string[] {
  const start = src.indexOf(`pub enum ${name} {`);
  expect(start, `fant ikke enum ${name}`).toBeGreaterThan(-1);
  const body = src.slice(start, src.indexOf("\n}\n", start));
  return [...body.matchAll(/^ {4}([A-Z][A-Za-z0-9]*)\b/gm)].map((m) => m[1] as string);
}

describe("kontrakt mot Rust", () => {
  it("har en feilkode i språkfilen for hver feil i error.rs, i samme rekkefølge", () => {
    expect(ERROR_CODES).toEqual(enumVariants(errorRs, "CoreError").map(snake));
    for (const code of ERROR_CODES) expect(typeof t.errors[code], code).toBe("function");
  });

  it("kaller kommandoene Rust har registrert", () => {
    const rust = [...commandNamesRs.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    expect([...COMMANDS]).toEqual(rust);
  });

  it("lytter på hendelsene Rust sender", () => {
    const rustEvents = Object.fromEntries(
      [...commandsRs.matchAll(/pub const (EV_[A-Z_]+): &str = "([a-z:-]+)";/g)].map((m) => [m[1], m[2]]),
    );
    expect(EVENTS.progress).toBe(rustEvents.EV_PROGRESS);
    expect(EVENTS.segment).toBe(rustEvents.EV_SEGMENT);
    expect(EVENTS.done).toBe(rustEvents.EV_DONE);
    expect(EVENTS.downloadProgress).toBe(rustEvents.EV_DOWNLOAD_PROGRESS);
    expect(EVENTS.downloadDone).toBe(rustEvents.EV_DOWNLOAD_DONE);
  });

  it("bruker samme innstillingsfil og nøkkel som Rust leser modellmappen fra", () => {
    expect(commandsRs).toContain(`pub const SETTINGS_FILE: &str = "${SETTINGS_FILE}";`);
    expect(commandsRs).toContain(`pub const MODEL_DIR_KEY: &str = "${MODEL_DIR_KEY}";`);
  });

  it("bruker identifikatorene Rust forventer for målform, stil og kvalitet", () => {
    expect(typesRs).toContain('#[serde(rename = "bokmål")]');
    expect(typesRs).toContain('#[serde(rename = "nynorsk")]');
    expect(enumVariants(typesRs, "Stil").map((s) => s.toLowerCase())).toEqual(["lydrett", "tolket"]);
    expect(enumVariants(typesRs, "Kvalitet").map((s) => s.toLowerCase())).toEqual([
      "rask",
      "anbefalt",
      "best",
    ]);
    expect(enumVariants(typesRs, "Decoding").map(snake)).toEqual(["beam5", "greedy"]);
  });

  it("sender alle topptekstene Rust ber om (HeaderLabels)", () => {
    const start = exportRs.indexOf("pub struct HeaderLabels {");
    const body = exportRs.slice(start, exportRs.indexOf("\n}\n", start));
    const fields = [...body.matchAll(/pub ([a-z_]+): String/g)].map((m) => m[1]).sort();
    expect(Object.keys(t.headerLabels).sort()).toEqual(fields);
    for (const v of Object.values(t.headerLabels)) expect(v.length).toBeGreaterThan(0);
  });

  it("har eksportformatene Rust kjenner", () => {
    expect(enumVariants(exportRs, "ExportFormat").map((s) => s.toLowerCase())).toEqual([
      "txt",
      "srt",
      "vtt",
      "docx",
    ]);
  });
});
