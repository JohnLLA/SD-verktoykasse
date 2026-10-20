// Kontrakten mot Rust-modulen jv: feilkoder, kommandoer, hendelser og typer her
// må stemme med Rust-filene. Filene leses som tekst (`?raw`), så testen feiler
// hvis noen endrer bare den ene siden.

import { describe, expect, it } from "vitest";
import argsRsRaw from "../../../src-tauri/src/tools/jv/args.rs?raw";
import catalogRsRaw from "../../../src-tauri/src/tools/jv/catalog.rs?raw";
import commandNamesRsRaw from "../../../src-tauri/src/tools/jv/command_names.rs?raw";
import commandsRsRaw from "../../../src-tauri/src/tools/jv/commands.rs?raw";
import errorRsRaw from "../../../src-tauri/src/tools/jv/error.rs?raw";
import planRsRaw from "../../../src-tauri/src/tools/jv/plan.rs?raw";
import serviceRsRaw from "../../../src-tauri/src/tools/jv/service.rs?raw";
import { t } from "../../i18n/nb";
import { menuGroups, tools } from "../registry";
import { schema as compare } from "../compare/schema";
import { schema as keyframes } from "../keyframes/schema";
import { schema as loudness } from "../loudness/schema";
import { schema as metadata } from "../metadata/schema";
import { schema as nynorsk } from "../nynorsk/schema";
import { schema as ocr } from "../ocr/schema";
import { schema as pdfTables } from "../pdf-tables/schema";
import { schema as datawrapper } from "../datawrapper/schema";
import { schema as redact } from "../redact/schema";
import { schema as subtitles } from "../subtitles/schema";
import { JV_COMMANDS, JV_ERROR_CODES, JV_EVENTS, JV_TOOL_IDS } from "./api";

const ALL_SCHEMAS = [compare, metadata, keyframes, loudness, subtitles, pdfTables, datawrapper, ocr, redact, nynorsk];

const lf = (s: string) => s.replace(/\r\n/g, "\n");
const errorRs = lf(errorRsRaw);
const commandsRs = lf(commandsRsRaw);
const commandNamesRs = lf(commandNamesRsRaw);
const catalogRs = lf(catalogRsRaw);
const serviceRs = lf(serviceRsRaw);
const planRs = lf(planRsRaw);
const argsRs = lf(argsRsRaw);

const snake = (s: string) => s.replace(/(?<!^)([A-Z])/g, "_$1").toLowerCase();

function enumVariants(src: string, name: string): string[] {
  const start = src.indexOf(`pub enum ${name} {`);
  expect(start, `fant ikke enum ${name}`).toBeGreaterThan(-1);
  const body = src.slice(start, src.indexOf("\n}\n", start));
  return [...body.matchAll(/^ {4}([A-Z][A-Za-z0-9]*)\b/gm)].map((m) => m[1] as string);
}

function structFields(src: string, name: string): string[] {
  const start = src.indexOf(`pub struct ${name} {`);
  expect(start, `fant struct ${name}`).toBeGreaterThan(-1);
  const body = src.slice(start, src.indexOf("\n}\n", start));
  return [...body.matchAll(/^ {4}pub ([a-z0-9_]+):/gm)].map((m) => m[1] as string);
}

describe("kontrakt mot Rust (jv)", () => {
  it("har en feilkode og en tekst for hver feil i error.rs, i samme rekkefølge", () => {
    expect(JV_ERROR_CODES).toEqual(enumVariants(errorRs, "JvError").map(snake));
    for (const code of JV_ERROR_CODES) expect(typeof t.jvErrors[code], code).toBe("function");
  });

  it("kaller kommandoene Rust har registrert", () => {
    const rust = [...commandNamesRs.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    expect([...JV_COMMANDS]).toEqual(rust);
  });

  it("lytter på hendelsene Rust sender", () => {
    const ev = Object.fromEntries([...commandsRs.matchAll(/pub const (EV_[A-Z_]+): &str = "([a-z:-]+)";/g)].map((m) => [m[1], m[2]]));
    expect(JV_EVENTS.installProgress).toBe(ev.EV_INSTALL_PROGRESS);
    expect(JV_EVENTS.installDone).toBe(ev.EV_INSTALL_DONE);
    expect(JV_EVENTS.runProgress).toBe(ev.EV_RUN_PROGRESS);
    expect(JV_EVENTS.runDone).toBe(ev.EV_RUN_DONE);
  });

  it("kjenner de samme verktøyene som Rust, i samme rekkefølge", () => {
    const start = catalogRs.indexOf("pub const KNOWN_TOOLS");
    const body = catalogRs.slice(start, catalogRs.indexOf("];", start));
    const rust = [...body.matchAll(/"([a-z-]+)"/g)].map((m) => m[1]);
    expect([...JV_TOOL_IDS]).toEqual(rust);
  });

  it("bruker statusene Rust sender", () => {
    expect(enumVariants(serviceRs, "ToolStatus").map(snake)).toEqual(["available", "needs_newer_app", "needs_newer_os", "not_for_platform", "unknown"]);
    expect(enumVariants(serviceRs, "InstallPhase").map(snake)).toEqual(["download", "install"]);
    expect(enumVariants(commandsRs, "Outcome").map(snake)).toEqual(["completed", "cancelled", "failed"]);
  });

  it("har feltene Rust sender i katalogen og i listen over installerte", () => {
    expect(structFields(catalogRs, "CatalogEntry")).toEqual(["id", "name", "version", "target", "url", "bytes", "sha256", "min_app_version", "min_os", "notes"]);
    expect(structFields(serviceRs, "ToolView")).toEqual(["id", "status", "entry", "installed_version", "update_available"]);
    expect(structFields(serviceRs, "CatalogView")).toEqual(["target", "source", "error", "tools"]);
    expect(structFields(serviceRs, "InstalledView")).toEqual(["id", "name", "version", "bytes", "license"]);
  });

  it("har planfeltene Rust sender (type heter `kind` i Rust og `type` i JSON)", () => {
    expect(structFields(planRs, "PlanItem")).toEqual(["id", "kind", "page", "excerpt", "placement", "redact", "rejected", "reason"]);
    expect(planRs).toContain('#[serde(rename = "type")]');
  });

  it("sender bare valg Rust godtar (hvitelisten i args.rs)", () => {
    for (const schema of ALL_SCHEMAS) {
      for (const f of schema.fields) {
        const keys: string[] = [];
        if (f.kind === "choice") for (const o of f.options) keys.push(...Object.keys(o.options ?? {}));
        else keys.push(f.optionKey);
        for (const k of keys) expect(argsRs, `${schema.id}: ${k}`).toContain(`"${k}"`);
      }
    }
    expect(argsRs).toContain('"plan_file"');
  });

  it("har registrert alle elleve verktøyene, hvert i én menygruppe, Transkribering først", () => {
    const ids = tools.map((x) => x.id);
    expect(ids[0]).toBe("transkribering");
    expect(new Set(ids).size).toBe(11);
    for (const id of JV_TOOL_IDS) expect(ids).toContain(id);
    const grouped = menuGroups.flatMap((g) => g.ids);
    expect([...grouped].sort()).toEqual([...ids].sort());
    expect(menuGroups[0]?.ids[0]).toBe("transkribering");
    expect(menuGroups.map((g) => g.label)).toEqual(["Lyd og video", "Dokumenter", "Språk"]);
  });
});
