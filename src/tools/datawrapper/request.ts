// Valgene på skjermen «Klargjør for Datawrapper», og hvordan de blir til
// forespørsler til Rust (`jv_run`, hvitelisten i src-tauri/src/tools/jv/args.rs).
// Rene funksjoner, uten Tauri og uten DOM.

import { fileName } from "../../lib/files";
import type { RunRequest } from "../jv/api";
import { dirName } from "../jv/paths";
import type { Analysis, SheetInfo } from "./report";

export interface Choices {
  /** Arket brukeren ser på, eller `null` før analysen er lest. */
  sheet: string | null;
  /** Tabellnummer i arket (fra 1), eller `null` før analysen er lest. */
  table: number | null;
  withSums: boolean;
  transpose: boolean;
  /**
   * Kolonner brukeren har klikket bort. Nummer fra 1 i tabellen etter
   * sumfjerning og bytte, slik `lag` teller dem. Alltid sortert og uten dubletter.
   */
  removed: number[];
}

export function initialChoices(): Choices {
  return { sheet: null, table: null, withSums: false, transpose: false, removed: [] };
}

/** Foreslått ark og tabell fra analysen. Alt annet nullstilles. */
export function choicesFromAnalysis(a: Analysis, keep: Pick<Choices, "withSums" | "transpose"> = { withSums: false, transpose: false }): Choices {
  const sheet = a.sheets.find((s) => s.name === a.suggestedSheet && s.tables.length > 0) ?? a.sheets.find((s) => s.tables.length > 0) ?? null;
  return { sheet: sheet?.name ?? null, table: sheet ? suggestedTable(sheet) : null, withSums: keep.withSums, transpose: keep.transpose, removed: [] };
}

export function suggestedTable(s: SheetInfo): number | null {
  if (s.tables.length === 0) return null;
  return s.suggestedTable ?? s.tables.find((t) => t.suggested)?.index ?? (s.tables[0] as { index: number }).index;
}

/** Nytt ark: tabellen verktøyet foreslår der, og ingen fjernede kolonner (tallene gjelder en annen tabell). */
export function withSheet(c: Choices, a: Analysis, name: string): Choices {
  const sheet = a.sheets.find((s) => s.name === name && s.tables.length > 0);
  if (!sheet) return c;
  return { ...c, sheet: sheet.name, table: suggestedTable(sheet), removed: [] };
}

export function withTable(c: Choices, table: number): Choices {
  return { ...c, table, removed: [] };
}

/** Ta med sumrader eller bytt: kolonnenumrene flytter seg, så fjernede kolonner nullstilles. */
export function withSums(c: Choices, on: boolean): Choices {
  return { ...c, withSums: on, removed: [] };
}

export function withTranspose(c: Choices, on: boolean): Choices {
  return { ...c, transpose: on, removed: [] };
}

/** Fjerner kolonne `index` (fra 1). Ingen endring hvis den allerede er borte. */
export function removeColumn(c: Choices, index: number): Choices {
  if (!Number.isInteger(index) || index < 1 || c.removed.includes(index)) return c;
  return { ...c, removed: [...c.removed, index].sort((x, y) => x - y) };
}

/** Angrer fjerning av én kolonne. */
export function restoreColumn(c: Choices, index: number): Choices {
  return c.removed.includes(index) ? { ...c, removed: c.removed.filter((i) => i !== index) } : c;
}

export function restoreAllColumns(c: Choices): Choices {
  return c.removed.length === 0 ? c : { ...c, removed: [] };
}

export function buildAnalyseRequest(file: string): RunRequest {
  return { command: "analyser", inputs: [file], options: {} };
}

/**
 * `lag`. Arket sendes bare når det er et annet enn det verktøyet foreslår, og
 * tabellen bare når arket har flere. Uten disse velger verktøyet selv det samme
 * som analysen foreslo. Det holder arknavn som Rust ikke slipper gjennom
 * (hvitelisten avviser blant annet «/» og «[») borte fra vanlige filer.
 */
export function buildLagRequest(file: string, c: Choices, a: Analysis | null, csvFile?: string): RunRequest {
  const options: RunRequest["options"] = {};
  const sheetInfo = a?.sheets.find((s) => s.name === c.sheet);
  if (c.sheet !== null && a && c.sheet !== a.suggestedSheet) options.sheet = c.sheet;
  if (c.table !== null && sheetInfo && sheetInfo.tables.length > 1) options.table = c.table;
  if (c.withSums) options.with_sums = true;
  if (c.transpose) options.transpose = true;
  if (c.removed.length > 0) options.remove_columns = [...c.removed];
  if (csvFile) options.csv_file = csvFile;
  return { command: "lag", inputs: [file], options };
}

/** Foreslått filnavn i lagre-dialogen: samme mappe og navn som originalen, med `.csv`. */
export function defaultCsvPath(file: string): string {
  const dir = dirName(file);
  const name = fileName(file).replace(/\.[^./\\]*$/, "") || "tabell";
  if (dir === "") return `${name}.csv`;
  const sep = file.includes("\\") && !file.includes("/") ? "\\" : "/";
  return dir.endsWith("/") || dir.endsWith("\\") ? `${dir}${name}.csv` : `${dir}${sep}${name}.csv`;
}

/** Verktøyet godtar bare stier som ender på `.csv`. */
export function ensureCsvExtension(path: string): string {
  return /\.csv$/i.test(path) ? path : `${path}.csv`;
}
